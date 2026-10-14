#!/bin/zsh
# B-09 canary, tier 1: the real preflight only (4 provider requests ceiling; the first session request would exceed it).
# Run from anywhere:  zsh <this file>     (writes run/, run.anchor, store-before/after.json, started/finished.txt next to it)
set -u
D=${0:A:h}; W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21
export PYTHONPATH=$W PYTHONDONTWRITEBYTECODE=1; PY=/opt/homebrew/bin/python3
SS=$W/closure-evidence/v2/v2.1/isolation/tools/store_stat.py
cd $D || exit 9
[[ ! -e run ]] || { echo "run/ exists: a record is written once"; exit 2; }
date '+%F %T %Z' > started.txt; $PY $SS $HOME > store-before.json
$PY -m aisef run --project calc/approved.json --settings settings-t1.json --repo calc/repo --out run --anchor-out run.anchor > run.stdout 2> run.stderr
echo "exit $?" > exit.txt; date '+%F %T %Z' > finished.txt; $PY $SS $HOME > store-after.json
tail -40 run.stdout | cut -c1-240; tail -5 run.stderr; cat exit.txt
