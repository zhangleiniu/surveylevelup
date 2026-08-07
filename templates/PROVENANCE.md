# Provenance

Which prompt or script consumed what and produced what. This is the chain that
lets a reader — or a later session — decide how far an artifact can be trusted.

**Does not hold:** conclusions. This file records where things came from, not
what they mean.

---

## Corpus

| | |
|---|---|
| Source | `{{CORPUS_PATH}}` (a `paperlevelup` topic folder) |
| Linked read-only at | `corpus/` |
| Papers at link time | {{N_PAPERS}} |
| Metadata sources | _record which sources identified the corpus, and their coverage_ |

Known coverage limits of the search channels used to build the corpus — venues a
source cannot see, reference-list coverage ratios, anything that makes an absence
uninformative:

_To be recorded._

## Corpus changes after linking

Every round of corpus growth, so a later reader knows the corpus was not static.

| Date | What was searched | Added | Rationale |
|---|---|---|---|
| _none_ | | | |

## Bibliography

| | |
|---|---|
| Built by | `build_bib.py` from `corpus/.paperlevelup/papers.jsonl` |
| Last built | _not built_ |
| Entries | — |
| Hand-corrected fields | _none; corrections belong upstream in the corpus sidecar_ |

## Full text

| | |
|---|---|
| Extracted by | `extract_fulltext.py` (PyMuPDF) |
| Last run | _not run_ |
| Files | — |
| Known failures | _record any PDF that yielded no usable text_ |

## Prompts and cards

| Prompt | SHA | Backend / exact model | Applies to | Cards produced |
|---|---|---|---|---|
| _none_ | | | | |

Record here whenever a prompt changes, because every card produced by the old
version is now a different artifact from the ones produced after. Cards are never
edited to catch up; they are re-run or marked stale. Do not mix prompt, backend or
model cohorts within one card type. Generated card front matter carries the
per-artifact provenance; this table records the cohort and its scope.

## Cards flagged as wrong

Flag, do not fix. A flagged card stays in place until it is re-run.

| Card | Field | Problem | Raised | Resolution |
|---|---|---|---|---|
| _none_ | | | | |

## Facts taken from full text rather than cards

Traceback is allowed; sedimentation is not. When prose needs something no card
holds, it is read from full text and recorded here — never written back into a
card.

| Fact | Paper | Where in the manuscript | Located at |
|---|---|---|---|
| _none_ | | | |
