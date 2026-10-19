"""dryrun.py: call v21_mutation_record.build(ROOT, head) and print the derived numbers WITHOUT writing MUTATION files.
Run from repo root: python -P scratch/dryrun.py [head]"""
import sys, pathlib
ROOT = pathlib.Path(".").resolve()
sys.path.insert(0, str(ROOT))
from validation.qualification import v21_mutation_record as R
head = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
record, summary = R.build(R.ROOT, head)
keys = ["FINAL_HEAD","TOTAL_TARGETS","ACCOUNTED_EXACTLY_ONCE","measured_at_final_head",
        "reused_after_mechanical_proof","MUTANTS","KILLED","CLASSES","KILLED_BY_TIMEOUT",
        "AUDITED_SURVIVORS","AUDITED_BY_CLASS","UNAUDITED_SURVIVORS","STALE_RESULTS_EXCLUDED",
        "RERUN_TARGETS","MUTATION_VERDICT"]
for k in keys:
    v = summary.get(k)
    print(f"{k:32} {v}")
print(f"{'MISSING_TARGETS(len)':32} {len(summary['MISSING_TARGETS'])}", summary['MISSING_TARGETS'][:8])
print(f"{'NOT_PASSING(len)':32} {len(summary['NOT_PASSING'])}", summary['NOT_PASSING'][:8])
print(f"{'problems(len)':32} {len(summary['problems'])}", summary['problems'][:4])
# which workers contributed chosen targets
prov = summary["provenance"]
from collections import Counter
print("chosen-by-worker:", dict(Counter(p["worker"] for p in prov.values())))
print("num targets in record:", len(record["targets"]))
