"""P7-FINDING-001 — the deterministic reproducer run against the old semantic candidate and the corrected one
(owner's kernel correction authorization §28: the reproducer fails on the old candidate and passes on the corrected
one; §6: which mechanism carries correctness).

    python -P validation/qualification/p7_finding_001_reproducer.py [--old 097daefefd9229eafeacaca321b7a008a581899b] [--write]

The scenario is tests/v2/test_p7_finding_001.py's PYC-1: a checkout whose app/mod.py holds source B beside
app/__pycache__/mod.<tag>.pyc compiled from source A (same size, one character apart), the source dated to the
bytecode's header second — the collision that let an interpreter reading in-tree bytecode take the stale code. The
old candidate's probe module is read from git at `--old` (its `probe/protocol.py` beside it, so its digest computes
to what that candidate declared) and loaded as a module of its own; the current one is the tree's. Both observe the
same checkout with the same spec input. Recorded: each probe's digest, the harness command line it launched, and its
verdict; then the corrected probe under two controlled mutants — without -B (the external cache alone) and without
the external cache (-B alone) — so the record says which control carries correctness. Nothing is timed, nothing
sleeps; the state is constructed. With --write the record goes to closure-evidence/v2/P7-FINDING-001/REPRODUCER.json.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import time
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict as V, Enforcement  # noqa: E402
from aisef2.probe import python_callable as pc  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, bound_result, run_probe  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402
from tests.v2 import test_p7_finding_001 as T  # noqa: E402

OUT_REL = "closure-evidence/v2/P7-FINDING-001/REPRODUCER.json"
OLD_CANDIDATE = "097daefefd9229eafeacaca321b7a008a581899b"
ENV = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL)


def git_show(rev: str, rel: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{rel}"], capture_output=True, check=True).stdout


def load_old_probe(rev: str, into: pathlib.Path):
    """The probe module of `rev`, loaded from a copy of its two sources laid out as the digest expects them."""
    probe_dir = into / "aisef2old" / "probe"
    probe_dir.mkdir(parents=True)
    for rel in ("probe/protocol.py", "probe/python_callable.py"):
        (into / "aisef2old" / rel).write_bytes(git_show(rev, f"aisef2/{rel}"))
    spec = importlib.util.spec_from_file_location("aisef2old_python_callable", probe_dir / "python_callable.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def spec_for(module, observable):
    return ProductProofSpec.create(
        contract_id="BC-PYC", probe_id=module.PROBE_ID, probe_digest=module.DIGEST,
        probe_input={"subject": {"kind": "python_callable", "locator": "app.mod:f"}, "stimulus": {},
                     "observable": observable, "subject_absence": "REQUIRES_SUBJECT"},
        candidate_expectation=V.SATISFIED, compiler_id="reproducer", compiler_digest="c" * 64)


def observe(module, probe, root: pathlib.Path) -> dict:
    """One evaluation of PYC-1's spec (returns 2: the source's behaviour; the stale bytecode returns 1)."""
    launched = []
    real = module.ProcessRange

    def make(name, argv, **kw):
        launched.append([str(a) for a in argv])
        return real(name, argv, **kw)
    s = spec_for(module, T.RETURNS_2)
    with mock.patch.object(module, "ProcessRange", make):
        record = run_probe(probe, s, RevisionRef("a" * 40, str(root)), ENV)
    result = bound_result(record, spec=s, revision="a" * 40, enforcement=Enforcement.PARTIAL)   # PROBE-BIND-1: through the binding
    argv = launched[0] if launched else None
    return {"probe_digest": probe.digest, "record_digest": record.record_digest,
            "execution_status": result.status.value, "behavior_verdict": result.behavior_verdict.value if isinstance(result, Executed) else None,
            "detail": getattr(result, "detail", None), "harness_argv_flags": [a for a in (argv or [])[1:] if a.startswith("-")][:6],
            "external_pycache_prefix": any(a.startswith("pycache_prefix=") for a in (argv or [])),
            "dont_write_bytecode": "-B" in (argv or []), "observes_the_source": isinstance(result, Executed) and result.behavior_verdict is V.SATISFIED}


def measure(old_candidate: str = OLD_CANDIDATE) -> dict:
    """The whole measurement as a record: the old candidate's probe (from git) and this tree's on one constructed
    checkout, then the two controlled mutants. Raises when the old candidate's sources cannot be read from git (a
    shallow clone): the caller types that as an inability to run, never as a failure."""
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, encoding="utf-8").stdout.strip()
    with tempfile.TemporaryDirectory(prefix="aisef2-repro-") as t:
        tmp = pathlib.Path(t)
        old = load_old_probe(old_candidate, tmp / "old")
        checkout = tmp / "checkout"
        built = T.stale_checkout(checkout)
        before = T.snapshot(checkout)
        runs = {
            "old_candidate": observe(old, old.PythonCallableProbe(), checkout),
            "corrected": observe(pc, pc.PythonCallableProbe(), checkout),
        }
        checkout_after_corrected = T.snapshot(checkout) == before
        with T.WithoutB():
            runs["corrected_without_B (external cache alone)"] = observe(pc, pc.PythonCallableProbe(), checkout)
        with T.WithoutPrefix(keep_b=True):
            runs["corrected_without_external_cache (-B alone)"] = observe(pc, pc.PythonCallableProbe(), checkout)
        old_sources = {rel: hashlib.sha256(git_show(old_candidate, f"aisef2/{rel}")).hexdigest() for rel in ("probe/protocol.py", "probe/python_callable.py")}
    record = {
        "record": "P7-FINDING-001 deterministic reproducer — old candidate vs corrected candidate",
        "finding": "P7-FINDING-001", "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "head": head,
        "scenario": "tests/v2/test_p7_finding_001.py PYC-1: source B beside bytecode of source A (same size), the source dated to the bytecode's header second; spec returns 2 (the source); the stale bytecode returns 1",
        "constructed_state": {k: built[k] for k in ("header_mtime", "header_size", "source_mtime_s", "source_size", "collision")},
        "old_candidate": {"commit": old_candidate, "probe_sources_sha256": old_sources, "probe_digest": old.DIGEST,
                          "digest_is_the_one_the_candidate_declared": old.DIGEST == "ac434a4260cdc1ebbd7e5841959a89c3de8edc2c8552e7714cb85962bc0922a0"},
        "corrected_candidate": {"probe_digest": pc.DIGEST, "checkout_byte_identical_after_the_proof": checkout_after_corrected},
        "runs": runs,
        "verdicts": {
            "old_candidate_fails_the_reproducer": not runs["old_candidate"]["observes_the_source"],
            "corrected_candidate_passes_the_reproducer": runs["corrected"]["observes_the_source"],
            "external_cache_alone_carries_correctness": runs["corrected_without_B (external cache alone)"]["observes_the_source"],
            "B_alone_does_not": not runs["corrected_without_external_cache (-B alone)"]["observes_the_source"],
        },
    }
    record["conclusion"] = ("ESTABLISHED: the old candidate observes the stale bytecode, the corrected one the source; the external "
                            "bytecode cache is the load-bearing control and -B alone is not"
                            if all(record["verdicts"].values()) else "NOT ESTABLISHED — see verdicts")
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default=OLD_CANDIDATE)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    record = measure(a.old)
    runs = record["runs"]
    text = json.dumps(record, indent=1, ensure_ascii=False) + "\n"
    if a.write:
        (ROOT / OUT_REL).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / OUT_REL).write_text(text, encoding="utf-8")
        print(f"wrote {OUT_REL}")
    print(json.dumps({"verdicts": record["verdicts"], "old": runs["old_candidate"]["behavior_verdict"], "new": runs["corrected"]["behavior_verdict"],
                      "old_digest_ok": record["old_candidate"]["digest_is_the_one_the_candidate_declared"]}))
    return 0 if all(record["verdicts"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
