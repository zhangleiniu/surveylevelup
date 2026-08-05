# Deriving the axis

The survey's value is rarely that it covered N papers. It is **one organizing
axis that dissolves the field's surface split, and can be stated precisely enough
to decide boundary cases mechanically.**

This document is about finding that axis. It is the part of the work that cannot
be delegated to a script, and the part where a wrong answer costs the most,
because the axis determines the sections, the sections determine the schema, and
the schema determines what you can write at all.

---

## An axis is not a topic

| Not an axis | An axis |
|---|---|
| "Methods for X" | the variable along which methods for X actually differ |
| the corpus's category folders | the thing those categories are a symptom of |
| a list of subfields | one question every paper in the corpus answers differently |

Test: can you take a paper nobody has classified yet and place it on the axis by
applying a stated rule? If placing it requires an argument each time, it is a
theme, not an axis.

## The trap: inheriting the corpus taxonomy

The categories a corpus is organized into were built **for reading** — to route
papers to a folder so a human can find them. They are optimized for "where would
I look for this", not for "what does this field disagree about". They will be
sitting there, already agreed, already stable, at exactly the moment you need an
outline. Taking them is the single most common way an expert survey ends up
mechanical.

The same applies to a taxonomy inherited from the field's own vocabulary, and to
one derived by decomposing every paper into stages and then evaluating each
stage. Both produce a structure that is defensible, complete, and says nothing.

## The move

1. **Distrust the field's camps.** Where two accepted categories *overlap*, or
   where the same paper gets labelled differently by different authors, the split
   is cutting the wrong joint. That inconsistency is not noise to be tidied — it
   is the signal. Go there first.

2. **Find the deeper variable the camps are symptoms of.** The camps usually
   differ on something visible (an architecture, a framework, a community). Ask
   what varies *underneath* that the visible difference tracks imperfectly.

3. **Classify by the load-bearing component**, not by which parts are present.
   Many papers contain the same ingredients; what distinguishes them is which
   ingredient carries the weight.

4. **Formalize your own concepts.** Give precise — where possible, mathematical —
   definitions of the terms *you* introduce. Not generic ones. This is what turns
   boundary cases from rhetorical arguments into mechanical decisions, and it is
   the thing a reader can actually take away and reuse.

5. **De-emphasize the loud axis, foreground the quiet one.** Ask which variable
   is actually decisive for this domain. It is often not the one the field
   advertises in its titles.

## Diagnostics worth running

These are cheap and they surface structure you will not see by reading in order.

**Publication year by category.** Compute the year distribution per category and
the share published after some cut. It tells you which parts of the field are
accelerating, which have gone quiet, and where the existing surveys stopped. A
category with a sharp peak and a long tail of nothing is either finished or
abandoned — and which of those it is, is a claim worth making.

**Papers that resist classification.** Keep a list of the papers that were
genuinely hard to place, and of any you had to cross-list. Under the right axis,
most of them stop being hard. If a candidate axis leaves the same papers awkward,
it is not the axis. If it makes a previously coherent group split cleanly along a
line nobody had drawn, that is evidence it is.

**Who reacts to whom.** Chains of papers that correct, refute or re-evaluate each
other are usually the highest-value content a survey has, and they rarely appear
in any taxonomy. Follow them explicitly.

### Their traps

**A year distribution reflects your collection, not the field.** A category that
looks dead may just be where you stopped collecting. Before making the claim,
search that category specifically for recent work. A narrative built on "activity
migrated from A to B" is worthless if it is really "the collector's attention
migrated".

**Internal citation counts do not measure relevance in a seed set.** A curated
corpus is a set of seeds, not a sample. Counting how often a paper is cited *by
the other papers you happen to hold* is confounded three ways at once: recency (a
2026 paper cannot be cited by a corpus that ends in 2026), venue coverage (if
your metadata source indexes some venues and not others, whole communities are
structurally invisible), and collection bias. Papers that are central to the topic
routinely score zero. Use citation structure to find *chains and reactions*, never
to decide whether a paper belongs.

**Reference coverage is uneven, not random.** Bibliographic sources cover
publisher-deposited references far better than preprints. A thin citation graph
over a preprint-heavy corpus is a coverage artifact. Quote the ratio rather than
letting a half-covered graph pass as a complete one.

## Testing a candidate axis

Before building an outline on it, check all four:

- **Does it produce non-trivial comparative claims?** If every section under it
  would say "papers in this group do the group's thing", the axis is a label, not
  a variable.
- **Does it place the awkward papers?** Take the ones that resisted the reading
  taxonomy. If they are still awkward, keep looking.
- **Does it survive the papers you expect to break it?** Name them in advance,
  then check. Choosing the test cases after seeing the result proves nothing.
- **Is it decidable?** State the rule. Hand it to someone with a paper you have
  not discussed. If they cannot place it, the axis is not yet formal enough.

An axis that passes all four but is *obvious* is still a good axis. Novelty is
not the criterion; being load-bearing is.

## Record what you rejected

Every candidate axis you consider and drop goes into `DECISIONS.md` with the
reason it failed. Two lines each.

This is not bookkeeping. Deriving an axis takes several sessions, and without the
list the work circles: an axis is tried, abandoned for a good reason, forgotten,
and proposed again three sessions later as a fresh idea. Read the list before
proposing a new one, and make the new one differ from all of them in kind, not in
wording.

## When to stop

Stop when the axis places the awkward papers, survives its named tests, and
generates a section list where each section has something to compare. Not when it
is elegant.

Then write it into `CONSTITUTION.md` as one sentence, with the section list and
the dimensions each section compares, and get the expert to approve it. That
sentence is what the schema is derived from.
