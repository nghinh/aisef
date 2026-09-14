"""Project closure gate — the evaluator for `docs/PROJECT-CLOSURE-GATE.md`.

The contract is the prose; `docs/closure-gate.json` is the machine form this
module reads. Nothing here decides policy: the six gates, the 27 criteria,
which of them may be waived and what counts as blocking all come from that
file. This module only **reads evidence and says what it found**.

Four properties are the point of the module, each paid for by a defect:

1. **Read-only.** It never launches an agent, never runs a paid workload,
   never modifies a corpus, and never approves anything. Evidence that costs
   money or a network round-trip (the published wheel, a full suite run) is
   *recorded* by whoever ran it under `closure-evidence/` and read back here.
2. **No criterion is satisfied by its own absence** (bug 154). Missing
   evidence is `UNRUNNABLE`, which blocks; never a skip, never a silent pass.
3. **`UNCONFIGURED` is promoted to `UNRUNNABLE`.** `UNCONFIGURED.blocks` is
   `False` for story gates and that is right there — a project need not
   configure every verification kind. At closure it would let an unconfigured
   check read as absolution.
4. **Waivers are signed and reasoned**, and only for the criteria the contract
   marks `waiver_eligible`. A waiver without a reason is not evidence.

Evidence recorded by other runs lives in `closure-evidence/` and is read, never
written, by the probes:

| file | criteria | shape |
|---|---|---|
| `release.json` | G1.1–G1.4 | `{"ci": {...}, "package": {...}, "pypi_install": {...}, "packaged_data": {...}}` |
| `suite.json` | G2.1 | `{"passed": n, "skipped": n, "failed": n, "tree": "main", "commit": sha}` |
| `lint.json` | G2.2 | `{"tool": "ruff", "exit": 0, "commit": sha}` |
| `judge-only-audit.json` | G2.4b | `{"G2.4b-i".."iv": {"holds": bool, "evidence": str}, "judge_alone_blocks": n, "blocks_total": n}` |
| `bench-selfcheck.json` | G5.4 | `{"passed": n, "total": n, "commit": sha}` |
| `onboarding-digest.json` | G6.1 | `{"sha256": ..., "version": "1.6.0"}` |

The evaluator writes exactly two files, both outputs: the machine report
`closure-evidence/closure-report.json` and, on `--report`, `docs/CLOSURE-REPORT.md`.
`closure-evidence/closure-state.json` holds the signed waivers and the owner's
approval.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..clients.stream import INFRA_STATUSES
from ..config import DEFAULTS
from ..harness.observe import TOOL_RUN, EvidenceStore
from .approvals import (
    GATE_ORDER,
    PRE_DEPLOY_REPORT,
    ApprovalStore,
    Gate,
    Status,
    _current_user,
    _now,
    sha256_of,
)
from .gate import Outcome, _stale_candidates
from .gate import CHECK_KIND
from .outcome import CHECK_KINDS
from .state import StateStore, StoryStatus
from .worktree import GitError, _git, main_repo

#: Criteria file — the machine form of the contract.
CRITERIA_PATH = "docs/closure-gate.json"

#: Where evidence that cannot be re-derived from the source tree is recorded,
#: and where the machine report and the signed state are written.
EVIDENCE_DIR = "closure-evidence"
REPORT_JSON = f"{EVIDENCE_DIR}/closure-report.json"
STATE_JSON = f"{EVIDENCE_DIR}/closure-state.json"

#: Human report. `docs/` is where this repository already keeps generated
#: evidence documents a person reads (`docs/CONFORMANCE.md`); the framework
#: repo is not itself an aisef project, so it has no `_bmad-output/`.
REPORT_MD = "docs/CLOSURE-REPORT.md"

#: Artifact root inside a corpus — the corpus *is* an aisef project.
ARTIFACT_ROOT = "_bmad-output"

#: Check kinds where a false PASS is a defect rather than a published property
#: (§5 G2.4). Values are from `outcome.CHECK_KINDS`, asserted by the tests.
HARD_KINDS = ("deterministic", "structural")

#: Runtime package data that must ship inside the wheel (§5 G1.4).
PACKAGED_DATA = ("kit/prompts", "kit/rules", "kit/skills", "kit/catalog.json", "harness/assets")

#: Honesty markers for G5.5 — a bench report either states the noise band or
#: states that the corpus cannot resolve one. Both languages, because the
#: reports are written in both.
NOISE_MARKERS = ("inconclusive", "không kết luận", "chưa kết luận", "noise", "nhiễu", "±")

#: Statuses that close a finding in the external-validation record (G6.3).
RESOLVED = ("resolved", "fixed", "closed", "waived", "đã sửa", "đã xử lý")


# --------------------------------------------------------------- plumbing


def _ref(spec: str):
    """Resolve a ``module:attribute`` reference — the form the criteria file
    uses for probes and for `MAX_AGE_DAYS`."""
    mod, _, attr = spec.partition(":")
    return getattr(importlib.import_module(mod), attr)


def _git_out(repo: Path, *args: str) -> str:
    """Read-only git, empty string on any failure. The only subprocess this
    module ever reaches, and it goes through the existing helper."""
    try:
        proc = _git(repo, *args, check=False)
    except (OSError, GitError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _norm(text: str) -> str:
    """Whitespace-collapsed content — prose reflow must not change a digest."""
    return " ".join(text.split())


@dataclass
class Probed:
    """What a probe found. `evidence`/`digest` default to what the probe
    actually read (`Ctx.seen`); a probe sets them only when the binding is
    something else — a corpus HEAD, an approval hash."""

    outcome: Outcome
    detail: str = ""
    evidence: str = ""
    digest: str = ""


@dataclass
class Ctx:
    """One criterion being evaluated. Reads go through `read`/`read_json` so
    the report can name the exact evidence and its digest."""

    root: Path
    spec: dict
    criterion: dict = field(default_factory=dict)
    corpus_arg: str = ""
    seen: list[Path] = field(default_factory=list)

    def path(self, rel: str | Path) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    def read(self, rel: str | Path) -> str | None:
        p = self.path(rel)
        self.seen.append(p)
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def read_json(self, rel: str | Path) -> dict | None:
        text = self.read(rel)
        if text is None:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def evidence(self) -> str:
        """Paths actually read, relative to the root where possible."""
        out = []
        for p in self.seen:
            try:
                out.append(str(p.relative_to(self.root)))
            except ValueError:
                out.append(str(p))
        return ", ".join(dict.fromkeys(out))

    def digest(self) -> str:
        """Digest of the evidence read. One file: its own hash — readable in
        the report. Several: hashed as a set, the way `ApprovalStore` binds a
        multi-file gate."""
        if not self.seen:
            return ""
        if len(self.seen) == 1:
            return sha256_of(self.seen[0])
        parts = [f"{p.name}:{sha256_of(p)}" for p in self.seen]
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()

    @property
    def head(self) -> str:
        return _git_out(self.root, "rev-parse", "HEAD")

    def corpus_spec(self) -> dict:
        for gate in self.spec.get("gates") or []:
            if isinstance(gate.get("corpus"), dict):
                return gate["corpus"]
        return {}

    def corpus(self) -> tuple[Path | None, str]:
        """The **primary** corpus, resolved by path (R2), or why not.

        A missing primary is never replaced by the fallback: substitution is a
        named R1 decision the owner approves (ruling 2), not something an
        evaluator does because a directory was easier to find.
        """
        spec = self.corpus_spec()
        name = str(spec.get("primary") or "")
        if self.corpus_arg:
            p = Path(self.corpus_arg).expanduser().resolve()
        elif name:
            p = main_repo(self.root).parent / name
        else:
            return None, "criteria file declares no primary corpus"
        if not (p / ARTIFACT_ROOT).is_dir():
            fb = spec.get("fallback") or "—"
            return None, (f"primary corpus `{name}` not resolvable: no {p / ARTIFACT_ROOT} "
                          f"(fallback `{fb}` is NOT substituted — owner ruling 2)")
        return p, ""

    def artifacts(self) -> tuple[Path | None, str]:
        corpus, why = self.corpus()
        return (None, why) if corpus is None else (corpus / ARTIFACT_ROOT, "")


def _missing(what: str) -> Probed:
    """Evidence that does not exist. UNRUNNABLE blocks — "could not check" is
    never "it is fine" (§5 G1)."""
    return Probed(Outcome.UNRUNNABLE, f"missing: {what}")


def _only_bookkeeping_changed(ctx: Ctx, at: str) -> bool:
    """True when every file changed between ``at`` and HEAD is closure bookkeeping.

    Lỗi 162. Bằng chứng buộc vào `commit` mà **chính nó** được git theo dõi thì
    không bao giờ hiện hành được: ghi ở commit X, rồi commit tệp bằng chứng làm
    HEAD đi qua X, nên phép so `== HEAD` cũ ngay lập tức; còn không commit thì
    cây bẩn và `pin_target` từ chối. "G2.1 xanh" và "chốt được
    `closure_target_sha`" loại trừ nhau — một vòng không lối ra mà máy đóng gate
    tự tạo cho mình, đo trên chính kho này 2026-09-14.

    Câu probe **thật sự** hỏi là "bằng chứng này có tả đúng **mã nguồn** hiện tại
    không". Một commit chỉ đụng `closure-evidence/` không đổi một dòng mã nào,
    nên câu trả lời vẫn là có. Nới đúng chừng ấy: một tệp nào **ngoài** thư mục
    ấy đổi thì bằng chứng cũ, như trước.

    Tệp tiêu chí (`docs/closure-gate.json`) cùng lớp, và vì cùng lý do: chốt
    `closure_target_sha` ghi vào nó, nên commit bản ghim làm HEAD đi qua đúng
    commit vừa chốt và vế *HEAD vẫn là đích* của G1.0 hỏng ngay sau khi chốt —
    anh em của cùng một lỗi, chỉ đổi tệp. Sổ sách đóng dự án không phải mã nguồn.

    Không đọc được danh sách thay đổi → `False`: không biết thì coi là cũ.
    """
    changed = _git_out(ctx.root, "diff", "--name-only", f"{at}..HEAD")
    names = [ln.strip() for ln in changed.splitlines() if ln.strip()]
    return bool(names) and all(
        n.startswith(f"{EVIDENCE_DIR}/") or n == CRITERIA_PATH for n in names)


def _at_commit(ctx: Ctx, rec: dict, field_name: str = "commit") -> Probed | None:
    """Freshness ``bound_to: commit``. Evidence recorded at another commit does
    not describe this one, and "cannot tell" is UNRUNNABLE, not a pass."""
    head = ctx.head
    at = str(rec.get(field_name) or "")
    if not head:
        return Probed(Outcome.UNRUNNABLE, "cannot read git HEAD here")
    if not at:
        return Probed(Outcome.UNRUNNABLE, f"record names no `{field_name}`")
    if not (head.startswith(at) or at.startswith(head)):
        if _only_bookkeeping_changed(ctx, at):
            return None
        return Probed(Outcome.UNRUNNABLE,
                      f"recorded at {at[:7]}, HEAD is {head[:7]} — re-run and re-record")
    return None


def _release(ctx: Ctx, key: str) -> tuple[dict, Probed | None]:
    """G1 reads one record: the published artifact cannot be inspected from the
    source tree, and the evaluator does not build, install or reach the network."""
    rel = f"{EVIDENCE_DIR}/release.json"
    data = ctx.read_json(rel)
    if data is None:
        return {}, _missing(f"{rel} — no recorded verification of the published artifact")
    part = data.get(key)
    if not isinstance(part, dict):
        return {}, _missing(f"{rel}#{key}")
    return part, None


def _md_table(text: str, header_has: str) -> tuple[list[str], list[list[str]]]:
    """First markdown table whose header row mentions `header_has`."""
    head: list[str] = []
    rows: list[list[str]] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw.startswith("|"):
            if head:
                break
            continue
        cells = [c.strip() for c in raw.strip("|").split("|")]
        if not head:
            if header_has.lower() in raw.lower():
                head = [c.lower() for c in cells]
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return head, rows


def _cell(head: list[str], row: list[str], name: str) -> str:
    for i, h in enumerate(head):
        if name in h and i < len(row):
            return row[i]
    return ""


# ------------------------------------------------------- G1 release integrity


def probe_ci_green(ctx: Ctx) -> Probed:
    """G1.1 — CI green on the commit the released tag points at.

    The record is not taken at its word: the tag is resolved locally and the
    commits compared, so a green run on some other commit cannot pass here.
    """
    rec, err = _release(ctx, "ci")
    if err:
        return err
    tag, sha = str(rec.get("tag") or ""), str(rec.get("commit") or "")
    if not tag or not sha:
        return Probed(Outcome.UNRUNNABLE, "record names no tag/commit for the CI run")
    at_tag = _git_out(ctx.root, "rev-list", "-n", "1", tag)
    if not at_tag:
        return Probed(Outcome.UNRUNNABLE, f"tag {tag} is unknown to git in this checkout")
    if not (at_tag.startswith(sha) or sha.startswith(at_tag)):
        return Probed(Outcome.FAILED,
                      f"CI ran on {sha[:7]}, but {tag} points at {at_tag[:7]}")
    if str(rec.get("conclusion") or "") != "success":
        return Probed(Outcome.FAILED,
                      f"{rec.get('workflow') or 'workflow'} on {tag}: {rec.get('conclusion') or 'no conclusion'}")
    return Probed(Outcome.PASSED,
                  f"{rec.get('workflow') or 'workflow'} success on {tag} ({at_tag[:7]})")


def probe_package_checks(ctx: Ctx) -> Probed:
    """G1.2 — wheel and sdist build, and `twine check` passes both."""
    rec, err = _release(ctx, "package")
    if err:
        return err
    stale = _at_commit(ctx, rec)
    if stale:
        return stale
    bad = [k for k in ("build_exit", "twine_exit") if rec.get(k) is None]
    if bad:
        return _missing(f"{EVIDENCE_DIR}/release.json#package.{', '.join(bad)}")
    if int(rec["build_exit"]) or int(rec["twine_exit"]):
        return Probed(Outcome.FAILED,
                      f"build exit {rec['build_exit']}, twine exit {rec['twine_exit']}")
    return Probed(Outcome.PASSED, "python -m build and twine check both exit 0")


def probe_pypi_install(ctx: Ctx) -> Probed:
    """G1.3 — a clean venv install from PyPI serves the released version."""
    rec, err = _release(ctx, "pypi_install")
    if err:
        return err
    want = _version(ctx.root)
    if not want:
        return Probed(Outcome.UNRUNNABLE, "cannot read the released version from pyproject.toml")
    got = str(rec.get("version_reported") or "")
    if not got:
        return _missing(f"{EVIDENCE_DIR}/release.json#pypi_install.version_reported")
    if got != want:
        return Probed(Outcome.FAILED, f"clean venv reported {got}, this tree is {want}")
    return Probed(Outcome.PASSED, f"clean venv install reported aisef {got}")


def probe_packaged_data(ctx: Ctx) -> Probed:
    """G1.4 — runtime package data ships inside the wheel and is non-empty."""
    rec, err = _release(ctx, "packaged_data")
    if err:
        return err
    absent = [name for name in PACKAGED_DATA if name not in rec]
    if absent:
        return _missing(f"{EVIDENCE_DIR}/release.json#packaged_data: {', '.join(absent)}")
    empty = [name for name in PACKAGED_DATA if not int(rec.get(name) or 0)]
    if empty:
        return Probed(Outcome.FAILED, f"empty in the wheel: {', '.join(empty)}")
    return Probed(Outcome.PASSED,
                  "in the wheel: " + ", ".join(f"{n} {rec[n]}" for n in PACKAGED_DATA))


def _version(root: Path) -> str:
    """Released version — from `pyproject.toml`, the one place that says it."""
    import tomllib

    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str((data.get("project") or {}).get("version") or "")


# ------------------------------------------------------- G2 core correctness


def probe_suite_green(ctx: Ctx) -> Probed:
    """G2.1 — the full suite is green, run from the MAIN checkout.

    A git worktree skips ~61 more tests than the main tree, because
    `.gitignore` excludes `references/*`, `.bench*/`, `.conformance/` and
    `.dogfood/`: main 2682 passed / 19 skipped, worktree ~2608 / ~80. A count
    taken in a worktree is not comparable and "skipped" is indistinguishable
    from "passed" in pytest's summary line, so the probe refuses to grade one
    and records the skip count and the tree the run used.
    """
    root = ctx.root.resolve()
    main = main_repo(root)
    if main != root:
        return Probed(Outcome.UNRUNNABLE,
                      f"not the main checkout ({root}) — a worktree skips ~61 more tests; "
                      f"the comparable tree is {main}")
    rec = ctx.read_json(f"{EVIDENCE_DIR}/suite.json")
    if rec is None:
        return _missing(f"{EVIDENCE_DIR}/suite.json — no recorded suite run")
    stale = _at_commit(ctx, rec)
    if stale:
        return stale
    tree = str(rec.get("tree") or "")
    if tree != "main":
        return Probed(Outcome.UNRUNNABLE,
                      f"recorded run was in tree={tree or '?'} — only a main-checkout run is comparable")
    passed, skipped = int(rec.get("passed") or 0), int(rec.get("skipped") or 0)
    bad = int(rec.get("failed") or 0) + int(rec.get("errors") or 0)
    if not passed:
        return Probed(Outcome.UNRUNNABLE, "record carries no passed count")
    if bad:
        return Probed(Outcome.FAILED, f"{bad} failed/errored · {passed} passed · {skipped} skipped")
    return Probed(Outcome.PASSED, f"{passed} passed · {skipped} skipped · tree={tree}")


def probe_lint_clean(ctx: Ctx) -> Probed:
    """G2.2 — the lint gate is clean under the rule set in `pyproject.toml`."""
    rec = ctx.read_json(f"{EVIDENCE_DIR}/lint.json")
    if rec is None:
        return _missing(f"{EVIDENCE_DIR}/lint.json — no recorded lint run")
    stale = _at_commit(ctx, rec)
    if stale:
        return stale
    if rec.get("exit") is None:
        return _missing(f"{EVIDENCE_DIR}/lint.json#exit")
    if int(rec["exit"]):
        return Probed(Outcome.FAILED,
                      f"{rec.get('tool') or 'lint'} exit {rec['exit']}: {rec.get('detail') or 'not clean'}")
    return Probed(Outcome.PASSED, f"{rec.get('tool') or 'lint'} clean")


def _register(ctx: Ctx) -> tuple[list[dict], Probed | None]:
    reg = ctx.read_json("docs/DEFECT-REGISTER.json")
    if reg is None:
        return [], _missing("docs/DEFECT-REGISTER.json — the canonical open-defect "
                            "register (owner ruling 6: repository-local, not an external tracker)")
    entries = reg.get("defects")
    if not isinstance(entries, list):
        return [], Probed(Outcome.UNRUNNABLE, "register has no `defects` list")
    return [e for e in entries if isinstance(e, dict)], None


def _open_entries(entries: list[dict]) -> tuple[list[dict], list[str]]:
    """Open entries, and the ids whose status cannot be read. An entry with no
    status is not "closed" — it is unreadable, and that is said out loud."""
    open_, unknown = [], []
    for e in entries:
        status = str(e.get("status") or "").strip().upper()
        if not status:
            unknown.append(str(e.get("id") or "?"))
        elif status == "OPEN":
            open_.append(e)
    return open_, unknown


def probe_defect_register(ctx: Ctx) -> Probed:
    """G2.3 — zero OPEN P0/P1 defects in the canonical register.

    An empty register is a real PASS; a missing register is not (bug 154).
    Blocking severities are read from the criteria file, which points at the
    protocol's own P0–P3 ladder rather than defining a second one.
    """
    entries, err = _register(ctx)
    if err:
        return err
    blocking = tuple(str(s).upper() for s in
                     (ctx.spec.get("severity_scale") or {}).get("blocking") or ())
    if not blocking:
        return Probed(Outcome.UNRUNNABLE, "criteria file declares no blocking severities")
    open_, unknown = _open_entries(entries)
    if unknown:
        return Probed(Outcome.UNRUNNABLE,
                      f"{len(unknown)} entries carry no status: {', '.join(unknown[:5])}")
    hit = [e for e in open_ if str(e.get("severity") or "").upper() in blocking]
    if hit:
        return Probed(Outcome.FAILED,
                      f"{len(hit)} open {'/'.join(blocking)}: "
                      + ", ".join(str(e.get("id") or "?") for e in hit[:5]))
    return Probed(Outcome.PASSED,
                  f"0 open {'/'.join(blocking)} of {len(entries)} registered defects")


def probe_deterministic_false_pass(ctx: Ctx) -> Probed:
    """G2.4a — no known false PASS in a deterministic or structural blocking check.

    The register must classify what it records: an entry needs `false_pass`
    (bool) and `check_kind` (one of `outcome.CHECK_KINDS`). A register that
    classifies nothing cannot answer this question, and the absence of the
    field is not evidence of the absence of the defect — so that is
    UNRUNNABLE, not a pass.
    """
    entries, err = _register(ctx)
    if err:
        return err
    open_, unknown = _open_entries(entries)
    if unknown:
        return Probed(Outcome.UNRUNNABLE,
                      f"{len(unknown)} entries carry no status: {', '.join(unknown[:5])}")
    if entries and not any("false_pass" in e for e in entries):
        return Probed(Outcome.UNRUNNABLE,
                      "register carries no `false_pass`/`check_kind` classification — "
                      "G2.4a cannot be read from it")
    lech = [f"{e.get('id') or '?'}: `{e.get('check')}` is "
            f"{CHECK_KIND[str(e.get('check'))]}, register says "
            f"{e.get('check_kind')}"
            for e in open_
            if e.get("false_pass") and str(e.get("check")) in CHECK_KIND
            and e.get("check_kind")
            and str(e.get("check_kind")) != CHECK_KIND[str(e.get("check"))]]
    if lech:
        return Probed(Outcome.UNRUNNABLE,
                      "register contradicts `gate.CHECK_KIND` on "
                      + "; ".join(lech[:5])
                      + " — a structural false PASS declared `model-judge` is "
                        "exactly how one would walk past G2.4a, so the two "
                        "disagreeing means neither can be trusted here")
    bad_kind = [f"{e.get('id') or '?'}={_kind_of(e) or 'none'}" for e in open_
                if e.get("false_pass") and _kind_of(e) not in CHECK_KINDS]
    if bad_kind:
        return Probed(Outcome.UNRUNNABLE,
                      f"unknown check_kind on {', '.join(bad_kind[:5])} — "
                      f"expected one of {', '.join(CHECK_KINDS)}, or a `check` "
                      f"naming one of the gate's own checks")
    hit = [str(e.get("id") or "?") for e in open_
           if e.get("false_pass") and _kind_of(e) in HARD_KINDS]
    if hit:
        return Probed(Outcome.FAILED,
                      f"{len(hit)} open false PASS in a {'/'.join(HARD_KINDS)} check: "
                      + ", ".join(hit[:5]))
    return Probed(Outcome.PASSED,
                  f"no open false PASS in a {'/'.join(HARD_KINDS)} check "
                  f"({len(entries)} registered defects)")


def _kind_of(entry: dict) -> str:
    """Loại của mục cổng mà một khiếm khuyết nói về — **suy ra** trước, khai sau.

    `gate.CHECK_KIND` là nguồn duy nhất phân loại ai chấm mỗi mục, nên khi mục
    ghi `check` là tên một mục cổng thật thì câu trả lời đã có sẵn và việc bắt
    người ghi tay thêm `check_kind` chỉ mở một đường lách: khai `model-judge`
    cho một mục **cấu trúc** là cách hợp lệ hoá đúng cái PASS giả mà G2.4a hỏi
    về. Lời khai chỉ dùng khi `check` không phải mục cổng nào — khiếm khuyết
    ngoài cổng vẫn có thật.
    """
    ten = str(entry.get("check") or "")
    if ten in CHECK_KIND:
        return CHECK_KIND[ten]
    return str(entry.get("check_kind") or "")


#: The four properties of §5 G2.4b, in the contract's own numbering.
JUDGE_PROPERTIES = ("G2.4b-i", "G2.4b-ii", "G2.4b-iii", "G2.4b-iv")


def probe_judge_only_semantics(ctx: Ctx) -> Probed:
    """G2.4b — a judge-only block is identifiable, distinguishable, overridable,
    and cannot masquerade as deterministic.

    The measured rate stays published and recomputable from evidence on disk,
    so the audit must carry the counts, not only four booleans.
    """
    rel = f"{EVIDENCE_DIR}/judge-only-audit.json"
    rec = ctx.read_json(rel)
    if rec is None:
        return _missing(f"{rel} — the G2.4b-i..iv audit ({', '.join(JUDGE_PROPERTIES)})")
    # `reviewer_qual.judge_only_audit` nests the four properties under
    # `properties` and the counters under `measured`. Chấp nhận cả dạng phẳng:
    # hai hình dạng cùng một sự thật thì đọc cả hai, đừng bắt bên sinh dẹt đi —
    # bản lồng còn mang `assertions` và **hai** mẫu số, thứ bản phẳng đánh mất.
    props = rec.get("properties") if isinstance(rec.get("properties"), dict) else rec
    absent = [p for p in JUDGE_PROPERTIES if not isinstance(props.get(p), dict)]
    if absent:
        return _missing(f"{rel}: {', '.join(absent)}")
    measured = rec.get("measured") if isinstance(rec.get("measured"), dict) else {}
    alone = rec.get("judge_alone_blocks", measured.get("judge_only_records"))
    total = rec.get("blocks_total", measured.get("blocking_records"))
    if alone is None or total is None:
        return _missing(f"{rel}: judge_alone_blocks/blocks_total (or measured."
                        f"judge_only_records/blocking_records) — the rate must stay published")
    broken = [p for p in JUDGE_PROPERTIES if not props[p].get("holds")]
    alone, total = int(alone), int(total) or 1
    rate = f"{alone}/{total} blocks judge-alone ({100 * alone / total:.1f}%)"
    if broken:
        return Probed(Outcome.FAILED, f"{', '.join(broken)} does not hold · {rate}")
    return Probed(Outcome.PASSED, f"{', '.join(JUDGE_PROPERTIES)} hold · {rate}")


# ----------------------------------------------------- G3 client conformance


def probe_conformance(ctx: Ctx) -> Probed:
    """G3.1 — every first-class client has a complete, passing column.

    Read through `conformance.release_ready`, the same reader the release gate
    uses, with `MAX_AGE_DAYS` taken from the module named by the criteria file
    rather than a second number that could drift from it. The clients the
    policy actually checks are printed, so a policy narrower than ADR-006 §4 is
    visible in the report instead of hidden inside a PASS.
    """
    from . import conformance as C

    text = ctx.read(C.REPORT_PATH)
    if text is None:
        return _missing(f"{C.REPORT_PATH} — no conformance table")
    fresh = ctx.criterion.get("freshness") or {}
    max_age = _ref(str(fresh.get("max_from") or "aisef.control.conformance:MAX_AGE_DAYS"))
    rep = C.parse(text)
    ok, why = C.release_ready(rep, max_age_days=max_age)
    policy = "release policy reads " + ", ".join(C.RELEASE_CLIENTS)
    left = ""
    try:
        left = f" · {max_age - (date.today() - date.fromisoformat(rep.generated)).days}d left of {max_age}d"
    except ValueError:
        pass
    return Probed(Outcome.PASSED if ok else Outcome.FAILED, f"{why} · {policy}{left}")


# -------------------------------------------------- G4 real end-to-end delivery


def probe_corpus_present(ctx: Ctx) -> Probed:
    """G4.1 — the corpus is resolvable by path (R2) and has an artifact root."""
    corpus, why = ctx.corpus()
    if corpus is None:
        return Probed(Outcome.UNRUNNABLE, why)
    head = _git_out(corpus, "rev-parse", "HEAD")
    return Probed(Outcome.PASSED, f"{corpus} · {ARTIFACT_ROOT} present · HEAD {head[:7] or '?'}",
                  evidence=str(corpus / ARTIFACT_ROOT), digest=head)


def probe_upstream_gates(ctx: Ctx) -> Probed:
    """G4.2 — every upstream human gate is APPROVED and not STALE.

    `ApprovalStore.status` recomputes from on-disk content, so a gate approved
    against an artifact that has since changed reads STALE without anyone
    marking it.
    """
    art, why = ctx.artifacts()
    if art is None:
        return Probed(Outcome.UNRUNNABLE, why)
    store = ApprovalStore(art)
    bad = [(g.value, store.status(g).value) for g in GATE_ORDER[:-1]
           if store.status(g) is not Status.APPROVED]
    digest = hashlib.sha256(
        "\n".join(f"{g.value}:{store.content_hash(g)}" for g in GATE_ORDER[:-1]).encode()).hexdigest()
    if bad:
        return Probed(Outcome.FAILED,
                      "not approved: " + ", ".join(f"{g} ({s})" for g, s in bad),
                      evidence=str(store.dir), digest=digest)
    return Probed(Outcome.PASSED, f"{len(GATE_ORDER) - 1} upstream gates approved, none stale",
                  evidence=str(store.dir), digest=digest)


def _corpus_stories(art: Path) -> tuple[list[str], list[str]]:
    """Registered stories and planned-but-never-registered ones. A story that
    was never registered is not "done" (`deploy._planned_but_never_run`)."""
    from ..phases.deploy import _planned_but_never_run

    state = StateStore(art).load()
    never = _planned_but_never_run(art, set(state.stories))
    return sorted(state.stories), sorted(never)


def probe_stories_done(ctx: Ctx) -> Probed:
    """G4.3 — every planned story reached done, and none was never run.

    Same rule as the pre-deploy gate: `verified` means gate-passed but unmerged,
    which is not deployed; and a story in the plan with no state record at all
    is not done, it never ran (e9 2026-09-05).
    """
    art, why = ctx.artifacts()
    if art is None:
        return Probed(Outcome.UNRUNNABLE, why)
    state = StateStore(art).load()
    registered, never = _corpus_stories(art)
    if not registered and not never:
        return Probed(Outcome.UNRUNNABLE, "no stories in the corpus plan or state")
    unmerged = [r.id for r in state.stories.values() if r.state is StoryStatus.VERIFIED]
    not_done = [r.id for r in state.stories.values()
                if r.state not in (StoryStatus.DONE, StoryStatus.VERIFIED)]
    corpus = art.parent
    digest = _git_out(corpus, "rev-parse", "HEAD")
    if not_done or never or unmerged:
        parts = []
        if not_done:
            parts.append(f"{len(not_done)} not done: {', '.join(sorted(not_done)[:5])}")
        if never:
            parts.append(f"{len(never)} never run: {', '.join(never[:5])}")
        if unmerged:
            parts.append(f"{len(unmerged)} done but not merged: {', '.join(sorted(unmerged)[:5])}")
        return Probed(Outcome.FAILED, " · ".join(parts), digest=digest)
    return Probed(Outcome.PASSED, f"{len(registered)} stories done and merged", digest=digest)


def probe_review_and_security(ctx: Ctx) -> Probed:
    """G4.4 — independent review **and** security ran for every story."""
    art, why = ctx.artifacts()
    if art is None:
        return Probed(Outcome.UNRUNNABLE, why)
    registered, never = _corpus_stories(art)
    stories = sorted(set(registered) | set(never))
    if not stories:
        return Probed(Outcome.UNRUNNABLE, "no stories in the corpus plan or state")
    store = EvidenceStore(art)
    gaps = [f"{sid}:{name}" for sid in stories
            for name in ("review", "security")
            if not store.read(sid).of(TOOL_RUN, name)]
    digest = _git_out(art.parent, "rev-parse", "HEAD")
    if gaps:
        return Probed(Outcome.FAILED,
                      f"{len(gaps)} missing of {2 * len(stories)}: {', '.join(gaps[:5])}",
                      evidence=str(store.root), digest=digest)
    return Probed(Outcome.PASSED, f"review and security recorded for {len(stories)} stories",
                  evidence=str(store.root), digest=digest)


def probe_evidence_at_candidate(ctx: Ctx) -> Probed:
    """G4.5 — deterministic verification is recorded at the merged candidate.

    Two ways this goes wrong, both checked: the latest result of a check still
    points at an older build (`gate._stale_candidates`, the same rule the story
    gate applies), or the candidate the evidence names is not in the corpus's
    history at all — verified on a build nobody merged.

    `kinds=()` excludes `qa:*` records, as the story gate does when a story
    declares no such contract: those sit at whatever SHA the last full `aisef
    qa` ran on and would otherwise declare every later story stale (bug 136).
    """
    art, why = ctx.artifacts()
    if art is None:
        return Probed(Outcome.UNRUNNABLE, why)
    corpus = art.parent
    if not (corpus / ".git").exists():
        return Probed(Outcome.UNRUNNABLE, f"{corpus} is not a git checkout — merged-ness unreadable")
    registered, _ = _corpus_stories(art)
    if not registered:
        return Probed(Outcome.UNRUNNABLE, "no stories have run in the corpus")
    store = EvidenceStore(art)
    problems = []
    for sid in registered:
        ev = store.read(sid)
        cand = ev.candidate
        if not cand:
            problems.append(f"{sid}: no candidate recorded")
            continue
        stale = _stale_candidates(ev, cand, ())
        if stale:
            problems.append(f"{sid}: checks at {', '.join(s[:7] for s in stale)} ≠ {cand[:7]}")
        elif not _git_out(corpus, "rev-parse", "--verify", f"{cand}^{{commit}}"):
            problems.append(f"{sid}: candidate {cand[:7]} is not in the corpus history")
    digest = _git_out(corpus, "rev-parse", "HEAD")
    if problems:
        return Probed(Outcome.FAILED, f"{len(problems)} of {len(registered)}: {'; '.join(problems[:4])}",
                      evidence=str(store.root), digest=digest)
    return Probed(Outcome.PASSED, f"{len(registered)} stories verified at a merged candidate",
                  evidence=str(store.root), digest=digest)


def probe_pre_deploy(ctx: Ctx) -> Probed:
    """G4.6 — pre-deploy passes with its scope declared.

    Read from the report on disk, the one the signer reads — not from state.
    A waived verification kind with no reason is not evidence, the rule
    `tests/test_release_gate.py` already applies to this same report.
    """
    art, why = ctx.artifacts()
    if art is None:
        return Probed(Outcome.UNRUNNABLE, why)
    rep = ctx.read_json(art / PRE_DEPLOY_REPORT)
    if rep is None:
        return _missing(f"{art / PRE_DEPLOY_REPORT} — run `aisef pre-deploy --epic E` in the corpus")
    noreason = [k for k, v in (rep.get("waivers") or {}).items() if not str(v).strip()]
    if noreason:
        return Probed(Outcome.FAILED, f"waived without a reason: {', '.join(sorted(noreason))}")
    if not (rep.get("scope") or {}).get("epic"):
        return Probed(Outcome.FAILED, "report declares no acceptance scope (`--epic`)")
    failing = [str(c.get("name")) for c in rep.get("checks") or [] if not c.get("passed")]
    if failing or not rep.get("passed"):
        return Probed(Outcome.FAILED,
                      f"{len(failing)} checks red: {', '.join(failing[:6])}" if failing
                      else "report says passed: false")
    return Probed(Outcome.PASSED, f"passed, scope {rep['scope']['epic']}")


def probe_pre_deploy_approved(ctx: Ctx) -> Probed:
    """G4.7 — the PRE_DEPLOY gate is human-approved against THAT report.

    `aisef closure` must never approve this, and an `auto` signature is not a
    human one: the whole point of the gate is that a person read the report.
    """
    art, why = ctx.artifacts()
    if art is None:
        return Probed(Outcome.UNRUNNABLE, why)
    if not (art / PRE_DEPLOY_REPORT).is_file():
        return _missing(f"{art / PRE_DEPLOY_REPORT} — nothing to approve yet")
    store = ApprovalStore(art)
    rec = store.load(Gate.PRE_DEPLOY)
    digest = store.content_hash(Gate.PRE_DEPLOY)
    if rec is None:
        return Probed(Outcome.FAILED,
                      "nobody has signed the PRE_DEPLOY gate — `aisef closure` never signs it",
                      evidence=str(store.dir), digest=digest)
    if rec.was_auto:
        return Probed(Outcome.FAILED, "signed by `auto` — not a human signature",
                      evidence=str(store.dir), digest=digest)
    status = store.status(Gate.PRE_DEPLOY)
    if status is not Status.APPROVED:
        return Probed(Outcome.FAILED, f"PRE_DEPLOY is {status.value} — approved against another report",
                      evidence=str(store.dir), digest=digest)
    return Probed(Outcome.PASSED, f"approved by {rec.decided_by} at {rec.decided_at}",
                  evidence=str(store.dir), digest=digest)


# ---------------------------------------------------- G5 benchmark integrity


class AmbiguousRegion(ValueError):
    """Số vùng ghim khác 1 — không đo được, chứ không phải đo ra sai."""

    def __init__(self, n: int):
        self.n = n
        super().__init__(f"{n} frozen regions, expected exactly 1")


def frozen_region_digest(path: Path, region: dict) -> str:
    """Digest của **vùng ghim**, theo đúng công thức `BENCH-PREREGISTRATION-C2.md` §1.1.

    Mốc và luật đến **từ dữ liệu** (`prereg_frozen_region` trong tệp tiêu chí),
    không viết cứng ở đây: §1.1 nói công thức không được có bản thứ hai, và một
    bản sao trong mã là bản thứ hai kể cả khi hôm nay nó trùng.

    Chuẩn hoá đúng **hai** khoản: CRLF/CR → LF, và cắt dòng trống ở hai đầu vùng.
    Ngoài hai khoản ấy, từng byte. Không chuẩn hoá nội dung — ngược hẳn với
    `onboarding_digest`, và có chủ ý: ở đó một lỗi chính tả không được làm mất
    hiệu lực công của một người thật, còn ở đây giá trị cần bảo vệ **là** việc
    văn bản không đổi, nên vỡ pin vì một lỗi chính tả là yêu cầu, không phải
    khiếm khuyết. Vùng ghim mang ngưỡng số trong văn xuôi (`≥ 3`, `±0,08`), và
    gộp khoảng trắng cho phép đổi cách viết chúng mà digest không đổi.

    Khoản LF thì buộc phải có: kho không có `.gitattributes` và CI chạy cả trên
    Windows, nên một checkout bật `core.autocrlf` sẽ làm digest lệch trên một tệp
    không ai chạm — một FAILED giả.
    """
    import hashlib

    bd = str(region.get("begin") or r"<!--\s*PREREG-FROZEN:BEGIN\s*-->")
    kt = str(region.get("end") or r"<!--\s*PREREG-FROZEN:END\s*-->")
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    found = re.findall(rf"(?s){bd}\n(.*?)\n{kt}", text)
    if len(found) != 1:
        raise AmbiguousRegion(len(found))
    return hashlib.sha256(found[0].strip("\n").encode("utf-8")).hexdigest()


def probe_closure_target(ctx: Ctx) -> Probed:
    """G1.0 — one revision is being certified, and everything points at it.

    Owner adjustment 2: `release_tag_commit == closure_target_sha`. The gap it
    closes is not hypothetical — G1 certified the PyPI artefact at the *tag*
    commit while G2–G5 read *HEAD*, 46 commits later. Those are different
    software, and a closure record that mixes them certifies nothing. The owner
    named the three moves to refuse: build HEAD but install an older PyPI
    version; read packaged data from HEAD and call it proof about the old tag;
    combine evidence from different source revisions into one G1 PASS.

    One criterion owns the invariant rather than four probes each checking a
    corner, so the failure says "G1 certifies X, closure targets Y" in one
    place. Two conjuncts, and it must not pass on one of them (bug 154): the tag
    resolves to the target, **and** HEAD is still the target — G2–G5 bind their
    evidence to HEAD, so a HEAD that has moved on means their evidence describes
    something other than what G1 certifies.

    An unset target is UNRUNNABLE: no candidate has been frozen, so there is no
    invariant to read, and "nothing to compare" is never a pass.
    """
    rel = str(ctx.criterion.get("evidence") or "closure-evidence/release.json")
    rec = ctx.read_json(rel)
    if rec is None:
        return _missing(f"{rel} — the release record naming the certified tag")
    target = str(ctx.spec.get("closure_target_sha") or "")
    if not target:
        return Probed(Outcome.UNRUNNABLE,
                      "`closure_target_sha` is not set in the criteria file — no closure "
                      "candidate has been frozen, so there is no single revision to "
                      "certify; run `aisef closure --pin-target` on the candidate")
    head = ctx.head
    if not head:
        return Probed(Outcome.UNRUNNABLE, "cannot read git HEAD here")
    tag = str(rec.get("tag") or "")
    if not tag:
        return Probed(Outcome.UNRUNNABLE, f"{rel} names no `tag` — nothing to resolve")
    at_tag = _git_out(ctx.root, "rev-list", "-n", "1", tag)
    if not at_tag:
        return Probed(Outcome.UNRUNNABLE,
                      f"tag {tag} does not resolve in this checkout — a release record "
                      f"whose tag is absent cannot be bound to a revision")
    if not (at_tag.startswith(target) or target.startswith(at_tag)):
        return Probed(Outcome.FAILED,
                      f"G1 certifies {tag} at {at_tag[:12]}, closure targets "
                      f"{target[:12]} — the released artefact and the revision being "
                      f"closed are different software; release the closure candidate, "
                      f"or re-pin the target at the commit actually released")
    if not (head.startswith(target) or target.startswith(head)) \
            and not _only_bookkeeping_changed(ctx, target):
        return Probed(Outcome.FAILED,
                      f"HEAD is {head[:12]}, closure targets {target[:12]} — G2 to G5 "
                      f"bind their evidence to HEAD, so that evidence describes a "
                      f"different revision from the one G1 certifies; re-record it at "
                      f"the target, or re-pin the target and release again")
    return Probed(Outcome.PASSED,
                  f"one revision: {tag}, HEAD and closure target all at {target[:12]}")


def probe_prereg_digest(ctx: Ctx) -> Probed:
    """G5.1 — the methodology was pre-registered, and its digest still matches.

    An unpinned prediction is indistinguishable from a post-hoc one (owner
    ruling 7), so an unpinned pre-registration is UNRUNNABLE rather than a
    pass. The pin lives in the criteria file next to `contract_sha256` and is
    written by `aisef closure --pin`, never at evaluation time.

    The digest covers the **frozen region**, not the whole file, and there is no
    fallback to whole-file hashing: this file is required to grow (a dated
    addendum, the G5.3 status, a pointer to the column-2 report), so a whole-file
    digest breaks on every such addition — and a pin that breaks routinely turns
    "digest mismatch" into noise that a real edit to the prediction then walks
    through unseen. Hashing the whole file when the markers cannot be found is
    hashing something else and calling it this measurement, which is the
    false-PASS class §4.1 of the contract exists to forbid.

    Five steps, as §1.5 of the pre-registration declares them. It calls an
    ambiguous marker pair FAILED; this reads it UNRUNNABLE, because with no
    single region there is nothing to compare and FAILED would assert a fact —
    that the text was rewritten — which has not been established. Both block, so
    no closure outcome turns on the difference (see §3 of that file, dated).
    """
    rel = str((ctx.criterion.get("evidence") or "docs/BENCH-PREREGISTRATION-C2.md"))
    if ctx.read(rel) is None:
        return _missing(f"{rel} — the pre-registration promoted to a closure artifact")
    region = ctx.criterion.get("prereg_frozen_region") or {}
    try:
        now = frozen_region_digest(ctx.path(rel), region)
    except AmbiguousRegion as e:
        return Probed(Outcome.UNRUNNABLE,
                      f"{rel} has {e.n} `PREREG-FROZEN` regions, expected exactly 1 — "
                      f"with no single region there is nothing to compare, and hashing "
                      f"the whole file instead would measure something else")
    pin = str(ctx.criterion.get("prereg_sha256") or ctx.spec.get("prereg_sha256") or "")
    if not pin:
        return Probed(Outcome.UNRUNNABLE,
                      f"{rel} exists but is not digest-pinned — run `aisef closure --pin`")
    if pin != now:
        return Probed(Outcome.FAILED,
                      f"{rel} changed after pinning inside the frozen region "
                      f"({pin[:12]} → {now[:12]}) — prediction and success criteria "
                      f"are not rewritten after data exists; restore the text rather "
                      f"than re-recording the digest")
    # Bản lịch sử là thứ **định ngày** cho tiền đăng ký. Nó lệch thì bằng chứng
    # "viết trước khi có một byte dữ liệu" đã mất, dù bản ghim vẫn khớp — nên đây
    # là một bước riêng, không phải một chú thích.
    also = str(region.get("also_in") or "")
    if also:
        if ctx.read(also) is None:
            return Probed(Outcome.UNRUNNABLE,
                          f"missing {also} — the pre-data copy that dates the "
                          f"pre-registration; without it the pin proves the text is "
                          f"unchanged but not that it predates the data")
        try:
            xua = frozen_region_digest(ctx.path(also), region)
        except AmbiguousRegion as e:
            return Probed(Outcome.UNRUNNABLE,
                          f"{also} has {e.n} `PREREG-FROZEN` regions, expected exactly 1")
        if xua != now:
            return Probed(Outcome.FAILED,
                          f"{also} no longer carries the same frozen region "
                          f"({xua[:12]} vs {now[:12]}) — the historical copy is what "
                          f"dates the text, so the two must agree byte for byte")
    return Probed(Outcome.PASSED,
                  f"frozen region pinned at {pin[:12]}, unchanged"
                  + (f", and matched in {also}" if also else ""))


def probe_cut_session_separation(ctx: Ctx) -> Probed:
    """G5.2 — cut sessions are not silently mixed with valid ones.

    Every row must carry `exit_status`. A row without one cannot be told apart
    from a graded attempt, which is how C-1b's three cut sessions read as
    failures and produced a +0.06 that was an artifact.
    """
    files = sorted(ctx.root.glob(".bench*/results.jsonl"))
    if not files:
        return _missing(".bench*/results.jsonl — no bench results in this tree")
    total = blank = infra = 0
    for path in files:
        text = ctx.read(path) or ""
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            if not str(row.get("exit_status") or ""):
                blank += 1
            elif row["exit_status"] in INFRA_STATUSES:
                infra += 1
    where = ", ".join(str(p.relative_to(ctx.root)) for p in files)
    if not total:
        return Probed(Outcome.UNRUNNABLE, f"no rows in {where}")
    if blank:
        return Probed(Outcome.FAILED,
                      f"{blank} of {total} rows carry no exit_status — a cut session is "
                      f"indistinguishable from a graded one ({where})")
    return Probed(Outcome.PASSED, f"{total} rows all carry exit_status · {infra} infra/cut ({where})")


def probe_pair_qualification(ctx: Ctx) -> Probed:
    """G5.3 — a model↔CLI pair satisfying the pre-registered validity rule exists.

    The report states, per pair: model · client · qualification sessions · cut
    sessions · cut-session rate · timeout/infra failures · qualifies · evidence
    path (owner ruling 3). No pair qualifying is `WAIVER_PENDING`: it blocks,
    the 72-attempt run does not start, and only the owner may waive it.
    """
    rel = str(ctx.criterion.get("evidence") or "docs/BENCH-PAIR-QUALIFICATION.md")
    text = ctx.read(rel)
    if text is None:
        return _missing(f"{rel} — the bounded pair qualification has not run")
    # Owner adjustment 4: the threshold and the sample size are frozen BEFORE any
    # session runs — "do not inspect qualification results and then choose the
    # threshold". A report is therefore unreadable except against the protocol it
    # was produced under, so the pin is checked before the table: a good-looking
    # table on a protocol edited afterwards is exactly the move being forbidden.
    protocol = str(ctx.criterion.get("protocol") or "")
    pin = str(ctx.criterion.get("protocol_sha256") or "")
    if protocol and pin:
        if ctx.read(protocol) is None:
            return _missing(f"{protocol} — the pinned qualification protocol")
        try:
            now = frozen_region_digest(
                ctx.path(protocol), ctx.criterion.get("protocol_frozen_region") or {})
        except AmbiguousRegion as e:
            return Probed(Outcome.UNRUNNABLE,
                          f"{protocol} has {e.n} `QUAL-FROZEN` regions, expected exactly 1")
        if now != pin:
            return Probed(Outcome.FAILED,
                          f"{protocol} changed after pinning ({pin[:12]} → {now[:12]}) — "
                          f"the threshold and sample size are frozen before any session "
                          f"runs, so a report scored against an edited protocol is a "
                          f"post-hoc bar wearing a pre-registered label")
        # Cột digest của báo cáo phải là **cùng** giao thức. Một bảng sinh dưới
        # giao thức khác đọc bằng giao thức này là so hai thứ khác nhau.
        khai = re.findall(r"`([0-9a-f]{12,64})…?`", text)
        if not any(pin.startswith(k) for k in khai):
            return Probed(Outcome.UNRUNNABLE,
                          f"{rel} does not state the protocol digest it was produced "
                          f"under" + (f" (it names {', '.join(k[:8] for k in khai[:3])}, "
                                      f"the pin is {pin[:8]})" if khai else "")
                          + " — without it the table cannot be bound to a frozen bar")
    head, rows = _md_table(text, "qualifies")
    if not head:
        return Probed(Outcome.UNRUNNABLE, f"{rel} has no table with a `qualifies` column")
    absent = [c for c in ("model", "client", "cut", "rate", "evidence") if not any(c in h for h in head)]
    if absent:
        return Probed(Outcome.UNRUNNABLE, f"{rel} does not state: {', '.join(absent)}")
    good = [r for r in rows if _cell(head, r, "qualifies").strip().lower() in ("yes", "✅", "có")]
    if not good:
        return Probed(Outcome.FAILED,
                      f"WAIVER_PENDING — none of {len(rows)} pairs qualifies; column 2 does not start")
    return Probed(Outcome.PASSED,
                  f"{len(good)} of {len(rows)} pairs qualify: "
                  + ", ".join(f"{_cell(head, r, 'model')}/{_cell(head, r, 'client')}" for r in good[:3]))


def probe_bench_reproducible(ctx: Ctx) -> Probed:
    """G5.4 — the dataset digest matches and the selfcheck passes.

    The digest half is recomputed here through the bench module's own renderer,
    so it reads the manifest the dataset actually declares. The selfcheck half
    is a recorded run: it spawns processes, and the evaluator runs nothing.
    Either half missing is UNRUNNABLE — a criterion with two conjuncts must not
    pass on one of them (bug 154).
    """
    try:
        from tests.bench import _mine as M
    except ImportError as e:
        return Probed(Outcome.UNRUNNABLE, f"tests.bench not importable ({e}) — not a source checkout")
    manifest = M.TASKS_DIR / "MANIFEST.sha256"
    have = ctx.read(manifest)
    if have is None:
        return _missing(str(manifest))
    if M.render_dataset_manifest(M.TASKS_DIR) != have:
        return Probed(Outcome.FAILED, f"{manifest.name} does not match the dataset byte for byte")
    rel = f"{EVIDENCE_DIR}/bench-selfcheck.json"
    rec = ctx.read_json(rel)
    if rec is None:
        return _missing(f"{rel} — record of `python3 -m tests.bench selfcheck`")
    stale = _at_commit(ctx, rec)
    if stale:
        return stale
    passed, total = int(rec.get("passed") or 0), int(rec.get("total") or 0)
    if not total:
        return _missing(f"{rel}#total")
    if passed != total:
        return Probed(Outcome.FAILED, f"selfcheck {passed}/{total}")
    return Probed(Outcome.PASSED, f"manifest matches · selfcheck {passed}/{total}")


def probe_inconclusive_reported(ctx: Ctx) -> Probed:
    """G5.5 — noise and inconclusive results are reported as such.

    Each bench report must either state the band or state that the corpus
    cannot resolve one. A report that prints deltas and says neither presents
    noise as a result.
    """
    files = sorted(ctx.root.glob("docs/BENCH-REPORT-*.md"))
    if not files:
        return _missing("docs/BENCH-REPORT-*.md")
    silent = []
    for path in files:
        text = (ctx.read(path) or "").lower()
        if not any(m in text for m in NOISE_MARKERS):
            silent.append(path.name)
    if silent:
        return Probed(Outcome.FAILED,
                      f"{len(silent)} of {len(files)} state neither a band nor an inconclusive "
                      f"verdict: {', '.join(silent)}")
    return Probed(Outcome.PASSED, f"{len(files)} reports state a band or an inconclusive verdict")


#: Claims withdrawn as unreproducible (§5 G5.6). Presenting one as current
#: evidence is the failure this criterion exists to catch.
RETIRED_CLAIMS = ("near-zero measured cost overhead", "near-zero cost overhead",
                  "36× cost", "36x cost", "±0.08")


def probe_no_stale_claims(ctx: Ctx) -> Probed:
    """G5.6 — no unreproducible historical claim presented as current evidence."""
    rels = [r.strip() for r in str(ctx.criterion.get("evidence") or "").split(",") if r.strip()]
    if not rels:
        return Probed(Outcome.UNRUNNABLE, "criterion names no surfaces to audit")
    hits, absent = [], []
    for rel in rels:
        text = ctx.read(rel)
        if text is None:
            absent.append(rel)
            continue
        low = text.lower()
        hits += [f"{rel}: {claim}" for claim in RETIRED_CLAIMS if claim in low]
    if absent:
        return _missing(", ".join(absent))
    if hits:
        return Probed(Outcome.FAILED, f"{len(hits)} retired claims: {'; '.join(hits[:4])}")
    return Probed(Outcome.PASSED, f"{len(rels)} public surfaces carry no retired claim")


# ---------------------------------------------------- G6 external validation


def _section(text: str, name: str) -> str:
    """Content of a markdown section, heading excluded, to the next heading of
    the same or higher level. Line structure is preserved — a caller that
    wants a digest normalises it, a caller that wants a table needs the rows."""
    lines = text.splitlines()
    out: list[str] = []
    level = 0
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if level:
            if m and len(m.group(1)) <= level:
                break
            out.append(line)
        elif m and name.lower() in m.group(2).strip().lower():
            level = len(m.group(1))
    return "\n".join(out).strip()


def _cli_workflow(text: str) -> str:
    """The canonical public CLI workflow: the `aisef …` verb sequence with its
    flags, in document order."""
    return _norm(" ".join(re.findall(r"(?m)^\s*(?:\$\s*)?(aisef\s+[^\n`]*)$", text)))


def onboarding_digest(root: Path, spec: dict) -> tuple[str, list[str]]:
    """Deterministic hash over the PUBLIC ONBOARDING SURFACE (owner ruling 4).

    Taken over extracted, normalised content — whitespace collapsed, prose
    reflow ignored — never raw file bytes: a typo fix must not invalidate a
    real person's validation, while a changed install step or a changed
    onboarding default must not hide.

    Returns `(digest, missing)`; a non-empty `missing` means the digest could
    not be taken and the caller must say so rather than hash less.
    """
    parts, missing = [], []
    for src in spec.get("sources") or []:
        rel, extract = str(src.get("path") or ""), str(src.get("extract") or "")
        path = root / rel
        if not path.is_file():
            missing.append(rel)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if extract.startswith("section:"):
            piece = _norm(_section(text, extract[len("section:"):]))
        elif extract == "canonical_cli_workflow":
            piece = _cli_workflow(text)
        elif extract == "onboarding_defaults":
            keys = list(spec.get("onboarding_defaults") or [])
            gone = [k for k in keys if k not in DEFAULTS]
            if gone:
                missing.append(f"config defaults {', '.join(gone)}")
                continue
            piece = json.dumps({k: DEFAULTS[k] for k in keys}, sort_keys=True, ensure_ascii=False)
        else:
            missing.append(f"{rel}#{extract} (unknown extract)")
            continue
        if not piece:
            missing.append(f"{rel}#{extract} (empty)")
            continue
        parts.append(f"{rel}#{extract}:{piece}")
    if missing:
        return "", missing
    return hashlib.sha256("\n".join(parts).encode()).hexdigest(), []


def _external_report(ctx: Ctx) -> tuple[str, Probed | None]:
    rel = str(ctx.criterion.get("evidence") or "docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md")
    text = ctx.read(rel)
    if text is None:
        return "", _missing(f"{rel} — the validation RECORD "
                            "(docs/EXTERNAL-VALIDATION-v1.1.0.md is the protocol, not the record)")
    return text, None


def probe_external_report(ctx: Ctx) -> Probed:
    """G6.1 — the record exists at the declared path, carrying the protocol's
    metric fields, and the onboarding surface has not moved under it.

    The metric list is read from the protocol's own Metrics table, not copied
    into this file: two lists drift.
    """
    text, err = _external_report(ctx)
    if err:
        return err
    protocol = "docs/EXTERNAL-VALIDATION-v1.1.0.md"
    ptext = ctx.read(protocol)
    if ptext is None:
        return _missing(f"{protocol} — the protocol that declares the metric fields")
    _, rows = _md_table(_section(ptext, "Metrics") or ptext, "metric")
    labels = [r[0].split("(")[0].strip() for r in rows if r and r[0].strip()]
    if not labels:
        return Probed(Outcome.UNRUNNABLE, f"{protocol} has no readable Metrics table")
    low = _norm(text).lower()
    absent = [lab for lab in labels if lab.lower() not in low]
    if absent:
        return Probed(Outcome.FAILED,
                      f"{len(absent)} of {len(labels)} protocol metrics absent: {', '.join(absent[:5])}")
    rec = ctx.read_json(f"{EVIDENCE_DIR}/onboarding-digest.json")
    if rec is None:
        return _missing(f"{EVIDENCE_DIR}/onboarding-digest.json — the onboarding digest "
                        "the validation was taken against (owner ruling 4)")
    now, gone = onboarding_digest(ctx.root, ctx.spec.get("onboarding_digest") or {})
    if gone:
        return Probed(Outcome.UNRUNNABLE, f"cannot take the onboarding digest: {', '.join(gone)}")
    version, release = str(rec.get("version") or ""), _version(ctx.root)
    if version.split(".")[:2] != release.split(".")[:2]:
        return Probed(Outcome.FAILED,
                      f"validated on {version or '?'}, closing {release} — different MAJOR.MINOR")
    if str(rec.get("sha256") or "") != now:
        return Probed(Outcome.FAILED,
                      "the public onboarding surface changed since the validation "
                      f"({str(rec.get('sha256'))[:12]} → {now[:12]})")
    return Probed(Outcome.PASSED,
                  f"{len(labels)} protocol metrics present · onboarding digest {now[:12]} unchanged")


def probe_participant_external(ctx: Ctx) -> Probed:
    """G6.2 — the participant is a genuinely external person.

    Not machine-decidable on its own (owner ruling 4): the probe reads the
    record's own declaration — a line `Participant: …` — and the owner confirms
    at approval. An AI agent is refused outright; it is exactly the corner an
    agent under time pressure would cut.
    """
    text, err = _external_report(ctx)
    if err:
        return err
    m = re.search(r"(?im)^\s*(?:[-*]\s*)?\**participant\**\s*:\s*(.+?)\s*$", text)
    if not m:
        return Probed(Outcome.UNRUNNABLE,
                      "the record declares no `Participant:` line — G6.2 cannot be read from it")
    who = m.group(1).strip()
    if re.search(r"(?i)\b(ai|agent|claude|gpt|llm|bot|opencode)\b", who):
        return Probed(Outcome.FAILED,
                      f"participant reads as an AI agent: {who} — an agent cannot satisfy G6")
    if not re.search(r"(?i)\bexternal\b", who):
        return Probed(Outcome.FAILED,
                      f"participant does not assert external status: {who}")
    return Probed(Outcome.PASSED, f"declared: {who} — the owner confirms this at approval")


def probe_onboarding_blockers(ctx: Ctx) -> Probed:
    """G6.3 — no unresolved P0/P1 onboarding blocker, on the protocol's own
    severity ladder."""
    text, err = _external_report(ctx)
    if err:
        return err
    blocking = tuple(str(s).upper() for s in
                     (ctx.spec.get("severity_scale") or {}).get("blocking") or ())
    head, rows = _md_table(text, "severity")
    if not head:
        return Probed(Outcome.UNRUNNABLE, "the record has no findings table with a `severity` column")
    open_ = []
    for row in rows:
        sev = _cell(head, row, "severity").strip().upper()
        if sev not in blocking:
            continue
        status = _cell(head, row, "status").strip().lower()
        if not any(done in status for done in RESOLVED):
            open_.append(f"{sev} {row[0][:40]} ({status or 'no status'})")
    if open_:
        return Probed(Outcome.FAILED, f"{len(open_)} unresolved: {'; '.join(open_[:4])}")
    return Probed(Outcome.PASSED, f"no unresolved {'/'.join(blocking)} in {len(rows)} findings")


# ------------------------------------------------------------- the evaluator


@dataclass
class Result:
    """One criterion, evaluated. This is the row the report records: outcome,
    the evidence path, that evidence's digest, when, and which probe said so."""

    id: str
    gate: str
    statement: str
    probe: str
    outcome: Outcome
    detail: str = ""
    evidence: str = ""
    digest: str = ""
    at: str = ""
    waiver: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"id": self.id, "gate": self.gate, "statement": self.statement,
                "probe": self.probe, "outcome": self.outcome.value, "detail": self.detail,
                "evidence": self.evidence, "digest": self.digest, "at": self.at,
                "blocks": self.outcome.blocks, "waiver": self.waiver}


