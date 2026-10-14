"""kill_one.py TARGET INDEX TESTMODULE: the mutant of the tree's own module put in place of the real one, the test module
run once (the T0 null mutant first, as control). Prints KILLED/SURVIVED. Run through py.sh from the repository root."""
import importlib, pathlib, sys, types, unittest
sys.path.insert(0, "."); sys.dont_write_bytecode = True
from validation.v2 import mutation as m
target, idx, test = sys.argv[1], int(sys.argv[2]), sys.argv[3]
rel, func = target.split("::")
src = pathlib.Path(rel).read_text(encoding="utf-8")
modname = rel[:-3].replace("/", ".")
importlib.import_module(modname)
found = m.mutants(src, func, m._enum_members(src, pathlib.Path(".")))
def run(text):
    mod = types.ModuleType(modname); mod.__package__ = modname.rpartition(".")[0]; mod.__file__ = rel
    exec(compile(text, rel, "exec"), mod.__dict__)
    saved = sys.modules[modname]; sys.modules[modname] = mod
    parent = sys.modules[modname.rpartition(".")[0]]; old = getattr(parent, modname.rpartition(".")[2])
    setattr(parent, modname.rpartition(".")[2], mod)
    for n in [n for n in sys.modules if n.startswith("tests.v2.") and n != "tests.v2"]:
        sys.modules.pop(n)
    try:
        t = importlib.import_module(test)
        r = unittest.TextTestRunner(stream=open("/dev/null", "w")).run(unittest.defaultTestLoader.loadTestsFromModule(t))
    finally:
        sys.modules[modname] = saved; setattr(parent, modname.rpartition(".")[2], old)
    return r
r = run(m.null_mutant(src, func)); print("null:", "PASS" if r.wasSuccessful() else "FAIL", r.testsRun)
r = run(found[idx][1]); print(f"[{idx}] {found[idx][0]}:", "SURVIVED" if r.wasSuccessful() else "KILLED", f"run={r.testsRun} fail={len(r.failures)} err={len(r.errors)}")
