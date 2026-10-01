"""WP-6.1 — the generated V1 proof-mode migration table: MIG-1..10 and the generator's failure modes, on the real V1
kernel file and on crafted roots. Every test here is self-contained (the mutation runner's tree copy holds `aisef/`
but no V1 evidence); the repository-level assertions are in test_migration_table_repo.py.

The load-bearing rule: SubjectAbsence is never inferred — from polarity, the mode's name, its transition, wording,
history or a default. It is proven twice: behaviourally (every derivation, under every definition and transition
variant, leaves it HUMAN_DECLARATION_REQUIRED unless an explicit typed declaration is given) and structurally (the
only assignment of it in `derive` calls `declared(...)` with the declaration as its only input, and `declared` reads
nothing else).
"""

import ast
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ObligationRole, Polarity, SubjectAbsence  # noqa: E402

_NAME = "aisef_v2_gen_migration_table"
if _NAME in sys.modules:
    gm = sys.modules[_NAME]
else:
    _s = importlib.util.spec_from_file_location(_NAME, ROOT / "validation" / "v2" / "gen_migration_table.py")
    gm = importlib.util.module_from_spec(_s)
    sys.modules[_NAME] = gm
    _s.loader.exec_module(gm)

MODES = ("CHANGE_REQUIRED", "PRESERVE_REQUIRED", "NEGATIVE_INVARIANT")
KERNEL = gm.read_v1(ROOT)
OBLIGATION_SRC = (ROOT / gm.V1_OBLIGATION).read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
NORMALIZE_STUB = ("def ac_proof(entries, story, n):\n"
                  "    return {e.split('=')[0]: e.split('=')[1].strip().upper() for e in entries}\n")
NORMALIZE_NO_FOLD = "def ac_proof(entries, story, n):\n    return {e.split('=')[0]: e.split('=')[1] for e in entries}\n"
DOC = ("What each criterion must SHOW (test kernel).\n\n"
       "    CHANGE_REQUIRED     parent PROVEN RED  -> candidate GREEN   this story contributes the behaviour\n"
       "    PRESERVE_REQUIRED   parent GREEN       -> candidate GREEN   this story must not break what it inherits\n"
       "    NEGATIVE_INVARIANT  parent GREEN       -> candidate GREEN   a prohibition that holds before and after\n")


def v1_source(transitions=None, doc=DOC, members=None, expected_line=None, mode_class=True):
    """A V1 obligation module: the Mode enum, EXPECTED and the docstring, each variable for the failure-mode cases."""
    transitions = dict(transitions if transitions is not None else
                       {"CHANGE_REQUIRED": "RED -> GREEN", "PRESERVE_REQUIRED": "GREEN -> GREEN",
                        "NEGATIVE_INVARIANT": "GREEN -> GREEN"})
    members = list(members if members is not None else transitions)
    body = ['"""' + doc + '"""', "from enum import Enum", ""]
    if mode_class:
        body += ["class Mode(str, Enum):"] + [f'    {m} = "{m}"' for m in members] + [""]
    if expected_line is None:
        expected_line = "EXPECTED = {" + ", ".join(f'Mode.{m}: "{t}"' for m, t in transitions.items()) + "}"
    if expected_line:
        body.append(expected_line)
    body += ['VERIFICATION_ONLY = "VERIFICATION_ONLY"', 'NORMAL = "NORMAL"', "STORY_TYPES = (NORMAL, VERIFICATION_ONLY)", ""]
    return "\n".join(body)


def fake_root(obligation=OBLIGATION_SRC, normalize=NORMALIZE_STUB, extra=None):
    """A throwaway repository root holding a V1 kernel module (and whatever `extra` maps path -> text); nothing in
    it is ever deleted or overwritten by a test — a variant is a new root."""
    d = tempfile.TemporaryDirectory()
    root = pathlib.Path(d.name)
    files = {gm.V1_OBLIGATION: obligation} if obligation is not None else {}
    if normalize is not None:
        files[gm.V1_NORMALIZE] = normalize
    files.update(extra or {})
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8", newline="\n")
    return d


def by_mode(rows):
    return {r["v1_mode"]: r for r in rows}


def kernel(**kw):
    with fake_root(v1_source(**kw)) as d:
        return gm.read_v1(pathlib.Path(d))


# ================================================================================================ the rows (MIG-1..4, 8)

