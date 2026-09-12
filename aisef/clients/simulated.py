"""A **simulated weak** agent adapter for the bench harness.

Real frontier-model runs cost money and we cannot call paid APIs from this
environment.  Real weak-model calls have the same problem: there is no
guarantee the model has been wired, the run cost may dominate the
signal, and the metrics land at the operator's desk without anyone
auditing what the model actually did.

The A-3 question we want to ask is: **does the harness's pipeline —
post-test, post-guard, post-verify — change its verdict when the agent
is weaker?**  That question is meaningful even without a real weak
model, because the bench harness treats every candidate the same way
after `client.run()` returns: it runs `tools.test`, applies
`tests.patch`, and grades F2P/P2P.  A simulator lets us feed a known
distribution of agent outcomes into that pipeline and measure whether
the harness catches weak attempts.

What this simulator **is**:

* A `ClientAdapter` that, for each attempt, picks one of four
  deterministic strategies and applies it to the worktree:
  * ``gold``: apply ``gold.patch`` exactly (would PASS).
  * ``noop``: write nothing (should FAIL — bug remains).
  * ``partial``: write the first non-test file in sorted POSIX-path order
    (may PASS when that file contains the complete fix).
  * ``revert``: replace every file touched by ``gold.patch`` with the
    pre-fix version (should FAIL — the agent re-rolled the fix).
  Strategy is keyed on ``attempt % 4`` so it is reproducible across
  conditions and the report reader can see exactly what each attempt
  did.

* Honest about being a simulator.  Its `id` is ``simulated-weak``;
  its declared capability is UNSUPPORTED for everything except
  HEADLESS and MACHINE_OUTPUT; the cost is reported as 0 (no real
  tokens were ever consumed).

What this simulator **is not**:

* A model of a specific weak model.  The actual failure distribution
  of `gpt-4-mini` or `mistral-small` on these tasks is unknown, and
  pretending otherwise would make the bench report a lie.
* A model of a frontier agent.  25 % of attempts write the gold
  patch verbatim; a real agent almost never does that.  Treat that
  row as a **ceiling**, not a typical outcome.

The benchmark condition uses this client via:

    aisef.run --client simulated-weak --bare / --no-bare
    python -m tests.bench run --client simulated-weak

and the ``AISEF_BENCH_TASK_DIR`` env var is set by ``_runner.run``
so the simulator can locate the original ``gold.patch``.

Decision 2026-09-12: chosen over an HTTP stub of OpenAI-compatible
APIs because (a) zero install, zero network, zero credential; (b)
deterministic reproducibility — the same attempt always takes the
same strategy, so a re-run trivially confirms the result.
"""

from __future__ import annotations

import io
import os
import shutil
import time
from pathlib import Path

from aisef.control.impact import is_test_path

from .base import Capability, ClientAdapter, RunSpec, Support
from .stream import RunResult

BINARY = "simulated-weak"


def _apply_patch_file(scratch: Path, patch: Path) -> bool:
    """Apply ``patch`` inside ``scratch``; True when it really applied.

    Two appliers, tried in order, because neither works everywhere:

    * ``git apply`` **inside a repository**.  Run from a plain directory it
      prints ``Skipped patch '...'`` for a hunk it cannot place and still
      exits 0 (observed 2026-09-12 on ``bug-a2-state-1/gold.patch``) — no
      error, no apply, the file left at its pre-image.  Initialising the
      scratch tree as a repository removes that mode: a hunk that will not
      place is an error there, which is the contract this function needs.
    * GNU ``patch``, which is what the rest of the bench uses — and which
      simply **does not exist on Windows** (CI, 2026-09-12: every simulator
      strategy wrote nothing and the five bench tests failed with no
      diagnostic, because a missing tool and a patch that does not apply
      both arrived here as "returned nothing").

    The two cover each other: git ships on any machine that could have
    cloned this repository, and ``patch`` covers a git too old for
    ``--unsafe-paths`` semantics.
    """
    import subprocess

    init = subprocess.run(["git", "init", "-q", str(scratch)], capture_output=True, text=True, check=False)
    if init.returncode == 0:
        applied = subprocess.run(
            ["git", "apply", "-p1", "--whitespace=nowarn", str(patch.resolve())],
            cwd=str(scratch), capture_output=True, text=True, check=False,
        )
        if applied.returncode == 0 and "Skipped patch" not in (applied.stdout + applied.stderr):
            return True
    if not shutil.which("patch"):
        return False
    return subprocess.run(
        ["patch", "-p1", "--binary", "-d", str(scratch), "-i", str(patch.resolve())],
        capture_output=True, text=True, check=False,
    ).returncode == 0


