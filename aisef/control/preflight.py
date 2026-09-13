"""Check whether a story is executable, **before** calling the model.

A non-executable story is one whose acceptance criteria demand something
the write scope forbids, or demand a verification kind nobody configured.
Without this step the only way to discover it is to run and fail the gate —
measured on e9, two consecutive stories deadlocked this way, eight attempts
with none passing, $20.

The entire module is a **pure function over existing data**. No model calls:
"is this story executable" is a computable question, and asking a model only
adds an error source. The trade-off: every rule here must be conservative —
a false missing report blocks a runnable story, as expensive as missing one.

Each inferred capability carries the **evidence** that triggered it, so the
reader can verify the conclusion rather than trust it.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DEFAULTS, Config
from . import complexity
from .normalize import (
    LOCKFILES,
    MANIFESTS,
    Story,
    effective_write_scope,
    is_lockfile,
)

#: Return code when a story is not executable. Blocks before calling the model.
STORY_NOT_EXECUTABLE = "STORY_NOT_EXECUTABLE"


@dataclass(frozen=True)
class Need:
    """A capability the story needs, with the part of the story that required it."""

    capability: str
    #: Text in the story that gave rise to this need. Without it the conclusion
    #: is not verifiable, and the reader can only trust it.
    evidence: str
    #: How to provision the capability, printed when missing.
    remedy: str = ""
    #: Who must fix it. ``"story"`` = the story itself is defective (criteria
    #: demand what scope forbids) — fixable when splitting stories.
    #: ``"project"`` = project not yet configured — not the story's fault,
    #: and fixable **after** stories are finalized. The distinction matters
    #: because the `stories` gate runs before the mockup phase: demanding a
    #: visual contract there is a chicken-and-egg problem, but demanding it
    #: before calling the model is correct.
    kind: str = "project"

    def line(self) -> str:
        out = f"{self.capability} — {self.evidence}"
        return f"{out}. {self.remedy}" if self.remedy else out

    @property
    def blocks_run(self) -> bool:
        """Does missing this make the story **unrunnable**, or just missing
        acceptance evidence?

        No browser means a UI story cannot build any screen — block. No
        `verify.accessibility` means it can still write code; what is
        missing is acceptance evidence, and the story gate already records
        "unconfigured — does not count as passed", while the pre-deploy
        gate blocks for real. Blocking here too is blocking twice for the
        same thing, and makes the framework unusable from the very first
        UI story.
        """
        if self.capability.startswith("verify."):
            return False
        # Built-in provider still runs without a custom provider configured.
        return self.capability != "code-intelligence"


@dataclass
class Preflight:
    story_id: str
    needs: list[Need] = field(default_factory=list)
    missing: list[Need] = field(default_factory=list)

    @property
    def executable(self) -> bool:
        """Can it run. Missing **acceptance evidence** is not counted here —
        the story gate and pre-deploy gate handle that."""
        return not [m for m in self.missing if m.blocks_run]

    @property
    def complete(self) -> bool:
        """Has both run capabilities and acceptance capabilities."""
        return not self.missing

    @property
    def story_defects(self) -> list[Need]:
        """Missing due to **story** defect — blocks at the `stories` gate."""
        return [m for m in self.missing if m.kind == "story"]

    @property
    def provisioning_gaps(self) -> list[Need]:
        """Missing due to **project** not yet configured — still fixable after
        stories are finalized, so at the `stories` gate only a warning;
        blocks at `readiness` and right before calling the model."""
        return [m for m in self.missing if m.kind != "story"]

    def summary(self) -> str:
        if self.executable:
            return f"{self.story_id}: executable ({len(self.needs)} capabilities)"
        lines = [f"{self.story_id}: {STORY_NOT_EXECUTABLE}"]
        lines += [f"  ✗ {m.line()}" for m in self.missing]
        return "\n".join(lines)


# ------------------------------------------------------------ markers

#: Markers triggering a verification kind. Deliberately narrow: only phrases
#: that specifically name the verification kind, not ones that vaguely
#: reference it. Widen them and every story "needs E2E" and the gate loses
#: all meaning.
_VERIFY_MARKERS: dict[str, tuple[str, ...]] = {
    "verify.e2e": ("e2e", "end-to-end", "đầu-cuối", "đầu cuối", "kịch bản người dùng"),
    "verify.sit": ("tích hợp", "integration test", "kiểm thử tích hợp"),
    "verify.api-contract": ("hợp đồng api", "api contract", "contract test", "openapi"),
    "verify.accessibility": ("trợ năng", "accessibility", "a11y", "wcag", "screen reader"),
    "verify.migration": ("migration", "di trú", "nâng cấp schema", "onupgradeneeded"),
    # "dropped frames", "benchmark", "at scale N" are all performance thresholds
    # without using the word "performance". Measured on e9: AC 3 of STORY-01-04
    # required "benchmark AR-16 confirms threshold ... at this scale" and matched
    # no marker — `readiness` gate was silent, then story deadlocked at review
    # after already spending $10.49.
    "verify.perf": (
        "hiệu năng", "performance", "p95", "p99", "độ trễ", "latency",
        "khung hình", "fps", "bài đo", "benchmark", "ở quy mô",
        "thông lượng", "throughput",
    ),
}

#: Markers that a story touches a security surface. Deliberately wider than
#: the group above: missing a security story is much more expensive than
#: running one extra review.
_SECURITY_MARKERS = (
    "bảo mật", "security", "xác thực", "phân quyền", "auth", "oauth", "jwt",
    "mã hoá", "mã hóa", "encrypt", "crypto", "băm mật khẩu", "hash",
    "bí mật", "secret", "credential", "injection", "xss", "csrf",
    # bare "token" is too broad: "design token" in a design system is a CSS
    # variable, and it appears in nearly every UI story.
    "token phiên", "token xác thực", "access token", "refresh token",
    "bearer", "api token", "session token",
    "sql", "sanitize", "khử trùng", "leo thang đặc quyền",
)

#: Markers that a story needs network during verification.
_NETWORK_MARKERS = (
    "gọi api ngoài", "dịch vụ ngoài", "third-party", "bên thứ ba",
    "tải về từ", "cdn", "webhook", "đồng bộ lên máy chủ",
)

#: Words that turn a network marker into a **prohibition** instead of a need.
_NEGATIONS = ("no ", "not ", "never ", "without ", "must not", "cannot", "n't",
              "khong ", "không ", "cấm ", "cam ")


def _is_forbidden(text: str, marker: str) -> bool:
    """Is this marker part of a requirement that network **not** happen.

    A story whose acceptance criteria read "no third-party resources are
    requested and no outbound network requests are made on load" was reported
    as needing `sandbox.tools_network` **enabled** — the preflight matched the
    words and ignored the sentence, turning a security requirement into a
    demand to weaken the sandbox, and blocking the story as not executable
    (measured 2026-09-09, todo-e2e STORY-01-01). Default is network off, which
    is exactly what such a story wants: nothing to configure.

    Only the clause the marker sits in is examined; a negation three sentences
    earlier says nothing about this one.
    """
    low = text.lower()
    i = low.find(marker.lower())
    if i < 0:
        return False
    start = max(low.rfind(".", 0, i), low.rfind(",", 0, i), low.rfind("\n", 0, i)) + 1
    return any(n in low[start:i] for n in _NEGATIONS)


#: Markers that a story needs cross-module impact analysis.
#: Deliberately **excludes** "full repository scan" markers: in Vietnamese
#: the word is ambiguous between code repository and data store, and on e9
#: it appeared in a sentence *forbidding* full IndexedDB scan — false
#: positive on the very first story containing it.
_IMPACT_MARKERS = (
    "mọi nơi dùng", "tất cả caller", "mọi lời gọi", "mọi nơi gọi",
    "cross-module", "liên module", "phiên bản api", "api version",
    "breaking change", "thay đổi phá vỡ", "mọi module",
)

#: Threshold of root modules the write scope touches to be considered cross-module.
IMPACT_MODULE_THRESHOLD = 3

_BACKTICK = re.compile(r"`([^`\n]{2,80})`")
#: Path: contains `/`, or has a recognized file extension.
_PATHISH = re.compile(r"^[\w.@/-]+$")
#: Real source/config file extensions — not "has a dot means it's a file".
#: Bug 20 (2026-09-05, real plan on e9 copy): `tools.lint`, `Note.text`,
#: `save.done`, `search.clear`, `tags.title`, `migrate.title` in criteria
#: are config keys / properties / i18n keys, misidentified as non-existent
#: files -> 6/21 stories "not executable", stories gate blocked the entire plan.
_EXT = re.compile(
    r"\.(?:tsx?|jsx?|mjs|cjs|py|rb|go|rs|java|kt|swift|json|ya?ml|toml|ini|cfg|md|txt|"
    r"css|scss|less|html?|svg|png|jpe?g|gif|ico|sql|sh|bash|zsh|env|lock|xml|csv|proto|"
    r"graphql|gql|vue|svelte|astro|mdx|wasm|map)$",
    re.IGNORECASE,
)
#: npm/pypi package name: lowercase, has hyphen or scope prefix, no `/`
#: (except scope), no file extension.
_PACKAGEISH = re.compile(r"^(@[a-z0-9][\w.-]*/)?[a-z0-9][a-z0-9._-]*$")

#: Verbs indicating the story must **create or modify** the named entity.
#: Without this, paths in criteria are **constraints**, not deliverables:
#: "files in `src/search/` that import React fail the build" references a
#: directory the story does not own. Measured on e9, the rule without this
#: clause produced false positives on 2/18 stories on the first run.
#: Bug 114: every verb here was Vietnamese except `commit`, so on an
#: English-language project `_ticked_in_mutations` returned nothing and the
#: whole "criteria require a file the story may not write" check was silent —
#: measured on `todo-cli`, where a story's criterion named four
#: `lib/commands/*.js` files outside its write scope and the stories gate said
#: nothing; the guard blocked the writes three attempts later.
_MUTATION = (
    "sinh ra", "tạo ", "tạo,", "ghi ", "ghi,", "cập nhật", "thêm vào",
    "sửa ", "xoá ", "xóa ", "commit", "lưu ", "dựng ", "xuất ra",
    "được tạo", "được ghi", "được sinh", "được lưu", "được commit",
    "create", "creates", "created", "write", "writes", "written",
    "add ", "adds ", "added", "update", "updates", "updated",
    "delete", "deletes", "deleted", "remove", "removes", "removed",
    "generate", "generates", "generated", "save", "saves", "saved",
    "produce", "produces", "produced", "scaffold", "exists with",
    "must exist", "exists as", "structured as",
)


def _text_of(story: Story) -> str:
    return " \n".join([story.title, *story.acceptance_criteria]).lower()


def _ticked(story: Story) -> list[str]:
    return _BACKTICK.findall(" \n".join([story.title, *story.acceptance_criteria]))


#: Maximum distance between identifier and mutation verb to consider them
#: related. A long acceptance criterion often has multiple clauses: scanning
#: the whole sentence lets a verb at the end pull in all paths at the start.
#: Measured on e9: AC 2 of STORY-01-01 names `src/search/` as a **constraint**
#: at the beginning then says "build fails" at the end — 90 characters apart.
MUTATION_WINDOW = 60


def _ticked_in_mutations(story: Story) -> list[str]:
    """Identifiers in backticks that are **near** a mutation verb.

    Mentioning a path does not demand write permission on it: criteria often
    name directories as constraints ("files in `src/search/` that import
    React fail the build") rather than as deliverables the story must create.
    """
    out: list[str] = []
    for cau in [story.title, *story.acceptance_criteria]:
        low = cau.lower()
        moc = [low.find(v) for v in _MUTATION if v in low]
        if not moc:
            continue
        for m in _BACKTICK.finditer(cau):
            if any(abs(m.start() - i) <= MUTATION_WINDOW for i in moc):
                out.append(m.group(1))
    return out


def _within(path: str, scope: str) -> bool:
    p, s = path.strip("/").split("/"), scope.strip("/").split("/")
    return len(p) >= len(s) and p[: len(s)] == s


def _covered(tok: str, scope: list[str]) -> bool:
    """Is this path already within write scope.

    Beyond prefix matching, also accepts **middle segments**: acceptance
    criteria often name a layer (`store/`) while scope declares the full
    path (`src/store/db.ts`). Treating them as different produces a false
    missing report, and a false missing blocks a runnable story — as
    expensive as a miss.
    """
    if any(_within(tok, s) for s in scope):
        return True
    want = [x for x in tok.strip("/").split("/") if x]
    for s in scope:
        have = [x for x in s.strip("/").split("/") if x]
        for i in range(len(have) - len(want) + 1):
            if have[i : i + len(want)] == want:
                return True
    return False


def _first_marker(text: str, markers: tuple[str, ...]) -> str:
    for m in markers:
        if m in text:
            return m
    return ""


# ------------------------------------------------------------ inference


#: Verification kinds tied to a structural marker, not textual.
#: A story with screens **always** requires accessibility and mockup-map:
#: a screen that cannot be used with a keyboard is a broken screen, even
#: if all acceptance criteria are green.
STRUCTURAL_CONTRACT = {
    "screens": ("unit", "e2e", "accessibility", "mockup-map"),
}

#: Verification kinds every story must pass. Deliberately short: a long
#: contract for every story means no kind is taken seriously.
BASE_CONTRACT = ("unit",)


def verification_contract(story: Story) -> list[str]:
    """Verification kinds this story must pass.

    If the story declares them, the declaration is used — the planner knows
    things code cannot infer. Otherwise inferred by code from the same
    markers `required_capabilities` uses, so the two never disagree.
    """
    if story.verification_contract:
        return list(dict.fromkeys(story.verification_contract))

    out = list(BASE_CONTRACT)
    if story.screens:
        out += list(STRUCTURAL_CONTRACT["screens"])
    text = _text_of(story)
    for cap, markers in _VERIFY_MARKERS.items():
        if _first_marker(text, markers):
            out.append(cap.split(".", 1)[1])
    if _first_marker(text, _SECURITY_MARKERS):
        out.append("security")
    return list(dict.fromkeys(out))


def required_capabilities(story: Story, *, project: Path | None = None) -> list[Need]:
    """Capabilities this story needs, inferred from the story's own content.

    Inference sources in order of reliability: structured fields first
    (``screens``, ``write_scope``), then acceptance criteria text. Text is
    the weakest source, so only used with markers that specifically name
    the capability, no guessing.
    """
    text = _text_of(story)
    needs: list[Need] = []

    # 1. UI story: needs browser to build screens, and visual contract to
    #    compare against. This is a structured field, highest certainty.
    for screen in story.screens:
        needs.append(Need(
            "browser", f"story builds screen `{screen}`",
            "configure `app.dev_command` and `app.base_url`",
        ))
        needs.append(Need(
            "mockup-map", f"story builds screen `{screen}`",
            "run `aisef mockup` to produce a design contract for this screen",
        ))

    # 2. Baseline tools: every story is scored by tests and lint. Without
    #    configuration the guard `completion` blocks the agent from finishing
    #    with an instruction it cannot run.
    needs.append(Need("tools.test", "every story is scored by tests",
                      "configure `tools.test`"))
    needs.append(Need("tools.lint", "every story is scored by lint",
                      "configure `tools.lint`"))

    # 3. Verification kinds in the story's contract. Single source so the
    #    gate and contract never disagree.
    khai = bool(story.verification_contract)
    for kind in verification_contract(story):
        if kind == "mockup-map":
            continue  # already counted in item 1 per screen
        vi_sao = (
            "story declares in `verification_contract`" if khai
            else _why_kind(story, kind)
        )
        needs.append(Need(f"verify.{kind}", vi_sao, f"configure `verify.{kind}`"))

    # 5. Network during verification.
    hit = _first_marker(text, _NETWORK_MARKERS)
    if hit and not _is_forbidden(text, hit):
        needs.append(Need("network", f'acceptance criteria mention "{hit}"',
                          "enable `sandbox.tools_network`"))

    # 6. Cross-module impact analysis.
    hit = _first_marker(text, _IMPACT_MARKERS)
    # Only count **root directories**: `vite.config.ts` or `index.html` are
    # config files at the project root, not modules. Counting them would make
    # every project-scaffolding story appear as a cross-module change.
    roots = {
        p.strip("/").split("/")[0]
        for p in story.write_scope
        if not is_lockfile(p) and ("/" in p.strip("/"))
    }
    roots -= set(MANIFESTS)
    if hit:
        needs.append(Need("code-intelligence", f'acceptance criteria mention "{hit}"',
                          "configure `review.impact_provider` — without it the builtin "
            "name-based search runs, but it is much coarser"))
    elif len(roots) >= IMPACT_MODULE_THRESHOLD:
        needs.append(Need(
            "code-intelligence",
            f"write scope touches {len(roots)} root modules: {', '.join(sorted(roots))}",
            "configure `review.impact_provider` — without it the builtin "
            "name-based search runs, but it is much coarser",
        ))

    # 7. Files and packages named in acceptance criteria.
    needs += _needs_from_names(story, project)
    return needs


def _why_kind(story: Story, kind: str) -> str:
    """Why this verification kind is in the contract — names the trigger."""
    if kind in BASE_CONTRACT:
        return "every story must pass"
    if story.screens and kind in STRUCTURAL_CONTRACT["screens"]:
        return f"story builds screen `{story.screens[0]}`"
    text = _text_of(story)
    markers = _VERIFY_MARKERS.get(f"verify.{kind}")
    hit = _first_marker(text, markers) if markers else ""
    if not hit and kind == "security":
        hit = _first_marker(text, _SECURITY_MARKERS)
    return f'acceptance criteria mention "{hit}"' if hit else "inferred from story content"


def _git_bo_qua(project: Path, tokens: list[str]) -> set[str]:
    """Which of these paths `.gitignore` covers — one call, not one per path."""
    duong_dan = [t for t in tokens if _PATHISH.match(t) and ("/" in t or _EXT.search(t))]
    if not duong_dan:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(project), "check-ignore", "--stdin"],
            input="\n".join(duong_dan), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    # exit 1 = nothing matched, which is not an error here.
    if proc.returncode not in (0, 1):
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _needs_from_names(story: Story, project: Path | None) -> list[Need]:
    """Files/packages that acceptance criteria name explicitly but the story
    is not allowed to touch.

    Distinguished by **disk**, not guessing: a path that exists in the
    project means the story may only read it; a path that does not exist
    means the story must create it, so it must be in write scope. Similarly,
    a package name not in the manifest means the story must declare it.
    """
    out: list[Need] = []
    # Compare against **effective** write scope, not the raw declaration:
    # harness auto-adds dependency manifests and lockfiles, so comparing
    # against the raw scope reports an issue that was already patched.
    scope = (
        effective_write_scope(story, project)
        if project is not None
        else list(story.write_scope)
    )
    deps = _declared_deps(project) if project else None

    ticked = _ticked_in_mutations(story)
    bo_qua = _git_bo_qua(project, ticked) if project is not None else set()
    for tok in ticked:
        if not _PATHISH.match(tok):
            continue
        la_duong_dan = "/" in tok or _EXT.search(tok)
        if la_duong_dan:
            if _covered(tok, scope):
                continue
            if tok in bo_qua:
                # A path git ignores never appears as an out-of-scope change,
                # so it cannot need write scope: `./.taskbook.json` is the
                # store the program writes when it runs, not a file the story
                # delivers.
                continue
            if project is not None and _exists_anywhere(project, tok):
                continue  # already exists — story only reads, no write needed
            if project is None:
                continue  # no disk to check against — cannot conclude
            out.append(Need(
                f"write:{tok}",
                f"acceptance criteria require `{tok}`, file does not exist",
                "add it to the story's `write_scope` or fix the criteria",
                kind="story",
            ))
        elif deps is not None and _PACKAGEISH.match(tok) and "-" in tok:
            # Only hyphenated names: single common words (`store`, `rev`) are
            # often backtick-wrapped but are not package names.
            if tok in deps:
                continue
            if not any(m in scope for m in MANIFESTS):
                out.append(Need(
                    "manifest-write",
                    f"acceptance criteria require package `{tok}`, not declared in manifest",
                    "add the manifest file to the story's `write_scope`",
                    kind="story",
                ))
    # A story only needs to report missing manifest **once**.
    seen: set[str] = set()
    needs: list[Need] = []
    for n in out:
        if n.capability in seen:
            continue
        seen.add(n.capability)
        needs.append(n)
    return needs


def _exists_anywhere(project: Path, tok: str) -> bool:
    """Does this file exist anywhere in the project — including other dirs.

    `DESIGN.md` lives in `_bmad-output/`, not at root; checking only one
    location makes the gate conclude the story must create it when it
    already exists.
    """
    if (project / tok).exists():
        return True
    name = tok.rstrip("/").rsplit("/", 1)[-1]
    if not name:
        return False
    for root in (project, project / "_bmad-output", project / "docs", project / "src"):
        if (root / name).exists():
            return True
    return False


def _declared_deps(project: Path) -> set[str] | None:
    """Package names declared by the project. ``None`` if no manifest is
    readable — unreadable means no conclusion, rather than a wrong one."""
    pkg = project / "package.json"
    if pkg.is_file():
        try:
            raw = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        deps: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies",
                    "optionalDependencies"):
            deps |= set((raw.get(key) or {}).keys())
        return deps
    for name in ("pyproject.toml", "requirements.txt", "requirements.in"):
        f = project / name
        if f.is_file():
            try:
                body = f.read_text(encoding="utf-8")
            except OSError:
                return None
            return set(re.findall(r"^\s*[\"']?([A-Za-z0-9][\w.-]*)", body, re.M))
    return None


# ------------------------------------------------------------ comparison


def provisioned(
    project: Path,
    config: Config,
    *,
    contract_screens: set[str] | None = None,
) -> set[str]:
    """Capabilities the project **already** provides. Reads config and disk, no guessing."""
    have: set[str] = set()

    for key in DEFAULTS:
        if key.startswith(("verify.", "tools.")) and str(config.get(key, "")).strip():
            have.add(key)

    # Any recorded waiver is a deliberate human decision, not a blank.
    for waived in str(config.get("verify.waived", "")).split(","):
        w = waived.strip()
        if w:
            have.add(w if w.startswith("verify.") else f"verify.{w}")

    if str(config.get("app.dev_command", "")).strip() and str(
        config.get("app.base_url", "")
    ).strip():
        have.add("browser")

    if config.get("sandbox.tools_network"):
        have.add("network")

    # Unit tests run through `tools.test` — harness runs it every turn and
    # the `completion` guard blocks the agent from finishing when it is red.
    # Requiring `verify.unit` on top means configuring twice for the same
    # thing, and it makes **every** story non-executable.
    if str(config.get("tools.test", "")).strip():
        have.add("verify.unit")

    if str(config.get("review.impact_provider", "")).strip():
        have.add("code-intelligence")

    # Harness's own semantic security review **is** a way to provision this
    # capability. Requiring `verify.security` when it is already enabled
    # means configuring twice for the same thing.
    if config.get("security.semantic_review", True):
        have.add("verify.security")

    if contract_screens is None:
        contract_screens = _contract_screens(project)
    if contract_screens:
        have.add("mockup-map")
        have |= {f"mockup-map:{s}" for s in contract_screens}

    return have


def _contract_screens(project: Path) -> set[str]:
    f = project / "_bmad-output" / "design-contract.json"
    if not f.is_file():
        return set()
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    screens = raw.get("screens") if isinstance(raw, dict) else raw
    if isinstance(screens, dict):
        return set(screens.keys())
    if isinstance(screens, list):
        # Real contract uses key `id`; also accepts `screen_id` for old format.
        # Reading the wrong key makes the gate report missing contract for
        # **every** screen — a widespread false block, far costlier than a miss.
        out = set()
        for s in screens:
            if not isinstance(s, dict):
                continue
            sid = s.get("id") or s.get("screen_id") or ""
            if sid:
                out.add(sid)
        return out
    return set()


def check_story(
    story: Story,
    *,
    project: Path,
    config: Config | None = None,
    have: set[str] | None = None,
    owned: dict[str, str] | None = None,
    done: set[str] | None = None,
    fan_in: int = 0,
) -> Preflight:
    """Is this story executable. Does not call a model.

    ``owned``: screen -> story that builds it first (see ``screen_owners``);
    used to measure story size. If absent, all screens the story touches count.
    ``fan_in``: number of stories depending on this one (see
    ``complexity.fan_in_counts``) — one dimension of the size score.
    ``done``: completed stories — size check is a **pre-coding-agent** gate;
    a story that already passed the gate has no point being split (e9
    STORY-01-04 finished in 8 turns, stories gate blocked the whole plan).
    """
    cfg = config or Config(dict(DEFAULTS))
    got = have if have is not None else provisioned(project, cfg)
    out = Preflight(story.id)
    out.needs = required_capabilities(story, project=project)
    qua_lon = None if (done and story.id in done) else story_size_defect(
        story, project=project, config=cfg, owned=owned, fan_in=fan_in)
    if qua_lon is not None:
        # Added only to `needs`: the loop below sees `size` is not in
        # provisioned capabilities and moves it to `missing`. Adding to both
        # makes the gate print the same error twice — measured on real e9 plan.
        out.needs.append(qua_lon)

    for need in out.needs:
        cap = need.capability
        if cap == "mockup-map":
            screen = need.evidence.split("`")[-2] if "`" in need.evidence else ""
            if f"mockup-map:{screen}" in got or (not screen and "mockup-map" in got):
                continue
            out.missing.append(need)
            continue
        if cap.startswith("write:") or cap == "manifest-write":
            out.missing.append(need)  # inference itself is evidence of missing
            continue
        if cap not in got:
            out.missing.append(need)
    return out


def screen_owners(stories) -> dict[str, str]:
    """Screen -> story that **builds it first** (plan order).

    A later story touching an existing screen (adding a button) does not
    carry that screen's full state count: e9 STORY-01-05 touches `notes-list`
    (11 states, 01-04 already built) and builds `note-editor` (7) — after
    fixing bugs 12/14/15 it finished machine part in 72 turns; carrying 18
    would have blocked it falsely.
    """
    owners: dict[str, str] = {}
    for s in stories:
        for sid in getattr(s, "screens", []) or []:
            owners.setdefault(sid, s.id)
    return owners


def story_size_defect(
    story: Story,
    *,
    project: Path,
    config: Config | None = None,
    owned: dict[str, str] | None = None,
    fan_in: int = 0,
) -> Need | None:
    """Story too large for **one session** — split before entering coding agent.

    Two thresholds; exceeding **either** blocks:

    * `story.max_screen_states` (P2-12, unchanged): screen states the story
      builds first. Measured 2026-09-05 on e9 — STORY-01-04 (builds
      `notes-list`) hit `max_turns` on the first turn and needed 8, $79.67.
    * `story.max_complexity` (ADR-004 R5): composite five-dimension score,
      see `control/complexity.py` — screen dimension alone misses non-UI
      stories that still take 61 turns (e9 01-01, 9 paths, 7 criteria).

    Score and split suggestion are both **deterministic**: same data yields
    same conclusion, and the message includes each component so the reader
    can verify.
    """
    cfg = config or Config(dict(DEFAULTS))
    exp = _experience(project)
    sc = complexity.score_story(story, project=project, experience=exp,
                                owned=owned, fan_in=fan_in)

    states = sc.get("screen_states")
    state_limit = int(cfg["story.max_screen_states"])
    score_limit = float(cfg["story.max_complexity"])
    qua_man = bool(story.screens) and states.count > state_limit
    qua_diem = sc.total > score_limit
    if not (qua_man or qua_diem):
        return None

    ly_do = []
    if qua_man:
        ly_do.append(f"{states.count} screen states ({states.evidence}) "
                     f"exceeds `story.max_screen_states` = {state_limit}")
    if qua_diem:
        ly_do.append(f"size score {sc.explain()} exceeds `story.max_complexity` = {score_limit:g}")
    return Need(
        "size",
        "; ".join(ly_do),
        complexity.split_suggestion(story, sc, experience=exp, owned=owned),
        kind="story",
    )


def _experience(project: Path | None):
    return complexity.read_experience(project)


def check_stories_executable(
    stories: list[Story],
    *,
    project: Path,
    config: Config | None = None,
) -> list[Preflight]:
    """Score all stories. Reads provisioned capabilities once, reuses for all."""
    cfg = config or Config(dict(DEFAULTS))
    got = provisioned(Path(project), cfg)
    owned = screen_owners(stories)
    fan_in = complexity.fan_in_counts(stories)
    done = _done_stories(Path(project))
    return [
        check_story(s, project=Path(project), config=cfg, have=got, owned=owned,
                    done=done, fan_in=fan_in.get(s.id, 0))
        for s in stories
    ]


def _done_stories(project: Path) -> set[str]:
    """Stories already `done`/`verified` per sprint-status — empty if none."""
    from .state import StateStore, StoryStatus

    root = project / "_bmad-output"
    try:
        st = StateStore(root).load()
    except Exception:  # noqa: BLE001 — no state means no one is done
        return set()
    return {sid for sid, r in st.stories.items()
            if r.state in (StoryStatus.DONE, StoryStatus.VERIFIED)}


__all__ = [
    "IMPACT_MODULE_THRESHOLD",
    "LOCKFILES",
    "Need",
    "Preflight",
    "STORY_NOT_EXECUTABLE",
    "check_stories_executable",
    "screen_owners",
    "story_size_defect",
    "check_story",
    "provisioned",
    "required_capabilities",
]
