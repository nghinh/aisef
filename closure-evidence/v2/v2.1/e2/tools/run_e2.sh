#!/bin/zsh
# run_e2.sh D [MAX_RUNS]  — the operator's one command for the REAL E2 campaign on a directory e2_setup.py built.
#
#   zsh closure-evidence/v2/v2.1/e2/tools/run_e2.sh "$D" 18        # all 18 runs (resumes: a run with RESULT.json is skipped)
#   zsh closure-evidence/v2/v2.1/e2/tools/run_e2.sh "$D" 3         # the next 3 runs only
#
# Before anything: refuses while the machine-wide heavy lock (campaign-9/tools/heavy.sh) is held by a live job, while any
# `mutation.py run` process exists (campaign 9 must be finished), without NINEROUTER_API_KEY in the environment (its value
# is never printed, never an argument: e2_launch.py copies it into the driver's environment), and while D/out/STOP exists.
# Then it takes the heavy lock through heavy.sh (by path) and runs e2_launch.py under it, nice 19: client version +
# realpath + sha256 recorded, store_stat on $HOME before and after, the hermetic environment, the driver
# (validation/experiments/campaign.py run ... --max-runs MAX_RUNS, stdout/stderr -> D/run.log), replay, summary,
# D/records and the secret scan. It writes to D only and prints the rsync command for the records.
#
# E2_OFFLINE=1 (tools/test_launch_offline.sh only): no lock, no campaign-9 check, no key; e2_launch.py then accepts only
# the dry run's fake client (CLIENT_EXE) and the loopback fake provider. Never for a paid run.
set -eu
D=${1:?usage: run_e2.sh D [MAX_RUNS]}; N=${2:-18}
T=${0:A:h}; REPO=${T:h:h:h:h:h}
SPD=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
HEAVY=$REPO/closure-evidence/v2/v2.1/campaign-9/tools/heavy.sh
PY=/opt/homebrew/bin/python3
if [[ ! -f $D/CAMPAIGN-real.json || ! -f $D/SETUP.json ]]; then
  echo "run_e2.sh: refused: $D is not a campaign directory (e2_setup.py first)" >&2; exit 2
fi
if [[ -e $D/out/STOP ]]; then
  echo "run_e2.sh: refused: $D/out/STOP exists — remove it to resume" >&2; exit 3
fi
if [[ ${E2_OFFLINE:-0} == 1 ]]; then
  echo "run_e2.sh: $(date '+%F %T %z') OFFLINE (E2_OFFLINE=1): no heavy lock, no campaign-9 check, fake client and loopback provider only"
  exec nice -n 19 $PY -P -B "$T/e2_launch.py" "$D" "$N"
fi
L=$SPD/heavy.lock.d
if [[ -d $L ]]; then
  o=$(cut -d' ' -f2 "$L/owner" 2>/dev/null || true)
  if [[ -n $o ]] && ps -p "$o" >/dev/null 2>&1; then
    echo "run_e2.sh: refused: the heavy lock is held by a live job: $(cat "$L/owner")" >&2; exit 2
  fi
fi
if pgrep -fq 'mutation\.py run'; then
  echo "run_e2.sh: refused: a 'mutation.py run' process exists — campaign 9 is not finished:" >&2
  pgrep -fl 'mutation\.py run' | cut -c1-120 >&2; exit 2
fi
if [[ -z ${NINEROUTER_API_KEY:-} ]]; then
  echo "run_e2.sh: refused: NINEROUTER_API_KEY is not set in this environment (its value is never printed)" >&2; exit 2
fi
if [[ ! -f $HEAVY ]]; then
  echo "run_e2.sh: refused: $HEAVY is missing" >&2; exit 2
fi
echo "run_e2.sh: $(date '+%F %T %z') taking the heavy lock ($HEAVY) for $D, max_runs $N"
exec zsh "$HEAVY" e2-campaign nice -n 19 $PY -P -B "$T/e2_launch.py" "$D" "$N"