def _read_gold(task_dir: Path, repo_root: Path | None = None) -> list[tuple[Path, str]]:
    """``gold.patch`` parsed into ``(file_path, new_contents)`` pairs.

    Strategy: ``git apply`` to a scratch tree, then read the result.
    The patch format allows merges, file renames, mode changes, and
    binary diffs that a hand-rolled line parser cannot reconstruct.
    We get the **whole post-image** for free — that is what the
    harness wants.

    Test files are excluded: the bench harness reverts any test file
    the agent touches, so writing test content here is wasted work.

    Empty list if ``gold.patch`` is missing, the patch cannot apply,
    or the target file is ``/dev/null``-only (a pure delete).
    """
    patch = task_dir / "gold.patch"
    if not patch.is_file() or not patch.stat().st_size:
        return []
    import shutil
    import subprocess
    import tarfile

    task_data = task_dir / "task.json"
    if not task_data.is_file():
        return []
    import json as _json

    base = _json.loads(task_data.read_text(encoding="utf-8")).get("base")
    if not base:
        return []

    import tempfile

    temporary = tempfile.TemporaryDirectory(prefix="aisef-sim-")
    scratch = Path(temporary.name) / "scratch"
    scratch.mkdir()
    clean: Path | None = None
    # Resolve the AISEF project root.  In production, ``_runner.run``
    # sets ``AISEF_BENCH_AISEF_ROOT`` explicitly; for unit tests we
    # accept either the env or a walk-up the task-dir tree.  ``task_dir``
    # is ``<aisef>/tests/bench/tasks/<id>/`` in both cases, so four
    # levels up is the repo root.
    repo_root = repo_root or Path(os.environ.get("AISEF_BENCH_AISEF_ROOT")
                     or task_dir.parent.parent.parent.parent)
    try:
        arch = subprocess.run(
            ["git", "archive", "--format=tar", base],
            cwd=str(repo_root),
            capture_output=True, check=True,
        )
        with tarfile.open(fileobj=io.BytesIO(arch.stdout)) as tf:
            tf.extractall(scratch, filter="data")
        if not _apply_patch_file(scratch, patch):
            return []
        # Find all files that differ from a fresh extraction.
        arch2 = subprocess.run(
            ["git", "archive", "--format=tar", base],
            cwd=str(repo_root),
            capture_output=True, check=True,
        )
        clean = Path(temporary.name) / "clean"
        shutil.rmtree(clean, ignore_errors=True)
        clean.mkdir()
        with tarfile.open(fileobj=io.BytesIO(arch2.stdout)) as tf:
            tf.extractall(clean, filter="data")
        out: list[tuple[Path, str]] = []
        seen: set[Path] = set()
        for f in sorted(scratch.rglob("*"), key=lambda p: p.relative_to(scratch).as_posix()):
            if not f.is_file() or f.is_symlink():
                continue
            rel = f.relative_to(scratch)
            if any(part.startswith(".") and part not in (".aisef", ".bench")
                   for part in rel.parts):
                continue
            if any(part == "node_modules" for part in rel.parts):
                continue
            clean_path = clean / rel
            if clean_path.is_file() and clean_path.read_bytes() == f.read_bytes():
                continue
            if is_test_path(rel.as_posix()):
                continue
            if rel in seen:
                continue
            seen.add(rel)
            out.append((rel, f.read_text(encoding="utf-8", errors="replace")))
        return out
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        temporary.cleanup()


def _apply_gold(workdir: Path, files: list[tuple[Path, str]]) -> int:
    """Write each ``(path, content)`` pair to the workdir.  Return count."""
    if not files:
        return 0
    for rel, body in files:
        target = workdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return len(files)


