"""V2.1 (owner B-03b): kill tests for the survivors of aisef2/app/lineage.py's V2.1 mutation target `claims`, the class
named by the target and the mutants it kills. In the kill set of exactly the target it kills (validation/v2/mutation.py).

The earlier kill set takes at most two claim generations, and the second is only ever written, never read back through
`claims`: no lineage was continued past a superseded claim, and no run directory held a file that looks like a claim
but is not one, so excluding every generation after the first, or counting the look-alikes, survived; and with one
generation after the first there is no order to get wrong."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import lineage  # noqa: E402


class Claims(unittest.TestCase):
    """claims — "L70 condition negated", "L70 And swapped", "L70 GtE->Lt", "L69 string 'CONTINUED-BY\\\\.(\\\\d+)\\\\.json'
    emptied" (generations 2.. not found, or a look-alike taken for one), "L72 sorted() -> list()" (the directory's
    order): a predecessor's claim generations are CONTINUED-BY.json (the first) and CONTINUED-BY.<n>.json for n >= 2,
    oldest first by n — `claim` supersedes the newest and writes n + 1, `continued_by` names the newest's run. Nothing
    else in the run directory is a generation: not a copy, not a ".1" twin of the first."""

    def test_the_generations_are_the_claim_files_oldest_first_and_the_newest_names_the_continuation(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        pred = pathlib.Path(t.name) / "first"
        pred.mkdir()

        def write(name: str, run: str) -> pathlib.Path:
            (pred / name).write_text(json.dumps({"run": str(pred.parent / run)}) + "\n", encoding="utf-8")
            return pred / name
        made = {1: write(lineage.CLAIM, "child-1")}
        for n in (7, 12, 2, 10, 5, 3, 11, 4, 9, 6, 8):    # neither creation order nor its reverse nor by name is by n
            made[n] = write(f"CONTINUED-BY.{n}.json", f"child-{n}")
        for look_alike in ("CONTINUED-BY.1.json", "CONTINUED-BY.0.json", "CONTINUED-BY.copy.json", "CONTINUED-BY.2.3.json"):
            write(look_alike, "not-a-generation")
        self.assertEqual(lineage.claims(pred), sorted(made.items()))
        self.assertEqual(lineage.continued_by(pred), (str(pred.parent / "child-12"), lineage.UNBEGUN))


if __name__ == "__main__":
    unittest.main()
