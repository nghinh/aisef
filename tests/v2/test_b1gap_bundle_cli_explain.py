"""B1 gap kill tests for aisef2/app/bundle_cli.py::explain — the report's own envelope, which the listed kill tests
read only through ["stories"]: the top level is exactly {"project": <bundle name>, "stories": <per-story entries>} and
no per-criterion entry repeats its story's grouping key. Pins aisef2/app/bundle_cli.py::explain [L815, L819].

Hermetic: the shipped example's authoring document sealed with a literal baseline and requirements sha256 (no --repo,
so seal never calls git), everything in-process and offline."""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402


class ExplainEnvelope(unittest.TestCase):
    """What explain returns around the stories: sealed once for the class, read many times."""

    @classmethod
    def setUpClass(cls) -> None:
        a = json.loads((bundle_cli.EXAMPLES / "calc-1-story.json").read_text(encoding="utf-8"))["authoring"]
        a["baseline"] = "a" * 40                                   # a literal baseline: seal reads no repository
        a["requirements_document"] = {"path": a["requirements_document"]["path"], "sha256": "b" * 64}
        cls.doc, _ = bundle_cli.seal(a)
        cls.told = bundle_cli.explain(cls.doc)

    # kills: L819 dict entry 0 dropped
    def test_the_report_is_exactly_a_project_and_its_stories(self):
        self.assertEqual(set(self.told), {"project", "stories"})

    # kills: L819 string 'project' emptied
    def test_the_project_key_carries_the_bundles_name(self):
        self.assertEqual(self.told.get("project"), self.doc["name"])

    # kills: L815 string 'story' emptied (the surviving occurrence: the k != "story" filter of the entry dict)
    def test_an_entry_does_not_repeat_its_storys_grouping_key(self):
        self.assertTrue(self.told["stories"])
        for story, entries in self.told["stories"].items():
            self.assertTrue(entries, story)
            for e in entries:
                self.assertNotIn("story", e, story)


if __name__ == "__main__":
    unittest.main()
