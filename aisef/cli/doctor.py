"""``doctor`` command — check environment, config, hooks, and installed skills."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import Config, ConfigError
from ._common import EXIT_NOT_READY, EXIT_OK


def _hook_paths_elsewhere(project: Path) -> list[str] | None:
    """Project paths declared in compiled hook/plugin that **differ** from this project.
    None when there are no hooks to compare."""
    import re as _re

    resolved = project.resolve()
    found: list[str] = []
    hook = project / ".claude" / "settings.json"
    if hook.is_file():
        found += _re.findall(r"--project\s+(\S+)\s+guard", hook.read_text(encoding="utf-8", errors="replace"))
    plugin = project / ".opencode" / "plugin" / "aisef-guard.ts"
    if plugin.is_file():
        found += _re.findall(r'const PROJECT = "([^"]+)"', plugin.read_text(encoding="utf-8", errors="replace"))
    if not found:
        return None
    return sorted({p for p in found if Path(p).resolve() != resolved})


def cmd_doctor(args) -> int:
    """Check whether the environment meets framework prerequisites."""
    project = Path(args.project)
    problems: list[str] = []
    lines: list[str] = []

    def check(label: str, ok: bool, detail: str = "", *, required: bool = True) -> None:
        mark = "✅" if ok else ("✗" if required else "○")
        lines.append(f"  {mark} {label}{(' — ' + detail) if detail else ''}")
        if required and not ok:
            problems.append(label)

    lines.append("Environment:")
    check("python >= 3.11", sys.version_info >= (3, 11), sys.version.split()[0])
    check("git", bool(shutil.which("git")))

    claude = shutil.which("claude")
    check("claude CLI", bool(claude), claude or "not found", required=False)
    opencode = shutil.which("opencode")
    check("opencode CLI", bool(opencode), opencode or "not found", required=False)

    # Which credential an agent session will authenticate with.  Not a
    # pass/fail — authenticating by key is legitimate — but the operator has to
    # be able to *see* it: a stale `ANTHROPIC_API_KEY` in the shell silently
    # outranks a working `claude.ai` login, and the only symptom is every
    # session returning 401 after burning its full wall-clock (measured
    # 2026-09-12).  Names only; a value never reaches this line.
    from ..clients.base import AUTH_ENV_NAMES
    auth_vars = [n for n in AUTH_ENV_NAMES if os.environ.get(n)]
    check(
        "agent credential",
        True,
        (", ".join(auth_vars) + " set in the environment — these outrank the client's own login; "
         "unset them to use it") if auth_vars else "none in the environment — the client uses its own login",
        required=False,
    )

    docker_ok = False
    if shutil.which("docker"):
        try:
            docker_ok = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=10
            ).returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            docker_ok = False
    check(
        "docker daemon",
        docker_ok,
        "running" if docker_ok else "not running — sandbox will degrade, lower guarantees",
        required=False,
    )

    from ..harness.browser import availability as browser_availability
    from ..harness.tools import image_for

    browser_why = browser_availability(project)
    check(
        "playwright + chromium",
        not browser_why,
        "ready" if not browser_why else f"{browser_why} — cannot extract mockup contracts",
        required=False,
    )

    lines.append("Project:")
    check("project directory", project.is_dir(), str(project))
    from ..harness import sandbox as _sandbox

    try:
        cfg_for_sandbox = Config.load(project)
        image = image_for(project, cfg_for_sandbox)
        spec = _sandbox.SandboxSpec(
            workspace=project, cmd=["true"],
            use_docker=cfg_for_sandbox["sandbox.use_docker"],
            provider=cfg_for_sandbox["sandbox.provider"],
        )
    except ConfigError:
        image, spec = "?", _sandbox.SandboxSpec(workspace=project, cmd=["true"])
    # Active provider and its declared guarantees (ADR-005 V5): the reader
    # knows evidence will record `degraded` due to **what is missing**, before
    # any story runs.
    try:
        prov, missing = _sandbox.select_provider(spec)
    except (RuntimeError, ValueError, ImportError, AttributeError) as e:
        prov, missing = None, []
        check("sandbox provider", False, str(e), required=False)
    if prov is not None:
        co = sorted(g.value for g, s in prov.guarantees(spec.level).items() if s.blocks_at_source)
        check(
            "sandbox provider", not missing,
            f"{prov.id} — guarantees at {spec.level.value}: {', '.join(co) or 'none'}"
            + (f"; MISSING {', '.join(missing)} — tools run outside isolation, evidence marked degraded"
               if missing else ""),
            required=False,
        )
    if prov is not None and prov.id == "docker":
        # Only Docker discusses the image; other providers use the host's tools.
        check(
            "sandbox image",
            image != "alpine:latest",
            image + (" — no stack tools, tests will fail due to missing tools"
                     if image == "alpine:latest" else " (matches stack)"),
            required=False,
        )
    req = project / "docs" / "requirements.md"
    check("docs/requirements.md", req.is_file(), str(req))

    # Generated hook != running hook.  Stories run in worktrees; a worktree
    # only has `.claude/` if the project commits it.  Harness now passes
    # `--settings` explicitly (G4), but that is only proven by conformance —
    # here we state the situation so the reader knows which layer they rely on.
    plugin = project / ".opencode" / "plugin" / "aisef-guard.ts"
    if plugin.is_file():
        tracked = subprocess.run(
            ["git", "-C", str(project), "ls-files", "--error-unmatch", str(plugin)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        ).returncode == 0
        check(
            "OpenCode plugin in worktree",
            tracked,
            "`.opencode/plugin` committed — worktree has plugin" if tracked else
            "`.opencode/plugin` not committed — worktree has NO plugin, OpenCode runs "
            "stories with zero guards (conformance measured 2026-09-05); commit `.opencode/` or "
            "do not use OpenCode for `run`",
            required=False,
        )
    hook = project / ".claude" / "settings.json"
    if hook.is_file():
        tracked = subprocess.run(
            ["git", "-C", str(project), "ls-files", "--error-unmatch", str(hook)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        ).returncode == 0
        check(
            "hook in worktree",
            tracked,
            "`.claude/settings.json` committed — worktree has hook" if tracked else
            "`.claude/settings.json` not committed — worktree has no hook; harness "
            "passes `--settings` explicitly, story gate \"guard ran\" will "
            "fail if hook is missing",
            required=False,
        )

    # Guards added after the last `compile` are unknown to the old hook —
    # e.g. `process-ref` (rule 6, 2026-09-05).  Without this check, new
    # guards exist only in code, not in any agent session.
    rep = project / "_bmad-output" / "compile-report.json"
    if rep.is_file():
        from ..harness.guardrails import GUARD_MATCHERS

        try:
            data = json.loads(rep.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        for c in data.get("clients", []):
            missing_guards = sorted(set(GUARD_MATCHERS) - set(c.get("guards_wired") or []) - set(c.get("guards_post_hoc") or []))
            check(
                f"hook {c.get('client')} has all guards", not missing_guards,
                f"{len(GUARD_MATCHERS)} guards" if not missing_guards else
                f"missing {', '.join(missing_guards)} — framework has new guards since last compile; run `aisef compile --client {c.get('client')}`",
            )

    # Story size thresholds are only trustworthy while they match real data
    # (ADR-004 R5).  The calibration table is written by `run` after each story.
    from ..control import complexity

    rows = complexity.load_calibration(project / "_bmad-output")
    if rows:
        threshold_divergence = complexity.divergence(rows)
        check(
            "story size thresholds match data", not threshold_divergence,
            f"{len(rows)} stories measured, no divergence" if not threshold_divergence else
            "; ".join(threshold_divergence) + " — adjust `story.max_complexity` in "
            "`.ai/config.json` or review weights in `control/complexity.py`",
            required=False,
        )

    stray = _hook_paths_elsewhere(project)
    if stray is not None:
        check(
            "hook points to this project", not stray,
            "`--project`/`PROJECT` path in hook matches this directory" if not stray else
            f"hook points to {', '.join(stray[:2])} — project copied/moved? guards will write "
            "evidence to that project; run `aisef compile` again",
        )

    try:
        cfg = Config.load(project)
        check("config", True, cfg.source)
        test_cmd = str(cfg.get("tools.test", "") or "")
        if test_cmd:
            has_cov = any(k in test_cmd for k in ("--coverage", "--cov", "--experimental-test-coverage", "c8 ", "nyc "))
            check(
                "test command prints coverage", has_cov,
                "gate `coverage.min` can read the number" if has_cov else
                f"`tools.test` = `{test_cmd}` does not print coverage — gate coverage check will be **not configured** "
                "(add `--coverage` / `--cov` / `--experimental-test-coverage`)",
                required=False,
            )
            # Are test names readable (ADR-005 V9)?  If evidence exists, trust
            # it: the latest `tool_run test` records `test_format`; otherwise
            # guess from command flags.  e9/par: 220/377 test runs had unreadable names.
            from ..harness.observe import TOOL_RUN, EvidenceStore

            store = EvidenceStore(project / "_bmad-output")
            runs = [e for sid in store.stories() for e in store.read(sid).of(TOOL_RUN)
                    if e.name in ("test", "test:baseline") and not e.detail.get("skipped")]
            if runs:
                has_names = bool(runs[-1].detail.get("test_format"))
                detail = f"last test run recorded test_format={runs[-1].detail.get('test_format') or ''!r}"
            else:
                has_names = any(k in test_cmd for k in ("-v", "--verbose", "--reporter=verbose",
                                                        "--test-reporter", "node --test", "ctrf"))
                detail = "no evidence yet — guessing from command flags"
            check(
                "test command prints test names", has_names,
                f"gate can read test names ({detail})" if has_names else
                f"{detail} — gate `has tests`/`no existing tests broken` will be **not configured**. "
                "Use a reporter that prints names or CTRF: pytest `-v` or `pip install pytest-json-ctrf` + "
                "`pytest --ctrf /dev/stdout`; vitest `--reporter=verbose` or `vitest-ctrf-json-reporter` "
                "(prints `vitest-ctrf/report.json` to stdout, preserves exit code); node `--test-reporter=spec|tap`",
                required=False,
            )
    except ConfigError as e:
        check("config", False, str(e))

    skills_dir = project / ".claude" / "skills"
    if skills_dir.is_dir():
        from ..kit.security_filter import Verdict, classify_all

        installed = [d for d in skills_dir.iterdir() if d.is_dir()]
        lines.append("Installed skills:")
        check("has skills", bool(installed), f"{len(installed)} directories")

        # Invariant: offensive skills must never be present in the project.
        offensive = [
            c.skill.name
            for c in classify_all(skills_dir)
            if c.verdict is Verdict.OFFENSIVE
        ]
        # Framework skills live in the framework repo; the project keeps a
        # copy.  Editing a skill without reinstalling leaves the agent running
        # the old copy, and the only way to detect this is a file-by-file diff.
        from ..kit.install import OWN_SKILLS

        stale = []
        for own in sorted(OWN_SKILLS.glob("*/SKILL.md")) if OWN_SKILLS.is_dir() else []:
            copied = skills_dir / own.parent.name / "SKILL.md"
            if copied.is_file() and copied.read_bytes() != own.read_bytes():
                stale.append(own.parent.name)
        check(
            "framework skills up to date",
            not stale,
            "matches source" if not stale
            else f"outdated: {', '.join(stale)} — run `aisef setup`",
            required=False,
        )

        check(
            "no offensive skills",
            not offensive,
            "clean" if not offensive else f"FOUND: {', '.join(offensive[:5])}",
        )
    else:
        lines.append("Installed skills:")
        check("setup completed", False, "not yet — run: aisef setup", required=False)

    print("\n".join(lines))
    if problems:
        print(f"\n✗ missing: {', '.join(problems)}")
        return EXIT_NOT_READY
    print("\n✅ ready")
    return EXIT_OK
