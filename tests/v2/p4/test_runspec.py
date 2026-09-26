"""WP-4.4 — RunSpec and capability identity grades (RFC §23, §24; F9; P4-LIFETIME-SEMANTICS.md §5).

Kill set for `runspec.py` and `capability.py`. Scenario H (the implementation changes, the version string does not);
OPAQUE bars Q6; an enforcement change breaks comparability; a provider or model change is visible; the checkout
path is a locator and never identity; the full revision SHA is authoritative; no hidden identity fallback.
"""

import hashlib
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import Enforcement as E, IdentityGrade as G  # noqa: E402
from aisef2.runtime import capability as cap, runspec as rsp  # noqa: E402
from aisef2.runtime.capability import CapabilityError, CapabilityIdentity, attested, opaque, verified  # noqa: E402
from aisef2.runtime.runspec import RunSpecError, comparable, q6_eligible, resolve  # noqa: E402
from tests.v2.p4.world import SHA  # noqa: E402

FINGERPRINT = {"model": "claude-x", "max_tokens": 8192, "tools": True}


def model(preflight=FINGERPRINT, **kw):
    fields = {"provider": "anthropic", "endpoint": "https://api.example/v1", "declared_model": "claude-x",
              "route": "direct", "client": "aisef2/0.1", **kw}
    return attested("model", preflight=preflight, enforcement=E.FULL, **fields)


def kernel(artefact=b"kernel v1", enforcement=E.FULL, **meta):
    return verified("kernel", artefact, enforcement, **meta)


def spec(*caps, settings=None, revision=SHA):
    return resolve(caps or (kernel(),), settings or {}, revision)


class Grades(unittest.TestCase):
    def test_verified_binds_a_locally_computed_digest_and_a_version_label_alone_is_refused(self):
        k = kernel(version="1.2.3")
        self.assertEqual(dict(k.tuple_), {"digest": cap.digest_of(b"kernel v1"), "version": "1.2.3"})
        with self.assertRaisesRegex(CapabilityError, "VERIFIED binds a locally computed sha256 digest; a version "
                                                     r"label is metadata, not identity \(§23\)"):
            CapabilityIdentity("tool", G.VERIFIED, {"version": "1.2.3"}, E.FULL)
        with self.assertRaisesRegex(CapabilityError, "VERIFIED binds"):
            CapabilityIdentity("tool", G.VERIFIED, {"digest": "abc"}, E.FULL)

    def test_attested_binds_the_whole_tuple_and_a_measured_fingerprint(self):
        m = model(deployment="us-east")
        self.assertEqual(sorted(m.tuple_), ["client", "declared_model", "deployment", "endpoint", "fingerprint",
                                            "provider", "route"])
        self.assertEqual(model().tuple_["fingerprint"], model().tuple_["fingerprint"])
        full = dict(model().tuple_)
        for missing in cap.ATTESTED_BINDING:
            with self.subTest(missing=missing), self.assertRaisesRegex(CapabilityError, rf"missing \['{missing}'\]"):
                CapabilityIdentity("m", G.ATTESTED, {k: v for k, v in full.items() if k != missing}, E.FULL)
        with self.assertRaisesRegex(CapabilityError, r"not in the binding \['weights'\]"):
            CapabilityIdentity("m", G.ATTESTED, {**full, "weights": "x"}, E.FULL)
        with self.assertRaisesRegex(CapabilityError, "the preflight fingerprint is a locally measured sha256"):
            CapabilityIdentity("m", G.ATTESTED, {**full, "fingerprint": "claude-x"}, E.FULL)
        self.assertNotIn("deployment", model().tuple_)
        extra = {k: "x" for k in ("zeta", "eta", "delta", "beta", "alpha")}
        with self.assertRaises(CapabilityError) as e:
            CapabilityIdentity("m", G.ATTESTED, {**full, **extra}, E.FULL)
        self.assertEqual(str(e.exception), "m: ATTESTED binds ['provider', 'endpoint', 'declared_model', 'route', "
                                           "'client', 'fingerprint'] (and deployment when exposed): missing [], not in "
                                           "the binding ['alpha', 'beta', 'delta', 'eta', 'zeta']")

    def test_opaque_binds_what_is_known_and_the_shape_is_checked(self):
        o = opaque("combo", E.PARTIAL, route="mycombo")
        self.assertEqual((o.grade, dict(o.tuple_)), (G.OPAQUE, {"route": "mycombo"}))
        for bad, message in ((("", G.OPAQUE, {}, E.FULL), "a capability has a name"),
                             (("x", "OPAQUE", {}, E.FULL), "grade is an IdentityGrade"),
                             (("x", G.OPAQUE, {}, "FULL"), "enforcement an Enforcement"),
                             (("x", G.OPAQUE, {"a": 1}, E.FULL), "maps names to strings"),
                             (("x", G.OPAQUE, [], E.FULL), "maps names to strings")):
            with self.subTest(bad=bad), self.assertRaisesRegex(CapabilityError, message):
                CapabilityIdentity(*bad)
        self.assertEqual(list(opaque("c", E.FULL, b="2", a="1").tuple_), ["a", "b"])  # canonical order

    def test_a_digest_covers_a_file_or_a_tree_and_there_is_no_fallback_for_a_missing_artefact(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "a").mkdir()
            (root / "a" / "f.py").write_text("x = 1")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "f.pyc").write_bytes(b"cache")
            tree = cap.digest_of(root)
            self.assertEqual(cap.digest_of(root / "a" / "f.py"), cap.digest_of(b"x = 1"))
            (root / "__pycache__" / "f.pyc").write_bytes(b"other cache")
            self.assertEqual(cap.digest_of(root), tree)  # caches are not the artefact
            (root / "a" / "f.py").write_text("x = 2")
            self.assertNotEqual(cap.digest_of(root), tree)
            (root / "a" / "f.py").write_text("x = 1")
            (root / "a" / "f.py").rename(root / "a" / "g.py")
            self.assertNotEqual(cap.digest_of(root), tree)  # a path is part of a tree
            for name in ("z.py", "m.py", "b.py"):
                (root / name).write_text(name)
            real = pathlib.Path.rglob
            forward = cap.digest_of(root)
            with mock.patch.object(pathlib.Path, "rglob", lambda self, pat: reversed(list(real(self, pat)))):
                self.assertEqual(cap.digest_of(root), forward)  # the walk order is not the digest's
            with self.assertRaisesRegex(CapabilityError, r"does not exist: there is nothing to digest \(no fallback "
                                                         r"grade\)"):
                verified("gone", root / "missing", E.FULL)

    def test_the_resolved_payload_names_the_identity(self):
        k = kernel()
        content = {"name": "kernel", "grade": "VERIFIED", "tuple": {"digest": cap.digest_of(b"kernel v1")},
                   "enforcement": "FULL"}
        self.assertEqual(k.content(), content)
        self.assertEqual(k.identity, hashlib.sha256(cap.canonical(content).encode("utf-8")).hexdigest())
        self.assertEqual(k.resolved(), {"name": "kernel", "grade": "VERIFIED", "enforcement": "FULL",
                                        "binding": dict(k.tuple_), "identity": k.identity})
        self.assertNotEqual(k.identity, kernel(enforcement=E.PARTIAL).identity)


