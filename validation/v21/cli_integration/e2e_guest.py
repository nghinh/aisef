"""AISEF 2.1, B-03 round 3, WP-E2E: a real `aisef run` — the real CLI, `python3 -B -m aisef` — end to end inside the Linux
guest, with a scripted client and a loopback provider (no paid provider, no network beyond the container's own
loopback). It runs in the container e2e_linux.sh starts, from the tree mounted read-only at /repo, in a scratch
directory of its own, and prints ONE JSON document: scenario -> checks -> passed/failed with the evidence excerpt.
A check that fails is a finding; the exit status is non-zero then, and no check is relaxed to pass.

    python3 -B validation/v21/cli_integration/e2e_guest.py run --profile X1|hardened [--work DIR] [--only S1,S2,...]
    python3 -B validation/v21/cli_integration/e2e_guest.py compare RESULT_A.json RESULT_B.json     (any host)

Scenarios (profile X1 unless noted):
  S1   success, confined
  S2   writes outside the allowed scope, confined;  S2c  the same attempts without confinement (the control: the
       operator's uid CAN write every target, so the denials in S2 are bubblewrap's)
  S2b  the isolation cannot be given, so the run is refused and nothing starts: S2b-readonly, S2b-missing,
       S2b-not-executable, S2b-client-holds-home; and, profile hardened, S2b-hardened (the container's own boundary
       stops bubblewrap)
  S3   children of a confined session;  S3t  the session times out (the kernel's teardown);  S3c  the control
  S4   evidence and anchor, on copies of S1's run directory

The driver signals nothing and removes nothing (INV-MUTATION-AUTHORITY): the processes it looks for are only
observed, the provider is a thread of this process, and what a scenario leaves stays in the container, which is
discarded. The client is validation/v21/cli_integration/e2e_client.py, data-driven by scenario.json."""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent
TREE = HERE.parents[2]
sys.path.insert(0, str(TREE))
BWRAP, PORT, KEY = "/usr/bin/bwrap", 18437, "sk-e2e-scripted-not-a-key"
CONFINEMENT = {"backend": "bwrap", "bwrap": BWRAP, "network": "host", "read_only": []}
OWNERS = ("DEVELOPER", "PLAN", "ENVIRONMENT", "PROVIDER", "INTEGRATION", "REVIEW", "SECURITY")
SYSTEM_SITE = sysconfig.get_paths()["purelib"]
EXPECTED_RUN_DIR = {"RUN.started.json", "RUN.json", "EVIDENCE.json", "repo", "run", "work", "test-python", "preflight",
                    "sessions", "confinement"}
NS = ("user", "pid", "net", "ipc", "uts", "mnt")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jread(p: pathlib.Path):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def snapshot(root: pathlib.Path) -> dict[str, str]:
    """Every entry below `root` (a file: its sha256; a link: its target; a directory), `__pycache__` aside."""
    out: dict[str, str] = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x != "__pycache__")
        for name in sorted([*dirs, *files]):
            p = pathlib.Path(d, name)
            key = p.relative_to(root).as_posix()
            out[key] = ("link:" + os.readlink(p)) if p.is_symlink() else "dir" if p.is_dir() else sha(p.read_bytes())
    return out


