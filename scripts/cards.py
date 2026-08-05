"""Validate cards against the field block their prompt declares.

This script does not write cards — an agent does, by running the prompts in
inputs/prompts/. What it does is check that what got written matches the contract
the prompt declared, and that nobody ran corpus-wide extraction before the gate
was opened.

Usage:
    python cards.py --check
    python cards.py --aggregate                 # field distributions, all types
    python cards.py --aggregate --type method
"""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from common import (Progress, add_project_arg, die, find_project, load_prompts,
                    parse_card, print_json)

ABSENT = {"", "n/a", "na", "none", "not reported", "not applicable", "-", "--"}


def card_files(project: Path) -> dict:
    """{card_type: {bibkey: path}}"""
    root = project / "inputs" / "cards"
    out = defaultdict(dict)
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.md")):
        card_type = path.parent.name
        out[card_type][path.stem] = path
    return out


def check_card(path: Path, fields: list) -> list:
    parsed = parse_card(path.read_text())
    values = {**parsed["front"], **parsed["body"]}
    problems = []
    for spec in fields:
        name = spec["name"]
        raw = values.get(name)
        present = raw is not None and raw.strip().lower() not in ABSENT
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
    allowed = declared | {f"{n}_evidence" for n in declared} | {
        "bib_key", "bibkey", "title", "venue", "year", "card", "prompt"}
    for name in values:
        if name not in allowed and not name.endswith("_note"):
            problems.append({"field": name, "problem": "field not declared by the prompt"})
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_project_arg(parser)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--aggregate", action="store_true",
                        help="dump field distributions; use this to judge what is worth tabling")
    parser.add_argument("--type", metavar="CARD_TYPE", default=None)
    args = parser.parse_args()
    if not (args.check or args.aggregate):
        args.check = True

    project = find_project(args.project)
    prompts = load_prompts(project)
    if not prompts:
        die("no prompts found", expected=str(project / "inputs" / "prompts" / "<type>_card.md"))
    found = card_files(project)
    progress = Progress(project)

    if args.aggregate:
        out = {}
        for card_type, fields in prompts.items():
            if args.type and card_type != args.type:
                continue
            counts = {}
            for spec in fields:
                if spec["kind"] not in ("enum", "int"):
                    continue
                tally = Counter()
                for path in found.get(card_type, {}).values():
                    values = parse_card(path.read_text())
                    raw = {**values["front"], **values["body"]}.get(spec["name"])
                    tally[(raw or "").strip() or "(absent)"] += 1
                counts[spec["name"]] = dict(tally.most_common())
            out[card_type] = {"cards": len(found.get(card_type, {})), "fields": counts}
        print_json({"aggregate": out,
                    "note": "a generated appendix column must be an enum; narrative "
                            "fields are hand-written or not tabled at all"})
        return

    unknown_types = sorted(set(found) - set(prompts))
    results, clean = [], 0
    for card_type, fields in prompts.items():
        for bibkey, path in sorted(found.get(card_type, {}).items()):
            problems = check_card(path, fields)
            if problems:
                results.append({"card": f"{card_type}/{bibkey}", "problems": problems})
            else:
                clean += 1

    trial = set(progress.data.get("trial_papers") or [])
    all_keys = {k for keys in found.values() for k in keys}
    violation = sorted(all_keys - trial) if not progress.gate_open else []

    payload = {
        "gate": "open" if progress.gate_open else "closed",
        "card_types": sorted(prompts),
        "cards_checked": clean + len(results),
        "cards_clean": clean,
        "cards_with_problems": results,
        "unknown_card_type_dirs": unknown_types,
    }
    if violation:
        payload["gate_violation"] = {
            "problem": "cards exist for papers outside the trial set while the gate is closed",
            "papers": violation,
            "fix": "either nominate them with gate.py --trial, or open the gate properly",
        }
    progress.data.setdefault("counts", {})["cards"] = clean + len(results)
    progress.log("cards_check", clean=clean, problems=len(results))
    progress.save()
    print_json(payload)


if __name__ == "__main__":
    main()
