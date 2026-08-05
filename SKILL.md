---
name: surveylevelup
description: Take a curated paper corpus and produce an expert survey — governance
  docs, a derived organizing thesis, per-paper extraction cards, and a drafted
  manuscript. Use when the user wants to write, plan, structure, or continue a
  survey or review paper from a folder of papers they have already collected;
  when they mention CONSTITUTION.md, FINDINGS.md, cards, a card schema, or a
  survey draft; or when a paperlevelup topic folder is ready and the question is
  "now what". Not for organizing PDFs — that is paperlevelup.
---

# Survey Level Up — agent workflow

This file is your operating manual. It takes a corpus that `paperlevelup` has
already organized and carries it to a drafted survey.

**The survey's value is one organizing axis, defended.** Not coverage, not paper
counts. Everything below is scaffolding in service of finding that axis and
making its evidence re-checkable. If a step stops serving that, cut the step.

**A human domain expert is the final judge on every domain call.** This skill is
written for a supervised collaboration, not an unattended run. When a taxonomy
boundary, an anchor paper, or an inclusion decision is genuinely ambiguous, ask.
Guessing is what produces the mechanical output the whole method exists to avoid.

---

## Where this skill starts and stops

| | |
|---|---|
| **Upstream — `paperlevelup`** | PDFs → identified metadata → categories → `TOPIC.md`, `papers.jsonl`. Owns the corpus. |
| **This skill** | corpus → thesis → card schema → extraction → manuscript. Owns the survey. |
| **Not here** | organizing or expanding the corpus. Call `paperlevelup` for that, at any point. |

The seam is `papers.jsonl` plus the PDF tree. **This skill never writes to
either.** When the survey needs papers the corpus lacks, run `paperlevelup`'s
`search.py` / `graph.py` / `fetch.py`, then re-run `build_bib.py` here and add
cards for the new papers. A manuscript citing a paper that is not in the corpus
is a defect.

---

## Running the scripts

Call them by absolute path; they find their own project root by walking up to
the directory containing `state/progress.json`.

```bash
python3 ~/.claude/skills/surveylevelup/scripts/init.py --corpus <paperlevelup topic dir> --project <new dir>
python3 ~/.claude/skills/surveylevelup/scripts/gate.py --status
```

Every script prints JSON.

| Script | Does |
|---|---|
| `init.py` | Create the project layout, link the corpus read-only, instantiate the six governance docs, write `state/progress.json` |
| `gate.py` | Report gate readiness; `--open` records the crossing once criteria and signature are in |
| `build_bib.py` | `papers.jsonl` → `inputs/references.bib` plus a blocking-gap report |
| `extract_fulltext.py` | PDFs → `inputs/fulltext/<bibkey>.md`. Ungated |
| `cards.py` | `--check` validates cards against the field block their prompt declares, and reports cards written outside the trial set while the gate is closed; `--aggregate` dumps field distributions |

---

## The project layout

```
<project>/
├── CLAUDE.md              index + current state + hard rules
├── CONSTITUTION.md        enduring standards; the living document
├── DECISIONS.md           dated decisions, append-only
├── FINDINGS.md            cross-paper findings, indexed
├── PROVENANCE.md          which prompt produced which artifact
├── STRUCTURE.md           file map: read-only vs writable
├── corpus/            →   symlink to the paperlevelup topic dir   [READ-ONLY]
├── inputs/                                                        [READ-ONLY once written]
│   ├── references.bib
│   ├── fulltext/<bibkey>.md
│   ├── prompts/<type>_card.md          method_card.md, benchmark_card.md, …
│   └── cards/<type>/<bibkey>.md
├── state/
│   ├── progress.json      gate state, signatures, counts
│   └── stances.jsonl      optional; see below
├── drafts/v1/
│   ├── main.tex, sections/, appendices/, figures/
└── archive/               superseded documents go here, not the root
```

`corpus/` and `inputs/` are evidence. Never edit them to fix a problem; fix the
producer and re-run it.

---

## The work: a loop, and one gate

Writing a survey is not a pipeline. You read, a candidate axis forms, you read
more and it breaks, you re-cut it. That loop is the work — it is not a sign that
something went wrong, and nothing here tries to stop it.

**Exactly one step is expensive enough to gate: running the card prompts over the
whole corpus.** Get the schema wrong and you re-extract everything. Everything
else is cheap and freely revisable.

```
    ┌──────────────────────────────────────────────┐
    │  read papers → sharpen the axis → name the   │
    │  sections → sketch the schema → test it on   │
    │  a handful of papers → find it wrong → back  │
    └───────────────────┬──────────────────────────┘
                        │   the extraction gate
                        ▼
              extract over the corpus  ⇄  draft
```

