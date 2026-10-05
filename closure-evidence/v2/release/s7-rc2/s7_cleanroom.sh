#!/bin/zsh
# S7 (charter §18) clean-room check of the frozen RC2 wheel: a fresh directory outside any repository, env -i (fresh HOME and
# XDG_*, PATH without the real client), a fresh venv, exactly the frozen wheel installed with --no-index --no-deps, every
# command run from outside the checkout with -I. The smoke scripts are RC2's own (git archive of 1565bcc tests/).
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/c2-corrective
O=$SP/s7; [[ ! -e $O ]] || { echo "$O exists"; exit 2; }
mkdir -p $O/home $O/xdg/config $O/xdg/data $O/xdg/state $O/xdg/cache $O/dist $O/rc-tests $O/run
cp $SP/rc2-dist/aisef-2.0.0-py3-none-any.whl $O/dist/
git -C $W archive 1565bccff66cda866820d5307a26de462e79e9a0 tests | tar -x -C $O/rc-tests
GUARD_PATH=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
HENV=(env -i PATH=$GUARD_PATH HOME=$O/home XDG_CONFIG_HOME=$O/xdg/config XDG_DATA_HOME=$O/xdg/data XDG_STATE_HOME=$O/xdg/state
      XDG_CACHE_HOME=$O/xdg/cache TMPDIR=/var/folders/y9/frkyw6m14_q020cmyzsh16jm0000gn/T/ LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME
      PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1)
print -r -- "HENV=(${(q)HENV[@]})" > $O/env.sh
cd $O/run || exit 2
step() { print -r -- "== $1"; shift; "$@"; print -r -- "rc=$?"; }
{
  for d in $O ${O:h} ${O:h:h} ${O:h:h:h} /private/tmp /private /; do [[ -e $d/.git ]] && print -r -- "INSIDE A REPOSITORY: $d"; done
  step "frozen wheel digest" shasum -a 256 $O/dist/aisef-2.0.0-py3-none-any.whl
  step "venv" $HENV /opt/homebrew/bin/python3 -m venv $O/venv
  step "install exactly the frozen wheel, offline" $HENV $O/venv/bin/python -m pip install --no-index --no-deps $O/dist/aisef-2.0.0-py3-none-any.whl
  step "pip check" $HENV $O/venv/bin/python -m pip check
  step "aisef --version" $HENV $O/venv/bin/aisef --version
  step "aisef --help (the CLI starts)" $HENV $O/venv/bin/aisef --help
  step "aisef run --help (V2 runtime)" $HENV $O/venv/bin/aisef run --help
  step "aisef legacy --help (V1 only behind the named legacy surface)" $HENV $O/venv/bin/aisef legacy --help
  step "no qualification harness in the install" $HENV $O/venv/bin/python -I -c "import importlib.util as u; print({m: u.find_spec(m) is not None for m in ('validation', 'tests', 'aisef', 'aisef2')})"
  step "installed smoke (RC2's tests/installed_smoke.py, -I)" $HENV $O/venv/bin/python -I $O/rc-tests/tests/installed_smoke.py 2.0.0 --product
  step "installed product smoke: aisef run --check / run / --verify, offline (RC2's tests/installed_product_smoke.py, -I)" $HENV $O/venv/bin/python -I $O/rc-tests/tests/installed_product_smoke.py
} > $O/s7.txt 2>&1
(cd $W && python3 -P validation/v2/packaging_check.py --artifacts $SP/rc2-dist) > $O/packaging_check.txt 2>&1; print -r -- "rc=$?" >> $O/packaging_check.txt
echo done > $O/done
