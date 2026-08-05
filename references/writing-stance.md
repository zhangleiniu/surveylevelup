# Writing stance

Re-read this before drafting any section, not just at the start of a project.

These are rules, not style advice. Most of them exist because a specific draft
failed in a specific way.

---

## 1. What you have authority over

**You have authority over your own construct.** The axis you derived, the
concepts you introduce, the boundaries you draw — define them precisely, defend
them, and say plainly why they cut better than the alternatives. This is the
survey's contribution. Hedging it away leaves nothing.

**You have no authority over the field.** Do not issue verdicts on what the field
ought to want, which research programme deserves to win, who is right, or what
the next five years hold. You are describing and organizing work other people
did.

The failure mode this prevents is the most common one in agent-drafted surveys:
prose that reads as a self-appointed authority summarizing from above. It comes
from applying the first rule without the second. A draft that says *"we organize
these methods by where the algorithmic structure is injected, because the field's
usual split by architecture cuts across that variable"* is doing the job. A draft
that says *"the field must move beyond its preoccupation with architecture"* is
not.

Signals you have drifted: sentences beginning *the field has yet to*, *researchers
should*, *the community must*; paragraphs that grade a line of work rather than
explain it; conclusions that forecast.

## 2. Register

Declarative, compact, evidence-led. A claim is followed immediately by the
number, control or mechanism that supports it — not by a citation alone, which
tells the reader where to look but not what they would find.

Concessions are integrated into the sentence that makes the claim, not staged as
a separate throat-clearing paragraph.

Start from what the reader needs to know, not from the order your extraction
schema happens to be in. A section whose paragraphs march through card fields
reads like a database dump because it is one.

Explain why an approach emerged, what it solves, what it trades away, and what it
leaves unresolved. Those four are the content. Enumerating who did what is not.

## 3. Claim strength never exceeds evidence strength

Pick the rung the evidence actually reaches:

```
demonstrates  →  a controlled result you can point at
shows         →  a reported result under stated conditions
suggests      →  a pattern across several papers, uncontrolled
may / might   →  a mechanism that would explain it
we hypothesize→  your own conjecture, labelled as such
```

An uncontrolled comparison across papers is a **contrast**, never an experiment
and never evidence that one method beats another. Different papers use different
data, splits and budgets; saying so once per section is not pedantry, it is the
only thing that makes the comparison honest.

## 4. Four kinds of statement, kept distinct

The reader must always be able to tell which of these they are reading:

| Kind | Marked how |
|---|---|
| **Observation** | what a paper reports, in its own terms |
| **Author claim** | what a paper concludes from that — attributed |
| **Survey inference** | what *you* conclude across papers — marked as synthesis |
| **Proposed mechanism** | your explanation for why the pattern holds — marked as conjecture |

A relation between papers that this survey created is **synthesis**. Never
attribute it to authors who did not draw it. If paper A and paper B never cite
each other and you are the one placing them on a shared axis, say so.

## 5. Citation discipline

The middle path between a citation dump and a name-dropping tour:

- **Anchors** — named, with real substance, chosen for being the best
  illustration of a concept, with venue tier as a tiebreak rather than the
  criterion.
- **Compact clusters** — a synthesizing claim ends with a short citation cluster
  covering the long tail.
- **Appendix tables** — full coverage lives there. Point to it from the prose.

A paper spanning two sections is analyzed in **both**, through the relevant lens
each time, without repeating the same paragraph. The sections cross-reference at
the handoff, in prose. Do not expose planning devices — a standalone "Handoffs"
subsection is scaffolding, not content.

## 6. Counts and systematicity

**Curated is not systematic. Say so, once, plainly.** The corpus is a judgment
call, not a census, and a reader who mistakes one for the other will read every
proportion as a population statistic.

**No paper counts in prose.** Not "N of M papers do X", not "the majority",
if the number came from counting your own corpus. Frame qualitatively — *a
dominant line*, *a smaller thread*, *an early attempt that did not carry*.
Counts may appear in appendix tables, under the curated-corpus disclaimer.

## 7. Presenting a taxonomy

If you call something a taxonomy, it must be at **one level of abstraction** and
have a **mechanical rule for boundary cases** — a rule you can apply to a new
paper without rhetoric. If it fails either test, it is still useful, but call it
dimensions, purposes or perspectives, not mutually exclusive classes.

Do not mix a taxonomy of representations with a taxonomy of pipeline stages in
one figure. They are different questions and the reader cannot hold both.

## 8. Tables and figures

- **A table must answer a question the prose asks.** A table that prints every
  value of a card field is extraction output, not evidence, and does not ship.
- A generated column must be an **enum**. A narrative field is hand-written or
  not tabled at all.
- **A truncated cell is worse than no table** — it reads as a claim the reader
  cannot check.
- **A figure earns its place by showing a mechanism a table cannot.** Otherwise
  use the table.

## 9. Prohibitions

- No emphatic bolding inside paragraphs.
- No sentence fragments for effect.
- No rhetorical questions as section openers.
- No verdicts about what the field ought to want.
- No forecasting.
- No hard line wrapping in `.tex`: one paragraph per source line, blank line
  between. Clean diffs; no effect on rendering.
