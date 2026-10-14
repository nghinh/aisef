"""trace_paths.py --out R.json [--files F...] [--control-only]

Which kill files RUN a changed path — in any process, a child that builds its own `env=` included?

`reach.py` hooks the Python processes that inherit its PYTHONPATH and says so: it can say a function WAS executed, never
that one was NOT, outside the children it hooked (most kill files start children it cannot see). This tool answers a
narrower question the other way: for a change whose BEHAVIOUR differs from the old code on a described class of inputs
and not elsewhere, does any kill file feed the code that class? The changed paths are marked in the source of the
runner's own fresh tree (a copy of the repository HEAD, `mutation._pristine`) — a one-line call at each path that
differs — so that every process that runs that tree's product code writes a line, whatever its environment or flags.

    {"commit", "tool", "python", "platform", "tree_sha256", "paths": {tag: description}, "controls": [...],
     "kill_files": {kf: {"outcome", "seconds", "hits": {tag: n}, "pids": n}}, "not_passed": {...}, "complete"}

How. `PATCHES` below is the whole of the source edit: (file, text, replacement), each text present exactly once. A
replacement is the text with a call `_aisef_trace(TAG)` added, and `HELPER` (a function appending `kill file<TAB>tag
<TAB>pid` to a file at an absolute path of this run, with the kill file read from `CURRENT` at the moment of the hit)
is appended to each patched module. The kill files run one at a time, each by the runner's own `_run_file` on a fresh
copy of the patched tree (argv, environment allowlist, ProcessRange, judgement, leftovers settled as the runner does).
CURRENT is written before the file and the hits are read after it, so a hit is attributed to the file that ran.

What the marks must be, and are not. A mark stands where the new code's behaviour differs from the old code's; the
claim a consumer may draw is: a kill file with NO hit never reached a path whose behaviour changed, so its outcome on
the unmutated tree is the old code's. Not covered, said here and in the output: (1) a MUTANT may reach a path the
original does not (a mutant of the module that holds the path is re-measured anyway; a mutant elsewhere would have to
manufacture the very input the path is about — a probe output with a try that has no exit status — which no mutant of
another module can); (2) a test that asserts on the bytes of a patched module (a digest of the kernel, the module's
names) fails here and is under `not_passed`, not measured: it clears nothing; (3) `os.write` of one short line: a hit
is lost when the process has no free descriptor (the recorder opens and closes the file per hit); (4) POSIX only.

Exit: 0 every kill file PASSed and the controls held; 1 otherwise; 2 refused (no git, HEAD differs from the tree).
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import cleanup_authority as ca  # noqa: E402
from validation.v2 import mutation as M  # noqa: E402
from validation.v21 import read_set as RS  # noqa: E402

TOOL = "validation/v21/trace_paths.py"

CONFINE = "aisef2/app/confine.py"
RANGE = "aisef2/runtime/process_range.py"

#: tag -> what a hit means
PATHS = {
    "confine._sections:no-status": "the probe's output left a try without an exit status (the marker ran into text)",
    "confine._judge:not-a-pair": "_judge was given a try that is not a (status, text) pair",
    "confine._judge:status-none": "_judge was given a try whose status is None",
    "range._Posix.abort:gone": "_Posix.abort's killpg raised ProcessLookupError or PermissionError",
}

#: (file, text present exactly once, the same text with the mark). Indentation is the text's own.
PATCHES: list[tuple[str, str, str]] = [
    (CONFINE,
     '    return values, sections, {k: v if isinstance(v, tuple) else (None, "\\n".join(v).strip()[:300])\n',
     '    if any(not isinstance(v, tuple) for v in tries.values()):\n'
     '        _aisef_trace("confine._sections:no-status")\n'
     '    return values, sections, {k: v if isinstance(v, tuple) else (None, "\\n".join(v).strip()[:300])\n'),
    (CONFINE,
     '    inside, bad = rep["inside"], []\n    if unran := ',
     '    inside, bad = rep["inside"], []\n'
     '    if any(type(v) is not tuple or len(v) != 2 for v in tries.values()):\n'
     '        _aisef_trace("confine._judge:not-a-pair")\n'
     '    if any(isinstance(v, (tuple, list)) and v and v[0] is None for v in tries.values()):\n'
     '        _aisef_trace("confine._judge:status-none")\n'
     '    if unran := '),
    (RANGE,
     '            except (ProcessLookupError, PermissionError):\n'
     '                # the anchor ended between poll() and the signal',
     '            except (ProcessLookupError, PermissionError):\n'
     '                _aisef_trace("range._Posix.abort:gone")\n'
     '                # the anchor ended between poll() and the signal'),
]

HELPER = '''

def _aisef_trace(tag, _dir={dir!r}):   # appended by validation/v21/trace_paths.py (a copy of the tree, never the repository)
    import os
    try:
        with open(_dir + "/CURRENT", encoding="utf-8") as f:
            cur = f.read().strip()
        fd = os.open(_dir + "/hits.log", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, f"{{cur}}\\t{{tag}}\\t{{os.getpid()}}\\n".encode())
        finally:
            os.close(fd)
    except OSError:
        pass
'''


def patch_tree(tree: pathlib.Path, trace_dir: pathlib.Path) -> list[str]:
    """Apply PATCHES to `tree` (the runner's pristine copy); the files patched."""
    done = []
    for rel in sorted({f for f, _, _ in PATCHES}):
        p = tree / rel
        text = p.read_text(encoding="utf-8")
        for f, old, new in PATCHES:
            if f != rel:
                continue
            if text.count(old) != 1:
                RS.refuse(f"{rel}: the text to mark is present {text.count(old)} times, not once: {old[:60]!r}")
            text = text.replace(old, new)
        p.write_text(text + HELPER.format(dir=str(trace_dir)), encoding="utf-8")
        done.append(rel)
    return done


def hits_of(trace_dir: pathlib.Path) -> dict[str, dict[str, list[int]]]:
    out: dict[str, dict[str, list[int]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    log = trace_dir / "hits.log"
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            kf, tag, pid = line.split("\t")
            out[kf][tag].append(int(pid))
    return out


def controls(tree: pathlib.Path, trace_dir: pathlib.Path) -> list[dict]:
    """Each mark is reached by a child that builds its own environment and runs -E -S (the case the other recorder
    cannot see); the hit must land under the control's name."""
    code = {
        "confine._sections:no-status": (
            "from aisef2.app import confine as c\n"
            "c._sections(c.MARK + 'try x\\ntext' + c.MARK + 'rc 1\\n')\n"),
        "confine._judge:not-a-pair": (
            "from aisef2.app import confine as c\n"
            "try:\n c._judge({'inside': {}}, 't', '', {'x': ['a', 'b', 'c']}, '/h', None)\nexcept Exception: pass\n"),
        "confine._judge:status-none": (
            "from aisef2.app import confine as c\n"
            "try:\n c._judge({'inside': {}}, 't', '', {'x': (None, '')}, '/h', None)\nexcept Exception: pass\n"),
        "range._Posix.abort:gone": (
            "from unittest import mock\nimport signal\nfrom aisef2.runtime import process_range as r\n"
            "class A:\n pid = 7\n def poll(self): return None\n"
            "with mock.patch.object(r.os, 'killpg', side_effect=ProcessLookupError()):\n r._Posix().abort(A())\n"),
    }
    rows = []
    for tag, src in code.items():
        (trace_dir / "CURRENT").write_text(f"control {tag}\n", encoding="utf-8")
        r = subprocess.run([sys.executable, "-E", "-S", "-B", "-c", "import sys; sys.path.insert(0, '.')\n" + src],
                           cwd=tree, env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=120, check=False)
        got = hits_of(trace_dir).get(f"control {tag}", {})
        rows.append({"tag": tag, "ok": tag in got, "got": sorted(got), **({"stderr": r.stderr[-300:]} if tag not in got else {})})
    (trace_dir / "CURRENT").write_text("-\n", encoding="utf-8")
    return rows


def record(root: pathlib.Path, files: list[str], progress=None) -> dict:
    kill_files, not_passed, not_measured = {}, {}, {}
    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aisef-trace-", ignore_cleanup_errors=True) as t:
        scratch = pathlib.Path(t)
        trace = scratch / "trace"
        trace.mkdir()
        pristine, digest = M._pristine(root, scratch / "pristine")
        patched = patch_tree(pristine, trace)
        ctl = controls(pristine, trace)
        tg = M._Target(None, scratch, ca.establish(scratch), "trace-" + M._worker(root), tests=list(files))
        stopped = None
        try:
            for i, rel in enumerate(files):
                if stopped:
                    not_measured[rel] = f"not reached: {stopped}"
                    continue
                if not (pristine / rel).is_file():
                    not_measured[rel] = "not a file of the runner's tree (outside mutation.COPY or missing)"
                    continue
                (trace / "CURRENT").write_text(rel + "\n", encoding="utf-8")
                tg.pristine = pristine
                M._new_tree(tg)
                tg.pristine = None
                rows: list[dict] = []
                try:
                    row = M._run_file(tg, rel, rows, failfast=False, role="trace")
                except M._Stop as e:
                    row, stopped = rows[-1] if rows else {}, str(e)
                    row.setdefault("outcome", "INFRA")
                    row["why"] = str(e)
                got = hits_of(trace).get(rel, {})
                entry = {"outcome": row.get("outcome"), "seconds": row.get("seconds"),
                         "hits": {k: len(v) for k, v in sorted(got.items())}, "pids": len({p for v in got.values() for p in v})}
                for k in ("why", "first"):
                    if row.get(k):
                        entry[k] = row[k]
                (kill_files if entry["outcome"] == "PASS" else not_passed)[rel] = entry
                if progress:
                    progress(i, len(files), rel, entry)
        finally:
            if tg.holder is not None:
                tg.holder.cleanup()
    complete = (not not_passed and not not_measured and len(kill_files) == len(files) and all(c["ok"] for c in ctl))
    return {"tool": TOOL, "tree_sha256": digest, "python": sys.version.split()[0], "platform": sys.platform,
            "patched": patched, "paths": PATHS, "controls": ctl, "complete": complete,
            "seconds": round(time.monotonic() - began, 2), "kill_files": kill_files,
            **({"not_passed": not_passed} if not_passed else {}), **({"not_measured": not_measured} if not_measured else {})}


def main(argv: list[str] | None = None, root: pathlib.Path = ROOT) -> int:
    ap = argparse.ArgumentParser(prog="trace_paths.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--files", nargs="+", metavar="F", help="kill files (default: every file of V21_TARGETS)")
    ap.add_argument("--commit", help="the full sha the checkout must be at")
    a = ap.parse_args(argv)
    head = RS.head_of(root, a.commit)
    files = list(dict.fromkeys(a.files or RS.kill_files()))

    def progress(i, n, rel, e):
        print(f"[{i + 1}/{n}] {e['outcome']:7s} {e['seconds']}s hits={e['hits']} {rel}", file=sys.stderr, flush=True)
    try:
        got = record(root, files, progress)
    except (ca.Unproven, OSError) as e:
        RS.refuse(f"the runner stopped before any kill file: {e}")
    out = {"commit": head, **got}
    a.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"{len(got['kill_files'])}/{len(files)} kill files measured in {got['seconds']}s; controls "
          f"{[c['ok'] for c in got['controls']]} -> {a.out}", file=sys.stderr)
    return 0 if got["complete"] else 1


if __name__ == "__main__":
    os.umask(0o022)
    raise SystemExit(main())
