#!/usr/bin/env python3
"""Diagnose survey state and card-backend readiness without generating content.

This command is read-only.  It does not install packages, refresh configuration,
write credentials, open the extraction gate, or call a model.
"""

import argparse
import importlib.util
import sys

import backends
from common import Progress, SKILL_ROOT, add_project_arg, die, find_project, print_json
from extraction_config import ExtractionConfigError, resolve


def dependency(name: str, package: str) -> dict:
    available = importlib.util.find_spec(name) is not None
    result = {"package": package, "available": available}
    if not available:
        result["fix"] = (f"{sys.executable} -m pip install -r "
                         f"{SKILL_ROOT / 'requirements.txt'}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_project_arg(parser)
    parser.add_argument("--backend")
    parser.add_argument("--model", help="exact provider model id")
    parser.add_argument("--backend-project", dest="backend_project")
    parser.add_argument("--backend-location", dest="backend_location")
    args = parser.parse_args()

    project = find_project(args.project)
    try:
        selection = resolve(project, {
            "backend": args.backend,
            "model": args.model,
            "project": args.backend_project,
            "location": args.backend_location,
        })
    except ExtractionConfigError as exc:
        die(str(exc), project=str(project))
    values, sources = selection["values"], selection["sources"]
    backend, model = values.get("backend"), values.get("model")

    if not backend:
        backend_status = {
            "backend": None,
            "model": model,
            "ready": False,
            "problems": [{
                "code": "backend_missing",
                "message": "no extraction backend is selected",
                "fix": f"{sys.executable} "
                       f"{SKILL_ROOT / 'scripts' / 'configure_extraction.py'} "
                       f"--project {project} --backend BACKEND --model EXACT_MODEL_ID",
                "known_backends": list(backends.KNOWN),
            }],
        }
    else:
        backend_status = backends.preflight(
            backend, model,
            project=values.get("project"),
            location=values.get("location"),
            project_source=sources.get("project"),
            location_source=sources.get("location"),
            check_service=True,
        )

    progress = Progress(project)
    trial = sorted(progress.data.get("trial_papers") or [])
    gate_open = progress.gate_open
    prompts = project / "inputs" / "prompts"
    fulltext = project / "inputs" / "fulltext"
    prompt_count = len(list(prompts.glob("*_card.md"))) if prompts.is_dir() else 0
    trial_with_fulltext = [key for key in trial if (fulltext / f"{key}.md").is_file()]

    base_dependencies = [dependency("fitz", "pymupdf")]
    backend_ready = bool(backend_status.get("ready"))
    ready_for_trial = backend_ready and bool(trial) and prompt_count > 0 \
        and len(trial_with_fulltext) == len(trial)
    missing_fulltext = sorted(set(trial) - set(trial_with_fulltext))
    next_steps = []
    if missing_fulltext:
        for item in base_dependencies:
            if item.get("fix") and item["fix"] not in next_steps:
                next_steps.append(item["fix"])
    for problem in backend_status.get("problems", []):
        if problem.get("fix") and problem["fix"] not in next_steps:
            next_steps.append(problem["fix"])
    if not trial:
        next_steps.append("gate.py --trial <bibkey> ...")
    if not prompt_count:
        next_steps.append("create inputs/prompts/<type>_card.md with a ```fields block")
    if missing_fulltext:
        next_steps.append("extract_fulltext.py for the nominated trial papers")
    if ready_for_trial:
        next_steps.append("extract_cards.py --type <type> --keys <trial-bibkeys>")

    print_json({
        "doctor": "surveylevelup",
        "read_only": True,
        "paid_call": False,
        "project": str(project),
        "python": {"executable": sys.executable, "version": sys.version.split()[0]},
        "base_dependencies": base_dependencies,
        "extraction_config": selection,
        "backend": backend_status,
        "survey": {
            "extraction_gate": "open" if gate_open else "closed",
            "gate_scope": "corpus-wide card extraction only",
            "trial_papers": trial,
            "trial_papers_with_fulltext": trial_with_fulltext,
            "card_prompts": prompt_count,
            "trial_extraction": (
                "allowed_for_nominated_papers" if not gate_open else "allowed"),
            "corpus_wide_extraction": "allowed" if gate_open else "blocked_by_gate",
        },
        "ready_for_trial_extraction": ready_for_trial,
        "next": next_steps,
        "install_files": {
            "base": str(SKILL_ROOT / "requirements.txt"),
            "vertex": str(SKILL_ROOT / "requirements-vertex.txt"),
            "anthropic": str(SKILL_ROOT / "requirements-anthropic.txt"),
        },
    })


if __name__ == "__main__":
    main()
