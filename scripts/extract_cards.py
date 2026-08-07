"""Run the card prompts over papers and write cards, with provenance.

The prompts in inputs/prompts/ are self-contained contracts: each declares its
fields in a machine-readable block and explains its own field semantics. That
makes a card a model-agnostic artifact, and it makes the bulk extraction pass
runnable on a cheaper backend than the agent driving the survey. This script is
what makes that possible without losing track of who produced what.

Every card it writes records the prompt's digest and the exact model id.
**Cards produced by two models are two different artifacts**, exactly as cards
produced by two prompt versions are, so the runner refuses to mix models within
one card type.

Nothing here edits a card that already exists. A wrong card is flagged, never
fixed: --verify-evidence reports, and stops.

Usage:
    python extract_cards.py --type method --keys gasse2019exact,ibarz2022generalist \\
            --backend vertex --model <model-id>
    python extract_cards.py --type theory --all --backend vertex --model <model-id>
    python extract_cards.py --type method --keys k1,k2 --backend fake --model test --dry-run
    python extract_cards.py --verify-evidence
    python extract_cards.py --verify-evidence --type method
"""

import argparse
import difflib
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

import backends
from common import (Progress, add_project_arg, card_problems, die, find_project,
                    load_prompts, now_iso, parse_card, print_json)

# Roughly four characters to a token. Good enough to decide whether a run is
# affordable; never presented as a measurement.
CHARS_PER_TOKEN = 4

# A whole paper, not a whole corpus. Truncation is reported per key.
DEFAULT_MAX_CHARS = 600_000

FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*$")
LEADING_FRONT_MATTER = re.compile(r"\A\s*---\s*\n.*?\n---\s*\n", re.S)
PAGE_REF = re.compile(
    r"[\s,;]*[\(\[]\s*(?:pp?\.?|pages?)\s*[^)\]]*[\)\]]\s*$", re.I)
QUOTED = re.compile(r"[\"“”„‟']([^\"“”„‟']{8,})[\"“”„‟']")

QUOTE_CHARS = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "–": "-", "—": "-", "‒": "-", "−": "-", "‐": "-",
    " ": " ", "…": ".",
})

NEAR_MATCH_RATIO = 0.90


# --------------------------------------------------------------------------
# reading files
# --------------------------------------------------------------------------
#
# Extracted PDF text carries mojibake and NUL bytes. Every read here is Python
# with errors="ignore"; nothing shells out to grep, which on macOS treats a file
# containing a NUL as binary and silently matches nothing in it.

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def fulltext_path(project: Path, bibkey: str) -> Path:
    return project / "inputs" / "fulltext" / f"{bibkey}.md"


def card_path(project: Path, card_type: str, bibkey: str) -> Path:
    return project / "inputs" / "cards" / card_type / f"{bibkey}.md"


def prompt_path(project: Path, card_type: str) -> Path:
    return project / "inputs" / "prompts" / f"{card_type}_card.md"


def prompt_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------
# building the request
# --------------------------------------------------------------------------

FIELD_BLOCK = re.compile(r"```fields\s*\n.*?```", re.S)

INSTRUCTIONS = """
---

The paper's full text follows between the markers. Extract exactly one card
from it.

Output the card as plain `field: value` lines and nothing else. One field per
line. No preamble, no closing remarks, no markdown fences, no front matter.

- Emit every field the block above declares as `required`.
- For a field flagged `evidence`, emit a sibling `<field>_evidence` line holding
  a **verbatim** quote from the text below and a page number, like:
  `purpose_evidence: "the exact words from the paper" (p. 7)`.
  Quote what the paper actually says. Do not paraphrase, reconstruct, or
  compose a quote.
- `not reported` means the paper did not say. It is not the same as `none`,
  which means the paper says there is none. Prefer `not reported` when unsure.
- If an `enum` value genuinely does not fit, do not force it into the nearest
  member. Write instead:
  `<field>: FREE TEXT - <what the paper actually does>. Suggested label: <candidate>`
- Emit no field the block above did not declare.
"""


