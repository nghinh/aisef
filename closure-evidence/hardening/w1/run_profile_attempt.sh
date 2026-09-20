#!/bin/zsh
# One W1 attempt under an execution profile (owner decision "CONTINUE W1 PROFILE QUALIFICATION", 2026-09-19):
#   1. provider-stability preflight on the profile's route — FAIL = no run copy is created (section 5);
#   2. a fresh run copy (prepare_run_copy.sh + PROFILE);
#   3. the driver: prepare (preflight incl. identity + reviewer read-only check) -> kernel-first -> approve -> run -> finish.
#   closure-evidence/hardening/w1/run_profile_attempt.sh <profile.json> <run-tag>        e.g. ... PROFILE-...GPT55... gpt55-ro-1
set -u
A=/Users/nghinh/Downloads/projects/ai-sdlc; cd $A
PROFILE=${1:A}; TAG=$2          # absolute: prepare_run_copy.sh changes into the new copy
F=$A/closure-evidence/hardening/P19-FREEZE.json
V=$(python3 -P -c "import json,sys; print(json.load(open(sys.argv[1]))['run_venv']['path'])" $F)
O=$(python3 -P -c "import json,sys; print(json.load(open(sys.argv[1]))['oracle_venv']['path'])" $F)
ROUTE=$(python3 -P -c "import json,sys; print(json.load(open(sys.argv[1]))['identity']['routes']['developer'])" $PROFILE)
RD=$A/closure-evidence/hardening/w1/run-$TAG; mkdir -p $RD
echo "[$(date '+%F %T')] attempt $TAG profile=$(basename $PROFILE) route=$ROUTE"
python3 closure-evidence/hardening/w1/provider_preflight.py $ROUTE --probes 3 --smokes 2 --out $RD/PROVIDER-PREFLIGHT.json || { echo "PROVIDER PREFLIGHT FAILED — no run created"; exit 3; }
PLAN_BASE=${PLAN_BASE:-8ff9f13}
PROFILE=$PROFILE PLAN_BASE=$PLAN_BASE closure-evidence/hardening/w1/prepare_run_copy.sh $TAG || { echo "PREPARE FAILED"; exit 4; }
for ph in prepare kernel-first approve run finish; do
  python3 closure-evidence/hardening/w1/w1_driver.py --run $TAG --project ~/Downloads/projects/w1-run-$TAG --aisef $V/bin/aisef \
    --python $V/bin/python --oracle-python $O/bin/python --freeze $F --profile $PROFILE --plan-base $PLAN_BASE \
    --phase $ph || { echo "STOP at phase $ph"; exit 5; }
done
echo "[$(date '+%F %T')] attempt $TAG complete"
