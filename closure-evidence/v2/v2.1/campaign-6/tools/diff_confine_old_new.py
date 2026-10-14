"""diff_confine_old_new.py BASE: `confine._judge` and `confine._sections` of BASE (git show) against the working tree's,
over a grid of probe outputs and tries. The claim the tool checks: they answer the same for every input whose every try
reported an exit status (an int) — the only inputs the other kill files can feed them — and differ only where a try has
no status (`_sections`: a try left open; `_judge`: a status None or a value that is not a (status, text) pair).
Run from the repository root through the wrapper; prints one line per class and exits 1 on a difference outside it."""
import itertools
import json
import pathlib
import subprocess
import sys
import types

sys.path.insert(0, ".")
sys.dont_write_bytecode = True
from aisef2.app import confine as NEW  # noqa: E402
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402

base = sys.argv[1]
text = subprocess.run(["git", "show", f"{base}:aisef2/app/confine.py"], capture_output=True, text=True, check=True).stdout
OLD = types.ModuleType("aisef2.app.confine_old")
OLD.__package__ = "aisef2.app"
exec(compile(text, "confine_old.py", "exec"), OLD.__dict__)
WS = pathlib.PurePosixPath("/w/ws")


def report():
    return {"network": "host", "created_outside_workspace": {"kernel": False}, "setsid_survivors": [], "host_mounts": rows.HOST,
            "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0000000000000000"),
                       "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                       "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                       "mounts": [rows.mount("/"), {"at": str(WS), "access": "rw", "fs": "ext4"}], "mount_targets": [str(WS)]}}


def call(mod, tries, out=""):
    try:
        return ["ok", mod._judge(report(), "TOKEN", out, tries, "/nonexistent", WS)]
    except BaseException as e:   # noqa: BLE001 — the same exception type and text is "the same behaviour"
        return ["raised", type(e).__name__, str(e)]


RC = (0, 1, 2, 127, 255, -9)
TEXT = ("", "ok", "cat: x: No such file or directory", "unshare: unshare failed: No space left on device",
        "unshare: unshare failed: Operation not permitted", "Segmentation fault")
PAIRS = [(r, t) for r in RC for t in TEXT]
NAMES = ("read_canary", "workspace", "read_git_directory", "user_namespace", "setsid")
n = same = 0
bad = []
# every try present with a status, or absent (a try the probe did not write), over a sample of the cross product
for combo in itertools.product([None, *PAIRS[::4]], repeat=4):
    tries = {k: v for k, v in zip(NAMES, combo, strict=False) if v is not None}
    for out in ("", "xx TOKEN yy"):
        n += 1
        a, b = call(OLD, dict(tries), out), call(NEW, dict(tries), out)
        if a == b:
            same += 1
        else:
            bad.append((tries, out, a, b))
print(f"_judge: {n} inputs (every try with an exit status or absent): {same} identical, {len(bad)} differ")
# `_sections`: closed tries (any statuses and texts) and the other marker words
M = NEW.MARK
sec_n = sec_same = 0
for rc_a, rc_b in itertools.product(range(0, 3), repeat=2):
    for body in ("", "line", "line one\nline two", "A" * 400):
        out = "\n".join([f"{M}try a", body, f"{M}rc {rc_a}", f"{M}try b", body, f"{M}rc {rc_b}", f"{M}section s", "x", f"{M}ns user own",
                         f"{M}uid 1000", f"{M}end"]) + "\n"
        sec_n += 1
        sec_same += OLD._sections(out) == NEW._sections(out)
print(f"_sections: {sec_n} outputs with every try closed: {sec_same} identical")
# the classes that DO differ, named
open_try = f"{M}try a\ntext{M}rc 1\n{M}end\n"
print("_sections, a try left open:", "old", json.dumps(OLD._sections(open_try)[2]), "| new", json.dumps(NEW._sections(open_try)[2]))
sys.exit(1 if bad or sec_same != sec_n else 0)
