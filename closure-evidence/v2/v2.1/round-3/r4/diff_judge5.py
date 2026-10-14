"""diff_judge5.py: the five campaign-5 survivors of confine._judge against the unmutated function over a grid of tries.
Run from a checkout of the snapshot through py.sh. Prints, per mutant, the number of inputs compared and the differing ones."""
import itertools, json, pathlib, sys, types
sys.path.insert(0, "."); sys.dont_write_bytecode = True
from validation.v2 import mutation as m
from aisef2.app import confine
from tests.v2.test_v21_kills3_A06 import clean_report
src = pathlib.Path("aisef2/app/confine.py").read_text(encoding="utf-8")
found = m.mutants(src, "_judge", m._enum_members(src, pathlib.Path(".")))
ws = pathlib.PurePosixPath("/w/ws")
def load(text):
    mod = types.ModuleType("aisef2.app.confine_mut"); mod.__dict__["__name__"] = "aisef2.app.confine_mut"
    mod.__package__ = "aisef2.app"
    exec(compile(text, "mutant.py", "exec"), mod.__dict__)
    return mod
WORK = [None, (0, "ok"), (0, ""), (1, "ok"), (1, ""), (2, "x"), (0, "nok"), (0, "ok\nok"), (-9, "ok"), (None, "ok"),
        [], ["ok"], ["x"], ("a", "ok"), (0,), (1,), ("",)]
USERNS = [None, (0, ""), (1, ""), (1, "unshare: unshare failed: No space left on device"),
          (1, "unshare: unshare failed: Operation not permitted"), (127, "Operation not permitted"), (127, "unshare: absent"),
          (None, ""), (None, "Operation not permitted"), (None, "No space left on device"), (2, "x"), [], ["Operation not permitted"]]
CANARY = [None, (1, "cat: x"), (0, "TOKEN"), (0, "")]
GIT = [None, (0, "ref: refs/heads/main"), (1, "No such file")]
def judged(mod, tries):
    try:
        return ["ok", mod._judge(clean_report(ws), "TOKEN-0123", "", tries, "/nonexistent", ws)]
    except BaseException as e:   # the same exception type and text is "the same behaviour"
        return ["raised", type(e).__name__, str(e)]
grid = []
for w, u, c, g in itertools.product(WORK, USERNS, CANARY, GIT):
    t = {}
    for k, v in (("workspace", w), ("user_namespace", u), ("read_canary", c), ("read_git_directory", g)):
        if v is not None:
            t[k] = v
    grid.append(t)
orig = load(src)
base = [judged(orig, t) for t in grid]
for i in (100, 135, 136, 137, 138, 139):
    desc, text = found[i]
    mod = load(text)
    diff = [(t, b, judged(mod, t)) for t, b in zip(grid, base) if judged(mod, t) != b]
    print(f"[{i}] {desc}: {len(grid)} inputs, {len(diff)} differ")
    for t, b, a in diff[:3]:
        print("    ", json.dumps(t, default=str), "->", json.dumps(b, default=str)[:100], "vs", json.dumps(a, default=str)[:100])
    if diff:
        keys = sorted({k for t, _, _ in diff for k in t})
        print("     differing inputs hold keys:", keys, "| user_namespace values:", sorted({repr(t.get("user_namespace")) for t, _, _ in diff}))
