#!/bin/zsh
# Q5 — the real-execution reproduction of the frozen corpus on ONE exact candidate (owner's P9 / QP-9 EXECUTION AUTHORIZATION):
# the subject frozen before the first reproduction, F1-F11 (F1, F9 in particular) and the V1 guard measured before and after,
# every corpus item reproduced inside an owned process range — the model stream replayed, everything else executed again.
#
#   validation/qualification/q5_run.sh
set -u; unsetopt nomatch
A=/Users/nghinh/Downloads/projects/ai-sdlc; cd $A
OUT=$A/closure-evidence/v2/Q5
SP=${AISEF_SCRATCH:-/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad}
LOG=$SP/q5-logs; mkdir -p $LOG $OUT/owned
KT=4d6081940f5b9dae47439f73f0157161e028d804
stamp() { date '+%F %T'; }
DIRTY=$(git status --porcelain | grep -v '^?? closure-evidence/v2/Q5/\|^ M closure-evidence/v2/Q5/\|^?? closure-evidence/v2/P9-RUN-HISTORY.json\|^ M closure-evidence/v2/P9-RUN-HISTORY.json' || true)
[ -z "$DIRTY" ] || { echo "REFUSED: the working tree is dirty outside Q5's output:"; echo "$DIRTY"; exit 1; }
[ "$(git rev-parse HEAD:aisef2)" = "$KT" ] || { echo "REFUSED: HEAD's aisef2 tree is not the candidate's $KT"; exit 1; }
[ -f $OUT/CORPUS.json ] || { echo "REFUSED: no frozen corpus (q5.py --record first, committed)"; exit 1; }
[ -f $OUT/CALIBRATION.json ] && python3 -P -c "import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))['all_rejected'] else 1)" $OUT/CALIBRATION.json \
  || { echo "REFUSED: no calibration with every defect rejected (q5.py --calibrate first)"; exit 1; }
ATTEMPT=${ATTEMPT:-1}
[ -d $OUT/reproduction ] && { echo "REFUSED: reproduction records exist — a rerun is a new attempt: move them under attempt-N/ and pass ATTEMPT=N"; exit 1; }
echo "[$(stamp)] Q5: reproduction attempt $ATTEMPT, kernel tree $KT, HEAD $(git rev-parse --short HEAD)"
[ -f $OUT/SUBJECT.json ] || python3 -P validation/qualification/q5.py --freeze || { echo "REFUSED: the subject could not be frozen"; exit 1; }
python3 -P validation/qualification/q5.py --conformance start || { echo "REFUSED: conformance at start"; exit 1; }
python3 -P validation/v2/owned_run.py --out $OUT/owned/reproduction.attempt-$ATTEMPT.json -- \
  python3 -P validation/qualification/q5.py --reproduce > $LOG/reproduce.attempt-$ATTEMPT.log 2>&1
RC=$?
cat $LOG/reproduce.attempt-$ATTEMPT.log
echo "[$(stamp)] reproduction rc=$RC"
[ "$(git rev-parse HEAD:aisef2)" = "$KT" ] || { echo "STOP: the kernel tree changed during the run"; exit 3; }
python3 -P validation/qualification/q5.py --conformance end || { echo "STOP: conformance at end"; exit 3; }
exit $RC
