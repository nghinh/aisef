"""V2.1 mutation survivors, batch T18b — `aisef2/probe/python_callable_v2.py::HARNESS/main`.

What the controller (`HARNESS`) reports about a subject that is *present* but does not give the observable a
value, and the one place it decides a subject is *absent*:

* a subject whose own import raises, whose attribute lookup raises, or that resolves to a non-callable value asked
  for a call class is present and does not resolve: OBSERVED, REFUTED, the facts `{"subject": "present",
  "resolved": false, "error": <exception type name | "not callable">}` as the observation's `detail`
  (module doc: "otherwise OBSERVED with `verdict_of`, `detail` the facts' JSON") — the result is Executed(REFUTED)
  under REQUIRES_SUBJECT too (never UNRUNNABLE, never "precondition absent"), and `exists` over such a subject is
  REFUTED, never SATISFIED;
* a ModuleNotFoundError is absence only when the missing module is the subject's own module or a parent package
  of it (by dotted prefix, not by string prefix); a missing dependency, a module whose name merely extends the
  missing one, or a submodule the subject's own package needs is a present, failing subject;
* `exists` is "the locator resolves": it reports `{"subject": "present", "resolved": true}` and never calls the
  subject;
* a declared attribute the raised exception does not have is in neither `raised_attrs` nor
  `raised_attrs_unserializable`.

Subprocess-backed on real checkouts, as tests/v2/test_python_callable_v2.py; no test of this file runs the real
opencode, a network or a provider.
"""

import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Enforcement, SubjectAbsence  # noqa: E402
from aisef2.probe import python_callable_v2 as pc2  # noqa: E402
from aisef2.probe.protocol import (  # noqa: E402
    ExecutionEnv, ObservationKind as K, RevisionRef, classify_failure, run_probe,
)
from aisef2.product.outcome import Executed, IndeterminateReason  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

P = pc2.PythonCallableV2Probe()
S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA = IndeterminateReason.PRECONDITION_ABSENT
REQUIRES, DECIDABLE = SubjectAbsence.REQUIRES_SUBJECT, SubjectAbsence.ABSENCE_IS_DECIDABLE
SHA = "89abcdef0123456789abcdef0123456789abcdef"

PRODUCT = {
    "app/__init__.py": "",
    "app/calc.py": "def add(a, b):\n    return a + b\n",
    "app/consts.py": "GENESIS = 'GENESIS'\n",
    # the subject's own import raises something that is not the absence of a module
    "app/boom.py": "raise RuntimeError('boom')\n\n\ndef f():\n    return 1\n",
    # the module imports; asking it for the attribute `boom` raises something that is not an AttributeError
    "app/props.py": "def __getattr__(name):\n    if name == 'boom':\n        raise ValueError(name)\n"
                    "    raise AttributeError(name)\n",
    # a ModuleNotFoundError that names a module which is neither the subject's own nor one of its parents
    "app/needs_dep.py": "import no_such_dependency_aisef\n\n\ndef f():\n    return 1\n",
    # ... one whose NAME is a string prefix of the subject's (`app.report` / `app.report_v2`)
    "app/report_v2.py": "import app.report\n\n\ndef f():\n    return 1\n",
    # ... a package (the subject's own module) whose import needs a submodule of itself that is not there: the
    # missing module is a CHILD of the subject's module, not the module or a parent of it
    "app/brokenpkg/__init__.py": "import app.brokenpkg.gone_submodule\n\n\ndef f():\n    return 1\n",
    # a function that records that it ran: an existence check must not run it
    "app/touch.py": "def f():\n    open('touched.flag', 'w').close()\n    return 1\n",
    "app/errors.py": "class ConflictError(ValueError):\n    def __init__(self, key):\n        super().__init__(key)\n"
                     "        self.key = key\n        self.raw = object()\n\n    @property\n    def unreadable(self):\n"
                     "        raise RuntimeError('cannot read')\n\n\ndef conflict(key):\n    raise ConflictError(key)\n",
}


def spec(locator, observable=None, stimulus=None, *, absence=DECIDABLE, window=10):
    observable = {**(observable or {"condition": "exists"}), "within_s": window}
    return ProductProofSpec.create(
        contract_id="BC-P2", probe_id=P.id, probe_digest=P.digest,
        probe_input={"subject": {"kind": "python_callable", "locator": locator}, "stimulus": stimulus or {},
                     "observable": observable, "subject_absence": absence.value},
        candidate_expectation=S, compiler_id="test", compiler_digest="c" * 64)


