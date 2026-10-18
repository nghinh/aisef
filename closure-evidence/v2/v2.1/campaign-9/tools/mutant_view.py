"""mutant_view.py TARGET INDEX [INDEX...]: for a V2.1 target of the tree you run in, each listed mutant as the
unified diff of its mutated module against the unmutated one (line numbers off), with the enclosing source lines.
Run through py.sh from a checkout of the snapshot."""
import difflib, pathlib, sys
sys.path.insert(0, "."); sys.dont_write_bytecode = True
from validation.v2 import mutation as m  # noqa: E402
target, idx = sys.argv[1], [int(x) for x in sys.argv[2:]]
rel, func = target.split("::")
src = pathlib.Path(rel).read_text(encoding="utf-8")
found = m.mutants(src, func, m._enum_members(src, pathlib.Path(".")))
null = m.null_mutant(src, func)
for i in idx:
    desc, mutated = found[i]
    print(f"[{i}] {desc}")
    for ln in difflib.unified_diff(null.splitlines(), mutated.splitlines(), lineterm="", n=2):
        if ln[:3] not in ("+++", "---"):
            print("   ", ln[:240])
