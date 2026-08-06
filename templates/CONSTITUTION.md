# Constitution

The authoritative, **living** standards for {{PROJECT_TITLE}}. When the expert
corrects a domain judgment, fold the correction back in here so the next pass is
sharper.

**Does not hold:** dated events or superseded plans — those belong in
`DECISIONS.md`. Keep this document about what is true now.

---

## 1. Scope

<!-- What this survey covers and, more usefully, what it deliberately does not.
     State the boundary as a rule someone else could apply. -->

_To be written._

## 2. The axis

<!-- One sentence naming the organizing variable. This is the survey's
     contribution; everything downstream derives from it.

     It stays "not yet derived" until the corpus has been described, the
     tensions named, and a candidate tested against the papers picked in advance
     to break it. A candidate under test lives in DECISIONS.md, not here; this
     line holds only what the expert has approved.
     See references/thesis-derivation.md. -->

_Not yet derived._

## 3. Sections and what each compares

<!-- The section list, and for each section the dimensions it compares across
     papers. The card schema is derived from this table, so it must be concrete:
     "compares how the method represents the input", not "discusses methods". -->

| Section | Dimensions it compares |
|---|---|
| _tbd_ | |

## 4. Inclusion rule

<!-- A stated rule, not a feeling. Someone handed a new paper should be able to
     apply it. Record the known blind spots of the search channels too. -->

_To be written._

## 5. Identifiers

- **Bib key convention:** {{BIBKEY_CONVENTION}}
- Collisions take letter suffixes (`smith2024a`, `smith2024b`), never numbers.
- The bib key is the canonical ID everywhere: `inputs/fulltext/<bibkey>.md`,
  `inputs/cards/<type>/<bibkey>.md`, provenance rows, citations.
- Per-paper filenames carry **no numeric prefix**. A number is a second identity
  for the same fact; the corpus grows, and the number then either stops sorting
  meaningfully or gets reassigned and breaks every reference already written.

## 6. Evidence rules

- Full text is the only primary source. Cards are LLM-derived evidence and stay
  re-checkable.
- `not reported` means the paper did not say so, not that the method lacks it.
- Never edit a card. Flag it; correct it by re-running its prompt.
- Traceback is allowed, sedimentation is not: prose may draw on full text beyond
  what a card holds, marked as such, but that fact is never written back into the
  card.
- Judgment-bearing card fields carry a sibling `<field>_evidence` with a verbatim
  quote and page number.
- Claims about a benchmark or dataset are checked against full text, because its
  card is deliberately lossy.
- Distinguish observation, author claim, survey inference and proposed mechanism.
  A cross-paper relation created by this survey is labelled synthesis, never
  attributed to authors who did not draw it.
- Uncontrolled comparisons are contrasts, never experiments.
- Search and inclusion history lives in `PROVENANCE.md`. Do not start a second
  methodology ledger in prose or in another governance file.

## 7. Writing stance

The full stance is `~/.claude/skills/surveylevelup/references/writing-stance.md`.
Re-read it before drafting. The two rules that carry the most weight:

- **Authority over your own construct, not over the field.** Define and defend
  the axis and the concepts you introduce. Do not issue verdicts on what the
  field ought to want, who is right, or what comes next.
- **Claim strength never exceeds evidence strength.**

Project-specific calibration, if any:

<!-- e.g. "register calibrated against <a paper the expert wrote or admires>" -->

_None recorded._

## 8. Workflow

{{EXPERT}} is the domain-expert reviewer and final judge on domain calls. The
loop is: inspect evidence → propose a structural or domain judgment → obtain
review → draft → compile → visual and citation check → review by diff.

Large changes are proposed before implementation. Corrections that change future
work are recorded here if they are enduring rules, or in `DECISIONS.md` if they
are dated decisions.
