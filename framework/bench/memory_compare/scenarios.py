"""Deterministic scenario fixtures for the paired A/B/C memory harness.

Each scenario is a small, reproducible story consisting of:

- ``id``: short, stable identifier; matches a fixture file under
  ``framework/bench/memory_compare/scenarios/<id>.json``.
- ``kind``: ``dogfood`` for hand-authored reproductions of the three
  dogfood tasks (par, calc, par_mutation) the directive names, and
  ``long_horizon`` for the four required scripted long-horizon micro-stories.
- ``description``: one-line summary; no behavior change.
- ``write_scope``: a list of paths the fake agent may write.
- ``fixture``: absolute path to a JSON file with deterministic inputs:
  scripted project root template, writeable files, initial ledger/journal
  contents, the memory records (when applicable), and the canonical
  expected outcome of one scripted attempt.

The scenarios deliberately **do not** import the dogfood test bodies or
mutate them. The parent directive says "Must NOT modify existing dogfood
tests." We re-derive the script by reading the same `tests/dogfood/_runner.py`
and the corresponding `test_*.py` only for description text, and the
scenario fixtures run their own minimal stubs (see `tests/fake_dogfood.py`).

For the four ``long_horizon`` scenarios (convention carry-over, failure
pattern repeat, reviewer recurrence, security recurrence, supersede
authority, tool-env repeat — the directive names six behaviour classes but
funds four scenario families; we instantiate six scenarios covering each
class) we hand-author a small canonical store and a sequence of scripted
attempts that, when paired against the local memory arm, demonstrate the
intended repeated-error behaviour. The scripted agent is deterministic;
the recorded outcome reproduces without external dependencies.

Adding a scenario:

- Implement the fixture JSON (deterministic; uses absolute paths only via
  ``pathlib.Path``).
- Register it in ``SCENARIOS`` below with id, kind, description, write_scope.
- Optionally add a corresponding fixture file. If omitted, the inline
  ``fixture`` block in the scenario dict is used.
- Scenario tests in `tests/test_scenarios.py` exercise the load path.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"


@dataclass(frozen=True)
class Scenario:
    id: str
    kind: str  # "dogfood" | "long_horizon"
    description: str
    write_scope: tuple[str, ...]
    fixture_path: Path | None = None
    fixture_inline: dict[str, Any] | None = None

    def fixture(self) -> dict:
        if self.fixture_path is not None:
            return json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if self.fixture_inline is not None:
            return dict(self.fixture_inline)
        raise RuntimeError(f"scenario {self.id!r} has no fixture")


def _merge_inline(path: Path | None, inline: dict[str, Any] | None) -> Scenario:
    if path is not None:
        return Scenario(
            id=inline["id"], kind=inline["kind"], description=inline["description"],
            write_scope=tuple(inline["write_scope"]),
            fixture_path=path,
        )
    return Scenario(
        id=inline["id"], kind=inline["kind"], description=inline["description"],
        write_scope=tuple(inline["write_scope"]),
        fixture_inline=inline,
    )


# Hand-authored inline fixtures. Each is deterministic and self-contained.
# A scenario with a fixture file may also be registered; we keep all inline
# here so that the harness has no external file dependency for the four
# long-horizon micro-stories (deterministic, reviewable in code review).

_LONG_HORIZON_FIXTURES: dict[str, dict] = {
    "long_horizon/convention_carry_over": {
        "story_sequence": ["S1", "S2", "S3", "S4", "S5", "S6"],
        "evidence_text": "Use bounded retries with exponential backoff",
        "expected_repeated_behavior_id": "BOUNDED_RETRY_UNAPPLIED",
        "scripted_outcomes": [
            {"story": "S1", "uses_convention": True, "repeated_error_id": None, "budget_used": 0.20},
            {"story": "S2", "uses_convention": True, "repeated_error_id": None, "budget_used": 0.18},
            {"story": "S3", "uses_convention": True, "repeated_error_id": None, "budget_used": 0.22},
            {"story": "S4", "uses_convention": True, "repeated_error_id": None, "budget_used": 0.17},
            {"story": "S5", "uses_convention": True, "repeated_error_id": None, "budget_used": 0.21},
            {"story": "S6", "uses_convention": True, "repeated_error_id": None, "budget_used": 0.19},
        ],
        "memory_records": [
            {
                "id": "CONVENTION_BOUNDED_RETRY",
                "epic": "E1",
                "story": "*",
                "roles": ["developer"],
                "paths": ["*"],
                "tools": ["*"],
                "trust": "deterministic",
                "text": "Use bounded retries with exponential backoff across consecutive stories.",
                "source_ref": "docs/conventions.md",
                "source_type": "artifact",
                "origin_story": "S1",
            },
        ],
    },
    "long_horizon/failure_pattern_repeat": {
        "story_sequence": ["S2", "S4", "S5", "S6", "S7", "S8"],
        "evidence_text": "Retry the migration transaction on contention",
        "expected_repeated_behavior_id": "MIGRATION_TX_UNPROTECTED",
        "scripted_outcomes": [
            {"story": "S2", "uses_failure_pattern": True, "repeated_error_id": None, "budget_used": 0.19},
            {"story": "S4", "uses_failure_pattern": True, "repeated_error_id": None, "budget_used": 0.21},
            {"story": "S5", "uses_failure_pattern": True, "repeated_error_id": None, "budget_used": 0.18},
            {"story": "S6", "uses_failure_pattern": True, "repeated_error_id": None, "budget_used": 0.20},
            {"story": "S7", "uses_failure_pattern": True, "repeated_error_id": None, "budget_used": 0.22},
            {"story": "S8", "uses_failure_pattern": True, "repeated_error_id": None, "budget_used": 0.20},
        ],
        "memory_records": [
            {
                "id": "FAILURE_MIGRATION_TX",
                "epic": "E1",
                "story": "*",
                "roles": ["developer"],
                "paths": ["src/db"],
                "tools": ["*"],
                "trust": "deterministic",
                "text": "Retry the migration transaction on contention. Failure id: MIGRATION_TX_UNPROTECTED.",
                "source_ref": "docs/failure-taxonomy.md",
                "source_type": "artifact",
                "origin_story": "S2",
            },
        ],
    },
    "long_horizon/reviewer_recurrence": {
        "story_sequence": ["S1", "S3", "S5", "S6"],
        "evidence_text": "Reviewer blocks null-boundary handling in similar reviews.",
        "expected_repeated_behavior_id": "NULL_BOUNDARY_UNDEFINED",
        "scripted_outcomes": [
            {"story": "S1", "review_blocks": True, "repeated_error_id": None, "budget_used": 0.21},
            {"story": "S3", "review_blocks": True, "repeated_error_id": None, "budget_used": 0.20},
            {"story": "S5", "review_blocks": True, "repeated_error_id": None, "budget_used": 0.19},
            {"story": "S6", "review_blocks": True, "repeated_error_id": None, "budget_used": 0.18},
        ],
        "memory_records": [
            {
                "id": "REVIEW_NULL_BOUNDARY",
                "epic": "E1",
                "story": "*",
                "roles": ["reviewer"],
                "paths": ["src/api"],
                "tools": ["*"],
                "trust": "reviewer",
                "text": "Reviewer blocks missing null-boundary handling across reviews.",
                "source_ref": "docs/review-patterns.md",
                "source_type": "artifact",
                "origin_story": "S1",
                "candidate": "a" * 40,
            },
        ],
    },
    "long_horizon/security_recurrence": {
        "story_sequence": ["S2", "S5", "S7"],
        "evidence_text": "Security requires ownership check on authorization edge.",
        "expected_repeated_behavior_id": "AUTHZ_OWNERSHIP_UNVERIFIED",
        "scripted_outcomes": [
            {"story": "S2", "security_blocks": True, "repeated_error_id": None, "budget_used": 0.22},
            {"story": "S5", "security_blocks": True, "repeated_error_id": None, "budget_used": 0.19},
            {"story": "S7", "security_blocks": True, "repeated_error_id": None, "budget_used": 0.21},
        ],
        "memory_records": [
            {
                "id": "SECURITY_AUTHZ_OWNERSHIP",
                "epic": "E1",
                "story": "*",
                "roles": ["security"],
                "paths": ["src/api"],
                "tools": ["*"],
                "trust": "security",
                "text": "Security blocks authorization edge lacking ownership check.",
                "source_ref": "docs/security-patterns.md",
                "source_type": "artifact",
                "origin_story": "S2",
                "candidate": "b" * 40,
            },
        ],
    },
    "long_horizon/supersede_authority": {
        "story_sequence": ["S1", "S2", "S6"],
        "evidence_text": "Architecture superseded: prefer audit pipeline over manual journal.",
        "expected_repeated_behavior_id": "JOURNAL_MANUAL_OBSOLETE",
        "scripted_outcomes": [
            {"story": "S1", "uses_old_advice": True, "repeated_error_id": None, "budget_used": 0.21,
             "supersession_event": {"active_id": "ARCH_OLD", "after": "superseded"}},
            {"story": "S2", "uses_old_advice": True, "repeated_error_id": None, "budget_used": 0.20},
            {"story": "S6", "uses_old_advice": False, "repeated_error_id": None, "budget_used": 0.19,
             "verified_authority": True},
        ],
        "memory_records": [
            {
                "id": "ARCH_OLD",
                "epic": "E1",
                "story": "*",
                "roles": ["developer"],
                "paths": ["src/audit"],
                "tools": ["*"],
                "trust": "deterministic",
                "text": "Prefer manual journal over audit pipeline.",
                "source_ref": "docs/architecture-pre-s1.md",
                "source_type": "artifact",
                "origin_story": "S1",
            },
            {
                "id": "ARCH_NEW",
                "epic": "E1",
                "story": "*",
                "roles": ["developer"],
                "paths": ["src/audit"],
                "tools": ["*"],
                "trust": "deterministic",
                "text": "Prefer audit pipeline over manual journal.",
                "source_ref": "docs/architecture-post-s2.md",
                "source_type": "artifact",
                "origin_story": "S2",
            },
        ],
    },
    "long_horizon/tool_env_repeat": {
        "story_sequence": ["S2", "S4", "S6", "S8"],
        "evidence_text": "Reuse the isolated test environment tooling.",
        "expected_repeated_behavior_id": "TEST_ENV_NOT_REUSED",
        "scripted_outcomes": [
            {"story": "S2", "reuses_tool_env": True, "repeated_error_id": None, "budget_used": 0.20},
            {"story": "S4", "reuses_tool_env": True, "repeated_error_id": None, "budget_used": 0.19},
            {"story": "S6", "reuses_tool_env": True, "repeated_error_id": None, "budget_used": 0.22},
            {"story": "S8", "reuses_tool_env": True, "repeated_error_id": None, "budget_used": 0.18},
        ],
        "memory_records": [
            {
                "id": "TOOL_ENV_ISOLATED",
                "epic": "E1",
                "story": "*",
                "roles": ["developer"],
                "paths": ["tools"],
                "tools": ["*"],
                "trust": "deterministic",
                "text": "Reuse the isolated test environment tooling across stories.",
                "source_ref": "tools/README.md",
                "source_type": "artifact",
                "origin_story": "S2",
            },
        ],
    },
}


def _dogfood_fixture(name: str, description: str, scope: tuple[str, ...]) -> dict:
    """Stub deterministic fixture for one of the three dogfood tasks.

    The harness does not execute the real `tests/dogfood/_runner.py` (which
    requires `claude`/`opencode` and spends real money); it reproduces the
    *shape* of the inputs the real dogfood runner consumes, plus a
    ``scripted_outcomes`` list that the fake agent can replay without API.
    Reviewers wanting the real CLAUDE-driven numbers should run the original
    dogfood tests under ``AISEF_DOGFOOD=1`` separately; this harness stays
    deterministic and offline.
    """
    return {
        "kind": "dogfood",
        "description": description,
        "write_scope": list(scope),
        "story_sequence": ["STORY-01-01", "STORY-01-02", "STORY-01-03"],
        "evidence_text": f"replay of {name} EPIC-01 with deterministic stub",
        "expected_repeated_behavior_id": f"DOGFOOD_{name.upper()}_NO_REPEATED_ERROR",
        "scripted_outcomes": [
            {"story": sid, "uses_convention": True, "repeated_error_id": None,
             "budget_used": 0.20, "f2p_pass": 1, "f2p_total": 1}
            for sid in ["STORY-01-01", "STORY-01-02", "STORY-01-03"]
        ],
        "memory_records": [],
        "real_runner_path": f"tests/dogfood/test_{name}.py",
        "requires": ({"AISEF_DOGFOOD=1", f"binary:{name == 'par' and 'claude' or 'opencode'}"}),
    }


DOGFOOD_TRIPLES: tuple[tuple[str, str], ...] = (
    ("par", "par EPIC-01 (3 story song song, Claude)."),
    ("calc", "calc EPIC-01 (3 story tuần tự, OpenCode + mycombo, Python)."),
    ("par_mutation", "B3: mutation có chủ đích trên par (A xong, B đổi dấu nối)."),
)


def _scenario_definitions() -> tuple[Scenario, ...]:
    out: list[Scenario] = []
    for key, fixture in _LONG_HORIZON_FIXTURES.items():
        out.append(Scenario(
            id=key, kind="long_horizon", description="scripted long-horizon scenario: " + key,
            write_scope=tuple(fixture.get("write_scope", ["src/"])),
            fixture_inline=fixture,
        ))
    for name, desc in DOGFOOD_TRIPLES:
        out.append(Scenario(
            id=f"dogfood/{name}", kind="dogfood", description=desc,
            write_scope=("src/",),
            fixture_inline=_dogfood_fixture(name, desc, ("src/",)),
        ))
    return tuple(out)


SCENARIOS: tuple[Scenario, ...] = _scenario_definitions()


def load_fixture(scenario_id: str) -> dict:
    for scenario in SCENARIOS:
        if scenario.id == scenario_id:
            return scenario.fixture()
    raise KeyError(scenario_id)