def build_request(prompt_text: str, paper_text: str, bibkey: str) -> str:
    """Prompt file, then the paper, then the declared field block verbatim."""
    block = FIELD_BLOCK.search(prompt_text)
    declared = block.group(0) if block else ""
    return (
        f"{prompt_text.rstrip()}\n"
        f"{INSTRUCTIONS}\n"
        f"The fields, exactly as the prompt declares them:\n\n{declared}\n\n"
        f"<<<BEGIN PAPER: {bibkey}>>>\n{paper_text}\n<<<END PAPER: {bibkey}>>>\n"
    )


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


# --------------------------------------------------------------------------
# turning a model's answer into a card
# --------------------------------------------------------------------------

def clean_response(text: str) -> str:
    """Strip a fence and any front matter the model wrapped its answer in.

    Ours is the only front matter a card carries — parse_card reads the first
    block, so a second one would shadow the provenance we stamp.
    """
    text = text.strip()
    lines = [ln for ln in text.splitlines() if not FENCE.match(ln)]
    text = "\n".join(lines).strip()
    text = LEADING_FRONT_MATTER.sub("", text).strip()
    return "\n".join(ln for ln in text.splitlines() if ln.strip() != "---").strip()


def render_card(front: dict, body: str) -> str:
    lines = ["---"] + [f"{k}: {v}" for k, v in front.items()] + ["---", ""]
    return "\n".join(lines) + body.rstrip() + "\n"


# --------------------------------------------------------------------------
# model identity across the cards already on disk
# --------------------------------------------------------------------------

def existing_models(project: Path, card_type: str) -> dict:
    """{bibkey: model} for cards of this type that record one."""
    directory = project / "inputs" / "cards" / card_type
    out = {}
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.md")):
        out[path.stem] = parse_card(read_text(path))["front"].get("model")
    return out


# --------------------------------------------------------------------------
# evidence verification
# --------------------------------------------------------------------------

def normalise(text: str) -> str:
    """Collapse whitespace, unify quotes and dashes, casefold."""
    text = unicodedata.normalize("NFKC", text or "").translate(QUOTE_CHARS)
    return re.sub(r"\s+", " ", text).strip().casefold()


def loosen(text: str) -> str:
    """Alphanumerics only — survives hyphenation and punctuation drift."""
    return re.sub(r"[^0-9a-z]+", "", normalise(text))


def quote_of(evidence: str) -> str:
    """The quoted span, with any trailing page reference stripped."""
    stripped = PAGE_REF.sub("", (evidence or "").strip())
    quoted = QUOTED.findall(stripped)
    if quoted:
        return max(quoted, key=len)
    return stripped.strip("\"“”„‟' ")


def best_ratio(needle: str, matcher) -> float:
    """Similarity of the needle to the best-aligned window of the haystack.

    Anchor on the longest span the two share, line the needle up against it,
    then score that window. Sliding a fixed step over the whole paper misses
    the alignment and scores a true near-match as a miss.
    """
    haystack = matcher.b
    if not needle or not haystack:
        return 0.0
    matcher.set_seq1(needle)
    block = matcher.find_longest_match(0, len(needle), 0, len(haystack))
    if not block.size:
        return 0.0
    start = max(0, block.b - block.a)
    window = haystack[start:start + len(needle)]
    return difflib.SequenceMatcher(autojunk=False, a=needle, b=window).ratio()


def locate(quote: str, paper_norm: str, paper_loose: str, matcher=None) -> dict:
    """verified | near_match | not_found, and how it was matched."""
    if not quote:
        return {"status": "no_evidence_field", "problem": "no quoted span in _evidence"}
    exact = normalise(quote)
    if exact and exact in paper_norm:
        return {"status": "verified", "match": "exact"}
    loose = loosen(quote)
    if loose and loose in paper_loose:
        return {"status": "verified", "match": "punctuation and whitespace differ"}
    if len(loose) >= 12:
        if matcher is None:
            matcher = difflib.SequenceMatcher(autojunk=False, b=paper_loose)
        ratio = best_ratio(loose, matcher)
        if ratio >= NEAR_MATCH_RATIO:
            return {"status": "near_match", "similarity": round(ratio, 3),
                    "note": "close but not identical — a diacritic or a mojibake "
                            "character the extraction mangled does this, and so "
                            "does a quote the model reconstructed rather than "
                            "copied. Check it against the PDF."}
    return {"status": "not_found"}


