#!/bin/zsh
# Move the current single-kernel Phase 12 dataset into phase12/history-kernel-<tree>/ before a new kernel's run.
# Nothing is edited: the files are moved with `git mv` and a README states what they are and are not.
#
#   validation/p12_archive_dataset.sh <old kernel tree prefix> "<why this kernel changed>"
set -e
A=/Users/nghinh/Downloads/projects/ai-sdlc; cd $A
TREE=$1; WHY=$2
D=closure-evidence/hardening/phase12/history-kernel-$TREE
[ -d "$D" ] && { echo "REFUSED: $D already exists"; exit 1; }
mkdir -p $D
for f in closure-evidence/hardening/differential-p12-*[0-9].json closure-evidence/hardening/differential-p12-summary.json \
         closure-evidence/hardening/phase12/PHASE12-KERNEL-IDENTITY.json \
         closure-evidence/hardening/phase12/PHASE12-DATASET-MANIFEST.json \
         closure-evidence/hardening/phase12/integrity.json closure-evidence/hardening/phase12/COVERAGE-REPORT.md \
         closure-evidence/hardening/phase12/kernel-split.json; do
  [ -e "$f" ] && git mv "$f" $D/ 2>/dev/null || true
done
cat > $D/README.md <<EOF
# VALID HISTORICAL EVIDENCE — NOT FINAL QUALIFICATION EVIDENCE

The complete single-kernel Phase 12 dataset for product tree \`$TREE…\`.

$WHY

The product tree changed, so this dataset is **valid historical evidence** and regression history, and it is **not**
qualification evidence for the new kernel. The new dataset is run in full against the new product tree and lives at
\`closure-evidence/hardening/differential-p12-*.json\` with its own identity, integrity, manifest and coverage
records. Nothing here was edited; the files were moved with \`git mv\`.
EOF
git add $D
echo "archived to $D:"; ls $D | head -20
