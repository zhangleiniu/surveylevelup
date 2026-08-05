"""Stand up a survey project against an existing paperlevelup corpus.

Creates the directory layout, links the corpus read-only, instantiates the six
governance documents from templates, and writes state/progress.json.

Usage:
    python init.py --corpus <paperlevelup topic dir> --project <new dir>
    python init.py --corpus <dir> --project <dir> --title "..." --expert "..."
"""

import argparse
import json
import shutil
from pathlib import Path

from common import (GOVERNANCE_DOCS, TEMPLATE_DIR, Progress, die, print_json,
                    today)

SUBDIRS = (
    "inputs/fulltext",
    "inputs/prompts",
    "inputs/cards",
    "state",
    "drafts/v1/sections",
    "drafts/v1/appendices",
    "drafts/v1/figures",
    "archive",
)


def count_corpus(corpus: Path) -> int:
    sidecar = corpus / ".paperlevelup" / "papers.jsonl"
    if not sidecar.is_file():
        return 0
    return sum(1 for line in sidecar.open() if line.strip())


def instantiate(project: Path, subs: dict, force: bool) -> list:
    written = []
    for name in GOVERNANCE_DOCS:
        target = project / name
        if target.exists() and not force:
            written.append({"doc": name, "status": "kept (already present)"})
            continue
        text = (TEMPLATE_DIR / name).read_text()
        for key, value in subs.items():
            text = text.replace("{{%s}}" % key, value)
        target.write_text(text)
        written.append({"doc": name, "status": "written"})
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True, help="a paperlevelup topic folder")
    parser.add_argument("--project", required=True, help="project directory to create")
    parser.add_argument("--title", default=None, help="survey title; defaults to the corpus name")
    parser.add_argument("--expert", default="the domain expert")
    parser.add_argument("--bibkey-convention",
                        default="surname + year + first content word of the title",
                        help="recorded in CONSTITUTION.md; build_bib.py implements this default")
    parser.add_argument("--copy-corpus", action="store_true",
                        help="copy the corpus instead of symlinking it (not recommended)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite governance documents that already exist")
    args = parser.parse_args()

    corpus = Path(args.corpus).expanduser().resolve()
    if not corpus.is_dir():
        die("corpus folder not found", corpus=str(corpus))
    if not (corpus / ".paperlevelup").is_dir():
        die("that folder is not a paperlevelup topic (no .paperlevelup/)",
            corpus=str(corpus),
            hint="run paperlevelup's collect.py on it first")

    project = Path(args.project).expanduser().resolve()
    if project == corpus:
        die("the project must not be the corpus folder; keep evidence separate from output")
    project.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        (project / sub).mkdir(parents=True, exist_ok=True)

    link = project / "corpus"
    if link.is_symlink() or link.exists():
        linked = "kept (already present)"
    elif args.copy_corpus:
        shutil.copytree(corpus, link)
        linked = "copied"
    else:
        link.symlink_to(corpus, target_is_directory=True)
        linked = "symlinked"

    n_papers = count_corpus(corpus)
    docs = instantiate(project, {
        "PROJECT_TITLE": args.title or corpus.name,
        "PROJECT_DIR": project.name,
        "EXPERT": args.expert,
        "CORPUS_PATH": str(corpus),
        "N_PAPERS": str(n_papers),
        "DATE": today(),
        "BIBKEY_CONVENTION": args.bibkey_convention,
    }, args.force)

    progress = Progress(project)
    if not progress.path.is_file():
        progress.data = Progress.blank(str(corpus), n_papers)
        progress.log("init", corpus=str(corpus), papers=n_papers)
        progress.save()
        state = "written"
    else:
        state = "kept (already present)"

    friction = project / "state" / "friction.md"
    if not friction.exists():
        friction.write_text(
            "# Friction\n\n"
            "Where **surveylevelup** got in the way. Feedback to the skill, not notes\n"
            "about this survey. Append in the moment — friction is obvious while you\n"
            "are stuck in it and nearly invisible a week later.\n\n"
            "Two lines each: what happened, and what would have helped.\n\n"
            "```\n"
            "## YYYY-MM-DD — <one line>\n"
            "What happened. What would have helped.\n"
            "```\n\n"
            "---\n\n"
            "_Nothing yet._\n")

    gitignore = project / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("corpus\ninputs/fulltext/\n*.aux\n*.log\n*.out\n*.bbl\n*.blg\n")

    print_json({
        "project": str(project),
        "corpus": str(corpus),
        "corpus_link": linked,
        "corpus_papers": n_papers,
        "governance_docs": docs,
        "progress": state,
        "gate": "closed",
        "next": [
            "read CONSTITUTION.md and fill in scope and the inclusion rule",
            "python build_bib.py   # then fix any blocking gaps upstream in the corpus",
            "read the corpus, derive the axis — see references/thesis-derivation.md",
        ],
    })


if __name__ == "__main__":
    main()
