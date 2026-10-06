"""V2.1 (C): the Open Code Review adapter (aisef2/app/review_ocr.py) — AISEF decides the scope, OCR only finds.

Fixtures: tests/v2/fixtures/ocr/{complete,partial,preview}.json, built from OCR v1.12.12's structs by the upstream
research (not a real run: none is installed and no provider budget is approved). Each check below is one way a review
that exits 0 is still not a full review of the frozen candidate — and the one way it is."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_ocr as O  # noqa: E402
from aisef2.app import review_verify  # noqa: E402

FIX = ROOT / "tests/v2/fixtures/ocr"
A = json.loads((FIX / "complete.json").read_text(encoding="utf-8"))
B = json.loads((FIX / "partial.json").read_text(encoding="utf-8"))
PREVIEW = json.loads((FIX / "preview.json").read_text(encoding="utf-8"))
BASE, HEAD = "1" * 40, "2" * 40
REQUIRED = ["src/app/api.py", "src/app/limits.py"]


class Coverage(unittest.TestCase):
    def cov(self, out=A, code=0, required=REQUIRED, base=BASE, head=HEAD, preview=None):
        return O.coverage(out, code, required=required, base=base, head=head, preview=preview)

    def test_a_complete_run_of_the_frozen_range_covering_every_required_path(self):
        c = self.cov()
        self.assertEqual((c.status, c.reasons), (O.COMPLETE, ()))

    def test_item_ids_are_ocr_s_own_derivation(self):
        for item in A["manifest"]["coverage"]["completed"]:
            self.assertEqual(O.item_id("range", item["path"], item["path"]), item["item_id"])

    def test_exit_0_is_not_a_full_review(self):
        cases = {
            "partial": (B, 0, ["pkg/store/db.go", "pkg/store/cache.go"], "3" * 40, "4" * 40),
            "nonzero exit, complete manifest": (A, 1, REQUIRED, BASE, HEAD),
            "a required path it never reviewed": (A, 0, [*REQUIRED, "src/app/new.py"], BASE, HEAD),
            "another head": (A, 0, REQUIRED, BASE, "9" * 40),
            "another base": (A, 0, REQUIRED, "8" * 40, HEAD),
        }
        for name, (out, code, req, base, head) in cases.items():
            with self.subTest(name):
                c = self.cov(out, code, req, base, head)
                self.assertEqual(c.status, O.INDETERMINATE, c)
                self.assertTrue(c.reasons)
        self.assertEqual(self.cov(None).status, O.INDETERMINATE)

    def test_a_manifest_that_does_not_hold_together_is_indeterminate(self):
        def changed(f):
            out = copy.deepcopy(A)
            f(out)
            return self.cov(out)
        self.assertIn("schema", changed(lambda o: o["manifest"].__setitem__("schema_version", "ocr.run-manifest/v2")).reasons[0])
        self.assertIn("pinned", " ".join(changed(lambda o: o["manifest"]["execution"].__setitem__("ocr_version", "v1.13.0")).reasons))
        forged = changed(lambda o: o["manifest"]["coverage"]["completed"][0].__setitem__("item_id", "0" * 64))
        self.assertTrue(any("item_id" in r for r in forged.reasons), forged)
        dropped = changed(lambda o: o["tool_calls"]["failure_details"].append({"tool_name": "code_comment", "error": "x"}))
        self.assertTrue(any("code_comment" in r for r in dropped.reasons), dropped)
        budget = changed(lambda o: o.setdefault("warnings", []).append({"type": "token_budget_reached", "message": "m"}))
        self.assertEqual(budget.status, O.INDETERMINATE)

    def test_the_preview_s_exclusions_and_omissions_are_named(self):
        c = self.cov(required=["src/app/limits.py", "tests/test_limits.py", "build/gen.py"], preview=PREVIEW)
        text = " ".join(c.reasons)
        self.assertIn("tests/test_limits.py (default_path)", text)
        self.assertIn("build/gen.py", text)          # gitignored files are absent from the preview entirely


class Findings(unittest.TestCase):
    def test_ids_are_ocr_s_sarif_fingerprint_stable_under_order_and_numbered_when_repeated(self):
        c = A["comments"][0]
        want = hashlib.sha256(f"{c['path']}|{c['category']}|{c['existing_code'].strip()}".encode()).hexdigest()
        self.assertEqual(O.finding_id(c), want)
        twice = {**A, "comments": [c, dict(c, content="the same place, said again")]}
        ids = [f["id"] for f in O.findings(twice, REQUIRED)]
        self.assertEqual(ids, [f"ocr-{want[:12]}-0", f"ocr-{want[:12]}-1"])
        reversed_ = {**twice, "comments": list(reversed(twice["comments"]))}
        self.assertEqual([f["summary"] for f in O.findings(reversed_, REQUIRED)], [f["summary"] for f in O.findings(twice, REQUIRED)])
        no_code = dict(c, existing_code="  ", start_line=41)
        self.assertEqual(O.finding_id(no_code), hashlib.sha256(f"{c['path']}|{c['category']}|41".encode()).hexdigest())

    def test_an_ocr_finding_is_triage_never_a_block(self):
        for f in O.findings(A, REQUIRED) + O.findings(B, ["pkg/store/db.go"]):
            self.assertFalse(f["blocking"])
            v = review_verify.Verification(review_verify.UNVERIFIABLE, "no reproducer")
            self.assertFalse(review_verify.blocks(v, f, "fix-loop", "low"))
        self.assertEqual([f["in_scope"] for f in O.findings(A, ["src/app/api.py"])], [False])   # out of AISEF's scope


class Process(unittest.TestCase):
    def test_the_environment_is_scrubbed_and_isolated(self):
        base = {"PATH": "/bin", "OCR_LLM_TOKEN": "t", "ANTHROPIC_AUTH_TOKEN": "a", "OTEL_EXPORTER_OTLP_ENDPOINT": "e",
                "OCR_ENABLE_TELEMETRY": "1", "HOME": "/Users/me"}
        env = O.environment(base, pathlib.Path("/iso"))
        self.assertEqual(env, {"PATH": "/bin", "HOME": "/iso", "USERPROFILE": "/iso", "OCR_NO_UPDATE": "1"})
        self.assertEqual(O.scrubbed_names(base), ["ANTHROPIC_AUTH_TOKEN", "OCR_ENABLE_TELEMETRY", "OCR_LLM_TOKEN",
                                                  "OTEL_EXPORTER_OTLP_ENDPOINT"])

    def test_the_command_reviews_exactly_the_frozen_range_into_a_fresh_file(self):
        a = O.argv("/opt/ocr", repo="/r", base=BASE, head=HEAD, rule="/c/rule.json", output="/c/out.json",
                   provider="p", model="m", max_tokens=8000, budget_tokens=200000, timeout_min=20,
                   background_file="/c/bg.txt")
        self.assertEqual(a[:12], ["/opt/ocr", "review", "--repo", "/r", "--from", BASE, "--to", HEAD, "--rule",
                                  "/c/rule.json", "--format", "json"])
        self.assertIn("--no-filter", a)
        self.assertEqual(a[a.index("--output") + 1], "/c/out.json")
        self.assertEqual(O.argv("/opt/ocr", repo="/r", base=BASE, head=HEAD, rule="r", output="o", provider="p",
                                model="m", max_tokens=1, budget_tokens=1, timeout_min=1, background_file="b",
                                preview=True)[-1], "--preview")

    def test_the_binary_runs_only_as_the_pinned_bytes_by_absolute_path(self):
        with tempfile.TemporaryDirectory() as t:
            exe = pathlib.Path(t) / "opencodereview"
            exe.write_bytes(b"binary")
            pin = hashlib.sha256(b"binary").hexdigest()
            self.assertIsNone(O.pinned(str(exe), pin))
            self.assertIn("not the pinned", O.pinned(str(exe), "0" * 64))
            self.assertIn("absolute", O.pinned("opencodereview", pin))
            self.assertIsNone(O.read_output(pathlib.Path(t) / "absent.json"))
            (pathlib.Path(t) / "o.json").write_text("not json")
            self.assertIsNone(O.read_output(pathlib.Path(t) / "o.json"))


if __name__ == "__main__":
    unittest.main()
