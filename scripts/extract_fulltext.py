"""PDFs -> inputs/fulltext/<bibkey>.md.

Ungated on purpose. This is a text dump, not a commitment: you usually cannot
tell what matters in a paper from its abstract, and reading is how the axis gets
found. What the extraction gate protects is the judgment-bearing extraction —
the cards — not this.

Usage:
    python extract_fulltext.py
    python extract_fulltext.py --only smith2024axis jones2023other
    python extract_fulltext.py --force
"""

import argparse
import re
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

from common import (Progress, add_project_arg, die, disambiguate, find_project,
                    load_corpus, make_bibkey, now_iso, print_json)

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
             "ﬄ": "ffl", "‘": "'", "’": "'", "“": '"',
             "”": '"', "–": "-", "—": "--"}


def clean(text: str) -> str:
    for bad, good in LIGATURES.items():
        text = text.replace(bad, good)
    text = re.sub(r"-\n(?=[a-z])", "", text)        # de-hyphenate line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_project_arg(parser)
    parser.add_argument("--only", nargs="+", metavar="BIBKEY")
    parser.add_argument("--force", action="store_true", help="re-extract existing files")
    args = parser.parse_args()

    if fitz is None:
        die("PyMuPDF is not installed", fix="pip install pymupdf")

    project = find_project(args.project)
    records = load_corpus(project)
    keys = disambiguate([make_bibkey(r) for r in records])

    out_dir = project / "inputs" / "fulltext"
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = set(args.only or [])

    written, skipped, failed = [], [], []
    for i, record in enumerate(records):
        key = keys[i]
        if wanted and key not in wanted:
            continue
        target = out_dir / f"{key}.md"
        if target.is_file() and not args.force:
            skipped.append(key)
            continue
        rel = record.get("path") or record.get("key")
        pdf = project / "corpus" / rel if rel else None
        if not pdf or not pdf.is_file():
            failed.append({"bibkey": key, "problem": "pdf not found", "path": str(rel)})
            continue
        try:
            with fitz.open(pdf) as doc:
                pages = [page.get_text() for page in doc]
        except Exception as exc:                     # noqa: BLE001
            failed.append({"bibkey": key, "problem": f"{type(exc).__name__}: {exc}"})
            continue
        body = clean("\n\n".join(pages))
        if len(body) < 500:
            failed.append({"bibkey": key, "problem": "almost no extractable text",
                           "chars": len(body),
                           "hint": "probably a scanned PDF; it needs OCR or manual handling"})
            continue
        header = (f"---\nbibkey: {key}\n"
                  f"title: \"{(record.get('title') or '').replace(chr(34), '')}\"\n"
                  f"source_pdf: {rel}\npages: {len(pages)}\n"
                  f"extracted: {now_iso()}\n---\n\n")
        target.write_text(header + body)
        written.append(key)

    progress = Progress(project)
    progress.data.setdefault("counts", {})["fulltext"] = len(list(out_dir.glob("*.md")))
    progress.log("extract_fulltext", written=len(written), failed=len(failed))
    progress.save()

    print_json({"written": len(written), "skipped_existing": len(skipped),
                "failed": failed, "total_on_disk": progress.data["counts"]["fulltext"],
                "note": "record any failure in PROVENANCE.md under Full text"})


if __name__ == "__main__":
    main()