Spin the loop as long as it is still paying. `gate.py` guards only the crossing.

**Reading full text is never gated.** You usually cannot tell what matters in a
paper from its abstract, and pretending otherwise is how a survey inherits its
categories instead of earning them. Read whatever you need, whenever. Running
`extract_fulltext.py` over everything is also fine at any point — it is a PDF-to-
text dump, not a commitment. What the gate protects is the *judgment-bearing*
extraction, the cards.

### Corpus and bibliography

Confirm the corpus is stable, then build the bibliography.

- Run `build_bib.py`. It reports gaps. **Only a missing author or venue blocks
  anything** — a missing DOI or abstract does not, because the bib does not need
  them.
- Fix gaps at the source (`paperlevelup`'s sidecar), never by hand-editing the bib.
- Decide the **bib key convention once** and record it in `CONSTITUTION.md`. It
  becomes the canonical ID for filenames, card front matter, provenance and
  citations. Collisions get letter suffixes (`smith2024a`), never numbers.

### The loop: reading, axis, sections, schema

These four move together. Treating them as ordered steps is the mistake.

**Do not inherit the corpus's category folders as the survey's structure.** Those
categories were built for reading; they route papers, they do not argue anything.
Deriving the outline from them is the most common way an expert survey ends up
mechanical. See `references/thesis-derivation.md`.

What the loop is trying to produce, and what it keeps revising:

| | |
|---|---|
| **The axis** | one sentence naming the organizing variable, in `CONSTITUTION.md` |
| **The sections** | a list, and for each, the dimensions it compares across papers |
| **The schema** | a card field for each of those dimensions, per paper type |

Record candidate axes you considered and rejected, with the reason, in
`DECISIONS.md`. This is cheap and it stops the loop from circling back into an
axis already tried and abandoned three sessions ago.

**Test the schema on a handful of papers before crossing the gate.** Pick five or
six that stress it — an easy one, a benchmark paper, a position paper, and the
two you most expect to break it. If any planned section has no field to draw on,
or a field turns out to have no stable meaning across papers, you are still in
the loop. That is the cheapest place to discover it.

On the schema itself, see `references/schema-design.md`. The three standing rules:

- One schema **per paper type**, not one universal schema. Method papers
  schematize; benchmark, dataset and position papers are narrative and a
  `field: value` card compresses away the thing that makes them worth citing.
- Each prompt declares its fields in a machine-readable block so `cards.py` can
  validate against it.
- Judgment-bearing fields carry a sibling `<field>_evidence` holding a verbatim
  quote and page number.

### The extraction gate

`gate.py --open --signed-by "Name, date"` records the crossing. It checks:

- **Mechanically** — the bib is built with no blocking gaps; the axis sentence
  and the section list exist in `CONSTITUTION.md`; every section names the
  dimensions it compares; the prompts' field blocks parse; trial papers were
  nominated and carry cards.
- **By signature** — `--signed-by` is the expert's, not the agent's. Without it
  the gate does not open, however green the checks are.

The skill cannot stop an agent from writing cards early, so it makes doing so
visible instead: while the gate is closed, `cards.py --check` reports every card
written for a paper outside the nominated trial set as a `gate_violation`.

Crossing is not irreversible. Cards frequently reveal the axis was wrong; re-cutting
it and re-extracting is sometimes the right call. Log it in `DECISIONS.md`, note
which cards are superseded, and cross again. What the gate prevents is doing that
*by accident*, before anyone has looked.

### Extraction and drafting

Run the prompts to produce cards, then `cards.py` to validate. Record every
prompt-to-artifact edge in `PROVENANCE.md`.

**Read the prompts before reading the cards.** They carry the field semantics,
the enum vocabularies, and the blind spots — above all that `not reported` means
the paper did not say so, not that the method lacks it.

Draft per section from cards. Read anchors and synthesize; never transcribe
fields. Then the craft loop:

1. Compile after every change; grep for undefined citations and references.
2. **Render every figure and table to PNG and look at it.** Compiling is the
   floor. Visual defects compile fine.
3. Update `CLAUDE.md`'s current-state block so a cold session resumes without
   re-deriving context.

---

## The six governance documents

Six. Not more. Each says at the top what does **not** belong in it.

| Document | Job | Does not hold |
|---|---|---|
| `CLAUDE.md` | Index, current state, hard rules, traps. Read first on a cold start | Reasoning. It points at documents; detail lives there |
| `CONSTITUTION.md` | Scope, thesis, inclusion rule, writing stance, evidence rules. Living — fold expert corrections back in | Dated events; those go to DECISIONS |
| `DECISIONS.md` | Dated structural decisions, append-only, superseded ones marked | Enduring rules; those get promoted to CONSTITUTION |
| `FINDINGS.md` | Cross-paper findings, one line each in an index, load-bearing ones marked | Per-paper facts; those are cards |
| `PROVENANCE.md` | Which prompt consumed and produced each artifact | Conclusions |
| `STRUCTURE.md` | File map, read-only vs writable, naming | Anything that changes weekly |

**A superseded document is moved to `archive/`, not kept in the root with a
warning label.** A frozen outline that everyone must be told to ignore is the
same fact living in two places, which is the failure mode this whole scheme
exists to prevent.

There is no `CHANGES.md`. `git diff` is the change log; `DECISIONS.md` is why.

---

## Hard rules

- **`corpus/` and `inputs/` are read-only.** They are evidence, not scratch space.
- **One canonical ID: the bib key.** Per-paper files are `<bibkey>.md` with **no
  numeric prefix**. A number is a second identity for the same fact; the corpus
  grows, and then the number either stops sorting meaningfully or gets reassigned
  and breaks every reference already written.
- **Never edit a card. Flag, don't fix.** A wrong card is corrected by re-running
  its prompt or by the expert. Inline edits contaminate evidence with analysis.
- **Traceback is allowed; sedimentation is not.** If prose needs something a card
  lacks, read the full text and mark that the fact came from full text — do not
  write it back into the card.
- **`not reported` ≠ absent.**
- **No paper counts in prose.** Curated is not systematic; say so. Counts live in
  appendix tables with a disclaimer.
- **Claim strength ≤ evidence strength.** `demonstrates > suggests > may >
  hypothesize`. Pick the rung the evidence actually reaches.
- **Ask on domain calls.** Taxonomy boundaries, anchor selection, inclusion.
- **Never open the gate by hand.** `gate.py --open` or not at all.
- **Name things in words.** No internal codenames, letter-number labels or
  private shorthand — not in filenames, not in documents, and above all not when
  talking to the expert. `method_card.md`, not `P1.md`. "the extraction gate", not
  "G2". A label that means nothing to the reader makes them ask what it means, and
  they will stop asking before you stop using it.

---

## `state/friction.md` — feedback to this skill

Not a governance document, and exempt from the cap of six: it points outward, at
the skill, not inward at the survey.

**Append two lines whenever the skill snags.** A rule that turned out to be
wrong, a script that fought back, a place the manual was silent when you needed
it, a step that cost far more than it should have. Date, what happened, what
would have helped.

Do it in the moment. Friction is obvious while you are stuck in it and nearly
invisible a week later, and a session transcript is a poor substitute — by the
time anyone reads one, the thing that was annoying has been smoothed over and
forgotten. This file is the first-hand record that improves the skill for the
next project.

## Optional: `state/stances.jsonl`

How a citing paper treats a cited one — builds-on, adopts, contrasts, refutes,
corrects, supersedes — is often where a survey's most valuable content is: real
controversies, with receipts.

It does **not** belong in a card. A card's unit is one paper; a stance's unit is
a *pair*. Mixing them breaks the schema's unit of analysis. Cards should instead
carry `corpus_ancestors`, `corpus_descendants` and a free-text `lineage` field,
which captures what a paper extends, borrows or attacks from its own side.

If a project needs stances, add `state/stances.jsonl` with one row per
`{citing, cited, stance, quote, page}`. **Extract only for contested pairs** —
those surface from `FINDINGS.md` as you write. Corpus-wide extraction is
quadratic and nearly all of it returns neutral background citation.

No script ships for this yet, deliberately. Fix the format after one project has
actually used it.

---

## Principles

- **The corpus taxonomy is not the outline.** One organizes reading, the other
  makes an argument. Deriving the second from the first is how surveys go
  mechanical.
- **Authority over your own construct, not over the field.** Define and defend
  the axis and the concepts *you* introduce, precisely and confidently. Do not
  issue verdicts on what the field ought to want, who is right, or what the
  future holds. See `references/writing-stance.md`.
- **The schema is the contract.** It decides what you can write. Design it after
  the sections, before the extraction.
- **Match the evidence layer to the paper type.** Method papers: the card is
  enough. Benchmark, dataset and position papers: read the full text and fold the
  specifics into prose.
- **One fact, one home.** Coding lives in cards; paper↔file in the filename;
  title, venue and year in the bib. Friction comes almost entirely from the same
  fact living in two places.
- **Everything is re-checkable.** Full text is the only primary source. Cards are
  LLM-derived evidence. Say which is which.
- **Say what you did.** Every gate advanced, every paper added, every card
  invalidated — state it and why.
