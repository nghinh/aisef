"""The product runtime (aisef2.app, `aisef run`) end to end, offline: a one-story calc project, a fake client that
writes the story's code and reports its steps the way the real client does, and a fake provider for the preflight.
Nothing here reaches a network or a model; the real client is never looked up (the run is given the fake's path)."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, cli, preflight, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.arch.enums import ObligationRole, Owner, Polarity, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.probe.calibration import ProbeCapabilityCalibration  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.compiler import ProbeRef, compile_spec  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402

ROUTE = "fakeprov/model-1"
REQUIREMENTS = "# Calc\n\n## 1. Addition\n\n1.1 `app.calc.add(a, b)` returns the sum of a and b.\n"
CALC = "def sub(a, b):\n    return a - b\n"
ADD = "def sub(a, b):\n    return a - b\n\n\ndef add(a, b):\n    return a + b\n"
TEST = ("import unittest\n\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n"
        "        self.assertEqual(calc.add(2, 3), 5)\n")
#: the fake client: `opencode run --format json --model M --title T --dir D PROMPT`, or `--version`. A developer
#: writes the story's code (unless told to change nothing); every session reports one finished step with its tokens.
FAKE_CLIENT = r'''import json, pathlib, sys
argv = sys.argv[1:]
if argv == ["--version"]:
    print("0.0.0-fake")
    raise SystemExit(0)
title, cwd = argv[argv.index("--title") + 1], pathlib.Path(argv[argv.index("--dir") + 1])
mode = pathlib.Path(__file__).with_name("mode").read_text()
if title.startswith("developer") and mode == "write":
    (cwd / "app" / "calc.py").write_text(ADD)
    (cwd / "tests").mkdir(exist_ok=True)
    (cwd / "tests" / "__init__.py").write_text("")
    (cwd / "tests" / "test_add.py").write_text(TEST)
if mode == "interrupt" and title.startswith("developer"):
    raise SystemExit(3)
text = '{"findings": []}' if title.startswith("reviewer") else "done"
print(json.dumps({"type": "text", "part": {"text": text}}))
print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 120, "output": 7, "reasoning": 3,
                                                             "cache": {"read": 10, "write": 0}}}}))
'''


def git(cwd, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", env=env,
                          check=True).stdout.strip()


def make_repo(root: pathlib.Path) -> str:
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "app").mkdir()
    (root / "app" / "__init__.py").write_text("")
    (root / "app" / "calc.py").write_text(CALC)
    (root / "docs").mkdir()
    (root / "docs" / "requirements.md").write_text(REQUIREMENTS)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    return git(root, "rev-parse", "HEAD")


def project_bundle(baseline: str) -> dict:
    req = Requirement.create(id="R-ADD", text="app.calc.add(a, b) returns the sum of a and b", source="docs/requirements.md 1.1")
    contract = BehaviorContract.create(
        id="BC-ADD", requirement_ids=(req.id,), subject=Subject(SubjectKind.PYTHON_CALLABLE, "app.calc:add"),
        stimulus={"args": [2, 3]}, observable={"returns": 5, "within_s": 10}, polarity=Polarity.MUST_HOLD,
        subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale="the requirement's own example")
    approval = ContractApproval(req.id, req.requirement_hash, contract.id, contract.contract_hash, "human:fixture-owner", 1.0, ())
    e = catalog.active()[SubjectKind.PYTHON_CALLABLE]
    spec_id = compile_spec(contract, requirements={req.id: req}, approvals=[approval],
                           probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(e.probe_id, e.probe_digest)}).id
    plan = Plan.create(id="PLAN-CALC", baseline=baseline, plan_quality_policy=NOT_PREREGISTERED, obligations=(
        PlanObligation("C-ADD", spec_id, "S1", ObligationRole.INTRODUCE, EXPECTED_AT_PARENT[ObligationRole.INTRODUCE], (),
                       "S1 introduces addition"),))
    return bundle.dump(name="calc", description="A calculator.", requirements_path="docs/requirements.md",
                       requirements_sha256=hashlib.sha256(REQUIREMENTS.encode()).hexdigest(), product_roots=("app", "tests"),
                       requirements=(req,), contracts=(contract,), approvals=(approval,), plan=plan,
                       facts={"C-ADD": {"requirement": "R-ADD", "section": "§1", "clause": "1.1",
                                        "clause_text": "app.calc.add(a, b) returns the sum of a and b", "subject": "app.calc:add"}},
                       stories={"S1": {"depends_on": [], "tests": ["tests/test_add.py"]}})


SETTINGS = {"format": settings.FORMAT, "client": "opencode", "route": ROUTE,
            "provider": {"name": "fakeprov", "endpoint": "https://provider.invalid/v1", "api_key_env": "AISEF_TEST_NO_KEY"},
            "client_env": [], "budget": {"provider_requests": 20, "turns": 50, "input_tokens": 100000, "output_tokens": 10000},
            "max_turns_per_session": 10, "limits": {o.value: 1 for o in Owner},
            "timeouts_s": {"developer": 60, "reviewer": 60, "tool": 120, "probe": 60}, "preflight": {"chat_probes": 2}}


def provider(served: str = "model-1", fingerprint: str = "fp-1"):
    calls = []

    def transport(path, body=None):
        calls.append(path)
        if body is None:
            return 200, {"data": [{"id": "model-1", "owned_by": "fake"}]}
        return 200, {"model": served, "system_fingerprint": fingerprint, "usage": {"prompt_tokens": 9, "completion_tokens": 1}}
    transport.calls = calls
    return transport


def calibrations() -> tuple:
    e = catalog.active()[SubjectKind.PYTHON_CALLABLE]
    return (ProbeCapabilityCalibration(e.probe_id, e.probe_digest, "returns", "fixture:positive", "fixture:negative", 1.0),)


class ProductBase(unittest.TestCase):
    """A one-story calc project, its settings and the fake client; no tests of its own."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.baseline = make_repo(self.tmp / "source")
        self.project = bundle.load(project_bundle(self.baseline))
        self.settings = settings.load(SETTINGS)
        self.client = self.tmp / "client" / "opencode"
        self.client.parent.mkdir()
        self.client.write_text(f"#!{sys.executable}\nADD = {ADD!r}\nTEST = {TEST!r}\n" + FAKE_CLIENT)
        self.client.chmod(0o755)
        self.mode("write")
        self.scanner = mock.patch.object(ad, "scanner", lambda: ad.NoScanner())
        self.scanner.start()
        self.addCleanup(self.scanner.stop)

    def mode(self, m: str) -> None:
        (self.client.parent / "mode").write_text(m)

    def execute(self, out: str = "out", **kw) -> dict:
        kw.setdefault("transport", provider())
        return R.execute(self.project, self.settings, self.tmp / "source", self.tmp / out, client_exe=str(self.client),
                         cals=calibrations(), **kw)

    def journal(self, out: str = "out"):
        return format3.reconstruct((self.tmp / out / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8"))



@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class Product(ProductBase):
    def test_a_story_is_delivered_and_the_run_verifies_from_its_journal(self):
        rec = self.execute()
        self.assertEqual(rec["delivery_verdict"], "PASS", rec)
        self.assertEqual(rec["story_outcomes"], {"S1": ["COMMIT"]})
        self.assertEqual((rec["productproof"]["total"], rec["productproof"]["delivered"]), (1, 1))
        self.assertEqual(rec["plan_quality_verdict"], "NOT_CLAIMED")
        self.assertEqual(rec["journal"]["closed"], "SHUTDOWN")
        self.assertEqual(json.loads((self.tmp / "out" / "RUN.json").read_text(encoding="utf-8"))["final_main"], rec["final_main"])
        self.assertIn("add", git(self.tmp / "out" / "repo", "show", "main:app/calc.py"))
        self.assertNotIn("add", git(self.tmp / "source", "show", "main:app/calc.py"))     # the source is never written
        spent = rec["budget"]["spent"]
        self.assertEqual((spent["provider_requests"], spent["unaccounted"]), (3 + 2, []))  # preflight 3, two sessions
        self.assertEqual(rec["preflight"]["verdict"], "ATTESTED")
        self.assertEqual(verify(self.project, self.tmp / "out")["verdict"], "VERIFIED")

    def test_verification_refutes_a_record_or_a_journal_that_was_changed(self):
        self.execute()
        out = self.tmp / "out"
        run_json = out / "RUN.json"
        rec = json.loads(run_json.read_text(encoding="utf-8"))
        run_json.write_text(json.dumps({**rec, "delivery_verdict": "FAIL"}), encoding="utf-8")
        self.assertIn("the record says FAIL; the journal re-derives PASS", verify(self.project, out)["problems"])
        run_json.write_text(json.dumps(rec), encoding="utf-8")
        journal = out / rec["journal"]["path"]
        lines = journal.read_text(encoding="utf-8").split("\n")
        lines[3] = lines[3].replace('"', "'", 1)
        journal.write_text("\n".join(lines), encoding="utf-8")
        v = verify(self.project, out)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("the journal does not reconstruct" in p for p in v["problems"]), v)

    def test_a_developer_that_changes_nothing_does_not_deliver(self):
        self.mode("nothing")
        rec = self.execute()
        self.assertEqual(rec["delivery_verdict"], "FAIL")
        self.assertNotEqual(rec["story_outcomes"]["S1"][-1:], ["COMMIT"])
        self.assertEqual(verify(self.project, self.tmp / "out")["verdict"], "VERIFIED")

    def test_an_unattested_route_stops_before_any_session(self):
        base, answers = provider(), iter(("fp-1", None))

        def drifting(path, body=None):      # one probe exposes a fingerprint, the next does not: the deployment changed
            code, doc = base(path, body)
            return (code, {**doc, "system_fingerprint": next(answers)}) if body else (code, doc)

        for name, transport in (("alias", provider(served="model-2")), ("drift", drifting)):
            with self.subTest(case=name):
                with self.assertRaises(preflight.IdentityStop):
                    self.execute(out=name, transport=transport)
                rec = json.loads((self.tmp / name / "RUN.json").read_text(encoding="utf-8"))
                self.assertEqual((rec["failure"]["type"], rec["failure"]["stage"], rec["journal"]), ("IdentityStop", "preflight", None))
                self.assertFalse((self.tmp / name / "sessions").exists())
                self.assertEqual(rec["delivery_verdict"], "NOT_REACHED")

    def test_a_run_directory_is_never_reused(self):
        (self.tmp / "out").mkdir()
        with self.assertRaisesRegex(R.RunRefused, "never reused"):
            self.execute()
        self.assertEqual(list((self.tmp / "out").iterdir()), [])

    def test_an_unadmitted_plan_never_reaches_the_provider(self):
        transport = provider()
        with self.assertRaisesRegex(R.RunRefused, "not admitted"):
            R.execute(self.project, self.settings, self.tmp / "source", self.tmp / "out", client_exe=str(self.client),
                      cals=(), transport=transport)
        self.assertEqual(transport.calls, [])
        rec = json.loads((self.tmp / "out" / "RUN.json").read_text(encoding="utf-8"))
        self.assertIn("probe_calibration", json.dumps(rec["admission"]["failed"]))

    def test_a_repository_whose_requirements_differ_is_refused(self):
        (self.tmp / "source" / "docs" / "requirements.md").write_text(REQUIREMENTS + "1.2 more\n")
        git(self.tmp / "source", "commit", "-qam", "edit")
        other = bundle.load(project_bundle(git(self.tmp / "source", "rev-parse", "HEAD")))
        with self.assertRaisesRegex(R.RunRefused, "not the bundle's"):
            R.execute(other, self.settings, self.tmp / "source", self.tmp / "out", client_exe=str(self.client),
                      cals=calibrations(), transport=provider())

    def test_B3_the_record_and_the_raw_journal_survive_a_run_that_breaks(self):
        """B3: an interruption (KeyboardInterrupt, a BaseException) in the middle of a story still leaves RUN.json, and
        the journal — closed by the kernel's own interruption when shutdown is refused — reconstructs."""
        real = ad.Developer.implement

        def broken(self_, *a, **k):
            real(self_, *a, **k)
            raise KeyboardInterrupt

        with mock.patch.object(ad.Developer, "implement", broken), self.assertRaises(KeyboardInterrupt):
            self.execute()
        rec = json.loads((self.tmp / "out" / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual((rec["failure"]["type"], rec["failure"]["stage"]), ("KeyboardInterrupt", "run"))
        self.assertIn("INTERRUPTED", rec["journal"]["closed"])
        journal = self.journal()
        self.assertFalse(journal.torn_tail)
        self.assertIn("run/interrupted", [e.type for e in journal.events])
        self.assertEqual(rec["delivery_verdict"], "NOT_REACHED")
        self.assertEqual(verify(self.project, self.tmp / "out")["problems"], [])


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class Command(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        baseline = make_repo(self.tmp / "source")
        (self.tmp / "project.json").write_text(json.dumps(project_bundle(baseline)), encoding="utf-8")
        (self.tmp / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")

    def cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.run([*argv])
        return code, out.getvalue(), err.getvalue()

    def test_check_admits_with_the_release_calibrations_and_sends_nothing(self):
        args = ("--check", "--project", str(self.tmp / "project.json"), "--settings", str(self.tmp / "settings.json"),
                "--repo", str(self.tmp / "source"))
        with mock.patch.object(R, "calibrations", calibrations), \
                mock.patch.object(preflight, "http_transport", side_effect=AssertionError("no request")):
            code, out, _ = self.cli(*args)
        self.assertEqual((code, json.loads(out)["ready"]), (0, True))
        with mock.patch.object(R, "calibrations", lambda: ()):
            code, out, _ = self.cli(*args)
        self.assertEqual((code, json.loads(out)["ready"]), (2, False))

    def test_an_input_that_does_not_hold_is_refused_with_status_2(self):
        (self.tmp / "settings.json").write_text(json.dumps({**SETTINGS, "budget": {}}), encoding="utf-8")
        code, _, err = self.cli("--project", str(self.tmp / "project.json"), "--settings", str(self.tmp / "settings.json"),
                                "--repo", str(self.tmp / "source"), "--out", str(self.tmp / "out"))
        self.assertEqual(code, 2)
        self.assertIn("refused: budget names exactly", err)
        self.assertFalse((self.tmp / "out").exists())

    def test_a_live_run_without_the_provider_key_stops_before_any_request(self):
        os.environ.pop("AISEF_TEST_NO_KEY", None)
        with mock.patch.object(R, "calibrations", calibrations), mock.patch("shutil.which", return_value="/bin/true"):
            code, _, err = self.cli("--project", str(self.tmp / "project.json"), "--settings", str(self.tmp / "settings.json"),
                                    "--repo", str(self.tmp / "source"), "--out", str(self.tmp / "out"))
        self.assertEqual(code, 2)
        self.assertIn("AISEF_TEST_NO_KEY is not set", err)
        self.assertEqual(json.loads((self.tmp / "out" / "RUN.json").read_text(encoding="utf-8"))["failure"]["stage"], "preflight")


if __name__ == "__main__":
    unittest.main()
