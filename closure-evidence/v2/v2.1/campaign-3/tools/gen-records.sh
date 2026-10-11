#!/bin/zsh
# gen-records.sh SHA OUT [STEPS]: the 2.1 derived records, in dependency order, at a detached checkout of SHA (a committed tree:
# the generators refuse an uncommitted aisef2/, tests/v2/ or validation/), under the workers' environment. Each record is
# written once into OUT/rc/closure-evidence/v2/v2.1/; a step's exit code and output are kept; the sequence stops at the
# first failure. Results are copied to the repository by the lead.
W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21
SHA=$1; OUT=$2; STEPS=${3:-"1 2 3 8 4 5 6 7"}   # 4-7 need the Q0 calibration record, so MUTATION.json: after the campaign
[[ -n $SHA && -n $OUT && ! -e $OUT ]] || { echo "usage: gen-records.sh SHA OUT (OUT absent)"; exit 2; }
mkdir -p $OUT/home $OUT/xdg/{config,data,state,cache} $OUT/tmp
GP=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
git -C $W worktree add -q --detach $OUT/rc $SHA || exit 1
cd $OUT/rc || exit 9
P() { env -i PATH=$GP HOME=$OUT/home XDG_CONFIG_HOME=$OUT/xdg/config XDG_DATA_HOME=$OUT/xdg/data XDG_STATE_HOME=$OUT/xdg/state \
      XDG_CACHE_HOME=$OUT/xdg/cache TMPDIR=$OUT/tmp LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME /opt/homebrew/bin/python3 -P "$@"; }
step() { local n=$1; shift; echo "=== $n $(date '+%F %T'): $*" >> $OUT/steps.log; local t0=$SECONDS
  P "$@" > $OUT/$n.out 2>&1; local rc=$?; echo "    rc $rc in $((SECONDS - t0)) s" >> $OUT/steps.log; return $rc; }
echo "HEAD $(git rev-parse HEAD) dirty: [$(git status --porcelain | tr '\n' ' ')]" > $OUT/steps.log
rc=0
for n in ${=STEPS}; do
  case $n in
    1) step 1-proposal validation/qualification/p5_acceptance.py --write-v21-proposal ;;
    2) step 2-falsifiability validation/qualification/p5_falsifiability.py --run-v21 ;;
    3) step 3-plan-correction validation/qualification/c2_plan_correction.py --write ;;
    4) step 4-reverification validation/qualification/p5_acceptance.py --write-v21 ;;
    5) step 5-k-nowork validation/qualification/c2_k_nowork_001.py --write ;;
    6) step 6-q5 validation/qualification/v21_q5_compare.py --write ;;
    7) step 7-ruling validation/qualification/v21_conformance_ruling.py --write ;;
    8) step 8-p2-evidence validation/v2/p2_evidence.py ;;
    *) echo "unknown step $n" >> $OUT/steps.log; false ;;
  esac
  rc=$?; [[ $rc -eq 0 ]] || break
done
echo "stopped/finished $(date '+%F %T') rc=$rc" >> $OUT/steps.log
git status --porcelain >> $OUT/steps.log
echo done > $OUT/gen.done
