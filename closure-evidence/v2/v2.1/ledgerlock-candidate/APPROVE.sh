#!/bin/zsh
# LedgerLock 2.1 candidate — the owner's re-approval of the 6 contracts the migration withheld (owner decision
# 2026-10-15 item 1: a contract a declared capability change evaluates differently loses its 2.0.0 approval).
# This reproduces the candidate from the SEALED 2.0.0 bundle (migrate is deterministic — no loose candidate is trusted),
# then approves each withheld contract as YOU, and lints the result. Nothing is signed or sealed; the output is a
# loadable 2.1 candidate bundle for review, not a release.
#
#   zsh closure-evidence/v2/v2.1/ledgerlock-candidate/APPROVE.sh human:<your-name> [OUT_DIR]
#
# OUT_DIR (default: a new temp dir, printed) receives CANDIDATE.json (migrated, withheld) and APPROVED.json (loadable).
set -eu
APPROVER=${1:?usage: APPROVE.sh human:<name> [OUT_DIR]}
case $APPROVER in human:?*) ;; *) print "approver must be human:<name>, got $APPROVER" >&2; exit 2;; esac
HERE=${0:A:h}; REPO=${HERE:h:h:h:h}   # ledgerlock-candidate -> v2.1 -> v2 -> closure-evidence -> <repo root>
OUT=${2:-$(mktemp -d)}; mkdir -p $OUT
PY=${PYTHON:-python3}
SRC=$REPO/closure-evidence/v2/release/LEDGERLOCK-PROJECT.json
CAND=$OUT/CANDIDATE.json; APPR=$OUT/APPROVED.json
WITHHELD=(BC-V22-S-10-a BC-V22-S-10-b BC-V22-S-10-c BC-V22-S-12-a BC-V22-S-12-b BC-V22-S-12-c)

export PYTHONPATH=$REPO
print "LedgerLock 2.1 candidate — approver $APPROVER, out $OUT"
print "1) migrate the sealed 2.0.0 bundle -> candidate (approvals of R-10/R-12 grep_count contracts withheld)"
$PY -P -c "import sys; sys.argv=['aisef','bundle','migrate','--out','$CAND','$SRC']; import aisef.cli as c; c.main()" >/dev/null
cur=$CAND
print "2) approve the $#WITHHELD withheld contracts as $APPROVER (chained, each reads the one before)"
for ctr in $WITHHELD; do
  nxt=$OUT/.step.json
  $PY -P -c "import sys; sys.argv=['aisef','bundle','approve','--contract','$ctr','--approver','$APPROVER','--out','$nxt','$cur']; import aisef.cli as c; c.main()" >/dev/null
  mv $nxt $cur
  print "   approved $ctr"
done
mv $cur $APPR
print "3) lint the approved candidate"
$PY -P -c "import sys; sys.argv=['aisef','bundle','lint','$APPR']; import aisef.cli as c; c.main()"
print "done: $APPR (loadable 2.1 LedgerLock candidate; NOT signed, NOT a release)"
