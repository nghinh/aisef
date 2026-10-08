#!/bin/zsh
# CLI integration of AISEF 2.1 (offline; no paid provider): the real `aisef` CLI from this tree, the REAL Open Code Review
# binary, a real HTTP preflight to a loopback OpenAI-compatible provider (fakeprov.py, which also plays OCR's model), a
# fake developer client (fake_opencode.py) on a PATH from which every directory holding a real `opencode` is removed.
#   zsh validation/v21/cli_integration/run.sh OUT_DIR /abs/path/to/ocr      (OUT_DIR must not exist)
set -u
HERE=${0:A:h}; W=${HERE:h:h:h}; I=${1:?OUT_DIR}; OCR=${2:?OCR binary}; PY=${PYTHON:-python3}
[[ ! -e $I ]] || { print "OUT_DIR exists"; exit 2; }
mkdir -p $I/fakebin $I/anchors $I/home
print -r -- "#!$(command -v $PY)" > $I/fakebin/opencode; cat $HERE/fake_opencode.py >> $I/fakebin/opencode; chmod +x $I/fakebin/opencode
GUARD=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
export PATH=$I/fakebin:$GUARD HOME=$I/home XDG_CONFIG_HOME=$I/xdg FAKE_PROVIDER_KEY=sk-integration-not-a-key PYTHONPATH=$W
print "commit: $(git -C $W rev-parse HEAD) dirty: $(git -C $W status --porcelain | wc -l | tr -d ' ')"
print "opencode on PATH: $(command -v opencode)"; print "ocr: $($OCR version | head -1) sha256 $(shasum -a 256 $OCR | cut -c1-64)"
A() { (cd $I && $PY -m aisef "$@"); print "exit $?"; }
(cd $I && $PY -I $HERE/fakeprov.py port provider.log &); while [[ ! -s $I/port ]]; do sleep 0.1; done
$PY $HERE/make_inputs.py $I $OCR
mkdir -p $I/repo/app $I/repo/docs && cd $I/repo && git init -q -b main && : > app/__init__.py
printf '# Calc CLI\n\n## 1. Command line\n\n1.1 python -m app A B exits with the sum of the integers A and B.\n\n1.2 Exit 2 on a usage error (any other number of arguments).\n' > docs/requirements.md
git add -A && git -c user.name=o -c user.email=o@o commit -qm baseline && cd $I
print "== seal"; A bundle seal authoring.json --repo repo --out sealed.json
print "== approve x3"; A bundle approve sealed.json --contract BC-SUM --approver human:integration --out a1.json
A bundle approve a1.json --contract BC-USAGE-0 --approver human:integration --out a2.json
A bundle approve a2.json --contract BC-USAGE-1 --approver human:integration --out approved.json
print "== lint"; A bundle lint approved.json
print "== check"; A run --check --project approved.json --settings settings.json --repo repo
print "== run"; A run --project approved.json --settings settings.json --repo repo --out run1 --anchor-out anchors/run1.anchor
print "== verify"; A run --verify --project approved.json --out run1 --expect-anchor "$(head -c 64 anchors/run1.anchor)"
# continuation: a run SIGKILLed once the S2 developer's usage is reported (its result never journaled) — then
# `aisef bundle continue`, a refused --parent (unknown spend), an accepted one, and a second continue of the same run
mkdir -p $I/repo2/app $I/repo2/docs && cd $I/repo2 && git init -q -b main && : > app/__init__.py
printf '# Calc CLI\n\n## 1. Command line\n\n1.1 python -m app A B exits with the sum of the integers A and B.\n\n1.2 Exit 2 on a usage error (any other number of arguments).\n\n1.3 Exit 3 when A or B is not an integer.\n' > docs/requirements.md
git add -A && git -c user.name=o -c user.email=o@o commit -qm baseline && cd $I
print "== seal + approve x4 (two stories)"; A bundle seal authoring2.json --repo repo2 --out sealed2.json
A bundle approve sealed2.json --contract BC-SUM --approver human:integration --out b1.json
A bundle approve b1.json --contract BC-USAGE-0 --approver human:integration --out b2.json
A bundle approve b2.json --contract BC-USAGE-1 --approver human:integration --out b3.json
A bundle approve b3.json --contract BC-NAN --approver human:integration --out approved2.json
print "== run2 (SIGKILLed in S2)"
(cd $I && exec $PY -m aisef run --project approved2.json --settings settings.json --repo repo2 --out run2 \
   --anchor-out anchors/run2.anchor) & RUN2=$!
# INV-MUTATION-AUTHORITY: the kill's target is this shell's own job ($!, started just above, not yet waited for);
# the fake developer only says when (kill-run2.ready, written once its S2 usage is reported, then it waits)
until [[ -e $I/kill-run2.ready ]] || ! kill -0 $RUN2 2>/dev/null; do sleep 0.05; done
[[ -e $I/kill-run2.ready ]] && kill -KILL $RUN2 && print "SIGKILL after the usage of 'developer S2' was reported" > $I/kill-run2.done
wait $RUN2; print "exit $? (137 = SIGKILL)"
print "run2: RUN.json $([[ -e $I/run2/RUN.json ]] && print present || print absent); RUN.started.json $([[ -e $I/run2/RUN.started.json ]] && print present || print absent); kill: $(cat $I/kill-run2.done)"
print "== continue"; A bundle continue approved2.json --from-run run2 --out cont.json
print "== run3 --parent, unknown spend not accepted"
A run --project cont.json --settings settings.json --repo run2/repo --parent run2 --out run3-refused
print "== run3 --parent --accept-unaccounted"
A run --project cont.json --settings settings.json --repo run2/repo --parent run2 --accept-unaccounted --out run3 \
  --anchor-out anchors/run3.anchor
print "== continue run2 again"; A bundle continue approved2.json --from-run run2 --out cont-again.json
print "== verify run3"; A run --verify --project cont.json --out run3 --expect-anchor "$(head -c 64 anchors/run3.anchor)"
print "== run3 record"; $PY -c 'import json,sys; r=json.load(open(sys.argv[1])); print(json.dumps({k: r.get(k) for k in ("delivery_verdict","story_outcomes","continues","lineage_usage")}, indent=1)[:3000])' $I/run3/RUN.json
print "== run1 context pack read-back (D4)"; $PY -P $HERE/readback.py $I; print "exit $?"
pkill -f "$HERE/fakeprov.py port provider.log"
