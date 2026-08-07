"""The extraction gate: the one crossing this skill guards.

Everything before it is cheap and freely revisable — reading, sharpening the
axis, naming sections, sketching a schema, trying it on a handful of papers.
Running the card prompts over the whole corpus is not: get the schema wrong and
you re-extract everything.

The gate opens on mechanical criteria AND a human signature. Only the expert can
supply the signature.

Usage:
    python gate.py --status
    python gate.py --trial smith2024axis jones2023other ...   # nominate trial papers
    python gate.py --open --signed-by "Name, YYYY-MM-DD"
    python gate.py --close --reason "axis re-cut, see DECISIONS"
"""

import argparse
import re
from pathlib import Path

from common import (Progress, add_project_arg, find_project, load_prompts,
                    now_iso, print_json, today)

SECTION_TABLE = re.compile(
    r"##\s*3\.\s*Sections and what each compares(.*?)(?=\n##\s|\Z)", re.S)
AXIS_SECTION = re.compile(r"##\s*2\.\s*The axis(.*?)(?=\n##\s|\Z)", re.S)
PLACEHOLDER = re.compile(r"_(?:to be written|not yet derived|tbd|none recorded)\._?", re.I)


def read_constitution(project: Path) -> str:
    path = project / "CONSTITUTION.md"
    return path.read_text() if path.is_file() else ""


def axis_stated(text: str) -> bool:
    hit = AXIS_SECTION.search(text)
    if not hit:
        return False
    body = re.sub(r"<!--.*?-->", "", hit.group(1), flags=re.S).strip()
    return bool(body) and not PLACEHOLDER.search(body)


def sections_and_dimensions(text: str) -> list:
    """Rows of the section table that carry both a name and dimensions."""
    hit = SECTION_TABLE.search(text)
    if not hit:
        return []
    rows = []
    for line in hit.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        name, dims = cells[0], cells[1]
        if not name or name.lower() in ("section", "_tbd_") or name.startswith("---"):
            continue
        rows.append({"section": name, "dimensions": dims})
    return rows


def run_checks(project: Path) -> dict:
    progress = Progress(project)
    constitution = read_constitution(project)

    bib = project / "inputs" / "references.bib"
    blocking = progress.data.get("bib", {}).get("blocking_gaps")
    rows = sections_and_dimensions(constitution)
    prompts = load_prompts(project)
    declared = {f["name"] for fields in prompts.values() for f in fields}

    sections_missing_dims = [r["section"] for r in rows if not r["dimensions"]]

    cards_dir = project / "inputs" / "cards"
    cards = sorted(p.stem for p in cards_dir.rglob("*.md")) if cards_dir.is_dir() else []
    trial = set(progress.data.get("trial_papers") or [])
    beyond_trial = sorted(set(cards) - trial) if not progress.gate_open else []

    checks = {
        "bibliography_built": bib.is_file(),
        "bibliography_no_blocking_gaps": blocking == 0,
        "axis_stated": axis_stated(constitution),
        "sections_listed": len(rows) > 0,
        "every_section_has_dimensions": bool(rows) and not sections_missing_dims,
        "prompts_declare_fields": bool(prompts),
        "trial_papers_nominated": bool(trial),
        "trial_cards_present": bool(trial) and bool(trial & set(cards)),
    }
    return {
        "checks": checks,
        "ready": all(checks.values()),
        "sections": rows,
        "sections_missing_dimensions": sections_missing_dims,
        "card_types": sorted(prompts),
        "declared_fields": sorted(declared),
        "trial_papers": sorted(trial),
        "cards_on_disk": len(cards),
        "cards_beyond_trial_while_closed": beyond_trial,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_project_arg(parser)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--trial", nargs="+", metavar="BIBKEY",
                        help="nominate the papers the schema is tried on first")
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--signed-by", metavar="'Name, YYYY-MM-DD'",
                        help="required with --open; only the expert supplies this")
    parser.add_argument("--close", action="store_true")
    parser.add_argument("--reason", default=None)
    args = parser.parse_args()

    project = find_project(args.project)
    progress = Progress(project)

    if args.trial:
        progress.data["trial_papers"] = sorted(set(args.trial))
        progress.log("trial_papers", papers=progress.data["trial_papers"])
        progress.save()
        print_json({"trial_papers": progress.data["trial_papers"],
                    "next": "write cards for these, then: gate.py --status"})
        return

    if args.close:
        progress.data["gate"] = {"open": False, "opened": None, "signed_by": None,
                                 "checks": progress.data.get("gate", {}).get("checks", {})}
        progress.log("gate_closed", reason=args.reason)
        progress.save()
        print_json({"gate": "closed", "reason": args.reason,
                    "note": "record the re-cut in DECISIONS.md and mark superseded cards"})
        return

    report = run_checks(project)

    if args.open:
        if not args.signed_by:
            print_json({"gate": "not opened", "why": "--signed-by is required",
                        "note": "the signature is the expert's, not the agent's",
                        **report})
            raise SystemExit(1)
        if not report["ready"]:
            failed = [k for k, v in report["checks"].items() if not v]
            print_json({"gate": "not opened", "why": "mechanical checks failed",
                        "failed": failed, **report})
            raise SystemExit(1)
        progress.data["gate"] = {"open": True, "opened": now_iso(),
                                 "signed_by": args.signed_by,
                                 "checks": report["checks"]}
        progress.log("gate_opened", signed_by=args.signed_by)
        progress.save()
        print_json({"gate": "open", "signed_by": args.signed_by, "opened": today(),
                    "next": "extract cards corpus-wide, then: cards.py --check"})
        return

    print_json({"gate": "open" if progress.gate_open else "closed",
                "signed_by": progress.data.get("gate", {}).get("signed_by"),
                "scope": "corpus-wide card extraction; nominated trial papers "
                         "may run while closed",
                "backend_readiness": "separate; run doctor.py",
                **report})


if __name__ == "__main__":
    main()
