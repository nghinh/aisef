#!/bin/zsh
# Prepare a FRESH W1 run copy exactly like w1-run-1 (P20 + the trunk-topology correction): a clone of the reference
# project with master := 8ff9f13 (the approved plan, no story work), the cost-cap commit cherry-picked from w1-run-1,
# no remote, one branch. The guard plugin is compiled and committed by the driver's prepare phase with the frozen aisef.
#   closure-evidence/hardening/w1/prepare_run_copy.sh <n>
set -e
n=$1; [ -n "$n" ] || { echo "usage: prepare_run_copy.sh <n>"; exit 2; }
P=~/Downloads/projects; REF=$P/ledgerlock-aiseftest-run2; DST=$P/w1-run-$n
[ -d "$DST" ] && { echo "REFUSED: $DST exists"; exit 1; }
git clone -q --no-hardlinks "$REF" "$DST"
cd "$DST"
git config user.name "AISEF W1 operator"; git config user.email "w1-operator@aisef.local"     # the same local identity as w1-run-1 (a fresh clone has none)
git checkout -q -B master 8ff9f13
git remote remove origin
git fetch -q "$P/w1-run-1" master          # brings the objects; fd4c644 (the cost-cap commit) is then cherry-picked by SHA
git cherry-pick --no-edit fd4c644 >/dev/null
cap=$(python3 -c "import json; print(json.load(open('.ai/config.json')).get('run.cost_cap_usd'))")
[ "$cap" = "80.0" ] || { echo "REFUSED: cost cap not applied (run.cost_cap_usd=$cap)"; exit 1; }
git for-each-ref --format='%(refname)' | grep -v '^refs/heads/master$' | while read r; do git update-ref -d "$r"; done
echo "w1-run-$n: HEAD=$(git rev-parse --short HEAD) branch=$(git rev-parse --abbrev-ref HEAD) refs=[$(git for-each-ref --format='%(refname:short)' | tr '\n' ' ')] remotes=[$(git remote | tr '\n' ' ')]"
echo "commits after 8ff9f13: $(git log --oneline 8ff9f13..master | tr '\n' ';')"
echo "ledgerlock dir at master: $(git ls-tree --name-only master | grep -c '^ledgerlock$') (0 = absent) | config: $(python3 -c "import json; print(json.load(open('.ai/config.json')).get('run.cost_cap_usd'))")"
git status --short | head -3; echo "(clean)"
