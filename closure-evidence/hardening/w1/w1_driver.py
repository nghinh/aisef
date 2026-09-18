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
sys.path.insert(0, str(HERE))
REPO = HERE.parents[2]
MARKERS = ["wave=EPIC-01/w3 DONE", "wave=EPIC-03/w1 DONE"]  # P20 procedure 3: the forced-resume boundaries
EXPECTED = {"client": "opencode", "opencode_version": "1.18.31", "model": "9router/mycombo", "stories": 16, "fresh_root": "8ff9f13",
            "max_turns": 40,          # owner section 4: the same max-turn configuration in every qualified run
            "requirements_sha256": "3a6a99959bbc6cf39c4d4afa9c2de222925fdcaad30aaf3fa2d04ee446597ecc",
            }   # owner item 9: asserted mechanically BEFORE the first model call; the image comes from the frozen candidate
STALL_S = 2 * 3600
ARB1_NOTE = ("ARB-1 OWNER_APPROVED_HASH_MIGRATION_REAPPROVAL: re-approval for byte-identical content after the hash-method change "
             "(SS-55 verifier-config digest); not a waiver; kernel refusal recorded first; conditions measured in "
             "closure-evidence/hardening/w1/ARBITRATION-PREDECLARED.json")


#: The only commits a fresh run copy may carry after 8ff9f13 — the named preparation steps, nothing else.
PREPARATION_COMMITS = ("run.cost_cap_usd=80", "sandbox.image re-pinned to the frozen candidate", "guard plugin compiled by",
                       "execution profile PROFILE-")


def _is_preparation_commit(line: str) -> bool:
    subject = line.split(" ", 1)[1] if " " in line else ""
    return subject.startswith("w1-run-") and any(marker in subject for marker in PREPARATION_COMMITS)


# ---- oracle ownership model (owner decision "COMPLETE W1 RUNS 2-3", section 1) ---------------------------------------
# Pure so it can carry deterministic negative controls: tests/hardening/test_w1_oracle_ownership.py.
def _signal_group(pgid: int, sig, record: dict, label: str) -> bool:
    """Signal a process group, recording refusal instead of dying on it (SS-80)."""
    try:
        os.killpg(pgid, sig)
        return True
    except OSError as e:
        record[f"{label}_error"] = f"{type(e).__name__}: {e}"
        return False


def run_metrics(runlog: str, state: dict, covers: dict, fr_map: dict, oracle_results: dict) -> dict:
    """The per-run numbers the owner's report table asks for (section 10), measured from the run's own log and state.

    false BLOCK is the mirror of false pass: a story the framework did NOT complete although every hidden-oracle check
    that covers its requirements is green. It is only measurable for stories whose FRs some oracle check covers.
    """
    dev_done = re.findall(r"#(\d+) agent DONE ok=(\w+).*?turns=(\d+)", runlog)
    metrics = {
        "developer_agent_runs": len(dev_done),
        "developer_retries": sum(max((st.get("attempts") or 1) - 1, 0) for st in state.values()),
        "reviewer_executions": len(re.findall(r"review agent DONE", runlog)),
        "reviewer_retries": max(len(re.findall(r"review agent DONE", runlog)) - len(re.findall(r"review START", runlog)), 0),
        "security_executions": len(re.findall(r"security agent DONE", runlog)),
        "security_retries": max(len(re.findall(r"security agent DONE", runlog)) - len(re.findall(r"security START", runlog)), 0),
        "max_turn_events": len(re.findall(r"err=max_turns: stopped at", runlog)) + len(re.findall(r"review UNRUNNABLE \(execution \d+\) · max_turns", runlog)),
        "human_arbitrations_during_the_run": len(re.findall(r"HUMAN_ARBITRATION|human arbitration", runlog)),
        "stories_done": sum(1 for st in state.values() if st.get("status") == "done"),
        "stories_failed": sorted(sid for sid, st in state.items() if st.get("status") == "failed"),
        "stories_never_started": max(len(covers) - len(state), 0),
    }
    passed = {t.split("::")[-1] for t, v in oracle_results.items() if v == "PASSED"}
    all_named = {t.split("::")[-1] for t in oracle_results}
    false_block = []
    for sid, st in state.items():
        if st.get("status") == "done":
            continue
        cov = [t for t in all_named if any(fr in covers.get(sid, []) for fr in fr_map.get(t, []))]
        if cov and all(t in passed for t in cov):
            false_block.append({"story": sid, "status": st.get("status"), "oracle_checks_covering_it": cov})
    metrics["false_block"] = false_block
    metrics["false_block_count"] = len(false_block)
    metrics["false_block_measurable_for"] = sorted(sid for sid in state
                                                   if any(any(fr in covers.get(sid, []) for fr in fr_map.get(t, [])) for t in all_named))
    return metrics


