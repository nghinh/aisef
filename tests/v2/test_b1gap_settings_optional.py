"""Kill tests for B1 gap target aisef2/app/settings.py::OPTIONAL (L56): every key named in OPTIONAL must pass
load()'s closed-world check (L139) and bind its Settings field — emptying any one of them out of the tuple turns a
valid settings document into a SettingsError. Offline, hermetic: no network, no client, no files."""

from __future__ import annotations

import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import settings  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

PRICES = {"currency": "USD", "input_per_mtok": 3.0, "cache_read_per_mtok": 0.3, "cache_write_per_mtok": 3.75,
          "output_per_mtok": 15.0, "source": "unit-test fixture", "effective_date": "2026-01-01"}


class OptionalKeys(unittest.TestCase):
    def load(self, **extra) -> settings.Settings:
        return settings.load({**copy.deepcopy(e2e.SETTINGS), **extra})

    # kills: L56 string 'client_pin' emptied
    def test_client_pin_is_an_accepted_optional_key_and_binds_settings_client_pin(self):
        exe = "C:\\opt\\aisef\\opencode.exe" if sys.platform == "win32" else "/opt/aisef/opencode"
        pin = {"exe": exe, "sha256": "a" * 64}  # a platform-native ABSOLUTE path (settings.py requires PurePath(exe).is_absolute())
        s = self.load(client_pin=dict(pin))
        self.assertIsInstance(s, settings.Settings)
        self.assertEqual(s.client_pin, pin)

    # kills: L56 string 'client_fence' emptied
    def test_client_fence_is_an_accepted_optional_key_and_binds_settings_client_fence(self):
        s = self.load(client_fence={"xdg": "run-scoped"})
        self.assertIsInstance(s, settings.Settings)
        self.assertEqual(s.client_fence, {"xdg": "run-scoped"})

    # kills: L56 string 'max_cost' emptied
    def test_max_cost_with_prices_is_an_accepted_optional_key_and_binds_the_ceiling(self):
        s = self.load(prices=dict(PRICES), max_cost=12.5)
        self.assertIsInstance(s, settings.Settings)
        self.assertEqual(s.max_cost, 12.5)
        self.assertEqual(s.prices, PRICES)


if __name__ == "__main__":
    unittest.main()
