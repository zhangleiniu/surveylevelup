"""Run the card prompts over papers and write cards, with provenance.

The prompts in inputs/prompts/ declare their fields and project-specific
semantics. This runner adds the shared output and evidence protocol, making each
request a self-contained contract. That makes a card a model-agnostic artifact
and lets the bulk pass run on a cheaper backend than the agent driving the
survey without losing track of who produced what.

Every card it writes records the prompt's digest and the exact backend and model.
Cards produced by different prompts, backends or models are different artifact
cohorts, so the runner refuses to mix them within one card type.

By default an existing card is skipped. ``--force`` may replace it only by
re-running the same prompt/backend/model cohort; cards are never hand-edited.
``--verify-evidence`` only reports and never changes a card.

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
from extraction_config import ExtractionConfigError, resolve

# Roughly four characters to a token. Good enough to decide whether a run is
# affordable; never presented as a measurement.
CHARS_PER_TOKEN = 4

# A whole paper, not a whole corpus. Truncation is reported per key.
DEFAULT_MAX_CHARS = 600_000

# Gemini reasoning tokens share this ceiling with the visible answer. This is a
# ceiling, not a reservation: providers bill actual usage. Prefer enough room
# for a complete card and reject a MAX_TOKENS response rather than saving a few
# tokens and writing a stub.
DEFAULT_MAX_OUTPUT_TOKENS = 65_536

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


def content_digest(text: str) -> str:
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
  Quote one contiguous span within one page. Do not join fragments with an
  ellipsis, cross a visible page break or running header, paraphrase,
  reconstruct, normalize, or compose a quote. If the best sentence crosses a
  page boundary, use a shorter contiguous span wholly on one side.
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

COHORT_FIELDS = ("prompt_sha256", "backend", "model")


def existing_cohorts(project: Path, card_type: str) -> dict:
    """{bibkey: {prompt_sha256, backend, model}} for existing cards."""
    directory = project / "inputs" / "cards" / card_type
    out = {}
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.md")):
        front = parse_card(read_text(path))["front"]
        out[path.stem] = {name: front.get(name) for name in COHORT_FIELDS}
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

CARD_ASSIGNMENTS = "state/card_assignments.json"


def split_keys(raw) -> list:
    out = []
    for chunk in raw or []:
        out.extend(k for k in re.split(r"[,\s]+", chunk) if k)
    return list(dict.fromkeys(out))


def all_keys_for(project: Path, card_type: str, known_types) -> tuple:
    """Every explicitly assigned key of this type.

    The file maps each bib key to a list because one paper may carry two cards.
    Missing assignments are unresolved domain judgments, so --all fails closed.
    """
    mapping = project / CARD_ASSIGNMENTS
    directory = project / "inputs" / "fulltext"
    have = sorted(p.stem for p in directory.glob("*.md")) if directory.is_dir() else []
    if not mapping.is_file():
        die(f"{CARD_ASSIGNMENTS} is required for --all",
            why="paper type is a domain judgment and one paper may have more than one card",
            format={"bibkey": ["method", "benchmark"],
                    "reviewed-with-no-card": []})
    try:
        table = json.loads(read_text(mapping))
    except ValueError as exc:
        die(f"{CARD_ASSIGNMENTS} does not parse", detail=str(exc))
    if not isinstance(table, dict):
        die(f"{CARD_ASSIGNMENTS} must be a JSON object",
            format={"bibkey": ["method", "benchmark"]})

    problems = []
    known = set(known_types)
    for bibkey, values in table.items():
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            problems.append({"bibkey": bibkey, "problem": "expected a list of card types"})
            continue
        duplicates = sorted({v for v in values if values.count(v) > 1})
        unknown = sorted(set(values) - known)
        if duplicates:
            problems.append({"bibkey": bibkey, "problem": "duplicate card types",
                             "values": duplicates})
        if unknown:
            problems.append({"bibkey": bibkey, "problem": "unknown card types",
                             "values": unknown, "known_types": sorted(known)})
    unlisted = sorted(set(have) - set(table))
    unknown_keys = sorted(set(table) - set(have))
    if unlisted or unknown_keys or problems:
        die(f"{CARD_ASSIGNMENTS} is incomplete or invalid",
            papers_with_no_assignment=unlisted,
            assignments_without_fulltext=unknown_keys,
            problems=problems,
            note="an empty list means the paper was reviewed and needs no card")
    keys = [k for k in have if card_type in table[k]]
    return keys, {"source": CARD_ASSIGNMENTS,
                  "assigned_papers": len(keys),
                  "reviewed_papers": len(table)}


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
    parser.add_argument("--backend-project", default=None,
                        help="Google Cloud project id; overrides project extraction config")
    parser.add_argument("--backend-location", default=None,
                        help="provider location; overrides project extraction config")
    parser.add_argument("--dry-run", action="store_true",
                        help="run read-only backend preflight and report the plan/token "
                             "estimate; call no model and write nothing")
    parser.add_argument("--force", action="store_true",
                        help="re-run and replace an existing card in the same artifact cohort")
    parser.add_argument("--verify-evidence", action="store_true",
                        help="check every quoted _evidence span against full text")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                        help=f"truncate paper text (default {DEFAULT_MAX_CHARS})")
    parser.add_argument("--max-output-tokens", type=int,
                        default=DEFAULT_MAX_OUTPUT_TOKENS,
                        help=f"output ceiling including reasoning tokens "
                             f"(default {DEFAULT_MAX_OUTPUT_TOKENS})")
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
    try:
        extraction = resolve(project, {
            "backend": args.backend,
            "model": args.model,
            "project": args.backend_project,
            "location": args.backend_location,
        })
    except ExtractionConfigError as exc:
        die(str(exc))
    selected = extraction["values"]
    backend = selected.get("backend")
    model = selected.get("model")
    if not backend:
        die("--backend is required (or configure state/extraction.json)",
            known_backends=list(backends.KNOWN))
    if backend not in backends.KNOWN:
        die(f"unknown backend {backend!r}", known_backends=list(backends.KNOWN))
    if not model:
        die("--model is required (or configure state/extraction.json)",
            why="the model id is part of a card's identity and is recorded in "
                "its front matter; the runner will not guess it")

    card_type = args.type
    fields = prompts[card_type]
    prompt_file = prompt_path(project, card_type)
    prompt_text = read_text(prompt_file)
    digest = prompt_digest(prompt_text)

    selection_note = None
    if args.all:
        keys, selection_note = all_keys_for(project, card_type, prompts)
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

    # Artifact identity. A field column extracted by different prompts, backends
    # or models is heterogeneous even if every individual card validates.
    requested_cohort = {
        "prompt_sha256": digest,
        "backend": backend,
        "model": model,
    }
    known = existing_cohorts(project, card_type)
    conflicting = {}
    no_provenance = []
    for bibkey, cohort in known.items():
        missing = [name for name in COHORT_FIELDS if not cohort.get(name)]
        if missing:
            no_provenance.append({"bibkey": bibkey, "missing": missing})
        mismatch = {name: {"existing": cohort.get(name),
                           "requested": requested_cohort[name]}
                    for name in COHORT_FIELDS
                    if cohort.get(name) and cohort[name] != requested_cohort[name]}
        if mismatch:
            conflicting[bibkey] = mismatch
    if conflicting:
        print_json({
            "refused": "artifact_cohort_mixing",
            "card_type": card_type,
            "problem": "cards of this type already exist from a different prompt, "
                       "backend or model",
            "requested_cohort": requested_cohort,
            "conflicts": conflicting,
            "papers": sorted(conflicting),
            "fix": ["use the same prompt, backend and model",
                    "or archive the existing cohort and re-extract the whole type"],
            "note": "no card was written",
        })
        raise SystemExit(1)

    # Read-only readiness check, once per run and before any card can be written.
    # The extraction gate above remains a separate concern: a closed gate still
    # permits nominated trial papers when the backend is ready.
    backend_status = backends.preflight(
        backend, model,
        project=selected.get("project"),
        location=selected.get("location"),
        project_source=extraction["sources"].get("project"),
        location_source=extraction["sources"].get("location"),
    )
    if not backend_status.get("ready"):
        print_json({
            "refused": "backend_not_ready",
            "backend": backend_status,
            "gate": "open" if gate_open else "closed",
            "trial_extraction": (
                "allowed_for_nominated_papers" if not gate_open else "allowed"),
            "note": "no model was called and no card was written; run doctor.py "
                    "for the combined survey/backend report",
        })
        raise SystemExit(1)
    runtime = backend_status.get("resolved", {})

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
                            "fix": "--force re-runs the producer in the same "
                                   "prompt/backend/model cohort; never edit by hand"})
            continue

        paper = read_text(source)
        fulltext_digest = content_digest(paper)
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
            result = backends.generate(
                backend, request, model,
                attempts=args.attempts, max_tokens=args.max_output_tokens,
                project=runtime.get("project"),
                location=runtime.get("location"))
        except backends.BackendError as exc:
            failed.append({"bibkey": bibkey, "status": "backend_error",
                           "error": str(exc)})
            continue

        front = {
            "bibkey": bibkey,
            "card_type": card_type,
            "prompt": prompt_file.name,
            "prompt_sha256": digest,
            "model": model,
            "backend": backend,
            "generated": now_iso(),
            "fulltext_sha256": fulltext_digest,
            "max_output_tokens": args.max_output_tokens,
        }
        metadata = dict(result.metadata)
        for source_name, front_name in (
            ("project", "backend_project"),
            ("location", "backend_location"),
            ("sdk_version", "sdk_version"),
            ("model_version", "model_version"),
            ("finish_reason", "finish_reason"),
            ("input_tokens", "input_tokens"),
            ("output_tokens", "output_tokens"),
            ("thought_tokens", "thought_tokens"),
            ("cached_input_tokens", "cached_input_tokens"),
            ("total_tokens", "total_tokens"),
        ):
            if source_name in metadata:
                front[front_name] = metadata[source_name]
        body = clean_response(result.text)
        card = render_card(front, body)

        # The same rules cards.py --check applies, before the file lands.
        parsed = parse_card(card)
        problems = card_problems({**parsed["front"], **parsed["body"]}, fields)

        record = {"bibkey": bibkey, "path": str(target),
                  "input_tokens_estimate": estimate}
        usage = {name: metadata[name] for name in (
            "input_tokens", "output_tokens", "thought_tokens",
            "cached_input_tokens", "total_tokens") if name in metadata}
        if usage:
            record["usage"] = usage
        if truncated:
            record["truncated"] = True
        if problems:
            invalid.append({**record, "status": "schema_invalid",
                            "problems": problems,
                            "note": "response rejected before writing"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(card, encoding="utf-8")
        written.append(record)

    payload = {
        "project": str(project),
        "card_type": card_type,
        "backend": backend,
        "model": model,
        "extraction_config": extraction,
        "backend_preflight": backend_status,
        "prompt": prompt_file.name,
        "prompt_sha256": digest,
        "max_output_tokens": args.max_output_tokens,
        "gate": "open" if gate_open else "closed",
        "requested": len(keys),
        "dry_run": bool(args.dry_run),
        "input_tokens_estimate_total": total_estimate,
    }
    if selection_note:
        payload["selection"] = selection_note
    completed = written + invalid
    usage_totals = {}
    for record in completed:
        for name, value in record.get("usage", {}).items():
            usage_totals[name] = usage_totals.get(name, 0) + value
    if usage_totals:
        payload["usage"] = usage_totals
    if no_provenance:
        payload["cards_without_complete_provenance"] = {
            "cards": no_provenance,
            "note": "the cohort check can compare only the provenance these cards carry",
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
        payload["note"] = ("schema-invalid responses were rejected before writing; "
                           "fix the prompt or producer, then re-run")

    progress.log("extract_cards", card_type=card_type, backend=backend,
                 model=model, prompt_sha256=digest,
                 max_output_tokens=args.max_output_tokens,
                 written=len(written), invalid=len(invalid),
                 failed=len(failed), skipped=len(skipped), usage=usage_totals)
    progress.save()
    print_json(payload)
    if failed or invalid:
        raise SystemExit(1)


if __name__ == "__main__":
    sys.exit(main())
