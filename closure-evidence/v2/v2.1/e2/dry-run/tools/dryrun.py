#!/opt/homebrew/bin/python3 -P -B
"""The E2 dry run (closure-evidence/v2/v2.1/e2/dry-run): validation/experiments/campaign.py on both workloads, offline —
the scripted client tools/fake_opencode.py plays every arm's agent, a loopback fake provider answers both arms'
preflight, nothing reaches the real client or a network host. Run from the AISEF repository root, python 3.14:

    PY="nice -n 19 /opt/homebrew/bin/python3 -P -B"; T=closure-evidence/v2/v2.1/e2/dry-run/tools/dryrun.py
    $PY $T settings                  # settings-offline/ derived from ../settings/ (endpoint -> the loopback fake)
    $PY $T template                  # CAMPAIGN-offline.json: 2 workloads x 3 arms x 1 rep, ${SCRATCH}/${REPO} placeholders
    $PY $T setup SCRATCH             # baselines (init_repo.sh), technical approvals, the fake client, the client's config,
                                     # and SCRATCH/CAMPAIGN-offline.json rendered from the template
    $PY $T check SCRATCH             # the reference slices: each story's tests, both bundles, the wrong slice
    $PY $T campaign SCRATCH run --campaign SCRATCH/CAMPAIGN-offline.json --out SCRATCH/out \\
            --client-exe SCRATCH/client/opencode --client-version 0.0.0-dry-run-fake [--max-runs N]
    $PY $T campaign SCRATCH replay --out SCRATCH/out ;  ... summary --out SCRATCH/out
    $PY $T manifests SCRATCH         # harness.check / pair_problems on the sealed manifests, independently of the driver
    $PY $T records SCRATCH           # MANIFEST/RESULT/ARM/PREFLIGHT/campaign.log/CAMPAIGN into records/, secret grep

`campaign` builds the hermetic environment (PATH = the fake client's directory, python's, git's, /usr/bin, /bin — never
~/.opencode/bin or ~/.npm-global/bin; XDG_* and TMPDIR under SCRATCH; the fake key in AISEF_DRYRUN_KEY;
NINEROUTER_API_KEY removed, never read), starts the loopback provider on PORT in a daemon thread of this process (it
dies with it: no background process, nothing to kill) and calls campaign.main(ARGS) in-process.
AISEF_DRYRUN_WRONG=<story> in this process's environment reaches the fake client of both arms (it is in the offline
settings' client_env) and makes it write the deliberately wrong slice for that story."""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve().parents[1]          # .../e2/dry-run
E2 = HERE.parent
ROOT = HERE.parents[4]                                      # the AISEF repository root
sys.path.insert(0, str(ROOT))

