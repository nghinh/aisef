"""Lifecycle probe: a story whose candidate is correct but whose PARENT nop evidence cannot run."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import tests  # noqa
from tests.hardening import policy_v2 as P
from aisef.clients.base import quote_command
from aisef.clients.synthetic import Script, Step, SyntheticClientAdapter
from aisef.config import DEFAULTS, Config
from aisef.phases.implement import implement_story

case = P.Case("PROBE", "one CHANGE_REQUIRED criterion, correct candidate, parent evidence unrunnable",
              [P._crit("parent_unrunnable", "CHANGE_REQUIRED")])
retries = int(sys.argv[1]) if len(sys.argv) > 1 else 2
p = P.Project()
try:
    client = SyntheticClientAdapter(Script(developer=[Step.changed(P.files_for(case))],
                                           review=[Step.passes()], security=[Step.passes()]))
    cfg = Config({**DEFAULTS, "tools.lint": "true", "run.max_retries": retries,
                  "tools.test": quote_command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"])})
    out = implement_story(P.story_for(case), project=p.path, workdir=p.work, artifact_root=p.artifacts,
                          client=client, config=cfg)
    print(f"max_retries={retries} terminal={out.terminal!r} done={out.done}")
    print(f"  reason: {out.blocked_reason[:200]}")
    print(f"  attempts={len(out.attempts)} quality_attempts={out.quality_attempts} "
          f"developer_sessions={len([c for c in client.calls if c.role=='developer'])}")
    for a in out.attempts:
        print(f"  attempt#{a.number} verify_only={a.verify_only} infra={a.infra} ok={a.ok} outcome={a.outcome!r}")
        if a.gate:
            for c in a.gate.checks:
                if c.outcome is not True and str(c.outcome) not in ("Outcome.PASSED", "Outcome.NOT_APPLICABLE"):
                    print(f"      {c.name}: {c.outcome} | {c.detail[:110]}")
finally:
    p.close()
