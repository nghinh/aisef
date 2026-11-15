"""B1 gap wave 2 — kill tests for the surviving mutants of aisef2/app/settings.py::load (max_cost L169-174,
client_pin L186/L190, client_fence L196-202). One test per audit finding; the comment above each test names the
mutant verbatim. Message-substring assertions follow the owner precedent (sealed v2.1 rows: a SettingsError's text
is a test-asserted observable) and pin the smallest stable substring the mutant destroys. Hermetic and offline:
settings.load only, no I/O, no subprocess."""
from __future__ import annotations

import unittest

from aisef2.app import settings
from tests.v2.test_v22_client_pin_fence import BASE, EXE

PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 5.0, "source": "test", "effective_date": "2026-11-04"}


def _mc(value, prices: bool = True) -> dict:
    """BASE plus a max_cost (and, by default, the price table it needs)."""
    d = {**BASE, "max_cost": value}
    if prices:
        d["prices"] = PRICES
    return d


class MaxCostKills(unittest.TestCase):
    # kills: L171 condition negated
    def test_L171_condition_negated(self):
        self.assertEqual(settings.load(_mc(2.5)).max_cost, 2.5)     # negated: the valid 2.5 raises
        with self.assertRaises(settings.SettingsError):
            settings.load(_mc(0))                                   # negated: 0 is accepted

    # kills: L173 condition negated
    def test_L173_condition_negated(self):
        self.assertEqual(settings.load(_mc(2.5)).max_cost, 2.5)     # negated: max_cost WITH prices raises
        with self.assertRaises(settings.SettingsError):
            settings.load(_mc(5.0, prices=False))                   # negated: max_cost WITHOUT prices is accepted

    # kills: L169 string 'max_cost' emptied
    def test_L169_max_cost_key_string_emptied(self):
        with self.assertRaises(settings.SettingsError):
            settings.load(_mc(-1))                  # '"" in data' is False: the whole validation block is dead

    # kills: L171 Or swapped
    def test_L171_or_swapped(self):
        for bad in (0, -1, "5"):                    # or->and is contradictory (bool is an int): never raises
            with self.assertRaises(settings.SettingsError):
                settings.load(_mc(bad))

    # kills: L173 NotIn->In
    def test_L173_notin_to_in(self):
        self.assertEqual(settings.load(_mc(2.5)).max_cost, 2.5)     # in: max_cost WITH prices raises
        with self.assertRaises(settings.SettingsError):
            settings.load(_mc(5.0, prices=False))                   # in: max_cost WITHOUT prices is accepted

    # kills: L170 string 'max_cost' emptied
    def test_L170_subscript_string_emptied(self):
        s = settings.load(_mc(2.5))                 # data[""] is a KeyError for every settings dict reaching L170
        self.assertEqual(s.max_cost, 2.5)

    # kills: L171 not removed  (the first `not`: not isinstance(mc, (int, float)))
    def test_L171_first_not_removed(self):
        self.assertEqual(settings.load(_mc(2.5)).max_cost, 2.5)     # every numeric max_cost would raise

    # kills: L171 not removed  (the second `not`: not math.isfinite(mc))
    def test_L171_second_not_removed(self):
        self.assertEqual(settings.load(_mc(3)).max_cost, 3)         # every finite max_cost would raise

    # kills: L171 LtE->Gt
    def test_L171_lte_to_gt(self):
        self.assertEqual(settings.load(_mc(2.5)).max_cost, 2.5)     # mc > 0: every positive max_cost raises
        with self.assertRaises(settings.SettingsError):
            settings.load(_mc(0))                                   # and 0 is accepted

    # kills: L173 string 'prices' emptied
    def test_L173_prices_string_emptied(self):
        s = settings.load(_mc(2.5))                 # '"" not in data' is always True: valid max_cost+prices raises
        self.assertEqual(s.max_cost, 2.5)

    # kills: L172 string "max_cost is a positive amount of money, in the price table's currency" emptied
    def test_L172_message_emptied(self):            # owner precedent: the message is the observable
        with self.assertRaisesRegex(settings.SettingsError, "positive amount of money"):
            settings.load(_mc(-1))

    # kills: L174 string 'max_cost needs a price table (prices): without it cost is unknown — fail closed' emptied
    def test_L174_message_emptied(self):            # owner precedent: the message is the observable
        with self.assertRaisesRegex(settings.SettingsError, "needs a price table"):
            settings.load(_mc(5.0, prices=False))

    # kills: L171 element 0 dropped  (and the BoolOp reading: the isinstance(mc, bool) guard dropped)
    def test_L171_element_0_dropped(self):
        self.assertEqual(settings.load(_mc(3)).max_cost, 3)         # (float,): a valid int max_cost raises
        with self.assertRaises(settings.SettingsError):
            settings.load(_mc(True))                                # no bool guard: True passes as $1

    # kills: L171 element 1 dropped  (and the BoolOp reading: the not-isinstance guard dropped)
    def test_L171_element_1_dropped(self):
        self.assertEqual(settings.load(_mc(2.5)).max_cost, 2.5)     # (int,): a valid float max_cost raises
        with self.assertRaises(settings.SettingsError):
            settings.load(_mc("5"))                                 # no type guard: isfinite('5') is a TypeError


class PinFenceKills(unittest.TestCase):
    # kills: L186 sorted() -> list()
    def test_L186_sorted_to_list(self):
        s = settings.load({**BASE, "client_pin": {"sha256": "a" * 64, "exe": EXE}})     # sha256 written first
        self.assertEqual(s.client_pin, {"exe": EXE, "sha256": "a" * 64})    # list(cp) order-sensitive: refused

    # kills: L190 string 'client_pin is {exe, sha256}: the client binary by absolute path and its sha256' emptied
    def test_L190_message_emptied(self):            # owner precedent: the message is the observable
        with self.assertRaises(settings.SettingsError) as cm:
            settings.load({**BASE, "client_pin": {"exe": "opencode", "sha256": "a" * 64}})  # not absolute
        self.assertIn("client_pin", str(cm.exception))

    # kills: L196 string 'client_fence names at least one of ' emptied
    def test_L196_message_emptied(self):            # owner precedent: the message is the observable
        with self.assertRaises(settings.SettingsError) as cm:
            settings.load({**BASE, "client_fence": {}})
        self.assertIn("client_fence names at least one of", str(cm.exception))

    # kills: L198 string 'client_fence.external_directory is "workspace-only"' emptied
    def test_L198_message_emptied(self):            # owner precedent: the message is the observable
        with self.assertRaises(settings.SettingsError) as cm:
            settings.load({**BASE, "client_fence": {"external_directory": "everything"}})
        self.assertIn("external_directory", str(cm.exception))

    # kills: L200 string 'client_fence.xdg is "run-scoped"' emptied
    def test_L200_message_emptied(self):            # owner precedent: the message is the observable
        with self.assertRaises(settings.SettingsError) as cm:
            settings.load({**BASE, "client_fence": {"xdg": "operator"}})
        self.assertIn("run-scoped", str(cm.exception))

    # kills: L202 string 'client_fence.output_token_max' emptied
    def test_L202_count_name_emptied(self):         # owner precedent: the _count name is the observable
        with self.assertRaisesRegex(settings.SettingsError, r"client_fence\.output_token_max is an integer"):
            settings.load({**BASE, "client_fence": {"output_token_max": 0}})


if __name__ == "__main__":
    unittest.main()
