"""WP-5.5 — RFC §4: invariants I–IX registered with named mechanisms, armed in every test tier before the tier
mounts, and uncontainable; the adversarial cases INV-REG-1..3, INV-MECH-1, INV-EXC-1..2, INV-I-1..4, INV-II-1..4,
INV-III-1..4, INV-IV, INV-V, INV-VI, INV-PROSE-1, INV-MEM-1, INV-PARENT-1, and INV-MUTATION-AUTHORITY."""

import ast
import contextlib
import dataclasses
import importlib
import importlib.util
import inspect
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    INVARIANT_TITLE, BehaviorVerdict, ControlProjection as P, Enforcement as E,
    EventType as T, IdentityGrade as G, InvariantId, Owner, TestExecutionStatus as X, TestOutcome as TO,
    TestSelection as TS, Vacuity as V, Relevance as R,
)
from aisef2.control import budget  # noqa: E402
from aisef2.control.owner import TAXONOMY, FailureCode, classify, flatten  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.invariants import evidence as evd, registry as reg  # noqa: E402
from aisef2.invariants.evidence import Context, EvidenceField, admit  # noqa: E402
from aisef2.invariants.registry import (  # noqa: E402
    REGISTRY, UNCONTAINABLE, Invariant, Mechanism, MechanismKind, RegistrationError, Tier, arm, armed, register,
    require_armed, resolve,
)
from aisef2.journal.event import Event, JournalError  # noqa: E402
from aisef2.journal.fold import fold  # noqa: E402
from aisef2.journal.format2 import JournalWriter2, ResourceKind as K, reconstruct  # noqa: E402
from aisef2.journal.projections import PROJECTIONS  # noqa: E402
from aisef2.probe import protocol as pr  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, ProbeRecord, RevisionRef, bound_result, run_probe  # noqa: E402
from aisef2.product import outcome as oc  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement, UnapprovedContract, binding_problems, require_approved  # noqa: E402
from aisef2.product.contract import ContractError, digest, names_test_artefact  # noqa: E402
from aisef2.product.outcome import Executed, contract_satisfaction  # noqa: E402
from aisef2.quality import test_execution as te, vacuity as vc  # noqa: E402
from aisef2.quality.adequacy import assemble  # noqa: E402
from aisef2.quality.test_execution import CollectionError, TestExecution, unrunnable  # noqa: E402
from aisef2.runtime.capability import CapabilityError, CapabilityIdentity  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from aisef2.runtime.runspec import RunSpecError, comparable, resolve as resolve_spec, runspec_hash  # noqa: E402
from aisef2.runtime.story_scope import StoryScope  # noqa: E402
from tests.v2.p1.test_contract import approve, contract, requirement  # noqa: E402
from tests.v2.p2.test_probe_protocol import AT, ENV, SHA, Fake, record, spec as proof_spec  # noqa: E402
from tests.v2.p3 import journal_gen  # noqa: E402
from tests.v2.p4.test_run_scope import spec as run_spec  # noqa: E402
from tests.v2.p4.test_runspec import kernel, model, spec as runspec  # noqa: E402
from tests.v2.p4.world import BEGIN, closed_after  # noqa: E402

V2 = ROOT / "validation" / "v2"


