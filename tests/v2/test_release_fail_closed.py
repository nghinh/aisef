"""V2.0 release charter §6 (S1, B2): every qualification/delivery profile fails closed unless a frozen experiment or
release-smoke record authorizes it, and no path starts a model session with the default model, an inherited
environment, unlimited turns or tokens, or an unattested route. No provider is called here: everything that could
reach one is replaced by a tripwire."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from validation.qualification import c2_delivery_experiment as dx  # noqa: E402
from validation.qualification import c2_p9  # noqa: E402

UNAUTHORIZED = sorted(set(c2_p9.PROFILES) - {c2_p9.EXPERIMENT})


class Tripwires:
    """Everything below the gates that a live run would touch: a call to any of them fails the test."""

    def __enter__(self):
        self.hit = mock.Mock(side_effect=AssertionError("reached past the gate"))
        self._ps = [mock.patch.object(c2_p9, "opencode_session", self.hit), mock.patch.object(c2_p9.P10, "ledgerlock_baseline", self.hit),
                    mock.patch.object(c2_p9.P10, "opencode_identity", self.hit), mock.patch.object(dx, "default_transport", self.hit),
                    mock.patch.object(c2_p9.tempfile, "mkdtemp", self.hit), mock.patch.object(c2_p9.shutil, "which", self.hit)]
        for p in self._ps:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._ps):
            p.stop()


class Profiles(unittest.TestCase):
    def test_the_profiles_are_the_three_known_ones(self):
        self.assertEqual(sorted(c2_p9.PROFILES), sorted(["qp-2.9", "v1-aligned", c2_p9.EXPERIMENT]))

    def test_an_unauthorized_profile_is_refused_before_anything_starts(self):
        for profile in UNAUTHORIZED:
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as t, Tripwires() as w:
                with self.assertRaises(SystemExit) as x:
                    c2_p9.run(pathlib.Path(t), preserve_to=pathlib.Path(t) / "kept.git", profile=profile)
                self.assertTrue(str(x.exception).startswith(f"REFUSED: profile {profile!r} is authorized by no frozen"), x.exception)
                w.hit.assert_not_called()
                self.assertEqual(list(pathlib.Path(t).iterdir()), [])

    def test_the_default_profile_is_refused(self):
        with tempfile.TemporaryDirectory() as t, Tripwires() as w:
            with self.assertRaises(SystemExit) as x:
                c2_p9.run(pathlib.Path(t), preserve_to=pathlib.Path(t) / "kept.git")
            self.assertIn("REFUSED: profile 'qp-2.9'", str(x.exception))
            w.hit.assert_not_called()

    def test_the_delivery_profile_is_refused_by_its_hold(self):
        with tempfile.TemporaryDirectory() as t, Tripwires() as w:
            with self.assertRaises(SystemExit) as x:
                c2_p9.run(pathlib.Path(t), preserve_to=pathlib.Path(t) / "kept.git", profile=c2_p9.EXPERIMENT)
            self.assertEqual(str(x.exception), f"REFUSED: delivery is locked — {dx.HOLD}")
            with self.assertRaises(SystemExit):
                dx.attest(pathlib.Path(t), oc={}, prereg={}, transport=w.hit, smoke=w.hit)
            w.hit.assert_not_called()

    def test_the_command_line_with_a_new_attempt_number_is_refused_on_every_profile(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.dict("os.environ", {c2_p9.PRESERVE_ENV: t}), Tripwires() as w:
            for argv in (["--run", "--attempt", "5"], *(["--run", "--attempt", "5", "--profile", p] for p in UNAUTHORIZED)):
                with self.subTest(argv=argv):
                    with self.assertRaises(SystemExit) as x:
                        c2_p9.main(argv)
                    self.assertIn("is authorized by no frozen experiment or release-smoke record", str(x.exception))
            w.hit.assert_not_called()
        self.assertFalse((ROOT / c2_p9.attempt_dir(5)).exists())


class DirectSession(unittest.TestCase):
    """The one function every model session goes through: a caller that bypasses the runner still cannot start the
    client without a fixed route, a built environment, a budget and a turn cap."""
    BOUND = {"model": "p/m", "env": {}, "budget": object(), "turn_cap": 80}

    def test_a_session_with_anything_unbound_is_refused_before_the_client_is_looked_up(self):
        for missing in self.BOUND:
            kw = {k: v for k, v in self.BOUND.items() if k != missing}
            with self.subTest(unbound=missing), tempfile.TemporaryDirectory() as t, \
                    mock.patch.object(c2_p9.shutil, "which", side_effect=AssertionError("the client was looked up")):
                with self.assertRaises(SystemExit) as x:
                    c2_p9.opencode_session("developer S", "prompt", t, pathlib.Path(t) / "S.jsonl", 60.0, **kw)
                self.assertIn(f"unbound: {missing}", str(x.exception))
                self.assertFalse((pathlib.Path(t) / "S.jsonl").exists())

    def test_with_nothing_bound_every_missing_binding_is_named(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(c2_p9.shutil, "which", side_effect=AssertionError("looked up")):
            with self.assertRaises(SystemExit) as x:
                c2_p9.opencode_session("developer S", "prompt", t, pathlib.Path(t) / "S.jsonl", 60.0)
        self.assertIn("unbound: model, env, budget, turn_cap", str(x.exception))


if __name__ == "__main__":
    unittest.main()
