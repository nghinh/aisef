#!/bin/zsh
# Prepare a FRESH W1 run copy exactly like w1-run-1 (P20 + the trunk-topology correction): a clone of the reference
# project with master := 8ff9f13 (the approved plan, no story work), the cost-cap commit cherry-picked from w1-run-1,
# no remote, one branch. The guard plugin is compiled and committed by the driver's prepare phase with the frozen aisef.
#   closure-evidence/hardening/w1/prepare_run_copy.sh <n> [<venv> <dest-dir>]   (the two optional arguments: rehearsal only)
set -e
n=$1; [ -n "$n" ] || { echo "usage: prepare_run_copy.sh <n> [<venv> <dest-dir>]"; exit 2; }
P=~/Downloads/projects; REF=$P/ledgerlock-aiseftest-run2; DST=${3:-$P/w1-run-$n}
COSTCAP_SRC=$P/w1-run-1-aborted-sast; [ -d "$COSTCAP_SRC" ] || COSTCAP_SRC=$P/w1-run-1
[ -d "$DST" ] && { echo "REFUSED: $DST exists"; exit 1; }
git clone -q --no-hardlinks "$REF" "$DST"
cd "$DST"
git config user.name "AISEF W1 operator"; git config user.email "w1-operator@aisef.local"     # the same local identity as w1-run-1 (a fresh clone has none)
# PLAN_BASE: the approved plan commit the copy starts from. 8ff9f13 is W1_WORKLOAD_V1; W1-LEDGERLOCK-PLAN-V2 is
# 1621a2bc (closure-evidence/hardening/w1/plan-v2/PLAN-V2-APPLIED.json), where every criterion carries its proof
# obligation. The run copy always starts at an approved plan with no story work.
PLAN_BASE=${PLAN_BASE:-8ff9f13}
git checkout -q -B master $PLAN_BASE
git remote remove origin
git fetch -q "$COSTCAP_SRC" master        # brings the objects; fd4c644 (the cost-cap commit) is then cherry-picked by SHA
git cherry-pick --no-edit fd4c644 >/dev/null
cap=$(python3 -c "import json; print(json.load(open('.ai/config.json')).get('run.cost_cap_usd'))")
[ "$cap" = "80.0" ] || { echo "REFUSED: cost cap not applied (run.cost_cap_usd=$cap)"; exit 1; }
# SS-65: the reference project pins the python environment by name; the name carries the recipe digest, so the frozen
# candidate's environment has a new name. Re-pin to exactly the frozen candidate's python profile image.
F=/Users/nghinh/Downloads/projects/ai-sdlc/closure-evidence/hardening/P19-FREEZE.json
VENV=${2:-$(python3 -c "import json; print(json.load(open('$F'))['run_venv']['path'])")}
IMG=$("$VENV/bin/python" -c "from aisef.harness.capabilities import profile_by_stack; print(profile_by_stack('python').image)")
[ -n "$IMG" ] || { echo "REFUSED: cannot read the frozen candidate's python image"; exit 1; }
python3 - "$IMG" <<'PYI'
import json, sys
p = ".ai/config.json"; c = json.load(open(p)); old = c.get("sandbox.image"); c["sandbox.image"] = sys.argv[1]
open(p, "w").write(json.dumps(c, indent=2, ensure_ascii=False) + "\n"); print(f"sandbox.image: {old} -> {sys.argv[1]}")
PYI
git commit -q -am "w1-run-$n: sandbox.image re-pinned to the frozen candidate's python environment $IMG (SS-65: the recipe now carries bandit)"
# Execution profile (owner decision "EXECUTION PROFILE NOT QUALIFIED", section 3): PROFILE=<profile.json> applies the
# profile's typed settings — run.max_turns, route.<role>_model, the project-level model declaration — as one named
# preparation commit. Without PROFILE the copy is the original PROFILE-W1-OC-MYCOMBO-T40 configuration.
if [ -n "$PROFILE" ]; then
  files=$(python3 /Users/nghinh/Downloads/projects/ai-sdlc/closure-evidence/hardening/w1/execution_profile.py apply "$PROFILE" "$DST")
  PNAME=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['profile'])" "$PROFILE")
  git add ${=files}
  git commit -q -m "w1-run-$n: execution profile $PNAME applied (run.max_turns, route.<role>_model, project model declaration — an execution-profile setting, not an AISEF change)"
fi
git for-each-ref --format='%(refname)' | grep -v '^refs/heads/master$' | while read r; do git update-ref -d "$r"; done
echo "w1-run-$n: HEAD=$(git rev-parse --short HEAD) branch=$(git rev-parse --abbrev-ref HEAD) refs=[$(git for-each-ref --format='%(refname:short)' | tr '\n' ' ')] remotes=[$(git remote | tr '\n' ' ')]"
echo "commits after $PLAN_BASE: $(git log --oneline $PLAN_BASE..master | tr '\n' ';')"
echo "ledgerlock dir at master: $(git ls-tree --name-only master | grep -c '^ledgerlock$') (0 = absent) | config: $(python3 -c "import json; print(json.load(open('.ai/config.json')).get('run.cost_cap_usd'))")"
git status --short | head -3; echo "(clean)"
