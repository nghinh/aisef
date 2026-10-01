"""WP-2.2 — ProbeCapabilityCalibration of the reference probe over the committed fixtures (RFC §9.1.1).

tests/v2/fixtures/calibration/<kind>/<class>/{positive,negative}: python_callable must be qualified for every class it
supports, and the same fixtures must reject it the moment they stop contrasting.
"""

import json
import pathlib
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.probe.calibration import NotQualified, calibrate, calibration_env, fixture_spec  # noqa: E402
from aisef2.probe.protocol import ProbeRegistry  # noqa: E402
from aisef2.probe.python_callable import CLASSES, METADATA, PythonCallableProbe, spec_class  # noqa: E402
from aisef2.product.contract import names_test_artefact  # noqa: E402

P = PythonCallableProbe()
BASE = ROOT / "tests" / "v2" / "fixtures" / "calibration" / "python_callable"
ENV = calibration_env(sys.executable)
REGISTRY = ProbeRegistry([METADATA])


class Fixtures(unittest.TestCase):
    def test_every_supported_class_has_both_fixtures_asking_for_it(self):
        self.assertEqual(sorted(p.name for p in BASE.iterdir()), sorted(CLASSES))
        for cls in CLASSES:
            for side in ("positive", "negative"):
                d = BASE / cls / side
                with self.subTest(cls=cls, side=side):
                    self.assertTrue((d / "checkout").is_dir())
                    self.assertEqual(spec_class(fixture_spec(P, d)), cls)
                    self.assertEqual(names_test_artefact(json.loads((d / "request.json").read_text(encoding="utf-8"))),
                                     [])
                    self.assertFalse([p for p in (d / "checkout").rglob("*") if p.name.startswith("test")])

    def test_python_callable_is_qualified_for_every_class(self):
        for cls in CLASSES:
            with self.subTest(cls=cls):
                rec = calibrate(P, cls, BASE / cls / "positive", BASE / cls / "negative", ENV, time.time, registry=REGISTRY)
                self.assertEqual((rec.probe_id, rec.probe_digest, rec.observation_class), (P.id, P.digest, cls))

    def test_the_same_fixtures_reject_it_once_they_stop_contrasting(self):
        for cls in CLASSES:
            with self.subTest(cls=cls):
                with self.assertRaises(NotQualified):
                    calibrate(P, cls, BASE / cls / "negative", BASE / cls / "negative", ENV, time.time, registry=REGISTRY)
                with self.assertRaises(NotQualified):
                    calibrate(P, cls, BASE / cls / "positive", BASE / cls / "positive", ENV, time.time, registry=REGISTRY)


if __name__ == "__main__":
    unittest.main()