def journal_events(out: pathlib.Path) -> list[dict]:
    p = out / "run" / "journals" / "aisef-run.jsonl"
    return [json.loads(x)["event"] for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.is_file() else []


def processes_with(marker: str) -> list[dict]:
    """The live processes (any session, any namespace the container's /proc shows) whose command line holds `marker`:
    observed only, never signalled."""
    found = []
    for p in os.listdir("/proc"):
        if not p.isdigit() or int(p) == os.getpid():
            continue
        try:
            cmd = pathlib.Path(f"/proc/{p}/cmdline").read_bytes().decode("utf-8", "replace").split("\0")[:-1]
            st = pathlib.Path(f"/proc/{p}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if any(marker in a for a in cmd) and st[0] not in ("Z", "X"):
            found.append({"pid": int(p), "state": st[0], "ppid": int(st[1]), "pgrp": int(st[2]), "sid": int(st[3]),
                          "last_arg": cmd[-1]})
    return sorted(found, key=lambda d: d["pid"])


class Watch:
    """A thread of this driver that looks at /proc every 20 ms while a CLI step runs — it reads, it never signals:
    when a session's processes (`--title <title>` in the command line) were there and when the marked children were."""

    def __init__(self, marker: str, title: str) -> None:
        self.marker, self.title, self.rows = marker, title, []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            session = marked = 0
            for p in os.listdir("/proc"):
                try:
                    cmd = pathlib.Path(f"/proc/{p}/cmdline").read_bytes().decode("utf-8", "replace").split("\0")
                except OSError:
                    continue
                session += "--title" in cmd and self.title in cmd
                marked += any(self.marker in a for a in cmd)
            self.rows.append((time.monotonic(), session, marked))
            self._stop.wait(0.02)

    def __enter__(self) -> "Watch":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()

    def timeline(self) -> dict:
        r, t0 = self.rows, self.rows[0][0] if self.rows else 0.0
        present = [i for i, x in enumerate(r) if x[1]]
        windows = sum(1 for i in present if i == 0 or not r[i - 1][1])
        kids = [i for i, x in enumerate(r) if x[2]]
        # a poll after the session's processes were seen gone (two polls in a row, so a scan that straddles the
        # exit does not count) that still shows a marked child
        after = [i for i in kids if present and i > present[0] and i >= 1 and not r[i][1] and not r[i - 1][1]]
        at = lambda i: round(r[i][0] - t0, 2)   # noqa: E731
        return {"polls": len(r), "session_windows": windows,
                "session_first_seen_s": at(present[0]) if present else None,
                "session_last_seen_s": at(present[-1]) if present else None,
                "children_first_seen_s": at(kids[0]) if kids else None, "children_last_seen_s": at(kids[-1]) if kids else None,
                "polls_with_children_after_the_session_was_gone": len(after)}


class Provider:
    """A loopback OpenAI-compatible endpoint, a thread of this process: the preflight's model listing and chat probes
    (what validation/v21/cli_integration/fakeprov.py answers for them). `log` is what reached it."""

    def __init__(self, port: int) -> None:
        self.log: list[dict] = []
        log = self.log

        class H(http.server.BaseHTTPRequestHandler):
            def reply(self, doc: dict) -> None:
                data = json.dumps(doc).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def note(self) -> None:
                log.append({"t_ns": time.time_ns(), "method": self.command, "path": self.path,
                            "bearer_is_the_key": self.headers.get("Authorization") == f"Bearer {KEY}"})

            def do_GET(self) -> None:
                self.note()
                self.reply({"data": [{"id": "model-1", "owned_by": "fake"}]})

            def do_POST(self) -> None:
                self.rfile.read(int(self.headers["Content-Length"]))
                self.note()
                self.reply({"id": "p", "object": "chat.completion", "model": "model-1", "system_fingerprint": "fp-1",
                            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})

            def log_message(self, *a) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


def settings_doc(confinement: dict | None, developer_timeout_s: float = 60) -> dict:
    doc = {"format": "aisef-v2-run/1", "client": "opencode", "route": "fakeprov/model-1",
           "provider": {"name": "fakeprov", "endpoint": f"http://127.0.0.1:{PORT}/v1", "api_key_env": "FAKE_PROVIDER_KEY",
                        "served_model": "model-1", "listed_owner": "fake", "model_limit": {"context": 100000, "output": 8000}},
           "client_env": [], "budget": {"provider_requests": 40, "turns": 80, "input_tokens": 200000, "output_tokens": 20000},
           "max_turns_per_session": 10, "limits": {o: 1 for o in OWNERS},
           "timeouts_s": {"developer": developer_timeout_s, "reviewer": 120, "tool": 120, "probe": 60},
           "preflight": {"chat_probes": 2}, "review": {"policy": "fix-loop", "min_severity": "high"},
           "prices": {"currency": "USD", "input_per_mtok": 1.32, "cache_read_per_mtok": 0.044, "cache_write_per_mtok": 1.32,
                      "output_per_mtok": 3.96, "source": "e2e fixture (not a real price)", "effective_date": "2026-10-12"}}
    if confinement is not None:
        doc["confinement"] = confinement
    return doc


def authoring() -> dict:
    def contract(cid, argv, code):
        return {"id": cid, "requirement_ids": ["R-CLI"], "subject": {"kind": "cli_invocation", "locator": "app:__main__"},
                "stimulus": {"argv": argv}, "observable": {"exit_code": code, "within_s": 20}, "polarity": "MUST_HOLD",
                "subject_absence": "REQUIRES_SUBJECT", "rationale": "the requirement's own example"}

    def crit(cid, con, clause, text):
        return {"id": cid, "contract": con, "role": "INTRODUCE", "depends_on": [], "why": f"S1 introduces {clause}",
                "facts": {"requirement": "R-CLI", "section": "§1", "clause": clause, "clause_text": text,
                          "subject": "python -m app"}}
    total, usage = "exits with the sum of the integers A and B", "exit 2 on a usage error (any other number of arguments)"
    return {"format": "aisef-v2-authoring/1", "name": "calc-cli", "description": "A calculator command.",
            "requirements_document": {"path": "docs/requirements.md"}, "product_roots": ["app", "tests"], "baseline": "HEAD",
            "requirements": [{"id": "R-CLI", "text": f"python -m app A B {total}; {usage}", "source": "docs/requirements.md §1"}],
            "contracts": [contract("BC-SUM", ["2", "3"], 5), contract("BC-USAGE-0", [], 2), contract("BC-USAGE-1", ["1"], 2)],
            "stories": {"S1": {"depends_on": [], "tests": ["tests/test_cli.py"], "criteria": [
                crit("C-SUM", "BC-SUM", "1.1", total), crit("C-USAGE-0", "BC-USAGE-0", "1.2", usage),
                crit("C-USAGE-1", "BC-USAGE-1", "1.2", usage)]}}}


class Scenario:
    """One scenario: a directory of its own holding the client (with its scenario.json), HOME, the client's
    configuration, the settings JSON the run used (verbatim) and, once run, the run directory."""

    def __init__(self, ctx: "Ctx", name: str, title: str, *, confinement: dict | None, children: str | None = None,
                 legit: bool = True, hang_s: int = 0, developer_timeout_s: float = 60, isolated_kernel: bool = False) -> None:
        self.ctx, self.name, self.title = ctx, name, title
        self.dir = ctx.work / name
        self.bin, self.home, self.xdg, self.out = self.dir / "fakebin", self.dir / "home", self.dir / "xdg", self.dir / "run"
        self.checks: list[dict] = []
        self.facts: dict = {}           # what two runs must agree on
        self.volatile: dict = {}        # what is expected to differ between runs (anchors, commit ids, timings)
        self.observed: dict = {}        # what was seen and is reported, not asserted
        self.cli_steps: list[dict] = []
        self.kernel, self.python = TREE, sys.executable
        for d in (self.bin, self.home, self.xdg / "opencode"):
            d.mkdir(parents=True)
        if isolated_kernel:     # a kernel and an interpreter the operator's uid CAN write: the denials are then bwrap's
            self.kernel = self.dir / "kernel"
            for pkg in ("aisef", "aisef2"):
                shutil.copytree(TREE / pkg, self.kernel / pkg, ignore=shutil.ignore_patterns("__pycache__"))
            subprocess.run([sys.executable, "-B", "-m", "venv", "--without-pip", str(self.dir / "venv")], check=True,
                           capture_output=True)
            self.python = str(self.dir / "venv" / "bin" / "python")
        exe = self.bin / "opencode"
        exe.write_text(f"#!{sys.executable}\n" + (HERE / "e2e_client.py").read_text(encoding="utf-8"), encoding="utf-8")
        exe.chmod(0o755)
        self.script(children=children, legit=legit, hang_s=hang_s, linger_s=0.5 if children else 0.0)
        (self.xdg / "opencode" / "opencode.json").write_text(json.dumps(
            {"provider": {"fakeprov": {"options": {"baseURL": f"http://127.0.0.1:{PORT}/v1", "apiKey": "{env:FAKE_PROVIDER_KEY}"}}}}))
        self.settings = settings_doc(confinement, developer_timeout_s)
        (self.dir / "settings.json").write_text(json.dumps(self.settings, indent=1), encoding="utf-8")
        self.env = {"PATH": f"{self.bin}:/usr/local/bin:/usr/bin:/bin", "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.xdg),
                    "FAKE_PROVIDER_KEY": KEY, "PYTHONPATH": str(self.kernel), "LANG": "C.UTF-8"}
        ctx.scenarios.append(self)

    def script(self, *, attempts=(), reviewer_attempts=(), children: str | None = None, legit: bool = True,
               hang_s: int = 0, linger_s: float = 0.0) -> None:
        """What the scripted client does in this scenario (its scenario.json, next to it, in the client's directory)."""
        (self.bin / "scenario.json").write_text(json.dumps(
            {"attempts": list(attempts), "reviewer_attempts": list(reviewer_attempts), "children": children, "legit": legit,
             "hang_s": hang_s, "linger_s": linger_s}, indent=1), encoding="utf-8")

    def ok(self, name: str, passed: bool, evidence) -> bool:
        self.checks.append({"name": name, "passed": bool(passed), "evidence": evidence})
        return bool(passed)

    def cli(self, tag: str, args: list[str], timeout: int = 900) -> dict:
        argv = [self.python, "-B", "-m", "aisef", *args]
        t0 = time.monotonic()
        p = subprocess.run(argv, cwd=self.dir, env=self.env, capture_output=True, text=True, timeout=timeout)
        step = {"tag": tag, "argv": argv, "cwd": str(self.dir), "exit": p.returncode,
                "seconds": round(time.monotonic() - t0, 1), "stdout": p.stdout, "stderr": p.stderr}
        try:
            step["json"] = json.loads(p.stdout)
        except ValueError:
            step["json"] = None
        self.cli_steps.append(step)
        (self.dir / f"cli-{len(self.cli_steps):02d}-{tag}.json").write_text(json.dumps(step, indent=1), encoding="utf-8")
        return step

    def project(self, *more: str) -> list[str]:
        return ["--project", str(self.ctx.approved), *more]

    def run_args(self) -> list[str]:
        return self.project("--settings", "settings.json", "--repo", str(self.ctx.repo))

    def record(self) -> dict:
        return jread(self.out / "RUN.json")

    def observations(self) -> dict[str, dict[str, list[dict]]]:
        """role -> observation name -> events, in session order: what the scripted client said, read back from the
        session streams (the run's evidence), never from anything else."""
        out: dict = {}
        for p in sorted((self.out / "sessions").glob("*.jsonl")):
            for line in p.read_text(encoding="utf-8").splitlines():
                ev = json.loads(line) if line.startswith("{") else {}
                if ev.get("type") == "e2e_observation":
                    out.setdefault(ev["role"], {}).setdefault(ev["name"], []).append(ev)
        return out

    def streams(self) -> list[str]:
        return sorted(p.name for p in (self.out / "sessions").glob("*.jsonl"))

    def summary(self) -> dict:
        return {"scenario": self.name, "title": self.title, "passed": all(c["passed"] for c in self.checks),
                "checks": self.checks, "observed": self.observed, "facts": self.facts, "volatile": self.volatile,
                "cli": [{k: s[k] for k in ("tag", "argv", "exit", "seconds")} for s in self.cli_steps]}


class Ctx:
    def __init__(self, work: pathlib.Path) -> None:
        self.work, self.scenarios = work, []
        work.mkdir(parents=True)
        self.provider = Provider(PORT)
        self.project_steps: list[dict] = []
        self.container_ns = {n: os.readlink(f"/proc/self/ns/{n}") for n in NS}

    def build_project(self) -> None:
        """The calculator project through the real CLI: seal, approve each contract (a human's act, here the driver's),
        lint — the bundle every scenario runs."""
        p = self.work / "project"
        (p / "home").mkdir(parents=True)
        (p / "authoring.json").write_text(json.dumps(authoring(), indent=1), encoding="utf-8")
        self.repo, self.approved = p / "repo", p / "approved.json"
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(p / "home"), "PYTHONPATH": str(TREE), "LANG": "C.UTF-8"}

        def sh(*argv: str, cwd=p) -> None:
            subprocess.run(list(argv), cwd=cwd, env=env, check=True, capture_output=True)
        (self.repo / "app").mkdir(parents=True)
        (self.repo / "docs").mkdir()
        (self.repo / "app" / "__init__.py").write_text("")
        (self.repo / "docs" / "requirements.md").write_text(
            "# Calc CLI\n\n## 1. Command line\n\n1.1 python -m app A B exits with the sum of the integers A and B.\n\n"
            "1.2 Exit 2 on a usage error (any other number of arguments).\n")
        sh("git", "init", "-q", "-b", "main", cwd=self.repo)
        sh("git", "add", "-A", cwd=self.repo)
        sh("git", "-c", "user.name=o", "-c", "user.email=o@o", "commit", "-qm", "baseline", cwd=self.repo)

        def aisef(*args: str) -> subprocess.CompletedProcess:
            argv = [sys.executable, "-B", "-m", "aisef", *args]
            r = subprocess.run(argv, cwd=p, env=env, capture_output=True, text=True)
            self.project_steps.append({"argv": argv, "exit": r.returncode, "stdout": r.stdout, "stderr": r.stderr})
            if r.returncode != 0:
                raise RuntimeError(f"the project could not be built: {argv[3:]} exited {r.returncode}: {r.stderr[:500]}")
            return r
        aisef("bundle", "seal", "authoring.json", "--repo", "repo", "--out", "sealed.json")
        prev = "sealed.json"
        for i, con in enumerate(("BC-SUM", "BC-USAGE-0", "BC-USAGE-1")):
            nxt = "approved.json" if con == "BC-USAGE-1" else f"a{i + 1}.json"
            aisef("bundle", "approve", prev, "--contract", con, "--approver", "human:e2e", "--out", nxt)
            prev = nxt
        aisef("bundle", "lint", "approved.json")
        (p / "not-bwrap").write_text("a regular file that is not executable\n")
        (p / "not-bwrap").chmod(0o644)
        (p / "project-steps.json").write_text(json.dumps(self.project_steps, indent=1), encoding="utf-8")


def environment(ctx: Ctx) -> dict:
    from aisef2.app import run as R
    st = {k: v.split()[0] for k, v in (ln.split(":", 1) for ln in pathlib.Path("/proc/self/status").read_text().splitlines()
                                       if ":" in ln) if k in ("NoNewPrivs", "Seccomp", "CapEff", "CapBnd")}

    def out(*argv: str) -> str:
        r = subprocess.run(list(argv), capture_output=True, text=True)
        return (r.stdout + r.stderr).strip().splitlines()[0] if (r.stdout + r.stderr).strip() else ""
    routes = pathlib.Path("/proc/net/route").read_text().splitlines()[1:]
    return {"uname": " ".join(os.uname()), "python": sys.version.split()[0], "python_executable": sys.executable,
            "debian": pathlib.Path("/etc/debian_version").read_text().strip(), "uid": os.getuid(), "gid": os.getgid(),
            "container_process_status": st, "max_user_namespaces": pathlib.Path("/proc/sys/user/max_user_namespaces").read_text().strip(),
            "bwrap": out(BWRAP, "--version"), "bwrap_sha256": sha(pathlib.Path(BWRAP).read_bytes()), "git": out("git", "--version"),
            "network_interfaces": sorted(os.listdir("/sys/class/net")), "routes": routes, "container_namespaces": ctx.container_ns,
            "kernel_digest": R.kernel_digest(), "tree": str(TREE), "system_site_packages": SYSTEM_SITE,
            "no_real_opencode_on_path": all(not (pathlib.Path(d) / "opencode").exists() for d in
                                            ("/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"))}


def expected_wrapper(s: Scenario, workspace: str, writable: bool) -> list[str]:
    """confine.argv's command line for this session, computed from the inputs the kernel had: the client's directory,
    the run clone's common git directory, the client's configuration directory — the prefix up to `--`."""
    from aisef2.app import confine
    ro = [os.path.dirname(os.path.realpath(s.bin / "opencode")), str((s.out / "repo" / ".git").resolve()),
          str(s.xdg / "opencode"), *CONFINEMENT["read_only"]]
    return confine.argv(CONFINEMENT, [], workspace, ro, writable)


def s1(ctx: Ctx) -> Scenario:
    s = Scenario(ctx, "S1", "success, confined", confinement=CONFINEMENT)
    before = len(ctx.provider.log)
    chk = s.cli("check", ["run", "--check", *s.run_args()])
    cj = chk["json"] or {}
    s.ok("check_is_ready_and_measured", chk["exit"] == 0 and cj.get("ready") is True
         and (cj.get("confinement") or {}).get("problems") == [] and len(ctx.provider.log) == before,
         {"exit": chk["exit"], "ready": cj.get("ready"), "problems": (cj.get("confinement") or {}).get("problems"),
          "provider_requests_during_check": len(ctx.provider.log) - before})
    run = s.cli("run", ["run", *s.run_args(), "--out", "run", "--anchor-out", "anchor.txt"])
    rj = run["json"] or {}
    s.ok("run_exit_0_delivery_pass", run["exit"] == 0 and rj.get("delivery_verdict") == "PASS"
         and rj.get("story_outcomes") == {"S1": ["COMMIT"]},
         {"exit": run["exit"], "delivery_verdict": rj.get("delivery_verdict"), "story_outcomes": rj.get("story_outcomes"),
          "delivery_blocked_by": rj.get("delivery_blocked_by"), "stderr": run["stderr"][:300]})
    rec = s.record()
    conf = rec.get("confinement") or {}
    inside = conf.get("inside") or {}
    caps = inside.get("capabilities") or {}
    s.ok("record_confinement_measured", conf.get("problems") == [] and conf.get("backend") == "bwrap"
         and conf.get("bwrap") == BWRAP and conf.get("network") == "host"
         and conf.get("bwrap_sha256") == sha(pathlib.Path(BWRAP).read_bytes())
         and all((inside.get("namespaces") or {}).get(n) == "own" for n in ("user", "pid", "ipc", "uts", "mnt"))
         and (inside.get("namespaces") or {}).get("net") == "shared"
         and all(int(v, 16) == 0 for k, v in caps.items() if k != "CapBnd" and v) and inside.get("no_new_privs") == "1"
         and conf.get("setsid_survivors") == [] and conf.get("left_on_host") == []
         and not any((conf.get("created_outside_workspace") or {}).values()),
         {"problems": conf.get("problems"), "bwrap": conf.get("bwrap"), "bwrap_version": conf.get("bwrap_version"),
          "bwrap_sha256": conf.get("bwrap_sha256"), "network": conf.get("network"), "namespaces": inside.get("namespaces"),
          "capabilities": caps, "no_new_privs": inside.get("no_new_privs"), "seccomp": inside.get("seccomp"),
          "mount_targets": inside.get("mount_targets"), "mounts": inside.get("mounts"), "uid": inside.get("uid"),
          "operator_uid": conf.get("operator_uid"), "setsid_survivors": conf.get("setsid_survivors"),
          "tried": conf.get("tried"), "operator_can": conf.get("operator_can")})
    canary = (s.out / "confinement" / "canary").stat().st_mtime_ns if (s.out / "confinement" / "canary").is_file() else None
    first = min((e["t_ns"] for e in ctx.provider.log[before:]), default=None)
    s.ok("measured_before_the_first_provider_request", canary is not None and first is not None and canary < first
         and (rec.get("preflight") or {}).get("verdict") == "ATTESTED",
         {"canary_mtime_ns": canary, "first_provider_request_ns": first, "preflight_verdict": (rec.get("preflight") or {}).get("verdict"),
          "requests_seen_by_provider": [(e["method"], e["path"], e["bearer_is_the_key"]) for e in ctx.provider.log[before:]]})
    sessions = rec.get("sessions") or []
    s.ok("every_session_recorded_as_bwrap", len(sessions) == 2 and {x.get("role") for x in sessions} == {"developer", "reviewer"}
         and all(x.get("started") and x.get("exit") == 0 and not x.get("timed_out") for x in sessions)
         and {x["role"]: x.get("confinement") for x in sessions}
         == {"developer": "bwrap network=host", "reviewer": "bwrap network=host workspace=read-only"},
         [{k: x.get(k) for k in ("role", "story_id", "attempt", "exit", "timed_out", "turns", "confinement", "log")} for x in sessions])
    obs = s.observations()
    dev = (obs.get("developer") or {}).get("self", [{}])[0]
    rev = (obs.get("reviewer") or {}).get("self", [{}])[0]
    for who, view, writable in (("developer", dev, True), ("reviewer", rev, False)):
        ws = view.get("cwd", "")
        want = expected_wrapper(s, ws, writable)
        got = view.get("pid1_cmdline") or []
        tail = got[len(want):]
        ns = view.get("ns") or {}
        s.ok(f"{who}_ran_inside_bwrap_as_pid_1_with_the_kernels_argv",
             view.get("pid1_comm") == "bwrap" and got[:len(want)] == want and tail == view.get("argv")
             and got[:1] == [BWRAP],
             {"pid1_comm": view.get("pid1_comm"), "pid1_cmdline_prefix_equals_confine.argv": got[:len(want)] == want,
              "tail_equals_the_clients_own_argv": tail == view.get("argv"), "wrapper_argv": got[:len(want)],
              "client_argv": view.get("argv")})
        st = view.get("status") or {}
        s.ok(f"{who}_inside_view_unprivileged_and_namespaced",
             view.get("uid") == 1000 and st.get("NoNewPrivs") == "1" and all(int(st.get(k, "1"), 16) == 0 for k in
                                                                             ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))
             and view.get("home") == "/aisef-home" and view.get("pid") < 20
             and all(ns.get(n) != ctx.container_ns[n] for n in ("user", "pid", "ipc", "uts", "mnt"))
             and ns.get("net") == ctx.container_ns["net"],
             {"uid": view.get("uid"), "status": st, "home": view.get("home"), "home_listing": view.get("home_listing"),
              "pid": view.get("pid"), "ppid": view.get("ppid"), "namespaces_inside": ns,
              "namespaces_of_the_container": ctx.container_ns})
        wm = view.get("workspace_mount") or [None, None, None]
        s.ok(f"{who}_workspace_mount_is_{'rw' if writable else 'ro'}", wm[2] == ("rw" if writable else "ro"),
             {"workspace": ws, "mount": wm})
    work = (obs.get("developer") or {}).get("work", [])
    git = subprocess.run(["git", "-C", str(s.out / "repo"), "show", f"{rec.get('final_main')}:app/cli.py"],
                         capture_output=True, text=True).stdout
    s.ok("developer_work_landed_on_main", "return int(args[0]) + int(args[1])" in git and bool(work),
         {"final_main": rec.get("final_main"), "app/cli.py": git, "developer_committed_itself":
          [x.get("developer_committed_itself") for x in sessions if x.get("role") == "developer"]})
    anchor_file = s.dir / "anchor.txt"
    s.ok("anchor_file_is_0444_and_is_the_printed_anchor", anchor_file.is_file()
         and (anchor_file.stat().st_mode & 0o777) == 0o444 and anchor_file.read_text().strip() == rj.get("evidence_anchor"),
         {"mode": oct(anchor_file.stat().st_mode & 0o777) if anchor_file.is_file() else None,
          "file": anchor_file.read_text().strip() if anchor_file.is_file() else None, "printed": rj.get("evidence_anchor")})
    ver = s.cli("verify", ["run", "--verify", *s.project("--out", "run", "--expect-anchor", rj.get("evidence_anchor", ""))])
    vj = ver["json"] or {}
    s.ok("verify_with_the_anchor_is_VERIFIED", ver["exit"] == 0 and vj.get("verdict") == "VERIFIED"
         and vj.get("evidence_anchor") == rj.get("evidence_anchor") and vj.get("delivery_verdict") == "PASS"
         and vj.get("problems") == [],
         {"exit": ver["exit"], "verdict": vj.get("verdict"), "problems": vj.get("problems"), "journal_events": vj.get("journal_events"),
          "evidence_anchor": vj.get("evidence_anchor"), "notes": vj.get("notes")})
    events = journal_events(s.out)
    s.facts = {"check_exit": chk["exit"], "run_exit": run["exit"], "delivery_verdict": rj.get("delivery_verdict"),
               "story_outcomes": rj.get("story_outcomes"), "verify_exit": ver["exit"], "verify_verdict": vj.get("verdict"),
               "confinement_problems": conf.get("problems"), "namespaces": inside.get("namespaces"),
               "sessions": [(x["role"], x.get("exit"), x.get("turns"), x.get("confinement")) for x in sessions],
               "journal_events": len(events), "journal_event_types_sha": sha("\n".join(e["type"] for e in events).encode()),
               "provider_requests": len(ctx.provider.log) - before, "kernel_digest": rec.get("kernel_digest")}
    s.volatile = {"evidence_anchor": rj.get("evidence_anchor"), "final_main": rec.get("final_main"),
                  "journal_sha256": (rec.get("journal") or {}).get("sha256"), "started": rec.get("started")}
    return s


