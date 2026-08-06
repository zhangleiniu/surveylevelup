"""Describe the corpus as it was filed, so the first conversation is about evidence.

This runs before any axis talk. It answers "what is actually in here?" —
how big, how recent, which categories are growing and which have gone quiet,
where the filed categories share vocabulary, which papers sit closer to a
category other than their own.

It deliberately proposes nothing. Every number here describes the *reading*
taxonomy, which is exactly the structure a survey must not inherit. Overlap and
misfits are hints about where to look, computed from title and abstract wording
only — never a verdict that a boundary is wrong.

Usage:
    python corpus_portrait.py                       # the whole portrait
    python corpus_portrait.py --top 30              # longer lists
    python corpus_portrait.py --recent-since 2024   # set the recency cut by hand
"""

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from common import add_project_arg, corpus_sidecar, find_project, load_corpus, print_json

UNCATEGORIZED = "Uncategorized"

WORD = re.compile(r"[a-z][a-z\-']+")

# Function words plus the vocabulary every paper in every corpus uses. Left in,
# they crowd out the terms that actually distinguish one filed category from
# another.
STOPWORDS = frozenset("""
a about above across after again against all almost along already also although
always among an and another any are around as at be because been before being
below best better between both but by can cannot could did do does doing done
down due during each either else enough especially et etc even every few first
for from further get given had has have having he her here hers herself him
himself his how however if in into is it its itself just least less like made
mainly make many may me more most much must my namely near nearly neither never
nevertheless next no nor not nothing now obtained of off often on one only onto
or other others ought our ours ourselves out over overall own particularly per
perhaps please quite rather really regarding same seem seen several shall she
should show showed shown shows significantly since so some such sufficiently
than that the their theirs them themselves then there therefore these they this
those though through thus to together too toward towards under unless unlike
until up upon us use used using various very via was we were what when where
whether which while who whom whose why will with within without would yet you
your yours

approach approaches based case cases challenges compared comparison different
effect effective empirical evaluate evaluation existing experiment experimental
experiments framework general however improve improved improvement literature
method methods model models new novel paper papers performance possible present
problem problems propose proposed prior recent related report research result
results review setting settings state study studies survey system systems task
tasks technique techniques work works
""".split())


def tokens(text: str) -> list:
    """Unigrams and bigrams. Bigrams carry most of the field's real vocabulary."""
    words = [w for w in WORD.findall((text or "").lower())
             if len(w) > 2 and w not in STOPWORDS]
    return words + ["%s %s" % pair for pair in zip(words, words[1:])]


def paper_text(record: dict) -> str:
    parts = [record.get("title") or "",
             record.get("abstract") or record.get("excerpt") or ""]
    return " ".join(parts)


def category_of(record: dict) -> str:
    return (record.get("category") or "").strip() or UNCATEGORIZED


def read_taxonomy(project: Path) -> dict:
    path = corpus_sidecar(project).parent / "taxonomy.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    return {c["name"]: c.get("description") for c in data.get("categories", [])}


def normalize(vector: dict) -> dict:
    norm = math.sqrt(sum(v * v for v in vector.values()))
    return {k: v / norm for k, v in vector.items()} if norm else {}


def cosine(a: dict, b: dict) -> float:
    small, large = (a, b) if len(a) < len(b) else (b, a)
    return sum(weight * large.get(term, 0.0) for term, weight in small.items())


def vectors(records: list) -> dict:
    """key -> L2-normalized tf-idf vector, for papers that have any text."""
    bags = {r["key"]: Counter(tokens(paper_text(r))) for r in records}
    bags = {k: b for k, b in bags.items() if b}
    doc_freq = Counter()
    for bag in bags.values():
        doc_freq.update(bag.keys())
    n = len(bags) or 1
    out = {}
    for key, bag in bags.items():
        weighted = {t: (1 + math.log(c)) * math.log(n / doc_freq[t])
                    for t, c in bag.items() if doc_freq[t] > 1}
        out[key] = normalize(weighted)
    return out


