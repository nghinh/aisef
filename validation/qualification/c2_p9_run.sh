#!/bin/zsh
# QP-2.9 — LedgerLock regression (DEVELOPMENT_REGRESSION) on the ONE Cycle-2 candidate: the guards before and after,
# the run inside an owned process range, the kernel tree checked before and after. A rerun is a new attempt directory.
#
#   validation/qualification/c2_p9_run.sh
set -u; unsetopt nomatch
A=/Users/nghinh/Downloads/projects/ai-sdlc; cd $A
OUT=$A/closure-evidence/v2/cycle2/P10
KT=37bf6457f350dd720a2214f04f3896c554ad0904   # the Cycle-2 candidate ac4a6c7 kernel tree (QP-2.9; QP-2.6 R2)
stamp() { date '+%F %T'; }
DIRTY=$(git status --porcelain | grep -v '^?? closure-evidence/v2/cycle2/P10/\|^ M closure-evidence/v2/cycle2/P10/\|C2-P9-RUN-HISTORY.json' || true)
[ -z "$DIRTY" ] || { echo "REFUSED: the working tree is dirty outside QP-2.9's output:"; echo "$DIRTY"; exit 1; }
[ "$(git rev-parse HEAD:aisef2)" = "$KT" ] || { echo "REFUSED: HEAD's aisef2 tree is not the candidate's $KT"; exit 1; }
ATTEMPT=${ATTEMPT:-1}
DIR=$OUT; [ "$ATTEMPT" = 1 ] || DIR=$OUT/attempt-$ATTEMPT
{ [ -f $DIR/LEDGERLOCK-REGRESSION.json ] || [ -f $DIR/NO-RECORD.json ]; } && { echo "REFUSED: attempt $ATTEMPT already left a record in $DIR — a rerun is a new attempt (ATTEMPT=N)"; exit 1; }
guards() {
  for g in "cycle2_baseline.py --check" "freeze_conformance.py --check" "v1_evidence_guard.py --check"; do
    python3 -P validation/v2/${=g} > /dev/null || { echo "guard $g FAILED ($1)"; return 1; }
  done
  echo "[$(stamp)] guards PASS ($1)"
}
echo "[$(stamp)] QP-2.9: LedgerLock regression, kernel tree $KT, HEAD $(git rev-parse --short HEAD)"
guards start || exit 1
mkdir -p $OUT/owned
python3 -P validation/v2/owned_run.py --out $OUT/owned/run.attempt-$ATTEMPT.json -- python3 -P validation/qualification/c2_p9.py --run --attempt $ATTEMPT
RC=$?
echo "[$(stamp)] run rc=$RC"
[ "$(git rev-parse HEAD:aisef2)" = "$KT" ] || { echo "STOP: the kernel tree changed during the run"; exit 3; }
guards end || exit 3
exit $RC
