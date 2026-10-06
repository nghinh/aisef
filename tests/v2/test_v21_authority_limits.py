"""V2.1 (B-03c) — the kill tests of validation/qualification/authority_limits.py: the real tree is inside the owner's
limits for `aisef bundle migrate` and the review's verification, and one edited source per case is caught, by its rule,
at its line. In process: the edited text is read in place of the file, nothing is written."""

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import authority_limits as al  # noqa: E402

BUNDLE_CLI, BUNDLE, VERIFY, ADAPTERS = ("aisef2/app/bundle_cli.py", "aisef2/app/bundle.py", "aisef2/app/review_verify.py",
                                        "aisef2/app/adapters.py")
APPROVES = ": what migrate reaches re-binds the plan and never approves"
DECIDES = ": what migrate or verify reaches never commits, merges or decides"
CORROBORATES = (" corroborates a Finding other than by what review_verify.blocks answered: a finding blocks only when "
                "blocks() says so")
UNBOUND = "verify reads run_probe's record unbound: every run_probe is bound_result's first argument (PROBE-BIND-1)"
UNCALIBRATED = ("verify runs the probe with no calibration lookup before it that returns when the class is not calibrated "
                "at the bytes that run")


def edited(rel: str, *pairs: tuple[str, str]) -> str:
    src = (ROOT / rel).read_text(encoding="utf-8")
    for find, replace in pairs:
        if src.count(find) != 1:
            raise AssertionError(f"{rel}: the anchor {find!r} must occur exactly once")
        src = src.replace(find, replace)
    return src


def line_of(src: str, needle: str) -> int:
    return next(n for n, line in enumerate(src.splitlines(), 1) if needle in line)


def check(rel: str, src: str) -> list[str]:
    return al.check(al.ROOT, {rel: src})


class RealTree(unittest.TestCase):
    def test_the_tree_is_inside_the_limits_and_the_closure_crosses_modules(self):
        self.assertEqual(al.check(), [])     # adapters.Developer commits: it is not reached from migrate or verify
        mods = al._modules(al.ROOT, {})
        index = {f"{al.opa._module_name(rel)}.{name}": (rel, node) for rel, m in mods.items() for name, node in m.defs}
        migrate = {q for q, _, _ in al._closure(mods, index, (al.MIGRATE,))}
        verify = {q for q, _, _ in al._closure(mods, index, (al.VERIFY,))}
        self.assertLessEqual({al.MIGRATE, "aisef2.app.bundle.load", "aisef2.app.bundle_cli._earlier"}, migrate)
        self.assertLessEqual({al.VERIFY, "aisef2.app.bundle_cli._mint", "aisef2.app.run.calibrations"}, verify)
        self.assertTrue(all(index[q][0].startswith("aisef2/app/") for q in migrate | verify))
        self.assertNotIn("aisef2.app.bundle_cli.approve", migrate)


