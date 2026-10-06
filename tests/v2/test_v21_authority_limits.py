"""V2.1 (B-03c) — the kill tests of validation/qualification/authority_limits.py: the real tree is inside the owner's
limits for `aisef bundle migrate` and the review's verification, and one edited source per case is caught, by its rule,
at its line. In process: the edited text is read in place of the file, nothing is written.

Also (outside every mutation kill set, because it needs the repository's git objects): the 2.0 release inventory's
pinned blob is its blob at tag v2.0.0."""

import importlib.util
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import authority_limits as al  # noqa: E402
from validation.qualification import release_inventory as ri  # noqa: E402

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

    def test_a_write_into_an_approval_already_there_is_caught(self):
        # in place, on the input's own objects: the output shares the input's approvals list
        loop = '    for a in out["approvals"]:\n        a["approver"] = "human:migrate"'
        src = edited(BUNDLE_CLI, (self.OUT, f"{self.OUT}\n{loop}"))
        at = line_of(src, 'a["approver"] = "human:migrate"')
        self.assertEqual(check(BUNDLE_CLI, src), [f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{at} bundle_cli.migrate writes the "
                                                  f"approvals{APPROVES}"])
        for write in ('    out["approvals"][0].update({"contract_hash": "x"})', '    out["approvals"][0]["contract_hash"] = "x"',
                      '    del out["approvals"][0]', '    out.get("approvals")[0].setdefault("note", "human:migrate")',
                      '    object.__setattr__(approvals[0], "approver", "human:migrate")',
                      '    held = out["approvals"]\n    held.extend([{"approver": "human:migrate"}])',
                      '    held: list = out["approvals"]\n    held.insert(0, {"approver": "human:migrate"})',
                      '    held = []\n    held += out["approvals"]\n    held[0]["approver"] = "human:migrate"',
                      '    if (held := out["approvals"]):\n        held[0]["approver"] = "human:migrate"'):
            with self.subTest(write=write):
                src = edited(BUNDLE_CLI, (self.OUT, f"{self.OUT}\n{write}"))
                self.assertEqual(check(BUNDLE_CLI, src), [
                    f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{line_of(src, write.splitlines()[-1])} bundle_cli.migrate "
                    f"writes the approvals{APPROVES}"])
        for write in ('    del out["approvals"]', '    out.pop("approvals")'):
            with self.subTest(write=write):
                src = edited(BUNDLE_CLI, (self.OUT, f"{self.OUT}\n{write}"))
                why = "writes an 'approvals' key" if write.startswith("    del") else "writes the approvals"
                self.assertEqual(check(BUNDLE_CLI, src), [f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{line_of(src, write)} "
                                                          f"bundle_cli.migrate {why}{APPROVES}"])

    def test_an_approval_copied_with_changes_or_re_loaded_from_a_rebindable_name_is_caught(self):
        reload = '        approvals = tuple(ContractApproval(**a) for a in data["approvals"])'
        created = f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{{}} bundle_cli.migrate creates a ContractApproval (a migration only " \
                  f"re-loads the input's: ContractApproval(**a)){APPROVES}"
        for edit, at in (
                ('        approvals = tuple(dataclasses.replace(ContractApproval(**a), approver="human:migrate") '
                 'for a in data["approvals"])', "human:migrate"),
                ('        approvals = tuple(ContractApproval(**a) for a in data["approvals"])\n'
                 '        approvals = (copy.replace(approvals[0], approver="human:migrate"), *approvals[1:])', "human:migrate"),
                ('        approvals = []\n        for a in data["approvals"]:\n            a = {**a, "approver": "human:migrate"}\n'
                 '            approvals.append(ContractApproval(**a))\n        approvals = tuple(approvals)',
                 "approvals.append(ContractApproval(**a))"),
                ('        approvals = tuple(ContractApproval(**a) for a in data["approvals"] for a in [{"approver": "human:migrate"}])',
                 "human:migrate"),
                ('        forged = {"approver": "human:migrate"}\n'
                 '        approvals = tuple(ContractApproval(**forged) for a in data["approvals"])', "ContractApproval(**forged)")):
            with self.subTest(edit=edit):
                src = edited(BUNDLE_CLI, (reload, edit))
                self.assertEqual(check(BUNDLE_CLI, src), [created.format(line_of(src, at))])

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


    def test_a_re_export_an_alias_or_a_reference_is_followed_to_where_it_is_defined(self):
        # app/adapters imports commit_all and git, app/run imports GitMerger, git, ad (adapters) and sr (story_runner)
        for imp, use, q in (
                ("from aisef2.app.adapters import commit_all", "commit_all(root, 'confirmed')", "workspace.commit_all"),
                ("from aisef2.app.run import GitMerger", "GitMerger(root).merge('x')", "workspace.GitMerger"),
                ("from aisef2.app.run import git", "git(root, 'commit')", "workspace.git"),
                ("from aisef2.app import run as R", "R.sr.run_story(None)", "story_runner.run_story"),
                ("from aisef2.app import run as R", "R.ad.commit_all(root, 'x')", "workspace.commit_all"),
                ("from aisef2.app import adapters as AD", "AD.git(root, 'commit', '-am', 'x')", "workspace.git")):
            with self.subTest(imp=imp, use=use):
                src = edited(VERIFY, (self.FACTORY, f"{self.FACTORY}\n    {imp}\n    {use}"))
                self.assertEqual(check(VERIFY, src), [f"NO_COMMIT_OR_MERGE {VERIFY}:{line_of(src, use)} review_verify.verify "
                                                      f"calls aisef2.orchestrate.{q}{DECIDES}"])
        # a module-level alias re-exports like an import; a reference that is not a call (a callback) is reached too
        alias = edited(VERIFY, ("from aisef2.product.outcome import Executed\n",
                                "from aisef2.product.outcome import Executed\nfrom aisef2.orchestrate import workspace as W\n"
                                "save = W.commit_all\n"), (self.FACTORY, f"{self.FACTORY}\n    save(root, 'x')"))
        self.assertEqual(check(VERIFY, alias), [f"NO_COMMIT_OR_MERGE {VERIFY}:{line_of(alias, 'save(root')} review_verify.verify "
                                                f"calls aisef2.orchestrate.workspace.commit_all{DECIDES}"])
        src = edited(ADAPTERS, ("from aisef2.app import client, feedback, review_ocr, review_verify\n",
                                "from aisef2.app import client, feedback, review_ocr, review_verify\nkeep = commit_all\n"))
        src = {ADAPTERS: src, VERIFY: edited(VERIFY, (self.FACTORY, f"{self.FACTORY}\n    from aisef2.app.adapters import keep\n"
                                                                    "    hooks = {'done': keep}"))}
        self.assertEqual(al.check(al.ROOT, src), [f"NO_COMMIT_OR_MERGE {VERIFY}:{line_of(src[VERIFY], 'hooks =')} "
                                                  f"review_verify.verify names aisef2.orchestrate.workspace.commit_all{DECIDES}"])

    def test_a_git_command_built_anywhere_is_caught(self):
        out = MigrateNeverApproves.OUT
        for cmd in ('    cmd = ["git", "commit", "-am", "m"]\n    subprocess.run(cmd)',
                    '    subprocess.run("git commit -am m", shell=True)', '    argv = ("git",) + ("merge", "x")'):
            with self.subTest(cmd=cmd):
                src = edited(BUNDLE_CLI, (out, f"{out}\n{cmd}"))
                self.assertEqual(check(BUNDLE_CLI, src), [f"NO_COMMIT_OR_MERGE {BUNDLE_CLI}:{line_of(src, cmd.splitlines()[0])} "
                                                          f"bundle_cli.migrate runs git{DECIDES}"])
        src = edited(BUNDLE_CLI, (out, f"{out}\n    from aisef2.orchestrate import workspace as W\n    W.GitMerger.merge(None, 'x')"))
        self.assertEqual(check(BUNDLE_CLI, src), [     # a method of GitMerger names GitMerger on its way
            f"NO_COMMIT_OR_MERGE {BUNDLE_CLI}:{line_of(src, 'W.GitMerger.merge(')} bundle_cli.migrate names "
            f"aisef2.orchestrate.workspace.GitMerger{DECIDES}"])
        src = edited(BUNDLE_CLI, (out, f'{out}\n    note = "github and gitignore are not git"'))
        self.assertEqual(check(BUNDLE_CLI, src), [])


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

    def test_a_lookup_that_does_not_refuse_this_run_is_caught(self):
        lookup = "    if calibration_for(calibrations(), entry.probe_id, executing(entry.factory), cls) is None:"
        for edit in ("    if calibration_for(calibrations(), entry.probe_id, executing(entry.factory), cls) is not None:",
                     "    if calibration_for(calibrations(), entry.probe_id, executing(entry.factory), 'nothing') is None:",
                     "    if calibration_for(calibrations(()), entry.probe_id, executing(entry.factory), cls) is None:",
                     "    if calibration_for(calibrations(), 'another', executing(entry.factory), cls) is None:",
                     "    if calibration_for(calibrations(), entry.probe_id, executing(len), cls) is None:",
                     "    if calibration_for(calibrations(), entry.probe_id, executing(entry.factory), cls) == ():",
                     "    if calibration_for(calibrations(), entry.probe_id, executing(entry.factory), cls) is False:",
                     "    if calibration_for(tuple(), entry.probe_id, executing(entry.factory), cls) is None:",
                     "    if calibration_for(calibrations(), entry.probe_id, str(entry.factory), cls) is None:",
                     "    other = str(spec)\n    if calibration_for(calibrations(), entry.probe_id, executing(entry.factory), other) is None:",
                     "    other = catalog.registry().observation_class(spec.probe_id, spec.probe_digest, c)\n"
                     "    if calibration_for(calibrations(), entry.probe_id, executing(entry.factory), other) is None:"):
            with self.subTest(edit=edit):
                src = edited(VERIFY, (lookup, edit))
                self.assertEqual(check(VERIFY, src), [f"{self.RULE} {VERIFY}:{line_of(src, 'run_probe(probe, spec')} {UNCALIBRATED}"])
        src = edited(VERIFY, (lookup, "    if not calibration_for(calibrations(), entry.probe_id, executing(entry.factory), cls):"))
        self.assertEqual(check(VERIFY, src), [])     # the other form of the same refusal
        factory = NoCommitOrMerge.FACTORY
        for edit in ((lookup, "    if timeout_s > 0:\n    " + lookup),                          # not on every path
                     (factory, "    probe = catalog.active()[c.subject.kind].factory()"),          # another entry's probe
                     (factory, "    probe = entry.spare()"),                                           # not the entry's factory
                     (factory, f"{factory}\n    entry = catalog.active().get(SubjectKind.CLI_INVOCATION)"),
                     (factory, f"{factory}\n    spec = _mint(c, ProbeRef('another', entry.probe_digest))")):
            with self.subTest(edit=edit):
                src = edited(VERIFY, edit)
                if edit[0] == lookup:     # the refusal's own lines, re-indented under the new if
                    src = src.replace('        return Verification(UNVERIFIABLE, f"{entry.probe_id} is not calibrated',
                                      '            return Verification(UNVERIFIABLE, f"{entry.probe_id} is not calibrated', 1)
                self.assertEqual(check(VERIFY, src), [f"{self.RULE} {VERIFY}:{line_of(src, 'run_probe(probe, spec')} {UNCALIBRATED}"])
        guard = ('    if calibration_for(calibrations(), entry.probe_id, executing(entry.factory), cls) is None:\n'
                 '        return Verification(UNVERIFIABLE, f"{entry.probe_id} is not calibrated for {cls!r} at the bytes that run: an "\n'
                 '                            "unqualified observation corroborates nothing", entry.probe_id)\n')
        bound = "enforcement=probe.enforcement())     # PROBE-BIND-1\n"
        src = edited(VERIFY, (guard, ""), (bound, bound + guard))     # the refusal after the run: too late
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

    def test_a_second_path_through_a_re_export_is_caught(self):
        for rel, src, q, only in (
                ("aisef2/orchestrate/second_gate.py", "from aisef2.app.adapters import review_verify\n\n\ndef decide(v, f):\n"
                 "    return review_verify.blocks(v, f, 'fix-loop', 'low', None)\n", "review_verify.blocks", "Reviewer.review"),
                ("aisef2/app/second_gate.py", "from aisef2.app import adapters as A\n\n\ndef decide(v, f):\n"
                 "    return A.review_verify.blocks(v, f, 'fix-loop', 'low', None)\n", "review_verify.blocks", "Reviewer.review"),
                ("aisef2/orchestrate/x.py", "from aisef2.app import run as R\n\n\ndef decide(f):\n"
                 "    return R.ad.review_verify.verify(f)\n", "review_verify.verify", "Reviewer._verify")):
            with self.subTest(rel=rel, src=src):
                self.assertEqual(check(rel, src), [f"{self.RULE} {rel}:5 decide names {q}: only aisef2/app/adapters.py::{only} does"])

    def test_what_blocks_answered_rebound_or_not_asked_on_every_path_is_caught(self):
        typed = "            typed.append(Finding("
        asked = "            confirmed = review_verify.blocks("
        for edit in ((typed, "            confirmed |= True\n" + typed), (typed, "            confirmed = True\n" + typed),
                     (typed, "            confirmed, _ = True, 0\n" + typed), (asked, "            if a:\n    " + asked)):
            with self.subTest(edit=edit):
                src = edited(ADAPTERS, edit)
                self.assertEqual(check(ADAPTERS, src), [f"{self.RULE} {ADAPTERS}:{line_of(src, 'typed.append(Finding(')} "
                                                        f"Reviewer.review{CORROBORATES}"])

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
        fx = json.loads((ROOT / "tests/v2/fixtures/known_bad/authority_limits.json").read_text(encoding="utf-8"))
        self.assertNotRegex(fx["expect"], r"\.py:\d")     # no line of a real file: an edit above it changes nothing here
        src = edited(fx["path"], (fx["find"], fx["replace"]))
        self.assertIn(f"MIGRATE_NEVER_APPROVES {BUNDLE_CLI}:{line_of(src, fx['replace'])} bundle_cli.migrate writes an "
                      f"'approvals' key{APPROVES}", r["observed"])
        self.assertFalse(cc.calibrate(cc.always_pass_mutant(c))["calibrated"])


class ReleaseInventoryHistoryAtTheTag(unittest.TestCase):
    """The pin release_inventory.history_problems checks without git (RELEASE_2_0_BLOB) is the 2.0 inventory's blob at
    tag v2.0.0. Needs the repository's git objects: outside every mutation kill set on purpose."""

    def test_the_pinned_2_0_blob_is_the_tags(self):
        def git(*args):
            r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, f"git {' '.join(args)}: the history of tag v2.0.0 is not available here; run "
                                              f"this test in the AISEF repository ({r.stderr.strip()})")
            return r.stdout.strip()
        self.assertEqual(git("rev-parse", "v2.0.0^{commit}"), ri.TAG_2_0)
        self.assertEqual(git("rev-parse", f"{ri.TAG_2_0}:{ri.RELEASE_2_0_REL}"), ri.RELEASE_2_0_BLOB)
        self.assertEqual(git("rev-parse", f"v2.0.0:{ri.RELEASE_2_0_REL}"), ri.RELEASE_2_0_BLOB)
        self.assertEqual(ri.history_problems(), [])


if __name__ == "__main__":
    unittest.main()