def verify_type(project: Path, card_type: str, fields: list, keys=None) -> list:
    evidence_fields = [f["name"] for f in fields if f["evidence"]]
    directory = project / "inputs" / "cards" / card_type
    results = []
    if not directory.is_dir():
        return results
    for path in sorted(directory.glob("*.md")):
        bibkey = path.stem
        if keys and bibkey not in keys:
            continue
        values = {}
        parsed = parse_card(read_text(path))
        values.update(parsed["front"])
        values.update(parsed["body"])
        entry = {"card": f"{card_type}/{bibkey}", "fields": []}
        source = fulltext_path(project, bibkey)
        if not source.is_file():
            entry["problem"] = "no full text to check against"
            entry["fulltext"] = str(source)
            results.append(entry)
            continue
        paper = read_text(source)
        paper_norm, paper_loose = normalise(paper), loosen(paper)
        # one matcher per card: indexing the paper is the expensive half
        matcher = difflib.SequenceMatcher(autojunk=False, b=paper_loose)
        for name in evidence_fields:
            if name not in values:
                continue
            evidence = values.get(f"{name}_evidence")
            if evidence is None or not evidence.strip():
                entry["fields"].append({"field": name, "status": "no_evidence_field"})
                continue
            outcome = locate(quote_of(evidence), paper_norm, paper_loose, matcher)
            record = {"field": name, **outcome}
            if outcome["status"] != "verified":
                record["evidence"] = evidence[:200]
            entry["fields"].append(record)
        results.append(entry)
    return results


# --------------------------------------------------------------------------
# key resolution
# --------------------------------------------------------------------------

PAPER_TYPES = "state/paper_types.json"


def split_keys(raw) -> list:
    out = []
    for chunk in raw or []:
        out.extend(k for k in re.split(r"[,\s]+", chunk) if k)
    return list(dict.fromkeys(out))


def all_keys_for(project: Path, card_type: str) -> tuple:
    """Every key of this type, and a note on how 'this type' was decided.

    The project records no paper -> card-type assignment anywhere, so --all
    falls back to every paper with full text unless state/paper_types.json maps
    bib keys to types.
    """
    mapping = project / PAPER_TYPES
    directory = project / "inputs" / "fulltext"
    have = sorted(p.stem for p in directory.glob("*.md")) if directory.is_dir() else []
    if mapping.is_file():
        try:
            table = json.loads(read_text(mapping))
        except ValueError as exc:
            die(f"{PAPER_TYPES} does not parse", detail=str(exc))
        keys = [k for k in have if table.get(k) == card_type]
        unlisted = [k for k in have if k not in table]
        return keys, {"source": PAPER_TYPES, "papers_with_no_type_recorded": unlisted}
    return have, {
        "source": "every paper with full text",
        "caveat": f"no {PAPER_TYPES} exists, so --all cannot tell one paper type "
                  f"from another; it selected every paper with extracted full "
                  f"text. Write {PAPER_TYPES} as {{bibkey: card_type}} to narrow it.",
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_project_arg(parser)
    parser.add_argument("--type", metavar="CARD_TYPE", default=None)
    parser.add_argument("--keys", nargs="+", metavar="BIBKEY", default=None,
                        help="comma- or space-separated bib keys")
    parser.add_argument("--all", action="store_true",
                        help="every paper of that type")
    parser.add_argument("--backend", default=None,
                        help=f"one of: {', '.join(backends.KNOWN)}")
    parser.add_argument("--model", default=None,
                        help="exact backend model id; recorded in every card")
    parser.add_argument("--dry-run", action="store_true",
                        help="report the plan and the token estimate; call no backend")
    parser.add_argument("--force", action="store_true",
                        help="overwrite existing cards, and allow a second model")
    parser.add_argument("--verify-evidence", action="store_true",
                        help="check every quoted _evidence span against full text")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                        help=f"truncate paper text (default {DEFAULT_MAX_CHARS})")
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--attempts", type=int, default=4,
                        help="tries per key before a hard failure is reported")
    args = parser.parse_args()

    project = find_project(args.project)
    prompts = load_prompts(project)
    if not prompts:
        die("no prompts found",
            expected=str(project / "inputs" / "prompts" / "<type>_card.md"))
    if args.type and args.type not in prompts:
        die(f"no prompt declares card type {args.type!r}",
            known_types=sorted(prompts),
            expected=str(prompt_path(project, args.type)))

    if args.verify_evidence:
        run_verify(project, prompts, args)
        return

    run_extract(project, prompts, args)


