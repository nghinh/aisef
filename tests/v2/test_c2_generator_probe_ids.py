"""QP-2.7 coverage key (CYCLE2-QUALIFICATION-PLAN §5): the P3 generator's probe/evaluated records may name probe
identities, drawn from a stream of their own — every other event of a run is exactly what it is without them, and a
run generated without them names none (every default trace, and every record that re-derives one, unchanged)."""

import unittest

from tests.v2.p3 import journal_gen as gen

IDS = ("probe.file_artifact", "probe.python_callable_v2", "probe.cli_invocation", "probe.process_effect")


def _without_probe_id(events):
    return [(t, {k: ({kk: vv for kk, vv in v.items() if kk != "probe_id"} if k == "record" else v) for k, v in d.items()}, c)
            for t, d, c in events]


class ProbeIds(unittest.TestCase):
    def test_the_probe_ids_are_the_only_difference_and_every_one_is_named(self):
        named = set()
        for seed in range(400):
            plain = gen.specs(seed, stories=3 + seed % 5, journal_format=3)
            tagged = gen.specs(seed, stories=3 + seed % 5, journal_format=3, probe_ids=IDS)
            self.assertEqual(_without_probe_id(tagged), plain, seed)
            named |= {d["record"]["probe_id"] for t, d, _ in tagged if t == "probe/evaluated"}
        self.assertEqual(named, set(IDS))

    def test_a_default_run_names_no_probe(self):
        for seed in range(200):
            for t, d, _ in gen.specs(seed, stories=3 + seed % 5, journal_format=3):
                if t == "probe/evaluated":
                    self.assertNotIn("probe_id", d["record"])

    def test_the_tagged_journal_is_readable_by_the_kernel(self):
        from aisef2.journal.format3 import reconstruct
        text = gen.journal(7, stories=5, journal_format=3, probe_ids=IDS)
        self.assertTrue(any(e.type == "probe/evaluated" for e in reconstruct(text).events))


if __name__ == "__main__":
    unittest.main()
