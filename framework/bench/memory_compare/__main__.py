"""CLI: run the paired A/B/C memory harness or refresh the lock.

Usage::

    python3 -m framework.bench.memory_compare run [--attempts 3]
    python3 -m framework.bench.memory_compare score
    python3 -m framework.bench.memory_compare --write-lock
    python3 -m framework.bench.memory_compare --check-lock

All operations are offline. The harness never imports a remote model or
contacts a remote service. ``AISEF_MEMORY_BENCH_FORCE=1`` allows running
when ``HEAD`` is no longer the lock's candidate_sha; this is the only
override supported.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="framework.bench.memory_compare")
    parser.add_argument("command", choices=("run", "score", "recheck-lock"),
                        nargs="?", default="run")
    parser.add_argument("--attempts", type=int, default=3,
                        help="attempts per (arm, scenario) pair (default 3)")
    parser.add_argument("--scenarios", nargs="*",
                        help="restrict to specific scenario ids")
    parser.add_argument("--write-lock", action="store_true",
                        help="(re)generate the lock file at HEAD")
    parser.add_argument("--check-lock", action="store_true",
                        help="verify the lock matches the working tree")
    parser.add_argument("--out-dir", default=str(Path(__file__).parent / "results"),
                        help="where to write per-arm result JSONs and score.json")
    args = parser.parse_args(argv)

    from framework.bench.memory_compare import lock as L
    from framework.bench.memory_compare import runner, scoring

    out_dir = Path(args.out_dir)

    if args.write_lock:
        snap = L.lock_signature(ROOT)
        L.LOCK_PATH.write_text(snap.to_json(), encoding="utf-8")
        print(f"wrote lock {L.LOCK_PATH}")
        print(f"  candidate: {snap.candidate_sha}")
        print(f"  signature: {snap.signature}")
        return 0

    if args.check_lock:
        try:
            L.verify_lock(ROOT, L.LOCK_PATH)
        except L.LockMismatch as exc:
            print(f"LOCK MISMATCH: {exc}", file=sys.stderr)
            return 2
        print(f"lock OK: {L.LOCK_PATH}")
        return 0

    if args.command == "run":
        from framework.bench.memory_compare.runner import RunnerConfig
        cfg = RunnerConfig(results_dir=out_dir)
        results = runner.run_all(scenario_ids=args.scenarios, attempts=args.attempts, cfg=cfg)
        total = sum(len(paths) for paths in results.values())
        print(f"wrote {total} per-arm result files under {out_dir}")
        score_result = scoring.score_from_results(out_dir)
        json_path = scoring.score_to_json(score_result, out_dir)
        md_path = scoring.score_to_markdown(score_result, out_dir)
        print(f"score.json -> {json_path}")
        print(f"score.md   -> {md_path}")
        return 0

    if args.command == "score":
        score_result = scoring.score_from_results(out_dir)
        scoring.score_to_json(score_result, out_dir)
        scoring.score_to_markdown(score_result, out_dir)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
