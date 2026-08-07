#!/usr/bin/env bash
# End-to-end smoke test against a throwaway project.
#
#   tests/smoke.sh [a paperlevelup topic dir] [workdir]
#
# With no corpus argument it builds a fixture one, so the whole suite runs
# offline against nothing real.
#
# Verifies: init lays out the project; build_bib produces entries; the corpus
# portrait runs; the gate reports closed and refuses to open unsigned; a bad
# prompt field block is
# rejected; a good one parses; card validation catches a bogus enum value and
# flags cards written outside the trial set while the gate is closed; and the
# card runner stamps provenance, honours the gate, refuses to mix models,
# refuses to overwrite, and checks quoted evidence against full text.

set -euo pipefail

T="$(cd "$(dirname "$0")" && pwd)"
S="$(cd "$T/.." && pwd)/scripts"
ROOT="${2:-$(mktemp -d)}"
WORK="$ROOT/smoke-project"
if [ -n "${1:-}" ]; then
  CORPUS="$1"
else
  CORPUS="$ROOT/fixture-corpus"
  python3 "$T/make_fixture_corpus.py" "$CORPUS" >/dev/null
fi
ok() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; exit 1; }

echo "corpus:  $CORPUS"
echo "project: $WORK"

python3 "$S/init.py" --corpus "$CORPUS" --project "$WORK" \
  --title "Smoke Test" --expert "Tester" >/dev/null
[ -f "$WORK/CONSTITUTION.md" ] || fail "governance docs not instantiated"
[ -L "$WORK/corpus" ] || fail "corpus not symlinked"
[ -f "$WORK/state/progress.json" ] || fail "progress.json not written"
ok "init laid out the project"

python3 "$S/build_bib.py" --project "$WORK" >/dev/null
grep -q "^@" "$WORK/inputs/references.bib" || fail "no bib entries"
ok "build_bib produced entries"

PORTRAIT="$(python3 "$S/corpus_portrait.py" --project "$WORK" --top 5)"
echo "$PORTRAIT" | grep -q '"by_category"' || fail "portrait reported no categories"
echo "$PORTRAIT" | grep -q '"papers_that_resist_their_category"' \
  || fail "portrait skipped the misfit diagnostic"
echo "$PORTRAIT" | grep -q 'menu of candidate axes' \
  || fail "portrait dropped the no-menu instruction"
ok "corpus portrait describes the corpus"

python3 "$S/gate.py" --project "$WORK" --status | grep -q '"gate": "closed"' \
  || fail "gate should start closed"
ok "gate starts closed"

if python3 "$S/gate.py" --project "$WORK" --open >/dev/null 2>&1; then
  fail "gate opened without a signature"
fi
ok "gate refuses to open unsigned"

printf 'x\n```fields\nbroken line without a pipe\n```\n' \
  > "$WORK/inputs/prompts/method_card.md"
if python3 "$S/cards.py" --project "$WORK" --check >/dev/null 2>&1; then
  fail "a malformed field block was accepted"
fi
ok "malformed field block rejected"

cat > "$WORK/inputs/prompts/method_card.md" <<'PROMPT'
# Method card
```fields
# name    | kind | values            | flags
approach  | enum | graph, sequence   | required
purpose   | text |                   | required, evidence
stages    | int  |                   |
```
PROMPT

mkdir -p "$WORK/inputs/cards/method"
cat > "$WORK/inputs/cards/method/goodpaper2024x.md" <<'CARD'
---
bib_key: goodpaper2024x
card: method
---
approach: graph
purpose: does a thing
  purpose_evidence: "it does a thing" (p. 3)
stages: 2
CARD

cat > "$WORK/inputs/cards/method/badpaper2024y.md" <<'CARD'
---
bib_key: badpaper2024y
card: method
---
approach: telepathy
purpose: does another thing
stages: many
CARD

python3 "$S/gate.py" --project "$WORK" --trial goodpaper2024x badpaper2024y >/dev/null
OUT="$(python3 "$S/cards.py" --project "$WORK" --check)"
echo "$OUT" | grep -q "outside the declared enum" || fail "bogus enum not caught"
echo "$OUT" | grep -q "without _evidence" || fail "missing evidence not caught"
echo "$OUT" | grep -q "not an integer" || fail "bad int not caught"
echo "$OUT" | grep -q '"cards_clean": 1' || fail "the good card did not validate"
ok "card validation catches enum, evidence and type problems"

cat > "$WORK/inputs/cards/method/sneaky2024z.md" <<'CARD'
---
bib_key: sneaky2024z
card: method
---
approach: graph
purpose: written before the gate opened
  purpose_evidence: "quoted" (p. 1)
CARD
python3 "$S/cards.py" --project "$WORK" --check | grep -q "gate_violation" \
  || fail "card outside the trial set not flagged while the gate is closed"
ok "gate violation detected"

python3 "$S/cards.py" --project "$WORK" --aggregate | grep -q '"approach"' \
  || fail "aggregate produced no distribution"
ok "aggregate works"

# --------------------------------------------------------------------------
# the card runner
# --------------------------------------------------------------------------
# Everything below uses --backend fake, so nothing reaches a network. The
# canned answers live in scripts/backends/fake.py.

