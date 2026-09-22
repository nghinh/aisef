"""PROBE-BIND-1 beyond the kernel: the evidence builders make product and admission decisions too, so the kernel's
RESULT_ONLY_THROUGH_BINDING rule runs over validation/v2 as well — a builder reads a probe result only through
`bound_result`."""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_s = importlib.util.spec_from_file_location("p2_ks_binding", ROOT / "validation" / "v2" / "kernel_static_checks.py")
ks = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ks)
RULE = ("RESULT_ONLY_THROUGH_BINDING",)


class EvidenceBuilders(unittest.TestCase):
    def test_no_builder_reads_a_bare_result(self):
        for p in sorted((ROOT / "validation" / "v2").glob("*.py")):
            rel = p.relative_to(ROOT).as_posix()
            with self.subTest(builder=rel):
                self.assertEqual(ks.violations(rel, p.read_text(encoding="utf-8"), RULE), [])

    def test_the_rule_sees_both_forms_of_a_bare_read(self):
        for src in ("def f(r):\n    return r.result\n", "def f(r):\n    return getattr(r, 'result')\n"):
            with self.subTest(src=src):
                self.assertEqual(ks.violations("validation/v2/x.py", src, RULE),
                                 ["RESULT_ONLY_THROUGH_BINDING validation/v2/x.py:2 reads a probe result without its "
                                  "binding (use bound_result)"])
        self.assertEqual(ks.violations(ks.BINDING_MODULE, "def f(r):\n    return r.result\n", RULE), [])


if __name__ == "__main__":
    unittest.main()
