"""Onboarding digest — reference test for the G6 staleness clock (owner ruling 4).

The digest exists to answer one question: *did the public onboarding surface
change materially since a real person validated it?* So the test has to prove
**both** halves of that sentence, and the second half is the one that is easy to
get wrong:

* a cosmetic edit — reflowing a paragraph, fixing a typo in prose, rewording the
  comment on a command line — must leave the digest **unchanged**, because a
  typo fix must never invalidate a volunteer's afternoon;
* changing a documented command, one of its flags, or one of the ten named
  config defaults must **change** it, because that silently changes what the
  next participant experiences.

This is deliberately the **opposite** convention to G5.1's pre-registration pin
(`docs/BENCH-PREREGISTRATION-C2.md` §1.3), which is byte-exact inside its frozen
region because there the protected value *is* the text.
"""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.onboarding import (  # noqa: E402
    EVIDENCE_PATH,
    compute_onboarding_digest,
)

#: Files the digest reads. Copied into a scratch tree so a test may edit them.
TOUCHED = (
    "README.md",
    "docs/USAGE-GUIDE.md",
    "docs/EXTERNAL-VALIDATION-v1.1.0.md",
    "docs/closure-gate.json",
)


class _Tree(unittest.TestCase):
    """A scratch copy of the onboarding surface, editable per test."""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for rel in TOUCHED:
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        self.addCleanup(self._tmp.cleanup)
        self.base = self.digest()

    def digest(self, defaults: dict | None = None) -> str:
        return compute_onboarding_digest(self.root, defaults=defaults)["digest"]

    def edit(self, rel: str, old: str, new: str) -> None:
        p = self.root / rel
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text, f"{rel}: fixture text moved — {old!r}")
        p.write_text(text.replace(old, new, 1), encoding="utf-8")


class TestCosmeticEditsDoNotChangeTheDigest(_Tree):
    def test_prose_reflow(self):
        """Rejoining two wrapped prose lines is not a change to the product."""
        self.edit(
            "README.md",
            "No Python dependencies beyond the standard library. Optional: `docker`\n(isolation when running tests)",
            "No Python dependencies beyond the standard library. Optional: `docker` (isolation when running tests)",
        )
        self.assertEqual(self.digest(), self.base)

    def test_typo_fix_in_prose(self):
        self.edit("README.md", "The reference skill repositories", "The referenceskill repositories")
        self.assertEqual(self.digest(), self.base)

    def test_reworded_comment_on_a_command_line(self):
        """The `#` tail of a command line is prose about the command, not the command."""
        self.edit(
            "README.md",
            "aisef doctor                       # is the environment complete",
            "aisef doctor                       # is the environment complete?",
        )
        self.assertEqual(self.digest(), self.base)

    def test_prose_edit_inside_the_protocol_section(self):
        self.edit(
            "docs/EXTERNAL-VALIDATION-v1.1.0.md",
            "Tester records observations in real-time",
            "Tester records observations in real time",
        )
        self.assertEqual(self.digest(), self.base)

    def test_reworded_paragraph_that_mentions_a_verb_in_backticks(self):
        """A paragraph that *mentions* a verb is prose. Found while building this:
        harvesting inline code out of paragraphs made a reword of §17's
        "`aisef gate` currently requires `--replay`" move the digest."""
        self.edit(
            "docs/USAGE-GUIDE.md",
            "`aisef gate` currently requires `--replay`; without it it says so and exits.",
            "Without `--replay`, `aisef gate` says so and exits.",
        )
        self.assertEqual(self.digest(), self.base)

    def test_whitespace_in_a_command_line(self):
        """Column alignment inside a code block is formatting."""
        self.edit("README.md", "aisef gates                        #", "aisef gates   #")
        self.assertEqual(self.digest(), self.base)


