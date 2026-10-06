"""B-10 prepared: the README a package index shows has no relative link (validation/v21/public_readme.py)."""

from __future__ import annotations

import importlib.util
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("public_readme", ROOT / "validation" / "v21" / "public_readme.py")
PR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PR)


class PublicReadme(unittest.TestCase):
    def test_the_self_contained_readme_has_no_relative_link(self):
        text, problems = PR.render((ROOT / "README.md").read_text(encoding="utf-8"), None)
        self.assertEqual(problems, [])
        self.assertEqual([t for _, _, t in PR.LINK.findall(text) if not PR.ABSOLUTE.match(t)], [])
        self.assertIn("`docs/v2/USAGE.md`", text)

    def test_with_a_host_every_repository_link_goes_there(self):
        text, problems = PR.render((ROOT / "README.md").read_text(encoding="utf-8"), "https://docs.example/aisef")
        self.assertEqual(problems, [])
        targets = [t for _, _, t in PR.LINK.findall(text)]
        self.assertIn("https://docs.example/aisef/docs/v2/USAGE.md", targets)
        self.assertTrue(all(PR.ABSOLUTE.match(t) for t in targets))

    def test_a_link_to_nothing_is_refused_and_no_file_is_overwritten(self):
        _, problems = PR.render("see [x](docs/no-such-file.md)", None)
        self.assertEqual(problems, ["a link to docs/no-such-file.md names nothing in the tree",
                                    "relative link left: docs/no-such-file.md"])
        with tempfile.TemporaryDirectory() as t:
            out = pathlib.Path(t) / "R.md"
            self.assertEqual(PR.main(["--out", str(out)]), 0)
            self.assertFalse(re.search(r"\]\((?!https?:|#)", out.read_text(encoding="utf-8")))
            with self.assertRaises(FileExistsError):
                PR.main(["--out", str(out)])


if __name__ == "__main__":
    unittest.main()
