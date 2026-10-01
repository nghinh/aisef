"""WP-6.1 — the migration table as committed in this repository: current, complete, and the inventory of every V1
proof-mode representation still present, classified. Not a mutation kill test (the runner's tree copy holds no V1
evidence, so these assertions hold only in the real repository)."""

import hashlib
import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_NAME = "aisef_v2_gen_migration_table"
if _NAME in sys.modules:
    gm = sys.modules[_NAME]
else:
    _s = importlib.util.spec_from_file_location(_NAME, ROOT / "validation" / "v2" / "gen_migration_table.py")
    gm = importlib.util.module_from_spec(_s)
    sys.modules[_NAME] = gm
    _s.loader.exec_module(gm)

TABLE = json.loads((ROOT / gm.TABLE_REL).read_text(encoding="utf-8"))
ROWS = {r["v1_mode"]: r for r in TABLE["rows"]}


def entry(**match):
    found = [e for e in TABLE["inventory"] if all(e.get(k) == v for k, v in match.items())]
    assert len(found) == 1, (match, found)
    return found[0]


class Committed(unittest.TestCase):
    def test_the_committed_outputs_are_exactly_what_the_generator_writes(self):
        self.assertEqual(gm.check(ROOT), [])

    def test_the_table_binds_the_frozen_V1_kernel_it_was_read_from(self):
        src = (ROOT / gm.V1_OBLIGATION).read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(TABLE["inputs"]["v1"]["sha256_lf"], hashlib.sha256(src).hexdigest())
        self.assertEqual(TABLE["inputs"]["v1"]["mode_members"], ["CHANGE_REQUIRED", "PRESERVE_REQUIRED", "NEGATIVE_INVARIANT"])
        self.assertEqual(TABLE["inputs"]["v2"]["EXPECTED_AT_PARENT"],
                         {"INTRODUCE": "UNSATISFIED_AT_PARENT", "PRESERVE": "SATISFIED_AT_PARENT", "VERIFY": "UNCONSTRAINED"})
        self.assertEqual(TABLE["aliases"], {})
        self.assertEqual(TABLE["inventory_problems"], [])
        self.assertEqual(gm.problems(TABLE), [])

    def test_the_three_V1_modes_and_their_V2_fields(self):
        self.assertEqual(sorted(ROWS), ["CHANGE_REQUIRED", "NEGATIVE_INVARIANT", "PRESERVE_REQUIRED"])
        want = {"CHANGE_REQUIRED": ("INTRODUCE", "UNSATISFIED_AT_PARENT", "MUST_HOLD"),
                "PRESERVE_REQUIRED": ("PRESERVE", "SATISFIED_AT_PARENT", "MUST_HOLD"),
                "NEGATIVE_INVARIANT": ("PRESERVE", "SATISFIED_AT_PARENT", "MUST_NOT_HOLD")}
        for mode, (role, expected, polarity) in want.items():
            r = ROWS[mode]
            self.assertEqual((r["obligation_role"], r["expected_parent"], r["polarity"]), (role, expected, polarity), mode)
            self.assertEqual((r["subject_absence"], r["status"], r["reason"], r["missing"]),
                             ("HUMAN_DECLARATION_REQUIRED", "UNMAPPED", "HUMAN_DECLARATION_REQUIRED", ["subject_absence"]), mode)
            self.assertEqual((r["obligation_role_source"], r["polarity_source"], r["subject_absence_source"]),
                             ("V1_TRANSITION", "V1_DEFINITION", "NONE"))
        self.assertEqual([p["loss"] for p in TABLE["v2_without_v1_source"]],
                         ["V1_COULD_NOT_INTRODUCE_A_PROHIBITION", "V1_HAS_NO_UNCONSTRAINED_PARENT", "V1_HAS_NO_UNCONSTRAINED_PARENT"])
        self.assertEqual([e["code"] for e in TABLE["loss_report"]],
                         ["V1_NO_SUBJECT_ABSENCE_DECLARATION", "V1_POLARITY_UNVERIFIED",
                          "V1_COULD_NOT_INTRODUCE_A_PROHIBITION", "V1_HAS_NO_UNCONSTRAINED_PARENT"])


class RepositoryInventory(unittest.TestCase):
    def test_the_active_representations(self):
        self.assertEqual(entry(kind="enum", classification="ACTIVE_V1_MODE")["where"], "aisef/control/obligation.py::Mode")
        self.assertEqual(entry(kind="constant", where="aisef/control/obligation.py::EXPECTED")["classification"], "ACTIVE_V1_MODE")
        for mode in ("CHANGE_REQUIRED", "PRESERVE_REQUIRED", "NEGATIVE_INVARIANT"):
            e = entry(kind="token", token=mode)
            kinds = {c["kind"] for c in e["carried_by"]}
            self.assertLessEqual({"code", "prompt", "config", "test", "doc", "evidence", "evidence-text"}, kinds, mode)
            paths = [c["path"] for c in e["carried_by"]]
            self.assertEqual(paths, sorted(paths))
            self.assertIn("aisef/invariants.yaml", paths)
            self.assertIn("aisef/kit/prompts/story-implement.md", paths)
            self.assertEqual(entry(kind="evidence_value", key="proof_mode", value=mode)["classification"], "ACTIVE_V1_MODE")
        self.assertEqual(entry(kind="policy_record", where="closure-evidence/hardening/TDD-PROOF-POLICY-V2.json")["classification"],
                         "ACTIVE_V1_MODE")

    def test_the_historical_unmapped_and_non_mode_representations(self):
        self.assertEqual(entry(kind="policy_record", where="closure-evidence/hardening/W1-WORKLOAD-V1-POLICY-V1-MARKER.json")
                         ["classification"], "HISTORICAL_ONLY")
        self.assertEqual(entry(kind="evidence_value", key="proof_mode", value="NO_SUCH_MODE")["classification"], "UNMAPPED")
        self.assertEqual(entry(kind="enum", where="aisef/harness/capabilities.py::Mode")["classification"], "NOT_A_PROOF_MODE")
        self.assertEqual(entry(kind="token", token="HUMAN_REQUIRED")["where"], "aisef/control/outcome.py::StageOutcome")
        self.assertEqual(entry(kind="grammar")["where"], "aisef/control/normalize.py::ac_proof")
        for value in ("RED -> GREEN", "GREEN -> GREEN"):
            self.assertEqual(entry(kind="evidence_value", key="expected_transition", value=value)["classification"], "NOT_A_PROOF_MODE")
        for value in ("auto", "explicit"):
            self.assertEqual(entry(kind="evidence_value", key="mode", value=value)["classification"], "NOT_A_PROOF_MODE")
        for name in ("STORY_TYPES", "VERIFICATION_ONLY", "NORMAL", "OWNER_OF"):
            self.assertEqual(entry(kind="constant", where=f"aisef/control/obligation.py::{name}")["classification"], "NOT_A_PROOF_MODE")
        self.assertEqual([e for e in TABLE["inventory"] if e["classification"] == "ALIAS"], [])
        self.assertEqual({e["classification"] for e in TABLE["inventory"]},
                         {"ACTIVE_V1_MODE", "HISTORICAL_ONLY", "UNMAPPED", "NOT_A_PROOF_MODE"})

    def test_the_V2_kernel_carries_no_V1_proof_mode(self):
        hits = [p.relative_to(ROOT).as_posix() for p in (ROOT / "aisef2").rglob("*.py")
                if any(m in p.read_text(encoding="utf-8") for m in ("CHANGE_REQUIRED", "PRESERVE_REQUIRED", "NEGATIVE_INVARIANT"))]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