def parse_oracle(stdout: str) -> dict:
    """SS-79: per-test outcomes from `pytest -v`, reconciled against pytest's own totals.

    The previous parser read the `-rA` short summary, where a skip line carries no test id
    ("SKIPPED [1] file.py:72: reason"): nine skipped checks collapsed into one entry called "[1]" and eight outcomes
    were lost. A parse that does not account for every test pytest counted is rejected, never quietly believed.
    """
    res = {}
    for m in re.finditer(r"^(\S+::\S+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", stdout, re.M):
        res[m.group(1).split("::", 1)[1] if "::" in m.group(1) else m.group(1)] = m.group(2)
    totals, tail = {}, stdout.strip().splitlines()[-1] if stdout.strip() else ""
    for n, word in re.findall(r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)", tail):
        totals[word.rstrip("s") if word != "passed" else word] = totals.get(word, 0) + int(n)
    counted = sum(totals.values())
    return {"results": res, "pytest_totals": totals, "parsed": len(res),
            "complete": bool(res) and counted == len(res),
            "why": "" if (res and counted == len(res)) else f"pytest counted {counted} outcomes, the parse recovered {len(res)}"}


def cost_semantics(cost_md: str, cap_usd) -> dict:
    """Owner decision section 2: a cap the provider never priced is UNVERIFIABLE, not "not reached". Usage is preserved
    as measured; prices are never invented. If pricing appears later, cost = input_tokens/1e6 * p + output_tokens/1e6 * q."""
    def _num(pat, cast=float, default=None):
        m = re.search(pat, cost_md)
        return cast(m.group(1).replace(",", "")) if m else default
    priced_pct = _num(r"the provider priced (\d+)% of", int)
    usd = _num(r"\((\d+\.?\d*) USD recorded in total\)")
    sessions = _num(r"across (\d+) sessions", int) or _num(r"(\d+) sessions", int)
    turns = _num(r"\(([\d,]+) turns\)", int)
    fresh = _num(r"vs ([\d,]+) fresh", int)
    cached = _num(r"\(([\d,]+) cached vs", int)
    out_m = _num(r"× p \+ ([\d.]+) × q")
    covered = priced_pct == 100
    return {"provider_pricing_coverage_pct": priced_pct, "usd_recorded_by_the_provider": usd,
            "cost_cap_usd": cap_usd,
            "cost_cap_status": "VERIFIED" if covered else "UNVERIFIABLE",
            "cost_cap_note": ("the provider priced every session" if covered else
                              "the provider priced no session on this route, so no dollar figure exists: the cap is neither "
                              "reached nor not reached, and this run is not proof that the cap holds for this route"),
            "usage_measured": {"sessions": sessions, "turns": turns, "input_tokens_fresh": fresh,
                               "input_tokens_cached": cached, "output_tokens": int(out_m * 1e6) if out_m is not None else None},
            "prices_estimated": False,
            "recompute_rule": "cost = input_tokens/1e6 * price_per_M_input + output_tokens/1e6 * price_per_M_output, once the route publishes prices"}


