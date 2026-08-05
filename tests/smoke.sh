#!/usr/bin/env bash
# End-to-end smoke test against a throwaway project.
#
#   tests/smoke.sh <a paperlevelup topic dir> [workdir]
#
# Verifies: init lays out the project; build_bib produces entries; the gate
# reports closed and refuses to open unsigned; a bad prompt field block is
# rejected; a good one parses; card validation catches a bogus enum value and
# flags cards written outside the trial set while the gate is closed.

set -euo pipefail

CORPUS="${1:?usage: smoke.sh <paperlevelup topic dir> [workdir]}"
WORK="${2:-$(mktemp -d)}/smoke-project"
S="$(cd "$(dirname "$0")/../scripts" && pwd)"
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

echo "all smoke checks passed"
