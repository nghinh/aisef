"""Phase 17 — the replay contract (INV-S.1): a replay compares its manifest with the source's BEFORE the first agent
invocation; material drift stops the run with a typed record unless the owner accepted each field by name."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import tests  # noqa: E402,F401
from aisef.clients.synthetic import SyntheticClientAdapter  # noqa: E402
from aisef.control import replay_manifest as RM  # noqa: E402

SOURCE = RM.ReplayManifest(framework_version="1.7.6", client="opencode", client_version="1.18.29", model="mycombo",
                           route="9router", config_digest="c", requirements_digest="r",
                           story_contract_digests={"S-1": "aaaa"}, environment_digest="e", sandbox_digests={},
                           baseline_identities={}, source_run="run-1")


def _requested(**changes) -> RM.ReplayManifest:
    return RM.ReplayManifest(**{**SOURCE.__dict__, "source_run": "run-2", **changes})


class TestPreflight(unittest.TestCase):
    def test_the_claude_for_opencode_mistake_is_material(self):
        drift = RM.preflight(_requested(client="claude", client_version="2.0"), SOURCE)
        self.assertTrue(drift.stop)
        self.assertEqual(set(drift.material), {"client", "client_version"})
        self.assertIn("client", drift.fields)

    def test_the_same_identity_proceeds(self):
        drift = RM.preflight(_requested(), SOURCE)
        self.assertFalse(drift.stop); self.assertEqual(drift.fields, {})

    def test_an_accepted_drift_is_recorded_not_blocking(self):
        drift = RM.preflight(_requested(client="claude", client_version="2.0"), SOURCE, accept=("client", "client_version"))
        self.assertFalse(drift.stop)
        self.assertEqual(set(drift.immaterial), {"client", "client_version"})
        self.assertEqual(drift.accepted, ("client", "client_version"))
        self.assertIn("client", drift.fields, "accepted drift is still a difference on the record")

    def test_a_changed_story_contract_digest_is_material(self):
        drift = RM.preflight(_requested(story_contract_digests={"S-1": "bbbb"}), SOURCE)
        self.assertEqual(list(drift.material), ["story_contract_digests"])

    def test_a_framework_patch_bump_is_immaterial_a_minor_bump_is_not(self):
        self.assertFalse(RM.preflight(_requested(framework_version="1.7.7"), SOURCE).stop)
        self.assertIn("framework_version", RM.preflight(_requested(framework_version="1.7.7"), SOURCE).immaterial)
        self.assertTrue(RM.preflight(_requested(framework_version="1.8.0"), SOURCE).stop)

    def test_a_client_patch_is_immaterial_a_major_is_material(self):
        self.assertFalse(RM.preflight(_requested(client_version="1.19.0"), SOURCE).stop)
        self.assertTrue(RM.preflight(_requested(client_version="2.0.0"), SOURCE).stop)

    def test_a_field_the_source_never_recorded_is_not_compared(self):
        src = RM.ReplayManifest(**{**SOURCE.__dict__, "model": "", "route": ""})
        self.assertFalse(RM.preflight(_requested(model="other", route="direct"), src).stop)


class TestCliStopsBeforeTheFirstAgentCall(unittest.TestCase):
    """`aisef run --replay-of` with the source declared for OpenCode and the run made with Claude: the preflight
    stops the run before any client call (the synthetic client's `calls == []`) and writes the typed record."""

    def _project(self, root: Path) -> Path:
        (root / ".ai").mkdir(); (root / ".ai" / "config.json").write_text("{}", encoding="utf-8")
        art = root / "_bmad-output"; art.mkdir()
        (art / "stories.index.json").write_text(json.dumps({"stories": [{"id": "S-1", "epic_id": "E-1", "title": "t",
                                                                          "acceptance_criteria": ["a"]}],
                                                             "epics": [{"id": "E-1"}], "waves": {"E-1": [["S-1"]]}}), encoding="utf-8")
        return art

    def _args(self, root: Path, **over) -> argparse.Namespace:
        base = dict(project=str(root), client="claude", epic="", sequential=True, no_isolate=False, force=True,
                    verify_only=False, story="", repeat=1, replay_of="", accept_drift="", project_defaulted=False)
        return argparse.Namespace(**{**base, **over})

    def test_client_drift_stops_the_run_with_a_typed_record_and_no_agent_call(self):
        from aisef.cli import implement as CLI
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); art = self._project(root)
            source = RM.capture(root, art, None, SimpleNamespace(name="opencode", model="mycombo"), run_id="run-src")
            self.assertEqual(source.client, "opencode")
            client = SyntheticClientAdapter(); client.name = "claude"
            with mock.patch.object(CLI, "_client", return_value=(client, 0)), \
                 mock.patch.object(CLI, "_readiness_blocked", return_value=False), \
                 mock.patch("aisef.phases.run.run_sprint", side_effect=AssertionError("the agent must never be invoked")) as sprint:
                rc = CLI.cmd_run(self._args(root, replay_of="run-src"))
            self.assertEqual(rc, CLI.EXIT_NOT_READY)
            self.assertEqual(client.calls, [])
            sprint.assert_not_called()
            rec = json.loads(next((art / "replay").glob("*.drift.json")).read_text(encoding="utf-8"))
            self.assertEqual(rec["record"], RM.DRIFT_RECORD)
            self.assertIn("client", rec["material"])

    def test_an_accepted_drift_lets_the_run_proceed_and_is_recorded(self):
        from aisef.cli import implement as CLI
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); art = self._project(root)
            RM.capture(root, art, None, SimpleNamespace(name="opencode", model="mycombo"), run_id="run-src")
            client = SyntheticClientAdapter(); client.name = "claude"
            report = SimpleNamespace(ok=True, error="", summary=lambda: "ok")
            with mock.patch.object(CLI, "_client", return_value=(client, 0)), \
                 mock.patch.object(CLI, "_readiness_blocked", return_value=False), \
                 mock.patch.object(CLI, "_ensure_git", return_value=None), \
                 mock.patch.object(CLI, "_canh_bao_chua_bien_dich_guard", return_value=None), \
                 mock.patch("aisef.phases.run.run_sprint", return_value=report) as sprint:
                rc = CLI.cmd_run(self._args(root, replay_of="run-src", accept_drift="client,model"))
            self.assertEqual(rc, CLI.EXIT_OK)
            sprint.assert_called_once()
            rec = json.loads(next((art / "replay").glob("*.drift.json")).read_text(encoding="utf-8"))
            self.assertFalse(rec["stop"]); self.assertEqual(sorted(rec["accepted"]), ["client", "model"])
            self.assertIn("client", rec["fields"], "the accepted drift stays on the record")


if __name__ == "__main__":
    unittest.main()
