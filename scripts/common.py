"""Shared helpers: project discovery, state, prompt field blocks, card parsing."""

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_ROOT / "templates"

GOVERNANCE_DOCS = (
    "CLAUDE.md",
    "CONSTITUTION.md",
    "DECISIONS.md",
    "FINDINGS.md",
    "PROVENANCE.md",
    "STRUCTURE.md",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def print_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def die(message: str, **extra):
    print_json({"error": message, **extra})
    raise SystemExit(1)


# --------------------------------------------------------------------------
# project discovery
# --------------------------------------------------------------------------

def find_project(start=None) -> Path:
    """Walk up from `start` (or cwd) to the directory holding state/progress.json."""
    here = Path(start).expanduser().resolve() if start else Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "state" / "progress.json").is_file():
            return candidate
    die("not inside a surveylevelup project (no state/progress.json found)",
        looked_from=str(here))


def add_project_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", metavar="DIR", default=None,
                        help="project root; defaults to walking up from cwd")


class Progress:
    """state/progress.json — gate state, signatures, counts."""

    def __init__(self, project: Path):
        self.project = project
        self.path = project / "state" / "progress.json"
        self.data = json.loads(self.path.read_text()) if self.path.is_file() else {}

    @staticmethod
    def blank(corpus_path: str, n_papers: int) -> dict:
        return {
            "created": now_iso(),
            "corpus": corpus_path,
            "corpus_papers_at_link": n_papers,
            "gate": {
                "open": False,
                "opened": None,
                "signed_by": None,
                "checks": {},
            },
            "trial_papers": [],
            "counts": {"bib": 0, "fulltext": 0, "cards": 0},
            "history": [],
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n")

    @property
    def gate_open(self) -> bool:
        return bool(self.data.get("gate", {}).get("open"))

    def log(self, event: str, **detail) -> None:
        self.data.setdefault("history", []).append(
            {"ts": now_iso(), "event": event, **detail})


def corpus_sidecar(project: Path) -> Path:
    path = project / "corpus" / ".paperlevelup" / "papers.jsonl"
    if not path.is_file():
        die("corpus sidecar not found; is corpus/ linked to a paperlevelup topic?",
            expected=str(path))
    return path


def load_corpus(project: Path) -> list:
    records = []
    with corpus_sidecar(project).open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# --------------------------------------------------------------------------
# bib keys
# --------------------------------------------------------------------------

_NONWORD = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _NONWORD.sub("", text.lower())


def surname(author: str) -> str:
    """Last token of a name, or the part before a comma."""
    author = (author or "").strip()
    if not author:
        return "anon"
    if "," in author:
        return slug(author.split(",")[0]) or "anon"
    return slug(author.split()[-1]) or "anon"


def make_bibkey(record: dict) -> str:
    """<surname><year><firstTitleWord> — the default convention."""
    authors = record.get("authors") or []
    first = surname(authors[0]) if authors else "anon"
    year = str(record.get("year") or "0000")
    words = re.findall(r"[A-Za-z]+", record.get("title") or "")
    stop = {"a", "an", "the", "on", "of", "for", "in", "to", "and", "with", "is",
            "are", "can", "do", "does", "what", "how", "why", "towards", "toward"}
    word = next((slug(w) for w in words if slug(w) and slug(w) not in stop), "paper")
    return f"{first}{year}{word}"


def disambiguate(keys: list) -> dict:
    """Map index -> unique key, adding letter suffixes to collisions."""
    seen, out = {}, {}
    for i, key in enumerate(keys):
        seen.setdefault(key, []).append(i)
    for key, idxs in seen.items():
        if len(idxs) == 1:
            out[idxs[0]] = key
        else:
            for n, i in enumerate(idxs):
                out[i] = f"{key}{chr(ord('a') + n)}" if n < 26 else f"{key}{n}"
    return out


# --------------------------------------------------------------------------
# prompt field blocks
# --------------------------------------------------------------------------
#
# A prompt declares the fields its cards must carry, inside a fenced block:
#
#     ```fields
#     # name        | kind  | values                        | flags
#     task_type     | enum  | local, global, other          | required
#     purpose       | text  |                               | required, evidence
#     n_stages      | int   |                               |
#     ```
#
# kind:  text | enum | int | list
# flags: required, evidence   (comma-separated, may be empty)

FIELD_BLOCK = re.compile(r"```fields\s*\n(.*?)```", re.S)


def parse_field_block(prompt_text: str, source: str) -> list:
    match = FIELD_BLOCK.search(prompt_text)
    if not match:
        die("prompt declares no ```fields block", prompt=source)
    fields, problems = [], []
    for lineno, raw in enumerate(match.group(1).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            problems.append({"prompt": source, "line": lineno, "raw": raw,
                             "problem": "expected at least name | kind"})
            continue
        name, kind = parts[0], parts[1].lower()
        values = [v.strip() for v in parts[2].split(",") if v.strip()] if len(parts) > 2 else []
        flags = [f.strip().lower() for f in parts[3].split(",") if f.strip()] if len(parts) > 3 else []
        if kind not in ("text", "enum", "int", "list"):
            problems.append({"prompt": source, "line": lineno, "field": name,
                             "problem": f"unknown kind {kind!r}"})
            continue
        if kind == "enum" and not values:
            problems.append({"prompt": source, "line": lineno, "field": name,
                             "problem": "enum with no values"})
            continue
        fields.append({"name": name, "kind": kind, "values": values,
                       "required": "required" in flags,
                       "evidence": "evidence" in flags})
    if problems:
        die("prompt field block does not parse", problems=problems)
    if not fields:
        die("prompt field block is empty", prompt=source)
    return fields


def load_prompts(project: Path) -> dict:
    """{card_type: [field specs]} from inputs/prompts/<type>_card.md."""
    directory = project / "inputs" / "prompts"
    if not directory.is_dir():
        return {}
    out = {}
    for path in sorted(directory.glob("*_card.md")):
        card_type = path.stem[: -len("_card")]
        out[card_type] = parse_field_block(path.read_text(), path.name)
    return out


# --------------------------------------------------------------------------
# card parsing
# --------------------------------------------------------------------------

FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
# `★ ` markers and leading indentation are cosmetic and stripped.
CARD_LINE = re.compile(r"^\s*(?:★\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


def parse_card(text: str) -> dict:
    """Return {'front': {...}, 'body': {field: value}} — last value wins."""
    front, rest = {}, text
    match = FRONT_MATTER.match(text)
    if match:
        for line in match.group(1).splitlines():
            hit = CARD_LINE.match(line)
            if hit:
                front[hit.group(1)] = hit.group(2).strip().strip('"')
        rest = text[match.end():]
    body = {}
    for line in rest.splitlines():
        hit = CARD_LINE.match(line)
        if hit:
            body[hit.group(1)] = hit.group(2).strip()
    return {"front": front, "body": body}


# --------------------------------------------------------------------------
# card validation
# --------------------------------------------------------------------------
#
# One implementation, used both by cards.py --check (after the fact) and by
# extract_cards.py (before writing). If these two ever disagree the runner
# writes cards that the checker rejects, so they share this function rather
# than each carrying their own copy of the rules.

# A value that means "no answer", however the card writer spelled it.
ABSENT = {"", "n/a", "na", "none", "not reported", "not applicable", "-", "--"}

# Front matter a card may carry beyond the fields its prompt declares:
# identity, and the provenance extract_cards.py stamps on every card it writes.
PROVENANCE_FRONT_MATTER = frozenset({
    "bib_key", "bibkey", "title", "venue", "year", "card", "card_type",
    "prompt", "prompt_sha256", "model", "backend", "generated",
})


def is_present(raw) -> bool:
    """A field is present if it exists and does not say 'no answer'."""
    return raw is not None and raw.strip().lower() not in ABSENT


def card_problems(values: dict, fields: list) -> list:
    """Check a card's flattened {field: value} map against its prompt's specs.

    `values` is `{**parsed['front'], **parsed['body']}`. Returns a list of
    {"field", "problem", ...}; empty means the card honours its contract.
    """
    problems = []
    for spec in fields:
        name = spec["name"]
        raw = values.get(name)
        present = is_present(raw)
        if spec["required"] and raw is None:
            problems.append({"field": name, "problem": "required field absent"})
            continue
        if raw is None:
            continue
        value = raw.strip()
        if spec["kind"] == "enum" and present:
            # a free-text escape hatch is allowed but must be declared inline
            if value not in spec["values"] and not value.upper().startswith("FREE TEXT"):
                problems.append({"field": name, "problem": "value outside the declared enum",
                                 "value": value[:60], "allowed": spec["values"]})
        if spec["kind"] == "int" and present and not value.lstrip("-").isdigit():
            problems.append({"field": name, "problem": "not an integer", "value": value[:40]})
        if spec["evidence"] and present:
            ev = values.get(f"{name}_evidence")
            if ev is None or ev.strip().lower() in ABSENT:
                problems.append({"field": name,
                                 "problem": "judgment-bearing field without _evidence"})
            elif '"' not in ev and "'" not in ev:
                problems.append({"field": name,
                                 "problem": "_evidence carries no quoted span"})
    declared = {s["name"] for s in fields}
    allowed = declared | {f"{n}_evidence" for n in declared} | PROVENANCE_FRONT_MATTER
    for name in values:
        if name not in allowed and not name.endswith("_note"):
            problems.append({"field": name, "problem": "field not declared by the prompt"})
    return problems