def checkout(files):
    d = tempfile.mkdtemp(prefix="aisef2-rev-")
    for rel, text in files.items():
        p = pathlib.Path(d, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


#: one observable per class a call-class subject can be asked for, with the stimulus it takes
CALL_CLASSES = {
    "returns": ({"returns": 1}, {}),
    "raises": ({"raises": "ValueError"}, {}),
    "blocks": ({"blocks": True}, {}),
    "returns_bytes": ({"returns_bytes_hex": "00"}, {}),
    "raises_attrs": ({"raises": "ValueError", "attrs": {"a": 1}}, {}),
}
ALL_CLASSES = {"exists": ({"condition": "exists"}, {}), **CALL_CLASSES}


class _Revision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = checkout(PRODUCT)
        cls.at = RevisionRef(SHA, cls.root)
        cls.env = ExecutionEnv(sys.executable, 20, Enforcement.PARTIAL)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def see(self, locator, observable, stimulus=None, absence=DECIDABLE):
        return P.observe(spec(locator, observable, stimulus, absence=absence), self.at, self.env)

    def run_(self, locator, observable, stimulus=None, absence=DECIDABLE):
        return run_probe(P, spec(locator, observable, stimulus, absence=absence), self.at, self.env).result

    def facts(self, locator, observable, stimulus=None, absence=DECIDABLE):
        """The observation, asserted to be OBSERVED/REFUTED, and its facts parsed."""
        seen = self.see(locator, observable, stimulus, absence)
        self.assertEqual((seen.kind, seen.verdict), (K.OBSERVED, R), seen)
        return json.loads(seen.detail)

    def assert_present_and_unresolved(self, locator, error, classes):
        """Every class in `classes` over `locator`: OBSERVED, REFUTED, exactly the failing-subject facts, and the
        result the harness records for that observation (`HarnessProbe.evaluate` is `classify_failure` over it)
        Executed(REFUTED) under REQUIRES_SUBJECT — never UNRUNNABLE, never PRECONDITION_ABSENT."""
        want = {"subject": "present", "resolved": False, "error": error}
        for name in classes:
            observable, stimulus = ALL_CLASSES[name]
            s = spec(locator, observable, stimulus, absence=REQUIRES)
            seen = P.observe(s, self.at, self.env)
            with self.subTest(cls=name):
                self.assertEqual((seen.kind, seen.verdict), (K.OBSERVED, R), seen)
                self.assertEqual(json.loads(seen.detail), want)
                self.assertEqual(classify_failure(s, seen), Executed(R))


class ImportRaises(_Revision):
    """Pins aisef2/probe/python_callable_v2.py::HARNESS/main [15, 40, 41, 42, 83, 84, 85, 86, 87, 131]: the facts of
    a subject whose own import raises (`app/boom.py`, RuntimeError) — present, not resolved, the exception's type
    name — and that `exists` over it is REFUTED."""

    def test_the_facts_name_the_exception_and_every_class_is_REFUTED(self):
        # `exists` is the only class that reads `resolved`: a module that cannot be imported does not "exist"
        self.assert_present_and_unresolved("app.boom:f", "RuntimeError", ("exists", "returns", "blocks"))


class AttributeLookupRaises(_Revision):
    """Pins aisef2/probe/python_callable_v2.py::HARNESS/main [20, 49, 50, 51, 52, 97, 98, 99, 100, 101, 133]: the
    facts of a subject whose module imports but whose attribute lookup raises something other than AttributeError
    (`app/props.py`, a module-level `__getattr__` raising ValueError for `boom`) — present, not resolved, the
    exception's type name — and that `exists` over it is REFUTED, not "the locator resolves"."""

    def test_the_facts_name_the_exception_and_every_class_is_REFUTED(self):
        # `exists` included: the locator did not resolve, so it is REFUTED, never SATISFIED
        self.assert_present_and_unresolved("app.props:boom", "ValueError", ("exists", "returns", "blocks"))

    def test_an_attribute_the_module_answers_AttributeError_for_is_absent_not_failing(self):
        # the contrast: the same module, an attribute that is simply not there
        self.assertEqual(self.run_("app.props:nope", {"condition": "exists"}, absence=REQUIRES), Executed(I, PA))


class NotCallable(_Revision):
    """Pins aisef2/probe/python_callable_v2.py::HARNESS/main [27, 58, 59, 60, 113, 114, 115, 116, 117, 118]: a
    subject that resolves to a non-callable value (`app.consts:GENESIS`) asked for a call class is present and not
    callable — the facts carry the reason token `error: "not callable"` — for every call class, `blocks` included."""

    def test_every_call_class_over_a_constant_is_present_not_callable_and_REFUTED(self):
        self.assert_present_and_unresolved("app.consts:GENESIS", "not callable",
                                           ("returns", "blocks", "raises_attrs"))

    def test_a_callable_subject_is_not_reported_as_not_callable(self):
        # the contrast: `app.calc:add` is callable, so the same class gets the call's facts, not this reason
        facts = self.facts("app.calc:add", {"returns": 4}, {"args": [1, 2]})
        self.assertEqual(facts, {"subject": "present", "resolved": True, "returned": 3})


class MissingModule(_Revision):
    """Pins aisef2/probe/python_callable_v2.py::HARNESS/main [38, 153]: ModuleNotFoundError raised by the subject's
    module is absence only when the missing module is the subject's own module or a parent package of it.

    A missing third-party dependency, a missing module whose name merely extends the other's by characters
    (`app.report` / `app.report_v2`), or a missing submodule of the subject's own package, is a present subject
    whose import fails: under REQUIRES_SUBJECT a product that breaks on a missing dependency is REFUTED, not
    "precondition absent" (which would send the story back to wait for a subject that is there)."""

    def test_a_missing_dependency_is_a_present_failing_subject(self):
        self.assert_present_and_unresolved("app.needs_dep:f", "ModuleNotFoundError", ("exists", "returns"))

    def test_a_missing_module_whose_name_is_a_string_prefix_of_the_subjects_is_not_its_parent(self):
        self.assert_present_and_unresolved("app.report_v2:f", "ModuleNotFoundError", ("exists", "returns"))

    def test_a_package_whose_own_import_needs_a_missing_submodule_is_a_present_failing_subject(self):
        # the other direction: the missing module lies BELOW the subject's module (`app.brokenpkg` needs
        # `app.brokenpkg.gone_submodule`). The subject's own module is there and cannot be imported; only the
        # subject's own module or a parent of it being missing is absence, never a child of it
        self.assert_present_and_unresolved("app.brokenpkg:f", "ModuleNotFoundError", ("exists", "returns"))

    def test_the_subjects_own_module_or_a_parent_package_missing_is_absence(self):
        # the contrast, which both mutants keep: only these two readings are absence
        cases = {"the subject's own module": "app.telemetry:send",    # the missing name is the subject's module
                 "a parent package": "gone_pkg_aisef.inner:f"}        # the subject's module starts with `<missing>.`
        for what, locator in cases.items():
            s = spec(locator, absence=REQUIRES)
            seen = P.observe(s, self.at, self.env)
            with self.subTest(what=what):
                self.assertEqual(seen.kind, K.SUBJECT_ABSENT)
                self.assertEqual(classify_failure(s, seen), Executed(I, PA))


class ExistsIsResolution(_Revision):
    """Pins aisef2/probe/python_callable_v2.py::HARNESS/main [53, 54, 103, 105]: `exists` is "the locator resolves"
    (module doc table): it reports `{"subject": "present", "resolved": true}` and returns there — it never calls the
    subject, so a constant is "there" and a function that must not run is not run."""

    def test_the_facts_of_a_resolved_exists_are_the_presence_marker_and_resolved(self):
        for locator in ("app.calc:add", "app.consts:GENESIS"):
            s = spec(locator)
            seen = P.observe(s, self.at, self.env)
            with self.subTest(locator=locator):
                self.assertEqual((seen.kind, seen.verdict), (K.OBSERVED, S), seen)
                self.assertEqual(json.loads(seen.detail), {"subject": "present", "resolved": True})
                self.assertEqual(classify_failure(s, seen), Executed(S))

    def test_exists_never_executes_the_subject(self):
        own = checkout({"app/__init__.py": "", "app/touch.py": PRODUCT["app/touch.py"]})   # its own: nothing else runs it
        self.addCleanup(shutil.rmtree, own, ignore_errors=True)
        at, flag = RevisionRef(SHA, own), pathlib.Path(own, "touched.flag")

        def run_(observable):
            return run_probe(P, spec("app.touch:f", observable), at, self.env).result
        self.assertEqual(run_({"condition": "exists"}), Executed(S))
        self.assertFalse(flag.exists(), "the existence check ran the subject")
        # the contrast: asking for the call does run it, so the flag is what tells the two apart
        self.assertEqual(run_({"returns": 1}), Executed(S))
        self.assertTrue(flag.exists())


class RaisedAttrsMissing(_Revision):
    """Pins aisef2/probe/python_callable_v2.py::HARNESS/main [155]: for a raised exception `raised_attrs` holds the
    declared attributes that exist and serialise, `raised_attrs_unserializable` lists the declared attributes whose
    value does not serialise or whose read raises (module doc), and a MISSING attribute is in neither — so a reader
    of the facts is not told that an attribute which is not there "does not serialise"."""

    def facts_of(self, attrs):
        seen = self.see("app.errors:conflict", {"raises": "ConflictError", "attrs": attrs}, {"args": ["k"]})
        self.assertEqual((seen.kind, seen.verdict), (K.OBSERVED, R), seen)   # a missing attribute is REFUTED
        return json.loads(seen.detail)

    def test_a_missing_attribute_is_in_neither_list(self):
        facts = self.facts_of({"key": "k", "nope": 1})
        self.assertEqual(facts, {"subject": "present", "resolved": True, "raised": "ConflictError",
                                 "raised_attrs": {"key": "k"}, "raised_attrs_unserializable": []})

    def test_a_value_that_does_not_serialise_or_whose_read_raises_is_unserializable_and_missing_is_not(self):
        facts = self.facts_of({"key": "k", "nope": 1, "raw": None, "unreadable": 1})
        self.assertEqual(facts["raised_attrs"], {"key": "k"})
        self.assertEqual(sorted(facts["raised_attrs_unserializable"]), ["raw", "unreadable"])


if __name__ == "__main__":
    unittest.main()
