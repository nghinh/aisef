"""kill_check.py TARGET TEST_FILE... [--only I,J,...] [--out FILE.json]

Which mutants of TARGET do these kill files kill — by the runner's own bracket (`run_target`: the mutant FAILs, the
unmutated module PASSes twice, the mutant FAILs again with the same signature) — and nothing else. The target's own
kill set is NOT used: this is for a test written to kill survivors, to show that it does and that it passes the
unmutated module (T0). Not a measurement of record: no record is written, and a result of record needs the file in the
target's kill set (`validation/v2/mutation.py`, `_V21_KILLS`) and a run of the whole target.

Run it from a tree that holds the runner and the files, through a wrapper that gives the kill tests an environment
without `opencode` on PATH (the runner builds the kill tests' environment from its own allowlist; PATH is one of
them). `--only`: the mutants' positions in the target's list (the `[N]` of `survivor_view.py`); the others are not run.
Output: one line per mutant run and a summary; `--out`: the same as JSON with each kill's file and failing test.
Exit 0 when every mutant run is KILLED, 1 otherwise, 2 on refusal (T0 not passing: the file is not usable)."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from validation.v2 import mutation as m  # noqa: E402


def only_positions(full, only: set[int]):
    """`mutants` restricted to the listed positions of the OUTER list. `mutants` of a `SCRIPT/function` target calls
    itself through the module global this replaces, so a filter applied at every level also filtered the inner list
    (the child script's) by the same positions and dropped what the outer positions named."""
    depth = [0]

    def some(src, func, enums):
        depth[0] += 1
        try:
            got = full(src, func, enums)
        finally:
            depth[0] -= 1
        return got if depth[0] else [x for i, x in enumerate(got) if i in only]
    return some


def main(argv: list[str]) -> int:
    only = out = None
    args = list(argv)
    for flag in ("--only", "--out"):
        if flag in args:
            i = args.index(flag)
            val = args[i + 1]
            del args[i:i + 2]
            if flag == "--only":
                only = {int(x) for x in val.split(",") if x}
            else:
                out = pathlib.Path(val)
    if len(args) < 2:
        print(__doc__)
        return 2
    target, files = args[0], args[1:]
    if only is not None:
        full = m.mutants
        src = (ROOT / target.split("::")[0]).read_text(encoding="utf-8")
        # the descriptions of the listed positions, taken from the unfiltered list BEFORE the filter is installed
        names = [d for i, (d, _) in enumerate(full(src, target.split("::")[1], m._enum_members(src, ROOT))) if i in only]
        m.mutants = only_positions(full, only)
        positions = sorted(only)
    r = m.run_target(ROOT, target, files)
    if r.get("error") and not r.get("results"):
        print(f"REFUSED: {r['error']}")
        return 2
    rows = []
    for k, res in enumerate(r["results"]):
        pos = positions[k] if only is not None else k
        kb = res.get("killed_by") or {}
        rows.append({"index": pos, "mutant": res["mutant"], "class": res["class"], "file": kb.get("file"),
                     "first": kb.get("first")})
        print(f"[{pos}] {res['class']:8s} {res['mutant']}" + (f"  <- {kb.get('first')}" if kb else ""))
    if only is not None:
        assert [x["mutant"] for x in rows] == names, "positions and descriptions disagree"
    by = {}
    for x in rows:
        by[x["class"]] = by.get(x["class"], 0) + 1
    t0 = [{k: v for k, v in x.items() if k in ("file", "outcome", "ran", "seconds")} for x in r.get("t0", [])]
    print(f"# {target}: {len(rows)} mutants run, {by}; T0 {t0}; source_sha256 {r.get('source_sha256')}")
    if out:
        out.write_text(json.dumps({"target": target, "files": files, "source_sha256": r.get("source_sha256"), "t0": t0,
                                   "error": r.get("error"), "results": rows}, indent=1) + "\n", encoding="utf-8")
    return 0 if rows and all(x["class"] == "KILLED" for x in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
