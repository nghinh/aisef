"""W1 driver — one fresh LedgerLock run per invocation series, exactly per the P20 plan and its sanity-check
additions. Every phase writes into closure-evidence/hardening/w1/run-<n>/ and NEVER edits AISEF or the project's
state files (the only project writes are the ones the plan names: the guard-plugin commit and the ARB-1 re-approval,
both through the candidate's own CLI).

  prepare       environment + candidate identity (the wheel's aisef, not the checkout); doctor; gates; guard plugin
                compiled with the candidate's aisef and committed (P20 addition — a story worktree is a fresh checkout)
  kernel-first  `aisef run --client opencode` with NO re-approval and NO --force: the kernel must refuse the STALE
                readiness before any agent call (ARB-1 "kernel path first"); a run that proceeds is a P0 → STOP
  approve       `aisef approve readiness --note ARB-1` for the byte-identical content; gates measured before/after
  run           `aisef run --client opencode` in its own process group under a watcher: SIGTERM to the group at the two
                predeclared wave boundaries (forced resumes), `aisef run` started again, survivors measured; a stall
                watchdog; every kill and exit recorded
  finish        status / gates / cost / run.log / journal / evidence / replay manifest / drift archived; the hidden oracle
                (sha pinned by ORACLE-INDEPENDENCE.json) run on a clean clone of master; W1-LEDGERLOCK-<n>.json written

    python3 closure-evidence/hardening/w1/w1_driver.py --run 1 --project ~/Downloads/projects/w1-run-1 \
        --aisef <run venv>/bin/aisef --python <run venv>/bin/python --oracle-python <oracle venv>/bin/python \
        --freeze closure-evidence/hardening/P19-FREEZE.json --phase all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MARKERS = ["wave=EPIC-01/w3 DONE", "wave=EPIC-03/w1 DONE"]  # P20 procedure 3: the forced-resume boundaries
EXPECTED = {"client": "opencode", "opencode_version": "1.18.31", "model": "9router/mycombo", "stories": 16, "fresh_root": "8ff9f13",
            "requirements_sha256": "3a6a99959bbc6cf39c4d4afa9c2de222925fdcaad30aaf3fa2d04ee446597ecc",
            "sandbox_image": "aisef-verify-python:b2c7afff2aed"}   # owner item 9: asserted mechanically BEFORE the first model call
STALL_S = 2 * 3600
ARB1_NOTE = ("ARB-1 OWNER_APPROVED_HASH_MIGRATION_REAPPROVAL: re-approval for byte-identical content after the hash-method change "
             "(SS-55 verifier-config digest); not a waiver; kernel refusal recorded first; conditions measured in "
             "closure-evidence/hardening/w1/ARBITRATION-PREDECLARED.json")


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Driver:
    def __init__(self, a):
        self.a = a
        self.project = Path(a.project).expanduser().resolve()
        self.art = self.project / "_bmad-output"
        self.run_dir = HERE / f"run-{a.run}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.rec_path = self.run_dir / "driver.json"
        self.rec = json.loads(self.rec_path.read_text(encoding="utf-8")) if self.rec_path.is_file() else {"run": a.run, "project": str(self.project), "phases": {}}
        self.log = open(self.run_dir / "driver.log", "a", encoding="utf-8")

    # ---- plumbing ------------------------------------------------------------------------------------------------
    def say(self, msg: str) -> None:
        line = f"[{now()}] {msg}"
        print(line, flush=True)
        self.log.write(line + "\n")
        self.log.flush()

    def save(self) -> None:
        self.rec["updated"] = now()
        self.rec_path.write_text(json.dumps(self.rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def env(self) -> dict:
        e = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        return e

    def cli(self, *args: str, timeout: int = 900, cwd: Path | None = None, save_as: str | None = None) -> dict:
        t0 = time.time()
        r = subprocess.run([self.a.aisef, *args], cwd=str(cwd or self.project), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=self.env())
        out = {"cmd": ["aisef", *args], "exit": r.returncode, "seconds": round(time.time() - t0, 1),
               "stdout_tail": r.stdout[-3000:], "stderr_tail": r.stderr[-1500:]}
        if save_as:
            (self.run_dir / save_as).write_text(r.stdout + ("\n--- stderr ---\n" + r.stderr if r.stderr else ""), encoding="utf-8")
        return out

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.project), *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()

    def gates(self) -> dict:
        r = self.cli("gates", timeout=120)
        out = {}
        for ln in r["stdout_tail"].splitlines():
            m = re.match(r"\s*\S+\s+([a-z-]+)\s+(approved|stale|pending|rejected|\w+)", ln)
            if m and m.group(1) in ("prd", "architecture", "ux-spec", "epics", "stories", "mockups", "readiness", "pre-deploy", "improve"):
                out[m.group(1)] = m.group(2)
        return out

    def agent_starts(self) -> int:
        p = self.art / "run.log"
        return p.read_text(encoding="utf-8", errors="replace").count(" agent START") if p.is_file() else 0

    def story_evidence(self) -> list[str]:
        d = self.art / "evidence"
        return sorted(p.name for p in d.glob("STORY-*.jsonl")) if d.is_dir() else []

    def processes(self) -> list[dict]:
        ps = subprocess.run(["ps", "-eo", "pid=,pgid=,etime=,command="], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        out = []
        for ln in ps.splitlines():
            parts = ln.split(None, 3)
            if len(parts) == 4 and ("opencode" in parts[3] or str(self.project) in parts[3] or "aisef" in parts[3]) and "w1_driver" not in parts[3]:
                out.append({"pid": int(parts[0]), "pgid": int(parts[1]), "etime": parts[2], "command": parts[3][:160]})
        return out

    # ---- phases -------------------------------------------------------------------------------------------------
    def prepare(self) -> bool:
        self.say("phase prepare")
        P = {"at": now()}
        P["aisef_version"] = self.cli("--version", timeout=60)["stdout_tail"].strip()
        ident = subprocess.run([self.a.python, "-c", "import aisef, sys; print(aisef.__file__); print(sys.prefix)"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               cwd=str(self.run_dir), env=self.env()).stdout.split()
        P["aisef_file"] = ident[0] if ident else ""
        P["aisef_from_the_wheel_not_the_checkout"] = bool(ident) and "site-packages" in ident[0] and str(REPO / "aisef") not in ident[0]
        P["venv_packages"] = subprocess.run([self.a.python, "-m", "pip", "list", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=self.env()).stdout[:2000]
        if self.a.freeze:
            P["freeze"] = json.loads(Path(self.a.freeze).read_text(encoding="utf-8"))
        P["project_git"] = {"head": self.git("rev-parse", "HEAD"), "branch": self.git("rev-parse", "--abbrev-ref", "HEAD"),
                            "status": self.git("status", "--porcelain").splitlines(), "log": self.git("log", "--oneline", "-5").splitlines()}
        P["config"] = json.loads((self.project / ".ai/config.json").read_text(encoding="utf-8"))
        P["opencode_version"] = subprocess.run(["opencode", "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
        P["opencode_binary"] = shutil.which("opencode")
        img = P["config"].get("sandbox.image", "")
        P["docker_image"] = {"name": img, "id": subprocess.run(["docker", "image", "inspect", img, "--format", "{{.Id}}"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()}
        P["doctor"] = self.cli("doctor", timeout=300, save_as="doctor.txt")
        P["doctor_red"] = [ln.strip() for ln in P["doctor"]["stdout_tail"].splitlines() if ln.strip().startswith("✗")]
        indep = json.loads((HERE / "ORACLE-INDEPENDENCE.json").read_text(encoding="utf-8"))
        P["oracle"] = {"sha256_now": sha(HERE / "oracle/test_oracle.py"), "sha256_pinned": indep["oracle"]["sha256"], "independence_verdict": indep["verdict"]}
        P["oracle_ok"] = P["oracle"]["sha256_now"] == P["oracle"]["sha256_pinned"] and indep["verdict"] == "PASS"
        # guard plugin (P20 addition): compile with the CANDIDATE's aisef and commit — a story worktree is a fresh checkout
        plugin = self.project / ".opencode/plugin/aisef-guard.ts"
        tracked = subprocess.run(["git", "-C", str(self.project), "ls-files", "--error-unmatch", str(plugin)], capture_output=True).returncode == 0
        if not tracked:
            P["compile"] = self.cli("compile", "--client", "opencode", "--bin", self.a.aisef, timeout=300, save_as="compile.txt")
            self.git("add", ".opencode", "_bmad-output/compile-report.json")
            self.git("commit", "-q", "-m", f"w1-run-{self.a.run}: guard plugin compiled by {P['aisef_version']} — a story worktree is a fresh checkout (P20 preparation, not an AISEF change)")
            P["guard_commit"] = self.git("rev-parse", "HEAD")
        P["guard_plugin"] = {"tracked_now": subprocess.run(["git", "-C", str(self.project), "ls-files", "--error-unmatch", str(plugin)], capture_output=True).returncode == 0,
                             "sha256": sha(plugin) if plugin.is_file() else None,
                             "bin_line": next((ln.strip() for ln in plugin.read_text(encoding="utf-8").splitlines() if "BIN" in ln), None) if plugin.is_file() else None,
                             "compile_report": json.loads((self.art / "compile-report.json").read_text(encoding="utf-8")) if (self.art / "compile-report.json").is_file() else None}
        # fresh-trunk topology (rehearsal finding): the run copy's trunk must be the FRESH plan state — 8ff9f13 plus the
        # named preparation commits only — with no run-2 delivery on it and no remote to fetch one from
        after = [ln for ln in self.git("log", "--oneline", "8ff9f13..master").splitlines() if ln.strip()]
        P["fresh_topology"] = {"head_branch": self.git("rev-parse", "--abbrev-ref", "HEAD"), "master": self.git("rev-parse", "master"),
                               "commits_after_8ff9f13": after, "ledgerlock_dir_absent_at_master": "ledgerlock" not in self.git("ls-tree", "--name-only", "master").split(),
                               "remotes": self.git("remote").split(), "branches": self.git("branch", "--list").replace("*", "").split()}
        t = P["fresh_topology"]
        P["fresh_topology_ok"] = t["head_branch"] == "master" and t["ledgerlock_dir_absent_at_master"] and not t["remotes"] and len(after) <= 3 \
            and all(("cost_cap" in ln or "guard plugin" in ln) for ln in after)
        # owner item 9 — W1 freshness preflight, every check mechanical; any failure STOPS before the first model call
        idx = json.loads((self.art / "stories.index.json").read_text(encoding="utf-8"))
        stories = idx["stories"] if isinstance(idx, dict) and "stories" in idx else idx
        req = self.project / "docs/requirements.md"
        model = subprocess.run([self.a.python, "-c", "from aisef.clients.opencode import configured_model; print(configured_model(%r))" % str(self.project)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(self.run_dir), env=self.env()).stdout.strip()
        status_text = self.cli("status", timeout=120)["stdout_tail"]
        plugin_bin = P["guard_plugin"]["bin_line"] or ""
        img_id = P["docker_image"]["id"]
        frozen_img = (P.get("freeze") or {}).get("docker_image_id")
        P["preflight"] = {
            "trunk_is_the_approved_fresh_root": t["head_branch"] == "master" and self.git("merge-base", "--is-ancestor", EXPECTED["fresh_root"], "master") == "" and t["ledgerlock_dir_absent_at_master"],
            "zero_prior_delivery_commits": all(("cost_cap" in ln or "guard plugin" in ln) for ln in after),
            "expected_story_count": len(stories) == EXPECTED["stories"],
            "expected_story_state_none_registered": "No stories registered" in status_text,
            "no_candidate_branches": t["branches"] == ["master"],
            "artifacts_match_frozen_requirements": req.is_file() and sha(req) == EXPECTED["requirements_sha256"],
            "client_is_opencode": EXPECTED["client"] == "opencode",
            "expected_opencode_version": P["opencode_version"] == EXPECTED["opencode_version"],
            "expected_model_route": model == EXPECTED["model"],
            "guard_plugin_bound_to_the_frozen_candidate": self.a.aisef in plugin_bin,
            "no_stale_story_worktrees": len(self.git("worktree", "list").splitlines()) == 1,
            "sandbox_image_declared": P["config"].get("sandbox.image") == EXPECTED["sandbox_image"],
            "sandbox_image_present": bool(img_id),
            "environment_identity_matches_freeze": (img_id == frozen_img) if frozen_img else "no freeze record given — not compared",
            "no_remotes": not t["remotes"],
        }
        P["preflight_measured"] = {"model": model, "opencode_version": P["opencode_version"], "plugin_bin": plugin_bin, "worktrees": self.git("worktree", "list").splitlines(),
                                   "stories": len(stories), "docker_image_id": img_id}
        P["preflight_ok"] = all(v is True or v == "no freeze record given — not compared" for v in P["preflight"].values())
        P["gates"] = self.gates()
        P["agent_starts_before"] = self.agent_starts()
        P["story_evidence_before"] = self.story_evidence()
        P["ok"] = P["aisef_from_the_wheel_not_the_checkout"] and P["oracle_ok"] and P["guard_plugin"]["tracked_now"] and P["gates"].get("readiness") == "stale" \
            and P["fresh_topology_ok"] and P["preflight_ok"] \
            and all(v == "approved" for g, v in P["gates"].items() if g not in ("readiness", "pre-deploy")) and not P["story_evidence_before"]
        self.rec["phases"]["prepare"] = P
        self.save()
        self.say(f"prepare ok={P['ok']} aisef={P['aisef_version']} wheel={P['aisef_from_the_wheel_not_the_checkout']} oracle={P['oracle_ok']} guard={P['guard_plugin']['tracked_now']} topology={P['fresh_topology_ok']} preflight={P['preflight_ok']} failed={[k for k, v in P['preflight'].items() if v is not True and not isinstance(v, str)]} gates={P['gates']} doctor_red={P['doctor_red']}")
        return P["ok"]

    def kernel_first(self) -> bool:
        self.say("phase kernel-first: aisef run with NO re-approval, NO --force")
        K = {"at": now(), "agent_starts_before": self.agent_starts(), "evidence_before": self.story_evidence(), "gates_before": self.gates()}
        K["run"] = self.cli("run", "--client", "opencode", timeout=900, save_as="kernel-first-run.txt")
        K["agent_starts_after"] = self.agent_starts()
        K["evidence_after"] = self.story_evidence()
        K["refused_on_readiness"] = K["run"]["exit"] != 0 and "readiness" in (K["run"]["stdout_tail"] + K["run"]["stderr_tail"])
        K["no_agent_call"] = K["agent_starts_after"] == K["agent_starts_before"] and K["evidence_after"] == K["evidence_before"]
        K["ok"] = K["refused_on_readiness"] and K["no_agent_call"]
        K["classification"] = "kernel refused the STALE gate before any agent call (ARB-1 kernel path first)" if K["ok"] else "P0: the kernel proceeded past a STALE readiness without --force — STOP W1"
        self.rec["phases"]["kernel_first"] = K
        self.save()
        self.say(f"kernel-first ok={K['ok']} exit={K['run']['exit']} {K['classification']}")
        return K["ok"]

    def approve(self) -> bool:
        self.say("phase approve: ARB-1 re-approval of readiness for byte-identical content")
        A = {"at": now(), "gates_before": self.gates()}
        A["approve"] = self.cli("approve", "readiness", "--note", ARB1_NOTE, timeout=120, save_as="approve.txt")
        A["gates_after"] = self.gates()
        rec = self.art / "approvals" / "readiness.json"
        A["approval_record"] = json.loads(rec.read_text(encoding="utf-8")) if rec.is_file() else None
        changed = {g for g in set(A["gates_before"]) | set(A["gates_after"]) if A["gates_before"].get(g) != A["gates_after"].get(g)}
        A["changed_gates"] = sorted(changed)
        A["ok"] = A["approve"]["exit"] == 0 and A["gates_after"].get("readiness") == "approved" and changed == {"readiness"}
        self.rec["phases"]["approve"] = A
        self.save()
        self.say(f"approve ok={A['ok']} changed={A['changed_gates']} gates={A['gates_after']}")
        return A["ok"]

    def run(self) -> bool:
        self.say("phase run")
        R = self.rec["phases"].setdefault("run", {"at": now(), "invocations": [], "resumes": [], "markers_pending": list(MARKERS)})
        runlog = self.art / "run.log"
        offset0 = runlog.stat().st_size if runlog.is_file() else 0
        R["runlog_offset_at_start"] = R.get("runlog_offset_at_start", offset0)
        k = len(R["invocations"])
        while True:
            k += 1
            out = open(self.run_dir / f"aisef-run-{k}.log", "a", encoding="utf-8")
            proc = subprocess.Popen([self.a.aisef, "run", "--client", "opencode"], cwd=str(self.project), stdout=out, stderr=subprocess.STDOUT,
                                    start_new_session=True, env=self.env())
            inv = {"k": k, "pid": proc.pid, "pgid": os.getpgid(proc.pid), "started": now(), "t0": time.time()}
            R["invocations"].append(inv)
            self.save()
            self.say(f"aisef run #{k} pid={proc.pid} pgid={inv['pgid']}")
            if k > 1:
                time.sleep(90)
                inv["survivors_90s_after_resume_start"] = [p for p in self.processes() if p["pgid"] != inv["pgid"] and "opencode" in p["command"]]
                self.save()
            last_sig, last_change = None, time.time()
            killed = None
            while proc.poll() is None:
                time.sleep(5)
                sig = (runlog.stat().st_size if runlog.is_file() else 0, (self.run_dir / f"aisef-run-{k}.log").stat().st_size)
                if sig != last_sig:
                    last_sig, last_change = sig, time.time()
                text = runlog.read_text(encoding="utf-8", errors="replace")[R["runlog_offset_at_start"]:] if runlog.is_file() else ""
                hit = next((m for m in R["markers_pending"] if m in text), None)
                if hit:
                    killed = {"marker": hit, "at": now(), "line": next((ln for ln in text.splitlines() if hit in ln), ""), "kind": "forced resume (P20 procedure 3)"}
                elif time.time() - last_change > STALL_S:
                    killed = {"marker": None, "at": now(), "kind": f"STALL: no log growth for {STALL_S}s — measured stop, reported"}
                if killed:
                    R["markers_pending"] = [m for m in R["markers_pending"] if m != killed["marker"]]
                    self.say(f"SIGTERM process group {inv['pgid']}: {killed}")
                    killed["processes_before"] = self.processes()
                    os.killpg(inv["pgid"], signal.SIGTERM)
                    t = time.time()
                    while proc.poll() is None and time.time() - t < 120:
                        time.sleep(2)
                    if proc.poll() is None:
                        os.killpg(inv["pgid"], signal.SIGKILL)
                        killed["sigkill_after_120s"] = True
                    time.sleep(5)
                    killed["exit"] = proc.poll()
                    killed["survivors_after_kill"] = [p for p in self.processes() if p["pid"] != proc.pid]
                    break
            out.close()
            inv["exit"] = proc.returncode
            inv["ended"] = now()
            inv["seconds"] = round(time.time() - inv["t0"], 1)
            inv["killed"] = killed
            tail = (self.run_dir / f"aisef-run-{k}.log").read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
            inv["stdout_tail"] = tail
            self.save()
            self.say(f"aisef run #{k} exit={proc.returncode} after {inv['seconds']}s killed={bool(killed)}")
            if killed and killed.get("marker"):
                R["resumes"].append({"after": killed["marker"], "kill": killed, "resume_invocation": k + 1})
                self.save()
                continue
            break
        R["ended"] = now()
        R["terminal_exit"] = R["invocations"][-1]["exit"]
        R["markers_not_reached"] = R["markers_pending"]
        R["runlog_lines_epic"] = [ln for ln in runlog.read_text(encoding="utf-8", errors="replace").splitlines() if "epic=" in ln or "wave=" in ln][-60:]
        R["ok"] = True
        self.save()
        return True

    def finish(self) -> bool:
        self.say("phase finish")
        F = {"at": now()}
        F["status"] = self.cli("status", timeout=300, save_as="status.txt")
        F["gates"] = self.gates()
        F["cost"] = self.cli("cost", "--out", str(self.run_dir / "cost.md"), timeout=300)
        F["project_git"] = {"head": self.git("rev-parse", "HEAD"), "branch": self.git("rev-parse", "--abbrev-ref", "HEAD"),
                            "branches": self.git("branch", "--list").split(), "status": self.git("status", "--porcelain").splitlines()[:40],
                            "master_log": self.git("log", "--oneline", "-40", "master").splitlines()}
        arch = self.run_dir / "artifacts"
        arch.mkdir(exist_ok=True)
        for name in ("run.log", "journal", "evidence", "replay", "approvals", "budget.json", "compile-report.json", "sprint-status.json"):
            src = self.art / name
            if src.is_dir():
                shutil.copytree(src, arch / name, dirs_exist_ok=True)
            elif src.is_file():
                shutil.copy(src, arch / name)
        F["drift_records"] = [str(p.relative_to(self.art)) for p in self.art.rglob("*.json") if "REPLAY_CONDITION" in p.name or "drift" in p.name.lower()]
        m = re.search(r"Progress: (\d+)/(\d+) stories done", F["status"]["stdout_tail"])
        F["progress"] = {"done": int(m.group(1)), "total": int(m.group(2))} if m else None
        F["stories"] = {}
        for ln in F["status"]["stdout_tail"].splitlines():
            mm = re.match(r"\s+(STORY-\d+-\d+)\s+(\w+)\s*(.*)", ln)
            if mm:
                F["stories"][mm.group(1)] = {"status": mm.group(2), "reason": mm.group(3)[:300]}
        # per-story terminal step from the journal (the framework's own record)
        for jf in sorted((self.art / "journal").glob("STORY-*.jsonl")) if (self.art / "journal").is_dir() else []:
            recs = [json.loads(l) for l in jf.read_text(encoding="utf-8").splitlines() if l.strip()]
            F["stories"].setdefault(jf.stem, {})["journal_last_step"] = recs[-1].get("step") if recs else None
            F["stories"][jf.stem]["journal_records"] = len(recs)
        # the hidden oracle on a clean clone of master (never the run's working tree)
        with tempfile.TemporaryDirectory() as td:
            deliv = Path(td) / "delivered"
            subprocess.run(["git", "clone", "--quiet", "--branch", "master", str(self.project), str(deliv)], check=True)
            F["delivered"] = {"master_head": subprocess.run(["git", "-C", str(deliv), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip(),
                              "has_package": (deliv / "ledgerlock").is_dir(), "files": sorted(str(p.relative_to(deliv)) for p in deliv.rglob("*.py") if ".git" not in p.parts)[:80]}
            obs = self.run_dir / "oracle-observations.jsonl"
            env = dict(self.env(), AISEF_W1_PROJECT=str(deliv), AISEF_W1_ORACLE_OBSERVATIONS=str(obs))
            r = subprocess.run([self.a.oracle_python, "-m", "pytest", str(HERE / "oracle/test_oracle.py"), "-q", "-rA", "-p", "no:cacheprovider", "--tb=short"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(HERE), timeout=1800)
            (self.run_dir / "oracle.txt").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
            res = {}
            for mm in re.finditer(r"^(PASSED|FAILED|ERROR|SKIPPED) (\S+)", r.stdout, re.M):
                res[mm.group(2).split("::", 1)[1] if "::" in mm.group(2) else mm.group(2)] = mm.group(1)
            F["oracle"] = {"sha256": sha(HERE / "oracle/test_oracle.py"), "exit": r.returncode, "results": res,
                           "observations": [json.loads(l) for l in obs.read_text(encoding="utf-8").splitlines()] if obs.is_file() else []}
        # exit criteria (SCALE-QUALIFICATION W1) — computed, not asserted
        fr_map = json.loads((HERE / "oracle-fr-map.json").read_text(encoding="utf-8")) if (HERE / "oracle-fr-map.json").is_file() else {}
        idx = json.loads((self.art / "stories.index.json").read_text(encoding="utf-8"))
        stories = idx["stories"] if isinstance(idx, dict) and "stories" in idx else idx
        covers = {s["id"]: s.get("covers", []) for s in (stories if isinstance(stories, list) else stories.values())}
        done = {sid for sid, s in F["stories"].items() if s.get("status") == "done"}
        complete = bool(F["progress"]) and F["progress"]["done"] == F["progress"]["total"]
        false_pass = []
        for test, verdict in F["oracle"]["results"].items():
            if verdict in ("PASSED", "SKIPPED"):
                continue
            frs = fr_map.get(test.split("::")[-1], [])
            owners = [sid for sid, c in covers.items() if any(fr in c for fr in frs)]
            if complete or (owners and all(o in done for o in owners)):
                false_pass.append({"test": test, "frs": frs, "stories_done": owners, "run_complete": complete})
        run = self.rec["phases"].get("run", {})
        F["exit_criteria"] = {
            "false_pass": false_pass, "false_pass_count": len(false_pass),
            "manual_state_repair": 0, "manual_state_repair_note": "the driver never writes _bmad-output; the only project writes are the guard commit and the ARB-1 re-approval through the CLI",
            "orphan_state": [k for k in run.get("resumes", []) if k["kill"].get("survivors_after_kill")],
            "drift_records": F["drift_records"], "oracle_ran": bool(F["oracle"]["results"]),
            "resumes_forced": len(run.get("resumes", [])), "markers_not_reached": run.get("markers_not_reached"),
            "stops": [ln for ln in run.get("runlog_lines_epic", []) if "STOPPED" in ln],
        }
        F["ok"] = bool(F["oracle"]["results"]) and F["progress"] is not None
        self.rec["phases"]["finish"] = F
        self.save()
        rec = {"run": self.a.run, "generated": now(), "candidate": self.rec["phases"].get("prepare", {}).get("freeze"),
               "aisef": {k: self.rec["phases"].get("prepare", {}).get(k) for k in ("aisef_version", "aisef_file", "opencode_version", "docker_image")},
               "arbitrations": [{"id": "ARB-1", "kernel_first": self.rec["phases"].get("kernel_first", {}).get("classification"),
                                 "approval": self.rec["phases"].get("approve", {}).get("approval_record")}],
               "phases": self.rec["phases"], "exit_criteria": F["exit_criteria"], "oracle": F["oracle"], "stories": F["stories"], "progress": F["progress"]}
        (HERE.parent / f"W1-LEDGERLOCK-{self.a.run}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        self.say(f"finish: progress={F['progress']} oracle={F['oracle']['results']} false_pass={len(false_pass)} → W1-LEDGERLOCK-{self.a.run}.json")
        return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--aisef", required=True, help="the CANDIDATE's console script (run venv)")
    ap.add_argument("--python", required=True, help="the run venv's python")
    ap.add_argument("--oracle-python", required=True)
    ap.add_argument("--freeze", default="", help="P19 freeze record (JSON)")
    ap.add_argument("--phase", default="all", choices=["all", "prepare", "kernel-first", "approve", "run", "finish"])
    a = ap.parse_args()
    d = Driver(a)
    order = ["prepare", "kernel-first", "approve", "run", "finish"] if a.phase == "all" else [a.phase]
    fn = {"prepare": d.prepare, "kernel-first": d.kernel_first, "approve": d.approve, "run": d.run, "finish": d.finish}
    for ph in order:
        if not fn[ph]():
            d.say(f"STOP at phase {ph} — see {d.rec_path}")
            return 1
    d.say("W1 driver complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
