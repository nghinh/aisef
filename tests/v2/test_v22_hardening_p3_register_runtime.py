"""ROADMAP-2.2 wave-2 hardening P3 — register_runtime CODE-resolution regression guard (owner #1 GO).

Pins the wave-2 survived-mutant gap on `aisef2/invariants/registry.py::register_runtime` (the resolve loop's
`if m.kind is MechanismKind.CODE` flipped to `STATIC_RULE`). register_runtime is the sole runtime fail-closed
guard that every CODE enforcement mechanism actually resolves (import + attribute), and it must NOT resolve
STATIC_RULE mechanisms (those belong to the development tier). Shipped code is correct; no product change."""
from __future__ import annotations

import dataclasses
import unittest

from aisef2.invariants import registry as reg


def _first_code(registry):
    for i, inv in enumerate(registry):
        for j, m in enumerate(inv.mechanisms):
            if m.kind is reg.MechanismKind.CODE:
                return i, j
    raise AssertionError("the registry has no CODE mechanism to exercise")


class RegisterRuntimeResolvesCode(unittest.TestCase):
    def test_the_baseline_registry_registers(self):
        self.assertEqual(len(reg.register_runtime().invariants), len(reg.REGISTRY))

    def test_a_present_module_with_a_missing_code_attribute_fails_closed(self):
        # the CODE-resolution loop is the only runtime catch for a renamed/deleted enforcement qualname whose
        # module still imports. A STATIC_RULE mutant would skip it and register_runtime would wrongly succeed.
        i, j = _first_code(reg.REGISTRY)
        broken = dataclasses.replace(reg.REGISTRY[i].mechanisms[j],
                                     ref="aisef2.invariants.registry:NO_SUCH_ATTR")   # module imports, attr absent
        mechs = reg.REGISTRY[i].mechanisms[:j] + (broken,) + reg.REGISTRY[i].mechanisms[j + 1:]
        inv = dataclasses.replace(reg.REGISTRY[i], mechanisms=mechs)
        bad = reg.REGISTRY[:i] + (inv,) + reg.REGISTRY[i + 1:]
        with self.assertRaises(reg.RegistrationError):
            reg.register_runtime(bad)

    def test_runtime_does_not_resolve_static_rules(self):
        # a STATIC_RULE whose rule name is missing must be IGNORED at runtime (the dev tier resolves static
        # rules). The CODE->STATIC_RULE mutant would resolve it and raise, so this pins the kind distinction.
        i, j = _first_code(reg.REGISTRY)
        probe = reg.Mechanism("P3-STATIC-PROBE", reg.MechanismKind.STATIC_RULE,
                              "kernel_static_checks:NO_SUCH_RULE", "a deliberately missing static rule")
        inv = dataclasses.replace(reg.REGISTRY[i], mechanisms=reg.REGISTRY[i].mechanisms + (probe,))
        ok = reg.REGISTRY[:i] + (inv,) + reg.REGISTRY[i + 1:]
        self.assertEqual(len(reg.register_runtime(ok).invariants), len(reg.REGISTRY))


if __name__ == "__main__":
    unittest.main()
