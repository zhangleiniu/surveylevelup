#!/usr/bin/env python3
"""Explicit, paid Vertex integration test against a temporary survey project.

Nothing here reads or writes a real survey. It creates one synthetic trial
paper, runs the complete paper -> Gemini -> card path, validates the card, checks
its evidence quote, prints a non-sensitive JSON report, and deletes the fixture.

Run only when deliberately requested:

    SURVEYLEVELUP_LIVE_VERTEX=1 \
    GOOGLE_CLOUD_PROJECT=... GOOGLE_CLOUD_LOCATION=global \
    python tests/live_vertex.py [model-id]
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.6-flash"
KEY = "fixture2026routing"

PROMPT = """# Method card

Extract only what the paper reports. Copy evidence verbatim.

```fields
# name    | kind | values           | flags
approach  | enum | graph, sequence  | required
purpose   | text |                  | required, evidence
stages    | int  |                  | required
```
"""

PAPER = """# Routing on an Instance Graph

This fixture describes a graph approach. We route messages along the instance
graph to construct a solution. The encoder runs for two stages.
"""


def invoke(*args):
    proc = subprocess.run(
        [sys.executable, *map(str, args)], capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        payload = {"stdout": proc.stdout, "stderr": proc.stderr}
    if proc.returncode:
        print(json.dumps({"command_failed": list(map(str, args)), **payload}, indent=2))
        raise SystemExit(proc.returncode)
    return payload


def main():
    if os.environ.get("SURVEYLEVELUP_LIVE_VERTEX") != "1":
        raise SystemExit(
            "refusing a paid call: set SURVEYLEVELUP_LIVE_VERTEX=1 deliberately")
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise SystemExit("GOOGLE_CLOUD_PROJECT is required")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

    with tempfile.TemporaryDirectory(prefix="surveylevelup-live-vertex-") as tmp:
        project = Path(tmp) / "project"
        for sub in ("state", "inputs/prompts", "inputs/fulltext", "inputs/cards"):
            (project / sub).mkdir(parents=True)
        (project / "state/progress.json").write_text(json.dumps({
            "gate": {"open": False, "opened": None, "signed_by": None},
            "trial_papers": [KEY],
            "counts": {},
            "history": [],
        }))
        (project / "inputs/prompts/method_card.md").write_text(PROMPT)
        (project / f"inputs/fulltext/{KEY}.md").write_text(PAPER)

        extraction = invoke(
            SCRIPTS / "extract_cards.py", "--project", project,
            "--type", "method", "--keys", KEY,
            "--backend", "vertex", "--model", MODEL,
        )
        checked = invoke(SCRIPTS / "cards.py", "--project", project, "--check")
        evidence = invoke(
            SCRIPTS / "extract_cards.py", "--project", project,
            "--verify-evidence", "--type", "method", "--keys", KEY,
        )

        if extraction.get("invalid") or len(extraction.get("written", [])) != 1:
            raise SystemExit("Vertex returned no valid card")
        if checked.get("cards_clean") != 1:
            raise SystemExit("the generated card did not pass cards.py --check")
        if evidence.get("flagged"):
            raise SystemExit("the generated evidence quote did not verify")

        print(json.dumps({
            "live_vertex": "passed",
            "principal": os.environ.get(
                "SURVEYLEVELUP_VERTEX_PRINCIPAL", "not recorded"),
            "project": project_id,
            "location": location,
            "model": MODEL,
            "gate": extraction.get("gate"),
            "prompt_sha256": extraction.get("prompt_sha256"),
            "usage": extraction.get("usage", {}),
            "schema_check": "clean",
            "evidence_check": evidence.get("verify_evidence"),
            "fixture_removed_on_exit": True,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
