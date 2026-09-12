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
  * ``partial``: apply only the first non-test hunk from ``gold.patch``
    (should FAIL — fix is incomplete).
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
import time
from pathlib import Path

from .base import Capability, ClientAdapter, RunSpec, Support
from .stream import RunResult

BINARY = "simulated-weak"


def _read_gold(task_dir: Path) -> list[tuple[Path, str]]:
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

    scratch = task_dir / ".sim_scratch"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    clean: Path | None = None
    # Resolve the AISEF project root.  In production, ``_runner.run``
    # sets ``AISEF_BENCH_AISEF_ROOT`` explicitly; for unit tests we
    # accept either the env or a walk-up the task-dir tree.  ``task_dir``
    # is ``<aisef>/tests/bench/tasks/<id>/`` in both cases, so four
    # levels up is the repo root.
    repo_root = Path(os.environ.get("AISEF_BENCH_AISEF_ROOT")
                     or task_dir.parent.parent.parent.parent)
    try:
        arch = subprocess.run(
            ["git", "archive", "--format=tar", base],
            cwd=str(repo_root),
            capture_output=True, check=True,
        )
        with tarfile.open(fileobj=io.BytesIO(arch.stdout)) as tf:
            tf.extractall(scratch, filter="data")
        # Use GNU ``patch`` rather than ``git apply``: a clean
        # ``git apply`` from a non-worktree directory emits
        # ``Skipped patch 'aisef/phases/...'.`` for any hunk that does
        # not match byte-for-byte (observed 2026-09-12 on
        # ``bug-a2-state-1/gold.patch``: no error, no apply, the file
        # stays the pre-image).  ``patch`` applies the same diff with
        # the same exit-code contract and is what the validate step
        # already uses elsewhere in the bench.
        proc = subprocess.run(
            ["patch", "-p1", "--binary", "-d", str(scratch), "-i", str(patch.resolve())],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            return []
        # Find all files that differ from a fresh extraction.
        arch2 = subprocess.run(
            ["git", "archive", "--format=tar", base],
            cwd=str(repo_root),
            capture_output=True, check=True,
        )
        clean = task_dir / ".sim_clean"
        shutil.rmtree(clean, ignore_errors=True)
        clean.mkdir()
        with tarfile.open(fileobj=io.BytesIO(arch2.stdout)) as tf:
            tf.extractall(clean, filter="data")
        out: list[tuple[Path, str]] = []
        seen: set[Path] = set()
        for f in scratch.rglob("*"):
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
            if "tests/" in rel.parts:
                continue
            if rel in seen:
                continue
            seen.add(rel)
            out.append((rel, f.read_text(encoding="utf-8", errors="replace")))
        return out
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if clean is not None and clean.exists():
            shutil.rmtree(clean, ignore_errors=True)


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
    """Restore each file touched by ``gold.patch`` to its pre-image at
    ``base_sha``.  Falls back to delete if the file is new at the gold
    version.  Count restored.

    Reads ``<base_sha>:<path>`` from the AISEF repo, not the workdir:
    a fresh worktree's object DB only has its own HEAD, and the base
    SHA may be dangling.  The bench ``_runner`` sets
    ``AISEF_BENCH_AISEF_ROOT``; fall back to walking up ``workdir``
    for unit tests that already start from the AISEF repo.
    """
    if not base_sha or not files:
        return 0
    import subprocess

    repo = Path(os.environ.get("AISEF_BENCH_AISEF_ROOT")
                or workdir.parent.parent.parent.parent).resolve()
    n = 0
    for rel, _ in files:
        rel_s = str(rel)
        proc = subprocess.run(
            ["git", "show", f"{base_sha}:{rel_s}"],
            cwd=str(repo), capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode == 0:
            target = workdir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(proc.stdout, encoding="utf-8")
            n += 1
        else:
            target = workdir / rel
            if target.exists():
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
        attempt_n = int(env.get("AISEF_BENCH_ATTEMPT")
                        or os.environ.get("AISEF_BENCH_ATTEMPT") or "1")
        base_sha = env.get("AISEF_BENCH_BASE_SHA") or os.environ.get("AISEF_BENCH_BASE_SHA") or ""
        # ``_read_gold`` picks up ``AISEF_BENCH_AISEF_ROOT`` itself; we
        # only need to keep it consistent across this call and ``_read_gold``.
        ws = Path(spec.workdir)
        if task_dir_env:
            files = _read_gold(Path(task_dir_env))
        else:
            files = []

        strategy = ["gold", "noop", "partial", "revert"][(attempt_n - 1) % 4]
        applied = 0
        try:
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
        except OSError as e:
            res.ok = False
            res.error = f"simulator I/O failed: {e}"
        res.duration_ms = int((time.monotonic() - started) * 1000)
        return res


__all__ = ["BINARY", "SimulatedWeakAdapter"]
