"""PHASE12-KERNEL-IDENTITY.json (owner item 3): the exact product identity every chunk of the final 100 000-trace dataset
must carry — git SHA, `aisef/` tree object (PHASE12_KERNEL_DIGEST), on-disk content digest, invariant registry,
transition model, synthetic adapter, comparator, and the fault-matrix record's version. Refuses a dirty aisef/ tree.

    python3 validation/p12_identity.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.hardening.differential import _kernel_identity  # noqa: E402

OUT = ROOT / "closure-evidence/hardening/phase12/PHASE12-KERNEL-IDENTITY.json"


def main() -> int:
    k = _kernel_identity()
    if k["dirty_aisef"]:
        print("REFUSED: aisef/ is dirty:", k["dirty_aisef"])
        return 1
    fm = json.loads((ROOT / "closure-evidence/hardening/fault-matrix.json").read_text(encoding="utf-8"))
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "PHASE12_KERNEL_DIGEST": k["aisef_tree"], "git_sha": k["head"],
           "aisef_content_sha256": k["aisef_content_sha256"], "invariants_registry_sha256": k["invariants_registry_sha256"],
           "transition_model_sha256": k["model_sha256"], "synthetic_adapter_sha256": k["synthetic_adapter_sha256"],
           "comparator_sha256": k["comparator_sha256"], "hygiene_case_sha256": k["hygiene_case_sha256"],
           "fault_matrix": {"program": fm.get("program"), "phase": fm.get("phase"), "generated": fm.get("generated"), "status_count": fm.get("status_count")},
           "rule": "From this point until Phase 12 closes: NO production code change. Evidence-only/docs-only commits are allowed only while the "
                   "aisef/ tree digest stays identical. Any production change creates a new kernel identity, invalidates every final trace of the "
                   "previous kernel and requires the full qualification set again — never hidden behind commit equivalence.",
           "dataset_rule": "every chunk of the final dataset must record kernel.aisef_tree == PHASE12_KERNEL_DIGEST and the same model and comparator digests"}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k2: (v[:12] if isinstance(v, str) and len(v) >= 40 else v) for k2, v in out.items() if k2 not in ("rule", "dataset_rule", "fault_matrix")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