def _script(name: str):
    spec = importlib.util.spec_from_file_location("aisef_v2_inv_" + name, V2 / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ks = _script("kernel_static_checks")
eb = _script("except_boundaries")
fm = _script("freeze_manifest")
da = _script("destructive_authority")


def replaced(index: int, **changes) -> tuple[Invariant, ...]:
    out = list(REGISTRY)
    out[index] = dataclasses.replace(out[index], **changes)
    return tuple(out)


def fake_root(doc: bool = True, without_init: Tier | None = None) -> tempfile.TemporaryDirectory:
    """A copy of what `register` reads: the kernel, the validation scripts, the tier inits and the document."""
    td = tempfile.TemporaryDirectory(prefix="aisef2-inv-")
    root = pathlib.Path(td.name)
    shutil.copytree(ROOT / "aisef2", root / "aisef2", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "validation" / "v2", root / "validation" / "v2", ignore=shutil.ignore_patterns("__pycache__"))
    for tier in Tier:
        (root / tier.value).mkdir(parents=True, exist_ok=True)
        if tier is not without_init:
            shutil.copy(ROOT / tier.value / "__init__.py", root / tier.value / "__init__.py")
    (root / reg.DOC_REL).parent.mkdir(parents=True, exist_ok=True)
    if doc:
        (root / reg.DOC_REL).write_text(reg.render(), encoding="utf-8")
    return td


# ------------------------------------------------------------------------------------------------ the registry

class Registry(unittest.TestCase):
    def test_the_nine_are_registered_with_frozen_titles_and_resolved_mechanisms(self):
        registered = register()
        self.assertEqual([i.id for i in registered.invariants], list(InvariantId))
        for inv in registered.invariants:
            self.assertEqual(inv.title, INVARIANT_TITLE[inv.id])
            self.assertGreaterEqual(len(inv.mechanisms), 3, inv.id)
            self.assertEqual(inv.tiers, tuple(Tier))
            for m in inv.mechanisms:
                self.assertIsNotNone(resolve(m), m.id)
        for m in UNCONTAINABLE:
            self.assertIsNotNone(resolve(m), m.id)
        self.assertEqual((len(registered.digest), len(registered.mechanism_digest)), (64, 64))
        self.assertEqual(registered.digest, reg.registry_digest())
        self.assertEqual(sorted({m.kind for i in REGISTRY for m in i.mechanisms}, key=lambda k: k.value),
                         sorted(MechanismKind, key=lambda k: k.value))

    def test_INV_REG_1_an_invariant_without_a_mechanism_is_refused(self):
        with self.assertRaisesRegex(RegistrationError, "^I has no enforcement mechanism"):
            register(replaced(0, mechanisms=()), doc=False)
        with self.assertRaisesRegex(RegistrationError, "^IX has no enforcement mechanism"):
            register(replaced(8, mechanisms=()), doc=False)

    def test_INV_REG_2_an_invariant_missing_from_one_tier_is_refused(self):
        without_p3 = tuple(t for t in Tier if t is not Tier.P3)
        with self.assertRaisesRegex(RegistrationError, r"^V is declared but not armed in every tier: \['tests/v2/p3'\]"):
            register(replaced(4, tiers=without_p3), doc=False)
        with fake_root() as root:  # the tier's package does not arm: refused at registration, before any test mounts
            init = pathlib.Path(root, Tier.P3.value, "__init__.py")
            init.write_text(init.read_text(encoding="utf-8").replace("ARMED = arm(Tier.P3)", "ARMED = None"), encoding="utf-8")
            self.assertIs(reg._arms(Tier.P3, pathlib.Path(root)), False)
            with self.assertRaisesRegex(RegistrationError, "^tier tests/v2/p3 does not arm I..IX in its package __init__$"):
                register(root=pathlib.Path(root))
            init.write_text(init.read_text(encoding="utf-8").replace("ARMED = None", "ARMED = arm(Tier.P5)"), encoding="utf-8")
            self.assertIs(reg._arms(Tier.P3, pathlib.Path(root)), False)   # arms another tier: not this one
            with self.assertRaisesRegex(RegistrationError, "^tier tests/v2/p3 does not arm I..IX in its package __init__$"):
                register(root=pathlib.Path(root))
        with fake_root() as root:  # the attribute form arms as well
            init = pathlib.Path(root, Tier.P0.value, "__init__.py")
            init.write_text("from aisef2.invariants import registry\nfrom aisef2.invariants.registry import Tier\n\n"
                            "ARMED = registry.arm(Tier.P0)\n", encoding="utf-8")
            self.assertIs(reg._arms(Tier.P0, pathlib.Path(root)), True)
            register(root=pathlib.Path(root))
        with fake_root(without_init=Tier.PLAN) as root:  # no package __init__ at all
            self.assertIs(reg._arms(Tier.PLAN, pathlib.Path(root)), False)
            with self.assertRaisesRegex(RegistrationError, "^tier tests/v2/plan does not arm I..IX in its package __init__$"):
                register(root=pathlib.Path(root))
        for tier in Tier:
            self.assertIs(reg._arms(tier, ROOT), True)

    def test_INV_REG_3_an_invariant_declared_but_not_armed_is_refused(self):
        with self.assertRaisesRegex(RegistrationError, "^VIII is declared but not armed in every tier"):
            register(replaced(7, tiers=()), doc=False)
        with fake_root() as root:  # tests outside every tier would run unarmed: refused
            stray = pathlib.Path(root, "tests/v2/extra")
            stray.mkdir()
            (stray / "test_x.py").write_text("import unittest\n", encoding="utf-8")
            with self.assertRaisesRegex(RegistrationError, r"^tests live outside every tier, unarmed: tests/v2/extra \(1 directory\)$"):
                register(root=pathlib.Path(root))
            self.assertEqual(reg.test_directories(pathlib.Path(root)), frozenset({"tests/v2/extra"}))
            more = pathlib.Path(root, "tests/v2/aextra")
            more.mkdir()
            (more / "test_y.py").write_text("import unittest\n", encoding="utf-8")
            with self.assertRaisesRegex(RegistrationError, r"^tests live outside every tier, unarmed: tests/v2/aextra \(2 directories\)$"):
                register(root=pathlib.Path(root))
        dirs = reg.test_directories(ROOT)
        self.assertIsInstance(dirs, frozenset)
        self.assertEqual(dirs, frozenset(t.value for t in Tier))   # every tier holds tests, the root included

    def test_unknown_duplicate_omitted_or_retitled_invariants_are_refused(self):
        with self.assertRaisesRegex(RegistrationError, "^the registry holds exactly I..IX in order"):
            register(REGISTRY[:-1], doc=False)
        with self.assertRaisesRegex(RegistrationError, "^duplicate invariant ids"):
            register(REGISTRY + (REGISTRY[0],), doc=False)
        with self.assertRaisesRegex(RegistrationError, "unknown invariant"):
            register(replaced(3, id="X"), doc=False)
        with self.assertRaisesRegex(RegistrationError, "unknown invariant"):
            register(REGISTRY[:8] + ("IX",), doc=False)
        with self.assertRaisesRegex(RegistrationError, "^II: title 'Determinism' is not the frozen 'Semantic Determinism'"):
            register(replaced(1, title="Determinism"), doc=False)
        with self.assertRaisesRegex(RegistrationError, "^the registry holds exactly I..IX in order"):
            register(tuple(reversed(REGISTRY)), doc=False)
        with self.assertRaisesRegex(RegistrationError, "^the registry is a tuple of invariants, closed at registration"):
            register(list(REGISTRY), doc=False)

    def test_a_containable_InvariantError_is_refused_at_registration(self):
        class Contained(Exception):
            pass

        with mock.patch.object(reg, "InvariantError", Contained):
            with self.assertRaisesRegex(RegistrationError, r"^InvariantError must derive from BaseException and not from Exception \(§4\)$"):
                register(doc=False)

    def test_INV_MECH_1_a_mechanism_that_resolves_nowhere_is_refused(self):
        cases = [
            (Mechanism("x.absent-attr", MechanismKind.CODE, "aisef2.product.approval:no_such_function", ""),
             "^x.absent-attr: aisef2.product.approval:no_such_function resolves nowhere$"),
            (Mechanism("x.absent-module", MechanismKind.CODE, "aisef2.no_such_module:f", ""),
             "^x.absent-module: module 'aisef2.no_such_module' does not import: No module named 'aisef2.no_such_module'$"),
            (Mechanism("x.absent-rule", MechanismKind.STATIC_RULE, "kernel_static_checks:NO_SUCH_RULE", ""),
             "^x.absent-rule: NO_SUCH_RULE is not a rule of validation/v2/kernel_static_checks.py$"),
            (Mechanism("x.rule-elsewhere", MechanismKind.STATIC_RULE, "other_checks:NO_PROSE_CONTROL", ""),
             "^x.rule-elsewhere: static rules live in kernel_static_checks, not 'other_checks'$"),
            (Mechanism("x.absent-checker", MechanismKind.CHECKER, "validation/v2/freeze_manifest.py:nope", ""),
             "^x.absent-checker: validation/v2/freeze_manifest.py:nope resolves nowhere$"),
            (Mechanism("x.absent-script", MechanismKind.CHECKER, "validation/v2/no_such.py:check", ""),
             "^validation/v2/no_such.py does not exist$"),
            (Mechanism("x.malformed", MechanismKind.CODE, "aisef2.product.approval", ""),
             "^x.malformed: reference 'aisef2.product.approval' is not <target>:<name>$"),
            (Mechanism("x.untyped-kind", "code", "aisef2.product.approval:require_approved", ""), " is not a typed mechanism$"),
        ]
        checker = resolve(Mechanism("ok", MechanismKind.CHECKER, "validation/v2/freeze_manifest.py:check", ""))
        self.assertEqual(checker.__module__, "aisef2_invariants_freeze_manifest")   # loaded under the registry's own name
        self.assertEqual(resolve(Mechanism("ok", MechanismKind.STATIC_RULE, "kernel_static_checks:NO_PROSE_CONTROL", "")), "NO_PROSE_CONTROL")
        for mechanism, why in cases:
            with self.subTest(mechanism=mechanism.id):
                with self.assertRaisesRegex(RegistrationError, why):
                    resolve(mechanism)
                broken = replaced(0, mechanisms=REGISTRY[0].mechanisms + (mechanism,))
                with self.assertRaisesRegex(RegistrationError, why):
                    register(broken, doc=False)
        with self.assertRaisesRegex(RegistrationError, "resolves nowhere"):
            with mock.patch.object(reg, "UNCONTAINABLE", (Mechanism("all.gone", MechanismKind.CODE, "aisef2.errors:Nope", ""),)):
                register(doc=False)

    def test_registry_and_document_drift_is_refused(self):
        with fake_root() as root:
            doc = pathlib.Path(root, reg.DOC_REL)
            register(root=pathlib.Path(root))                       # in sync: accepted
            doc.write_text(doc.read_text(encoding="utf-8") + "\nedited by hand\n", encoding="utf-8")
            with self.assertRaisesRegex(RegistrationError, "drifted from the registry"):
                register(root=pathlib.Path(root))
        with fake_root(doc=False) as root:
            with self.assertRaisesRegex(RegistrationError, "drifted from the registry"):
                register(root=pathlib.Path(root))
        self.assertEqual(_script("invariants_doc").check(ROOT), [])
        text = reg.render()
        for inv in REGISTRY:
            for m in inv.mechanisms:
                self.assertIn(f"`{m.id}`", text)

    def test_the_document_renders_typed_identifiers_never_read_for_control(self):
        source = (ROOT / "aisef2/invariants/registry.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render")
        for node in ast.walk(tree):  # `role` (prose) is read by render alone
            if isinstance(node, ast.Attribute) and node.attr == "role":
                self.assertTrue(fn.lineno <= node.lineno <= fn.end_lineno, node.lineno)

    def test_InvariantError_is_structurally_uncatchable_by_except_Exception_and_names_its_module(self):
        self.assertTrue(issubclass(InvariantError, BaseException))
        self.assertFalse(issubclass(InvariantError, Exception))
        self.assertTrue(issubclass(RegistrationError, InvariantError))
        try:
            raise InvariantError("x", invariant="VIII")
        except InvariantError as e:
            self.assertEqual((str(e), e.invariant, e.module), ("x", "VIII", __name__))
        with self.assertRaises(InvariantError) as cm:
            require_armed("VIII")
        self.assertEqual(cm.exception.module, "aisef2.invariants.registry")


# ------------------------------------------------------------------------------------------------ arming

class Arming(unittest.TestCase):
    def test_every_tier_arms_all_nine_before_its_first_test_module(self):
        for tier in Tier:
            package = importlib.import_module(tier.value.replace("/", "."))
            self.assertIsInstance(package.ARMED, reg.Armed)
            self.assertEqual((package.ARMED.tier, package.ARMED.invariants), (tier, frozenset(InvariantId)))
        self.assertEqual(dict(armed()), {t: frozenset(InvariantId) for t in Tier})
        order = list(sys.modules)
        prefixes = {t.value.replace("/", "."): t for t in Tier}
        checked = 0
        for name in order:
            bare = name[6:] if name.startswith("tests.") else name
            for prefix in prefixes:
                head = prefix[6:] if prefix.startswith("tests.") else prefix
                if bare.startswith(head + ".test_") and bare.count(".") == head.count(".") + 1:
                    package = name[:len(name) - len(bare) + len(head)]
                    self.assertLess(order.index(package), order.index(name), (package, name))
                    checked += 1
        self.assertGreater(checked, 0)

    def test_arming_is_idempotent_and_fails_closed_without_touching_the_armed_state(self):
        before = dict(armed())
        a, b = arm(Tier.P5), arm(Tier.P5)
        self.assertEqual(a, b)
        with self.assertRaises(RegistrationError):
            arm(Tier.P5, registry=replaced(0, mechanisms=()))
        with self.assertRaisesRegex(RegistrationError, "is not a tier"):
            arm("tests/v2/p5")
        self.assertEqual(dict(armed()), before)

    def test_a_runtime_guard_refuses_to_work_in_an_unarmed_process(self):
        with mock.patch.dict(reg._ARMED, clear=True):
            with self.assertRaisesRegex(InvariantError, "^invariant VIII is not armed in this process: its enforcement mechanism "
                                                        r"is absent, so nothing it guards may proceed \(§4\)$") as cm:
                require_armed(InvariantId.VIII)
            self.assertEqual(cm.exception.invariant, "VIII")
            with self.assertRaisesRegex(InvariantError, "not armed in this process"):
                admit(unrunnable("x"))
        require_armed(InvariantId.VIII)
        admit(unrunnable("x"))


# ------------------------------------------------------------------------------------------------ uncontainable

class Raises:
    """A resource whose release raises an invariant violation."""
    kind = K.SESSION

    def __init__(self, name: str = "verifier-session") -> None:
        self.name = name

    def release(self):
        raise InvariantError("the verifier's session was not the verifier's")


class Uncontainable(unittest.TestCase):
    def test_INV_EXC_1_raised_inside_except_Exception_it_escapes(self):
        def guarded():
            try:
                raise InvariantError("violated")
            except Exception:
                return "held"

        def raised_in_handler():
            try:
                try:
                    raise ValueError("ordinary")
                except Exception:
                    raise InvariantError("violated while handling") from None
            except Exception:
                return "held"

        for fn in (guarded, raised_in_handler):
            with self.subTest(fn=fn.__name__), self.assertRaises(InvariantError):
                fn()

    def test_INV_EXC_2_nested_broad_catches_all_let_it_escape(self):
        def nested():
            try:
                try:
                    try:
                        with contextlib.suppress(Exception):
                            raise InvariantError("deep")
                    except (ValueError, Exception):
                        return "held 3"
                except Exception:
                    return "held 2"
            except Exception as e:
                return f"held 1 {e}"

        with self.assertRaisesRegex(InvariantError, "^deep$"):
            nested()

        def bare():  # the one form that could hold it — which is why the audit refuses it without a re-raise
            try:
                raise InvariantError("held by a bare except")
            except:  # noqa: E722
                return "held"

        self.assertEqual(bare(), "held")
        self.assertEqual(eb.violations("aisef2/x.py", inspect.getsource(bare).replace("        ", "", 1)),
                         ["EXCEPT_BOUNDARY aisef2/x.py:4 bare except does not re-raise InvariantError"])

    def test_the_violation_escapes_the_kernels_own_boundaries(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-inv-") as t:
            path = pathlib.Path(t, "journal.jsonl")
            clock = iter(float(n) for n in range(10 ** 6))
            w = JournalWriter2(path, clock=lambda: next(clock))
            try:
                w.append(T.RUN_BEGIN, BEGIN)
                w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
                emit = lambda t_, data, source_seqs=(): w.append(t_, data, source_seqs=source_seqs)  # noqa: E731
                for timeout in (None, 5.0):  # inline, and through the release thread
                    with self.subTest(timeout=timeout):
                        scope = StoryScope("S1", emit, release_timeout_s=timeout)
                        resource = scope.acquire(Raises(f"verifier-session-{timeout}"))
                        with self.assertRaisesRegex(InvariantError, "not the verifier's"):
                            scope.release(resource)
            finally:
                w.close()

    def test_the_audit_holds_over_the_whole_kernel(self):
        result = eb.audit(ROOT)
        self.assertEqual(result["problems"], [])
        self.assertEqual(set(result["counts"]), {eb.RERAISES, eb.STRUCTURAL})
        self.assertGreaterEqual(len(result["boundaries"]), 30)
        real = {(b["catches"], b["disposition"]) for b in result["boundaries"] if b["path"] == "aisef2/runtime/story_scope.py"}
        self.assertEqual(real, {("JournalError", eb.STRUCTURAL), ("InvariantError", eb.RERAISES), ("Exception", eb.RERAISES),
                                ("BaseException", eb.RERAISES), ("Residual", eb.RERAISES)})
        self.assertEqual(result["counts"][eb.RERAISES], 7)   # the seven boundaries that could hold it all re-raise

    def test_the_audit_flags_every_swallowing_pattern_and_accepts_every_re_raise(self):
        def v(src):
            return eb.violations("aisef2/x.py", src)

        self.assertEqual(v("try:\n    f()\nexcept:\n    pass\n"), ["EXCEPT_BOUNDARY aisef2/x.py:3 bare except does not re-raise InvariantError"])
        self.assertEqual(v("try:\n    f()\nexcept BaseException:\n    log()\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:3 except BaseException: could hold an InvariantError (BaseException) and does not re-raise it"])
        self.assertEqual(v("try:\n    f()\nexcept (ValueError, BaseException) as e:\n    log(e)\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:3 except (ValueError, BaseException): could hold an InvariantError (BaseException) and does not re-raise it"])
        self.assertEqual(v("from aisef2.errors import InvariantError\ntry:\n    f()\nexcept InvariantError:\n    pass\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:4 except InvariantError: 'InvariantError' cannot be resolved to an exception class; it could hold an InvariantError"])
        self.assertEqual(v("try:\n    f()\nexcept Something:\n    pass\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:3 except Something: 'Something' cannot be resolved to an exception class; it could hold an InvariantError"])
        self.assertEqual(v("class Mine(BaseException):\n    pass\ntry:\n    f()\nexcept Mine:\n    pass\n"), [])   # a sibling of InvariantError cannot hold it
        self.assertEqual(v("class Mine(InvariantError):\n    pass\ntry:\n    f()\nexcept Mine:\n    pass\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:5 except Mine: 'Mine' cannot be resolved to an exception class; it could hold an InvariantError"])
        self.assertEqual(v("import contextlib\nwith contextlib.suppress(BaseException):\n    f()\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:2 suppress(BaseException) would swallow an InvariantError"])
        self.assertEqual(v("try:\n    f()\nexcept exceptions[0]:\n    pass\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:3 except exceptions[0]: a catch pattern the audit does not model; it could hold an InvariantError"])
        # accepted: structural, or re-raised
        self.assertEqual(v("try:\n    f()\nexcept Exception:\n    pass\n"), [])
        self.assertEqual(v("try:\n    f()\nexcept (OSError, ValueError):\n    pass\n"), [])
        self.assertEqual(v("class Mine(ValueError):\n    pass\ntry:\n    f()\nexcept Mine:\n    pass\n"), [])
        self.assertEqual(v("import contextlib\nwith contextlib.suppress(Exception, OSError):\n    f()\n"), [])
        self.assertEqual(v("try:\n    f()\nexcept InvariantError:\n    raise\nexcept BaseException:\n    pass\n"), [])
        self.assertEqual(v("try:\n    f()\nexcept OSError:\n    raise\nexcept BaseException:\n    pass\n"),   # re-raising OSError precedes nothing
                         ["EXCEPT_BOUNDARY aisef2/x.py:5 except BaseException: could hold an InvariantError (BaseException) and does not re-raise it"])
        self.assertEqual(v("try:\n    f()\nexcept InvariantError:\n    pass\nexcept BaseException:\n    pass\n"),   # holding it precedes nothing
                         ["EXCEPT_BOUNDARY aisef2/x.py:3 except InvariantError: 'InvariantError' cannot be resolved to an exception class; it could hold an InvariantError",
                          "EXCEPT_BOUNDARY aisef2/x.py:5 except BaseException: could hold an InvariantError (BaseException) and does not re-raise it"])
        self.assertEqual(v("try:\n    f()\nexcept BaseException:\n    undo()\n    raise\n"), [])
        self.assertEqual(v("try:\n    f()\nexcept:\n    undo()\n    raise\n"), [])
        self.assertEqual(v("try:\n    f()\nexcept (BaseException, BaseException):\n    pass\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:3 except (BaseException, BaseException): could hold an InvariantError "
                          "(BaseException, BaseException) and does not re-raise it"])
        self.assertEqual(v("from contextlib import suppress\nwith suppress(BaseException):\n    f()\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:2 suppress(BaseException) would swallow an InvariantError"])
        self.assertEqual(v("import contextlib\nwith contextlib.suppress(OSError, BaseException):\n    f()\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:2 suppress(OSError, BaseException) would swallow an InvariantError"])
        self.assertEqual(eb.audit_source("aisef2/x.py", "import contextlib\nwith contextlib.suppress(OSError, BaseException):\n    f()\n")[0],
                         [{"path": "aisef2/x.py", "line": 2, "catches": "suppress(OSError, BaseException)", "disposition": "HOLDS"}])
        self.assertEqual(v("try:\n    f()\nexcept* BaseException:\n    pass\n"),
                         ["EXCEPT_BOUNDARY aisef2/x.py:3 except BaseException: could hold an InvariantError (BaseException) and does not re-raise it"])
        # a real kernel module: its own exception classes resolve through the import
        real = eb.violations("aisef2/runtime/story_scope.py", (ROOT / "aisef2/runtime/story_scope.py").read_text(encoding="utf-8"))
        self.assertEqual(real, [])

    def test_the_audit_records_every_boundary_with_its_disposition(self):
        source = ("import contextlib\ntry:\n    f()\nexcept InvariantError:\n    raise\nexcept Exception:\n    pass\n"
                  "try:\n    g()\nexcept:\n    pass\nexcept ValueError:\n    pass\n"
                  "try:\n    h()\nexcept BaseException:\n    log()\nexcept Something:\n    pass\nexcept exceptions[0]:\n    pass\n"
                  "with contextlib.suppress(BaseException):\n    k()\nwith contextlib.suppress(OSError):\n    m()\n")
        boundaries, problems = eb.audit_source("aisef2/y.py", source)
        self.assertEqual(boundaries, [
            {"path": "aisef2/y.py", "line": 4, "catches": "InvariantError", "disposition": eb.RERAISES},
            {"path": "aisef2/y.py", "line": 6, "catches": "Exception", "disposition": eb.RERAISES},
            {"path": "aisef2/y.py", "line": 10, "catches": "<bare>", "disposition": "BARE"},
            {"path": "aisef2/y.py", "line": 12, "catches": "ValueError", "disposition": eb.STRUCTURAL},
            {"path": "aisef2/y.py", "line": 16, "catches": "BaseException", "disposition": "HOLDS"},
            {"path": "aisef2/y.py", "line": 18, "catches": "Something", "disposition": "UNKNOWN"},
            {"path": "aisef2/y.py", "line": 20, "catches": "exceptions[0]", "disposition": "UNKNOWN"},
            {"path": "aisef2/y.py", "line": 22, "catches": "suppress(BaseException)", "disposition": "HOLDS"},
            {"path": "aisef2/y.py", "line": 24, "catches": "suppress(OSError)", "disposition": eb.STRUCTURAL},
        ])
        self.assertEqual(len(problems), 5)
        result = eb.audit(ROOT)
        self.assertEqual([b["path"] for b in result["boundaries"]], sorted(b["path"] for b in result["boundaries"]))
        self.assertEqual(list(result["counts"]), sorted(result["counts"]))
        self.assertEqual(eb.check(ROOT), [])
        with tempfile.TemporaryDirectory(prefix="aisef2-inv-") as t:
            pathlib.Path(t, "aisef2").mkdir()
            pathlib.Path(t, "aisef2", "x.py").write_text("try:\n    f()\nexcept:\n    pass\n", encoding="utf-8")
            self.assertEqual(eb.check(pathlib.Path(t)), ["EXCEPT_BOUNDARY aisef2/x.py:3 bare except does not re-raise InvariantError"])

    def test_the_hierarchy_is_part_of_the_audit(self):
        class Contained(Exception):
            pass

        with mock.patch.object(eb, "InvariantError", Contained):
            problems = eb.audit(ROOT)["problems"]
            synthetic = eb.violations("aisef2/x.py", "try:\n    f()\nexcept Exception:\n    pass\n")
        self.assertTrue(problems and problems[0].startswith("InvariantError must derive from BaseException"))
        self.assertEqual(synthetic, ["EXCEPT_BOUNDARY aisef2/x.py:3 except Exception: could hold an InvariantError (Exception) and does not re-raise it"])


# ------------------------------------------------------------------------------------------------ I

class RequirementAuthority(unittest.TestCase):
    def test_INV_I_1_no_kernel_control_path_reads_requirement_text(self):
        self.assertEqual(ks.check(ROOT, ("NO_PROSE_CONTROL",)), [])
        hit = ks.violations("aisef2/control/x.py", "def decide(req):\n    return 'quiet' in req.text\n", ("NO_PROSE_CONTROL",))
        self.assertEqual(len(hit), 1)
        self.assertTrue(hit[0].startswith("NO_PROSE_CONTROL aisef2/control/x.py:2"))

    def test_INV_I_2_an_unapproved_contract_cannot_become_product_truth(self):
        req, c = requirement(), contract()
        with self.assertRaisesRegex(UnapprovedContract, "no approval binds requirement_hash and contract_hash"):
            require_approved(c, {req.id: req}, [])
        require_approved(c, {req.id: req}, [approve(req, c)])
        with self.assertRaisesRegex(UnapprovedContract, "requirement unknown"):
            require_approved(c, {}, [approve(req, c)])

    def test_INV_I_3_changing_a_requirement_or_contract_hash_invalidates_the_binding(self):
        req, c = requirement(), contract()
        a = approve(req, c)
        self.assertEqual(binding_problems(a, req, c), [])
        edited_req = requirement(text="quiet mode prints a banner")
        self.assertNotEqual(edited_req.requirement_hash, req.requirement_hash)
        self.assertEqual(binding_problems(a, edited_req, c), ["approval does not bind requirement REQ-1 at its current hash"])
        edited_c = contract(rationale="another reading")
        self.assertEqual(binding_problems(a, req, edited_c), [f"approval does not bind contract {c.id} at its current hash"])
        with self.assertRaises(UnapprovedContract):
            require_approved(edited_c, {req.id: req}, [a])

    def test_INV_I_4_an_artefacts_self_claims_grant_no_authority(self):
        with self.assertRaisesRegex(ContractError, "requirement_hash does not bind this content"):
            Requirement("REQ-1", "quiet mode prints nothing", "docs/req.md@abc", "0" * 64)
        req, c = requirement(), contract()
        with self.assertRaisesRegex(ContractError, "approval authority belongs to a human identity"):
            ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "model:claude", 1.0, ())
        with self.assertRaisesRegex(InvariantError, "record_digest does not bind this record"):
            ProbeRecord(spec_id=proof_spec().id, semantic_hash=proof_spec().semantic_hash, probe_id=Fake.id,
                        probe_digest=Fake.digest, revision=SHA, enforcement=E.PARTIAL, result=Executed(BehaviorVerdict.SATISFIED),
                        record_digest="0" * 64)
        with self.assertRaisesRegex(InvariantError, "reads a ProbeRecord, never a bare ProbeResult"):
            bound_result({"result": "SATISFIED"}, spec=proof_spec(), revision=SHA, enforcement=E.PARTIAL)


# ------------------------------------------------------------------------------------------------ II

class SemanticDeterminism(unittest.TestCase):
    def test_INV_II_1_developer_test_topology_is_not_an_input_of_the_product_verdict(self):
        self.assertEqual(list(inspect.signature(contract_satisfaction).parameters), ["result", "spec"])
        self.assertEqual(list(inspect.signature(run_probe).parameters), ["probe", "spec", "at", "env"])
        for cls in (oc.Executed, oc.Unrunnable, oc.InvalidSpec, ProbeRecord, RevisionRef, ExecutionEnv):
            names = {f.name for f in dataclasses.fields(cls)}
            self.assertFalse(names & {"tests", "test_path", "paths", "layout", "developer_tests"}, cls.__name__)
        s = proof_spec()
        with tempfile.TemporaryDirectory(prefix="aisef2-inv-") as t:
            before = contract_satisfaction(Executed(BehaviorVerdict.SATISFIED), s)
            (pathlib.Path(t) / "tests").mkdir()
            (pathlib.Path(t) / "tests" / "test_moved.py").write_text("import unittest\n", encoding="utf-8")
            (pathlib.Path(t) / "tests").rename(pathlib.Path(t) / "spec")
            after = contract_satisfaction(Executed(BehaviorVerdict.SATISFIED), s)
        self.assertIs(before, after)
        # the engineering side: REL-8 (another layout, the same measurement) and VAC-11 (moved tests, the same result)
        rel = (ROOT / "tests/v2/p5/test_relevance.py").read_text(encoding="utf-8")
        vac = (ROOT / "tests/v2/p5/test_vacuity.py").read_text(encoding="utf-8")
        self.assertIn("def test_REL_8_for_real_the_same_tests_in_another_layout", rel)
        self.assertIn("def test_VAC_11_moving_the_developer_tests_does_not_change_the_result", vac)

    def test_INV_II_2_wall_clock_time_does_not_control_verdicts_or_projections(self):
        self.assertEqual(ks.check(ROOT, ("NO_TIME_IN_PROJECTIONS",)), [])
        events = reconstruct(journal_gen.journal(3)).events
        shifted = tuple(dataclasses.replace(e, time=1e9 - e.seq) for e in events)
        for p in PROJECTIONS:
            with self.subTest(projection=p.value):
                self.assertEqual(fold(PROJECTIONS[p], events), fold(PROJECTIONS[p], shifted))
        self.assertEqual(Event(0, "run/begin", BEGIN, 1.0), Event(0, "run/begin", BEGIN, 1.0))
        self.assertNotIn("time", inspect.signature(budget.charge).parameters)

    def test_INV_II_3_component_import_order_does_not_alter_the_fold(self):
        modules = ["aisef2.control.budget", "aisef2.quality.adequacy", "aisef2.journal.projections",
                   "aisef2.runtime.run_scope", "aisef2.plan.story_admission"]
        outputs = []
        for order in (modules, list(reversed(modules))):
            code = ("import sys\nsys.path.insert(0, %r)\n" % str(ROOT)
                    + "".join(f"import {m}\n" for m in order)
                    + "from aisef2.journal.format2 import reconstruct\nfrom aisef2.journal.fold import fold\n"
                      "from aisef2.journal.projections import PROJECTIONS\nfrom aisef2.product.contract import digest\n"
                      "from tests.v2.p3 import journal_gen\n"
                      "events = reconstruct(journal_gen.journal(11)).events\n"
                      "print(digest({p.value: repr(fold(PROJECTIONS[p], events)) for p in PROJECTIONS}))\n")
            r = subprocess.run([sys.executable, "-P", "-c", code], cwd=ROOT, capture_output=True, encoding="utf-8", timeout=180)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            outputs.append(r.stdout.strip())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(len(outputs[0]), 64)

    def test_INV_II_4_the_same_frozen_inputs_give_the_same_run_identity(self):
        caps = (kernel(), model())
        settings = {"revision": {"value": SHA, "layer": "cli"}}
        h = runspec_hash(caps, G.VERIFIED, settings)
        self.assertEqual(h, runspec_hash(tuple(reversed(caps)), G.VERIFIED, settings))
        self.assertEqual(runspec(*caps).runspec_hash, runspec(*caps).runspec_hash)
        self.assertNotEqual(h, runspec_hash(caps, G.ATTESTED, settings))
        self.assertNotEqual(h, runspec_hash(caps, G.VERIFIED, {"revision": {"value": "b" * 40, "layer": "cli"}}))
        self.assertNotEqual(h, runspec_hash((kernel(b"kernel v2"), model()), G.VERIFIED, settings))
        self.assertNotEqual(h, runspec_hash((kernel(enforcement=E.PARTIAL), model()), G.VERIFIED, settings))


# ------------------------------------------------------------------------------------------------ III

class IndependentEvidence(unittest.TestCase):
    def test_INV_III_1_the_implementer_cannot_manufacture_a_sealed_record(self):
        r = record()
        with self.assertRaisesRegex(InvariantError, "an edited record is a new record"):
            dataclasses.replace(r, result=Executed(BehaviorVerdict.REFUTED))
        with self.assertRaisesRegex(InvariantError, "an edited record is a new record"):
            dataclasses.replace(r, revision="b" * 40)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            r.result = Executed(BehaviorVerdict.REFUTED)
        producers = set()
        for path in sorted((ROOT / "aisef2").rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and ast.unparse(node.func) in ("ProbeRecord.create", "ProbeRecord"):
                    producers.add(path.relative_to(ROOT).as_posix())
        # the harness seals records (run_probe); story admission rebuilds one from the journal payload, re-verified by its digest
        self.assertEqual(producers, {"aisef2/probe/protocol.py", "aisef2/plan/story_admission.py"})
        self.assertFalse(hasattr(pr, "VerifiedProof"))              # not yet built (P6): nothing can manufacture it

    def test_INV_III_2_the_verifier_scope_is_independently_acquired(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-inv-") as t:
            clock = iter(float(n) for n in range(10 ** 6))
            w = JournalWriter2(pathlib.Path(t, "journal.jsonl"), clock=lambda: next(clock))
            try:
                w.append(T.RUN_BEGIN, BEGIN)
                w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
                emit = lambda t_, data, source_seqs=(): w.append(t_, data, source_seqs=source_seqs)  # noqa: E731
                scope = StoryScope("S1", emit, release_timeout_s=None)
                mine = scope.acquire(Raises())
                self.assertEqual(scope.held, ("verifier-session",))
                acquired = [e for e in w.events if e.type == T.STORY_RESOURCE_ACQUIRED.value]
                self.assertEqual([e.data["story_id"] for e in acquired], ["S1"])      # the scope's own story, nobody else's
                foreign = Raises()
                with self.assertRaisesRegex(Exception, "not the most recent resource"):
                    scope.release(foreign)                                            # a resource the scope did not acquire
                self.assertIs(mine, scope._stack[-1][0])
                scope._stack.clear()
            finally:
                w.close()
        self.assertEqual(list(inspect.signature(StoryScope.__init__).parameters), ["self", "story_id", "emit", "release_timeout_s"])

    def test_INV_III_3_confinement_is_not_a_passable_parameter(self):
        sig = inspect.signature(run_probe)
        self.assertEqual([(n, p.default is inspect.Parameter.empty) for n, p in sig.parameters.items()],
                         [("probe", True), ("spec", True), ("at", True), ("env", True)])
        for extra in ("cwd", "env_override", "confinement", "sandbox", "test_path"):
            with self.subTest(extra=extra), self.assertRaises(TypeError):
                run_probe(Fake(), proof_spec(), AT, ENV, **{extra: "x"})
            with self.subTest(extra=extra, cls="ExecutionEnv"), self.assertRaises(TypeError):
                ExecutionEnv(sys.executable, 5, E.FULL, **{extra: "x"})
        bound = inspect.signature(bound_result)
        for name in ("spec", "revision", "enforcement"):
            self.assertIs(bound.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(bound.parameters[name].default, inspect.Parameter.empty)
        with self.assertRaisesRegex(InvariantError, "a probe runs a ProductProofSpec at a RevisionRef in an ExecutionEnv"):
            run_probe(Fake(), proof_spec(), AT, {"interpreter": sys.executable})

    def test_INV_III_4_developer_tests_cannot_certify_product_proof(self):
        for package in ("aisef2/product", "aisef2/probe", "aisef2/control", "aisef2/plan"):
            for path in sorted((ROOT / package).rglob("*.py")):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if isinstance(node, ast.ImportFrom):
                        self.assertFalse((node.module or "").startswith("aisef2.quality"), path)
                    if isinstance(node, ast.Import):
                        self.assertFalse(any(a.name.startswith("aisef2.quality") for a in node.names), path)
        ran = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, None, "ran")
        a = assemble(ran, V.NON_VACUOUS, R.RELEVANT, ran)
        self.assertFalse({"ProbeResult", "ProductProofSpec", "VerifiedProof", "BehaviorVerdict"} & set(vars(type(a.adequacy)).keys()))
        self.assertNotIn("aisef2.product.outcome", _closure("aisef2.quality.adequacy") - _closure("aisef2.quality.test_execution"))


def _closure(module: str) -> set[str]:
    seen, todo = set(), {module}
    while todo:
        mod = todo.pop()
        seen.add(mod)
        rel = mod.replace(".", "/") + ".py"
        if (ROOT / rel).exists():
            for n in ast.walk(ast.parse((ROOT / rel).read_text(encoding="utf-8"))):
                if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("aisef2"):
                    todo.add(n.module) if n.module not in seen else None
                elif isinstance(n, ast.Import):
                    todo.update(a.name for a in n.names if a.name.startswith("aisef2") and a.name not in seen)
    return seen


# ------------------------------------------------------------------------------------------------ IV

class TypedOwnership(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-inv-")
        self.run = closed_after(self, RunScope(self._d.name, "run-iv", spec=run_spec, clock=lambda: 1.0))
        self.run.begin()
        self.run.append(T.PLAN_FROZEN, {"plan_id": "PLAN-IV", "plan_hash": "b" * 64, "roles": {"C1": "INTRODUCE"}})

    def tearDown(self):
        self._d.cleanup()

    def attempt(self, story):
        self.run.append(T.STORY_BEGIN, {"story_id": story, "parent": SHA})
        self.run.append(T.STORY_ADMITTED, {"story_id": story, "parent": SHA, "admitted": True,
                                           "developer_call_permitted": True, "dispositions": {"C1": "READY"}})

    def fail(self, code, story):
        extra = {"original": "OSError"} if code is FailureCode.UNKNOWN else {}
        return self.run.append(T.FAILURE_OBSERVED, {"story_id": story, "code": code.value, "detail": "", **extra})

    def test_INV_IV_no_owner_consumes_another_owners_budget(self):
        limits = {o: 5 for o in Owner}
        by_owner = {o: [c for c, k in TAXONOMY.items() if k.owner is o] for o in Owner}
        self.assertEqual({o.value for o, codes in by_owner.items() if not codes}, {"REVIEW", "SECURITY"})  # no code charges them
        for n, (owner, codes) in enumerate(by_owner.items()):
            for code in codes:
                story = f"S-{n}-{code.value}"
                with self.subTest(owner=owner.value, code=code.value):
                    self.attempt(story)
                    developer_before = dict(budget.developer_spend(self.run.events, story))
                    self.fail(code, story)
                    c = budget.charge(self.run.events, story, limits)
                    want = TAXONOMY[code].budget
                    self.assertIn(c.budget, (owner.value, None))
                    self.assertEqual(c.budget, want.value if want else None)
                    if owner is not Owner.DEVELOPER:
                        self.assertNotEqual(c.budget, "DEVELOPER")
                    if want is not None:
                        self.run.retry(story, limits)
                        spent = self.run.state(P.BUDGETS)["retries"].get(story, {})
                        self.assertEqual(spent, {want.value: 1})
                        if owner is not Owner.DEVELOPER:
                            self.assertNotIn("DEVELOPER", spent)
                    self.assertEqual(dict(budget.developer_spend(self.run.events, story)), developer_before)
        # PLAN cannot consume DEVELOPER even when only the developer budget is funded
        self.attempt("S-plan")
        self.fail(FailureCode.PRECONDITION_BROKEN, "S-plan")
        c = budget.charge(self.run.events, "S-plan", {Owner.DEVELOPER: 99})
        self.assertEqual((c.retry, c.budget), (False, None))

    def test_INV_IV_INCOMPLETE_and_UNRUNNABLE_never_charge_the_developer(self):
        ran = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, None, "ran")
        for a in (assemble(unrunnable("no interpreter"), None, None, ran), assemble(ran, V.NON_VACUOUS, R.RELEVANT, unrunnable("x")),
                  assemble(ran, V.INDETERMINATE, R.RELEVANT, ran), assemble(ran, V.NON_VACUOUS, R.UNMEASURABLE, ran)):
            with self.subTest(outcome=a.outcome):
                self.assertFalse(a.developer_chargeable)
                self.assertIsNot(a.owner, Owner.DEVELOPER)

    def test_INV_IV_retry_reads_typed_fields_only_and_keeps_no_counter(self):
        self.assertEqual(ks.check(ROOT, ("NO_SIDE_RETRY_COUNTER", "RETRYABLE_ONLY_IN_TAXONOMY")), [])
        self.assertEqual({k for k, v in vars(budget).items() if isinstance(v, (list, dict, set)) and not k.startswith("__")}, set())
        with self.assertRaisesRegex(InvariantError, "is not a typed failure code"):
            classify("PROVIDER_UNAVAILABLE")


# ------------------------------------------------------------------------------------------------ V

class ReproducibleQualification(unittest.TestCase):
    def test_INV_V_comparability_rejects_every_identity_mismatch(self):
        a = runspec(kernel(), model())
        self.assertEqual(comparable(a, runspec(kernel(), model())), (True, []))
        same, why = comparable(a, runspec(kernel(b"kernel v2"), model()))
        self.assertEqual((same, why), (False, ["kernel: digest differs"]))
        same, why = comparable(a, runspec(kernel(enforcement=E.PARTIAL), model()))
        self.assertEqual((same, why), (False, ["kernel: enforcement FULL vs PARTIAL"]))
        opaque_kernel = CapabilityIdentity("kernel", G.OPAQUE, {"version": "1"}, E.FULL)
        same, why = comparable(a, runspec(opaque_kernel, model()))
        self.assertFalse(same)
        self.assertTrue(any("grade VERIFIED vs OPAQUE" in w for w in why), why)
        same, why = comparable(a, runspec(kernel()))
        self.assertEqual((same, why), (False, ["model: only in one run"]))
        self.assertNotEqual(a.runspec_hash, runspec(kernel(), model(), settings={"x": {"value": 1, "layer": "cli"}}).runspec_hash)
        with self.assertRaises(CapabilityError):
            CapabilityIdentity("kernel", G.VERIFIED, {"version": "1.2.3"}, E.FULL)   # a label is not an identity


# ------------------------------------------------------------------------------------------------ VI

class ImmutableProvenance(unittest.TestCase):
    def test_INV_VI_abbreviated_shas_are_rejected_where_full_identity_is_required(self):
        for bad in (SHA[:12], SHA[:39], "main", "HEAD", SHA.upper()):
            with self.subTest(sha=bad):
                with self.assertRaisesRegex(InvariantError, "full 40-hex SHA"):
                    RevisionRef(bad, "/checkout")
                with self.assertRaisesRegex(RunSpecError, "the full 40-hex SHA is the authoritative identity"):
                    resolve_spec((kernel(),), {}, bad)
        with tempfile.TemporaryDirectory(prefix="aisef2-inv-") as t:
            w = JournalWriter2(pathlib.Path(t, "j.jsonl"), clock=lambda: 1.0)
            try:
                w.append(T.RUN_BEGIN, BEGIN)
                with self.assertRaises(JournalError):
                    w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA[:12]})
            finally:
                w.close()

    def test_INV_VI_mutable_labels_cannot_replace_immutable_ids(self):
        with self.assertRaisesRegex(CapabilityError, "VERIFIED binds a locally computed sha256 digest"):
            CapabilityIdentity("kernel", G.VERIFIED, {"version": "1.2.3"}, E.FULL)
        k = kernel(version="1.2.3")
        self.assertEqual(k.tuple_["digest"], kernel().tuple_["digest"])
        self.assertNotEqual(kernel(b"kernel v2", version="1.2.3").identity, k.identity)  # the label did not move

    def test_INV_VI_the_journal_is_append_only(self):
        public = sorted(n for n in dir(JournalWriter2) if not n.startswith("_"))
        self.assertEqual(public, ["append", "close", "emit", "events", "head", "path"])
        self.assertNotIn("seq", inspect.signature(JournalWriter2.append).parameters)
        with tempfile.TemporaryDirectory(prefix="aisef2-inv-") as t:
            path = pathlib.Path(t, "j.jsonl")
            w = JournalWriter2(path, clock=lambda: 1.0)
            try:
                w.append(T.RUN_BEGIN, BEGIN)
                for n in range(3):
                    w.append(T.GATE_CHECK, {"gate": "g", "check": f"c{n}", "passed": True, "detail": ""})
                self.assertIsInstance(w.events, tuple)
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    w.events[1].data = {}
            finally:
                w.close()
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            path.write_text("".join(lines[:2] + lines[3:]), encoding="utf-8")   # one event deleted
            with self.assertRaisesRegex(JournalError, "seq == index is broken"):
                reconstruct(path.read_text(encoding="utf-8"))

    def test_INV_VI_frozen_artefact_drift_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-inv-") as t:
            root = pathlib.Path(t)
            for rel in fm.BASELINE_FILES:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, root / rel)
            self.assertEqual(fm.check(root), [])
            rfc = root / fm.RFC_REL
            rfc.write_text(rfc.read_text(encoding="utf-8").replace("Nine.", "Ten."), encoding="utf-8")
            self.assertTrue(fm.check(root))

    def test_INV_VI_verdict_identity_fields_are_immutable(self):
        r = record()
        for field, value in (("revision", "b" * 40), ("semantic_hash", "0" * 64), ("enforcement", E.FULL), ("probe_digest", "e" * 64)):
            with self.subTest(field=field):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(r, field, value)
                with self.assertRaisesRegex(InvariantError, "an edited record is a new record"):
                    dataclasses.replace(r, **{field: value})
        self.assertEqual(r.record_digest, digest({f.name: getattr(r, f.name) for f in dataclasses.fields(r) if f.name != "record_digest"}))