@dataclass
class Report:
    contract: dict
    results: list[Result]
    at: str = ""
    approval: dict = field(default_factory=dict)

    @property
    def blocking(self) -> list[Result]:
        return [r for r in self.results if r.outcome.blocks]

    @property
    def closable(self) -> bool:
        """Closable needs a pinned contract as well as non-blocking criteria:
        an unpinned contract could have been edited into being satisfied."""
        return not self.blocking and self.contract.get("state") == "pinned"

    def tally(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.results:
            out[r.outcome.value] = out.get(r.outcome.value, 0) + 1
        return out

    def as_dict(self) -> dict:
        return {"at": self.at, "contract": self.contract, "closable": self.closable,
                "tally": self.tally(), "approval": self.approval,
                "criteria": [r.as_dict() for r in self.results]}


def load_spec(root: Path) -> dict:
    """Read the criteria file. Raises `FileNotFoundError`/`ValueError` — a gate
    that cannot be read is a usage error, not an empty pass."""
    path = Path(root) / CRITERIA_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("gates"):
        raise ValueError(f"{CRITERIA_PATH} declares no gates")
    return data


def load_state(root: Path) -> dict:
    path = Path(root) / STATE_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(root: Path, state: dict) -> Path:
    path = Path(root) / STATE_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def contract_state(root: Path, spec: dict) -> dict:
    """Where the contract digest stands: `pinned`, `unpinned`, `stale`, `missing`.

    The current digest is *computed* here and reported, but the pin only ever
    comes from the criteria file: computing the pin at evaluation time would
    mean the contract could be edited into being satisfied, which is the whole
    thing the pin prevents.
    """
    rel = str(spec.get("contract_path") or "docs/PROJECT-CLOSURE-GATE.md")
    now = sha256_of(Path(root) / rel)
    pin = str(spec.get("contract_sha256") or "")
    if not now:
        state = "missing"
    elif not pin:
        state = "unpinned"
    elif pin != now:
        state = "stale"
    else:
        state = "pinned"
    return {"path": rel, "pinned": pin, "sha256": now, "state": state}


def waiver_eligible(gate: dict, criterion: dict) -> bool:
    return bool(criterion.get("waiver_eligible", gate.get("waiver_eligible", False)))


def eligible_ids(spec: dict) -> list[str]:
    return [c["id"] for g in spec.get("gates") or [] for c in g.get("criteria") or []
            if waiver_eligible(g, c)]


def _find(spec: dict, criterion_id: str) -> tuple[dict, dict] | None:
    for gate in spec.get("gates") or []:
        for crit in gate.get("criteria") or []:
            if crit.get("id") == criterion_id:
                return gate, crit
    return None


def _run_probe(ctx: Ctx, criterion: dict) -> Probed:
    """Call the probe the criterion names. A probe that cannot be resolved or
    that raises is UNRUNNABLE — never a pass."""
    name = str(criterion.get("probe") or "")
    try:
        fn = _ref(name)
    except (ImportError, AttributeError, ValueError) as e:
        return Probed(Outcome.UNRUNNABLE, f"probe {name} not resolvable: {e}")
    try:
        return fn(ctx)
    except Exception as e:  # noqa: BLE001 — a crashing probe must block, not pass
        return Probed(Outcome.UNRUNNABLE, f"probe {name} raised {type(e).__name__}: {e}")


def evaluate(root: Path | str, *, corpus: str = "", spec: dict | None = None,
             state: dict | None = None) -> Report:
    """Score every criterion. Reads only; writes nothing, approves nothing."""
    root = Path(root).resolve()
    spec = load_spec(root) if spec is None else spec
    state = load_state(root) if state is None else state
    waivers = state.get("waivers") or {}
    tighten = bool(spec.get("unconfigured_is_unrunnable", True))
    at = _now()

    results: list[Result] = []
    for gate in spec.get("gates") or []:
        for crit in gate.get("criteria") or []:
            ctx = Ctx(root=root, spec=spec, criterion=crit, corpus_arg=corpus)
            probed = _run_probe(ctx, crit)
            outcome, detail = probed.outcome, probed.detail
            if outcome is Outcome.UNCONFIGURED and tighten:
                outcome = Outcome.UNRUNNABLE
                detail = ("UNCONFIGURED promoted to UNRUNNABLE at closure — nobody configured "
                          f"the check is not evidence of health ({detail})")
            waiver: dict = {}
            signed = waivers.get(crit.get("id")) or {}
            if (outcome.blocks and str(signed.get("reason") or "").strip()
                    and waiver_eligible(gate, crit)):
                waiver = {**signed, "was": outcome.value, "was_detail": detail}
                outcome = Outcome.WAIVED
                detail = (f"{signed['reason']} — {signed.get('by') or '?'} "
                          f"{signed.get('at') or ''} (was {waiver['was']}: {waiver['was_detail']})")
            results.append(Result(
                id=str(crit.get("id") or "?"), gate=str(gate.get("id") or "?"),
                statement=str(crit.get("statement") or ""), probe=str(crit.get("probe") or ""),
                outcome=outcome, detail=detail,
                evidence=probed.evidence or ctx.evidence() or str(crit.get("evidence") or ""),
                digest=probed.digest or ctx.digest(), at=at, waiver=waiver,
            ))
    report = Report(contract=contract_state(root, spec), results=results, at=at)
    report.approval = approval_state(state, report)
    return report


def approval_state(state: dict, report: Report) -> dict:
    """The owner's signature and whether it still stands.

    Same model as `ApprovalStore.status`: the record binds to content, and the
    content is recomputed from disk — an evidence digest that has changed since
    the signature makes it STALE without anyone marking it. Three independent
    causes, all reported by name: an evidence digest moved, the contract digest
    moved, or a declared freshness window lapsed (that one surfaces as the
    criterion itself turning UNRUNNABLE/FAILED, which also un-stands it).
    """
    rec = state.get("approval") or {}
    if not rec:
        return {"status": Status.PENDING.value}
    reasons = []
    signed = rec.get("digests") or {}
    now = {r.id: r.digest for r in report.results}
    moved = sorted(k for k, v in signed.items() if now.get(k, "") != v)
    if moved:
        reasons.append("evidence digest changed: " + ", ".join(moved[:5]))
    if str(rec.get("contract_sha256") or "") != report.contract.get("sha256"):
        reasons.append("contract digest changed")
    if report.blocking:
        reasons.append("blocking again: " + ", ".join(r.id for r in report.blocking[:5]))
    out = {**rec, "status": (Status.STALE if reasons else Status.APPROVED).value}
    if reasons:
        out["stale_because"] = reasons
    return out


# ------------------------------------------------------------- human actions


def pin(root: Path | str, *, force: bool = False) -> dict:
    """Write the contract digest into the criteria file — a deliberate act,
    committed like any other change, and never done at evaluation time.

    Also pins the bench pre-registration (owner ruling 7) when it exists: the
    pin is what makes a prediction distinguishable from a post-hoc one.
    """
    root = Path(root).resolve()
    spec = load_spec(root)
    if spec.get("contract_sha256") and not force:
        raise ValueError(f"already pinned at {spec['contract_sha256'][:12]} — "
                         "re-pinning hides an edit to the contract; pass --force if that is the intent")
    rel = str(spec.get("contract_path") or "docs/PROJECT-CLOSURE-GATE.md")
    digest = sha256_of(root / rel)
    if not digest:
        raise ValueError(f"{rel} does not exist — nothing to pin")
    spec["contract_sha256"] = digest
    pinned = {rel: digest}
    prereg = _find(spec, "G5.1")
    if prereg:
        crit = prereg[1]
        path = root / str(crit.get("evidence") or "")
        if path.is_file():
            # Ghi vào **tiêu chí**, cạnh `prereg_frozen_region` mô tả mốc, không
            # ghi ở mức trên cùng: giá trị và luật sinh ra nó phải ở cùng một chỗ,
            # còn một con số có hai nhà là một con số sẽ lệch (§1.4). Bản trước
            # giữ cả hai — một digest cả tệp ở mức trên cùng mà probe đọc, và một
            # digest vùng ghim ở mức tiêu chí không ai đọc.
            crit["prereg_sha256"] = frozen_region_digest(
                path, crit.get("prereg_frozen_region") or {})
            spec.pop("prereg_sha256", None)
            pinned[str(path.relative_to(root))] = crit["prereg_sha256"]
    (root / CRITERIA_PATH).write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return pinned


def pin_target(root: Path | str, *, force: bool = False) -> str:
    """Freeze HEAD as the revision this closure certifies (owner adjustment 2).

    Separate from `--pin`, which pins the contract text once and refuses to
    repeat: the target is chosen much later, when a candidate is actually ready,
    and it legitimately moves when the candidate is re-cut. Refuses on a dirty
    tree — a SHA pinned there names a revision that does not describe what was
    measured, which is the mixing this invariant exists to stop.
    """
    root = Path(root).resolve()
    head = _git_out(root, "rev-parse", "HEAD")
    if not head:
        raise ValueError("cannot read git HEAD — not a checkout?")
    if _git_out(root, "status", "--porcelain"):
        raise ValueError("working tree is dirty — a target pinned here names a revision "
                         "that does not describe what was measured; commit or stash first")
    spec = load_spec(root)
    old = str(spec.get("closure_target_sha") or "")
    if old and old != head and not force:
        raise ValueError(f"closure target already pinned at {old[:12]} — re-pinning "
                         f"moves what is being certified; pass --force if that is the intent")
    spec["closure_target_sha"] = head
    (root / CRITERIA_PATH).write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return head


def sign_waiver(root: Path | str, criterion_id: str, reason: str, *, by: str = "") -> dict:
    """Record a waiver. Refuses without a reason, and refuses for a criterion
    the contract does not mark waiver-eligible: a waiver without a reason is
    not evidence, and a waiver where the contract allows none is a rewrite of
    the contract."""
    root = Path(root).resolve()
    if not reason.strip():
        raise ValueError("a waiver without a reason is not evidence — pass --reason \"...\"")
    spec = load_spec(root)
    found = _find(spec, criterion_id)
    if not found:
        raise ValueError(f"unknown criterion: {criterion_id}")
    gate, crit = found
    if not waiver_eligible(gate, crit):
        raise ValueError(f"{criterion_id} is not waiver-eligible in {CRITERIA_PATH} — "
                         f"only {', '.join(eligible_ids(spec))} may be waived")
    state = load_state(root)
    rec = {"reason": reason.strip(), "by": by or _current_user(), "at": _now()}
    state.setdefault("waivers", {})[criterion_id] = rec
    _save_state(root, state)
    return rec


def sign_approval(root: Path | str, *, by: str = "", note: str = "") -> dict:
    """The owner's signature. Refuses unless every criterion is non-blocking and
    the contract is pinned, and records who, when, and the digest set signed.

    Never called by `evaluate` or by any probe — `aisef closure` evaluates and
    reports; approving is the owner's command (§0).
    """
    root = Path(root).resolve()
    report = evaluate(root)
    if report.contract.get("state") != "pinned":
        raise ValueError(f"contract is {report.contract.get('state')} — "
                         "run `aisef closure --pin` and commit it before approving")
    if report.blocking:
        raise ValueError("blocked by " + ", ".join(f"{r.id} ({r.outcome.value})"
                                                   for r in report.blocking))
    rec = {"by": by or _current_user(), "at": _now(), "note": note,
           "contract_sha256": report.contract["sha256"],
           "waived": [r.id for r in report.results if r.outcome is Outcome.WAIVED],
           "digests": {r.id: r.digest for r in report.results}}
    state = load_state(root)
    state["approval"] = rec
    _save_state(root, state)
    return rec


# ------------------------------------------------------------------ reporting


def write_report(root: Path | str, report: Report) -> Path:
    path = Path(root) / REPORT_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def read_report(root: Path | str) -> dict:
    return json.loads((Path(root) / REPORT_JSON).read_text(encoding="utf-8"))


def table(report: Report) -> str:
    """The per-criterion table `aisef closure` prints."""
    c = report.contract
    lines = [f"Project closure gate — {c['path']}",
             f"  contract {c['state']}" + (f" ({c['sha256'][:12]})" if c["sha256"] else "")]
    if c["state"] == "stale":
        lines[-1] += f", pinned at {c['pinned'][:12]}"
    gate = ""
    for r in report.results:
        if r.gate != gate:
            gate = r.gate
            lines.append("")
        statement = r.statement if len(r.statement) <= 72 else r.statement[:71] + "…"
        lines.append(f"  {r.outcome.mark} {r.id:<6} {statement}")
        if r.detail:
            lines.append(f"        {r.detail}")
    tally = report.tally()
    lines += ["", " · ".join(f"{n} {name}" for name, n in sorted(tally.items()))]
    approval = report.approval.get("status", Status.PENDING.value)
    if report.closable:
        lines.append(f"CLOSABLE — {len(report.results)} criteria, none blocking · approval {approval}")
    else:
        why = ", ".join(r.id for r in report.blocking) or f"contract {c['state']}"
        lines.append(f"BLOCKED — {len(report.blocking)} of {len(report.results)} block: {why}")
    return "\n".join(lines)


def render(data: dict) -> str:
    """The human report, from the machine report — same numbers, no re-probing.
    Deliberately link-free: this file lands in `docs/`, which the documentation
    link check reads."""
    c = data.get("contract") or {}
    out = ["# AISEF project closure — evidence table", "",
           f"Generated {data.get('at')} by `aisef closure`. The contract is `{c.get('path')}`; "
           f"its digest is **{c.get('state')}**"
           + (f" (`{str(c.get('sha256'))[:12]}`)." if c.get("sha256") else "."), "",
           "Outcome vocabulary is `aisef.control.gate.Outcome`, with one closure tightening: "
           "`UNCONFIGURED` is promoted to `UNRUNNABLE`, because nobody configuring a check is "
           "not evidence of health.", ""]
    verdict = "CLOSABLE" if data.get("closable") else "BLOCKED"
    tally = " · ".join(f"{n} {k}" for k, n in sorted((data.get("tally") or {}).items()))
    out += [f"**{verdict}** — {tally}.", ""]
    gate = ""
    for r in data.get("criteria") or []:
        if r["gate"] != gate:
            gate = r["gate"]
            out += ["", f"## {gate}", "",
                    "| criterion | outcome | what the evidence says | evidence | digest | probe |",
                    "|---|---|---|---|---|---|"]
        out.append("| {id} | {mark} {outcome} | {detail} | `{evidence}` | `{digest}` | `{probe}` |".format(
            mark=Outcome(r["outcome"]).mark, id=r["id"], outcome=r["outcome"],
            detail=(r["detail"] or "").replace("|", "/"), evidence=r["evidence"] or "—",
            digest=(r["digest"] or "—")[:12], probe=r["probe"]))
    blocked = [r for r in data.get("criteria") or [] if r["blocks"]]
    if blocked:
        out += ["", "## What blocks closure", ""]
        out += [f"- **{r['id']}** ({r['outcome']}) — {r['detail']}" for r in blocked]
    approval = data.get("approval") or {}
    out += ["", "## Approval", "",
            f"Status: **{approval.get('status', 'pending')}**"
            + (f", signed by {approval.get('by')} at {approval.get('at')}" if approval.get("by") else "")
            + ".", ""]
    for why in approval.get("stale_because") or []:
        out.append(f"- stale: {why}")
    out.append("")
    return "\n".join(out)


def write_markdown(root: Path | str, data: dict) -> Path:
    path = Path(root) / REPORT_MD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(data), encoding="utf-8")
    return path
