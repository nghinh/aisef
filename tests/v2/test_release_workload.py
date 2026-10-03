"""The release-smoke workload's authoritative-context policy (validation/qualification/release_workload.py; owner ruling
'CONTINUE RELEASE EXECUTION / OWNER RULING FOR RISK-G7-1', option 2): a path is removed only by provenance AND category,
anything else is kept (and reported when ambiguous); the committed derivation is what the source workload re-derives."""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import release_workload as W  # noqa: E402

METHODOLOGY = next(iter(W.METHODOLOGY))


class Classification(unittest.TestCase):
    def rows(self, origin: dict[str, str]) -> dict:
        entries = [("100644", "b" * 40, p) for p in sorted(origin)]
        return W.classify(entries, origin)

    def test_removed_only_by_provenance_and_category(self):
        c = self.rows({"_bmad-output/epics.md": METHODOLOGY, "AGENTS.md": METHODOLOGY, ".claude/skills/x/SKILL.md": METHODOLOGY,
                       "docs/requirements.md": W.AUTHORED_INPUT, "pyproject.toml": W.AUTHORED_INPUT})
        self.assertEqual(sorted(r["path"] for r in c["removed"]), [".claude/skills/x/SKILL.md", "AGENTS.md", "_bmad-output/epics.md"])
        self.assertEqual(sorted(r["path"] for r in c["kept"]), ["docs/requirements.md", "pyproject.toml"])
        self.assertEqual(c["ambiguous"], [])

    def test_disagreement_or_unknown_provenance_is_kept_and_reported(self):
        cases = {"a methodology commit outside every category": {"notes/plan.md": METHODOLOGY},
                 "a category path the authored input introduced": {"evidence/run.txt": W.AUTHORED_INPUT},
                 "a commit neither authored nor methodology": {"_bmad-output/x.md": "f" * 40},
                 "an authored path the policy does not name": {"CONTRIBUTING.md": W.AUTHORED_INPUT}}
        for name, origin in cases.items():
            with self.subTest(name):
                c = self.rows(origin)
                self.assertEqual((c["removed"], [r["path"] for r in c["kept"]], [r["path"] for r in c["ambiguous"]]),
                                 ([], list(origin), list(origin)))

    def test_a_category_prefix_is_a_directory_or_an_exact_path(self):
        self.assertEqual(W.category("evidence/x")[0], "V1_TOOL_RUN_LOGS")
        self.assertIsNone(W.category("evidence-of-something.md"))
        self.assertIsNone(W.category("docs/AGENTS.md"))


@unittest.skipUnless((W.source_repo() / ".git").exists(), "the preserved LedgerLock workload is not on this machine")
class Derivation(unittest.TestCase):
    def test_the_committed_derivation_is_what_the_source_re_derives(self):
        rec = json.loads((ROOT / W.DERIVATION_REL).read_text(encoding="utf-8"))
        d = W.derive()
        self.assertEqual({k: rec[k] for k in ("source", "derived", "kept", "removed", "ambiguous")},
                         json.loads(json.dumps({k: d[k] for k in ("source", "derived", "kept", "removed", "ambiguous")})))
        self.assertEqual((rec["verdict"], rec["problems"]), ("WORKLOAD_CONTEXT_SANITIZED", []))
        self.assertEqual({k: rec["invariants"][k] for k in W.INVARIANTS}, {k: "NO" for k in W.INVARIANTS})
        self.assertEqual([r["path"] for r in rec["ambiguous"]], ["README.md"])

    def test_the_policy_record_is_the_policy(self):
        self.assertEqual(json.loads((ROOT / W.POLICY_REL).read_text(encoding="utf-8")), json.loads(json.dumps(W.policy())))

    @unittest.skipUnless((W.RELEASE_REPO / ".git").exists(), "the release-smoke repository is not on this machine")
    def test_the_release_repository_holds_the_one_commit_and_nothing_else(self):
        self.assertEqual(W.repository_problems(), [])


if __name__ == "__main__":
    unittest.main()
