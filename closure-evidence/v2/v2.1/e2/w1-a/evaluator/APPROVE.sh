#!/bin/sh
# W1-a hidden evaluator — the OWNER's approvals. Not applied by the lane: the owner runs this after reading each
# contract of evaluator/bundle.json (authoring: evaluator/authoring.json; the argument table: ../README.md §4).
# Each command reads the file the one before wrote and adds one approval; the last line lints the result (READY).
#   NAME=<your name>  sh APPROVE.sh          from the AISEF repository root, with PYTHONPATH set to it
set -eu
: "${NAME:?set NAME to your name: the approver is recorded as human:$NAME}"
D=$(cd "$(dirname "$0")" && pwd)
PY=${PY:-/opt/homebrew/bin/python3}
A="$PY -P -B -m aisef bundle approve"
IN=$D/bundle.json
n=0
for c in HC-01 HC-02 HC-03 HC-04 HC-05 HC-06 HC-07 HC-08 HC-09 HC-10 HC-11 HC-12; do
    n=$((n + 1))
    OUT=$D/bundle.approved-$n.json
    $A "$IN" --contract "$c" --approver "human:$NAME" --out "$OUT"
    IN=$OUT
done
cp "$IN" "$D/approved.json"
$PY -P -B -m aisef bundle lint "$D/approved.json"
echo "approved evaluator: $D/approved.json (sha256: $(shasum -a 256 "$D/approved.json" | cut -c1-64))"
