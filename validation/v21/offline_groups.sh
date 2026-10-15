#!/bin/zsh
# V2.1 fix window, lane linux-recorder (owner decision 2026-10-15, item 6: "run the mockup tests if they belong to the
# suite, can be done offline and do not touch a real service; otherwise say why they are skipped, per group").
# The suite skips a group of tests when its tools are not on the machine. Two of those groups can run here, offline:
#
#   mockup      tests/test_mockup.py, tests/test_mockup_map.py, tests/test_cli.py::TestMockupCommand: 40 tests that
#               skip on `aisef.harness.browser.availability()` (node on PATH + a node_modules holding playwright);
#               they render pages with Chromium from the repository's own fixtures and a loopback app server.
#   references  tests/test_catalog.py, test_install.py, test_security_filter.py, test_detect_stack.py,
#               test_experience.py: the tests that skip unless the pinned clones of references/PINS.md are under
#               references/ (they read the clones; nothing is fetched).
#
# The third group the suite skips, AISEF_TEST_DOCKER=1 (tests.test_sandbox.TestIsolation + tests.test_tools.
# TestRunToolQuaDockerThat, 10 tests), needs a Docker daemon and runs containers: this script does NOT run it.
#
#   zsh validation/v21/offline_groups.sh [COMMIT]          COMMIT: default HEAD of the repository holding this script
#
# Nothing is written inside the repository, and nothing is copied into a tree of it: COMMIT is exported with `git archive`
# (without closure-evidence/, 1.4 GB, which no test of these groups reads) into OUT/tree, and the tools are LINKED into
# that export: OUT/tree/spike/s7/node_modules -> the playwright node_modules, OUT/tree/references/<name> -> a clone whose
# HEAD is the commit PINS.md records (a clone at another commit is not linked, and the report says so).
#
# What it needs, named explicitly (a default is the main checkout's, printed):
#   AISEF_PW_NODE_MODULES  a node_modules directory holding playwright/    [<main checkout>/spike/s7/node_modules]
#   AISEF_PW_BROWSERS      Playwright's browser cache (PLAYWRIGHT_BROWSERS_PATH)   [~/Library/Caches/ms-playwright]
#   AISEF_REFERENCES       a directory holding the pinned clones, one per repo of PINS.md   [<main checkout>/references]
#   OFFLINE_PYTHON         the interpreter   [/opt/homebrew/bin/python3, else python3 on PATH]
#   OFFLINE_OUT            output directory; must not exist   [$TMPDIR/aisef-offline-groups-<pid>]
#   OFFLINE_NETWORK        deny (default; macOS sandbox-exec: outbound network refused, loopback and unix sockets
#                          allowed, so Chromium reaching the loopback app server works and nothing reaches the
#                          internet) | none (not enforced; the report says so)
#   OFFLINE_KEEP           1 keeps OUT/tree
#
# Each group is run twice, as the suite would run it: WITHOUT the tools (what the suite does here: the skips counted
# and their reasons) and WITH them. The environment is `env -i`: HOME, XDG_*, TMPDIR fresh under OUT, PATH without any
# directory holding `opencode`, no AISEF_* variable, no proxy; only PLAYWRIGHT_BROWSERS_PATH when the browsers are named.
# Output: OUT/<group>-without.txt, OUT/<group>-with.txt (the unittest -v log), OUT/result.txt (what this prints).
# Exit: 0 every group that ran passed; 1 a test failed or errored; 2 refused (no commit, no python, OUT exists).
set -u
HERE=${0:A:h}
REPO=$(git -C $HERE rev-parse --show-toplevel) || { print "not inside a git repository"; exit 2 }
COMMIT=${1:-HEAD}
SHA=$(git -C $REPO rev-parse --verify -q "$COMMIT^{commit}") || { print "no such commit: $COMMIT"; exit 2 }
COMMON=$(git -C $REPO rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
MAIN=$REPO; [[ ${COMMON:t} == .git ]] && MAIN=${COMMON:h}

PW=${AISEF_PW_NODE_MODULES:-$MAIN/spike/s7/node_modules}
BROWSERS=${AISEF_PW_BROWSERS:-$HOME/Library/Caches/ms-playwright}
REFS=${AISEF_REFERENCES:-$MAIN/references}
PY=${OFFLINE_PYTHON:-/opt/homebrew/bin/python3}
[[ -x $PY ]] || PY=$(command -v python3) || { print "no python3"; exit 2 }
OUT=${OFFLINE_OUT:-${TMPDIR:-/private/tmp}/aisef-offline-groups-$$}
NETWORK=${OFFLINE_NETWORK:-deny}
[[ -e $OUT ]] && { print "OUT_DIR exists: $OUT"; exit 2 }
[[ $NETWORK == deny || $NETWORK == none ]] || { print "OFFLINE_NETWORK must be deny or none"; exit 2 }
[[ $NETWORK == deny && ! -x /usr/bin/sandbox-exec ]] && { print "sandbox-exec is absent: OFFLINE_NETWORK=none to run without enforcement"; exit 2 }
mkdir -p $OUT/home $OUT/xdg/{config,data,state,cache} $OUT/tmp $OUT/tree || exit 2
TREE=$OUT/tree
{
print "== offline groups of the suite, commit ${SHA[1,12]} of $REPO"
print "   $(date '+%Y-%m-%dT%H:%M:%S%z'); $(uname -srm); python $($PY -c 'import sys; print(sys.version.split()[0])')"
print "   network: $([[ $NETWORK == deny ]] && print 'outbound refused (sandbox-exec; loopback and unix sockets allowed)' || print 'NOT enforced')"

# ---- what is on this machine ------------------------------------------------------------------------------------
MOCKUP_WHY=()
NODE=$(command -v node) || NODE=
if [[ -z $NODE ]]; then MOCKUP_WHY+=("node is not on PATH"); fi
PWV=
if [[ -f $PW/playwright/package.json ]]; then
  PWV=$($PY -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' $PW/playwright/package.json)
else
  MOCKUP_WHY+=("no playwright/ under AISEF_PW_NODE_MODULES=$PW")
fi
CHROMIUM=(${(f)"$(ls -d $BROWSERS/chromium* 2>/dev/null)"})
(( $#CHROMIUM )) || MOCKUP_WHY+=("no chromium under AISEF_PW_BROWSERS=$BROWSERS")
BNAMES=(); for d in $CHROMIUM; do BNAMES+=(${d:t}); done
print "== mockup tools: node ${NODE:-MISSING} ${NODE:+$($NODE --version)}; playwright ${PWV:-MISSING} at $PW"
print "   browsers: ${${(j:, :)BNAMES}:-MISSING} at $BROWSERS"

PINNED=()    # name -> linked
SKIPPED_REFS=()
print "== references: clones under $REFS against the commits of references/PINS.md at ${SHA[1,12]}"
git -C $REPO show ${SHA}:references/PINS.md > $OUT/PINS.md 2>/dev/null || { print "no references/PINS.md at $SHA"; exit 2 }
while IFS='|' read -r _ name _ commit _; do
  name=${name# }; name=${name%% *}; commit=${commit//[ \`]/}
  [[ $commit =~ '^[0-9a-f]{40}$' ]] || continue
  if [[ ! -d $REFS/$name/.git && ! -f $REFS/$name/.git ]]; then SKIPPED_REFS+=("$name: not cloned"); print "   $name: not cloned"; continue; fi
  head=$(git -C $REFS/$name rev-parse HEAD 2>/dev/null)
  if [[ $head == $commit ]]; then PINNED+=($name); print "   $name: ${commit[1,12]} ok"
  else SKIPPED_REFS+=("$name: HEAD ${head[1,12]} is not the pinned ${commit[1,12]}"); print "   $name: HEAD ${head[1,12]} is NOT the pinned ${commit[1,12]} (not linked)"; fi
done < <(grep -E '^\| [A-Za-z0-9._-]+ .*\| `[0-9a-f]{40}` \|' $OUT/PINS.md)

# ---- the tree and the clean environment --------------------------------------------------------------------------
git -C $REPO archive --format=tar $SHA -- . ':(exclude)closure-evidence' | tar -x -C $TREE || { print "export failed"; exit 2 }
print "== tree: git archive $SHA (no closure-evidence): $(find $TREE -type f | wc -l | tr -d ' ') files, $(du -sh $TREE | cut -f1)"
GP=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
[[ $NETWORK == deny ]] && cat > $OUT/deny-net.sb <<'SB'
(version 1)
(allow default)
(deny network-outbound)
(allow network-outbound (remote ip "localhost:*"))
(allow network-outbound (remote unix-socket))
SB
NETCMD=(); [[ $NETWORK == deny ]] && NETCMD=(/usr/bin/sandbox-exec -f $OUT/deny-net.sb)

# run_group LABEL TOOLS(0|1) MODULE...: unittest -v in the export; the log is OUT/LABEL.txt
run_group() {
  local label=$1 tools=$2; shift 2
  local extra=(); (( tools )) && [[ -d $BROWSERS ]] && extra=(PLAYWRIGHT_BROWSERS_PATH=$BROWSERS)
  (cd $TREE && $NETCMD env -i PATH=$GP HOME=$OUT/home XDG_CONFIG_HOME=$OUT/xdg/config XDG_DATA_HOME=$OUT/xdg/data \
      XDG_STATE_HOME=$OUT/xdg/state XDG_CACHE_HOME=$OUT/xdg/cache TMPDIR=$OUT/tmp LANG=en_US.UTF-8 USER=${USER:-op} \
      LOGNAME=${LOGNAME:-op} PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$TREE/tests $extra \
      $PY -B -m unittest -v "$@") > $OUT/$label.txt 2>&1
  return $?
}
# the counts of one log: ran, skipped, failures, errors, the skip reasons
counts() {
  local f=$1 ran st sk fl er
  ran=$(sed -n 's/^Ran \([0-9]*\) test.*/\1/p' $f | tail -1)
  st=$(grep -E '^(OK|FAILED)' $f | tail -1)
  sk=$(print -r -- $st | sed -n 's/.*skipped=\([0-9]*\).*/\1/p')
  fl=$(print -r -- $st | sed -n 's/.*failures=\([0-9]*\).*/\1/p')
  er=$(print -r -- $st | sed -n 's/.*errors=\([0-9]*\).*/\1/p')
  print -r -- "ran ${ran:-?}, skipped ${sk:-0}, failures ${fl:-0}, errors ${er:-0}  [${st:-NO STATUS LINE}]"
}
reasons() { sed -n "s/.* skipped '\(.*\)'\$/\1/p" $1 | sort | uniq -c | sort -rn | sed 's/^ */      /' | cut -c1-170; }

MOCKUP=(test_mockup test_mockup_map test_cli.TestMockupCommand)
REFERENCES=(test_catalog test_install test_security_filter test_detect_stack test_experience)
RC=0
for g in mockup references; do
  mods=(); [[ $g == mockup ]] && mods=($MOCKUP) || mods=($REFERENCES)
  print "== group $g: ${mods[*]}"
  run_group $g-without 0 $mods
  print "   without the tools (what the suite does on a machine that has none): $(counts $OUT/$g-without.txt)"
  reasons $OUT/$g-without.txt
done

# ---- link the tools into the export, then the same groups again --------------------------------------------------
LINKED=()
if [[ -z $MOCKUP_WHY ]]; then
  mkdir -p $TREE/spike/s7 && ln -s $PW $TREE/spike/s7/node_modules && LINKED+=("spike/s7/node_modules -> $PW")
fi
mkdir -p $TREE/references
for n in $PINNED; do ln -s $REFS/$n $TREE/references/$n && LINKED+=("references/$n"); done
print "== linked into the export: ${#LINKED} (${(j:; :)LINKED})"
[[ -n $MOCKUP_WHY ]] && print "   mockup group NOT run with its tools: ${(j:; :)MOCKUP_WHY}"
for g in mockup references; do
  mods=(); [[ $g == mockup ]] && mods=($MOCKUP) || mods=($REFERENCES)
  if [[ $g == mockup && -n $MOCKUP_WHY ]]; then print "== group $g with the tools: not run"; continue; fi
  print "== group $g with the tools: ${mods[*]}"
  run_group $g-with 1 $mods; code=$?
  print "   $(counts $OUT/$g-with.txt); exit $code"
  reasons $OUT/$g-with.txt
  grep -E '^(FAIL|ERROR):' $OUT/$g-with.txt | sed 's/^/   /' | head -20
  (( code )) && RC=1
done
(( $#SKIPPED_REFS )) && print "== pinned clones not linked: ${(j:; :)SKIPPED_REFS}"

print "== not run: the Docker-gated group (AISEF_TEST_DOCKER=1 tests.test_sandbox tests.test_tools: 10 tests; image alpine:latest, --network=none)"
[[ ${OFFLINE_KEEP:-0} == 1 ]] || { [[ -n $TREE && $TREE == $OUT/tree ]] && rm -rf $TREE; }
print "== result in $OUT/result.txt; exit $RC"
exit $RC
} 2>&1 | tee $OUT/result.txt
exit ${pipestatus[1]}
