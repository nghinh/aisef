"""ROADMAP-2.2 G7 + G8a — the authoring surface: seal collects EVERY problem of a phase into one refusal whose
single-problem text is the fail-fast wording byte for byte, and the oracle-content lint names facts text that
carries its own contract's stimulus/observable values or probe-grammar vocabulary — informational: in the lint
output and the seal report, never a verdict flip, zero findings on the shipped example."""
from __future__ import annotations

import copy
import json
import unittest
from importlib import resources

from aisef2.app import bundle_cli
from aisef2.app.bundle import BundleError

EXAMPLE = json.loads(resources.files("aisef2.app.examples").joinpath("calc-1-story.json").read_text("utf-8"))["authoring"]


def authoring() -> dict:
    a = copy.deepcopy(EXAMPLE)
    a["baseline"] = "a" * 40
    a["requirements_document"]["sha256"] = "0" * 64
    return a


class CollectAll(unittest.TestCase):
    def test_every_broken_contract_and_criterion_is_named_in_one_refusal(self):
        a = authoring()
        a["contracts"][0]["not_a_field"] = 1                                   # one broken contract
        a["contracts"].append({"also": "not a contract"})                      # and another
        with self.assertRaises(BundleError) as c:
            bundle_cli.seal(a)
        lines = str(c.exception).split("\n")
        self.assertEqual(len(lines), 2, lines)                                 # BOTH, in one raise
        self.assertIn("$.contracts[0]: ", lines[0])
        self.assertIn("$.contracts[1]: ", lines[1])

    def test_every_bad_criterion_is_named_in_one_refusal(self):
        a = authoring()
        story = next(iter(a["stories"]))
        a["stories"][story]["criteria"][0]["contract"] = "BC-NOWHERE"
        a["stories"][story]["criteria"].append({"not": "a criterion"})
        with self.assertRaises(BundleError) as c:
            bundle_cli.seal(a)
        text = str(c.exception)
        self.assertIn(f"$.stories.{story}.criteria[0].contract: 'BC-NOWHERE'", text)
        self.assertIn(f"$.stories.{story}.criteria[1]: ", text)
        self.assertEqual(len(text.split("\n")), 2, text)

    def test_a_single_problem_reads_exactly_as_the_fail_fast_wording_did(self):
        a = authoring()
        story = next(iter(a["stories"]))
        a["stories"][story]["criteria"][0]["contract"] = "BC-NOWHERE"
        with self.assertRaises(BundleError) as c:
            bundle_cli.seal(a)
        self.assertEqual(str(c.exception),
                         f"$.stories.{story}.criteria[0].contract: 'BC-NOWHERE' is not a contract of the document")


class OracleContentLint(unittest.TestCase):
    def test_the_shipped_example_has_no_oracle_content_in_its_facts(self):
        doc, report = bundle_cli.seal(authoring())
        self.assertEqual(report["facts_oracle_content"], [])
        self.assertEqual(bundle_cli.facts_oracle_content(doc), [])

    def test_a_fact_quoting_its_contracts_oracle_value_is_named_and_never_a_refusal(self):
        doc, _ = bundle_cli.seal(authoring())
        contract = doc["contracts"][0]
        value = next(iter(bundle_cli._scalar_tokens(contract["observable"])))
        criterion = next(cid for cid, f in doc["facts"].items())
        doc["facts"][criterion]["clause_text"] += f" and the grader expects exactly {value} back"
        found = bundle_cli.facts_oracle_content(doc)
        self.assertTrue(any(x.startswith(f"{criterion}: ") and contract["id"] in x for x in found), found)
        out = bundle_cli.lint(doc)
        self.assertEqual(out["facts_oracle_content"], found)    # informational: present, and no verdict change from it

    def test_probe_grammar_vocabulary_in_facts_is_named(self):
        doc, _ = bundle_cli.seal(authoring())
        criterion = next(iter(doc["facts"]))
        doc["facts"][criterion]["clause_text"] += " (tune within_s if slow)"
        self.assertTrue(any("within_s" in x for x in bundle_cli.facts_oracle_content(doc)))


if __name__ == "__main__":
    unittest.main()