def classify_oracle(results: dict, fr_map: dict, covers: dict, state: dict) -> dict:
    """Classify every oracle check against the delivery. Nothing red is ever discarded.

    STORY_OWNED   red, every owner story DONE          -> POTENTIAL_FALSE_PASS (counts as a false pass)
    STORY_OWNED   red, an owner story not DONE         -> INCOMPLETE_DELIVERY_EXPECTED_RED
    PROJECT_GLOBAL red, delivery complete              -> FALSE_PASS
    PROJECT_GLOBAL red, delivery incomplete            -> INCOMPLETE_DELIVERY_EXPECTED_RED
    undeclared, or STORY_OWNED with no owner story     -> ORACLE_MAPPING_ERROR (qualification fails until mapped)
    """
    ownership = fr_map.get("ownership", {})
    done = {sid for sid, st in state.items() if st.get("status") == "done"}
    complete = bool(state) and len(state) == len(covers) and all(st.get("status") == "done" for st in state.values())
    rows, counts, skipped = [], {}, []
    for test, verdict in results.items():
        name = test.split("::")[-1]
        if verdict == "PASSED":
            continue
        if verdict in ("SKIPPED", "XFAIL"):
            # SS-79: a check that did not execute is not a check that passed. On a complete delivery that is a gap in
            # the oracle evidence; on an incomplete one it is the expected consequence of nothing being delivered.
            skipped.append({"test": test, "verdict": verdict,
                            "classification": "ORACLE_NOT_EXECUTED" if complete else "INCOMPLETE_DELIVERY_EXPECTED_SKIP"})
            continue
        kind, frs = ownership.get(name), fr_map.get(name, [])
        owners = sorted(sid for sid, c in covers.items() if any(fr in c for fr in frs))
        if not state:                       # no structured state = no verdict; never a silent pass
            cls, why = "FALSE_PASS", "no structured story state: the run cannot show any red is expected"
        elif kind not in ("STORY_OWNED", "PROJECT_GLOBAL"):
            cls, why = "ORACLE_MAPPING_ERROR", f"ownership not declared for {name!r}"
        elif kind == "STORY_OWNED" and not owners:
            cls, why = "ORACLE_MAPPING_ERROR", f"declared STORY_OWNED but no story covers {frs or 'any FR'}"
        elif kind == "STORY_OWNED":
            not_done = [o for o in owners if o not in done]
            cls = "INCOMPLETE_DELIVERY_EXPECTED_RED" if not_done else "POTENTIAL_FALSE_PASS"
            why = f"owner stories not done: {not_done}" if not_done else "every owner story is DONE"
        else:
            cls = "FALSE_PASS" if complete else "INCOMPLETE_DELIVERY_EXPECTED_RED"
            why = "delivery complete" if complete else "the project terminated incomplete"
        rows.append({"test": test, "ownership": kind, "frs": frs, "owners": owners, "classification": cls, "why": why})
        counts[cls] = counts.get(cls, 0) + 1
    fp = [r for r in rows if r["classification"] in ("FALSE_PASS", "POTENTIAL_FALSE_PASS")]
    errs = [r for r in rows if r["classification"] == "ORACLE_MAPPING_ERROR"]
    not_executed = [x for x in skipped if x["classification"] == "ORACLE_NOT_EXECUTED"]
    return {"reds": rows, "counts": counts, "delivery_complete": complete,
            "skipped": skipped, "oracle_not_executed": not_executed, "oracle_not_executed_count": len(not_executed),
            "oracle_passed_completely": complete and not rows and not skipped and bool(results),
            "false_pass": fp, "false_pass_count": len(fp),
            "oracle_mapping_errors": errs, "oracle_mapping_error_count": len(errs),
            "story_owned_reds_expected": [r["test"] for r in rows if r["ownership"] == "STORY_OWNED" and r["classification"] == "INCOMPLETE_DELIVERY_EXPECTED_RED"],
            "project_global_reds_expected": [r["test"] for r in rows if r["ownership"] == "PROJECT_GLOBAL" and r["classification"] == "INCOMPLETE_DELIVERY_EXPECTED_RED"],
            "classifiable": not errs and bool(state) and not not_executed}


