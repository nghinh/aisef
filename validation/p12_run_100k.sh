#!/bin/zsh
# Phase 12 on ONE exact kernel: 100 000 model-vs-real-kernel traces in ten 10 000-trace chunks, then the
# consolidation the W0 builder reads. The kernel must be clean and unchanged for the whole run — every chunk
# records the tree it imported, and p12_integrity refuses a dataset that mixes kernels.
#
#   validation/p12_run_100k.sh [<workers>] [<chunks>]        # default 8 workers, 10 chunks of 10 000
set -u
A=/Users/nghinh/Downloads/projects/ai-sdlc; cd $A
W=${1:-8}; N=${2:-10}
OUT=$A/closure-evidence/hardening
[ -z "$(git status --porcelain aisef)" ] || { echo "REFUSED: aisef/ is dirty — the dataset would not name one kernel"; exit 1; }
TREE=$(git rev-parse HEAD:aisef)
echo "[$(date '+%F %T')] Phase 12: $N x 10000 traces, $W workers, kernel tree $TREE"
for i in $(seq 0 $((N - 1))); do
  START=$((i * 10000))
  F=$(printf "%s/differential-p12-%05d.json" $OUT $START)
  if [ -f "$F" ] && python3 -P -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('traces')==10000 and d['kernel']['aisef_tree']==sys.argv[2] else 1)" "$F" "$TREE"; then
    echo "[$(date '+%F %T')] chunk $START already complete on this kernel — skipped"
    continue
  fi
  echo "[$(date '+%F %T')] chunk $START ..."
  .venv/bin/python -m tests.hardening.differential --traces 10000 --start $START --workers $W --out $F \
    > $OUT/phase12/diff-p12-$START.log 2>&1 || { echo "CHUNK $START FAILED — see phase12/diff-p12-$START.log"; exit 2; }
  python3 -P -c "import json,sys; d=json.load(open(sys.argv[1])); print('   ', {k: d[k] for k in ('traces','matched','unexplained_count','invariant_violations','exceptions','elapsed_s')})" "$F"
  NOW=$(git rev-parse HEAD:aisef)
  [ "$NOW" = "$TREE" ] || { echo "REFUSED: aisef/ changed mid-run ($TREE -> $NOW)"; exit 3; }
done
echo "[$(date '+%F %T')] consolidating"
.venv/bin/python -P validation/p12_identity.py --out $OUT/phase12/PHASE12-KERNEL-IDENTITY.json || exit 4
.venv/bin/python -P validation/p12_kernel_split.py --logs $OUT/phase12 || true
.venv/bin/python -P validation/p12_integrity.py || exit 5
python3 -P -c "
import json; d=json.load(open('$OUT/differential-p12-summary.json'))
print(json.dumps({k: d.get(k) for k in ('traces','unexplained','invariant_violations','known_deviations','manifest')})[:600])"
echo "[$(date '+%F %T')] Phase 12 complete"
