"""The ONE preflight-only `aisef run` for mycombo (lane PF), as canary tier 1 did it, under a built environment:

* PATH holds a stub `opencode` (stubbin/) and the system tools only — the real client is never on it, so even an
  ATTESTED preflight runs only the stub's `--version` (run.py client_identity) and the budget (4 of 4) stops the run
  before any session; the stub refuses `run` anyway;
* XDG_CONFIG_HOME names a scratch client configuration (provider 9router at the attested endpoint, key by env ref):
  the operator's own OpenCode configuration and store are not read by the run; store_stat.py stats them before/after;
* the key reaches the child ONLY through its environment (never an argument; this launcher prints nothing of it);
* python -P -B under nice -n 19, PYTHONPATH = this lane's worktree.

Usage: python3 -P -B run_probe.py   (refuses to run twice: the record directory must not exist)"""
import json
import os
import pathlib
import subprocess
import sys
import time

S = pathlib.Path(__file__).resolve().parent
W = "/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/wf_830a4f0d-db8-1"
PY = "/opt/homebrew/bin/python3"
STORE_STAT = f"{W}/closure-evidence/v2/v2.1/isolation/tools/store_stat.py"
out = S / "preflight-mycombo"
out.mkdir()                     # exists -> FileExistsError: a record is written once
if not os.environ.get("NINEROUTER_API_KEY"):
    sys.exit("NINEROUTER_API_KEY is not set in this environment")
env = {"PATH": f"{S / 'stubbin'}:/opt/homebrew/bin:/usr/bin:/bin", "HOME": os.environ["HOME"],
       "NINEROUTER_API_KEY": os.environ["NINEROUTER_API_KEY"], "XDG_CONFIG_HOME": str(S / "xdg"),
       "TMPDIR": str(S / "tmp"), "PYTHONPATH": W, "PYTHONDONTWRITEBYTECODE": "1", "LANG": "en_US.UTF-8"}
(S / "tmp").mkdir(exist_ok=True)
assert not any(p.exists() for p in (pathlib.Path(d) / "opencode" for d in env["PATH"].split(":") if "stubbin" not in d)), \
    "the real client is on the run's PATH"


def stamp(name: str) -> None:
    (out / name).write_text(subprocess.run(["date", "+%F %T %z"], capture_output=True, text=True).stdout, encoding="utf-8")


def store(name: str) -> None:
    (out / name).write_text(subprocess.run([PY, "-P", "-B", STORE_STAT, env["HOME"]], capture_output=True, text=True,
                                           check=True).stdout, encoding="utf-8")


stamp("started.txt")
store("store-before.json")
argv = ["nice", "-n", "19", PY, "-P", "-B", "-m", "aisef", "run", "--project", str(S / "calc/approved.json"),
        "--settings", str(S / "probe-settings.json"), "--repo", str(S / "calc/repo"), "--out", str(out / "run"),
        "--anchor-out", str(out / "run.anchor")]
(out / "argv.json").write_text(json.dumps(argv, indent=1) + "\n", encoding="utf-8")
(out / "env-names.txt").write_text("\n".join(sorted(env)) + "\n", encoding="utf-8")
t0 = time.monotonic()
with (out / "run.stdout").open("w") as so, (out / "run.stderr").open("w") as se:
    code = subprocess.run(argv, cwd=str(S), env=env, stdout=so, stderr=se, timeout=900).returncode
(out / "exit.txt").write_text(f"exit {code}\nwall_s {time.monotonic() - t0:.1f}\n", encoding="utf-8")
stamp("finished.txt")
store("store-after.json")
print((out / "exit.txt").read_text(), end="")
print("store before == after:", (out / "store-before.json").read_bytes() == (out / "store-after.json").read_bytes())