class MigrateNeverApproves(unittest.TestCase):
    OUT = '    out = {**dict(data), "plan": plain(new_plan)}'

    def test_an_approvals_key_or_store_or_append_is_caught_where_it_is_written(self):
        key = '    out = {**dict(data), "plan": plain(new_plan), "approvals": [*data["approvals"]]}'
        src = edited(BUNDLE_CLI, (self.OUT, key))
        self.assertEqual(check(BUNDLE_CLI, src), [f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{line_of(src, key)} "
                                                  f"bundle_cli.migrate writes an 'approvals' key{APPROVES}"])
        store = '    out["approvals"] = out["approvals"] + []'
        src = edited(BUNDLE_CLI, (self.OUT, f"{self.OUT}\n{store}"))
        self.assertEqual(check(BUNDLE_CLI, src), [f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{line_of(src, store)} "
                                                  f"bundle_cli.migrate writes an 'approvals' key{APPROVES}"])
        anchor = "    project.order()     # a cycle is refused at load"     # bundle.load: reached from migrate
        src = edited(BUNDLE, (anchor, '    data["approvals"].append({"approver": "human:migrate"})\n' + anchor))
        self.assertEqual(check(BUNDLE, src), [f"MIGRATE_NEVER_APPROVES {BUNDLE}:{line_of(src, 'human:migrate')} bundle.load "
                                              f"writes the approvals{APPROVES}"])

    def test_an_approval_created_rather_than_re_loaded_is_caught(self):
        reload = '        approvals = tuple(ContractApproval(**a) for a in data["approvals"])'
        src = edited(BUNDLE_CLI, (reload, '        approvals = tuple(ContractApproval(**{**a, "approver": "human:migrate"}) '
                                          'for a in data["approvals"])'))
        self.assertEqual(check(BUNDLE_CLI, src), [
            f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{line_of(src, 'human:migrate')} bundle_cli.migrate creates a ContractApproval "
            f"(a migration only re-loads the input's: ContractApproval(**a)){APPROVES}"])
        # re-loading names an element of the input's approvals; an element of anything else is a new approval
        src = edited(BUNDLE_CLI, (reload, '        approvals = tuple(ContractApproval(**b) for b in [{**a, "approver": "human:migrate"} '
                                          'for a in data["approvals"]])'))
        self.assertEqual(check(BUNDLE_CLI, src), [
            f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{line_of(src, 'human:migrate')} bundle_cli.migrate creates a ContractApproval "
            f"(a migration only re-loads the input's: ContractApproval(**a)){APPROVES}"])

    def test_calling_approve_is_caught_with_everything_approve_then_reaches(self):
        written = 'return {**dict(bundle), "approvals": [*bundle["approvals"], *new]}'
        src = edited(BUNDLE_CLI, (self.OUT, self.OUT + '\n    out = approve(out, contracts[0].id, "human:migrate", 0.0)'))
        self.assertCountEqual(check(BUNDLE_CLI, src), [
            f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{line_of(src, 'out = approve(')} bundle_cli.migrate calls bundle_cli.approve{APPROVES}",
            f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{line_of(src, 'new.append(plain(ContractApproval(')} bundle_cli.approve creates "
            f"a ContractApproval (a migration only re-loads the input's: ContractApproval(**a)){APPROVES}",
            f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{line_of(src, written)} bundle_cli.approve writes an 'approvals' key{APPROVES}"])


class NoCommitOrMerge(unittest.TestCase):
    FACTORY = "    probe = entry.factory()"

    def test_verify_committing_or_journaling_is_caught(self):
        src = edited(VERIFY, ("from aisef2.product.outcome import Executed",
                              "from aisef2.product.outcome import Executed\nfrom aisef2.orchestrate.workspace import commit_all"),
                     (self.FACTORY, self.FACTORY + '\n    commit_all(root, "a confirmed finding")'))
        self.assertEqual(check(VERIFY, src), [f"NO_COMMIT_OR_MERGE {VERIFY}:{line_of(src, 'commit_all(root')} review_verify.verify "
                                              f"calls aisef2.orchestrate.workspace.commit_all{DECIDES}"])
        src = edited(VERIFY, ("SubjectAbsence, SubjectKind\n", "SubjectAbsence, SubjectKind, EventType\n"),
                     (self.FACTORY, self.FACTORY + '\n    finding["run"].append(EventType.STORY_COMMIT, {})'))
        self.assertEqual(check(VERIFY, src), [f"NO_COMMIT_OR_MERGE {VERIFY}:{line_of(src, 'STORY_COMMIT')} review_verify.verify "
                                              f"appends the control event STORY_COMMIT to a journal{DECIDES}"])

    def test_migrate_deciding_or_what_it_reaches_running_git_is_caught(self):
        out = MigrateNeverApproves.OUT
        src = edited(BUNDLE_CLI, ("from aisef2.app import bundle as B\n", "from aisef2.app import bundle as B\nfrom aisef2.orchestrate import gate\n"),
                     (out, out + "\n    gate.decision(None, [], True)"))
        self.assertEqual(check(BUNDLE_CLI, src), [f"NO_COMMIT_OR_MERGE {BUNDLE_CLI}:{line_of(src, 'gate.decision(')} "
                                                  f"bundle_cli.migrate calls aisef2.orchestrate.gate.decision{DECIDES}"])
        anchor = "    project.order()     # a cycle is refused at load"
        src = edited(BUNDLE, (anchor, '    subprocess.run(["git", "commit", "-am", "migrated"], check=False)\n' + anchor))
        self.assertEqual(check(BUNDLE, src), [f"NO_COMMIT_OR_MERGE {BUNDLE}:{line_of(src, 'subprocess.run(')} bundle.load "
                                              f"runs git{DECIDES}"])


class VerifyThroughBindingAndCalibration(unittest.TestCase):
    RULE = "VERIFY_THROUGH_BINDING_AND_CALIBRATION"

    def test_an_unbound_probe_record_is_caught(self):
        factory = NoCommitOrMerge.FACTORY
        src = edited(VERIFY, (factory, factory + "\n    raw = run_probe(probe, spec, RevisionRef(revision, root), "
                                                 "ExecutionEnv(interpreter, timeout_s, Enforcement.PARTIAL))"))
        self.assertEqual(check(VERIFY, src), [f"{self.RULE} {VERIFY}:{line_of(src, 'raw = run_probe(')} {UNBOUND}"])

    def test_a_probe_run_without_the_calibration_refusal_before_it_is_caught(self):
        guard = ('    if calibration_for(calibrations(), entry.probe_id, executing(entry.factory), cls) is None:\n'
                 '        return Verification(UNVERIFIABLE, f"{entry.probe_id} is not calibrated for {cls!r} at the bytes that run: an "\n'
                 '                            "unqualified observation corroborates nothing", entry.probe_id)\n')
        src = edited(VERIFY, (guard, ""))
        self.assertEqual(check(VERIFY, src), [f"{self.RULE} {VERIFY}:{line_of(src, 'run_probe(probe, spec')} {UNCALIBRATED}"])
        src = edited(VERIFY, (guard, guard.replace("        return Verification(", "        _ = Verification(")))
        self.assertEqual(check(VERIFY, src), [f"{self.RULE} {VERIFY}:{line_of(src, 'run_probe(probe, spec')} {UNCALIBRATED}"])

    def test_a_verification_that_runs_no_probe_is_caught(self):
        src = edited(VERIFY, ("run_probe(probe, spec, RevisionRef", "probe.observe(spec, RevisionRef"))
        self.assertEqual(check(VERIFY, src), [f"{self.RULE} {VERIFY}:{line_of(src, 'def verify(')} verify runs no probe: a "
                                              "confirmation is the kernel's probe's, never the finding's"])


class OneDecisionPath(unittest.TestCase):
    RULE = "ONE_DECISION_PATH"

    def test_a_second_caller_of_verify_blocks_or_migrate_is_caught(self):
        src = edited(ADAPTERS, ("            v = self._verify(f, scope.root, head)",
                                "            v = review_verify.verify(f, requirements=self.project.requirements, product_roots=(), "
                                "root=scope.root, revision=head, timeout_s=1.0, interpreter=self.interpreter)"))
        self.assertEqual(check(ADAPTERS, src), [f"{self.RULE} {ADAPTERS}:{line_of(src, 'v = review_verify.verify(')} Reviewer.review "
                                                "names review_verify.verify: only aisef2/app/adapters.py::Reviewer._verify does"])
        second = "from aisef2.app import review_verify\n\n\ndef decide(v, f):\n    return review_verify.blocks(v, f, 'fix-loop', 'low', None)\n"
        self.assertEqual(check("aisef2/app/second_gate.py", second), [
            f"{self.RULE} aisef2/app/second_gate.py:5 decide names review_verify.blocks: only aisef2/app/adapters.py::Reviewer.review does"])
        auto = "from aisef2.app.bundle_cli import migrate as m\n\n\ndef upgrade(doc):\n    return m(doc)[0]\n"
        self.assertEqual(check("aisef2/orchestrate/auto.py", auto), [
            f"{self.RULE} aisef2/orchestrate/auto.py:5 upgrade names bundle_cli.migrate: only aisef2/app/bundle_cli.py::main does"])
        src = edited(ADAPTERS, ("    def _verify(self, finding: dict, root: str, head: str)", "    def _probe(self, finding: dict, root: str, head: str)"))
        self.assertEqual(check(ADAPTERS, src), [f"{self.RULE} {ADAPTERS}:{line_of(src, 'return review_verify.verify(')} Reviewer._probe "
                                                "names review_verify.verify: only aisef2/app/adapters.py::Reviewer._verify does"])

    def test_a_finding_corroborated_other_than_by_blocks_is_caught(self):
        src = edited(ADAPTERS, ("(v.evidence(),) if confirmed else ()", "(v.evidence(),) if v.status == review_verify.CONFIRMED else ()"))
        self.assertEqual(check(ADAPTERS, src), [f"{self.RULE} {ADAPTERS}:{line_of(src, 'typed.append(Finding(')} Reviewer.review{CORROBORATES}"])
        src = edited(ADAPTERS, ("            confirmed = review_verify.blocks(", "            confirmed = v.status == 'CONFIRMED' or review_verify.blocks("))
        self.assertEqual(check(ADAPTERS, src), [f"{self.RULE} {ADAPTERS}:{line_of(src, 'typed.append(Finding(')} Reviewer.review{CORROBORATES}"])
        src = edited(ADAPTERS, ("(v.evidence(),) if confirmed else ()", "(v.evidence(),)"))
        self.assertEqual(check(ADAPTERS, src), [f"{self.RULE} {ADAPTERS}:{line_of(src, 'typed.append(Finding(')} Reviewer.review{CORROBORATES}"])

    def test_a_path_that_is_gone_fails_closed(self):
        src = edited(BUNDLE_CLI, ("        out, report = migrate(_read(a.bundle))", "        out, report = _read(a.bundle), {}"))
        self.assertEqual(check(BUNDLE_CLI, src), [f"{self.RULE} {BUNDLE_CLI}:1 main no longer names bundle_cli.migrate: the one "
                                                  "path is gone (re-aim the rule)"])
        src = edited(BUNDLE_CLI, ("def migrate(data: Mapping)", "def rebind(data: Mapping)"))
        self.assertEqual(check(BUNDLE_CLI, src), [f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:1 bundle_cli.migrate is missing",
                                                  f"{self.RULE} {BUNDLE_CLI}:1 main no longer names bundle_cli.migrate: the one "
                                                  "path is gone (re-aim the rule)"])
        src = edited(ADAPTERS, ("class Reviewer:", "class Critic:"))
        self.assertIn(f"{self.RULE} {ADAPTERS}:1 Reviewer is missing", check(ADAPTERS, src))


class Calibration(unittest.TestCase):
    def test_the_q0_checker_rejects_its_known_bad_fixture_and_an_always_pass_mutant_fails_calibration(self):
        name = "aisef_v2_checker_calibration"
        if name in sys.modules:
            cc = sys.modules[name]
        else:
            spec = importlib.util.spec_from_file_location(name, ROOT / "validation/v2/checker_calibration.py")
            cc = importlib.util.module_from_spec(spec)
            sys.modules[name] = cc
            spec.loader.exec_module(cc)
        c = cc._authority_limits()
        self.assertIn(cc._authority_limits, cc.REGISTRY)
        r = cc.calibrate(c)
        self.assertTrue(r["calibrated"], r)
        self.assertTrue(any(p.startswith("MIGRATE_NEVER_APPROVES aisef2/app/bundle_cli.py:129 bundle_cli.migrate writes an "
                                         "'approvals' key") for p in r["observed"]), r["observed"])
        self.assertFalse(cc.calibrate(cc.always_pass_mutant(c))["calibrated"])


if __name__ == "__main__":
    unittest.main()
