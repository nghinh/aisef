"""Run the rungs in order on this platform and write one record per rung and platform.

    python -P validation/qualification/run.py --rungs q0 q1 q2 q3 [--print] [--out DIR]

Order is structural (owner §2): a rung runs only while every lower rung it depends on is GREEN here; the first
non-GREEN rung stops the run, and a rung that cannot execute is UNRUNNABLE, never FAILED. `--print` also writes each
record into the log in a form another machine can hand back byte-for-byte (`common.emit`).
"""

from __future__ import annotations

import argparse
import importlib
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402

RUNGS = ("q0", "q1", "q2", "q3")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rungs", nargs="+", default=list(RUNGS))
    ap.add_argument("--out", default=C.OUT_REL)
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--continue-after", action="store_true", help="measure later rungs after a non-GREEN one (never for a claim)")
    a = ap.parse_args(argv)
    ident = C.identity()
    subject = C.subject_problems(ident)
    plat = C.platform_id()
    label = plat["label"]
    if plat["free_disk_gb"] < 2.0:   # owner §25: enough free disk before a large run, or the attempt is UNRUNNABLE
        subject.append(f"only {plat['free_disk_gb']} GB free on the disk holding the tree")
    print(f"qualification subject: seal {C.SEAL_COMMIT[:12]} candidate {C.SEMANTIC_CANDIDATE[:12]} kernel {C.KERNEL_TREE[:12]} | "
          f"HEAD {ident['head'][:12]} kernel {ident['head_kernel_tree'][:12]} | harness {ident['harness']['sha256'][:12]} | platform {label}")
    if subject:
        for p in subject:
            print(f"UNRUNNABLE  {p}")
        rec = {"record": "AISEF V2 — QUALIFICATION SUBJECT", "status": C.UNRUNNABLE, "subject": ident, "problems": subject, "at": C.now()}
        C.write(f"{a.out}/SUBJECT-{label}.json", rec)
        if a.print:
            C.emit(f"{a.out}/SUBJECT-{label}.json", rec)
        return 2
    lower_green = True
    exit_code = 0
    for rung in a.rungs:
        if rung not in RUNGS:
            print(f"unknown rung {rung}")
            return 2
        rel = f"{a.out}/{rung.upper()}/{rung.upper()}-{label}.json"
        if not lower_green and not a.continue_after:
            print(f"{rung.upper()}: not run — a lower rung is not GREEN here (owner §2)")
            break
        t = time.monotonic()
        mod = importlib.import_module(f"validation.qualification.{rung}")
        record, err = C.capture(lambda m=mod: m.run(ident))
        if err:
            record = {"record": f"AISEF V2 — {rung.upper()}", "rung": rung.upper(), "status": C.UNRUNNABLE, "subject": ident,
                      "platform": C.platform_id(), "harness_problems": [err], "at": C.now()}
        record["seconds"] = round(time.monotonic() - t, 1)
        record["harness_digest_at_run"] = ident["harness"]["sha256"]
        C.write(rel, record)
        if a.print:
            C.emit(rel, record)
        print(f"{rung.upper()}: {record['status']} in {record['seconds']}s — {record.get('counts')} problems {len(record.get('problems', record.get('harness_problems', [])))}")
        for p in record.get("problems", record.get("harness_problems", []))[:40]:
            print(f"    {str(p)[:300]}")
        if record["status"] != C.GREEN:
            lower_green = False
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