PORT = 47311
ENDPOINT = f"http://127.0.0.1:{PORT}/v1"
KEY_ENV, KEY = "AISEF_DRYRUN_KEY", "dry-run-loopback-key-not-a-secret"
WRONG_ENV = "AISEF_DRYRUN_WRONG"
#: the brief's `agent:dry-run` is refused by the kernel (aisef2/product/approval.py: an approver is `human:<name>`); this
#: is a TECHNICAL approval of scratch copies, never the owner's (APPROVE.sh), never committed
APPROVER = "human:dry-run-agent"
SETTINGS = (("direct", "arm-direct"), ("aisef", "arm-aisef"), ("aisef+", "arm-aisef-plus"))
WORKLOADS = {
    "w1-a": {"init": ["sh", "init_repo.sh"], "arms": "arms/bundle.json", "evaluator": "evaluator/bundle.json",
             "requirements": "docs/requirements.md", "task": "direct-task.txt", "ref": "w1",
             "stories": {"S1": ["tests/test_digest.py"], "S2": ["tests/test_build.py"], "S3": ["tests/test_format.py"],
                         "S4": ["tests/test_cli.py"]}, "keep": ["tests/test_smoke.py"]},
    "w2": {"init": ["zsh", "init_repo.sh"], "arms": "arms/bundle.json", "evaluator": "hidden/evaluator.json",
           "requirements": "docs/requirements-delta.md", "task": "baseline/TASK.txt", "ref": "w2",
           "stories": {"S1": ["infrastructure/ci/test_delta_roots.py"], "S2": ["infrastructure/ci/test_delta_registry.py"],
                       "S3": ["infrastructure/ci/test_delta_json.py"]}, "keep": [], "wrong": "S3"},
}


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def write(p: pathlib.Path, doc) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def git(repo, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %z")


def settings() -> None:
    from aisef2.app import settings as S
    for _, name in SETTINGS:
        d = read(E2 / "settings" / f"{name}.json")
        d["provider"] = {**d["provider"], "endpoint": ENDPOINT, "api_key_env": KEY_ENV}
        d["client_env"] = [KEY_ENV, WRONG_ENV]
        S.load(d)
        write(HERE / "settings-offline" / f"{name}.json", d)
        print(f"settings-offline/{name}.json: endpoint {ENDPOINT}, api_key_env {KEY_ENV}, client_env {d['client_env']}")


def template() -> None:
    runs = []
    for wid, w in WORKLOADS.items():
        commit = read(E2 / wid / w["arms"])["plan"]["baseline"]
        task = (E2 / wid / w["task"]).read_text(encoding="utf-8").rstrip("\n")
        for arm, name in SETTINGS:
            runs.append({"run_id": f"{wid}-r1-{name[4:]}", "arm": arm, "rep": 1,
                         "workload": {"id": wid, "repo": f"${{SCRATCH}}/base/{wid}", "commit": commit,
                                      "requirements_path": w["requirements"], "task_text": task},
                         "settings_path": f"${{REPO}}/closure-evidence/v2/v2.1/e2/dry-run/settings-offline/{name}.json",
                         "bundle_path": f"${{SCRATCH}}/approved/{wid}-arms.json",
                         "evaluator_path": f"${{SCRATCH}}/approved/{wid}-evaluator.json"})
    write(HERE / "CAMPAIGN-offline.json", {"runs": runs})
    print(f"CAMPAIGN-offline.json: {len(runs)} runs; ${{SCRATCH}} = the setup directory, ${{REPO}} = the AISEF repository root")


def approve_copy(src: pathlib.Path, dst: pathlib.Path) -> dict:
    from aisef2.app import bundle_cli
    doc = read(src)
    for c in doc["contracts"]:
        doc = bundle_cli.approve(doc, c["id"], APPROVER, time.time())
    write(dst, doc)
    lint = bundle_cli.lint(doc)
    return {"source": str(src.relative_to(ROOT)), "source_sha256": sha(src), "approved": str(dst), "approved_sha256": sha(dst),
            "contracts": len(doc["contracts"]), "approver": APPROVER, "lint_verdict": lint["verdict"],
            "admitted": (lint.get("admission") or {}).get("admitted") if isinstance(lint.get("admission"), dict) else lint.get("admission")}


def setup(scratch: pathlib.Path) -> None:
    if scratch.exists():
        raise SystemExit(f"refused: {scratch} exists — setup wants a new directory")
    for d in ("base", "approved", "client", "xdg/config/opencode", "xdg/data", "xdg/state", "xdg/cache", "tmp"):
        (scratch / d).mkdir(parents=True)
    rec: dict = {"at": now(), "scratch": str(scratch), "aisef_head": git(ROOT, "rev-parse", "HEAD"), "baselines": {}, "approved": {}}
    for wid, w in WORKLOADS.items():
        dest = scratch / "base" / wid
        subprocess.run([*w["init"], str(dest)], cwd=str(E2 / wid), check=True, capture_output=True)
        commit, expected = git(dest, "rev-parse", "HEAD"), read(E2 / wid / w["arms"])["plan"]["baseline"]
        if commit != expected or git(dest, "status", "--porcelain"):
            raise SystemExit(f"{wid}: init_repo.sh gave {commit} (bundles name {expected}) or a dirty tree")
        rec["baselines"][wid] = {"repo": str(dest), "commit": commit, "tree": git(dest, "rev-parse", "HEAD^{tree}")}
        for kind in ("arms", "evaluator"):
            rec["approved"][f"{wid}-{kind}"] = approve_copy(E2 / wid / w[kind], scratch / "approved" / f"{wid}-{kind}.json")
    client = scratch / "client" / "opencode"
    shutil.copyfile(HERE / "tools" / "fake_opencode.py", client)
    client.chmod(0o755)
    shutil.copytree(HERE / "reference", scratch / "client" / "ref")
    provider = read(HERE / "settings-offline" / "arm-direct.json")["provider"]["name"]
    write(scratch / "xdg" / "config" / "opencode" / "opencode.json",
          {"provider": {provider: {"options": {"baseURL": ENDPOINT, "apiKey": f"{{env:{KEY_ENV}}}"}}}})
    text = (HERE / "CAMPAIGN-offline.json").read_text(encoding="utf-8")
    (scratch / "CAMPAIGN-offline.json").write_text(text.replace("${SCRATCH}", str(scratch)).replace("${REPO}", str(ROOT)), encoding="utf-8")
    rec.update(client={"exe": str(client), "sha256": sha(client), "source": "tools/fake_opencode.py", "source_sha256": sha(HERE / "tools" / "fake_opencode.py")},
               client_config=str(scratch / "xdg" / "config" / "opencode" / "opencode.json"), endpoint=ENDPOINT,
               campaign=str(scratch / "CAMPAIGN-offline.json"), campaign_template_sha256=sha(HERE / "CAMPAIGN-offline.json"))
    write(scratch / "SETUP.json", rec)
    print(json.dumps({k: rec[k] for k in ("baselines", "client")}, indent=1))
    for k, v in rec["approved"].items():
        print(f"approved {k}: {v['contracts']} contracts by {APPROVER}, lint {v['lint_verdict']}, admitted {v['admitted']}")


def apply_slice(repo: pathlib.Path, src: pathlib.Path, message: str) -> str:
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        dst = repo / f.relative_to(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dst)
    git(repo, "add", "-A")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=dry-run", "-c", "user.email=dry@run.invalid", "commit", "-q", "-m", message], check=True)
    return git(repo, "rev-parse", "HEAD")


def check(scratch: pathlib.Path) -> None:
    from validation.experiments import harness as H
    out: dict = {"at": now(), "workloads": {}, "ok": True}
    for wid, w in WORKLOADS.items():
        base = scratch / "base" / wid
        ref = HERE / "reference" / w["ref"]
        bundles = {k: read(scratch / "approved" / f"{wid}-{k}.json") for k in ("arms", "evaluator")}
        rows = []
        for variant in ("reference", "wrong") if "wrong" in w else ("reference",):
            repo = scratch / "check" / f"{wid}-{variant}"
            shutil.rmtree(repo, ignore_errors=True)
            subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(base), str(repo)], check=True, capture_output=True)
            for story, tests in w["stories"].items():
                rev = apply_slice(repo, ref / story, f"{story}: reference slice")
                if variant == "wrong" and story == w["wrong"]:
                    rev = apply_slice(repo, ref / f"wrong-{story}", f"{story}: wrong slice")
                # the kernel's runner flags (quality/test_execution.UNITTEST: -E -s -B, the candidate root as cwd)
                t = subprocess.run([sys.executable, "-E", "-s", "-B", "-m", "unittest", *tests, *w["keep"]], cwd=str(repo),
                                   capture_output=True, text=True)
                ev = {k: H.evaluate(repo, rev, b) for k, b in bundles.items()}
                row = {"variant": variant, "story": story, "commit": rev, "tests_exit": t.returncode,
                       "tests_tail": t.stderr.strip().splitlines()[-1:],
                       **{k: f"{e['satisfied']}/{e['total']}" for k, e in ev.items()},
                       "not_satisfied": {k: e["not_satisfied"] for k, e in ev.items()}}
                rows.append(row)
                expected_tests = 0 if not (variant == "wrong" and story == w["wrong"]) else t.returncode
                out["ok"] &= t.returncode == expected_tests
            last = rows[-1]
            full = {k: f"{len(b['contracts'])}/{len(b['contracts'])}" for k, b in bundles.items()}
            if variant == "reference":
                out["ok"] &= all(last[k] == full[k] for k in bundles)
            else:
                out["ok"] &= all(last[k] != full[k] for k in bundles)
            if wid == "w2" and variant == "reference":    # §4.1: the brownfield pytest file keeps passing
                p = subprocess.run([sys.executable, "-P", "-B", "-m", "pytest", "infrastructure/ci", "-q", "-p", "no:cacheprovider"],
                                   cwd=str(repo), capture_output=True, text=True)
                rows.append({"variant": variant, "pytest_infrastructure_ci_exit": p.returncode, "tail": p.stdout.strip().splitlines()[-1:]})
                out["ok"] &= p.returncode == 0
        out["workloads"][wid] = rows
    write(scratch / "CHECK.json", out)
    for wid, rows in out["workloads"].items():
        for r in rows:
            print(wid, json.dumps(r, sort_keys=True))
    print("check:", "OK" if out["ok"] else "PROBLEMS")
    raise SystemExit(0 if out["ok"] else 1)


