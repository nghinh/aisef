"""B1 wave-3 gap anchors — run.execute's record fields and session wiring (B1-BINDING-AMENDMENT-5).

The v2.2 B1 campaign measured 79 survivors on `aisef2/app/run.py::execute`; the wave-3 audit (wf_2866cff0)
confirmed 71 as coverage gaps: the kill set never asserted the record blocks execute writes (invariants,
client_pin, stimulus_tripwire, the STARTED file's exact form) nor the full session/budget wiring (needles,
run-scoped XDG environment, max_cost). test_v22_hardening_p1_run_pin_fence.py pins the pin/fence subset and
is added to the kill set by the same amendment; this file anchors the rest. Same offline demo harness: fake
developer, loopback provider, no network, no credentials. Shipped code is correct; these assertions fail only
if a regression reintroduces one of the audited mutations. No product change."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from aisef2.app import client, demo, settings, tripwire
from aisef2.app import run as R
from aisef2.invariants import registry as invariants

PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 5.0, "source": "test fixture", "effective_date": "2026-01-01"}


@unittest.skipUnless(os.name == "posix", "reuses the demo's shebang-started fake developer")
class RunExecuteRecordAnchors(unittest.TestCase):
    """One good run in setUpClass (argument recording wrappers active); refusal paths get runs of their own."""

    @classmethod
    def setUpClass(cls):
        cls.t = pathlib.Path(tempfile.mkdtemp(prefix="aisef-b1gap4-"))
        (cls.t / "xdg" / "opencode").mkdir(parents=True)
        (cls.t / "xdg" / "opencode" / "opencode.json").write_text(json.dumps(
            {"provider": {"fakeprov": {"options": {"baseURL": demo.SETTINGS["provider"]["endpoint"],
                                                   "apiKey": "{env:AISEF_DEMO_NO_KEY}"}}}}), encoding="utf-8")
        cls.client_exe = cls.t / "client" / "opencode"
        cls.client_exe.parent.mkdir()
        cls.client_exe.write_text(f"#!{sys.executable}\nBODIES = {demo.BODIES!r}\nTEST = {demo.TEST!r}\n"
                                  + demo.FAKE_CLIENT)
        cls.client_exe.chmod(0o755)
        cls.good = hashlib.sha256(cls.client_exe.read_bytes()).hexdigest()
        (cls.client_exe.parent / "mode").write_text("correct")
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(cls.t / "xdg")}):
            cls.project, cls.source = demo.build(cls.t)
        cls.wire = tripwire.needles_of(cls.project)
        # the good run: pin + fence + dollar ceiling declared; session/budget arguments recorded for the asserts
        cls.session_kws: list[dict] = []
        cls.budget_kws: list[dict] = []
        real_session, real_budget = client.session, client.Budget

        def recording_session(name, prompt, cwd, log, timeout_s, **kw):
            cls.session_kws.append(dict(kw))
            return real_session(name, prompt, cwd, log, timeout_s, **kw)

        class RecordingBudget(real_budget):
            def __init__(self, *a, **kw):
                cls.budget_kws.append(dict(kw))
                super().__init__(*a, **kw)

        cls.ok = cls.t / "ok"
        cls.settings = settings.load({**demo.SETTINGS, "prices": PRICES, "max_cost": 1.0,
                                      "client_pin": {"exe": str(cls.client_exe), "sha256": cls.good},
                                      "client_fence": {"external_directory": "workspace-only", "xdg": "run-scoped",
                                                       "output_token_max": 64000}})
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(cls.t / "xdg")}), \
                mock.patch.object(client, "session", recording_session), \
                mock.patch.object(client, "Budget", RecordingBudget):
            cls.rec = R.execute(cls.project, cls.settings, cls.source, cls.ok,
                                client_exe=str(cls.client_exe), transport=demo.loopback())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.t, ignore_errors=True)

    def _execute(self, out, extra=None, **kw):
        s = settings.load({**demo.SETTINGS, **(extra or {})})
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.t / "xdg")}):
            return R.execute(self.project, s, self.source, out,
                             client_exe=str(self.client_exe), transport=demo.loopback(), **kw)

    def test_the_started_file_is_sorted_keyed_json_ending_in_a_newline(self):
        text = (self.ok / R.STARTED).read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"), "the STARTED file does not end in a newline")
        doc = json.loads(text)
        self.assertEqual(sorted(doc), list(doc), "the STARTED file's keys are not sorted (sort_keys dropped)")
        self.assertEqual(set(doc), {"format", "bundle_digest", "project", "plan_hash", "started",
                                    "kernel_digest", "platform", "settings_sha256"})
        expect = hashlib.sha256(json.dumps(self.settings.content, sort_keys=True).encode()).hexdigest()
        self.assertEqual(doc["settings_sha256"], expect)

    def test_the_record_arms_the_invariants_and_keeps_no_nameless_field(self):
        inv = self.rec["invariants"]
        self.assertEqual(set(inv), {"armed", "registry_digest", "code_mechanism_digest", "statement"})
        self.assertTrue(inv["armed"], "no invariant armed")
        self.assertEqual(inv["armed"], sorted(inv["armed"]))
        self.assertEqual(inv["statement"], invariants.RUNTIME_STATEMENT)
        self.assertNotIn("", self.rec, "the record holds a field whose name was emptied")
        rec_on_disk = json.loads((self.ok / "RUN.json").read_text(encoding="utf-8"))
        self.assertNotIn("", rec_on_disk)

    def test_the_record_pins_the_client_identity_exactly(self):
        self.assertEqual(self.rec["client_pin"],
                         {"exe": str(self.client_exe), "sha256": self.good, "when": R.OCR_WHEN,
                          "status": "PASSED",
                          "statement": "sha256 byte identity against the operator's pin; not build provenance"})

    def test_a_pin_mismatch_is_recorded_with_the_rule_it_names(self):
        out = self.t / "pin-bad"
        with self.assertRaises(R.RunRefused):
            self._execute(out, extra={"client_pin": {"exe": str(self.client_exe), "sha256": "0" * 64}})
        rec = json.loads((out / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["client_pin"]["status"], "REFUSED")
        self.assertEqual(rec["failure"]["stage"], "client identity")
        detail = rec["failure"]["detail"]
        self.assertTrue(detail.startswith("client_pin: the client binary fails the identity check before the run — "),
                        f"refusal prefix changed: {detail[:90]!r}")
        self.assertIn("Find out why before changing the pin", detail)
        self.assertIn("set client_pin.exe to its absolute path and client_pin.sha256 to its sha256", detail)
        self.assertIn(R.SHA256_OF, detail)
        self.assertTrue(detail.endswith("). No session was started and no provider request was sent."),
                        f"refusal suffix changed: {detail[-80:]!r}")

    def test_a_tripwire_hit_refuses_at_its_stage_and_records_the_hits(self):
        out = self.t / "tripwire"
        hits = [{"contract": "C-ANCHOR", "needle_chars": 21}]
        with mock.patch.object(R.tripwire, "scan_repo",
                               return_value={"hits": hits, "dropped": [], "unscanned": []}):
            with self.assertRaises(R.RunRefused) as c:
                self._execute(out)
        self.assertIn("the repository tree at the baseline", str(c.exception))
        self.assertIn("contract C-ANCHOR", str(c.exception))
        rec = json.loads((out / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["failure"]["stage"], "stimulus tripwire")
        self.assertEqual(rec["stimulus_tripwire"]["hits"], hits)

    def test_the_sessions_receive_the_needles_and_the_run_scoped_environment(self):
        self.assertTrue(self.wire["needles"], "the demo project yields no needles; the anchor needs at least one")
        self.assertTrue(self.session_kws, "the good run opened no session")
        self.assertTrue(any(kw.get("needles") == self.wire["needles"] for kw in self.session_kws),
                        "no session received the project's needle set (needles kw entry dropped?)")
        xdg_data = str(self.ok / "client-xdg" / "data")
        self.assertTrue(any((kw.get("env") or {}).get("XDG_DATA_HOME") == xdg_data for kw in self.session_kws),
                        "no session environment carries the run-scoped XDG_DATA_HOME")

    def test_the_budget_receives_the_declared_dollar_ceiling(self):
        self.assertTrue(self.budget_kws, "the good run built no budget")
        self.assertEqual(self.budget_kws[-1].get("max_cost"), 1.0)
        self.assertEqual(self.budget_kws[-1].get("prices"), PRICES)

    def test_an_unreadable_lineage_is_refused_naming_the_lineage(self):
        streams = sorted((self.ok / "sessions").glob("*.jsonl"))
        self.assertTrue(streams, "the good run left no session stream to make unreadable")
        streams[0].chmod(0)
        self.addCleanup(streams[0].chmod, 0o644)
        with self.assertRaises(R.RunRefused) as c:
            self._execute(self.t / "lineage", predecessor=self.ok)
        msg = str(c.exception)
        self.assertTrue(msg.startswith(f"the lineage of {self.ok}"), f"lineage refusal prefix changed: {msg[:80]!r}")
        self.assertIn("cannot be read", msg)


if __name__ == "__main__":
    unittest.main()
