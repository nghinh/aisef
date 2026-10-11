"""V2.1 (owner B-03, kill round 3, batch A00): the survivors of aisef2/app/bundle_cli.py::main that the triage proposed
to audit and whose audit found a reader and a contract the mutant breaks. Both are refusals an operator reads; the
other survivors of this batch (help text, listing order, key order of a report) have no such reader and are audited,
not tested (the batch report names each reader it checked).

* a JSON file that is not a project bundle is refused saying *what it is not* (and which format it should be);
* a document whose kernel objects do not hold is refused saying *which kind of error* the kernel raised, apart from
  its message."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle as B  # noqa: E402
from aisef2.app import bundle_cli  # noqa: E402
from aisef2.product.approval import Requirement  # noqa: E402
from aisef2.product.contract import plain  # noqa: E402


def run_main(*argv) -> tuple[int, str, str]:
    """(exit status, stdout, stderr) of `aisef bundle ARGV`."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bundle_cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class AFileThatIsNotAProjectBundleIsRefusedAsSuch(unittest.TestCase):
    """Pins aisef2/app/bundle_cli.py::main [141] (the guard's refusal of `lint`/`explain`). The mistake an operator
    makes is to name the authoring document `init` just wrote instead of the sealed bundle `seal` made from it. The
    refusal (exit 2, no report) must say what the file is NOT — `not a project bundle`, the cause class — and the format
    it was expected to be: without the first, the line is just a format id, `refused: aisef-v2-project/1`."""

    def test_the_authoring_document_is_named_as_not_a_project_bundle(self):
        with tempfile.TemporaryDirectory() as t:
            example = pathlib.Path(t) / "calc"
            self.assertEqual(run_main("init", "--out", example)[0], 0)
            for command in ("lint", "explain"):
                with self.subTest(command):
                    code, out, err = run_main(command, example / "authoring.json")
                    self.assertEqual((code, out), (2, ""))
                    self.assertIn("not a project bundle", err)
                    self.assertIn(B.FORMAT, err)


class ADocumentWhoseKernelObjectsDoNotHoldIsRefusedWithTheKindOfError(unittest.TestCase):
    """Pins aisef2/app/bundle_cli.py::main [147] (the generic handler's line). A requirement whose text was edited by
    hand in a sealed bundle no longer matches its `requirement_hash`: the kernel's own constructor refuses it with a
    ContractError. The tool refuses the bundle (exit 2, no report) and the line gives the exception's type and, apart
    from it, the kernel's message — `ContractError` is the cause class, `requirement_hash` the element it names. Run
    together, `ContractErrorrequirement_hash does not bind ...` has no type name for the operator to read."""

    def test_the_line_names_the_error_type_as_a_word_of_its_own_and_then_the_kernel_message(self):
        requirement = plain(Requirement.create(id="R-1", text="app.calc.add(a, b) returns the sum", source="docs/r.md#1"))
        requirement["text"] = "app.calc.add(a, b) returns the product"          # edited, not sealed again
        doc = {"format": B.FORMAT, "name": "n", "description": "d",
               "requirements_document": {"path": "docs/requirements.md", "sha256": "0" * 64},
               "product_roots": ["app"], "requirements": [requirement], "contracts": [], "approvals": [], "plan": {},
               "facts": {}, "stories": {}}
        with tempfile.TemporaryDirectory() as t:
            path = pathlib.Path(t) / "edited.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            code, out, err = run_main("lint", path)
        self.assertEqual((code, out), (2, ""))
        self.assertRegex(err, r"^refused: ContractError\b")
        self.assertIn("requirement_hash", err)


if __name__ == "__main__":
    unittest.main()