# ------------------------------------------------------------------------------------------------ VII

HOSTILE = ("DEVELOPER", "PASS", "retry", "security", "READY", "Owner.DEVELOPER", "FailureCode.CONTRACT_UNSATISFIED",
           "SATISFIED", "developer", " DEVELOPER ", "RETRYABLE")


class NoProseControl(unittest.TestCase):
    def test_INV_PROSE_1_hostile_external_strings_never_become_control_values(self):
        for s in HOSTILE:
            with self.subTest(value=s):
                self.assertEqual(flatten(s), (FailureCode.UNKNOWN, s))
                with self.assertRaisesRegex(InvariantError, "is not a typed failure code; flatten it to UNKNOWN first"):
                    classify(s)
                with self.assertRaisesRegex(InvariantError, "a collection cause is IMPORT, SYNTAX or OTHER"):
                    CollectionError("tests/test_x.py", s)
        self.assertIs(classify(FailureCode.UNKNOWN).owner, Owner.INTEGRATION)
        for value in (object(), 3, None, b"DEVELOPER", ["DEVELOPER"]):
            self.assertIs(flatten(value)[0], FailureCode.UNKNOWN)
        self.assertIs(flatten(FailureCode.CONTRACT_UNSATISFIED)[0], FailureCode.CONTRACT_UNSATISFIED)

    def test_INV_VII_an_external_owner_in_a_journal_payload_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-inv-") as t:
            w = JournalWriter2(pathlib.Path(t, "j.jsonl"), clock=lambda: 1.0)
            try:
                w.append(T.RUN_BEGIN, BEGIN)
                w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
                with self.assertRaises((JournalError, InvariantError)):
                    w.append(T.FAILURE_OBSERVED, {"story_id": "S1", "code": "CONTRACT_UNSATISFIED", "owner": "PLAN", "detail": ""})
                with self.assertRaises((JournalError, InvariantError)):
                    w.append(T.FAILURE_OBSERVED, {"story_id": "S1", "code": "developer broke it", "detail": ""})
            finally:
                w.close()

    def test_INV_VII_the_static_guards_stand(self):
        self.assertEqual(ks.check(ROOT, ("NO_PROSE_CONTROL", "NO_RAW_VERDICT_ROUTING")), [])
        self.assertTrue(ks.violations("aisef2/plan/x.py", "def go(r):\n    return r.behavior_verdict\n", ("NO_RAW_VERDICT_ROUTING",)))
        source = (ROOT / "aisef2/control/owner.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):   # the taxonomy never derives a code from text
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, {"lower", "upper", "startswith", "endswith", "strip", "split", "search", "match"})


