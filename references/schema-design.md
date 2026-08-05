# Designing the card schema

**The schema decides which sections you can write.** A section can only compare
what the cards carry. Discover a gap after extracting and you pay for it with a
re-extraction round over the whole corpus — which is why this is the one thing
the extraction gate guards.

---

## Derive it backwards

Never forwards from "what is interesting about these papers". Always backwards:

```
the axis  →  the section list  →  per section, the dimensions it compares
          →  per dimension, a card field  →  per field, its kind and values
```

Concretely, for each planned section:

1. Write the sentence the section exists to support.
2. Name the dimensions along which papers differ in that sentence.
3. For each, ask: what would a card have to carry for me to write this without
   reopening the PDFs?
4. Add that field. Decide its kind and, if it is an enum, its values.

If step 3 has no answer, either the section is not really comparative — it is a
narrative section, and it will be written from full text — or the dimension is
not yet sharp enough to be a dimension.

Run the reverse check too: **every field must be traceable to a section.** A
field nobody asked for is extraction for its own sake, and it costs the same to
fill as a useful one.

## One schema per paper type

Not one universal schema. Papers come in kinds that resist the same treatment.

| Kind | The card | Why |
|---|---|---|
| **Method** | the card is enough | The comparable dimensions are exactly what makes methods comparable |
| **Benchmark / dataset** | deliberately lossy | Their value is narrative and idiosyncratic — how the data was built, what was deduplicated, how label noise was measured, which biases are known. A `field: value` card compresses away the whole reason to cite them |
| **Position / survey** | thin, mostly narrative | You are citing a claim and its scope, not a system |

**Never write a data or benchmark section from cards alone.** Read those papers'
full text and fold the specifics into prose. The card exists so the paper appears
in coverage tables, not so you can write about it without reading it.

A paper can carry two cards if it genuinely does two things. That is cheaper than
bending one schema to cover both.

## Declaring fields

Each prompt declares its fields in a fenced block, so validation is mechanical:

````
```fields
# name            | kind | values                        | flags
input_granularity | enum | token, sentence, document     | required
objective         | text |                               | required, evidence
n_stages          | int  |                               |
datasets          | list |                               |
```
````

- **kind** — `text`, `enum`, `int`, `list`
- **flags** — `required`, `evidence`, comma-separated, either may be absent

`cards.py --check` enforces exactly this: required fields present, enum values in
range, integers integral, evidence present where declared, and no field that the
prompt did not declare.

## Enums, and the escape hatch

An enum is a claim that the dimension has a small closed set of answers. Design
them from a sample of real papers, never from first principles — first-principles
enums acquire an "other" bucket that swallows a third of the corpus and means
nothing.

When a value genuinely does not fit, the card writes:

```
purpose: FREE TEXT — <what the paper actually does>. Suggested label: <candidate>
```

Validation accepts this. The point is that an unfitting value becomes **visible
and named** instead of being crushed into the nearest enum member. When the same
suggested label recurs, promote it into the enum and re-run the affected cards.

An enum that needs the escape hatch on most papers is the wrong enum. An enum
nothing escapes is probably too coarse to distinguish anything.

## Evidence fields

Any field carrying judgment gets `<field>_evidence` with a **verbatim quote and a
page number**:

```
★ query_granularity: document-level
  query_granularity_evidence: "despite lacking author information, ..." (p. 7)
```

This is what makes a card re-checkable rather than something to be believed. The
`★` marker is cosmetic — use it to mark the fields you had to think about, so a
later reader knows where the judgment calls were. Validation strips it.

Mechanical fields — year, backbone, dataset names — need no evidence.

## `not reported` is not `absent`

Distinguish, in the prompt and in the enum:

- **`not reported`** — the paper did not say. Says nothing about the method.
- **`none` / `n/a`** — the paper says there is none, or the field cannot apply.

Getting this wrong produces confident false claims about what methods lack. State
the distinction in the prompt itself, because whoever reads the cards later will
read the prompt to learn the field semantics — and if they do not, that is its
own problem worth preventing.

## What does not go in a card

- **Anything whose unit is not one paper.** How paper A treats paper B is a
  property of the *pair*; putting it in A's card breaks the unit of analysis. Use
  `corpus_ancestors`, `corpus_descendants` and a free-text `lineage` for what a
  paper extends, borrows or attacks from its own side — and if the project needs
  more, `state/stances.jsonl` for contested pairs only.
- **Your synthesis.** A card holds what the paper reports. What you conclude
  across papers is a finding; it goes in `FINDINGS.md`.
- **Counts and aggregates.** Those are computed from cards, never stored in them.

## Try it on a handful first

Before crossing the extraction gate, run the schema on five or six papers chosen
to stress it: one easy, one benchmark, one position paper, and the two you most
expect to break it. Name them in advance — picking the test cases after seeing
the result proves nothing.

Then check:

- Does every planned section now have fields to draw on?
- Did any field turn out to have no stable meaning across the five?
- Did the escape hatch fire more than occasionally?
- Could someone else fill this card from the same paper and get the same answer?

Any "no" means you are still in the loop. That is the cheapest possible place to
find out.

## Revising after the gate

Cards will reveal things the schema did not anticipate. Two responses:

**Live with it.** If the gap affects one section and the fact is recoverable from
full text, read it there and record it under "facts taken from full text" in
`PROVENANCE.md`. Do not write it back into the card.

**Re-extract.** If the gap is structural — a dimension the axis depends on has no
field — revise the prompt, record the change in `PROVENANCE.md`, mark the old
cards superseded, and re-run the affected ones. Note that cards produced by two
versions of a prompt are two different artifacts; never edit the old ones to
match.

Choosing to re-extract is a decision, not a failure. Log it in `DECISIONS.md`
with what the gap was, so the next schema starts from a sharper prior.