class Provider(http.server.BaseHTTPRequestHandler):
    """The loopback fake provider: lists the route's model under the settings' listed_owner, serves every chat probe as
    the settings' served_model under one fingerprint (tests/v2/test_app_run.provider, over HTTP)."""
    listing: dict = {}
    served: str = ""

    def _send(self, doc: dict) -> None:
        body = json.dumps(doc).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send({"data": [self.listing]})

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send({"model": self.served, "system_fingerprint": "fp-dry-run", "usage": {"prompt_tokens": 9, "completion_tokens": 1}})

    def log_message(self, *a) -> None:
        pass


def campaign(scratch: pathlib.Path, args: list[str]) -> None:
    st = read(HERE / "settings-offline" / "arm-direct.json")
    if st["provider"]["endpoint"] != ENDPOINT:
        raise SystemExit(f"settings-offline endpoint {st['provider']['endpoint']} is not {ENDPOINT}")
    git_dir = os.path.dirname(shutil.which("git") or "/usr/bin/git")
    env = {"PATH": os.pathsep.join([str(scratch / "client"), os.path.dirname(sys.executable), git_dir, "/usr/bin", "/bin"]),
           "XDG_CONFIG_HOME": str(scratch / "xdg" / "config"), "XDG_DATA_HOME": str(scratch / "xdg" / "data"),
           "XDG_STATE_HOME": str(scratch / "xdg" / "state"), "XDG_CACHE_HOME": str(scratch / "xdg" / "cache"),
           "TMPDIR": str(scratch / "tmp"), KEY_ENV: KEY}
    os.environ.pop("NINEROUTER_API_KEY", None)           # never read, never printed
    os.environ.update(env)
    found = shutil.which("opencode")
    if not found or os.path.realpath(found) != os.path.realpath(scratch / "client" / "opencode"):
        raise SystemExit(f"opencode on the hermetic PATH is {found}, not the fake client")
    Provider.listing = {"id": st["route"].split("/", 1)[1], "owned_by": st["provider"]["listed_owner"]}
    Provider.served = st["provider"]["served_model"]
    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Provider)
    except OSError as e:
        raise SystemExit(f"cannot bind the loopback provider to 127.0.0.1:{PORT}: {e}")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"dry-run: {now()} PATH={os.environ['PATH']} opencode={found} provider=127.0.0.1:{PORT} "
          f"{WRONG_ENV}={os.environ.get(WRONG_ENV, '')!r} NINEROUTER_API_KEY in env: {'NINEROUTER_API_KEY' in os.environ}")
    from validation.experiments import campaign as C
    code = C.main(args)
    srv.shutdown()
    print(f"dry-run: {now()} campaign.main exit {code}")
    raise SystemExit(code)