class Rows(unittest.TestCase):
    def setUp(self):
        self.rows = by_mode(gm.derive(MODES, KERNEL))

    def _common(self, row, mode):
        self.assertEqual(row["source"], f"aisef/control/obligation.py::Mode.{mode}")
        self.assertEqual(row["subject_absence"], gm.HUMAN_DECLARATION_REQUIRED)
        self.assertNotIn(row["subject_absence"], {m.value for m in SubjectAbsence})
        self.assertEqual(row["subject_absence_source"], gm.NO_SOURCE)
        self.assertEqual(row["obligation_role_source"], gm.V1_TRANSITION)
        self.assertEqual(row["polarity_source"], gm.V1_DEFINITION)
        self.assertEqual((row["status"], row["reason"], row["missing"]),
                         (gm.UNMAPPED, gm.HUMAN_DECLARATION_REQUIRED, ["subject_absence"]))
        self.assertEqual(row["rationale_ref"], gm.RATIONALE_REF)
        self.assertEqual(row["transition"]["source"], "aisef/control/obligation.py::EXPECTED")
        self.assertEqual(row["definition"]["source"], f"aisef/control/obligation.py module docstring, the {mode} line")
        self.assertEqual(row["derivation"]["subject_absence"],
                         "V1 declared none; nothing here infers it (not from polarity, name, transition, wording, "
                         "history or a default)")

    def test_MIG_1_CHANGE_REQUIRED_maps_to_INTRODUCE_and_MUST_HOLD_and_never_to_a_SubjectAbsence(self):
        r = self.rows["CHANGE_REQUIRED"]
        self.assertEqual((r["obligation_role"], r["expected_parent"], r["polarity"]),
                         ("INTRODUCE", "UNSATISFIED_AT_PARENT", "MUST_HOLD"))
        self.assertEqual(r["transition"], {"parent": "RED", "candidate": "GREEN", "source": "aisef/control/obligation.py::EXPECTED"})
        self.assertEqual(r["definition"]["kind"], "BEHAVIOUR")
        self.assertEqual(r["definition"]["quote"], "this story contributes the behaviour")
        self.assertEqual(r["derivation"]["obligation_role"],
                         "EXPECTED[CHANGE_REQUIRED] = 'RED -> GREEN': parent RED -> UNSATISFIED_AT_PARENT; the role "
                         "whose EXPECTED_AT_PARENT is that (§11) -> INTRODUCE")
        self.assertEqual(r["derivation"]["polarity"],
                         "the kernel defines CHANGE_REQUIRED as 'this story contributes the behaviour' -> BEHAVIOUR -> "
                         "MUST_HOLD; V1 never verified a criterion's test against it")
        self._common(r, "CHANGE_REQUIRED")

    def test_MIG_2_PRESERVE_REQUIRED_maps_to_PRESERVE_and_MUST_HOLD_with_SubjectAbsence_separate(self):
        r = self.rows["PRESERVE_REQUIRED"]
        self.assertEqual((r["obligation_role"], r["expected_parent"], r["polarity"]),
                         ("PRESERVE", "SATISFIED_AT_PARENT", "MUST_HOLD"))
        self.assertEqual((r["transition"]["parent"], r["transition"]["candidate"]), ("GREEN", "GREEN"))
        self.assertEqual((r["definition"]["kind"], r["definition"]["quote"]),
                         ("BEHAVIOUR", "this story must not break what it inherits"))
        self._common(r, "PRESERVE_REQUIRED")

    def test_MIG_3_and_4_NEGATIVE_INVARIANT_is_PRESERVE_MUST_NOT_HOLD_and_implies_no_SubjectAbsence(self):
        r = self.rows["NEGATIVE_INVARIANT"]
        self.assertEqual((r["obligation_role"], r["expected_parent"], r["polarity"]),
                         ("PRESERVE", "SATISFIED_AT_PARENT", "MUST_NOT_HOLD"))
        self.assertEqual((r["definition"]["kind"], r["definition"]["quote"]),
                         ("PROHIBITION", "a prohibition that holds before and after"))
        self.assertNotEqual(r["subject_absence"], SubjectAbsence.ABSENCE_IS_DECIDABLE.value)   # MIG-3
        self.assertNotEqual(r["subject_absence"], SubjectAbsence.REQUIRES_SUBJECT.value)       # MIG-4
        self.assertEqual(r["derivation"]["polarity"],
                         "the kernel defines NEGATIVE_INVARIANT as 'a prohibition that holds before and after' -> "
                         "PROHIBITION -> MUST_NOT_HOLD; V1 never verified a criterion's test against it")
        self._common(r, "NEGATIVE_INVARIANT")

    def test_the_three_rows_are_the_whole_table_and_nothing_is_MAPPED_without_a_declaration(self):
        self.assertEqual(sorted(self.rows), sorted(MODES))
        self.assertTrue(all(r["status"] == gm.UNMAPPED for r in self.rows.values()))
        self.assertEqual({r["polarity"] for r in self.rows.values()}, {"MUST_HOLD", "MUST_NOT_HOLD"})

    def test_MIG_8_only_an_explicit_typed_declaration_maps_a_row(self):
        rows = by_mode(gm.derive(MODES, KERNEL, declarations={"NEGATIVE_INVARIANT": SubjectAbsence.ABSENCE_IS_DECIDABLE}))
        r = rows["NEGATIVE_INVARIANT"]
        self.assertEqual((r["subject_absence"], r["subject_absence_source"], r["status"], r["reason"], r["missing"]),
                         ("ABSENCE_IS_DECIDABLE", gm.HUMAN_DECLARATION, gm.MAPPED, None, []))
        self.assertEqual(r["derivation"]["subject_absence"], "from an explicit typed declaration")
        self.assertEqual((r["obligation_role"], r["polarity"]), ("PRESERVE", "MUST_NOT_HOLD"))   # unchanged by it
        for other in ("CHANGE_REQUIRED", "PRESERVE_REQUIRED"):
            self.assertEqual((rows[other]["status"], rows[other]["subject_absence"]),
                             (gm.UNMAPPED, gm.HUMAN_DECLARATION_REQUIRED))
        rows = by_mode(gm.derive(MODES, KERNEL, declarations={"CHANGE_REQUIRED": SubjectAbsence.REQUIRES_SUBJECT}))
        self.assertEqual((rows["CHANGE_REQUIRED"]["subject_absence"], rows["CHANGE_REQUIRED"]["status"]),
                         ("REQUIRES_SUBJECT", gm.MAPPED))
        # a declaration for a mode that is not in the input changes nothing
        rows = by_mode(gm.derive(MODES, KERNEL, declarations={"OTHER": SubjectAbsence.REQUIRES_SUBJECT}))
        self.assertTrue(all(r["status"] == gm.UNMAPPED for r in rows.values()))
        # a declaration that is not a SubjectAbsence member (a string, a bool) is refused, never coerced
        for bad in ("REQUIRES_SUBJECT", True, Polarity.MUST_NOT_HOLD):
            with self.assertRaisesRegex(gm.MigrationError, "a SubjectAbsence declaration is a SubjectAbsence member, not "):
                gm.derive(MODES, KERNEL, declarations={"CHANGE_REQUIRED": bad})

    def test_declared_reads_the_declaration_and_nothing_else(self):
        self.assertEqual(gm.declared(None), gm.HUMAN_DECLARATION_REQUIRED)
        for m in SubjectAbsence:
            self.assertIs(gm.declared(m), m)
        with self.assertRaisesRegex(gm.MigrationError, "^a SubjectAbsence declaration is a SubjectAbsence member, not 'x'$"):
            gm.declared("x")


class SubjectAbsenceNeverInferred(unittest.TestCase):
    """Behavioural: under every polarity, definition and transition variant the result is the same. Structural: the
    derivation of subject_absence has one input, the declaration."""

    def test_no_definition_or_transition_variant_moves_subject_absence(self):
        variants = [
            {m: gm.Definition(gm.Kind.PROHIBITION, gm.V1_DEFINITIONS[m].quote) for m in MODES},   # all prohibitions
            {m: gm.Definition(gm.Kind.BEHAVIOUR, gm.V1_DEFINITIONS[m].quote) for m in MODES},     # all behaviours
            gm.V1_DEFINITIONS,
        ]
        kernels = [KERNEL, kernel(transitions={"CHANGE_REQUIRED": "GREEN -> GREEN", "PRESERVE_REQUIRED": "RED -> GREEN",
                                               "NEGATIVE_INVARIANT": "RED -> GREEN"})]
        seen_polarities, seen_roles = set(), set()
        for k in kernels:
            for defs in variants:
                for r in gm.derive(MODES, k, defs):
                    seen_polarities.add(r["polarity"])
                    seen_roles.add(r["obligation_role"])
                    self.assertEqual(r["subject_absence"], gm.HUMAN_DECLARATION_REQUIRED, r)
                    self.assertEqual(r["status"], gm.UNMAPPED)
        self.assertEqual(seen_polarities, {"MUST_HOLD", "MUST_NOT_HOLD"})   # both polarities were exercised ...
        self.assertEqual(seen_roles, {"INTRODUCE", "PRESERVE"})              # ... and both roles

    def test_structurally_the_only_input_of_subject_absence_is_the_declaration(self):
        tree = ast.parse((ROOT / "validation" / "v2" / "gen_migration_table.py").read_text(encoding="utf-8"))
        fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        declared = fns["declared"]
        self.assertEqual([a.arg for a in declared.args.args], ["declaration"])
        names = {n.id for n in ast.walk(declared) if isinstance(n, ast.Name)}
        self.assertEqual(names - {"declaration", "isinstance", "SubjectAbsence", "HUMAN_DECLARATION_REQUIRED",
                                  "MigrationError", "str"}, set())   # `str` is in the return annotation
        assigns = [n for n in ast.walk(fns["derive"]) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "absence" for t in n.targets)]
        self.assertEqual(len(assigns), 1)
        call = assigns[0].value
        self.assertIsInstance(call, ast.Call)
        self.assertEqual(ast.unparse(call), "declared(declarations.get(mode))")
        # nothing else in derive writes subject_absence: every "subject_absence" value is `absence` itself, or the
        # prose derivation chosen on `isinstance(absence, Enum)` — never on polarity, mode, name or transition
        values = sorted(ast.unparse(v) for n in ast.walk(fns["derive"]) if isinstance(n, ast.Dict)
                        for k, v in zip(n.keys, n.values, strict=True) if isinstance(k, ast.Constant) and k.value == "subject_absence")
        self.assertEqual([v for v in values if not v.startswith("'")], ["_value(absence)", "absence"])
        prose = [v for v in values if v.startswith("'")]
        self.assertEqual(len(prose), 1)
        self.assertIn(" if isinstance(absence, Enum) else ", prose[0])
        for forbidden in ("polarity", "mode", "name", "transition", "definition", "sides", "kernel"):
            self.assertNotIn(forbidden + ")", prose[0])
            self.assertNotIn("(" + forbidden, prose[0])


