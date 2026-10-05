#!/bin/zsh
# Phase 4: clean install of aisef==2.0.0 from PyPI into /tmp/aisef-2.0.0-final-verify (owner-named path); every command's
# output and exit status is kept under $SP/final/phase4/. CLI checks run under env -i, outside any repository.
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
V=/tmp/aisef-2.0.0-final-verify; O=$SP/final/phase4
[[ ! -e $V && ! -e $O ]] || { echo "exists"; exit 2; }
mkdir -p $O
date -u +%FT%TZ > $O/started
/opt/homebrew/bin/python3 -m venv $V > $O/venv.txt 2>&1; echo "exit $?" >> $O/venv.txt
source $V/bin/activate
mkdir -p $V/work $V/home && cd $V/work
python -m pip install --upgrade pip > $O/pip-upgrade.txt 2>&1; echo "exit $?" >> $O/pip-upgrade.txt
pip install --no-cache-dir aisef==2.0.0 > $O/pip-install.txt 2>&1; echo "exit $?" >> $O/pip-install.txt
pip list --format=freeze > $O/pip-list.txt 2>&1
GUARD_PATH=$V/bin:$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
H=(env -i PATH=$GUARD_PATH HOME=$V/home LANG=en_US.UTF-8)
for c in "aisef --version" "aisef doctor" "aisef run --help" "aisef legacy --help" "aisef --help"; do
  f=$O/${${c// /_}//-/}.txt
  print -r -- "\$ $c  (cwd $PWD)" > $f; $H ${=c} >> $f 2>&1; echo "exit $?" >> $f
done
$H python -I - > $O/package.json 2>&1 <<'PY'
import importlib.metadata as md, importlib.util as u, json, sys, aisef, aisef2
d = md.distribution("aisef")
files = [str(f) for f in d.files]
tops = sorted({f.split("/")[0] for f in files})
print(json.dumps({
  "version": d.version, "aisef_file": aisef.__file__, "aisef2_file": aisef2.__file__,
  "repo_local_import": any("/Downloads/projects/" in p for p in (aisef.__file__, aisef2.__file__)),
  "top_level_entries": tops,
  "tests_importable": u.find_spec("tests") is not None, "validation_importable": u.find_spec("validation") is not None,
  "shipped_tests_or_validation": [f for f in files if f.startswith(("tests/", "validation/"))],
  "package_data_non_py": sorted(f for f in files if f.startswith(("aisef/", "aisef2/")) and not f.endswith((".py", ".pyc"))),
  "file_count": len(files), "sys_path0": sys.path[:3]}, indent=1))
PY
date -u +%FT%TZ > $O/finished