def manifests(scratch: pathlib.Path) -> None:
    """harness.check on every sealed manifest under SCRATCH/out and harness.pair_problems on every pair, independently
    of the driver's own run (what `campaign: N manifests sealed and paired` summarised)."""
    from validation.experiments import harness as H
    ms = {p.parent.name: read(p) for p in sorted((scratch / "out").glob("*/MANIFEST.json"))}
    bad = 0
    for name, m in ms.items():
        problems = H.check(m)
        bad += bool(problems)
        print(f"check {name}: {'PASS' if not problems else 'FAIL ' + '; '.join(problems)}  seal {m['manifest_sha256'][:16]} arm {m['pair']['arm']} pair {m['pair']['pair_id']}")
    pairs: dict[str, list] = {}
    for name, m in ms.items():
        pairs.setdefault(m["pair"]["pair_id"], []).append((name, m))
    for pid, members in pairs.items():
        for name, m in members[1:]:
            problems = H.pair_problems(members[0][1], m)
            bad += bool(problems)
            print(f"pair {pid}: {members[0][0]} vs {name}: {'PASS' if not problems else 'FAIL ' + '; '.join(problems)}")
    print(f"manifests: {len(ms)} checked, {sum(len(v) - 1 for v in pairs.values())} pairings, {'all PASS' if not bad else f'{bad} FAIL'}")
    raise SystemExit(1 if bad else 0)


