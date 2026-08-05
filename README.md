<div id="header" align="center">
  <h1>Survey Level Up</h1>
</div>

**Turn a curated paper corpus into an expert survey**, with the evidence chain
intact and the parts that go wrong made visible.

This is the downstream half of a pair. [`paperlevelup`](https://github.com/zhangleiniu/paperlevelup) takes a
folder of PDFs and produces an organized, identified, growable corpus.
`surveylevelup` starts there and carries it to a drafted manuscript.

It is written for a **supervised collaboration**: an LLM writes, a human domain
expert is the final judge on every domain call. It is not an autonomous
framework, and the places where it asks are deliberate — guessing on a taxonomy
boundary or an inclusion call is what produces the mechanical survey the whole
method exists to avoid.

---

## What it actually does

The design rests on three claims, each learned the hard way from surveys that
came out badly the first time.

**1. A survey's value is one organizing axis, defended — not coverage.**
The categories a corpus is filed under were built for *reading*: they route a
paper to a folder so a human can find it. They are sitting right there, already
agreed, at exactly the moment you need an outline. Taking them is the most common
way a survey ends up complete, defensible, and saying nothing.
See [`references/thesis-derivation.md`](references/thesis-derivation.md).

**2. The card schema decides what you can write.**
Extraction schemas are derived backwards — from the axis, to the section list, to
the dimensions each section compares, to a field per dimension. Skip that and you
pay with a re-extraction round over the whole corpus.

**3. The failure mode of agent-written surveys is voice, not facts.**
Drafts come out sounding like a self-appointed authority summarizing a field from
above. The cause is asking for a strong organizing thesis without also bounding
what the author has standing to say. The rule that fixes it: **authority over
your own construct, not over the field.**
See [`references/writing-stance.md`](references/writing-stance.md).

## The shape of the work

Writing a survey is a loop, not a pipeline. You read, an axis forms, you read
more and it breaks, you re-cut. Nothing here tries to stop that.

Exactly one step is expensive enough to guard: **running the card prompts over
the whole corpus.** Everything before it — reading full text, sketching an axis,
naming sections, trying a schema on five papers — is cheap and freely revisable.

```
    ┌──────────────────────────────────────────────┐
    │  read → sharpen the axis → name the sections │
    │  → sketch the schema → try it on a handful   │
    │  → find it wrong → back                      │
    └───────────────────┬──────────────────────────┘
                        │   the extraction gate
                        ▼
              extract over the corpus  ⇄  draft
```

The gate opens on mechanical checks **and** an expert signature. Crossing is
reversible: cards often reveal the axis was wrong. What the gate prevents is
crossing by accident.

## Quickstart

```bash
pip install -r requirements.txt

python3 ~/.claude/skills/surveylevelup/scripts/init.py \
    --corpus ~/Papers/<topic> --project ~/work/<topic>-survey \
    --title "..." --expert "Your Name"

cd ~/work/<topic>-survey
python3 ~/.claude/skills/surveylevelup/scripts/build_bib.py       # fix gaps upstream
python3 ~/.claude/skills/surveylevelup/scripts/extract_fulltext.py
python3 ~/.claude/skills/surveylevelup/scripts/gate.py --status
```

Then read [`SKILL.md`](SKILL.md) — it is the operating manual.

## What the project looks like

```
<project>/
├── CLAUDE.md          index, current state, hard rules — read first on a cold start
├── CONSTITUTION.md    scope, the axis, inclusion rule, writing stance — living
├── DECISIONS.md       dated decisions, append-only, including axes already rejected
├── FINDINGS.md        cross-paper findings — the differentiated content
├── PROVENANCE.md      which prompt produced which artifact
├── STRUCTURE.md       file map: read-only evidence vs writable output
├── corpus/        →   a paperlevelup topic folder            [read-only]
├── inputs/            bib, full text, prompts, cards         [read-only once written]
├── state/             gate state, counts, optional stances
├── drafts/v1/
└── archive/           superseded documents live here, not in the root
```

Six governance documents, capped at six. Each says at the top what does **not**
belong in it. A superseded document moves to `archive/`; it does not stay in the
root with a warning label, because that is the same fact living in two places.

## Scripts

| Script | Does |
|---|---|
| `init.py` | Lay out the project, link the corpus read-only, instantiate the six documents |
| `build_bib.py` | Corpus sidecar → `references.bib`, plus a gap report that only flags what actually blocks |
| `extract_fulltext.py` | PDFs → `inputs/fulltext/<bibkey>.md` via PyMuPDF. Ungated |
| `gate.py` | Report gate readiness; `--open --signed-by` records the crossing |
| `cards.py` | Validate cards against the field block their prompt declares; `--aggregate` for distributions |

Scripts never write cards — an agent does, by running the prompts. Scripts check
that what got written matches the declared contract.

## Conventions worth knowing before you start

- **The bib key is the canonical ID.** Per-paper files are `<bibkey>.md`, with no
  numeric prefix. A number is a second identity for the same fact; the corpus
  grows, and the number then either stops sorting meaningfully or gets reassigned
  and breaks every reference already written.
- **Prompts declare their fields** in a ` ```fields ` block, so validation is
  mechanical rather than a matter of remembering.
- **Judgment-bearing fields carry `<field>_evidence`** with a verbatim quote and
  page number.
- **`not reported` ≠ absent.** It means the paper did not say so.
- **Never edit a card.** Flag it; fix the producer and re-run.
- **Name things in words.** No codenames, no letter-number labels — not in
  filenames, and above all not when talking to the expert.

## Tests

```bash
tests/smoke.sh ~/Papers/<topic>
```

Runs end to end against a throwaway project: layout, bibliography, gate refusal
without a signature, rejection of a malformed field block, and card validation
catching enum, evidence, type and gate-discipline problems.