def shared_vocabulary(records: list, by_category: dict, threshold: float,
                      min_size: int, top: int) -> list:
    """Terms that a sizeable share of two or more filed categories use.

    Where two categories talk about the same thing in different folders, the
    filed split may be cutting the wrong joint. A term that is common to most
    categories is just the topic itself, so those are dropped.
    """
    sized = {c: rs for c, rs in by_category.items()
             if c != UNCATEGORIZED and len(rs) >= min_size}
    if len(sized) < 2:
        return []
    share = {}
    for category, rs in sized.items():
        counts = Counter()
        for record in rs:
            counts.update(set(tokens(paper_text(record))))
        share[category] = {t: c / len(rs) for t, c in counts.items()}

    ceiling = max(2, len(sized) // 2)
    rows = []
    for term in {t for s in share.values() for t in s}:
        hits = sorted(((c, s[term]) for c, s in share.items()
                       if s.get(term, 0) >= threshold),
                      key=lambda x: -x[1])
        if 2 <= len(hits) <= ceiling:
            rows.append({"term": term,
                         "categories": [[c, round(v, 2)] for c, v in hits[:4]],
                         "_rank": hits[1][1]})
    rows.sort(key=lambda r: (-r["_rank"], r["term"]))
    for row in rows:
        del row["_rank"]
    return rows[:top]


def centroids(by_category: dict, vecs: dict, min_size: int) -> dict:
    out = {}
    for category, records in by_category.items():
        if category == UNCATEGORIZED:
            continue
        members = [vecs[r["key"]] for r in records if r["key"] in vecs]
        if len(members) < min_size:
            continue
        total = defaultdict(float)
        for vector in members:
            for term, weight in vector.items():
                total[term] += weight
        out[category] = {"sum": dict(total), "n": len(members)}
    return out


def resisting_papers(records: list, vecs: dict, cents: dict, margin: float,
                     top: int) -> list:
    """Papers whose wording sits closer to another category than to their own.

    Leave-one-out against the home category, so a paper is never scored against
    a centroid it helped build. This is a reading list, not a reclassification:
    a paper that resists its folder is where a filed boundary is worth arguing
    about, and under the right axis most of them stop being awkward.
    """
    unit = {c: normalize(v["sum"]) for c, v in cents.items()}
    rows = []
    for record in records:
        key, home = record["key"], category_of(record)
        vector = vecs.get(key)
        if not vector or home not in cents:
            continue
        block = cents[home]
        if block["n"] < 2:
            continue
        held_out = normalize({t: w - vector.get(t, 0.0)
                              for t, w in block["sum"].items()})
        own = cosine(vector, held_out)
        others = sorted(((c, cosine(vector, u)) for c, u in unit.items() if c != home),
                        key=lambda x: -x[1])
        if not others:
            continue
        best, score = others[0]
        if score - own >= margin:
            rows.append({"title": (record.get("title") or key)[:90],
                         "filed_under": home,
                         "reads_closer_to": best,
                         "own": round(own, 3),
                         "other": round(score, 3),
                         "gap": round(score - own, 3)})
    rows.sort(key=lambda r: -r["gap"])
    return rows[:top]


def overlapping_pairs(cents: dict, top: int) -> list:
    unit = {c: normalize(v["sum"]) for c, v in cents.items()}
    names = sorted(unit)
    pairs = [{"categories": [a, b], "similarity": round(cosine(unit[a], unit[b]), 3)}
             for i, a in enumerate(names) for b in names[i + 1:]]
    pairs.sort(key=lambda p: -p["similarity"])
    return pairs[:top]


def spanning(records: list, field: str, top: int, min_papers: int = 3) -> list:
    """Authors or venues that work in more than one filed category.

    A group publishing on both sides of a filed boundary is worth a look: they
    do not experience it as a boundary. Ranked by the *second* category's count,
    so a genuine straddle outranks someone with one stray paper elsewhere.
    Common surnames collide here; treat a row as a question, not a fact.
    """
    seen = defaultdict(Counter)
    for record in records:
        category = category_of(record)
        values = record.get(field) or []
        if isinstance(values, str):
            values = [values]
        for value in (values[:8] if field == "authors" else values):
            if value:
                seen[value][category] += 1
    rows = []
    for name, spread in seen.items():
        if len(spread) < 2 or sum(spread.values()) < min_papers:
            continue
        ranked = spread.most_common(5)
        rows.append({("author" if field == "authors" else field): name,
                     "categories": [[c, n] for c, n in ranked],
                     "papers": sum(spread.values()),
                     "_rank": ranked[1][1]})
    rows.sort(key=lambda r: (-r["_rank"], -r["papers"]))
    for row in rows:
        del row["_rank"]
    return rows[:top]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_project_arg(parser)
    parser.add_argument("--top", type=int, default=20, help="cap on every ranked list")
    parser.add_argument("--recent-since", type=int, default=None,
                        help="year the recency share counts from (default: latest year minus 2)")
    parser.add_argument("--min-category", type=int, default=3,
                        help="categories smaller than this are described but not compared")
    parser.add_argument("--overlap-threshold", type=float, default=0.2,
                        help="share of a category's papers that must use a term")
    parser.add_argument("--misfit-margin", type=float, default=0.02,
                        help="how much closer another category must read")
    args = parser.parse_args()

    project = find_project(args.project)
    records = load_corpus(project)
    if not records:
        print_json({"error": "the corpus sidecar is empty"})
        return

    by_category = defaultdict(list)
    for record in records:
        by_category[category_of(record)].append(record)

    years = [r["year"] for r in records if isinstance(r.get("year"), int)]
    cut = args.recent_since or (max(years) - 2 if years else 0)
    descriptions = read_taxonomy(project)

    detail = []
    for category, group in sorted(by_category.items(), key=lambda kv: -len(kv[1])):
        group_years = sorted(y for y in (r.get("year") for r in group) if isinstance(y, int))
        detail.append({
            "category": category,
            "papers": len(group),
            "description": descriptions.get(category),
            "median_year": group_years[len(group_years) // 2] if group_years else None,
            "year_span": [group_years[0], group_years[-1]] if group_years else None,
            "share_since_%d" % cut: (round(sum(1 for y in group_years if y >= cut)
                                           / len(group_years), 2) if group_years else None),
            "years": dict(sorted(Counter(group_years).items())),
            "top_venues": Counter(r["venue"] for r in group if r.get("venue")).most_common(4),
        })

    vecs = vectors(records)
    cents = centroids(by_category, vecs, args.min_category)
    with_text = sum(1 for r in records if (r.get("abstract") or r.get("excerpt")))
    resisting = resisting_papers(records, vecs, cents, args.misfit_margin, args.top)

    cautions = [
        "Everything here describes the reading taxonomy. That taxonomy routes "
        "papers to folders; it does not argue anything, and the survey must not "
        "inherit it as an outline.",
        "A year distribution reflects when this corpus was collected, not when "
        "the field moved. Before saying a category has gone quiet, search it "
        "for recent work.",
        "Shared vocabulary and resisting papers come from wording alone. They "
        "say where to look, not that a boundary is wrong.",
        "Nothing here is an axis, and no ranking in it should be read as one.",
    ]
    if not resisting:
        cautions.append(
            "No paper reads closer to another category than to its own. The filed "
            "categories are internally consistent in their wording, which is not "
            "evidence they cut the field at the right joint — papers that resist "
            "a taxonomy often do so on substance the abstract never states.")

    print_json({
        "corpus": str(Path(project / "corpus").resolve()),
        "papers": len(records),
        "categories": len([c for c in by_category if c != UNCATEGORIZED]),
        "uncategorized": len(by_category.get(UNCATEGORIZED, [])),
        "year_span": [min(years), max(years)] if years else None,
        "papers_by_year": dict(sorted(Counter(years).items())),
        "text_coverage": {
            "with_abstract_or_excerpt": with_text,
            "title_only": len(records) - with_text,
            "note": "vocabulary, overlap and misfits are computed from title plus "
                    "abstract; title-only papers contribute almost nothing to them",
        },
        "by_category": detail,
        "categories_that_read_alike": overlapping_pairs(cents, args.top),
        "vocabulary_shared_across_categories": shared_vocabulary(
            records, by_category, args.overlap_threshold, args.min_category, args.top),
        "papers_that_resist_their_category": resisting,
        "authors_across_categories": spanning(records, "authors", args.top),
        "venues_across_categories": spanning(records, "venue", args.top),
        "cautions": cautions,
        "next": "Read the corpus. Then describe it back to the expert in prose — "
                "what is in it, what is growing, where the filed categories blur, "
                "which papers refuse to sit still. Ask what they recognize and what "
                "surprises them. Do not offer a menu of candidate axes.",
    })


if __name__ == "__main__":
    main()
