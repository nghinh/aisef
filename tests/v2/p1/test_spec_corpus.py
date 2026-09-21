"""WP-1.2 — the committed spec corpus equals a fresh derivation, byte for byte (RFC §8: `--check` in Q0).

Not a mutation kill set: any compiler edit changes compiler_digest and therefore every committed spec.
"""

import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_s = importlib.util.spec_from_file_location("p1_gen_specs", ROOT / "validation" / "v2" / "gen_specs.py")
gs = importlib.util.module_from_spec(_s)
_s.loader.exec_module(gs)

from aisef2.product.compiler import COMPILER_DIGEST  # noqa: E402

CORPUS = ROOT / gs.CORPUS_REL


class Corpus(unittest.TestCase):
    def test_committed_specs_equal_a_fresh_derivation(self):
        self.assertEqual(gs.check(CORPUS), [])

    def test_every_committed_spec_names_the_current_compiler(self):
        for p in sorted((CORPUS / "specs").glob("*.json")):
            with self.subTest(spec=p.name):
                self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["compiler_digest"], COMPILER_DIGEST)

    def test_the_corpus_covers_both_polarities_and_both_absence_declarations(self):
        data = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))
        pairs = {(c["polarity"], c["subject_absence"]) for c in data["contracts"]}
        self.assertEqual(len(pairs), 4)

    def _drift(self, edit):
        with tempfile.TemporaryDirectory() as t:
            copy = pathlib.Path(t) / "corpus"
            shutil.copytree(CORPUS, copy)
            edit(copy)
            return gs.check(copy)

    def test_a_drifted_spec_fails(self):
        def edit(c):
            p = sorted((c / "specs").glob("*.json"))[0]
            p.write_text(p.read_text(encoding="utf-8").replace('"cli_invocation"', '"python_callable"', 1)
                         .replace('"file_artifact"', '"python_callable"', 1), encoding="utf-8")
        self.assertTrue(any("differs" in p for p in self._drift(edit)))

    def test_a_missing_or_orphan_spec_fails(self):
        self.assertTrue(any("has no committed spec" in p
                            for p in self._drift(lambda c: sorted((c / "specs").glob("*.json"))[0].unlink())))
        self.assertTrue(any("has no contract" in p
                            for p in self._drift(lambda c: (c / "specs" / "BC-GHOST.json").write_text("{}\n",
                                                                                                     encoding="utf-8"))))


if __name__ == "__main__":
    unittest.main()