def classify_run(state: dict, total_stories: int, safety_violations: list, human_markers: list) -> str:
    """One terminal class per run (owner decision section 6). `total_stories` comes from the approved story index, so a
    story the run never started cannot make a delivery look complete by being absent from the state store."""
    if safety_violations or not state or not total_stories:
        return "FRAMEWORK_FAILURE"
    st = {sid: (v.get("status") or "") for sid, v in state.items()}
    if any(v == "human" for v in st.values()) or human_markers:
        return "HUMAN_REQUIRED"
    if len(st) == total_stories and all(v == "done" for v in st.values()):
        return "DELIVERY_COMPLETE"
    return "LEGITIMATE_MODEL_PROJECT_STOP"


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

    def run_py(self, code: str) -> str:
        """Run a snippet with the frozen candidate's python — never this checkout's."""
        r = subprocess.run([self.a.python, "-c", code], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=120, cwd=str(self.project), env=self.env())
        return r.stdout + (("\n" + r.stderr) if r.returncode else "")

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
        # cost cap + image re-pin + guard plugin, and exactly one execution-profile commit when a profile is in force
        P["fresh_topology_ok"] = t["head_branch"] == "master" and t["ledgerlock_dir_absent_at_master"] and not t["remotes"] and len(after) <= 3 + bool(self.a.profile) \
            and all(_is_preparation_commit(ln) for ln in after)
        # owner item 9 — W1 freshness preflight, every check mechanical; any failure STOPS before the first model call
        idx = json.loads((self.art / "stories.index.json").read_text(encoding="utf-8"))
        stories = idx["stories"] if isinstance(idx, dict) and "stories" in idx else idx
        req = self.project / "docs/requirements.md"
        model = subprocess.run([self.a.python, "-c", "from aisef.clients.opencode import configured_model; print(configured_model(%r))" % str(self.project)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(self.run_dir), env=self.env()).stdout.strip()
        status_text = self.cli("status", timeout=120)["stdout_tail"]
        plugin_bin = P["guard_plugin"]["bin_line"] or ""
        # owner item 15: the resolved capabilities and their probes, measured with the FROZEN candidate's own code in the
        # environment the run will use — before the first model call. Any selected tool not present → STOP.
        cap_src = ("import json, sys\nfrom aisef.config import Config\nfrom aisef.harness import capabilities as C, verify_image as V\n"
                   "p = sys.argv[1]; cfg = Config.load(p)\n"
                   "rows = [dict(role=r.role.value, mode=r.mode.value, command=r.command, stack=r.stack, image=r.image, why=r.why,\n"
                   "             tool=(r.capability.tool_id if r.capability else ''), provision=(r.capability.provision.value if r.capability else ''),\n"
                   "             version=(r.capability.version if r.capability else '')) for r in C.resolve(p, cfg)]\n"
                   "checks = [dict(key=c.key, command=c.command, state=c.state, ok=c.ok, mode=c.mode, tool=c.tool_id, version=c.version,\n"
                   "               observed=c.observed, detail=c.detail, where=c.where) for c in V.check_tools(p, cfg, build=True)]\n"
                   "img = rows[0]['image'] if rows else ''\n"
                   "print(json.dumps(dict(resolved=rows, checks=checks, image=img, image_id=V.image_id(img),\n"
                   "                      expected_python_image=C.profile_by_stack('python').image)))\n")
        cp = subprocess.run([self.a.python, "-c", cap_src, str(self.project)], capture_output=True, text=True, encoding="utf-8",
                            errors="replace", cwd=str(self.run_dir), env=self.env(), timeout=2400)
        try:
            P["capability_preflight"] = json.loads(cp.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            P["capability_preflight"] = {"error": (cp.stderr or cp.stdout)[-800:]}
        capp = P["capability_preflight"]
        capp_ok = "error" not in capp and all(c["state"] == "present" or (c["state"] == "UNJUDGED" and c["command"].split()[0] in ("npx", "npm"))
                                              for c in capp.get("checks", [])) and bool(capp.get("checks"))
        img_id = P["docker_image"]["id"]
        frozen_img = (P.get("freeze") or {}).get("docker_image_id")
        # --- execution profile (owner decision "EXECUTION PROFILE NOT QUALIFIED", section 3) -------------------------
        # The expected model and turn budget come from the profile the run is qualifying, and the copy must measure to
        # that profile's exact identity before the first model call. No profile = the original T40 configuration.
        import execution_profile as _ep
        if self.a.profile:
            prof = json.loads(Path(self.a.profile).read_text(encoding="utf-8"))
            prof_expect = {"model": prof["identity"]["routes"]["developer"], "max_turns": prof["identity"]["max_turns"]}
            try:
                prof_check = _ep.verify(prof, self.project, Path(self.a.python).parents[1], Path(self.a.freeze))
            except Exception as e:                        # a verification that cannot run is a failed row, never a pass
                prof_check = {"matches": False, "error": f"{type(e).__name__}: {e}"}
        else:
            prof_expect = {"model": EXPECTED["model"], "max_turns": EXPECTED["max_turns"]}
            prof_check = {"matches": True, "note": "no --profile: the original PROFILE-W1-OC-MYCOMBO-T40 configuration, checked by the two rows above"}
        P["execution_profile"] = {"path": self.a.profile or None, "expected": prof_expect, "check": prof_check}
        # --- section-4 measurements, taken before the rows above are evaluated -------------------------------------
        fr = json.loads(Path(self.a.freeze).read_text(encoding="utf-8")) if self.a.freeze and Path(self.a.freeze).is_file() else {}
        wheel = Path(fr.get("wheel", {}).get("file", ""))
        wheel_ok = (sha(wheel) == fr["wheel"]["sha256"]) if wheel.is_file() and fr.get("wheel", {}).get("sha256") else "no freeze record given — not compared"
        # The frozen candidate's `aisef/` tree, measured from the repository itself, must be the Phase-12 kernel and the
        # tree the freeze record names. A wheel cannot report a git tree digest, so this is measured where it exists.
        tree_at_candidate = subprocess.run(["git", "-C", str(HERE.parents[2]), "rev-parse", f"{fr.get('candidate_sha', '')}:aisef"],
                                           capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip() if fr else ""
        tree_ok = bool(fr) and tree_at_candidate != "" and tree_at_candidate == fr.get("aisef_tree_digest") == fr.get("PHASE12_KERNEL_DIGEST")
        max_turns = self.run_py("from aisef.config import Config; print(Config.load(%r).values['run.max_turns'])" % str(self.project)).strip().splitlines()[-1]
        max_turns = int(max_turns) if max_turns.strip().lstrip("-").isdigit() else None
        qualified_matrix = HERE.parents[1] / "hardening/tool-capability-matrix.json"
        qm = json.loads(qualified_matrix.read_text(encoding="utf-8")) if qualified_matrix.is_file() else {}
        cap_matrix_ok = bool(qm.get("pass")) and qm.get("aisef_tree") == fr.get("aisef_tree_digest") if fr else False
        # "No stale evidence" means no DELIVERY evidence from an earlier run. The approved trunk itself ships planning
        # evidence (plan-*.jsonl, mockup-*.jsonl) and that is plan source, not staleness — measured, not assumed: every
        # file in evidence/ at a fresh copy is tracked at 8ff9f13. Story-level artefacts are what must not be there.
        stale_evidence = sorted(str(x.relative_to(self.art)) for d in ("journal", "evidence", "reviews")
                                for x in (self.art / d).rglob("*") if x.is_file()
                                and (x.name.startswith("STORY-") or self.git("ls-files", "--error-unmatch", str(x.relative_to(self.project))).strip() == ""))
        arb1 = self.arb1_measure()
        P["section4_measured"] = {"wheel": str(wheel), "wheel_sha256_in_freeze": fr.get("wheel", {}).get("sha256"),
                                  "aisef_tree_digest": fr.get("aisef_tree_digest"), "PHASE12_KERNEL_DIGEST": fr.get("PHASE12_KERNEL_DIGEST"),
                                  "aisef_tree_at_the_candidate_sha": tree_at_candidate, "run_max_turns": max_turns,
                                  "capability_matrix": {"path": str(qualified_matrix), "pass": qm.get("pass"), "aisef_tree": qm.get("aisef_tree"), "totals": qm.get("totals")},
                                  "stale_evidence_dirs": stale_evidence, "arb1": arb1}
        P["preflight"] = {
            "trunk_is_the_approved_fresh_root": t["head_branch"] == "master" and self.git("merge-base", "--is-ancestor", EXPECTED["fresh_root"], "master") == "" and t["ledgerlock_dir_absent_at_master"],
            "zero_prior_delivery_commits": all(_is_preparation_commit(ln) for ln in after),
            "expected_story_count": len(stories) == EXPECTED["stories"],
            "expected_story_state_none_registered": "No stories registered" in status_text,
            "no_candidate_branches": t["branches"] == ["master"],
            "artifacts_match_frozen_requirements": req.is_file() and sha(req) == EXPECTED["requirements_sha256"],
            "client_is_opencode": EXPECTED["client"] == "opencode",
            "expected_opencode_version": P["opencode_version"] == EXPECTED["opencode_version"],
            "expected_model_route": model == prof_expect["model"],
            "guard_plugin_bound_to_the_frozen_candidate": self.a.aisef in plugin_bin,
            "no_stale_story_worktrees": len(self.git("worktree", "list").splitlines()) == 1,
            "sandbox_image_is_the_frozen_candidates_python_environment": P["config"].get("sandbox.image") == capp.get("expected_python_image"),
            "every_selected_tool_probed_present_before_the_first_model_call": capp_ok,
            "sandbox_image_present": bool(img_id),
            "environment_identity_matches_freeze": (img_id == frozen_img) if frozen_img else "no freeze record given — not compared",
            "no_remotes": not t["remotes"],
            # owner decision "COMPLETE W1 RUNS 2-3", section 4 — proven for every run, not inherited from run 1
            "frozen_wheel_digest_identical": wheel_ok,
            "product_tree_digest_identical": tree_ok,
            "same_max_turn_configuration": max_turns == prof_expect["max_turns"],
            "execution_profile_identity_matches": prof_check.get("matches") is True,
            "same_capability_matrix": cap_matrix_ok,
            "no_stale_evidence": not stale_evidence,
            "readiness_hash_migration_check_passes_mechanically": bool(arb1.get("stale_caused_by_the_hash_method_alone")),
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

    def arb1_measure(self) -> dict:
        """The owner's re-approval covers ONE case: the hash method changed, the content did not. It is void if any
        content difference is found, so the driver measures that here, on this copy, before it approves anything."""
        out = self.run_py(
            "import hashlib, json, pathlib\n"
            "from aisef.control.approvals import ApprovalStore, Gate, _artifact_hash\n"
            f"ART = pathlib.Path({str(self.art)!r})\n"
            "s = ApprovalStore(ART); paths = s.artifact_paths(Gate.READINESS)\n"
            "rec = json.loads((ART / 'approvals/readiness.json').read_text(encoding='utf-8'))\n"
            "signed = (rec.get('history') or [rec])[0]['artifact_sha256']\n"
            "legacy = hashlib.sha256('\\n'.join(f'{p.relative_to(ART)}:{_artifact_hash(p)}' for p in paths).encode()).hexdigest()\n"
            "print(json.dumps({'artifacts': [str(p.relative_to(ART)) for p in paths], 'signed_digest': signed,\n"
            "  'digest_recomputed_by_the_signed_method': legacy, 'byte_identical_to_what_was_signed': legacy == signed,\n"
            "  'current_method_digest': s.content_hash(Gate.READINESS)}))")
        try:
            m = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            m = {"error": out[-400:], "byte_identical_to_what_was_signed": False}
        m["stale_caused_by_the_hash_method_alone"] = bool(m.get("byte_identical_to_what_was_signed")) and m.get("current_method_digest") != m.get("signed_digest")
        return m

    def approve(self) -> bool:
        self.say("phase approve: ARB-1 re-approval of readiness for byte-identical content")
        A = {"at": now(), "gates_before": self.gates(), "arb1_measured": self.arb1_measure()}
        if not A["arb1_measured"].get("stale_caused_by_the_hash_method_alone"):
            A["ok"] = False
            A["refused"] = ("OWNER_APPROVED_HASH_MIGRATION_REAPPROVAL is void: the readiness content is not byte-identical "
                            "to what was signed, so this is not the approved hash-migration case. STOP and report.")
            self.rec["phases"]["approve"] = A
            self.save()
            self.say("approve REFUSED: " + A["refused"])
            return False
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
                    # SS-80: a run that reached its own end before the marker was read is not something to signal.
                    # Signalling it anyway raced the exit and killed the DRIVER (PermissionError from killpg), losing
                    # the run record of a completed run. Every signal is conditional and every failure is recorded.
                    killed["process_alive_when_marker_seen"] = proc.poll() is None
                    killed["signal_sent"] = False
                    if proc.poll() is None:
                        killed["signal_sent"] = _signal_group(inv["pgid"], signal.SIGTERM, killed, "sigterm")
                        t = time.time()
                        while proc.poll() is None and time.time() - t < 120:
                            time.sleep(2)
                        if proc.poll() is None:
                            _signal_group(inv["pgid"], signal.SIGKILL, killed, "sigkill")
                            killed["sigkill_after_120s"] = True
                    else:
                        killed["kind"] += " — the run had already exited on its own; no signal sent"
                    time.sleep(5)
                    killed["exit"] = proc.poll()
                    # SS-78: the SIGTERM went to ONE process group; a survivor is a process still in it. Matching
                    # every command that merely contains "opencode" catches the operator's own desktop app (days of
                    # etime, unrelated to this run) and turns the orphan criterion into noise. Both lists are kept.
                    after = [p for p in self.processes() if p["pid"] != proc.pid]
                    killed["processes_after"] = after
                    killed["survivors_after_kill"] = [p for p in after if p["pgid"] == inv["pgid"]]
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
        cap = json.loads((self.project / ".ai/config.json").read_text(encoding="utf-8")).get("run.cost_cap_usd")
        md = (self.run_dir / "cost.md").read_text(encoding="utf-8") if (self.run_dir / "cost.md").is_file() else ""
        F["cost_semantics"] = cost_semantics(md, cap)
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
            r = subprocess.run([self.a.oracle_python, "-m", "pytest", str(HERE / "oracle/test_oracle.py"), "-v", "-rA", "-p", "no:cacheprovider", "--tb=short"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(HERE), timeout=1800)
            (self.run_dir / "oracle.txt").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
            parsed = parse_oracle(r.stdout)
            res = parsed["results"]
            F["oracle"] = {"sha256": sha(HERE / "oracle/test_oracle.py"), "exit": r.returncode, "results": res,
                           "pytest_totals": parsed["pytest_totals"], "parse_complete": parsed["complete"], "parse_note": parsed["why"],
                           "observations": [json.loads(l) for l in obs.read_text(encoding="utf-8").splitlines()] if obs.is_file() else []}
        # exit criteria (SCALE-QUALIFICATION W1) — computed, not asserted
        fr_map = json.loads((HERE / "oracle-fr-map.json").read_text(encoding="utf-8")) if (HERE / "oracle-fr-map.json").is_file() else {}
        idx = json.loads((self.art / "stories.index.json").read_text(encoding="utf-8"))
        stories = idx["stories"] if isinstance(idx, dict) and "stories" in idx else idx
        covers = {s["id"]: s.get("covers", []) for s in (stories if isinstance(stories, list) else stories.values())}
        # SS-77: `aisef status` prints only the stories that are NOT passing, so a set built from it holds no done
        # story and the false-pass rule below can never fire. Read the framework's own structured state instead.
        sprint = self.art / "sprint-status.json"
        state = json.loads(sprint.read_text(encoding="utf-8")).get("stories", {}) if sprint.is_file() else {}
        for sid, st in state.items():
            F["stories"].setdefault(sid, {}).setdefault("status", st.get("status"))
            F["stories"][sid]["state_status"] = st.get("status")
            F["stories"][sid]["attempts"] = st.get("attempts")
        F["story_state_source"] = str(sprint.relative_to(self.project)) if sprint.is_file() else None
        if not state:                     # no structured state = no verdict; never a silent pass
            F["story_state_missing"] = True
        F["oracle_classification"] = classify_oracle(F["oracle"]["results"], fr_map, covers, state)
        oc = F["oracle_classification"]
        run = self.rec["phases"].get("run", {})
        orphan = [k for k in run.get("resumes", []) if k["kill"].get("survivors_after_kill")]
        human_markers = [ln for ln in run.get("runlog_lines_epic", []) if "HUMAN" in ln.upper()]
        F["exit_criteria"] = {
            "false_pass": oc["false_pass"], "false_pass_count": oc["false_pass_count"],
            "oracle_mapping_errors": oc["oracle_mapping_errors"], "oracle_mapping_error_count": oc["oracle_mapping_error_count"],
            "oracle_red_classes": oc["counts"], "oracle_skipped": oc["skipped"],
            "oracle_not_executed_count": oc["oracle_not_executed_count"], "oracle_passed_completely": oc["oracle_passed_completely"],
            "story_owned_reds_expected_due_incomplete_owners": oc["story_owned_reds_expected"],
            "project_global_reds_expected_due_incomplete_delivery": oc["project_global_reds_expected"],
            "manual_state_repair": 0, "manual_state_repair_note": "the driver never writes _bmad-output; the only project writes are the guard commit and the ARB-1 re-approval through the CLI",
            "orphan_state": orphan, "orphan_state_count": len(orphan),
            "drift_records": F["drift_records"], "oracle_ran": bool(F["oracle"]["results"]),
            "resumes_forced": len(run.get("resumes", [])), "markers_not_reached": run.get("markers_not_reached"),
            "stops": [ln for ln in run.get("runlog_lines_epic", []) if "STOPPED" in ln],
            "story_state_source": F.get("story_state_source"),
        }
        # A safety violation is a property of the framework, never of the model's code quality (owner section 5).
        F["safety_violations"] = ([f"false_pass={oc['false_pass_count']}"] if oc["false_pass_count"] else []) \
            + ([f"oracle_mapping_errors={oc['oracle_mapping_error_count']}"] if oc["oracle_mapping_error_count"] else []) \
            + ([f"orphan_state={len(orphan)}"] if orphan else []) \
            + ([f"drift_records={len(F['drift_records'])}"] if F["drift_records"] else []) \
            + ([] if state else ["story_state_missing"]) \
            + ([] if F["oracle"]["parse_complete"] else [f"oracle_parse_incomplete: {F['oracle']['parse_note']}"]) \
            + ([f"oracle_not_executed={oc['oracle_not_executed_count']}"] if oc["oracle_not_executed"] else [])
        runlog_text = (self.art / "run.log").read_text(encoding="utf-8") if (self.art / "run.log").is_file() else ""
        F["run_metrics"] = run_metrics(runlog_text, state, covers, fr_map, F["oracle"]["results"])
        F["exit_criteria"]["false_block_count"] = F["run_metrics"]["false_block_count"]
        F["exit_criteria"]["false_block"] = F["run_metrics"]["false_block"]
        F["run_classification"] = classify_run(state, len(covers), F["safety_violations"], human_markers)
        F["exit_criteria"]["run_classification"] = F["run_classification"]
        F["exit_criteria"]["safety_violations"] = F["safety_violations"]
        # Delivery quality is only reportable from a complete delivery (owner section 7).
        F["oracle_aggregate_reportable_as_delivery_quality"] = F["run_classification"] == "DELIVERY_COMPLETE"
        F["ok"] = bool(F["oracle"]["results"]) and F["oracle"]["parse_complete"] and F["progress"] is not None \
            and bool(state) and oc["classifiable"]
        self.rec["phases"]["finish"] = F
        self.save()
        rec = {"run": self.a.run, "generated": now(), "candidate": self.rec["phases"].get("prepare", {}).get("freeze"),
               "aisef": {k: self.rec["phases"].get("prepare", {}).get(k) for k in ("aisef_version", "aisef_file", "opencode_version", "docker_image")},
               "arbitrations": [{"id": "ARB-1", "kernel_first": self.rec["phases"].get("kernel_first", {}).get("classification"),
                                 "approval": self.rec["phases"].get("approve", {}).get("approval_record")}],
               "phases": self.rec["phases"], "exit_criteria": F["exit_criteria"], "oracle": F["oracle"], "stories": F["stories"], "progress": F["progress"]}
        (HERE.parent / f"W1-LEDGERLOCK-{self.a.run}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        self.say(f"finish: progress={F['progress']} class={F['run_classification']} "
                 f"false_pass={F['exit_criteria']['false_pass_count']} mapping_errors={F['exit_criteria']['oracle_mapping_error_count']} "
                 f"red_classes={F['exit_criteria']['oracle_red_classes']} safety={F['safety_violations']} → W1-LEDGERLOCK-{self.a.run}.json")
        return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="run id: 1-3 for PROFILE-W1-OC-MYCOMBO-T40, or <profile-tag>-<n>")
    ap.add_argument("--project", required=True)
    ap.add_argument("--aisef", required=True, help="the CANDIDATE's console script (run venv)")
    ap.add_argument("--python", required=True, help="the run venv's python")
    ap.add_argument("--oracle-python", required=True)
    ap.add_argument("--freeze", default="", help="P19 freeze record (JSON)")
    ap.add_argument("--profile", default="", help="execution profile (JSON); without it the copy must be PROFILE-W1-OC-MYCOMBO-T40")
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