class Spec(unittest.TestCase):
    def test_the_aggregate_is_the_weakest_grade_and_opaque_bars_q6(self):
        self.assertEqual(spec(kernel()).aggregate_min_grade, G.VERIFIED)
        self.assertEqual(spec(kernel(), model()).aggregate_min_grade, G.ATTESTED)
        combo = spec(kernel(), model(), opaque("combo", E.FULL, route="mycombo"))
        self.assertEqual(combo.aggregate_min_grade, G.OPAQUE)
        self.assertFalse(q6_eligible(combo))
        self.assertTrue(q6_eligible(spec(kernel(), model())))
        self.assertTrue(q6_eligible(spec(kernel())))
        self.assertEqual(spec(model(), kernel()).resolved(), {
            "runspec_hash": spec(kernel(), model()).runspec_hash, "aggregate_min_grade": "ATTESTED",
            "capabilities": ["kernel", "model"], "revision": SHA})

    def test_runspec_hash_is_stable_and_total(self):
        base = spec(kernel(), model(), settings={"retries": {"value": 2, "layer": "project"}})
        self.assertEqual(base.runspec_hash, spec(model(), kernel(), settings={"retries": {"value": 2,
                                                                                          "layer": "project"}}).runspec_hash)
        variants = {
            "a capability's bytes": spec(kernel(b"kernel v2"), model(), settings={"retries": {"value": 2,
                                                                                              "layer": "project"}}),
            "an enforcement level": spec(kernel(enforcement=E.PARTIAL), model(),
                                         settings={"retries": {"value": 2, "layer": "project"}}),
            "a grade": spec(kernel(), opaque("model", E.FULL, route="direct"),
                            settings={"retries": {"value": 2, "layer": "project"}}),
            "a setting's value": spec(kernel(), model(), settings={"retries": {"value": 3, "layer": "project"}}),
            "a setting's layer": spec(kernel(), model(), settings={"retries": {"value": 2, "layer": "default"}}),
            "the revision": spec(kernel(), model(), settings={"retries": {"value": 2, "layer": "project"}},
                                 revision="b" * 40),
            "a capability": spec(kernel(), settings={"retries": {"value": 2, "layer": "project"}}),
        }
        for what, other in variants.items():
            with self.subTest(changed=what):
                self.assertNotEqual(other.runspec_hash, base.runspec_hash)
        self.assertEqual(rsp.runspec_hash(base.capabilities, base.aggregate_min_grade, base.settings),
                         base.runspec_hash)
        content = {"capabilities": [kernel().content(), model().content()], "aggregate_min_grade": "ATTESTED",
                   "settings": base.settings}
        self.assertEqual(base.runspec_hash, hashlib.sha256(cap.canonical(content).encode("utf-8")).hexdigest())
        self.assertEqual(spec(model(), kernel()).capabilities, (kernel(), model()))
        self.assertIsInstance(spec(model(), kernel()).capabilities, tuple)
        self.assertEqual(base.settings["revision"], {"value": SHA, "layer": "run"})
        self.assertEqual(tuple(rsp.RunSpec.__dataclass_fields__), ("capabilities", "aggregate_min_grade", "settings",
                                                                   "runspec_hash"))

    def test_a_location_is_never_identity_and_the_full_revision_is_required(self):
        for path in ("/home/ci/checkout", "C:\\\\work\\\\repo", "C:/work/repo", "~/repo", "\\\\\\\\server\\\\share"):
            with self.subTest(path=path), self.assertRaisesRegex(RunSpecError, "^setting 'checkout' is an absolute "
                                                                               "path: an execution locator is never "
                                                                               "identity$"):
                spec(settings={"checkout": {"value": path, "layer": "run"}})
        spec(settings={"subdir": {"value": "src/pkg", "layer": "project"}})  # a relative path is content, fine
        for rev in ("a" * 12, "A" * 40, None, "a" * 41):
            with self.subTest(revision=rev), self.assertRaisesRegex(RunSpecError, rf"^revision {rev!r}: the full "
                                                                                  "40-hex SHA is the authoritative "
                                                                                  "identity$"):
                spec(revision=rev)
        with self.assertRaisesRegex(RunSpecError, "the revision is given as the revision, not as a setting"):
            spec(settings={"revision": {"value": SHA, "layer": "run"}})
        for bad in ({"value": 1}, {"value": 1, "layer": "p", "why": "x"}, 1, {"value": 1, "layer": 2}):
            with self.subTest(setting=bad), self.assertRaisesRegex(RunSpecError, "^setting 'k' carries its value "
                                                                                 "and the layer it came from, nothing "
                                                                                 "else$"):
                spec(settings={"k": bad})
        with self.assertRaisesRegex(RunSpecError, "at least one capability"):
            resolve([], {}, SHA)
        with self.assertRaisesRegex(RunSpecError, "a capability is named once"):
            resolve([kernel(), kernel(b"other")], {}, SHA)

    def test_scenario_H_the_implementation_changes_and_the_version_string_does_not(self):
        v1 = spec(kernel(b"tool build 1", version="2.0.0"))
        v2 = spec(kernel(b"tool build 2", version="2.0.0"))  # VERIFIED: the digest sees the change
        same, why = comparable(v1, v2)
        self.assertFalse(same)
        self.assertEqual(why, ["kernel: digest differs"])
        self.assertNotEqual(v1.runspec_hash, v2.runspec_hash)
        drifted = spec(kernel(), model(preflight={**FINGERPRINT, "max_tokens": 4096}))  # ATTESTED: detectable drift
        self.assertEqual(comparable(spec(kernel(), model()), drifted), (False, ["model: fingerprint differs"]))
        silent = spec(kernel(), model())  # undetectable drift: the same fingerprint — comparable, and graded ATTESTED
        self.assertEqual(comparable(spec(kernel(), model()), silent), (True, []))
        self.assertEqual(silent.aggregate_min_grade, G.ATTESTED)

    def test_comparability_needs_the_same_tuples_grades_and_enforcement(self):
        base = spec(kernel(), model())
        cases = {
            "enforcement": (spec(kernel(enforcement=E.PARTIAL), model()), ["kernel: enforcement FULL vs PARTIAL"]),
            "provider": (spec(kernel(), model(provider="other")), ["model: provider differs"]),
            "model": (spec(kernel(), model(declared_model="claude-y")), ["model: declared_model differs"]),
            "grade": (spec(kernel(), opaque("model", E.FULL, **{k: v for k, v in model().tuple_.items()})),
                      ["model: grade ATTESTED vs OPAQUE"]),
            "capability set": (spec(kernel()), ["model: only in one run"]),
            "a new key": (spec(kernel(), model(deployment="eu")), ["model: deployment differs"]),
        }
        for what, (other, why) in cases.items():
            with self.subTest(changed=what):
                self.assertEqual(comparable(base, other), (False, why))
                self.assertEqual(comparable(other, base)[0], False)
        many = spec(kernel(e="1", d="1", c="1", b="1", a="1"), *(opaque(n, E.FULL) for n in "zyxw"))
        self.assertEqual(comparable(spec(kernel()), many)[1], [  # the reasons in a stable order
            "kernel: a differs", "kernel: b differs", "kernel: c differs", "kernel: d differs", "kernel: e differs",
            "w: only in one run", "x: only in one run", "y: only in one run", "z: only in one run"])
        self.assertEqual(comparable(base, spec(model(), kernel(), settings={"x": {"value": 1, "layer": "p"}})),
                         (True, []))  # settings are hashed, but comparability is the capabilities' (§23)


if __name__ == "__main__":
    unittest.main()