# ========================================================================================== unknown modes (MIG-5)

class Unknown(unittest.TestCase):
    def test_MIG_5_an_unknown_mode_is_an_UNMAPPED_row_that_is_kept_and_defaults_nothing(self):
        rows = gm.derive(["NO_SUCH_MODE", *MODES], KERNEL)
        self.assertEqual([r["v1_mode"] for r in rows], sorted(["NO_SUCH_MODE", *MODES]))   # kept, never dropped
        r = by_mode(rows)["NO_SUCH_MODE"]
        self.assertEqual(r, {
            "v1_mode": "NO_SUCH_MODE", "source": None, "transition": None, "definition": None, "expected_parent": None,
            "obligation_role": None, "polarity": None, "subject_absence": None,
            "obligation_role_source": "NONE", "polarity_source": "NONE", "subject_absence_source": "NONE",
            "status": "UNMAPPED", "reason": "UNKNOWN_V1_MODE",
            "missing": ["obligation_role", "polarity", "subject_absence"],
            "derivation": {"unknown": "neither a Mode member of the V1 kernel nor an entry of the alias table"},
            "rationale_ref": gm.RATIONALE_REF})
        self.assertEqual(gm.problems({"rows": [r]}),
                         ["row NO_SUCH_MODE: unknown V1 mode — no mapping and no default; declare it or remove it from the input"])

    def test_a_member_the_kernel_declares_but_cannot_define_is_unknown_too(self):
        k = kernel(members=[*MODES, "FOO"])   # in Mode, absent from EXPECTED and from the definitions
        r = by_mode(gm.derive(["FOO"], k))["FOO"]
        self.assertEqual((r["status"], r["reason"], r["obligation_role"]), (gm.UNMAPPED, gm.UNKNOWN_V1_MODE, None))
        self.assertEqual(r["derivation"], {"unknown": "FOO is a Mode member without a transition in EXPECTED, without a "
                                                      "cited definition, or its citation is not on the kernel's definition line"})
        k = kernel(transitions={**{m: KERNEL.transitions[m] for m in MODES}, "FOO": "RED -> GREEN"})   # transition, no definition
        self.assertEqual(by_mode(gm.derive(["FOO"], k))["FOO"]["reason"], gm.UNKNOWN_V1_MODE)
        defs = {**gm.V1_DEFINITIONS, "FOO": gm.Definition(gm.Kind.BEHAVIOUR, "x")}   # definition, no citation line
        self.assertEqual(by_mode(gm.derive(["FOO"], k, defs))["FOO"]["reason"], gm.UNKNOWN_V1_MODE)
        # a definition whose quote is not on the kernel's line for that mode is refused, not trusted
        defs = {**gm.V1_DEFINITIONS, "NEGATIVE_INVARIANT": gm.Definition(gm.Kind.PROHIBITION, "some other words")}
        self.assertEqual(by_mode(gm.derive(MODES, KERNEL, defs))["NEGATIVE_INVARIANT"]["reason"], gm.UNKNOWN_V1_MODE)
        # a known member without a definition entry at all
        self.assertEqual(by_mode(gm.derive(MODES, KERNEL, {m: gm.V1_DEFINITIONS[m] for m in MODES[:2]}))
                         ["NEGATIVE_INVARIANT"]["reason"], gm.UNKNOWN_V1_MODE)

    def test_a_transition_that_is_not_a_V1_transition_is_refused(self):
        for bad in ("RED -> RED", "GREEN -> RED", "PURPLE -> GREEN", "RED->GREEN", "RED -> GREEN "):
            k = kernel(transitions={"CHANGE_REQUIRED": bad, "PRESERVE_REQUIRED": "GREEN -> GREEN",
                                    "NEGATIVE_INVARIANT": "GREEN -> GREEN"})
            r = by_mode(gm.derive(MODES, k))["CHANGE_REQUIRED"]
            self.assertEqual(r["reason"], gm.UNKNOWN_V1_MODE, bad)
            self.assertEqual(r["derivation"], {"unknown": f"CHANGE_REQUIRED: EXPECTED transition {bad!r} is not a V1 "
                                                          "transition (<RED|GREEN> -> GREEN)"})
        k = kernel(transitions={"CHANGE_REQUIRED": "GREEN -> GREEN", "PRESERVE_REQUIRED": "RED -> GREEN",
                                "NEGATIVE_INVARIANT": "GREEN -> GREEN"})
        rows = by_mode(gm.derive(MODES, k))
        self.assertEqual((rows["CHANGE_REQUIRED"]["obligation_role"], rows["PRESERVE_REQUIRED"]["obligation_role"]),
                         ("PRESERVE", "INTRODUCE"))   # the role follows the transition, not the mode's name

    def test_generation_and_write_refuse_a_kernel_with_an_unknown_mode(self):
        with fake_root(v1_source(members=[*MODES, "FOO"])) as d:
            root = pathlib.Path(d)
            table = gm.generate(root)
            self.assertEqual([r["v1_mode"] for r in table["rows"]], ["CHANGE_REQUIRED", "FOO", "NEGATIVE_INVARIANT", "PRESERVE_REQUIRED"])
            self.assertIn("row FOO: unknown V1 mode — no mapping and no default; declare it or remove it from the input",
                          gm.problems(table))
            self.assertEqual(gm.write(root), gm.problems(table))
            self.assertFalse((root / gm.TABLE_REL).exists())
            self.assertFalse((root / gm.DOC_REL).exists())
            self.assertIn("row FOO: unknown V1 mode — no mapping and no default; declare it or remove it from the input",
                          gm.check(root))


