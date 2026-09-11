"""Configuration and thresholds.

All behaviour-controlling numbers live here, not scattered across the code.
Reason: the right threshold for one project is usually wrong for another —
85% coverage is reasonable for an internal service but low for a shared
library, and ``max_parallel`` depends on both model rate limits and machine
capacity.

Precedence: code defaults -> project ``.ai/config.json`` -> ``AISEF_*``
environment variables.  Closer to the run wins.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_PATH = ".ai/config.json"
ENV_PREFIX = "AISEF_"

#: Defaults.  Keys use dots to group by topic.
DEFAULTS: dict[str, Any] = {
    # quality
    "coverage.min": 0.85,
    "security.block_severities": ["critical", "high"],
    # Semantic security review, runs during the verification phase.
    "security.semantic_review": True,
    # story size — prevents context overflow in a single session
    "story.max_acceptance_criteria": 8,
    "story.max_write_scope_paths": 10,
    # screen states a story must build (P2-12): measured 2026-09-05 on e9,
    # stories with 11 and 18 states both hit max_turns on the first attempt and needed 4-8 attempts
    "story.max_screen_states": 8,
    # composite story complexity score (ADR-004 R5) — screen states + criteria +
    # write scope + fan-in + VERIFIED behaviours touched.  B4 retrospective
    # calibration on 23 real stories (Spearman 0.88 on 10 stories with turn
    # counts): 16 correctly separates the two most expensive stories (e9 01-04
    # 23.5 and 01-05 18.0) from the rest (<=15.5).
    # See ``control/complexity.py`` and ADR-004 section 6 R5.
    "story.max_complexity": 16.0,
    # Character cap for the evidence index slice loaded into the prompt (ADR-004
    # R6).  An index instead of dumping history: agent calls ``aisef evidence
    # <id>`` when it needs details, not pre-loading the entire ledger.
    "context.max_index_chars": 2000,
    # Character cap for the two R4 slots (``preservation``, ``validation``) —
    # VERIFIED behaviours of other stories whose files this story touches, and
    # what must stay green on the candidate.  Only id + verification source, no
    # history: measured on the e9 ledger, STORY-01-07 touches 31 behaviours of
    # 3 stories — dumping all into the prompt exceeds the 15% B5 budget.  The
    # "preservation" gate still checks the **full** list; the cap only trims
    # the printed portion.  1200 not 1500: B5 retrospective on e9 (ADR-004
    # section 6 R4) measured developer +17.5% prompt at 1500 cap — exceeds
    # 15%; trimming ~300 chars brings it to ~15%.
    "context.max_preservation_chars": 1200,
    # Code map around write scope (ADR-005 V7, ``harness/context.py``): file
    # skeletons in scope + 1-hop neighbours + tests mentioning them, loaded for
    # all three roles.  **0 = disabled** until A/B T8 passes (median turns
    # -20% **and** same gate outcome): Aider publishes no measurements for
    # repo map, and the B5 cap is +15% prompt — 2000 chars on a baseline of
    # 11537 is already +17%, so when enabling try 1500 (~+13%).  While disabled
    # the developer can still query via ``aisef ctx``.
    "context.max_repo_map_chars": 0,
    # External command for map rendering (tree-sitter, serena... pluggable,
    # no extra packages): stdin JSON {project, seeds, budget} -> stdout text.
    # Empty = built-in stdlib; broken command falls back to built-in and the
    # slot states it is coarse.
    "context.map_provider": "",
    # Codebase graph provider for brownfield: "auto" (Graphify if available,
    # Basic otherwise), "graphify", "basic".  MCP not enabled by default.
    "context.graph_provider": "auto",
    # Evidence-based epic improvement loops (ADR-004 R3).  HoH runs T=70
    # loops with no stopping condition; here every stopping condition is code
    # and these three numbers are ceilings.  Count by epic from ``loops[]`` in
    # the behaviour ledger — re-running ``aisef improve`` continues from the
    # last loop, not from 0.
    "improve.max_loops": 3,
    # stop when marginal improvement (delta_verified - delta_reopened between
    # two consecutive ``loops[]`` checkpoints) <= 0 for this many consecutive
    # loops: the next loop receives the same gap and context, will produce the
    # same result.
    "improve.flat_loops": 2,
    # total cost ceiling (USD) across loops of one epic; 0 = unlimited.
    # Cost read from evidence of the fix story, not from the client's word.
    "improve.cost_cap_usd": 0.0,
    # orchestration
    "run.max_parallel": 3,
    "run.max_turns": 40,
    "run.timeout_seconds": 1800,
    "run.max_retries": 2,
    # in-flight budget caps (Phase 2/3 wire-up). 0 = unlimited / disabled.
    # Set any non-zero value to engage ``BudgetGuard.reserve(...)`` around
    # every paid client call.  See ``aisef/control/budget.py``.
    "run.cost_cap_usd": 0.0,
    "run.turn_cap": 0,
    "run.wall_clock_cap_seconds": 0.0,
    # Phase 2/3 opt-in: run the unified qualification policy before
    # the first attempt.  Off by default — pending→failed projection in
    # ``run.py`` keeps the policy from rejecting a fresh project.
    "run.qualify_preflight": False,
    # cost
    "cost.warn_multiple": 3.0,
    # verification commands — empty means "not configured", NOT "passing"
    "verify.sit": "",
    "verify.api-contract": "",
    "verify.e2e": "",
    "verify.uat": "",
    "verify.perf": "",
    "verify.security": "",
    "verify.mutation": "",
    "verify.unit": "",
    "verify.accessibility": "",
    "verify.migration": "",
    "verify.sbom": "",
    "verify.image-scan": "",
    #: Explicitly waived types, comma-separated.  Waiving must be a signed
    #: decision, not a consequence of forgetting to configure.
    "verify.waived": "",
    #: Waiver reason (scope, date, signer).  ``pre-deploy`` requires a reason
    #: when ``verify.waived`` is non-empty and records it in
    #: ``pre-deploy-report.json``; waived types show as diamond, never checkmark.
    "verify.waiver_reason": "",
    # Pre-fix baseline (ADR-004 R9): harness runs the test suite at the parent
    # candidate **before** the first developer session, so the "did not break
    # existing tests" gate can compare green test names before/after.  Disable
    # when the test suite is too slow — disabled means the gate item is "not
    # applicable: disabled by config", not passing.
    "verify.baseline": True,
    # Project-level verification (``aisef qa``, ``pre-deploy``, ``improve``)
    # runs in a clean worktree built from the SHA being scored (ADR-005 V6,
    # following Harbor: stop agent env then run verifier separately): shim
    # ``node_modules/.bin/*``, ``conftest.py``, ``pytest.ini`` that are not
    # committed will not reach the verification tree; ``node_modules``/venv are
    # borrowed from the project.  Trade-off: **untracked** files that tests
    # need (``.env.test``, hand-made fixtures) are also missing there — commit
    # them, or disable this key when truly needed; disabled means evidence
    # records ``tree = "agent tree"``, not silent.  Story-level (``run``) keeps
    # its worktree: already frozen and write-scope guard blocks out-of-scope —
    # this key is not read there.
    "verify.clean_tree": True,
    # Nop control (ADR-005 V3): after freezing the candidate, copy story test
    # files (added/modified) into a temporary worktree at the parent SHA then
    # run ``tools.test`` — tests carrying acceptance criteria must be **red or
    # absent** without the story's code.  Disable when test suite is too slow
    # (+1 test run per attempt) — disabled means the gate item "tests actually
    # verify the story" is "not applicable: disabled by config", not passing.
    "verify.nop": True,
    # project application — to open real routes when comparing against mockups
    "app.dev_command": "",
    "app.base_url": "http://localhost:5173",
    "app.ready_timeout_seconds": 60,
    # model routing by role — empty means use the client's default
    "route.developer_model": "",
    "route.reviewer_model": "",
    "route.designer_model": "",
    "route.security_model": "",
    # Impact analysis provider for the reviewer (P0.3).
    "review.impact_provider": "",
    # Include "Available skills" section (router-selected, name + when-to-use)
    # in the story prompt.  Disabled by default until A/B on ``par`` has
    # numbers (ADR-003 section 6).
    "memory.enabled": False,
    "memory.provider": "local",
    "memory.fallback": "none",
    "memory.timeout_seconds": 2,
    "memory.max_chars": 1200,
    "memory.capture": False,
    "skills.offer": False,
    # ADR-003 mechanism B (experimental): inline the highest-scored skill content
    # into the prompt instead of just offering it via the ``Skill`` tool — measure
    # before deciding.
    "skills.inline": False,
    # project commands — empty means auto-detect from files in the project
    "tools.test": "",
    "tools.lint": "",
    "tools.sast": "",
    # sandbox — empty image means auto-select based on the project's stack
    "sandbox.image": "",
    "sandbox.tools_network": False,
    "sandbox.use_docker": True,
    "sandbox.allow_degraded": True,
    # Execution provider (ADR-005 V5): ``docker`` / ``local`` (runs directly,
    # all guarantees UNSUPPORTED — evidence records ``missing``) /
    # ``"module:Class"`` for an external backend with the same contract as
    # ``harness/sandbox.py::ExecutionProvider``.  ``use_docker=false`` is
    # equivalent to ``local``; kept so existing configs still work.
    "sandbox.allow_hosts": [],
    "sandbox.provider": "docker",
    # Pre-deploy gate does **not** accept degradation (verification running
    # outside Docker) unless an explicit reason is declared here; the reason is
    # recorded in ``pre-deploy.json``.  ``run`` still follows
    # ``sandbox.allow_degraded`` as usual.
    "sandbox.pre_deploy_degraded_waiver": "",
    # Host env-var prefixes passed through to the client process, beyond the
    # fixed allowlist (``clients.base.ENV_KEEP``: PATH HOME LANG LC_* TERM TMPDIR
    # SHELL USER LOGNAME SSL_CERT_FILE + ``ANTHROPIC_*`` + ``AISEF_*``).  Default
    # empty (ADR-005 V2): the agent should not hold what it does not need, and
    # what it needs the project declares explicitly — OpenCode's provider reads
    # keys from custom env vars, so declare that prefix; CI authenticating Claude
    # with ``CLAUDE_CODE_OAUTH_TOKEN`` declares that name (a full name is also a
    # prefix).  Measured 2026-09-06 with ``9router/mycombo`` (key lives at
    # ``~/.local/share/opencode/auth.json``, config only reads ``{env:HOME}``):
    # OpenCode runs fully conformant with an empty list.
    "clients.env_allow": [],
}

#: Expected types, to catch config errors early instead of mid-run blowups.
_TYPES: dict[str, type | tuple[type, ...]] = {
    "coverage.min": float,
    "security.block_severities": list,
    "security.semantic_review": bool,
    "story.max_acceptance_criteria": int,
    "story.max_write_scope_paths": int,
    "story.max_screen_states": int,
    "story.max_complexity": float,
    "context.max_index_chars": int,
    "context.max_preservation_chars": int,
    "context.max_repo_map_chars": int,
    "context.map_provider": str,
    "context.graph_provider": str,
    "improve.max_loops": int,
    "improve.flat_loops": int,
    "improve.cost_cap_usd": float,
    "run.max_parallel": int,
    "run.max_turns": int,
    "run.timeout_seconds": int,
    "run.max_retries": int,
    "run.cost_cap_usd": float,
    "run.turn_cap": int,
    "run.wall_clock_cap_seconds": float,
    "run.qualify_preflight": bool,
    "cost.warn_multiple": float,
    "verify.sit": str,
    "verify.api-contract": str,
    "verify.e2e": str,
    "verify.uat": str,
    "verify.perf": str,
    "verify.security": str,
    "verify.mutation": str,
    "verify.unit": str,
    "verify.accessibility": str,
    "verify.migration": str,
    "verify.sbom": str,
    "verify.image-scan": str,
    "verify.waived": str,
    "verify.waiver_reason": str,
    "verify.baseline": bool,
    "verify.clean_tree": bool,
    "verify.nop": bool,
    "app.dev_command": str,
    "app.base_url": str,
    "app.ready_timeout_seconds": int,
    "route.developer_model": str,
    "route.reviewer_model": str,
    "route.designer_model": str,
    "route.security_model": str,
    "review.impact_provider": str,
    "memory.enabled": bool,
    "memory.provider": str,
    "memory.fallback": str,
    "memory.timeout_seconds": int,
    "memory.max_chars": int,
    "memory.capture": bool,
    "skills.offer": bool,
    "skills.inline": bool,
    "tools.test": str,
    "tools.lint": str,
    "tools.sast": str,
    "sandbox.image": str,
    "sandbox.tools_network": bool,
    "sandbox.allow_hosts": list,
    "sandbox.use_docker": bool,
    "sandbox.allow_degraded": bool,
    "sandbox.provider": str,
    "sandbox.pre_deploy_degraded_waiver": str,
    "clients.env_allow": list,
}


#: Retired keys, with reason.  When found in ``.ai/config.json`` they are
#: **warned then ignored**, not errored: old projects must still load.  A knob
#: with no code reading it is an empty promise — same class as "not configured
#: != passing" applied to config.
RETIRED: dict[str, str] = {
    "story.max_context_tokens": (
        "2026-09-05 — chưa từng có mã đọc; thay bằng `prompt_chars` ghi vào "
        "evidence của mỗi lượt gọi model, `aisef status` cảnh báo story vượt "
        "3× trung vị"
    ),
}


class ConfigError(ValueError):
    """Wrong type or out-of-range configuration value."""


def _env_key(key: str) -> str:
    """`run.max_parallel` → `AISEF_RUN_MAX_PARALLEL`."""
    return ENV_PREFIX + key.replace(".", "_").upper()


def _coerce(key: str, raw: str) -> Any:
    """Coerce a string value from an environment variable to the expected type."""
    want = _TYPES.get(key, str)
    try:
        if want is bool:
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if want is int:
            return int(raw)
        if want is float:
            return float(raw)
        if want is list:
            return [p.strip() for p in raw.split(",") if p.strip()]
        return raw
    except ValueError as e:
        raise ConfigError(f"{_env_key(key)}={raw!r} cannot coerce to {want.__name__}") from e


def _validate(values: dict[str, Any]) -> None:
    for key, want in _TYPES.items():
        if key not in values:
            continue
        val = values[key]
        # bool is a subclass of int in Python — do not let True slip into a numeric field
        if want is int and isinstance(val, bool):
            raise ConfigError(f"{key} must be int, got {val!r}")
        if want is float and isinstance(val, int) and not isinstance(val, bool):
            values[key] = float(val)
            continue
        if not isinstance(val, want):
            raise ConfigError(f"{key} must be {want.__name__}, got {type(val).__name__}")

    if values.get("memory.provider", "local") not in ("local", "openviking"):
        raise ConfigError("memory.provider must be local or openviking")
    if values.get("memory.fallback", "none") not in ("none", "local"):
        raise ConfigError("memory.fallback must be none or local")
    if not 1 <= values.get("memory.timeout_seconds", 2) <= 30:
        raise ConfigError("memory.timeout_seconds must be in 1..30")
    if not 0 <= values.get("memory.max_chars", 1200) <= 20000:
        raise ConfigError("memory.max_chars must be in 0..20000")
    if not 0.0 <= values["coverage.min"] <= 1.0:
        raise ConfigError("coverage.min must be in range 0..1")
    for key in ("run.max_parallel", "run.max_turns", "run.timeout_seconds"):
        if values[key] < 1:
            raise ConfigError(f"{key} must be >= 1")
    if values["run.max_retries"] < 0:
        raise ConfigError("run.max_retries must be >= 0")
    for key in ("run.cost_cap_usd", "run.wall_clock_cap_seconds"):
        if values[key] < 0:
            raise ConfigError(f"{key} must be >= 0 (0 = unlimited)")
    if values["run.turn_cap"] < 0:
        raise ConfigError("run.turn_cap must be >= 0 (0 = unlimited)")
    for key in ("improve.max_loops", "improve.flat_loops"):
        if values[key] < 1:
            raise ConfigError(f"{key} must be >= 1")
    if values["context.max_repo_map_chars"] < 0:
        raise ConfigError("context.max_repo_map_chars must be >= 0 (0 = disabled)")
    if values["improve.cost_cap_usd"] < 0:
        raise ConfigError("improve.cost_cap_usd must be >= 0 (0 = unlimited)")
    if values["cost.warn_multiple"] <= 1.0:
        raise ConfigError("cost.warn_multiple must be > 1 for the warning to be meaningful")


@dataclass
class Config:
    values: dict[str, Any]
    source: str = "defaults"

    @classmethod
    def load(cls, project_root: Path | str = ".", *, env: dict[str, str] | None = None) -> Config:
        values = dict(DEFAULTS)
        sources = ["defaults"]

        path = Path(project_root) / CONFIG_PATH
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise ConfigError(f"{path} is not valid JSON: {e}") from e
            retired = sorted(k for k in loaded if k in RETIRED)
            for k in retired:
                print(f"config: `{k}` is retired ({RETIRED[k]}) — remove from {path}",
                      file=sys.stderr)
                loaded.pop(k)
            unknown = sorted(set(loaded) - set(DEFAULTS))
            if unknown:
                raise ConfigError(f"unrecognized keys in {path}: {', '.join(unknown)}")
            values.update(loaded)
            sources.append(Path(path).as_posix())

        environ = os.environ if env is None else env
        overridden = []
        for key in DEFAULTS:
            raw = environ.get(_env_key(key))
            if raw is not None:
                values[key] = _coerce(key, raw)
                overridden.append(key)
        if overridden:
            sources.append(f"env({len(overridden)})")

        _validate(values)
        return cls(values, source=" → ".join(sources))

    def __getitem__(self, key: str) -> Any:
        try:
            return self.values[key]
        except KeyError:
            raise KeyError(f"config key does not exist: {key}") from None

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def __contains__(self, key: object) -> bool:
        """Without this, ``key in config`` falls back to integer-index iteration
        and errors on key "0" — wrong location and hard to trace."""
        return key in self.values

    def overlay(self, overrides: dict[str, object]) -> "Config":
        """Return a new Config with overridden values — used for stack presets."""
        merged = dict(self.values)
        merged.update(overrides)
        return Config(merged, source=self.source)

    def write_template(self, project_root: Path | str = ".") -> Path:
        """Write a config file for the user to customise."""
        path = Path(project_root) / CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.values, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return path
