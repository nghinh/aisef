#!/opt/homebrew/bin/python3 -P -B
"""E2 launch kit, step 2 — ONE invocation of the campaign driver on a directory e2_setup.py built, hermetic. run_e2.sh is
the entry point (it checks the machine first and holds the heavy lock around this); nothing here is run by hand.

    python3 -P -B e2_launch.py D MAX_RUNS            real: the client is CLIENT_EXE (env) or the first `opencode` on PATH;
                                                     the settings' api_key_env (NINEROUTER_API_KEY) is copied from this
                                                     environment into the driver's — never an argument, never printed
    E2_OFFLINE=1 python3 ... e2_launch.py D MAX_RUNS  offline: refuses any client whose bytes are not ../dry-run/tools/
                                                     fake_opencode.py, the settings must name the loopback endpoint of
                                                     ../dry-run/tools/dryrun.py, whose fake provider answers from a thread
                                                     of this process; the fake key; NINEROUTER_API_KEY is never read

Per invocation, under D/launch/<stamp>/: launch.json (mode, client realpath + sha256 + `--version` + where it came
from, the hermetic PATH and the environment's variable NAMES, max_runs), store-before/after.json (store_stat.py on the
operator's $HOME — D/home offline), exit.txt, end.json. The driver's stdout/stderr append to D/run.log; its records are
D/out (OUT); then `replay` -> D/replay.txt, `summary` -> D/summary.txt, the record copy D/records/ (INDEX.json: sha256
per file) and the secret scan of the whole of D (the key's value: in-process count, never printed; a mixed-case token of
40+ characters: listed masked, for the operator). The rsync command that would put D/records into the repository is
printed, never run: this tool writes nothing under the repository. D/out/STOP present: nothing starts (exit 3)."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent          # .../e2/tools
E2 = HERE.parent
ROOT = E2.parents[3]
V21 = E2.parent
PY = sys.executable
DRIVER = ROOT / "validation" / "experiments" / "campaign.py"
STORE_STAT = V21 / "isolation" / "tools" / "store_stat.py"
FAKE = E2 / "dry-run" / "tools" / "fake_opencode.py"
TOKEN = re.compile(rb"[A-Za-z0-9_\-]{40,}")
#: a labelled digest (PPS-<sha256>, the kernel's probe spec references) is not a key
LABELLED_HASH = re.compile(rb"[A-Za-z_]{0,8}-?[0-9a-f]{40,}")
#: OUT's records (never the arms' workspaces or the kernel's repository clones) and D's own
RECORD_GLOBS = ("*/MANIFEST.json", "*/RESULT.json", "*/arm/ARM.json", "*/arm/preflight/PREFLIGHT.json",
                "*/arm/run/preflight/PREFLIGHT.json", "*/arm/run/RUN.json", "*/arm/run/EVIDENCE.json",
                "*/arm/run/run/journals/*.jsonl", "*/arm/sessions/*.jsonl", "*/arm/run/sessions/*.jsonl",
                "*/arm/run.stdout", "*/arm/run.stderr", "*/arm/exit.txt", "campaign.log", "CAMPAIGN.json")
D_GLOBS = ("SETUP.json", "APPROVALS.md", "CAMPAIGN-real.json", "run.log", "replay.txt", "summary.txt", "approved/*.json",
           "approved/provisional/*.json", "settings/*.json", "client/config/opencode/opencode.json", "launch/*/*")


def sha_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p: pathlib.Path, doc) -> None:
    p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %z")


def refuse(msg: str, code: int = 2) -> None:
    print(f"e2_launch: refused: {msg}", file=sys.stderr)
    raise SystemExit(code)


def records(d: pathlib.Path) -> dict:
    """D/records rebuilt from D/out and D's own records; INDEX.json names every copy's sha256."""
    dest = d / "records"
    shutil.rmtree(dest, ignore_errors=True)
    copied = {}
    for base, globs in ((d / "out", RECORD_GLOBS), (d, D_GLOBS)):
        for g in globs:
            for src in sorted(base.glob(g)):
                if not src.is_file():
                    continue
                rel = src.relative_to(d)
                dst = dest / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                copied[str(rel)] = {"sha256": sha_file(dst), "bytes": dst.stat().st_size}
    return copied


def scan(d: pathlib.Path, secret: bytes) -> dict:
    """Every file under D (not .git objects): files holding the key's VALUE (counted in-process, never printed) and
    mixed-case tokens of 40+ characters (upper, lower and digit together: what a key looks like and a sha256, a
    labelled sha256, a path component or a word does not), masked."""
    hits, tokens = [], {}
    for p in sorted(d.rglob("*")):
        if not p.is_file() or ".git" in p.parts or p.name == "INDEX.json":
            continue
        data = p.read_bytes()
        if secret and secret in data:
            hits.append(str(p.relative_to(d)))
        found = {t for t in TOKEN.findall(data)
                 if re.search(rb"[A-Z]", t) and re.search(rb"[a-z]", t) and re.search(rb"[0-9]", t) and not LABELLED_HASH.fullmatch(t)}
        if found:
            tokens[str(p.relative_to(d))] = sorted(f"{t[:4].decode()}…({len(t)})" for t in found)
    return {"files_holding_key_value": hits, "mixed_case_tokens_40plus": tokens}


class Provider:
    """The loopback fake provider of the dry run (dryrun.Provider), in a thread of this process; dies with it."""

    def __init__(self, st: dict):
        sys.path.insert(0, str(E2 / "dry-run" / "tools"))
        import dryrun
        import http.server
        self.dryrun = dryrun
        if st["provider"]["endpoint"] != dryrun.ENDPOINT:
            refuse(f"offline, but the settings' endpoint is {st['provider']['endpoint']}, not {dryrun.ENDPOINT}")
        dryrun.Provider.listing = {"id": st["route"].split("/", 1)[1], "owned_by": st["provider"]["listed_owner"]}
        dryrun.Provider.served = st["provider"]["served_model"]
        try:
            self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", dryrun.PORT), dryrun.Provider)
        except OSError as e:
            refuse(f"cannot bind the loopback provider to 127.0.0.1:{dryrun.PORT}: {e}")
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


def main(argv: list[str]) -> int:
    d, max_runs = pathlib.Path(argv[0]).resolve(), int(argv[1])
    if not (d / "CAMPAIGN-real.json").is_file() or not (d / "SETUP.json").is_file():
        refuse(f"{d} is not a campaign directory (e2_setup.py first)")
    if d.is_relative_to(ROOT):
        refuse(f"{d} is inside the repository")
    if (d / "out" / "STOP").exists():
        print(f"e2_launch: {d / 'out' / 'STOP'} exists: nothing started (remove it to resume)")
        return 3
    offline = os.environ.get("E2_OFFLINE") == "1"
    st = json.loads((d / "settings" / "arm-direct.json").read_text(encoding="utf-8"))
    key_env = st["provider"]["api_key_env"]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    L = d / "launch" / stamp
    L.mkdir(parents=True)
    # the client, and where it came from
    exe, which = os.environ.get("CLIENT_EXE"), "CLIENT_EXE"
    if not exe:
        exe, which = shutil.which("opencode"), "PATH"
    if not exe or pathlib.Path(exe).name != "opencode" or not pathlib.Path(exe).is_file():
        refuse(f"no client: CLIENT_EXE unset and no `opencode` on PATH, or not a file named opencode ({exe})")
    real = os.path.realpath(exe)
    client_sha = sha_file(pathlib.Path(real))
    if offline:
        if client_sha != sha_file(FAKE):
            refuse(f"offline, but {real} is not {FAKE} byte for byte: no other client runs offline")
        provider = Provider(st)
        key = provider.dryrun.KEY
        if key_env != provider.dryrun.KEY_ENV:
            refuse(f"offline, but the settings' api_key_env is {key_env}, not {provider.dryrun.KEY_ENV}")
        store_home = d / "home"
    else:
        if not st["provider"]["endpoint"].startswith("https://"):
            refuse(f"the settings' endpoint {st['provider']['endpoint']} is not https (E2_OFFLINE=1 for the loopback)")
        key = os.environ.get(key_env, "")
        if not key:
            refuse(f"{key_env} is not set in this environment (its value is never printed)")
        store_home = pathlib.Path(os.environ["HOME"])
    # the hermetic environment: the client's directory, python's, git's, the system's — never the operator's PATH
    path = os.pathsep.join([os.path.dirname(os.path.abspath(exe)), os.path.dirname(PY),
                            os.path.dirname(shutil.which("git") or "/usr/bin/git"), "/usr/bin", "/bin"])
    found = shutil.which("opencode", path=path)
    if not found or os.path.realpath(found) != real:
        refuse(f"`opencode` on the hermetic PATH {path} is {found}, not {real}")
    env = {"PATH": path, "HOME": str(d / "home"), "XDG_CONFIG_HOME": str(d / "client" / "config"),
           "XDG_DATA_HOME": str(d / "client" / "data"), "XDG_STATE_HOME": str(d / "client" / "state"),
           "XDG_CACHE_HOME": str(d / "client" / "cache"), "TMPDIR": str(d / "tmp"), "LANG": "en_US.UTF-8",
           "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", key_env: key}
    for sub in ("home", "tmp", "client/data", "client/state", "client/cache"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    v = subprocess.run([exe, "--version"], env=env, capture_output=True, text=True, timeout=120, cwd=str(d))
    if v.returncode != 0 or not v.stdout.strip():
        refuse(f"`{exe} --version` exit {v.returncode}: {v.stderr.strip()[:300]!r}")
    version = v.stdout.strip().splitlines()[-1]

    def store(name: str) -> bytes:
        out = subprocess.run([PY, "-P", "-B", str(STORE_STAT), str(store_home)], capture_output=True, check=True).stdout
        (L / name).write_bytes(out)
        return out

    before = store("store-before.json")
    argv_driver = [PY, "-u", "-P", "-B", str(DRIVER), "run", "--campaign", str(d / "CAMPAIGN-real.json"), "--out", str(d / "out"),
                   "--client-exe", exe, "--client-version", version, "--max-runs", str(max_runs)]
    rec = {"at": now(), "mode": "offline" if offline else "real", "dir": str(d), "max_runs": max_runs,
           "client": {"given": exe, "from": which, "realpath": real, "sha256": client_sha, "version": version},
           "hermetic_path": path, "env_names": sorted(env), "store_home": str(store_home), "driver_argv": argv_driver,
           "python": PY, "aisef_head": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                                                       text=True).stdout.strip(),
           "nice": os.getpriority(os.PRIO_PROCESS, 0)}   # read (os.nice(0) raises EPERM on macOS when already niced)
    write(L / "launch.json", rec)
    print(f"e2_launch: {rec['at']} {rec['mode']} client {real} ({which}) sha256 {client_sha[:16]} version {version!r} "
          f"max_runs {max_runs} env names {rec['env_names']}")
    with (d / "run.log").open("ab") as log:
        log.write(f"=== {rec['at']} launch {stamp} {rec['mode']} max_runs {max_runs} client {real} version {version!r}\n".encode())
        log.flush()
        t0 = time.monotonic()
        code = subprocess.run(argv_driver, env=env, cwd=str(d), stdout=log, stderr=subprocess.STDOUT).returncode
        wall = round(time.monotonic() - t0, 1)
        log.write(f"=== {now()} driver exit {code} wall_s {wall}\n".encode())
    (L / "exit.txt").write_text(f"exit {code}\nwall_s {wall}\n", encoding="utf-8")
    print(f"e2_launch: {now()} driver exit {code} ({'done' if code == 0 else 'stopped (STOP or --max-runs)' if code == 3 else 'REFUSED/failed'}) wall_s {wall}")
    derived = {}
    for cmd in ("replay", "summary"):
        with (d / f"{cmd}.txt").open("wb") as f:
            derived[cmd] = subprocess.run([PY, "-P", "-B", str(DRIVER), cmd, "--out", str(d / "out")], env=env, cwd=str(d),
                                          stdout=f, stderr=subprocess.STDOUT).returncode
        print(f"e2_launch: {cmd} exit {derived[cmd]} -> {d / f'{cmd}.txt'}")
    after = store("store-after.json")
    print(f"e2_launch: store_stat {store_home}: before == after: {before == after}")
    if offline:
        provider.srv.shutdown()
    scanned = scan(d, key.encode("utf-8"))
    write(L / "end.json", {"at": now(), "driver_exit": code, "wall_s": wall, "replay_exit": derived["replay"],
                           "summary_exit": derived["summary"], "store_equal": before == after, "secret_scan": scanned,
                           "stop_present": (d / "out" / "STOP").exists()})
    copied = records(d)
    write(d / "records" / "INDEX.json", {"at": now(), "launch": stamp, "files": copied, "secret_scan": scanned})
    print(f"e2_launch: records {len(copied)} files -> {d / 'records'}; secret scan: files holding the key's value "
          f"{len(scanned['files_holding_key_value'])}, files with mixed-case 40+ tokens {len(scanned['mixed_case_tokens_40plus'])}")
    for f, ts in scanned["mixed_case_tokens_40plus"].items():
        print(f"e2_launch:   token(s) in {f}: {', '.join(ts)}  (masked; judge by eye)")
    if scanned["files_holding_key_value"]:
        print(f"e2_launch: THE KEY'S VALUE IS IN: {scanned['files_holding_key_value']} — do not copy D anywhere", file=sys.stderr)
        return 1
    print(f"e2_launch: to put the records into the repository (not run by this tool):\n"
          f"  rsync -a {d / 'records'}/ {ROOT}/closure-evidence/v2/v2.1/e2/runs/{time.strftime('%Y-%m-%d')}/")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
