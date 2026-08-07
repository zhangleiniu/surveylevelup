"""Build a throwaway paperlevelup topic folder, so smoke.sh runs with no corpus.

    python3 tests/make_fixture_corpus.py <dir>

Writes <dir>/.paperlevelup/papers.jsonl plus empty placeholder PDFs. The
records are invented — enough structure for build_bib.py and
corpus_portrait.py, and nothing that resembles a real paper.
"""

import json
import sys
from pathlib import Path

CATEGORIES = {
    "routing": ("routing", "instance graph", "message passing", "decoder"),
    "theory": ("hardness", "impossibility", "separation", "lower bound"),
    "benchmarks": ("benchmark", "dataset", "leaderboard", "reproduction"),
}

SURNAMES = ("Alder", "Bram", "Cowen", "Dass", "Eberle", "Farr", "Gill", "Hoyt",
            "Ivers", "Joss", "Krall", "Lund")


def records() -> list:
    out = []
    for index, (category, vocabulary) in enumerate(CATEGORIES.items()):
        for n in range(4):
            i = index * 4 + n
            surname = SURNAMES[i % len(SURNAMES)]
            title = (f"{vocabulary[n].title()} for combinatorial problems, "
                     f"part {n + 1}")
            out.append({
                "key": f"{category}/paper{i:02d}.pdf",
                "path": f"{category}/paper{i:02d}.pdf",
                "category": category,
                "title": title,
                "authors": [f"{surname}, R.", f"{SURNAMES[(i + 3) % 12]}, Q."],
                "year": 2021 + (n % 4),
                "venue": "Journal of Invented Results" if n % 2 else "Proc. Nowhere",
                "doi": f"10.0000/fixture.{i:04d}",
                "abstract": (
                    f"We study {vocabulary[n]} in the context of {category}. "
                    f"The method encodes each instance and decodes a solution, "
                    f"and we report results on invented instances. "
                    f"{' '.join(vocabulary)} recur throughout."),
                "summary": f"A fixture record about {vocabulary[n]}.",
                "tags": list(vocabulary[:2]),
            })
    return out


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    root = Path(sys.argv[1]).expanduser().resolve()
    sidecar = root / ".paperlevelup"
    sidecar.mkdir(parents=True, exist_ok=True)
    rows = records()
    with (sidecar / "papers.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    for row in rows:
        path = root / row["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n%% fixture, not a real document\n")
    print(json.dumps({"corpus": str(root), "papers": len(rows),
                      "categories": sorted(CATEGORIES)}, indent=2))


if __name__ == "__main__":
    main()
