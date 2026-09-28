#!/bin/zsh
# P10 — LedgerLock as a DEVELOPMENT / REGRESSION benchmark on ONE exact candidate (owner's P10 / QP-10 EXECUTION AUTHORIZATION):
# F1-F11 and the V1 guard before and after, the run inside an owned process range, the kernel tree checked before and after.
#
#   validation/qualification/p10_run.sh
set -u; unsetopt nomatch
A=/Users/nghinh/Downloads/projects/ai-sdlc; cd $A
OUT=$A/closure-evidence/v2/P10
SP=${AISEF_SCRATCH:-/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad}
LOG=$SP/p10-logs; mkdir -p $LOG $OUT/owned
KT=4d6081940f5b9dae47439f73f0157161e028d804
stamp() { date '+%F %T'; }
DIRTY=$(git status --porcelain | grep -v '^?? closure-evidence/v2/P10/\|^ M closure-evidence/v2/P10/\|^?? closure-evidence/v2/P10-RUN-HISTORY.json\|^ M closure-evidence/v2/P10-RUN-HISTORY.json' || true)
[ -z "$DIRTY" ] || { echo "REFUSED: the working tree is dirty outside P10's output:"; echo "$DIRTY"; exit 1; }
[ "$(git rev-parse HEAD:aisef2)" = "$KT" ] || { echo "REFUSED: HEAD's aisef2 tree is not the candidate's $KT"; exit 1; }
ATTEMPT=${ATTEMPT:-1}
[ -f $OUT/LEDGERLOCK-REGRESSION.json ] && { echo "REFUSED: LEDGERLOCK-REGRESSION.json exists — a rerun is a new attempt directory"; exit 1; }
echo "[$(stamp)] P10: LedgerLock regression attempt $ATTEMPT, kernel tree $KT, HEAD $(git rev-parse --short HEAD)"
python3 -P validation/qualification/p10.py --conformance start || { echo "REFUSED: conformance at start"; exit 1; }
python3 -P validation/v2/owned_run.py --out $OUT/owned/run.attempt-$ATTEMPT.json -- \
  python3 -P validation/qualification/p10.py --run > $LOG/run.attempt-$ATTEMPT.log 2>&1
RC=$?
cat $LOG/run.attempt-$ATTEMPT.log
echo "[$(stamp)] run rc=$RC"
[ "$(git rev-parse HEAD:aisef2)" = "$KT" ] || { echo "STOP: the kernel tree changed during the run"; exit 3; }
python3 -P validation/qualification/p10.py --conformance end || { echo "STOP: conformance at end"; exit 3; }
exit $RC
