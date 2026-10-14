import sys
sys.path.insert(0, "."); sys.dont_write_bytecode = True
from aisef2.app import review_verify as V
from tests.v2 import test_v21_kills3_T16a as T
def nest(n):
    d = {}
    for _ in range(n):
        d = {"a": d}
    return d
for n in (50, 200, 400, 800, 3000):
    rep = {**T.SNAPSHOT_MISSING, "stimulus": {"argv": ["x"], "env": nest(n)}}
    f = {"id": "F-1", "severity": "high", "reproducer": rep}
    try:
        r = V.reproducer_contract(f, {"R-9": object()}, ("ledgerlock",))
        print(n, "->", type(r).__name__, (str(r)[:100] if isinstance(r, str) else ""))
    except BaseException as e:
        print(n, "RAISED", type(e).__name__, str(e)[:80])