def records(scratch: pathlib.Path) -> None:
    out, dest = scratch / "out", HERE / "records"
    copied = {}
    for src in sorted([*out.glob("*/MANIFEST.json"), *out.glob("*/RESULT.json"), *out.glob("*/arm/ARM.json"),
                       *out.glob("*/arm/preflight/PREFLIGHT.json"), *out.glob("*/arm/run/preflight/PREFLIGHT.json"),
                       *out.glob("*/arm/sessions/*.jsonl"), *out.glob("*/arm/run/sessions/*.jsonl"),     # small: the fake's two lines each
                       out / "campaign.log", out / "CAMPAIGN.json", scratch / "SETUP.json", scratch / "CHECK.json"]):
        if not src.exists():
            continue
        rel = src.relative_to(scratch)
        d = dest / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, d)
        copied[str(rel)] = {"sha256": sha(d), "bytes": d.stat().st_size}
    # the variable's NAME occurs once per `campaign` output, in this tool's own line proving it was removed from the
    # environment ("NINEROUTER_API_KEY in env: False"); any other occurrence, or the fake key's value, fails the copy
    env_line = "NINEROUTER_API_KEY in env: False"
    hits = {"NINEROUTER_in_env_check_line": 0, "NINEROUTER_elsewhere": 0, "fake_key_value": 0, "[REDACTED]": 0}
    for p in dest.rglob("*"):
        if p.is_file() and p.name != "INDEX.json":
            text = p.read_text(encoding="utf-8", errors="replace")
            hits["NINEROUTER_in_env_check_line"] += text.count(env_line)
            hits["NINEROUTER_elsewhere"] += text.count("NINEROUTER") - text.count(env_line)
            hits["fake_key_value"] += text.count(KEY)
            hits["[REDACTED]"] += text.count("[REDACTED]")
    write(dest / "INDEX.json", {"at": now(), "from": str(out), "files": copied, "secret_grep": hits})
    print(json.dumps({"copied": len(copied), "secret_grep": hits}))
    if hits["NINEROUTER_elsewhere"] or hits["fake_key_value"]:
        raise SystemExit("a secret-like string is in the records")


def main(argv: list[str]) -> None:
    cmd, rest = argv[0], argv[1:]
    if cmd == "settings":
        settings()
    elif cmd == "template":
        template()
    elif cmd in ("setup", "check", "manifests", "records"):
        {"setup": setup, "check": check, "manifests": manifests, "records": records}[cmd](pathlib.Path(rest[0]).resolve())
    elif cmd == "campaign":
        campaign(pathlib.Path(rest[0]).resolve(), rest[1:])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