def _revert_files(workdir: Path, files: list[tuple[Path, str]],
                  base_sha: str) -> int:
    """Restore source files from the materialized workdir base commit."""
    if not base_sha or not files:
        return 0
    import subprocess

    subprocess.run(["git", "cat-file", "-e", f"{base_sha}^{{commit}}"],
                   cwd=workdir, capture_output=True, check=True)
    restored = []
    for rel, _ in files:
        entry = subprocess.run(
            ["git", "ls-tree", "-z", base_sha, "--", rel.as_posix()],
            cwd=workdir, capture_output=True, check=True,
        )
        body = None
        if entry.stdout:
            body = subprocess.run(
                ["git", "show", f"{base_sha}:{rel.as_posix()}"],
                cwd=workdir, capture_output=True, check=True,
            ).stdout
        restored.append((rel, body))
    n = 0
    for rel, body in restored:
        target = workdir / rel
        if body is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            n += 1
        elif target.exists():
            target.unlink()
            n += 1
    return n


def _aisef_root() -> Path:
    """Best-effort path to the AISEF project root.  Used by callers that
    only have a workdir or task dir to walk up from.
    """
    return Path(os.environ.get("AISEF_BENCH_AISEF_ROOT")
                or Path.cwd()).resolve()


class SimulatedWeakAdapter(ClientAdapter):
    """A bench-only client adapter that applies a known strategy to the
    worktree.  See module docstring for the design contract.
    """

    id = BINARY

    def available(self) -> bool:
        # Always available — no real binary required.
        return True

    def capabilities(self) -> dict[Capability, Support]:
        return {
            Capability.HEADLESS: Support.NATIVE,
            # The simulator writes files directly, so MACHINE_OUTPUT is
            # "emulated" in the sense that the bench harness can read
            # what was written — but it is worth being precise: this is
            # not a real machine-readable stream from an LLM.
            Capability.MACHINE_OUTPUT: Support.EMULATED,  # emulated by: aisef.clients.simulated._read_gold
            Capability.PRE_TOOL_GUARD: Support.UNSUPPORTED,
            Capability.TOOL_ALLOWLIST: Support.UNSUPPORTED,
            Capability.DIR_ALLOWLIST: Support.UNSUPPORTED,
            Capability.SUBAGENT: Support.UNSUPPORTED,
            Capability.MODEL_ROUTING: Support.UNSUPPORTED,
            Capability.COST_REPORTING: Support.NATIVE,  # 0, real cost is 0
            Capability.TURN_LIMIT: Support.NATIVE,        # 1, deterministic
        }

    def run(self, spec: RunSpec) -> RunResult:
        started = time.monotonic()
        res = RunResult(ok=True, num_turns=1)

        # The bench wires context through ``spec.env``; the simulator
        # reads the same dict directly instead of going through
        # ``os.environ`` (the subprocess route would apply to a real
        # CLI, but the simulator is a library call).
        env = dict(spec.env or {})
        task_dir_env = env.get("AISEF_BENCH_TASK_DIR") or os.environ.get("AISEF_BENCH_TASK_DIR")
        attempt = env.get("AISEF_BENCH_ATTEMPT") or os.environ.get("AISEF_BENCH_ATTEMPT") or "1"
        base_sha = env.get("AISEF_BENCH_BASE_SHA") or os.environ.get("AISEF_BENCH_BASE_SHA") or ""
        root_env = env.get("AISEF_BENCH_AISEF_ROOT") or os.environ.get("AISEF_BENCH_AISEF_ROOT")
        ws = Path(spec.workdir)
        files = []

        applied = 0
        import subprocess
        import tarfile

        try:
            attempt_n = int(attempt)
            strategy = ["gold", "noop", "partial", "revert"][(attempt_n - 1) % 4]
            if task_dir_env and strategy != "noop":
                files = _read_gold(Path(task_dir_env), Path(root_env) if root_env else None)
            if strategy == "gold":
                applied = _apply_gold(ws, files)
                res.text = f"simulated-weak strategy=gold wrote {applied} files"
            elif strategy == "noop":
                res.text = "simulated-weak strategy=noop wrote nothing"
            elif strategy == "partial":
                head = files[:1] if files else []
                applied = _apply_gold(ws, head)
                res.text = (
                    f"simulated-weak strategy=partial wrote {applied}/{len(files)} files"
                )
            elif strategy == "revert":
                applied = _revert_files(ws, files, base_sha)
                res.text = f"simulated-weak strategy=revert restored {applied} files"
            res.raw_result = {"strategy": strategy, "files_touched": applied,
                              "task_dir_present": bool(task_dir_env)}
        except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as e:
            res.ok = False
            res.error = f"simulator I/O failed: {e}"
        res.duration_ms = int((time.monotonic() - started) * 1000)
        return res


__all__ = ["BINARY", "SimulatedWeakAdapter"]