rm -f "$WORK/inputs/cards/method/"*.md

mkdir -p "$WORK/inputs/fulltext"
for KEY in trial2024a trial2024b outside2024c; do
  cat > "$WORK/inputs/fulltext/$KEY.md" <<'PAPER'
# A Paper About Routing

We route messages along the instance graph, then decode a solution.
The encoder runs for two stages.
PAPER
done
python3 "$S/gate.py" --project "$WORK" --trial trial2024a trial2024b >/dev/null

OUT="$(python3 "$S/extract_cards.py" --project "$WORK" --type method \
  --keys trial2024a --backend fake --model smoke-model-1 --dry-run)"
echo "$OUT" | grep -q '"dry_run": true' || fail "dry run not reported as such"
echo "$OUT" | grep -q '"input_tokens_estimate_total"' || fail "no token estimate"
echo "$OUT" | grep -q '"model": "smoke-model-1"' || fail "dry run hid the model"
if [ -f "$WORK/inputs/cards/method/trial2024a.md" ]; then fail "dry run wrote a card"; fi
ok "dry run reports the plan and writes nothing"

if python3 "$S/extract_cards.py" --project "$WORK" --type method \
     --keys outside2024c --backend fake --model smoke-model-1 >/dev/null 2>&1; then
  fail "extracted a paper outside the trial set while the gate was closed"
fi
OUT="$(python3 "$S/extract_cards.py" --project "$WORK" --type method \
  --keys outside2024c --backend fake --model smoke-model-1 2>/dev/null || true)"
echo "$OUT" | grep -q '"refused": "gate_violation"' || fail "gate refusal not reported"
if [ -f "$WORK/inputs/cards/method/outside2024c.md" ]; then fail "gate-violating card written"; fi
ok "runner refuses to write past a closed gate"

OUT="$(python3 "$S/extract_cards.py" --project "$WORK" --type method \
  --keys trial2024a,trial2024b --backend fake --model smoke-model-1)"
echo "$OUT" | grep -q '"invalid": \[\]' || fail "the canned card did not validate"
grep -q '^model: smoke-model-1$' "$WORK/inputs/cards/method/trial2024a.md" \
  || fail "card front matter records no model"
grep -q '^prompt_sha256: ' "$WORK/inputs/cards/method/trial2024a.md" \
  || fail "card front matter records no prompt digest"
ok "runner writes cards stamped with model and prompt digest"

python3 "$S/cards.py" --project "$WORK" --check | grep -q '"cards_clean": 2' \
  || fail "cards.py rejected what the runner wrote"
ok "written cards pass cards.py --check"

OUT="$(python3 "$S/extract_cards.py" --project "$WORK" --type method \
  --keys trial2024a --backend fake --model smoke-model-1)"
echo "$OUT" | grep -q '"status": "exists"' || fail "overwrote an existing card"
ok "runner refuses to overwrite without --force"

if python3 "$S/extract_cards.py" --project "$WORK" --type method \
     --keys trial2024b --backend fake --model smoke-model-2 --force \
     >/dev/null 2>&1; then :; else fail "--force did not allow a second model"; fi
OUT="$(python3 "$S/extract_cards.py" --project "$WORK" --type method \
  --keys trial2024a --backend fake --model smoke-model-3 2>/dev/null || true)"
echo "$OUT" | grep -q '"refused": "model_mixing"' || fail "model mixing not refused"
ok "runner refuses to mix models within one card type"

SURVEYLEVELUP_FAKE_MODE=bad_enum python3 "$S/extract_cards.py" --project "$WORK" \
  --type method --keys trial2024a --backend fake --model smoke-model-1 --force \
  | grep -q 'outside the declared enum' || fail "pre-validation missed a bad enum"
ok "pre-validation reports an invalid card instead of retrying it"

SURVEYLEVELUP_FAKE_MODE=free_text python3 "$S/extract_cards.py" --project "$WORK" \
  --type method --keys trial2024a --backend fake --model smoke-model-1 --force \
  | grep -q '"invalid": \[\]' || fail "the FREE TEXT escape hatch was rejected"
ok "pre-validation accepts the FREE TEXT escape hatch"

OUT="$(python3 "$S/extract_cards.py" --project "$WORK" --verify-evidence --type method)"
echo "$OUT" | grep -q '"verified": 2' || fail "a real quote did not verify"
ok "verify-evidence finds quotes that are in the full text"

python3 - "$WORK" <<'PY'
import sys, pathlib
card = pathlib.Path(sys.argv[1]) / "inputs/cards/method/trial2024b.md"
text = card.read_text()
card.write_text(text.replace('"we route messages along the instance graph"',
                             '"we solve the whole thing with one transformer"'))
PY
python3 "$S/extract_cards.py" --project "$WORK" --verify-evidence --type method \
  | grep -q '"status": "not_found"' || fail "a fabricated quote was not flagged"
ok "verify-evidence flags a quote that is not in the full text"

python3 "$T/test_extract_cards.py" 2>&1 | tail -1 | grep -q '^OK' \
  || fail "extract_cards unit tests failed (run tests/test_extract_cards.py)"
ok "extract_cards unit tests pass"

echo "all smoke checks passed"
