"""V2.1 Q5-KERNEL-COMPARISON — every Q5 corpus item, 2.0's and 2.1's, under the v2.0.0 kernel and under this tree's
(owner B-03d, RELEASE-DECISIONS seq 5: each changed expectation traced to behavioural evidence). An ENGINEERING
MEASUREMENT for the B-03d ruling (validation/qualification/v21_q5_changes.py cites it); never a Q5 rung, never 2.0's.

    python -P validation/qualification/v21_q5_compare.py --write [--out PATH]   # closure-evidence/v2/v2.1/Q5-KERNEL-COMPARISON.json
    python -P validation/qualification/v21_q5_compare.py --check [--out PATH]   # exit 1 unless the record binds this tree

The items: q5.CORPUS (2.1's), and each item of 2.0's last corpus (release/Q5-RC2) that q5.CORPUS no longer has, rebuilt
from its corpus record's definition; an item in both must have RC2's definition exactly. Each is recorded and replayed
(q5.execute, as tests/v2/test_p9_reproduction does: temporary directories only, the item's scripted model stream, no
provider) in a fresh interpreter whose aisef2 is the v2.0.0 tree (c2_orchestration_repair.materialise, read from git)
and in one whose aisef2 is this tree's; the harness is this tree's q5 in both, its fixture (tests/v2) each kernel tree's
own, the sources of the fixture helpers q5 calls recorded per tree and required equal. Each process binds the kernel it imported
(c2_orchestration_repair._neutral neutralises exactly that identity in the journals). Classification of an item:
`identical` — no observation differs; `identity-only` — every differing field is a derived identity (IDENTITY_KEYS, the
criteria's semantic hashes, a process-range name differing only by its spec id); `differs` — anything else. Every
differing field is listed; a leaf only one side has, or not a string on both, is never an identity. Each side records the
digests its probes evaluated with. --write opens its output with mode "x", refuses any path in the repository outside
closure-evidence/v2/v2.1/ (by path or file identity), and refuses a tree whose aisef2/, tests/v2/ or validation/ is not
committed (before measuring and after: the record names the commit it measured). --check re-derives the bindings (q5.py,
this tool, q5's fixture helpers, both kernel digests) and the definitions, and requires a clean measured tree, the
record's 2.1 side to meet q5.CORPUS's expected outcomes, its v2.0.0 side of 2.0's post-merge-regression to be what
release/Q5-RC2 recorded, the probe digests and the classification v21_q5_changes states; the executions are --write's,
read as recorded.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import c2_orchestration_repair as rp  # noqa: E402
from validation.qualification import common as C  # noqa: E402
from validation.qualification import v21_q5_changes as X  # noqa: E402

OUT_REL = X.COMPARISON_REL
V21_DIR = "closure-evidence/v2/v2.1"
RC2 = "closure-evidence/v2/release/Q5-RC2"
FIXTURE_REL = "tests/v2/test_p6_orchestration.py"
FIXTURE_HELPERS = ("contract", "land", "make_repo", "obligation", "plan_of")   # q5.execute calls these (T.git is the kernel's)
DEPENDS = ("aisef2", "tests/v2", "validation")   # committed when measured: the record's execution_commit then names them all
IDENTITY_KEYS = frozenset({"plan_hash", "probe_digest", "record_digest", "request_hash", "semantic_hash", "spec_id"})
SPEC_ID = re.compile(r"PPS-[0-9a-f]{64}")
METHOD = ("every item of q5.CORPUS (2.1) and of release/Q5-RC2's corpus (2.0; an item q5.CORPUS no longer has rebuilt from its "
          "record's definition) recorded and replayed with q5.execute in temporary directories, its scripted model stream, no "
          "provider, in a fresh interpreter whose aisef2 is the v2.0.0 tree (materialised from git) and in one whose aisef2 is "
          "this tree's; this tree's q5 in both, its fixture (tests/v2) each kernel tree's own (the helpers q5 calls: their sources "
          "recorded, required equal); the kernel's own identity neutralised (c2_orchestration_repair._neutral). "
          "identical: no observation differs; identity-only: every differing field is a derived identity (" + ", ".join(sorted(IDENTITY_KEYS))
          + ", a criterion's semantic hash in a request, a process-range name differing only by its spec id); differs: anything else")
CHILD = """
import sys
kernel, root, out = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path[:0] = [p for p in (kernel, root) if p]
import aisef2
from validation.qualification import v21_q5_compare as M
M.job(out)
"""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------------- the items

def rebuild(item_id: str, rec: dict):
    """A q5 Item from a corpus record (its covers and definition)."""
    from validation.qualification import q5
    d = rec["definition"]
    stories = tuple(q5.Story(s["id"], tuple(map(tuple, s["obligations"])), tuple(s["tests"]), tuple(s["regressions"]), s["tests_block"])
                    for s in d["stories"])
    return q5.Item(item_id, tuple(rec["covers"]), stories, tuple(d["developer"]), tuple(d["reviewer"]), d["pre_landed"],
                   tuple((f[0], f[1], tuple(f[2])) for f in d["scanner_findings"]), d["limits"], d["expected_outcomes"])


def items() -> list[tuple]:
    """(item, in 2.0's corpus, in 2.1's): q5.CORPUS, then each RC2 item q5.CORPUS no longer has, rebuilt."""
    from validation.qualification import q5
    rc2 = json.loads((ROOT / RC2 / "CORPUS.json").read_text(encoding="utf-8"))["items"]
    have = {i.id for i in q5.CORPUS}
    return [(i, i.id in rc2, True) for i in q5.CORPUS] + [
        (rebuild(k, json.loads((ROOT / RC2 / "corpus" / f"{k}.json").read_text(encoding="utf-8"))), True, False) for k in sorted(set(rc2) - have)]


def definition_problems() -> list[str]:
    """Every item measured as 2.0's is RC2's: its definition and covers exactly as RC2 recorded them (2.0 had no
    lands_after); a rebuilt one is proved by the Cycle-1 contracts (no kind recorded)."""
    from validation.qualification import q5
    out = []
    for item, in_2_0, in_2_1 in items():
        if not in_2_0:
            continue
        rec = json.loads((ROOT / RC2 / "corpus" / f"{item.id}.json").read_text(encoding="utf-8"))
        mine = json.loads(json.dumps(q5.definition(item)))
        if mine.pop("lands_after") or mine != rec["definition"] or list(item.covers) != rec["covers"]:
            out.append(f"{item.id}: the definition measured is not {RC2}'s")
        if not in_2_1 and not all(cid in q5.CONTRACTS for st in item.stories for cid, _ in st.obligations):
            out.append(f"{item.id}: rebuilt with a criterion outside q5.CONTRACTS (its kind is not recorded)")
    return out


# --------------------------------------------------------------------------------------------- one kernel

def fixture_helpers(path: pathlib.Path) -> dict[str, str]:
    """sha256 of the source of each fixture function q5.execute calls."""
    src = path.read_text(encoding="utf-8")
    nodes = {n.name: n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
    return {k: _sha(ast.get_source_segment(src, nodes[k]).encode()) for k in FIXTURE_HELPERS}


def observation(base: dict, replay: dict) -> dict:
    """What an item's record and replay observed, the kernel's own identity neutralised; a note's first line only (a
    traceback carries temporary paths)."""
    return {"outcomes": base["outcomes"], "errors": {k: n for k, n in base["errors"].items() if n},
            "notes": [n.splitlines()[0][:300] for n in base["notes"] if n], "consumption": base["consumption"],
            "model_requests": base["model_requests"], "requests": [r["request"] for r in base["model_ledger"]],
            "replay_failure": base.get("replay_failure"), "tool_ledger": base["tool_ledger"], "subprocesses": base.get("subprocesses"),
            "initial_workspace": base.get("initial_workspace"), "final_workspace": base.get("final_workspace"),
            "journal": rp._neutral(base.get("journal") or []),
            "replay": {"status": replay["status"], "errors": {k: n for k, n in replay["errors"].items() if n},
                       "model_calls": replay["model_calls"]["observed"]}}


def job(out: str) -> None:
    """In the child: every item recorded and replayed under the aisef2 this process imported."""
    import aisef2
    from tests.v2 import test_p6_orchestration as T
    from validation.qualification import q5
    kernel = pathlib.Path(aisef2.__file__).resolve().parent
    q5.kernel_digest = lambda: rp.kernel_digest(kernel)   # the kernel this process imported, not the working tree's
    res = {"kernel_file": aisef2.__file__, "kernel_digest": rp.kernel_digest(kernel), "fixture_file": T.__file__,
           "fixture_helpers": fixture_helpers(pathlib.Path(T.__file__)), "items": {}}
    for item, _, _ in items():
        base = q5.execute(item, "record")
        res["items"][item.id] = observation(base, q5.compare(base, q5.execute(item, "replay", ledger=base["model_ledger"])))
    pathlib.Path(out).write_text(json.dumps(res, default=str), encoding="utf-8")


def in_kernel(kernel_root: pathlib.Path | None, out: pathlib.Path) -> dict:
    """job() in a fresh interpreter whose aisef2 is the one under `kernel_root` (None: this tree's); -B: no bytecode."""
    r = subprocess.run([sys.executable, "-P", "-B", "-c", CHILD, str(kernel_root or ""), str(ROOT), str(out)], cwd=ROOT,
                       capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode or not out.exists():
        raise SystemExit(f"under {kernel_root or 'this tree'} the job exited {r.returncode}:\n{(r.stdout + r.stderr)[-4000:]}")
    res = json.loads(out.read_text(encoding="utf-8"))
    want = (kernel_root or ROOT) / "aisef2"
    if pathlib.Path(res["kernel_file"]).resolve().parent != want.resolve():
        raise SystemExit(f"imported {res['kernel_file']}, not the kernel under {want}")
    return res


# --------------------------------------------------------------------------------------------- comparison

def _leaves(a, b, at: str = ""):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            yield from _leaves(a.get(k), b.get(k), f"{at}.{k}" if at else k)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            yield from _leaves(x, y, f"{at}[{i}]")
    elif a != b:
        yield at, a, b


def is_identity(path: str, a, b) -> bool:
    """A derived identity whose value moved; a leaf one side lacks (or holds as None or a non-string) is structure."""
    if not (isinstance(a, str) and isinstance(b, str)):
        return False
    keys = re.sub(r"\[\d+\]", "", path).split(".")
    return keys[-1] in IDENTITY_KEYS or keys[-2:-1] == ["semantic_hashes"] or (
        keys[-1] == "resource" and SPEC_ID.sub("PPS-", a) == SPEC_ID.sub("PPS-", b))


def _field(obs: dict, path: str) -> str:
    """A differing leaf's name without indices; a journal leaf named by its event's type."""
    m = re.match(r"journal\[(\d+)\]\.(.+)", path)
    bare = re.sub(r"\[\d+\]", "[]", m[2] if m else path)
    return f"journal {obs['journal'][int(m[1])]['type']}: {bare}" if m else bare


def classify(old: dict, new: dict) -> dict:
    """identical / identity-only / differs, with every differing field (index-free, counted)."""
    leaves = list(_leaves(old, new))
    fields: dict[str, dict[str, int]] = {"identity": {}, "other": {}}
    for path, a, b in leaves:
        bucket = fields["identity" if is_identity(path, a, b) else "other"]
        name = _field(old, path)
        bucket[name] = bucket.get(name, 0) + 1
    kind = "identical" if not leaves else "differs" if fields["other"] else "identity-only"
    return {"classification": kind, "identity_fields": fields["identity"], "other_fields": fields["other"]}


def summary(obs: dict) -> dict:
    j = obs["journal"]
    refused = obs["replay_failure"]
    probes: dict[str, set] = {}
    for e in j:
        if e["type"] == "probe/evaluated":
            r = e["data"]["record"]
            probes.setdefault(str(r.get("probe_id")), set()).add(str(r.get("probe_digest")))
    return {"outcomes": obs["outcomes"], "errors": obs["errors"], "notes": obs["notes"], "consumption_ok": obs["consumption"]["ok"],
            "model_calls": [f"{r['header_class']} {r['story_id']}" for r in obs["requests"]],
            "refused_request": refused and f"{refused['kind']}: {refused['detail']}",
            "failures": [{"seq": e["seq"], **{k: e["data"].get(k) for k in ("story_id", "code", "owner", "retryable", "detail")}}
                         for e in j if e["type"] == "failure/observed"],
            "gate_checks": [[e["data"]["check"], e["data"]["passed"]] for e in j if e["type"] == "gate/check"],
            "events": len(j), "tool_calls": len(obs["tool_ledger"]), "final_tip": (obs["final_workspace"] or {}).get("tip"),
            "probe_digests": {k: sorted(v) for k, v in sorted(probes.items())},
            "journal_digest": _sha(json.dumps(j, sort_keys=True).encode()), "replay": obs["replay"]}


# --------------------------------------------------------------------------------------------- record

def bindings(v2_0_0_kernel_digest: str | None = None) -> dict:
    """What the measurement depends on, derived now."""
    if v2_0_0_kernel_digest is None:
        with tempfile.TemporaryDirectory(prefix="aisef2-v21-q5-digest-") as t:
            v2_0_0_kernel_digest = rp.materialise(X.V2_0_0, pathlib.Path(t))["kernel_digest"]
    return {"validation/qualification/q5.py": C.lf_sha(HERE / "q5.py"), "validation/qualification/v21_q5_compare.py": C.lf_sha(HERE / "v21_q5_compare.py"),
            "fixture_helpers": fixture_helpers(ROOT / FIXTURE_REL), "kernel_2_1": rp.kernel_digest(ROOT / "aisef2"),
            "kernel_v2_0_0": v2_0_0_kernel_digest}


def refused(out: pathlib.Path) -> str | None:
    from validation.qualification import q5
    p = out.resolve()
    if q5.within(p, ROOT) and not q5.within(p, ROOT / V21_DIR):
        return f"{p} is in the repository outside {V21_DIR} (2.0's records are never written)"
    if p.exists():
        return f"{p} exists (a record is written once)"
    return None


def dirty() -> list[str]:
    """The uncommitted changes under DEPENDS (git status --porcelain)."""
    return [ln for ln in C.git("status", "--porcelain", "--", *DEPENDS).splitlines() if ln.strip()]


def derive() -> dict:
    with tempfile.TemporaryDirectory(prefix="aisef2-v21-q5-compare-") as t:
        t = pathlib.Path(t)
        k200 = rp.materialise(X.V2_0_0, t / "k200")
        runs = {"v2.0.0": in_kernel(t / "k200", t / "v2.0.0.json"), "2.1": in_kernel(None, t / "2.1.json")}
    if runs["v2.0.0"]["kernel_digest"] != k200["kernel_digest"] or runs["2.1"]["kernel_digest"] != rp.kernel_digest(ROOT / "aisef2"):
        raise SystemExit("a child measured another kernel than the one it was given")
    out = {}
    for item, in_2_0, in_2_1 in items():
        old, new = runs["v2.0.0"]["items"][item.id], runs["2.1"]["items"][item.id]
        out[item.id] = {"in_2_0_corpus": in_2_0, "in_2_1_corpus": in_2_1, "expected_outcomes": item.expected_outcomes,
                        "v2.0.0": summary(old), "2.1": summary(new), **classify(old, new)}
    return {
        "record": "AISEF V2.1 — Q5-KERNEL-COMPARISON: every 2.0 and 2.1 Q5 corpus item under the v2.0.0 kernel and the 2.1 kernel",
        "status": "ENGINEERING MEASUREMENT (not owner-approved evidence; cited by validation/qualification/v21_q5_changes.py)",
        "authority": X.DECISION[1], "tool": "validation/qualification/v21_q5_compare.py", "measured_at": C.now(),
        "execution_commit": C.git("rev-parse", "HEAD"), "tree_dirty": dirty(), "bindings": bindings(k200["kernel_digest"]),
        "kernels": {"v2.0.0": {"commit": X.V2_0_0, "aisef2_tree": k200["aisef2_tree"], "kernel_digest": k200["kernel_digest"],
                               "fixture_helpers": runs["v2.0.0"]["fixture_helpers"]},
                    "2.1": {"kernel_digest": runs["2.1"]["kernel_digest"], "fixture_helpers": runs["2.1"]["fixture_helpers"]}},
        "method": METHOD,
        "items": out,
        "summary": {c: sorted(k for k, v in out.items() if v["classification"] == c) for c in ("identical", "identity-only", "differs")},
    }


def _dirty_why(lines: list[str]) -> str:
    return f"{' '.join(DEPENDS)} not committed ({lines[:5]}): measure a committed tree" if lines else ""


def write(out: pathlib.Path) -> int:
    why = refused(out) or _dirty_why(dirty()) or "; ".join(definition_problems())
    if why:
        print(f"REFUSED: {why}")
        return 2
    head = C.git("rev-parse", "HEAD")
    rec = derive()
    if why := _dirty_why(rec["tree_dirty"]):   # the tree moved while it was measured
        print(f"REFUSED: {why}")
        return 2
    if rec["execution_commit"] != head:        # a commit landed while it was measured: the record would name code that did not run
        print(f"REFUSED: HEAD moved from {head[:12]} to {rec['execution_commit'][:12]} while the items were measured")
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as f:
        f.write(C.render(rec))
    print(f"{out}: {rec['summary']}")
    return 0


def probe_digest_problems(rec: dict) -> list[str]:
    """The identity-only items' probes, per probe and side, are the one digest each UNCHANGED states (by prefix)."""
    stated = X.UNCHANGED["identity_only"]
    kind_of = {pid: kind for kind, pid in stated["probe_ids_by_kind"].items()}
    got: dict[str, tuple[set, set]] = {}
    for item in stated["items"]:
        for i, side in enumerate(("v2.0.0", "2.1")):
            for pid, ds in ((((rec["items"].get(item) or {}).get(side) or {}).get("probe_digests")) or {}).items():
                got.setdefault(pid, (set(), set()))[i].update(ds)
    if set(got) != set(kind_of):
        return [f"probes measured {sorted(got)}, v21_q5_changes states {sorted(kind_of)}"]
    out = []
    for pid, (old, new) in sorted(got.items()):
        want = stated["probe_digests_by_kind"][kind_of[pid]]
        if not (len(old) == len(new) == 1 and min(old).startswith(want[0]) and min(new).startswith(want[1])):
            out.append(f"{pid}: measured {sorted(old)} -> {sorted(new)}, v21_q5_changes states {want[0]} -> {want[1]}")
    return out


def check(path: pathlib.Path | None = None) -> list[str]:
    from validation.qualification import q5
    path = path or ROOT / OUT_REL
    if not path.exists():
        return [f"{path}: no record (v21_q5_compare.py --write)"]
    rec = json.loads(path.read_text(encoding="utf-8"))
    now = bindings()
    out = [f"stale: {k} recorded {rec['bindings'].get(k)}, now {v}" for k, v in now.items() if rec["bindings"].get(k) != v]
    out += [f"stale: {k} recorded, not derived" for k in sorted(set(rec["bindings"]) - set(now))]
    out += definition_problems()
    if rec.get("tree_dirty") != []:
        out.append(f"measured on a tree with uncommitted changes: {rec.get('tree_dirty')}")
    measured = {(k, v["in_2_0_corpus"], v["in_2_1_corpus"]) for k, v in rec["items"].items()}
    if measured != {(i.id, a, b) for i, a, b in items()}:
        out.append(f"the items measured are not 2.0's and 2.1's corpora: {sorted(measured)}")
    for item in q5.CORPUS:
        got = (rec["items"].get(item.id) or {}).get("2.1") or {}
        if (got.get("outcomes"), got.get("consumption_ok"), (got.get("replay") or {}).get("status")) != (item.expected_outcomes, True, "GREEN"):
            out.append(f"{item.id}: 2.1 measured {got.get('outcomes')} consumed {got.get('consumption_ok')} replay "
                       f"{(got.get('replay') or {}).get('status')}; q5.CORPUS expects {item.expected_outcomes}, every answer consumed, GREEN")
    q = X.RC2_POST_MERGE_REGRESSION
    old = (rec["items"].get(q["item"]) or {}).get("v2.0.0") or {}
    if (old.get("outcomes"), len(old.get("model_calls") or ()), old.get("tool_calls"), old.get("events"), old.get("failures")) != (
            q["outcomes"], q["model_calls"], q["tool_calls"], q["events"], [q["failure"]]):
        out.append(f"{q['item']}: the v2.0.0 kernel did not measure what {q['source']} recorded")
    out += probe_digest_problems(rec)
    by_class = {c: sorted(k for k, v in rec["items"].items() if v["classification"] == c) for c in ("identical", "identity-only", "differs")}
    stated = {"identical": sorted(X.UNCHANGED["identical_up_to_kernel_identity"]), "identity-only": sorted(X.UNCHANGED["identity_only"]["items"]),
              "differs": sorted(set(X.CHANGES) | {X.RC2_POST_MERGE_REGRESSION["item"]})}
    if rec["kernels"]["v2.0.0"]["fixture_helpers"] != rec["kernels"]["2.1"]["fixture_helpers"]:
        out.append("q5's fixture helpers differ between the two kernels' trees: the comparison is not the kernels' alone")
    if rec["summary"] != by_class:
        out.append("the summary is not the items' classification")
    out += [f"{c}: measured {by_class[c]}, v21_q5_changes states {stated[c]}" for c in stated if by_class[c] != stated[c]]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=OUT_REL)
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out) if os.path.isabs(a.out) else ROOT / a.out
    if a.write:
        return write(out)
    problems = check(out)
    for p in problems:
        print(f"  {p}")
    print(f"Q5-KERNEL-COMPARISON {'PASS' if not problems else 'FAIL'}: {out}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