def run_verify(project: Path, prompts: dict, args) -> None:
    keys = set(split_keys(args.keys)) or None
    types = [args.type] if args.type else sorted(prompts)
    cards, tally = [], {"verified": 0, "near_match": 0, "not_found": 0,
                        "no_evidence_field": 0}
    for card_type in types:
        for entry in verify_type(project, card_type, prompts[card_type], keys):
            for field in entry["fields"]:
                tally[field["status"]] = tally.get(field["status"], 0) + 1
            cards.append(entry)
    flagged = [c for c in cards
               if c.get("problem")
               or any(f["status"] != "verified" for f in c["fields"])]
    print_json({
        "verify_evidence": {
            "cards_checked": len(cards),
            "cards_clean": len(cards) - len(flagged),
            "fields": tally,
        },
        "flagged": flagged,
        "method": "quotes compared after collapsing whitespace, unifying quote "
                  "marks and dashes, and stripping the trailing page reference; "
                  "files read in Python with errors='ignore', never through grep",
        "note": "nothing was edited. near_match means a close but inexact match — "
                "mojibake in the extracted text produces these, and so does a "
                "quote the model reconstructed rather than copied. Both need a "
                "human against the PDF.",
    })


def run_extract(project: Path, prompts: dict, args) -> None:
    if not args.type:
        die("--type is required", known_types=sorted(prompts))
    if not args.backend:
        die("--backend is required", known_backends=list(backends.KNOWN))
    if args.backend not in backends.KNOWN:
        die(f"unknown backend {args.backend!r}", known_backends=list(backends.KNOWN))
    if not args.model:
        die("--model is required",
            why="the model id is part of a card's identity and is recorded in "
                "its front matter; the runner will not guess it")

    card_type = args.type
    fields = prompts[card_type]
    prompt_file = prompt_path(project, card_type)
    prompt_text = read_text(prompt_file)
    digest = prompt_digest(prompt_text)

    selection_note = None
    if args.all:
        keys, selection_note = all_keys_for(project, card_type)
    else:
        keys = split_keys(args.keys)
    if not keys:
        die("no bib keys to extract", hint="pass --keys, or --all")

    progress = Progress(project)
    gate_open = progress.gate_open
    trial = set(progress.data.get("trial_papers") or [])

    # The gate. cards.py reports a card written outside the trial set while the
    # gate is closed as a violation after the fact; the runner refuses to write
    # one at all, and refuses the whole run rather than half of it.
    if not gate_open:
        outside = sorted(k for k in keys if k not in trial)
        if outside:
            print_json({
                "refused": "gate_violation",
                "gate": "closed",
                "problem": "extraction was requested for papers outside the "
                           "nominated trial set while the extraction gate is closed",
                "papers": outside,
                "trial_papers": sorted(trial),
                "fix": ["nominate them: gate.py --trial <bibkey> ...",
                        "or open the gate properly: gate.py --open "
                        "--signed-by 'Name, YYYY-MM-DD' (the expert's signature)"],
                "note": "no card was written",
            })
            raise SystemExit(1)

    # Model identity. Two models means two artifacts, and a field column half
    # filled by each is not comparable.
    known = existing_models(project, card_type)
    conflicting = sorted(k for k, m in known.items() if m and m != args.model)
    no_provenance = sorted(k for k, m in known.items() if not m)
    if conflicting and not args.force:
        print_json({
            "refused": "model_mixing",
            "card_type": card_type,
            "problem": f"cards of this type already exist from a different model; "
                       f"this run would produce {args.model!r}",
            "existing_models": sorted({known[k] for k in conflicting}),
            "papers": conflicting,
            "fix": ["re-extract those cards with the same model",
                    "or move them aside and re-extract the type",
                    "or --force, and record the split in PROVENANCE.md"],
            "note": "no card was written",
        })
        raise SystemExit(1)

    written, invalid, failed, skipped, planned = [], [], [], [], []
    total_estimate = 0

    for bibkey in keys:
        source = fulltext_path(project, bibkey)
        if not source.is_file():
            failed.append({"bibkey": bibkey, "status": "no_fulltext",
                           "expected": str(source)})
            continue
        target = card_path(project, card_type, bibkey)
        if target.exists() and not args.force:
            skipped.append({"bibkey": bibkey, "status": "exists",
                            "path": str(target),
                            "fix": "--force to overwrite; cards are evidence, and "
                                   "the project's rule is flag, never fix"})
            continue

        paper = read_text(source)
        truncated = len(paper) > args.max_chars
        if truncated:
            paper = paper[:args.max_chars]
        request = build_request(prompt_text, paper, bibkey)
        estimate = estimate_tokens(request)
        total_estimate += estimate

        if args.dry_run:
            planned.append({"bibkey": bibkey, "path": str(target),
                            "input_tokens_estimate": estimate,
                            "fulltext_chars": len(paper),
                            "truncated": truncated})
            continue

        try:
            answer = backends.generate(
                args.backend, request, args.model,
                attempts=args.attempts, max_tokens=args.max_output_tokens)
        except backends.BackendError as exc:
            failed.append({"bibkey": bibkey, "status": "backend_error",
                           "error": str(exc)})
            continue

        front = {
            "bibkey": bibkey,
            "card_type": card_type,
            "prompt": prompt_file.name,
            "prompt_sha256": digest,
            "model": args.model,
            "backend": args.backend,
            "generated": now_iso(),
        }
        body = clean_response(answer)
        card = render_card(front, body)

        # The same rules cards.py --check applies, before the file lands.
        parsed = parse_card(card)
        problems = card_problems({**parsed["front"], **parsed["body"]}, fields)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(card, encoding="utf-8")
        record = {"bibkey": bibkey, "path": str(target),
                  "input_tokens_estimate": estimate}
        if truncated:
            record["truncated"] = True
        if problems:
            invalid.append({**record, "problems": problems})
        else:
            written.append(record)

    payload = {
        "project": str(project),
        "card_type": card_type,
        "backend": args.backend,
        "model": args.model,
        "prompt": prompt_file.name,
        "prompt_sha256": digest,
        "gate": "open" if gate_open else "closed",
        "requested": len(keys),
        "dry_run": bool(args.dry_run),
        "input_tokens_estimate_total": total_estimate,
    }
    if selection_note:
        payload["selection"] = selection_note
    if no_provenance:
        payload["cards_without_model_provenance"] = {
            "papers": no_provenance,
            "note": "these carry no model in their front matter, so the "
                    "mixing check cannot see them. They were written by hand or "
                    "by an agent; record which model in PROVENANCE.md.",
        }
    if args.dry_run:
        payload["would_write"] = planned
        payload["skipped"] = skipped
        payload["failed"] = failed
        print_json(payload)
        return

    payload["written"] = written
    payload["invalid"] = invalid
    payload["skipped"] = skipped
    payload["failed"] = failed
    payload["next"] = ["cards.py --check", "extract_cards.py --verify-evidence"]
    if invalid:
        payload["note"] = ("invalid cards were written and are reported here "
                           "rather than silently retried; read them, then fix "
                           "the prompt and re-run with --force")

    progress.log("extract_cards", card_type=card_type, backend=args.backend,
                 model=args.model, prompt_sha256=digest,
                 written=len(written), invalid=len(invalid),
                 failed=len(failed), skipped=len(skipped))
    progress.save()
    print_json(payload)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    sys.exit(main())