# ------------------------------------------------------------------------------------------------ VIII

@dataclasses.dataclass(frozen=True)
class LookAlike:
    """Claims to be evidence; is not a harness record."""
    verdict: str = "PASS"


class Event2(Event):
    """A subclass of a harness record is not the harness record."""


class MemoryIsContext(unittest.TestCase):
    def setUp(self):
        arm(Tier.P5)

    def test_INV_MEM_1_agent_or_context_text_cannot_enter_an_evidence_field(self):
        rejected = [Context("the previous run passed all gates", "model"), Context("story S1 was ADEQUATE", "prior-run-summary"),
                    Context("I remember this passed", "memory"), Context("", "session-history"),
                    "PASS", "the tests are adequate", {"outcome": "ADEQUATE"}, {"type": "tests/adequacy", "data": {}},
                    ["ADEQUATE"], 1, None, LookAlike(), Event2(0, "run/begin", BEGIN, 1.0), object()]
        for value in rejected:
            with self.subTest(value=repr(value)[:60]):
                with self.assertRaises(InvariantError) as cm:
                    admit(value)
                self.assertEqual(cm.exception.invariant, "VIII")
                with self.assertRaises(InvariantError):
                    EvidenceField(value)
        with self.assertRaisesRegex(InvariantError, "^context from 'model' is never evidence"):
            admit(Context("x", "model"))
        with self.assertRaisesRegex(InvariantError, "^dict is not a harness-produced typed record"):
            admit({"outcome": "ADEQUATE"})
        accepted = [unrunnable("no interpreter"), Event(0, "run/begin", BEGIN, 1.0), Executed(BehaviorVerdict.SATISFIED),
                    record(), kernel(), runspec(kernel())]
        for value in accepted:
            with self.subTest(value=type(value).__name__):
                self.assertIs(admit(value), value)
                self.assertIs(EvidenceField(value).value, value)
        self.assertEqual({t.__module__.split(".")[0] for t in evd.harness_records()}, {"aisef2"})
        self.assertEqual({t.__name__ for t in evd.harness_records()},
                         {"Event", "ProbeRecord", "Executed", "Unrunnable", "InvalidSpec", "TestExecution", "RunnerReport", "ResultSet",
                          "RelevanceResult", "VacuityResult", "EngineeringTestAdequacy", "Assembly", "CapabilityIdentity", "RunSpec", "Charge"})

    def test_the_boundary_inspects_no_model_and_fails_closed(self):
        source = (ROOT / "aisef2/invariants/evidence.py").read_text(encoding="utf-8")
        for name in ("openai", "anthropic", "requests", "http", "subprocess", "sqlite3"):
            self.assertNotIn(f"import {name}", source)
        with mock.patch.dict(reg._ARMED, clear=True):
            with self.assertRaisesRegex(InvariantError, "not armed"):
                admit(unrunnable("x"))
        with mock.patch.dict(reg._ARMED, {Tier.P5: frozenset(InvariantId) - {InvariantId.VIII}}, clear=True):
            with self.assertRaisesRegex(InvariantError, "^invariant VIII is not armed in this process"):   # VIII itself
                admit(unrunnable("x"))


