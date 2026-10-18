#!/bin/zsh
# E2 / W2 — the OWNER's approvals (EXPERIMENT-PLAN "Trình tự" step 1: duyệt evaluator ẩn, từng contract).
# Nothing here is run by the lane. Replace human:NAME with `human:` and your name; `aisef bundle approve` refuses the
# placeholder as it is. Each command reads the file the previous one wrote; the last file of each chain is the one to use.
#
#   zsh APPROVE.sh human:yourname          (from this directory; writes approved-*.json here, never over an input)
set -eu
D=${0:A:h}; W=${D:h:h:h:h:h}            # the AISEF worktree (closure-evidence/v2/v2.1/e2/w2 -> 5 up)
export PYTHONPATH=$W PYTHONDONTWRITEBYTECODE=1
PY=(/opt/homebrew/bin/python3 -P -B -m aisef bundle approve)
APPROVER=${1:-human:NAME}
cd "$D"
# the HIDDEN evaluator (12 contracts, 13 contract-requirement pairs) — no arm ever sees this file or any approved-hidden-*.json
IN=hidden/evaluator.json; n=0
for c in H-DIR H-MISSING H-REG-OK H-REG-BAD H-REG-MISSING H-REG-LIST H-JSON H-JSON-ZERO H-CITED H-TARGET H-REPORT H-STDLIB; do
  n=$((n+1)); OUT=hidden/approved-$n-$c.json
  $PY "$IN" --contract "$c" --approver "$APPROVER" --out "$OUT" > /dev/null; IN=$OUT
done
cp "$IN" hidden/approved.json; echo "hidden evaluator approved: hidden/approved.json"
# the ARMS' bundle (7 contracts) — the bundle arms B and C run
IN=arms/bundle.json; n=0
for c in A-ROOT-DIR A-ROOT-MISSING A-REG-PATH A-REG-BAD A-JSON A-STDLIB A-CITED; do
  n=$((n+1)); OUT=arms/approved-$n-$c.json
  $PY "$IN" --contract "$c" --approver "$APPROVER" --out "$OUT" > /dev/null; IN=$OUT
done
cp "$IN" arms/approved.json; echo "arms bundle approved: arms/approved.json"
/opt/homebrew/bin/python3 -P -B -m aisef bundle lint hidden/approved.json > hidden/lint-approved.json && echo "hidden lint: READY"
/opt/homebrew/bin/python3 -P -B -m aisef bundle lint arms/approved.json > arms/lint-approved.json && echo "arms lint: READY"
