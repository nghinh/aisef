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
pkill -f "$HERE/fakeprov.py port provider.log"
