# CLAUDE.md

Working repository for **{{PROJECT_TITLE}}**.
You are the writer; **{{EXPERT}}** is the domain-expert reviewer and the final
judge on every domain call.

**This file is an index.** It carries current state, hard rules, and the traps
that actually cause errors here. Reasoning lives in the documents it points at —
do not move detail back into this file.

## Read before doing anything

1. `CONSTITUTION.md` — scope, the axis, inclusion rule, writing stance, evidence
   rules. Re-read before writing, not only at session start.
2. `STRUCTURE.md` — file map; what is read-only evidence and what is writable.
3. `DECISIONS.md` — decision history, including axes already tried and rejected.
   Read before proposing a new one.
4. `FINDINGS.md` — start at the index. This is the survey's differentiated
   content.
5. `PROVENANCE.md` — where each artifact came from and how far it can be trusted.

The skill's own manual is `~/.claude/skills/surveylevelup/SKILL.md`, with
`references/thesis-derivation.md` and `references/writing-stance.md`.

## Hard rules

- **Never modify anything under `corpus/` or `inputs/`.** PDFs, full text, cards,
  prompts and metadata are read-only evidence, not scratch space.
- **Never edit a card.** Cards come only from running the prompts in
  `inputs/prompts/`. A wrong card is *flagged*, never fixed inline. If prose needs
  something a card lacks, read the full text and mark that the fact came from full
  text — do not write it back into a card.
- **`not reported` ≠ absent.** It means the paper did not say so.
- **No paper counts in prose.** Counts live in appendix tables with the
  curated-corpus disclaimer.
- **Claim strength ≤ evidence strength.**
- **Never open the extraction gate by hand** — `gate.py --open` or not at all.
- **Name things in words.** No codenames, no letter-number labels, not in
  filenames and not in conversation.
- **Corpus changes go through `paperlevelup`**, then re-run `build_bib.py` here.
  A manuscript citing a paper absent from the corpus is a defect.
- **No hard line wrapping in `.tex`.** One paragraph = one source line.

## How we work

- **Propose before large changes.** State the plan, get approval, then generate.
- **Ask rather than guess** on domain calls — axis boundaries, anchor selection,
  whether a paper belongs. Guessing produces the mechanical output this method
  exists to eliminate. Ask in prose, about named papers, one question at a time.
- **Never offer a menu of candidate axes**, and never ask which axis to use
  before the corpus has been described back to the expert. The axis is converged
  on over several rounds: portrait → tensions → one candidate with its evidence →
  the cut. A multiple-choice question about the organizing variable asks for the
  one judgment that has to be earned by reading first.
- **Record corrections in the document that owns them.** Enduring rules to
  `CONSTITUTION.md`; dated structural decisions to `DECISIONS.md`; cross-paper
  evidence to `FINDINGS.md`.
- Review happens by diff. Prefer small, legible commits.
- **Append to `state/friction.md` whenever the skill gets in the way** — a rule
  that was wrong, a script that fought back, a place the manual was silent, a
  step that cost far more than it should have. Two lines, written *in the
  moment*. This is feedback to the skill, not a note about this survey, and it is
  the only record that will still exist when someone improves the skill later.

## Current state — {{DATE}}

| Layer | State |
|---|---|
| Corpus | {{N_PAPERS}} papers · `corpus/TOPIC.md` |
| Bibliography | not built |
| Full text | not extracted |
| Corpus portrait | not run, not yet described to the expert |
| Axis | not derived — see DECISIONS.md for candidates under test |
| Sections | not defined |
| Schema | not designed |
| Extraction gate | **closed** |
| Cards | none |
| Findings | none |
| Manuscript | none |

Update this table at the end of any session that changes it. A cold session
should be able to resume from this file alone.
