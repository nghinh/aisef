#!/bin/sh
# W1-a — the OWNER's approvals of the two sealed bundles: the arms' (arms/bundle.json, 13 contracts) and then the
# hidden evaluator (evaluator/bundle.json, 12 contracts). The lane did not run this: an approval is a human's statement
# about each contract (`aisef bundle approve`, one contract per command, approver human:<name>), made after reading
# the contract (authoring.json beside each bundle; the hidden evaluator's argument table is README.md §4).
#
#   cd <AISEF repository root>; PYTHONPATH=. sh closure-evidence/v2/v2.1/e2/w1-a/APPROVE.sh human:<your name>
#
# Each command reads the file the one before wrote and writes one more approval to a NEW file (approved-N.json beside
# the bundle; the bundle tools create files exclusively and never overwrite); the last is hard-linked as approved.json
# and linted (expected READY). Nothing is overwritten: a directory that already holds an approved*.json is refused.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
A=${1:?usage: APPROVE.sh human:<your name>}
case "$A" in human:?*) ;; *) echo "APPROVE.sh: the approver is human:<name>, got '$A'" >&2; exit 2 ;; esac
PY=${PY:-/opt/homebrew/bin/python3}

approve() {
  dir=$1; shift
  for f in "$HERE/$dir"/approved*.json; do
    [ -e "$f" ] && { echo "APPROVE.sh: $f exists; approvals are written once, never over" >&2; exit 2; }
  done
  in=$HERE/$dir/bundle.json; n=0
  for c in "$@"; do
    n=$((n + 1)); out=$HERE/$dir/approved-$n.json
    "$PY" -P -B -m aisef bundle approve "$in" --contract "$c" --approver "$A" --out "$out"
    in=$out
  done
  ln "$in" "$HERE/$dir/approved.json"
  "$PY" -P -B -m aisef bundle lint "$HERE/$dir/approved.json"
  echo "approved $dir: $HERE/$dir/approved.json (sha256: $(shasum -a 256 "$HERE/$dir/approved.json" | cut -c1-64))"
}

# arms B/C: the thirteen contracts the developer's stories are proved against (public examples of the task text)
approve arms BC-DIGEST BC-DIGEST-MISSING BC-BUILD BC-BUILD-MISSING BC-DUMPS BC-LOADS BC-ROUNDTRIP BC-COMPARE \
  BC-CLI-BUILD BC-CLI-BUILD-OUT BC-CLI-VERIFY BC-CLI-USAGE BC-STDLIB

# the hidden evaluator: twelve contracts no arm sees (read each one in evaluator/authoring.json before approving)
approve evaluator HC-01 HC-02 HC-03 HC-04 HC-05 HC-06 HC-07 HC-08 HC-09 HC-12 HC-13 HC-14
