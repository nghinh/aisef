"""V2.1 (owner B-03b): kill tests for the survivors of aisef2/app/settings.py's V2.1 mutation target `endpoint_problem`,
the class named by the target and the mutants it kills. In the kill set of exactly the target it kills
(validation/v2/mutation.py).

The earlier kill set gives the settings string endpoints only, all of which parse, and checks that a refused one is
refused, not what the refusal says: an endpoint that is not a string or not a URL was never given (so returning None
for it — accepting it — survived), and the plaintext refusal's wording was never read."""

from __future__ import annotations

import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import settings  # noqa: E402
from tests.v2.test_app_run import SETTINGS  # noqa: E402


class EndpointProblem(unittest.TestCase):
    """endpoint_problem — "L69 returns None", "L69 string 'the provider endpoint is a URL string' emptied" (either way an
    endpoint that is not a string is accepted), "L74 returns None" (a URL that does not parse is accepted), "L74 string
    'the provider endpoint is not a URL: ' emptied", "L80 string '): ' emptied", "L80 string ' is not loopback' emptied",
    "L80 string ', ' emptied": run settings whose provider endpoint cannot carry the key are refused before anything
    starts, and the refusal tells the operator what the endpoint must be and what is wrong with this one (the parser's
    own reason for a URL that does not parse; the host for plaintext http to a host that is not loopback)."""

    def refusal(self, endpoint) -> str:
        doc = copy.deepcopy(SETTINGS)
        doc["provider"]["endpoint"] = endpoint
        with self.assertRaises(settings.SettingsError) as c:
            settings.load(doc)
        return str(c.exception)

    def test_an_endpoint_that_cannot_carry_the_key_is_refused_saying_why(self):
        https = "the provider endpoint is https (or http to 127.0.0.1, localhost, ::1): "
        cases = [(None, "the provider endpoint is a URL string"), (443, "the provider endpoint is a URL string"),
                 (["https://api.example.com/v1"], "the provider endpoint is a URL string"),
                 ("https://api.example.com:port/v1", ("the provider endpoint is not a URL: Port could not be cast to "
                                                      "integer value as 'port'")),
                 ("https://api.example.com:70000/v1", "the provider endpoint is not a URL: Port out of range 0-65535"),
                 ("https://[::1/v1", "the provider endpoint is not a URL: Invalid IPv6 URL"),
                 ("http://localhost.example.com/v1", https + "localhost.example.com is not loopback"),
                 ("http://10.0.0.1:8080/v1", https + "10.0.0.1 is not loopback")]
        self.assertEqual([(e, self.refusal(e)) for e, _ in cases], cases)


if __name__ == "__main__":
    unittest.main()
