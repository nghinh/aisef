#!/bin/zsh
# QP-2.9 — LedgerLock regression (DEVELOPMENT_REGRESSION) on the ONE Cycle-2 candidate: the guards before and after,
# the run inside an owned process range, the kernel tree checked before and after. A rerun is a new attempt directory.
#
#   validation/qualification/c2_p9_run.sh
#   ATTEMPT=3 PROFILE=delivery-experiment-1 validation/qualification/c2_p9_run.sh   # the ONE preregistered delivery run:
#       NOT AUTHORIZED until the owner authorizes it (DELIVERY-EXPERIMENT-1-PREREGISTRATION.json). This script only
#       orchestrates: the runner itself (c2_p9.run) refuses unless the preregistration holds and the attempt holds a
#       verified ATTESTED preflight record — calling it directly opens nothing.
set -u; unsetopt nomatch
A=${0:A:h:h:h}; cd $A                          # the checkout this script is in (attempts 1 and 2 ran in the main one)
OUT=$A/closure-evidence/v2/cycle2/P10
KT=c2717d2ed98b76bd3d284a37c47103b5dc2bd020   # the corrected kernel 4f6dfc1 (K-NOWORK-001, on K-PRESAT-001 d427299); attempts 1 and 2 ran 37bf6457… (ac4a6c7)
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
PROFILE=${PROFILE:-qp-2.9}   # v1-aligned: the proposed 3-attempt profile of the controlled V1-vs-V2 experiment (never the default)
DX=validation/qualification/c2_delivery_experiment.py
HEAD0=$(git rev-parse HEAD)
echo "[$(stamp)] QP-2.9: LedgerLock regression, kernel tree $KT, HEAD $(git rev-parse --short HEAD), profile $PROFILE"
guards start || exit 1
mkdir -p $OUT/owned
if [ "$PROFILE" = delivery-experiment-1 ]; then
  # preregistration verification -> provider preflight -> ATTESTED tuple built and verified -> resolved RunSpec frozen;
  # only then does the runner unlock delivery. The preflight is made once and its requests are in the budget.
  python3 -P $DX --check || { echo "REFUSED: the delivery experiment is not as preregistered"; exit 1; }
  python3 -P $DX --attest || { echo "REFUSED: the model identity was not attested — delivery stays locked, no run"; exit 1; }
fi
python3 -P validation/v2/owned_run.py --out $OUT/owned/run.attempt-$ATTEMPT.json -- python3 -P validation/qualification/c2_p9.py --run --attempt $ATTEMPT --profile $PROFILE
RC=$?
echo "[$(stamp)] run rc=$RC"
[ "$(git rev-parse HEAD:aisef2)" = "$KT" ] || { echo "STOP: the kernel tree changed during the run"; exit 3; }
[ "$(git rev-parse HEAD)" = "$HEAD0" ] || { echo "STOP: HEAD moved during the run"; exit 3; }
guards end || exit 3
if [ "$PROFILE" = delivery-experiment-1 ]; then     # no request is made after the run: there is no budget outside the budget
  python3 -P $DX --check --after-run || { echo "STOP: the preregistered identities changed during the run"; exit 3; }
fi
exit $RC
