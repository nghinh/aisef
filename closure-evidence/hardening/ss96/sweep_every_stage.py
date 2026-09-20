"""Family sweep: make each stage's evidence UNRUNNABLE in turn and record how the kernel routes it."""
import json
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import tests  # noqa
from tests.hardening import policy_v2 as P
from aisef.clients.base import quote_command
from aisef.clients.synthetic import Script, Step, SyntheticClientAdapter
from aisef.config import DEFAULTS, Config
from aisef.control.outcome import Outcome
from aisef.phases.implement import implement_story

TEST_OK = quote_command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"])
MISSING = "aisef-no-such-tool-xyz"


def run(name, *, crit="new", test=TEST_OK, lint="true", review="PASS", security="PASS",
        contract=None, retries=1, extra_cfg=None):
    case = P.Case(name, name, [P._crit(crit, "CHANGE_REQUIRED")])
    p = P.Project()
    try:
        client = SyntheticClientAdapter(Script(developer=[Step.changed(P.files_for(case))],
                                               review=[Step(review)], security=[Step(security)]))
        cfg = Config({**DEFAULTS, "tools.lint": lint, "run.max_retries": retries, "tools.test": test,
                      **(extra_cfg or {})})
        story = P.story_for(case)
        if contract:
            story.verification_contract = list(contract)
        out = implement_story(story, project=p.path, workdir=p.work, artifact_root=p.artifacts,
                              client=client, config=cfg)
        failed, unrunnable = [], []
        for a in out.attempts:
            for c in (a.gate.checks if a.gate else []):
                if c.outcome is Outcome.FAILED and c.name not in failed:
                    failed.append(c.name)
                if c.outcome is Outcome.UNRUNNABLE and c.name not in unrunnable:
                    unrunnable.append(c.name)
        return {"case": name, "terminal": "done" if out.done else (out.terminal or ""),
                "quality_attempts": out.quality_attempts,
                "developer_sessions": len([c for c in client.calls if c.role == "developer"]),
                "verify_only_attempts": len([a for a in out.attempts if a.verify_only]),
                "infra_attempts": len([a for a in out.attempts if a.infra]),
                "checks_FAILED": failed, "checks_UNRUNNABLE": unrunnable,
                "reason": (out.blocked_reason or "")[:90]}
    finally:
        p.close()


rows = [
    run("control: everything runnable", crit="new"),
    run("A/B nop+tdd: parent evidence unrunnable", crit="parent_unrunnable"),
    run("C: test tool unrunnable", test=MISSING),
    run("D1: lint unrunnable", lint=MISSING),
    run("E: review unrunnable", review="UNRUNNABLE"),
    run("F: security unrunnable", security="UNRUNNABLE"),
    run("G: genuine candidate failure", crit="new", extra_cfg={"tools.test": TEST_OK}),
]
for r in rows:
    print(json.dumps(r, ensure_ascii=False))
