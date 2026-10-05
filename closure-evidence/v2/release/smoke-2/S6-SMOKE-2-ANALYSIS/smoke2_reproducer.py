"""S6-SMOKE-2: the S-10-a refutation reproduced offline with the RC2 kernel's own grep (aisef2.probe.file_artifact.grep_facts)
on the preserved candidates. usage (cwd = the release worktree): python3 -P smoke2_reproducer.py SIDE_DIR"""
import json, pathlib, re, subprocess, sys
sys.path.insert(0, ".")
from aisef2.app import bundle
from aisef2.probe.file_artifact import grep_facts
from validation.qualification import release_bundle as rb

repo = pathlib.Path(sys.argv[1]) / "run" / "repo"
spec = bundle.read(pathlib.Path(rb.BUNDLE_REL)).specs["PPS-54a03b9063ac639586b0931ede2a2e1ba2b67cdfed5d653a8fe0c98755c299f9"]
stim = spec.probe_input["stimulus"] if hasattr(spec, "probe_input") else spec["probe_input"]["stimulus"]
pat = re.compile(stim["grep"])


def files(rev):
    names = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", rev, "ledgerlock"], capture_output=True, text=True, check=True).stdout.split()
    return [(n, subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{n}"], capture_output=True, check=True).stdout) for n in names if n.endswith(".py")]


out = {"pattern": stim["grep"]}
for name, rev in (("parent 8398d43 (STORY-01-05 merged)", "8398d43db576151efc96874ff4e55a734caae6ef"),
                  ("STORY-02-01 candidate 8f140e1", "8f140e13abff7234856c9c4c900ba99ec17654e3"),
                  ("merged d90a7f6", "d90a7f6f23e8520b45e625ad82351a4200c09f8c")):
    fs = files(rev)
    facts = grep_facts(pat, fs)
    lines = {f"{r}:{n}": dict(fs)[r].decode().splitlines()[n - 1] for r, n in facts.get("locations", [])}
    imports = sorted({ln.strip() for _, data in fs for ln in data.decode().splitlines() if re.match(r"^(import|from)\s", ln)})
    out[name] = {"matches": facts["matches"], "matching_lines": lines, "top_level_import_statements": imports}
# the same merged file with only the docstring line's first word changed
fs = dict(files("d90a7f6f23e8520b45e625ad82351a4200c09f8c"))
fixed = fs["ledgerlock/ledger.py"].replace(b"    from disk without trusting", b"    reading disk without trusting")
out["merged d90a7f6 with the docstring line reworded"] = {"matches": grep_facts(pat, [(k, fixed if k == "ledgerlock/ledger.py" else v) for k, v in fs.items()])["matches"]}
print(json.dumps(out, indent=1))