# ================================================================================================ aliases (MIG-10)

class Aliases(unittest.TestCase):
    def test_the_committed_alias_table_is_explicit_and_empty(self):
        self.assertEqual(gm.ALIASES, {})

    def test_MIG_10_resolution_is_by_exact_key_only(self):
        for m in MODES:
            self.assertEqual(gm.resolve(m, KERNEL.members), m)
        for near in ("change_required", "Change_Required", " CHANGE_REQUIRED", "CHANGE_REQUIRED ", "CHANGE-REQUIRED",
                     "CHANGE_REQUIRE", "CHANGE_REQUIREDX", "CHANGE REQUIRED", "", "Mode.CHANGE_REQUIRED"):
            self.assertIsNone(gm.resolve(near, KERNEL.members), near)
            self.assertEqual(by_mode(gm.derive([near], KERNEL))[near]["reason"], gm.UNKNOWN_V1_MODE, near)

    def test_an_alias_resolves_only_through_the_table_and_only_to_a_mode(self):
        aliases = {"CHANGE_REQ": "CHANGE_REQUIRED"}
        self.assertEqual(gm.resolve("CHANGE_REQ", KERNEL.members, aliases), "CHANGE_REQUIRED")
        self.assertIsNone(gm.resolve("change_req", KERNEL.members, aliases))
        self.assertIsNone(gm.resolve("CHANGE_REQ", KERNEL.members))   # not in the (empty) default table
        r = by_mode(gm.derive(["CHANGE_REQ"], KERNEL, aliases=aliases))["CHANGE_REQ"]
        self.assertEqual((r["obligation_role"], r["polarity"], r["status"]), ("INTRODUCE", "MUST_HOLD", gm.UNMAPPED))
        self.assertEqual(r["source"], "aisef/control/obligation.py::Mode.CHANGE_REQUIRED (alias 'CHANGE_REQ')")
        self.assertTrue(r["derivation"]["obligation_role"].startswith("EXPECTED[CHANGE_REQUIRED] = 'RED -> GREEN'"))
        with self.assertRaisesRegex(gm.MigrationError, "^alias 'OLD' -> 'GONE': the target is not a V1 mode$"):
            gm.resolve("OLD", KERNEL.members, {"OLD": "GONE"})
        with self.assertRaisesRegex(gm.MigrationError, "the target is not a V1 mode"):
            gm.derive(["OLD"], KERNEL, aliases={"OLD": "GONE"})


# ============================================================================================ determinism (MIG-9)

class Determinism(unittest.TestCase):
    def test_MIG_9_row_order_is_canonical_whatever_the_input_order(self):
        names = ["Z_MODE", *MODES, "A_MODE", "M_MODE", "NO_SUCH_MODE", "B_MODE"]
        expected = gm.derive(names, KERNEL)
        self.assertEqual([r["v1_mode"] for r in expected], sorted(names))
        for order in (list(reversed(names)), names[3:] + names[:3], names + names):
            self.assertEqual(gm.derive(order, KERNEL), expected)

    def test_generation_is_byte_identical_whatever_the_discovery_order(self):
        with fake_root(extra={"docs/a.md": "CHANGE_REQUIRED and WEIRD", "docs/b.md": "PRESERVE_REQUIRED",
                              "closure-evidence/hardening/x.json": json.dumps({"record": "TDD PROOF POLICY V2",
                                                                               "rows": [{"proof_mode": "CHANGE_REQUIRED"}]}),
                              "closure-evidence/hardening/y.json": json.dumps({"record": "OLD POLICY marker"})}) as d:
            root = pathlib.Path(d)
            first = gm.generate(root)
            files = list(gm._files(root))
            enums = gm._enums(root)
            with mock.patch.object(gm, "_files", lambda r, dirs=gm.SCAN_DIRS, exclude=gm.V2_DIRS: iter(list(reversed(files)))
                                   if tuple(dirs) == gm.SCAN_DIRS else iter([])), \
                    mock.patch.object(gm, "_enums", lambda r: list(reversed(enums))):
                second = gm.generate(root)
            self.assertEqual(gm.render_json(first), gm.render_json(second))
            self.assertEqual(gm.render_doc(first), gm.render_doc(second))
            self.assertEqual(gm.write(root), [])
            a = ((root / gm.TABLE_REL).read_bytes(), (root / gm.DOC_REL).read_bytes())
            self.assertEqual(gm.write(root), [])
            self.assertEqual(a, ((root / gm.TABLE_REL).read_bytes(), (root / gm.DOC_REL).read_bytes()))
            self.assertNotIn(b"\r\n", a[0] + a[1])


# ===================================================================================== --check (MIG-6, MIG-7)