class TestMaterialChangesDoChangeTheDigest(_Tree):
    def test_install_command(self):
        self.edit("README.md", "```bash\npip install aisef\n```", "```bash\npip install aisef==1.6.0\n```")
        self.assertNotEqual(self.digest(), self.base)

    def test_removed_step_from_the_quick_start(self):
        self.edit("README.md", "aisef qa                           # the verification suite\n", "")
        self.assertNotEqual(self.digest(), self.base)

    def test_changed_flag_in_the_canonical_cli_workflow(self):
        self.edit("docs/USAGE-GUIDE.md", "[--sequential]", "[--sequentially]")
        self.assertNotEqual(self.digest(), self.base)

    def test_changed_command_in_the_protocol_steps(self):
        self.edit("docs/EXTERNAL-VALIDATION-v1.1.0.md", "- `aisef doctor`", "- `aisef doctor --json`")
        self.assertNotEqual(self.digest(), self.base)

    def test_changed_onboarding_default(self):
        from aisef.config import DEFAULTS

        moved = dict(DEFAULTS)
        moved["run.max_turns"] = DEFAULTS["run.max_turns"] + 1
        self.assertNotEqual(self.digest(defaults=moved), self.base)

    def test_changed_default_outside_the_ten_is_ignored(self):
        """Scope is the ten named keys — not all 69."""
        from aisef.config import DEFAULTS

        other = next(k for k in DEFAULTS if k not in set(
            json.loads((ROOT / "docs/closure-gate.json").read_text(encoding="utf-8"))
            ["onboarding_digest"]["onboarding_defaults"]))
        moved = dict(DEFAULTS)
        moved[other] = "changed-by-test"
        self.assertEqual(self.digest(defaults=moved), self.base)


class TestRecordedEvidenceIsInSync(unittest.TestCase):
    """`closure-evidence/onboarding-digest.json` is what G6.1's freshness reads."""

    def setUp(self) -> None:
        self.contract = json.loads((ROOT / "docs/closure-gate.json").read_text(encoding="utf-8"))
        self.spec = self.contract["onboarding_digest"]
        self.recorded = json.loads((ROOT / EVIDENCE_PATH).read_text(encoding="utf-8"))

    def test_recorded_digest_matches_a_fresh_computation(self):
        fresh = compute_onboarding_digest(ROOT)
        self.assertEqual(
            self.recorded["digest"],
            fresh["digest"],
            "onboarding surface moved — regenerate: python3 -m aisef.control.onboarding --write",
        )

    def test_sources_are_exactly_the_ones_the_contract_names(self):
        named = [(s["path"], s["extract"]) for s in self.spec["sources"]]
        got = [(s["path"], s["extract"]) for s in compute_onboarding_digest(ROOT)["sources"]]
        self.assertEqual(named, got)

    def test_every_named_default_is_a_real_key(self):
        from aisef.config import DEFAULTS

        for key in self.spec["onboarding_defaults"]:
            self.assertIn(key, DEFAULTS)

    def test_no_source_extracted_nothing(self):
        """An extractor that silently matches no heading would pin the empty string."""
        for s in compute_onboarding_digest(ROOT)["sources"]:
            self.assertGreater(s["items"], 0, f"{s['path']}::{s['extract']} extracted nothing")


class TestTheReportTemplateCannotBeMisreadAsEvidence(unittest.TestCase):
    """G6.1's evidence is `docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md`. The blank
    template must not be reachable by any glob a probe would plausibly write for
    that path, and must announce itself as not-evidence on its first lines."""

    TEMPLATE = ROOT / "docs/TEMPLATE-EXTERNAL-VALIDATION-REPORT.md"
    REPORT = "EXTERNAL-VALIDATION-REPORT"

    def test_template_exists(self):
        self.assertTrue(self.TEMPLATE.is_file())

    def test_name_does_not_match_a_report_glob(self):
        self.assertFalse(self.TEMPLATE.name.startswith(self.REPORT))
        self.assertEqual(list((ROOT / "docs").glob(f"{self.REPORT}-v*.md")), [])

    def test_banner_says_not_evidence(self):
        head = self.TEMPLATE.read_text(encoding="utf-8")[:600]
        self.assertIn("TEMPLATE_NOT_EVIDENCE", head)

    def test_carries_every_metric_the_protocol_requires(self):
        import re

        protocol = (ROOT / "docs/EXTERNAL-VALIDATION-v1.1.0.md").read_text(encoding="utf-8")
        metrics = re.search(r"(?s)## Metrics\n(.*?)\n## ", protocol).group(1)
        rows = [
            m.group(1).strip()
            for m in re.finditer(r"^\|\s*([^|]+?)\s*\|", metrics, re.M)
            if m.group(1).strip() not in {"Metric", "--------", ":---", ""}
            and set(m.group(1).strip()) != {"-"}
        ]
        body = self.TEMPLATE.read_text(encoding="utf-8")
        missing = [r for r in rows if r not in body]
        self.assertEqual(missing, [], f"template missing protocol metrics: {missing}")

    def test_carries_the_six_fields_the_closure_contract_lists(self):
        body = self.TEMPLATE.read_text(encoding="utf-8").lower()
        for field in (
            "install success",
            "time to first success",
            "undocumented steps",
            "author intervention",
            "framework defect",
            "user blocker",
        ):
            self.assertIn(field, body, f"template missing closure field: {field}")


if __name__ == "__main__":
    unittest.main()
