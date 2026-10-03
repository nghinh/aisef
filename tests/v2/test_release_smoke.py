"""The release smoke's preregistration logic (validation/qualification/release_smoke.py, charter §15-§17): the budget
envelope never exceeds the owner's ceilings, the client identity carries no secret, and the rehearsal refuses a false
acceptance or a delivery that does not pass."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import release_smoke as S  # noqa: E402


class Envelope(unittest.TestCase):
    def test_seven_stories_under_the_ceilings(self):
        e = S.envelope(7)
        self.assertEqual(e["estimate"], {"provider_requests": 46, "turns": 3360})
        self.assertEqual(e["budget"], {"provider_requests": 58, "turns": 700, "input_tokens": 60_000_000, "output_tokens": 400_000})

    def test_never_above_a_ceiling(self):
        self.assertEqual(S.envelope(50)["budget"]["provider_requests"], 60)


class ClientIdentity(unittest.TestCase):
    def test_the_key_is_neither_recorded_nor_part_of_the_routing_digest(self):
        with tempfile.TemporaryDirectory() as t:
            cfg = pathlib.Path(t) / "opencode"
            cfg.mkdir()
            doc = {"provider": {"9router": {"npm": "x", "options": {"baseURL": S.PROVIDER["endpoint"], "apiKey": "sk-secret-1"}}}}
            (cfg / "opencode.json").write_text(json.dumps(doc), encoding="utf-8")
            env = {"XDG_CONFIG_HOME": t, "PATH": t}
            one = S.client_identity(environ=env)
            doc["provider"]["9router"]["options"]["apiKey"] = "sk-secret-2"
            (cfg / "opencode.json").write_text(json.dumps(doc), encoding="utf-8")
            two = S.client_identity(environ=env)
            doc["provider"]["9router"]["options"]["baseURL"] = "https://elsewhere.invalid/v1"
            (cfg / "opencode.json").write_text(json.dumps(doc), encoding="utf-8")
            three = S.client_identity(environ=env)
        self.assertNotIn("sk-secret", json.dumps(one))
        self.assertEqual(one, two)
        self.assertEqual((one["endpoint"], one["key_present"], one["binary"]), (S.PROVIDER["endpoint"], True, None))
        self.assertNotEqual(one["routing_config_sha256"], three["routing_config_sha256"])


class Rehearsal(unittest.TestCase):
    OK = {"exit": 0, "verify_exit": 0, "release_smoke_pass": "YES", "false_acceptance": [], "unaccounted": []}
    NONE = {"exit": 1, "verify_exit": 0, "release_smoke_pass": "NO", "false_acceptance": [], "unaccounted": []}

    def test_a_good_rehearsal_has_no_problem(self):
        self.assertEqual(S.rehearsal_problems({"reference": self.OK, "partial": self.OK, "nothing": self.NONE}), [])

    def test_each_failure_is_a_problem(self):
        cases = {"a missing scenario": {"reference": self.OK, "nothing": self.NONE},
                 "a reference that does not pass": {"reference": {**self.OK, "release_smoke_pass": "NO"}, "partial": self.OK, "nothing": self.NONE},
                 "a false acceptance": {"reference": self.OK, "partial": self.OK, "nothing": {**self.NONE, "release_smoke_pass": "YES"}},
                 "nothing exits 0": {"reference": self.OK, "partial": self.OK, "nothing": {**self.NONE, "exit": 0}},
                 "an unverified run": {"reference": {**self.OK, "verify_exit": 1}, "partial": self.OK, "nothing": self.NONE},
                 "unaccounted spend": {"reference": self.OK, "partial": {**self.OK, "unaccounted": ["x"]}, "nothing": self.NONE}}
        for name, results in cases.items():
            with self.subTest(name):
                self.assertTrue(S.rehearsal_problems(results))


if __name__ == "__main__":
    unittest.main()