# ------------------------------------------------------------------------------------------------ IX

class NoDeveloperArtefactAtParent(unittest.TestCase):
    def test_INV_PARENT_1_parent_developer_test_execution_is_refused_statically(self):
        self.assertEqual(ks.check(ROOT, ("CANDIDATE_ONLY_EXECUTION", "NO_DEVELOPER_ARTEFACT_AT_PARENT")), [])
        gate = ("from aisef2.quality.test_execution import UNITTEST, execute\n\n\ndef red_at(parent, tests, deps):\n"
                "    return execute(UNITTEST, parent, tests, deps)\n")
        hits = ks.violations("aisef2/control/gate.py", gate, ("NO_DEVELOPER_ARTEFACT_AT_PARENT",))
        self.assertTrue(hits and hits[0].startswith("NO_DEVELOPER_ARTEFACT_AT_PARENT aisef2/control/gate.py:4"), hits)
        v1 = "from aisef.control.tdd import tdd_subjects\n"
        hits = ks.violations("aisef2/control/gate.py", v1, ("NO_DEVELOPER_ARTEFACT_AT_PARENT",))
        self.assertEqual(len(hits), 1)
        self.assertIn("imports the frozen V1 kernel (aisef.control.tdd)", hits[0])
        quality = "def evaluate(runner, candidate, parent, tests, deps):\n    pass\n"
        self.assertTrue(ks.violations("aisef2/quality/vacuity.py", quality, ("CANDIDATE_ONLY_EXECUTION",)))
        self.assertEqual(ks.violations("aisef2/probe/x.py", quality, ("NO_DEVELOPER_ARTEFACT_AT_PARENT",)), [])  # no developer artefacts run here

    def test_INV_PARENT_1_the_apis_are_structurally_candidate_only(self):
        for fn in (te.execute, vc.evaluate, vc.neutralise):
            names = set(inspect.signature(fn).parameters)
            self.assertFalse({n for n in names if ks.PARENT_NAMES.search(n)}, fn.__name__)
        with self.assertRaises(TypeError):
            vc.evaluate(te.UNITTEST, "/candidate", "", te.DeveloperTests("S", ("tests/t.py",)), None, None, parent="/parent")
        self.assertEqual(names_test_artefact({"subject": {"kind": "python_callable", "locator": "tests/test_x.py:T.test"}}),
                         ["tests/test_x.py:T.test"])
        with tempfile.TemporaryDirectory(prefix="aisef2-inv-") as t:
            s = proof_spec(locator="tests/test_x.py")
            rec = run_probe(Fake(), s, RevisionRef(SHA, t), ENV)
        self.assertIsInstance(rec.result, oc.InvalidSpec)
        self.assertRegex(rec.result.detail, "invariant IX")
        for path in sorted((ROOT / "aisef2").rglob("*.py")):   # no aisef2 module imports the V1 kernel
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                self.assertFalse([n for n in names if n == "aisef" or n.startswith("aisef.")], path)
        self.assertFalse(list((ROOT / "aisef2").rglob("tdd*.py")))

    def test_the_only_counterfactual_is_candidate_side_vacuity(self):
        mech = next(m for m in REGISTRY[8].mechanisms if m.id == "IX.candidate-side-vacuity")
        self.assertIs(resolve(mech), vc.evaluate)
        text = (ROOT / "tests/v2/p5/test_vacuity.py").read_text(encoding="utf-8")
        self.assertIn("def test_invariant_IX_is_structural", text)


# ------------------------------------------------------------------------------------------------ operational

class MutationAuthority(unittest.TestCase):
    def test_INV_MUTATION_AUTHORITY_destructive_sites_of_the_invariant_code_are_ledgered(self):
        self.assertEqual(da.check(ROOT), [])
        for rel in ("aisef2/invariants/registry.py", "aisef2/invariants/evidence.py", "validation/v2/except_boundaries.py"):
            source = (ROOT / rel).read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, {"kill", "killpg", "rmtree", "remove", "unlink", "terminate", "send_signal"}, rel)


if __name__ == "__main__":
    unittest.main()