class Check(unittest.TestCase):
    def test_a_generated_root_passes_check_and_a_missing_output_fails_it(self):
        with fake_root() as d:
            root = pathlib.Path(d)
            self.assertEqual(gm.check(root), [f"{gm.TABLE_REL} is missing: run the generator",
                                              f"{gm.DOC_REL} is missing: run the generator"])
            self.assertEqual(gm.write(root), [])
            self.assertEqual(gm.check(root), [])
            with fake_root(extra={gm.TABLE_REL: (root / gm.TABLE_REL).read_text(encoding="utf-8")}) as d2:
                self.assertEqual(gm.check(pathlib.Path(d2)), [f"{gm.DOC_REL} is missing: run the generator"])

    def test_MIG_6_a_hand_edit_of_the_document_fails_check(self):
        with fake_root() as d:
            root = pathlib.Path(d)
            gm.write(root)
            doc = root / gm.DOC_REL
            text = doc.read_text(encoding="utf-8")
            anchor = "| PRESERVE | SATISFIED_AT_PARENT | MUST_NOT_HOLD | HUMAN_DECLARATION_REQUIRED |"
            self.assertEqual(text.count(anchor), 1)
            doc.write_text(text.replace(anchor, anchor.replace("HUMAN_DECLARATION_REQUIRED", "ABSENCE_IS_DECIDABLE")),
                           encoding="utf-8")
            self.assertEqual(gm.check(root), [f"{gm.DOC_REL} drifted from its generator: hand-edited or stale"])
            doc.write_text(text + "\n", encoding="utf-8")   # even a trailing newline
            self.assertEqual(gm.check(root), [f"{gm.DOC_REL} drifted from its generator: hand-edited or stale"])

    def test_MIG_7_a_hand_edit_of_the_evidence_json_fails_check_twice_over(self):
        with fake_root() as d:
            root = pathlib.Path(d)
            gm.write(root)
            path = root / gm.TABLE_REL
            table = json.loads(path.read_text(encoding="utf-8"))
            row = by_mode(table["rows"])["CHANGE_REQUIRED"]
            row["subject_absence"] = "REQUIRES_SUBJECT"          # declared by hand, with no source
            path.write_text(json.dumps(table, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            found = gm.check(root)
            self.assertIn(f"{gm.TABLE_REL} drifted from its generator: hand-edited or stale", found)
            self.assertIn("committed row CHANGE_REQUIRED: subject_absence 'REQUIRES_SUBJECT' was not declared: inferred or defaulted", found)
            self.assertIn("committed row CHANGE_REQUIRED: subject_absence = 'REQUIRES_SUBJECT' has no typed source: a silently defaulted value", found)
            row["status"] = "MAPPED"
            row["subject_absence_source"] = "HUMAN_DECLARATION"   # forging the source still drifts
            path.write_text(json.dumps(table, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            found = gm.check(root)
            self.assertEqual(found, [f"{gm.TABLE_REL} drifted from its generator: hand-edited or stale",
                                     "committed row CHANGE_REQUIRED: 'missing' ['subject_absence'] does not match the row's own fields []"])
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(gm.check(root), [f"{gm.TABLE_REL} drifted from its generator: hand-edited or stale",
                                              f"{gm.TABLE_REL} is not JSON"])

    def test_check_reports_a_kernel_it_cannot_read(self):
        with fake_root(v1_source(mode_class=False)) as d:
            self.assertEqual(gm.check(pathlib.Path(d)), ["generation refused: aisef/control/obligation.py has no Mode enum"])

    def test_compare_names_each_output(self):
        table = gm.generate(ROOT)
        j, m = gm.render_json(table), gm.render_doc(table)
        self.assertEqual(gm.compare(table, j, m), [])
        self.assertEqual(gm.compare(table, None, None), [f"{gm.TABLE_REL} is missing: run the generator",
                                                          f"{gm.DOC_REL} is missing: run the generator"])
        self.assertEqual(gm.compare(table, j + " ", m), [f"{gm.TABLE_REL} drifted from its generator: hand-edited or stale"])
        self.assertEqual(gm.compare(table, j, m.lower()), [f"{gm.DOC_REL} drifted from its generator: hand-edited or stale"])

    def test_write_writes_both_outputs_with_lf_and_refuses_on_problems(self):
        with fake_root(extra={"docs/x.md": "WEIRD_REQUIRED"}) as d:   # an unclassifiable token: a problem
            root = pathlib.Path(d)
            self.assertEqual(gm.write(root), ["inventory: token 'WEIRD_REQUIRED' (1 files) matches no classification rule"])
            self.assertFalse((root / gm.TABLE_REL).exists())
        with fake_root() as d:
            root = pathlib.Path(d)
            self.assertEqual(gm.write(root), [])
            self.assertTrue((root / gm.TABLE_REL).exists() and (root / gm.DOC_REL).exists())
            self.assertEqual(json.loads((root / gm.TABLE_REL).read_text(encoding="utf-8"))["record"], "AISEF V2 — P6 MIGRATION TABLE")


class Problems(unittest.TestCase):
    """`problems` reads the typed fields of a table — fresh or committed — and names every way a row is unacceptable."""

    def good(self, **changes):
        r = dict(by_mode(gm.derive(MODES, KERNEL, declarations={"CHANGE_REQUIRED": SubjectAbsence.REQUIRES_SUBJECT}))
                 ["CHANGE_REQUIRED"])
        r.update(changes)
        return r

    def test_a_correct_table_has_no_problems_mapped_or_not(self):
        self.assertEqual(gm.problems({"rows": gm.derive(MODES, KERNEL)}), [])
        self.assertEqual(gm.problems({"rows": [self.good()]}), [])
        self.assertEqual(gm.problems({"rows": [self.good()], "inventory_problems": ["x"]}), ["x"])

    def test_no_rows(self):
        for table in ({}, {"rows": []}, {"rows": None}, {"rows": "x"}):
            self.assertEqual(gm.problems(table), ["the table has no rows"])

    def test_status_vocabulary(self):
        self.assertEqual(gm.problems({"rows": [self.good(status="PARTIAL")]}),
                         ["row CHANGE_REQUIRED: status 'PARTIAL' is neither MAPPED nor UNMAPPED"])

    def test_a_value_with_no_typed_source_is_a_defaulted_row(self):
        self.assertEqual(gm.problems({"rows": [self.good(obligation_role_source="NONE")]}),
                         ["row CHANGE_REQUIRED: obligation_role = 'INTRODUCE' has no typed source: a silently defaulted value"])
        self.assertEqual(gm.problems({"rows": [self.good(polarity_source=None)]}),
                         ["row CHANGE_REQUIRED: polarity = 'MUST_HOLD' has no typed source: a silently defaulted value"])
        self.assertEqual(gm.problems({"rows": [self.good(subject_absence_source="V1_DEFINITION")]}),
                         ["row CHANGE_REQUIRED: subject_absence 'REQUIRES_SUBJECT' was not declared: inferred or defaulted"])

    def test_a_value_outside_the_V2_vocabulary(self):
        self.assertEqual(gm.problems({"rows": [self.good(polarity="POSITIVE", missing=["polarity"], status="UNMAPPED")]}),
                         ["row CHANGE_REQUIRED: polarity = 'POSITIVE' is not a V2 value"])
        self.assertEqual(gm.problems({"rows": [self.good(obligation_role="CHANGE", missing=["obligation_role"], status="UNMAPPED")]}),
                         ["row CHANGE_REQUIRED: obligation_role = 'CHANGE' is not a V2 value"])
        self.assertEqual(gm.problems({"rows": [self.good(subject_absence="UNKNOWN", missing=["subject_absence"], status="UNMAPPED",
                                                         subject_absence_source="NONE")]}),
                         ["row CHANGE_REQUIRED: subject_absence = 'UNKNOWN' is not a V2 value"])

    def test_MAPPED_needs_every_dimension_and_UNMAPPED_needs_a_gap(self):
        self.assertEqual(gm.problems({"rows": [self.good(subject_absence=gm.HUMAN_DECLARATION_REQUIRED,
                                                         subject_absence_source="NONE", missing=["subject_absence"])]}),
                         ["row CHANGE_REQUIRED: MAPPED while ['subject_absence'] still need a declaration"])
        self.assertEqual(gm.problems({"rows": [self.good(status="UNMAPPED")]}),
                         ["row CHANGE_REQUIRED: UNMAPPED although every dimension holds a V2 value"])
        self.assertEqual(gm.problems({"rows": [self.good(missing=["polarity"])]}),
                         ["row CHANGE_REQUIRED: 'missing' ['polarity'] does not match the row's own fields []"])
        two = self.good(status="UNMAPPED", polarity=gm.HUMAN_DECLARATION_REQUIRED, polarity_source="NONE",
                        subject_absence=gm.HUMAN_DECLARATION_REQUIRED, subject_absence_source="NONE",
                        missing=["subject_absence", "polarity"])   # listed in another order than the row's fields
        self.assertEqual(gm.problems({"rows": [two]}), [])
        self.assertEqual(gm.problems({"rows": [self.good(missing=None, subject_absence=None, subject_absence_source="NONE")]}),
                         ["row CHANGE_REQUIRED: MAPPED while ['subject_absence'] still need a declaration",
                          "row CHANGE_REQUIRED: 'missing' None does not match the row's own fields ['subject_absence']"])


# ================================================================================================= the V1 reader

class ReadV1(unittest.TestCase):
    def test_the_real_kernel(self):
        self.assertIsInstance(KERNEL.members, tuple)
        self.assertEqual(KERNEL.members, MODES)
        self.assertEqual(KERNEL.transitions, {"CHANGE_REQUIRED": "RED -> GREEN", "PRESERVE_REQUIRED": "GREEN -> GREEN",
                                              "NEGATIVE_INVARIANT": "GREEN -> GREEN"})
        self.assertIsInstance(KERNEL.doc_lines, tuple)
        import hashlib
        self.assertEqual(KERNEL.sha256, hashlib.sha256(OBLIGATION_SRC.encode("utf-8")).hexdigest())
        self.assertTrue(any(ln.strip().startswith("NEGATIVE_INVARIANT ") for ln in KERNEL.doc_lines))
        self.assertEqual(gm.read_v1(ROOT), KERNEL)

    def test_crlf_does_not_change_the_identity(self):
        with fake_root() as d:
            root = pathlib.Path(d)
            (root / gm.V1_OBLIGATION).write_bytes(OBLIGATION_SRC.replace("\n", "\r\n").encode("utf-8"))
            self.assertEqual(gm.read_v1(root), KERNEL)

    def test_every_way_the_kernel_is_unreadable_is_named(self):
        cases = [
            (None, "aisef/control/obligation.py is missing: no V1 kernel to read"),
            (v1_source(mode_class=False), "aisef/control/obligation.py has no Mode enum"),
            (v1_source(expected_line=""), "aisef/control/obligation.py has no EXPECTED transition table"),
            (v1_source(expected_line="EXPECTED = ['RED -> GREEN']"), "aisef/control/obligation.py has no EXPECTED transition table"),
            (v1_source(expected_line='EXPECTED = {"CHANGE_REQUIRED": "RED -> GREEN"}'),
             "aisef/control/obligation.py: EXPECTED is not keyed by Mode members with string transitions"),
            (v1_source(expected_line='EXPECTED = {Mode.CHANGE_REQUIRED: 1}'),
             "aisef/control/obligation.py: EXPECTED is not keyed by Mode members with string transitions"),
            (v1_source(expected_line='EXPECTED = {Other.CHANGE_REQUIRED: "RED -> GREEN"}'),
             "aisef/control/obligation.py: EXPECTED is not keyed by Mode members with string transitions"),
        ]
        for src, message in cases:
            with fake_root(src) as d:
                root = pathlib.Path(d)
                with self.assertRaisesRegex(gm.MigrationError, "^" + message.replace("(", r"\(").replace(")", r"\)") + "$"):
                    gm.read_v1(root)

    def test_members_come_from_the_enum_in_declaration_order_and_only_constant_members(self):
        src = v1_source(members=["PRESERVE_REQUIRED", "CHANGE_REQUIRED"]).replace(
            '    CHANGE_REQUIRED = "CHANGE_REQUIRED"', '    CHANGE_REQUIRED = "CHANGE_REQUIRED"\n    helper = staticmethod(len)')
        with fake_root(src) as d:
            k = gm.read_v1(pathlib.Path(d))
        self.assertEqual(k.members, ("PRESERVE_REQUIRED", "CHANGE_REQUIRED"))
        self.assertEqual(k.transitions, {"CHANGE_REQUIRED": "RED -> GREEN", "PRESERVE_REQUIRED": "GREEN -> GREEN",
                                         "NEGATIVE_INVARIANT": "GREEN -> GREEN"})   # EXPECTED read as written
        self.assertEqual(k.doc_lines[0], "What each criterion must SHOW (test kernel).")

    def test_cited_requires_exactly_one_definition_line_carrying_the_quote(self):
        self.assertTrue(gm.cited(KERNEL, "NEGATIVE_INVARIANT", "a prohibition that holds before and after"))
        self.assertFalse(gm.cited(KERNEL, "NEGATIVE_INVARIANT", "a behaviour"))
        self.assertFalse(gm.cited(KERNEL, "FOO", "a prohibition"))
        twice = gm.V1Kernel(KERNEL.members, KERNEL.transitions, KERNEL.doc_lines + KERNEL.doc_lines, KERNEL.sha256)
        self.assertFalse(gm.cited(twice, "NEGATIVE_INVARIANT", "a prohibition that holds before and after"))
        prefixed = gm.V1Kernel(KERNEL.members, KERNEL.transitions, ("NEGATIVE_INVARIANTS a prohibition that holds before and after",),
                               KERNEL.sha256)
        self.assertFalse(gm.cited(prefixed, "NEGATIVE_INVARIANT", "a prohibition that holds before and after"))


# ============================================================================================== losses and gaps

class Losses(unittest.TestCase):
    def test_the_V2_pairs_no_V1_mode_produces(self):
        rows = gm.derive(MODES, KERNEL)
        self.assertEqual(gm.without_v1_source(rows), [
            {"obligation_role": "INTRODUCE", "polarity": "MUST_NOT_HOLD", "loss": "V1_COULD_NOT_INTRODUCE_A_PROHIBITION"},
            {"obligation_role": "VERIFY", "polarity": "MUST_HOLD", "loss": "V1_HAS_NO_UNCONSTRAINED_PARENT"},
            {"obligation_role": "VERIFY", "polarity": "MUST_NOT_HOLD", "loss": "V1_HAS_NO_UNCONSTRAINED_PARENT"}])
        self.assertEqual(len(gm.without_v1_source([])), 6)
        self.assertEqual({(p["obligation_role"], p["polarity"]) for p in gm.without_v1_source(rows[:1])},
                         {(r.value, p.value) for r in ObligationRole for p in Polarity} - {("INTRODUCE", "MUST_HOLD")})

    def test_loss_codes_over_every_pair(self):
        self.assertEqual({(r.value, p.value): gm._loss_code(r, p) for r in ObligationRole for p in Polarity}, {
            ("INTRODUCE", "MUST_HOLD"): "V1_NO_SOURCE", ("INTRODUCE", "MUST_NOT_HOLD"): "V1_COULD_NOT_INTRODUCE_A_PROHIBITION",
            ("PRESERVE", "MUST_HOLD"): "V1_NO_SOURCE", ("PRESERVE", "MUST_NOT_HOLD"): "V1_NO_SOURCE",
            ("VERIFY", "MUST_HOLD"): "V1_HAS_NO_UNCONSTRAINED_PARENT", ("VERIFY", "MUST_NOT_HOLD"): "V1_HAS_NO_UNCONSTRAINED_PARENT"})

    def test_the_loss_report_names_what_V1_did_not_carry(self):
        rows = gm.derive(["NO_SUCH_MODE", *MODES], KERNEL)
        report = gm.loss_report(rows, gm.without_v1_source(rows))
        known = ["CHANGE_REQUIRED", "NEGATIVE_INVARIANT", "PRESERVE_REQUIRED"]
        self.assertEqual([(e["code"], e["dimension"], e["affects"]) for e in report], [
            ("V1_NO_SUBJECT_ABSENCE_DECLARATION", "subject_absence", known),
            ("V1_POLARITY_UNVERIFIED", "polarity", known),
            ("V1_COULD_NOT_INTRODUCE_A_PROHIBITION", "obligation_role+polarity", ["INTRODUCE+MUST_NOT_HOLD"]),
            ("V1_HAS_NO_UNCONSTRAINED_PARENT", "obligation_role+polarity", ["VERIFY+MUST_HOLD", "VERIFY+MUST_NOT_HOLD"])])
        for e in report:
            self.assertEqual(e["statement"], gm.LOSS_STATEMENTS[e["code"]])
        self.assertEqual(gm.loss_report([], [])[0]["affects"], [])
        one = gm.without_v1_source(gm.derive(MODES, KERNEL))[:1]
        self.assertEqual([e["code"] for e in gm.loss_report(rows, one)][2:], ["V1_COULD_NOT_INTRODUCE_A_PROHIBITION"])


# ==================================================================================================== inventory

EVIDENCE = {"record": "TDD PROOF POLICY V2", "rows": [
    {"proof_mode": "CHANGE_REQUIRED"}, {"proof_mode": "CHANGE_REQUIRED"}, {"proof_mode": "NO_SUCH_MODE"},
    {"expected_transition": "RED -> GREEN"}, {"mode": "auto"}, {"mode": "PRESERVE_REQUIRED"},
    {"nested": {"deeper": [{"proof_mode": "NEGATIVE_INVARIANT"}]}}]}


class Inventory(unittest.TestCase):
    def entries(self, extra=None, normalize=NORMALIZE_STUB, obligation=OBLIGATION_SRC):
        with fake_root(obligation, normalize, extra) as d:
            root = pathlib.Path(d)
            return gm.inventory(root, gm.read_v1(root))

    def find(self, entries, **match):
        found = [e for e in entries if all(e.get(k) == v for k, v in match.items())]
        self.assertEqual(len(found), 1, (match, found))
        return found[0]

    def test_the_kernel_module_alone(self):
        entries, problems = self.entries()
        self.assertEqual(problems, [])
        self.assertEqual(self.find(entries, kind="enum"), {
            "kind": "enum", "where": "aisef/control/obligation.py::Mode", "members": list(MODES),
            "classification": "ACTIVE_V1_MODE", "reason": "the V1 kernel's proof-mode enum: the migration input"})
        self.assertEqual(self.find(entries, kind="constant", where="aisef/control/obligation.py::EXPECTED"), {
            "kind": "constant", "where": "aisef/control/obligation.py::EXPECTED", "carries": list(MODES),
            "classification": "ACTIVE_V1_MODE", "reason": "a kernel table keyed by Mode members: the transition input"})
        self.assertEqual(self.find(entries, kind="constant", where="aisef/control/obligation.py::STORY_TYPES")["reason"],
                         "a constant of the kernel's obligation module that names no Mode member (story types, owner routing)")
        self.assertEqual(self.find(entries, kind="constant", where="aisef/control/obligation.py::OWNER_OF")["classification"],
                         "NOT_A_PROOF_MODE")
        self.assertEqual(self.find(entries, kind="grammar"), {
            "kind": "grammar", "where": "aisef/control/normalize.py::ac_proof", "classification": "NOT_A_PROOF_MODE",
            "reason": "V1's plan parser folds the mode token to upper case before the kernel; a case-folded spelling is "
                      "neither a mode value nor an alias of this table"})
        for m in MODES:
            e = self.find(entries, kind="token", token=m)
            self.assertEqual(e["classification"], "ACTIVE_V1_MODE")
            self.assertEqual(e["carried_by"], [{"path": "aisef/control/obligation.py", "kind": "code"}])
        order = [(e["classification"], gm._ident(e)) for e in entries]
        self.assertEqual(order, sorted(order))   # by classification, then kind and identifier — not by discovery
        self.assertEqual(order[:3], [("ACTIVE_V1_MODE", "constant aisef/control/obligation.py::EXPECTED"),
                                     ("ACTIVE_V1_MODE", "enum aisef/control/obligation.py::Mode"),
                                     ("ACTIVE_V1_MODE", "token CHANGE_REQUIRED")])
        self.assertTrue(all(e["classification"] in gm.CLASSIFICATIONS for e in entries))

    def test_enums_named_like_a_mode_and_enums_carrying_a_mode(self):
        entries, problems = self.entries(extra={
            "aisef/harness/caps.py": "from enum import Enum\nclass Mode(str, Enum):\n    AUTO = 'auto'\n    OFF = 'off'\n",
            "aisef/x.py": "from enum import Enum\nclass Legacy(Enum):\n    A = 'CHANGE_REQUIRED'\n",
            "aisef/y.py": "from enum import Enum\nclass Plain(Enum):\n    A = 'a'\n"})
        self.assertEqual(problems, [])
        self.assertEqual(self.find(entries, where="aisef/harness/caps.py::Mode"), {
            "kind": "enum", "where": "aisef/harness/caps.py::Mode", "members": ["auto", "off"], "classification": "NOT_A_PROOF_MODE",
            "reason": "an enum named like a mode with no proof-mode member (name collision)"})
        self.assertEqual(self.find(entries, where="aisef/x.py::Legacy")["classification"], "ACTIVE_V1_MODE")
        self.assertEqual([e for e in entries if e.get("where") == "aisef/y.py::Plain"], [])

    def test_tokens_are_classified_by_their_defining_enum_or_fail_closed(self):
        entries, problems = self.entries(extra={
            "aisef/control/outcome.py": "from enum import Enum\nclass StageOutcome(str, Enum):\n    HUMAN_REQUIRED = 'HUMAN_REQUIRED'\n",
            "docs/a.md": "HUMAN_REQUIRED and CHANGE_REQUIRED", "tests/t.py": "HUMAN_REQUIRED",
            "docs/b.md": "WEIRD_REQUIRED and ODD_INVARIANT", "docs/c.md": "WEIRD_REQUIRED",
            "tests/v2/z.py": "IGNORED_REQUIRED", "closure-evidence/v2/z.json": "{}", "aisef2/k.py": "x = 1"})
        self.assertEqual(problems, ["inventory: token 'ODD_INVARIANT' (1 files) matches no classification rule",
                                    "inventory: token 'WEIRD_REQUIRED' (2 files) matches no classification rule"])
        self.assertEqual(self.find(entries, token="HUMAN_REQUIRED"), {
            "kind": "token", "token": "HUMAN_REQUIRED", "where": "aisef/control/outcome.py::StageOutcome",
            "classification": "NOT_A_PROOF_MODE", "reason": "a member of a V1 enum that is not the proof-mode enum", "files": 3})
        self.assertEqual(self.find(entries, token="CHANGE_REQUIRED")["carried_by"],
                         [{"path": "aisef/control/obligation.py", "kind": "code"}, {"path": "docs/a.md", "kind": "doc"}])
        self.assertEqual([e for e in entries if e.get("token") == "IGNORED_REQUIRED"], [])

    def test_serialized_evidence_values_and_policy_records(self):
        entries, problems = self.entries(extra={
            "closure-evidence/hardening/a.json": json.dumps(EVIDENCE),
            "closure-evidence/hardening/b.json": json.dumps({"record": "W1 / TDD_POLICY_V1 — historical marker", "rule": []}),
            "closure-evidence/hardening/c.json": json.dumps({"record": "no policy here", "proof_mode": "CHANGE_REQUIRED"}),
            "closure-evidence/hardening/d.json": json.dumps({"expected_transition": "BLUE -> GREEN"}),
            "closure-evidence/hardening/e.json": "{broken proof_mode",
            "closure-evidence/hardening/f.txt": "proof_mode: CHANGE_REQUIRED",
            "validation/targets.json": json.dumps({"rows": [{"proof_mode": "NO_SUCH_MODE"}]}),
            "docs/notes.json": "not json at all"})
        self.assertEqual(problems, ["inventory: closure-evidence/hardening/e.json is not JSON",
                                    "inventory: docs/notes.json is not JSON",
                                    "inventory: evidence value expected_transition='BLUE -> GREEN' matches no classification rule"])
        self.assertEqual(self.find(entries, kind="evidence_value", key="proof_mode", value="CHANGE_REQUIRED"), {
            "kind": "evidence_value", "key": "proof_mode", "value": "CHANGE_REQUIRED", "occurrences": 3,
            "classification": "ACTIVE_V1_MODE", "reason": "a serialized V1 proof mode"})
        self.assertEqual(self.find(entries, key="proof_mode", value="NEGATIVE_INVARIANT")["occurrences"], 1)
        self.assertEqual(self.find(entries, key="proof_mode", value="NO_SUCH_MODE"), {
            "kind": "evidence_value", "key": "proof_mode", "value": "NO_SUCH_MODE", "occurrences": 2, "classification": "UNMAPPED",
            "reason": "a proof_mode value the V1 kernel does not know: V1 refused it (PLAN_METADATA_MISSING); nothing to migrate"})
        self.assertEqual(self.find(entries, key="expected_transition", value="RED -> GREEN"), {
            "kind": "evidence_value", "key": "expected_transition", "value": "RED -> GREEN", "occurrences": 1,
            "classification": "NOT_A_PROOF_MODE", "reason": "derived from the mode by EXPECTED; not an input"})
        self.assertEqual(self.find(entries, key="mode", value="auto"), {
            "kind": "evidence_value", "key": "mode", "value": "auto", "occurrences": 1, "classification": "NOT_A_PROOF_MODE",
            "reason": "a different 'mode' vocabulary (not a proof mode)"})
        self.assertEqual(self.find(entries, key="mode", value="PRESERVE_REQUIRED")["classification"], "ACTIVE_V1_MODE")
        self.assertEqual(self.find(entries, kind="policy_record", where="closure-evidence/hardening/a.json"), {
            "kind": "policy_record", "where": "closure-evidence/hardening/a.json", "record": "TDD PROOF POLICY V2",
            "classification": "ACTIVE_V1_MODE", "reason": "a policy record naming the active modes"})
        self.assertEqual(self.find(entries, kind="policy_record", where="closure-evidence/hardening/b.json"), {
            "kind": "policy_record", "where": "closure-evidence/hardening/b.json", "record": "W1 / TDD_POLICY_V1 — historical marker",
            "classification": "HISTORICAL_ONLY",
            "reason": "a policy record from before the per-criterion modes (the superseded whole-story policy)"})
        self.assertEqual([e for e in entries if e.get("where") == "closure-evidence/hardening/c.json"], [])
        self.assertEqual(self.find(entries, token="CHANGE_REQUIRED")["carried_by"], [
            {"path": "aisef/control/obligation.py", "kind": "code"},
            {"path": "closure-evidence/hardening/a.json", "kind": "evidence"},
            {"path": "closure-evidence/hardening/c.json", "kind": "evidence"},
            {"path": "closure-evidence/hardening/f.txt", "kind": "evidence-text"}])
        entries, problems = self.entries(extra={"docs/a.md": "CHANGE_REQUIRED", "closure-evidence/hardening/f.txt": "CHANGE_REQUIRED"})
        self.assertEqual([c["path"] for c in self.find(entries, token="CHANGE_REQUIRED")["carried_by"]],
                         ["aisef/control/obligation.py", "closure-evidence/hardening/f.txt", "docs/a.md"])   # by path, not discovery

    def test_the_grammar_citation_and_the_V2_kernel_fail_closed(self):
        _, problems = self.entries(normalize=NORMALIZE_NO_FOLD)
        self.assertEqual(problems, ["inventory: aisef/control/normalize.py::ac_proof with its case folding is not where the citation says"])
        _, problems = self.entries(normalize=None)
        self.assertEqual(problems, ["inventory: aisef/control/normalize.py::ac_proof with its case folding is not where the citation says"])
        _, problems = self.entries(extra={"aisef2/plan/x.py": "MODE = 'PRESERVE_REQUIRED'\nY = 'CHANGE_REQUIRED'\n"})
        self.assertEqual(problems, ["inventory: V1 proof modes appear inside the V2 kernel: ['CHANGE_REQUIRED', 'PRESERVE_REQUIRED']"])

    def test_alias_entries_and_kinds(self):
        with mock.patch.object(gm, "ALIASES", {"OLD": "CHANGE_REQUIRED"}):
            entries, problems = self.entries()
        self.assertEqual(problems, [])
        self.assertEqual(self.find(entries, kind="alias"), {"kind": "alias", "name": "OLD", "target": "CHANGE_REQUIRED",
                                                            "classification": "ALIAS"})
        self.assertEqual([gm._kind(p) for p in ("aisef/kit/prompts/x.md", "aisef/invariants.yaml", "aisef/control/gate.py",
                                                "tests/fixtures/bmad/epics.md", "tests/hardening/t.py", "docs/x.md",
                                                "validation/x.json", "closure-evidence/hardening/x.json",
                                                "closure-evidence/hardening/x.py")],
                         ["prompt", "config", "code", "fixture", "test", "doc", "validation", "evidence", "evidence-text"])


if __name__ == "__main__":
    unittest.main()