def attempts_for(s: Scenario, nonce: str) -> tuple[list, list]:
    """What the scripted developer (and, on the reviewer's own list, the model reviewer) tries outside its workspace."""
    n = f".e2e-probe-{nonce}"
    site = subprocess.run([s.python, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                          capture_output=True, text=True, check=True).stdout.strip()
    dev = [["run_directory", "create", f"{s.out}/{n}-run-directory"],
           ["run_directory_canary", "read", f"{s.out}/RUN.started.json"],
           ["kernel_directory", "create", f"{s.kernel}/aisef2/{n}-kernel"],
           ["interpreter_site_packages", "create", f"{site}/{n}-site"],
           ["client_directory", "create", f"{s.bin}/{n}-client"],
           ["git_directory", "create", f"{s.out}/repo/.git/{n}-git"],
           ["git_directory_head", "read", f"{s.out}/repo/.git/HEAD"],
           ["operator_home", "create", f"{s.home}/{n}-operator-home"],
           ["session_home", "create", "{home}/" + f"{n}-session-home"],
           ["tmp", "create", f"/tmp/{n}-tmp"],
           ["system_site_packages", "create", f"{SYSTEM_SITE}/{n}-system-site"]]
    rev = [["checkout_under_review", "create", "{cwd}/" + f"{n}-checkout"],
           ["run_directory", "create", f"{s.out}/{n}-run-directory-reviewer"]]
    return dev, rev


#: what the operator's uid cannot write anyway (the container's own permissions): a denial there is not bwrap's
CONTAINER_DENIES = ("system_site_packages",)


def s2(ctx: Ctx, confined: bool) -> Scenario:
    name, nonce = ("S2", "s2") if confined else ("S2c", "s2c")
    s = Scenario(ctx, name, "writes outside the allowed scope are refused" if confined
                 else "control: the same attempts without confinement", confinement=CONFINEMENT if confined else None,
                 isolated_kernel=True)
    dev, rev = attempts_for(s, nonce)
    s.script(attempts=dev, reviewer_attempts=rev)
    watched = {"kernel": s.kernel, "interpreter_site": pathlib.Path(dev[3][2]).parent, "client_directory": s.bin,
               "operator_home": s.home}
    before = {k: snapshot(v) for k, v in watched.items()}
    run = s.cli("run", ["run", *s.run_args(), "--out", "run", "--anchor-out", "anchor.txt"])
    rj = run["json"] or {}
    rec = s.record()
    after = {k: snapshot(v) for k, v in watched.items()}
    changed = {k: sorted(x for x in set(before[k]) | set(after[k]) if before[k].get(x) != after[k].get(x)) for k in watched}
    obs = s.observations()
    rows = {}
    for role, planned in (("developer", dev), ("reviewer", rev)):
        said = {k: evs[0] for k, evs in (obs.get(role) or {}).items() if k not in ("self", "work", "children")}
        for target, op, _ in planned:
            ev = said.get(target) or {}
            mount = ev.get("mount") or [None, None, None]
            host_has = os.path.exists(ev["path"]) if ev.get("op") == "create" and target != "checkout_under_review" else None
            # ENOENT is a sandbox's answer only where the host HAS the place (a create's parent directory, a read's
            # file): a path whose parent is absent on the host fails under any kernel, sandbox or not (review fix:
            # S2 on its own used to pass a mistyped path; S2c, the control, was the only thing that caught it)
            place = os.path.dirname(ev["path"]) if ev.get("op") == "create" else ev.get("path")
            place_on_host = os.path.exists(place) if place and target != "checkout_under_review" else None
            not_there = ev.get("ok") is False and ev.get("errname") == "ENOENT"
            rows[f"{role}:{target}"] = {"op": ev.get("op"), "path": ev.get("path"), "client_saw": (
                "created" if ev.get("ok") and op == "create" else "read" if ev.get("ok") else ev.get("errname")),
                "errno": ev.get("errno"), "client_mount_of_the_path": mount, "host_has_the_file": host_has,
                "host_has_the_place": place_on_host, "sha256_read": ev.get("sha256"), "recorded": bool(ev)}
            if confined:
                if target == "git_directory_head":      # by design: the session reads the run clone's HEAD
                    good = ev.get("ok") is True
                elif target == "run_directory_canary":
                    good = ev.get("ok") is False and (not not_there or bool(place_on_host))
                else:   # refused, or accepted only into the sandbox's own tmpfs — and the host never got the file
                    good = (bool(ev) and not host_has and (ev.get("ok") is False or mount[1] == "tmpfs")
                            and (not not_there or bool(place_on_host)))
            elif target in CONTAINER_DENIES:
                good = ev.get("ok") is False
            elif target == "run_directory_canary":     # the control reads the file itself, byte for byte
                good = ev.get("ok") is True and ev.get("sha256") == sha((s.out / "RUN.started.json").read_bytes())
            else:       # the control: the operator's uid reaches every one of them
                good = ev.get("ok") is True and host_has is not False
            s.ok(f"{role}:{target}", good, rows[f"{role}:{target}"])
    classes: dict[str, list[str]] = {}      # what the sessions were told, by kind: "refused" is not the only answer
    for k, v in rows.items():
        fs = v["client_mount_of_the_path"][1]
        classes.setdefault(f"{v['client_saw']}" + (f" (a {fs} mount)" if fs else ""), []).append(k)
    s.observed["what_the_session_was_told"] = classes
    top = sorted(os.listdir(s.out))
    from aisef2.app import run as R
    s.ok("kernel_that_ran_is_this_trees_kernel", rec.get("kernel_digest") == R.kernel_digest(),
         {"record": rec.get("kernel_digest"), "tree": R.kernel_digest(), "ran_from": str(s.kernel), "interpreter": s.python})
    if confined:
        s.ok("controller_view_nothing_changed_on_the_host", not any(changed.values())
             and not any(x.startswith(".e2e-probe-") for x in top) and set(top) <= EXPECTED_RUN_DIR,
             {"entries_added_or_changed": changed, "run_directory_listing": top,
              "watched": {k: f"{len(v)} entries" for k, v in before.items()}})
        rsess = rec.get("sessions") or []
        s.ok("legitimate_work_landed_and_run_completes_as_S1", run["exit"] == 0 and rj.get("delivery_verdict") == "PASS"
             and rj.get("story_outcomes") == {"S1": ["COMMIT"]} and all(x.get("exit") == 0 for x in rsess),
             {"exit": run["exit"], "delivery_verdict": rj.get("delivery_verdict"), "story_outcomes": rj.get("story_outcomes"),
              "sessions": [(x.get("role"), x.get("exit"), x.get("confinement")) for x in rsess]})
        ver = s.cli("verify", ["run", "--verify", *s.project("--out", "run", "--expect-anchor", rj.get("evidence_anchor", ""))])
        s.ok("verify_with_the_anchor_is_VERIFIED", ver["exit"] == 0 and (ver["json"] or {}).get("verdict") == "VERIFIED",
             {"exit": ver["exit"], "problems": (ver["json"] or {}).get("problems")})
    else:
        s.ok("control_the_controller_view_sees_every_write", all(changed[k] for k in ("kernel", "interpreter_site",
                                                                                     "client_directory", "operator_home"))
             and any(x.startswith(".e2e-probe-") for x in top),
             {"entries_added_or_changed": changed, "run_directory_listing": top})
        seen = [e["data"].get("detail") for e in journal_events(s.out)
                if e["type"] == "provider/result" and f".e2e-probe-{nonce}-checkout" in str(e["data"].get("detail"))]
        s.ok("control_the_kernel_itself_noticed_the_reviewers_write", bool(seen) and rj.get("delivery_verdict") == "FAIL",
             {"journal_provider_result": seen[:1], "exit": run["exit"], "delivery_verdict": rj.get("delivery_verdict"),
              "story_outcomes": rj.get("story_outcomes"), "story_errors": rec.get("story_errors")})
    s.facts = {"run_exit": run["exit"], "delivery_verdict": rj.get("delivery_verdict"), "story_outcomes": rj.get("story_outcomes"),
               "attempts": {k: [v["client_saw"], v["host_has_the_file"], v["client_mount_of_the_path"][1:]]
                            for k, v in rows.items()},
               "changed_on_the_host": {k: len(v) for k, v in changed.items()}, "kernel_digest": rec.get("kernel_digest")}
    s.volatile = {"evidence_anchor": rj.get("evidence_anchor")}
    return s


def s2b(ctx: Ctx, name: str, title: str, confinement: dict, expect: str, home_in_client_dir: bool = False) -> Scenario:
    s = Scenario(ctx, name, title, confinement=confinement)
    if home_in_client_dir:      # the operator's HOME lies inside the client's own directory: bound read-only, it would show HOME
        (s.bin / "home").mkdir()
        s.env["HOME"] = str(s.bin / "home")
    before = len(ctx.provider.log)
    chk = s.cli("check", ["run", "--check", *s.run_args()])
    cj = chk["json"] or {}
    problems = (cj.get("confinement") or {}).get("problems") or []
    s.ok("check_is_not_ready", chk["exit"] == 2 and cj.get("ready") is False and any(expect in x for x in problems),
         {"exit": chk["exit"], "ready": cj.get("ready"), "problems": problems})
    run = s.cli("run", ["run", *s.run_args(), "--out", "run"])
    rec = s.record() if (s.out / "RUN.json").is_file() else {}
    rconf = rec.get("confinement") or {}
    s.ok("run_refused_exit_2_with_the_cause", run["exit"] == 2 and "refused" in run["stderr"] and expect in run["stderr"],
         {"exit": run["exit"], "stderr": run["stderr"][:600], "stdout": run["stdout"][:200]})
    s.ok("record_names_the_stage_and_the_problems", rec.get("stage") == "confinement" and any(expect in x for x in rconf.get("problems") or [])
         and (rec.get("failure") or {}).get("type") == "RunRefused" and rec.get("delivery_verdict") == "NOT_REACHED",
         {"stage": rec.get("stage"), "confinement.problems": rconf.get("problems"), "failure": rec.get("failure"),
          "delivery_verdict": rec.get("delivery_verdict"), "journal": rec.get("journal")})
    started = sorted(p.name for p in s.out.iterdir()) if s.out.is_dir() else []
    s.ok("nothing_started_no_provider_request_no_session", len(ctx.provider.log) == before and "sessions" not in started
         and "preflight" not in started and rec.get("journal") is None and not rec.get("sessions"),
         {"provider_requests_seen": len(ctx.provider.log) - before, "run_directory_listing": started,
          "sessions_in_record": rec.get("sessions"), "preflight_in_record": "preflight" in rec})
    s.facts = {"check_exit": chk["exit"], "run_exit": run["exit"], "stage": rec.get("stage"), "problems": rconf.get("problems"),
               "provider_requests": len(ctx.provider.log) - before, "run_directory_listing": started}
    return s


def children_scenario(ctx: Ctx, name: str, title: str, *, confined: bool, legit: bool, hang_s: int, timeout_s: float) -> Scenario:
    marker = f"e2e-{name}-{sha(name.encode())[:8]}"
    s = Scenario(ctx, name, title, confinement=CONFINEMENT if confined else None, children=marker, legit=legit,
                 hang_s=hang_s, developer_timeout_s=timeout_s)
    pre = processes_with(marker)
    with Watch(marker, "developer S1") as watch:
        run = s.cli("run", ["run", *s.run_args(), "--out", "run"])
    line = watch.timeline()
    rj = run["json"] or {}
    rec = s.record()
    first = processes_with(marker)
    again = first
    for _ in range(30):     # a process still being torn down is looked at again; one alive after 3 s counts
        if not again:
            break
        time.sleep(0.1)
        again = processes_with(marker)
    kids = {}
    for evs in s.observations().values():
        for ev in evs.get("children", []):
            kids = ev
    dev = [x for x in rec.get("sessions") or [] if x.get("role") == "developer"]
    s.ok("marker_unique_before_the_run", pre == [], {"processes_with_the_marker_before": pre, "marker": marker})
    s.ok("children_were_alive_in_the_session", set((kids.get("alive") or {})) == {"background", "grandchild", "setsid"},
         {"observed_by_the_client": kids})
    s.facts = {"run_exit": run["exit"], "delivery_verdict": rj.get("delivery_verdict"), "story_outcomes": rj.get("story_outcomes"),
               "story_errors": [e["error"].split(":")[0] for e in rec.get("story_errors") or []],
               "developer_sessions": [(x.get("exit"), x.get("timed_out"), x.get("stopped")) for x in dev],
               "alive_after_cli_first_look": len(first), "alive_after_3s": len(again),
               "survivors": sorted(d["last_arg"].rsplit("-", 1)[1] for d in again),
               "session_windows": line["session_windows"],
               "polls_with_children_after_the_session_was_gone_is_zero":
                   line["polls_with_children_after_the_session_was_gone"] == 0}
    s.volatile = {"session_seconds": [x.get("seconds") for x in dev], "timeline": line}
    detail = {"run_exit": run["exit"], "delivery_verdict": rj.get("delivery_verdict"), "story_outcomes": rj.get("story_outcomes"),
              "story_errors": rec.get("story_errors"), "developer_sessions": [
                  {k: x.get(k) for k in ("exit", "timed_out", "stopped", "error", "seconds", "turns", "confinement")} for x in dev],
              "processes_alive_first_look": first, "processes_alive_after_re_looks": again}
    if confined and not hang_s:
        s.ok("run_completes_session_exit_0", run["exit"] == 0 and rj.get("delivery_verdict") == "PASS"
             and all(x.get("exit") == 0 and not x.get("timed_out") for x in dev), detail)
    elif confined:
        s.ok("session_timed_out_and_the_kernels_teardown_ran", bool(dev) and all(
            x.get("timed_out") is True and x.get("exit") is None and (x.get("seconds") or 0) >= timeout_s for x in dev)
             and line["session_windows"] == len(dev), {**detail, "timeout_s": timeout_s, "client_slept_s": hang_s})
    if confined:
        s.ok("no_child_alive_after_the_cli_returned", again == [] and first == [],
             {"first_look": first, "after_re_looks": again})
        s.ok("children_died_with_their_session_not_later", line["children_first_seen_s"] is not None
             and line["polls_with_children_after_the_session_was_gone"] == 0 and line["session_windows"] >= 1,
             {"watch_every_20ms_while_the_cli_ran": line})
        s.ok("no_residual_reported_by_the_kernel", not any("Range" in str(e.get("error")) for e in rec.get("story_errors") or [])
             and not any("Range" in str(o) for v in (rec.get("story_outcomes") or {}).values() for o in v),
             {"story_errors": rec.get("story_errors"), "story_outcomes": rec.get("story_outcomes"),
              "session_record_fields": sorted(dev[0]) if dev else None})
    else:
        gone = {"background", "grandchild"}
        survivors = {d["last_arg"].rsplit("-", 1)[1] for d in again}
        s.ok("control_the_setsid_child_outlives_the_cli", "setsid" in survivors and not (survivors & gone), detail)
        s.ok("control_the_child_is_seen_after_its_session_is_gone", line["polls_with_children_after_the_session_was_gone"] > 0,
             {"watch_every_20ms_while_the_cli_ran": line})
        s.ok("control_the_kernel_reports_the_escape", any("RangeEscaped" in str(e.get("error")) for e in rec.get("story_errors") or []),
             {"story_errors": rec.get("story_errors"), "story_outcomes": rec.get("story_outcomes")})
    return s


def s4(ctx: Ctx, base: Scenario) -> Scenario:
    s = Scenario(ctx, "S4", "evidence and anchor, on copies of S1's run directory", confinement=None)
    from aisef2.app import run as R
    src = base.out
    anchor = (base.dir / "anchor.txt").read_text().strip()
    original = snapshot(src)

    def verify(tag: str, out: pathlib.Path, expect: str | None) -> dict:
        args = ["run", "--verify", *s.project("--out", str(out))] + (["--expect-anchor", expect] if expect else [])
        r = s.cli(tag, args)
        return {"exit": r["exit"], "verdict": (r["json"] or {}).get("verdict"), "problems": (r["json"] or {}).get("problems"),
                "delivery_verdict": (r["json"] or {}).get("delivery_verdict"), "stderr": r["stderr"][:300]}

    def copy(tag: str) -> pathlib.Path:
        dst = s.dir / f"copy-{tag}"
        shutil.copytree(src, dst, symlinks=True)
        return dst

    def rebind(d: pathlib.Path) -> None:
        (d / "EVIDENCE.json").write_text(json.dumps(R.evidence_manifest(d), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    right = verify("original-right-anchor", src, anchor)
    s.ok("original_with_the_right_anchor_VERIFIED", right["exit"] == 0 and right["verdict"] == "VERIFIED", right)
    wrong_anchor = ("0" if anchor[0] != "0" else "1") + anchor[1:]
    wrong = verify("original-wrong-anchor", src, wrong_anchor)
    s.ok("original_with_a_wrong_anchor_REFUTED", wrong["exit"] == 1 and wrong["verdict"] == "REFUTED"
         and any("evidence anchor" in p for p in wrong["problems"] or []), {**wrong, "given": wrong_anchor, "right": anchor})
    stream = "sessions/" + next(n for n in base.streams() if ".developer." in n)
    c1 = copy("stream-byte")
    data = (c1 / stream).read_bytes()
    i = next(k for k, b in enumerate(data) if 0x30 <= b <= 0x38)       # one digit, raised by one: still JSON
    (c1 / stream).write_bytes(data[:i] + bytes([data[i] + 1]) + data[i + 1:])
    v1 = verify("stream-byte", c1, anchor)
    s.ok("one_byte_of_a_session_stream_changed_REFUTED_naming_the_file", v1["exit"] == 1 and v1["verdict"] == "REFUTED"
         and any(stream in p for p in v1["problems"] or []), {**v1, "byte_offset": i, "from": chr(data[i]), "to": chr(data[i] + 1)})
    c2 = copy("verdict")
    txt = (c2 / "RUN.json").read_text(encoding="utf-8")
    (c2 / "RUN.json").write_text(txt.replace('"delivery_verdict": "PASS"', '"delivery_verdict": "FAIL"', 1), encoding="utf-8")
    v2 = verify("verdict", c2, anchor)
    s.ok("delivery_verdict_edited_REFUTED", v2["exit"] == 1 and v2["verdict"] == "REFUTED"
         and any("RUN.json" in p for p in v2["problems"] or []), v2)
    c3 = copy("verdict-rebound")
    (c3 / "RUN.json").write_text((c3 / "RUN.json").read_text(encoding="utf-8").replace(
        '"delivery_verdict": "PASS"', '"delivery_verdict": "FAIL"', 1), encoding="utf-8")
    rebind(c3)
    v3a, v3b = verify("verdict-rebound-anchor", c3, anchor), verify("verdict-rebound-no-anchor", c3, None)
    s.ok("verdict_edited_and_manifest_regenerated_REFUTED_with_the_anchor", v3a["exit"] == 1 and v3a["verdict"] == "REFUTED"
         and any("evidence anchor" in p for p in v3a["problems"] or []), v3a)
    s.ok("verdict_edited_and_manifest_regenerated_REFUTED_by_the_journal_alone", v3b["exit"] == 1 and v3b["verdict"] == "REFUTED"
         and any("journal re-derives" in p for p in v3b["problems"] or []), v3b)
    c4 = copy("stream-rebound")
    d4 = (c4 / stream).read_bytes()
    (c4 / stream).write_bytes(d4[:i] + bytes([d4[i] + 1]) + d4[i + 1:])
    rebind(c4)
    v4a, v4b = verify("stream-rebound-anchor", c4, anchor), verify("stream-rebound-no-anchor", c4, None)
    s.ok("stream_changed_and_manifest_regenerated_REFUTED_with_the_anchor", v4a["exit"] == 1 and v4a["verdict"] == "REFUTED"
         and any("evidence anchor" in p for p in v4a["problems"] or []), v4a)
    s.observed["a_stream_changed_and_the_manifest_regenerated_verified_without_an_anchor"] = {
        **v4b, "note": "not an assertion: without an anchor, verification proves consistency, not authenticity (the "
                       "docstring of aisef2/app/verify.py); the check above, with the anchor, is the one that holds"}
    s.ok("the_original_run_directory_is_unchanged", snapshot(src) == original, {"entries": len(original)})
    s.facts = {"right": [right["exit"], right["verdict"]], "wrong": [wrong["exit"], wrong["verdict"]],
               "stream_byte": [v1["exit"], v1["verdict"]], "verdict": [v2["exit"], v2["verdict"]],
               "verdict_rebound_anchor": [v3a["exit"], v3a["verdict"]], "verdict_rebound_alone": [v3b["exit"], v3b["verdict"]],
               "stream_rebound_anchor": [v4a["exit"], v4a["verdict"]], "stream_rebound_alone": [v4b["exit"], v4b["verdict"]]}
    return s


def proofs(ctx: Ctx, s1_: Scenario | None) -> list[dict]:
    if s1_ is None:
        return []
    rec = s1_.record()
    run_step = next(x for x in s1_.cli_steps if x["tag"] == "run")
    ver = next(x for x in s1_.cli_steps if x["tag"] == "verify")
    conf = rec.get("confinement") or {}
    dev = [x for x in rec.get("sessions") or [] if x.get("role") == "developer"]
    return [
        {"segment": "CLI -> aisef2/app/cli.py::run", "field": "stdout of `python3 -B -m aisef run ...`: keys delivery_verdict, "
         "evidence_anchor, record", "value": {k: (run_step["json"] or {}).get(k) for k in ("delivery_verdict", "record")}},
        {"segment": "cli.run -> run.execute (the record)", "field": "RUN.json format / stage / kernel_digest",
         "value": {"format": rec.get("format"), "stage": rec.get("stage"), "kernel_digest": rec.get("kernel_digest")}},
        {"segment": "run.execute -> confine.measure (before the first provider request)", "field":
         "RUN.json confinement.{bwrap,bwrap_version,bwrap_sha256,argv[0],problems} and <out>/confinement/canary mtime < "
         "first provider request", "value": {k: conf.get(k) for k in ("bwrap", "bwrap_version", "bwrap_sha256", "problems")}
         | {"argv_0": (conf.get("argv") or [None])[0]}},
        {"segment": "run.execute -> preflight against the loopback provider", "field": "RUN.json preflight.verdict, accounting",
         "value": {"verdict": (rec.get("preflight") or {}).get("verdict"), "accounting": (rec.get("preflight") or {}).get("accounting")}},
        {"segment": "adapters.Developer/Reviewer -> client.session -> confine.wrap -> bwrap", "field":
         "RUN.json sessions[].confinement; the client's own /proc/1/cmdline equals confine.argv (S1 check "
         "*_ran_inside_bwrap_as_pid_1_with_the_kernels_argv)",
         "value": [x.get("confinement") for x in rec.get("sessions") or []]},
        {"segment": "story_runner -> merge (commit by the kernel, the git directory read-only to the session)", "field":
         "RUN.json story_outcomes, final_main, sessions[developer].developer_committed_itself",
         "value": {"story_outcomes": rec.get("story_outcomes"), "final_main": rec.get("final_main"),
                   "developer_committed_itself": [x.get("developer_committed_itself") for x in dev]}},
        {"segment": "cli --verify -> aisef2/app/verify.py::verify", "field": "stdout verdict, journal_events, evidence_anchor, notes",
         "value": {k: (ver["json"] or {}).get(k) for k in ("verdict", "journal_events", "evidence_anchor", "notes")}}]


def tar_evidence(work: pathlib.Path) -> str:
    """The run's evidence files (not the clones, the work trees, the interpreters or the kernel copies), base64 of a
    tar.gz: the only way out of a container that has no writable host mount."""
    skip = {"repo", "work", "test-python", "kernel", "venv", ".git", "__pycache__"}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for d, dirs, files in os.walk(work):
            dirs[:] = sorted(x for x in dirs if x not in skip and not x.startswith("copy-")
                             and not pathlib.Path(d, x).is_symlink())
            for f in sorted(files):
                p = pathlib.Path(d, f)
                if p.is_file() and not p.is_symlink() and p.stat().st_size < 2_000_000:
                    tf.add(p, arcname=p.relative_to(work).as_posix(), recursive=False)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def run_all(args: argparse.Namespace) -> int:
    ctx = Ctx(pathlib.Path(args.work))
    env = environment(ctx)
    ctx.build_project()
    wanted = (args.only.split(",") if args.only else
              ["S2b-hardened"] if args.profile == "hardened" else
              ["S1", "S2", "S2c", "S2b-readonly", "S2b-missing", "S2b-not-executable", "S2b-client-holds-home",
               "S3", "S3t", "S3c", "S4"])
    done: dict[str, Scenario] = {}
    plan = {
        "S1": lambda: s1(ctx),
        "S2": lambda: s2(ctx, True),
        "S2c": lambda: s2(ctx, False),
        "S2b-readonly": lambda: s2b(ctx, "S2b-readonly", "refused: read_only names a path that does not exist",
                                    {**CONFINEMENT, "read_only": ["/no/such/e2e-path"]}, "do not exist"),
        "S2b-missing": lambda: s2b(ctx, "S2b-missing", "refused: bubblewrap is not at the given path",
                                   {**CONFINEMENT, "bwrap": "/usr/bin/bwrap-e2e-absent"}, "not an executable file"),
        "S2b-not-executable": lambda: s2b(ctx, "S2b-not-executable", "refused: the given bubblewrap is not executable",
                                          {**CONFINEMENT, "bwrap": str(ctx.work / "project" / "not-bwrap")},
                                          "not an executable file"),
        "S2b-client-holds-home": lambda: s2b(ctx, "S2b-client-holds-home", "refused: the client's directory would expose HOME",
                                             CONFINEMENT, "holds HOME", home_in_client_dir=True),
        "S2b-hardened": lambda: s2b(ctx, "S2b-hardened", "refused: the container's own boundary stops bubblewrap",
                                    CONFINEMENT, "did not run the probe"),
        "S3": lambda: children_scenario(ctx, "S3", "children of a confined session", confined=True, legit=True, hang_s=0,
                                        timeout_s=60),
        "S3t": lambda: children_scenario(ctx, "S3t", "children, the session times out (the kernel's teardown)",
                                         confined=True, legit=False, hang_s=120, timeout_s=5),
        "S3c": lambda: children_scenario(ctx, "S3c", "control: children without confinement", confined=False, legit=True,
                                         hang_s=0, timeout_s=60),
        "S4": lambda: s4(ctx, done["S1"]),
    }
    for name in wanted:
        if name == "S4" and "S1" not in done:
            continue
        try:
            done[name] = plan[name]()
        except Exception:   # noqa: BLE001 — a scenario that broke is a finding with its traceback, never a silent gap
            sc = next((x for x in reversed(ctx.scenarios) if x.name == name), None)
            if sc is None:
                continue
            sc.ok("scenario_ran_to_its_end", False, {"traceback": traceback.format_exc()[-3000:]})
            done[name] = sc
        print(f"[{name}] {'PASS' if all(c['passed'] for c in done[name].checks) else 'FAIL'}", file=sys.stderr, flush=True)
    result = {"format": "aisef-v21-e2e-linux/1", "profile": args.profile, "environment": env,
              "project_steps": [{k: x[k] for k in ("argv", "exit")} for x in ctx.project_steps],
              "scenarios": [s.summary() for s in ctx.scenarios],
              "code_path_proofs": proofs(ctx, done.get("S1")),
              "provider_log_total": len(ctx.provider.log)}
    result["passed"] = all(x["passed"] for x in result["scenarios"]) and bool(result["scenarios"])
    print("@@E2E-RESULT-BEGIN")
    print(json.dumps(result, indent=1, sort_keys=True, default=str))
    print("@@E2E-RESULT-END")
    print("@@E2E-TAR-BEGIN")
    print(tar_evidence(ctx.work))
    print("@@E2E-TAR-END")
    return 0 if result["passed"] else 1


def compare(a: str, b: str) -> int:
    """What differs between two results of the driver: a check's verdict, a stable fact. Volatile values (anchors,
    commit ids, timings) are listed as differing, never as failures."""
    A, B = jread(pathlib.Path(a)), jread(pathlib.Path(b))
    diffs, volatile = [], []
    sa = {s["scenario"]: s for s in A["scenarios"]}
    sb = {s["scenario"]: s for s in B["scenarios"]}
    for name in sorted(set(sa) | set(sb)):
        if name not in sa or name not in sb:
            diffs.append({"scenario": name, "what": "present in only one run"})
            continue
        ca = {c["name"]: c["passed"] for c in sa[name]["checks"]}
        cb = {c["name"]: c["passed"] for c in sb[name]["checks"]}
        diffs += [{"scenario": name, "check": k, "a": ca.get(k), "b": cb.get(k)} for k in sorted(set(ca) | set(cb))
                  if ca.get(k) != cb.get(k)]
        fa, fb = sa[name]["facts"], sb[name]["facts"]
        diffs += [{"scenario": name, "fact": k, "a": fa.get(k), "b": fb.get(k)} for k in sorted(set(fa) | set(fb))
                  if fa.get(k) != fb.get(k)]
        va, vb = sa[name]["volatile"], sb[name]["volatile"]
        volatile += [{"scenario": name, "volatile": k, "a": va.get(k), "b": vb.get(k)} for k in sorted(set(va) | set(vb))
                     if va.get(k) != vb.get(k)]
    print(json.dumps({"identical_checks_and_facts": not diffs, "differences": diffs, "volatile_values_that_differ": volatile},
                     indent=1, sort_keys=True, default=str))
    return 0 if not diffs else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--profile", choices=("X1", "hardened"), required=True)
    r.add_argument("--work", default="/tmp/e2e")
    r.add_argument("--only")
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    a = ap.parse_args()
    return run_all(a) if a.cmd == "run" else compare(a.a, a.b)


if __name__ == "__main__":
    sys.exit(main())
