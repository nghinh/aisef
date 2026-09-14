"""Bảng chứng nhận cho **phán quyết** của reviewer (ADR-009 O1).

`review` là mục duy nhất trong `gate.CHECK_NAMES` do model chấm
(`CHECK_KIND["review"] == "model-judge"`).  Ba control ở
`tests/test_gate_qualification.py` chứng nhận **mục cổng** — cổng đọc đúng
danh sách findings, chặn khi có mục chặn, gọi tên khi không đọc được.  Không
control nào chứng nhận **lời phán**: liệu mục chặn ấy là thật, và liệu một
`pass` có bỏ sót lỗi mà tầng máy bắt được.  Phép thử hợp quy C11
(`docs/RELEASE-CHECKLIST-v0.1.0.md` dòng 39) cho thấy hai tầng **lệch nhau**
— "cổng máy bắt, người máy không" — nhưng không đo tần suất, cũng không nói
lệch về phía nào.

Module này chấm phán quyết ấy trên **bằng chứng đã ghi**: mỗi phiên review
trong `_bmad-output/evidence/<story>.jsonl` là một hàng, phân loại bằng thứ
tầng khác đã chứng minh được ở **cùng ứng viên**.  Không gọi model, không
chấm lại: tất cả đã nằm trên đĩa.

Sáu lớp phán quyết (`CLASSES`), mỗi lớp có ba control
positive / negative / env ở `tests/test_reviewer_qualification.py`, bảng đọc
bằng AST qua `gate.controls_in` — cùng một bộ đọc với bảng cổng, nên hai bảng
không thể hiểu "có control" theo hai nghĩa.

Sự thật nền (ground truth), nói thẳng ra
---------------------------------------

* **false block** — có bằng chứng đảo chiều, đọc từ **kho git của dự án**,
  không từ lời khai của harness: (a) phiên review kế tiếp chấm `pass` trên
  một ứng viên mà `git diff` với ứng viên bị chặn là **rỗng** (cùng cây, ngược
  phán quyết), hay (b) lượt kế tiếp `pass` mà `git diff` giữa hai ứng viên
  **không chạm tệp nào** trong số các tệp mục chặn trỏ tới.  Sự kiện
  `file_change` *không* dùng cho việc này: đo trên todo-e2e/STORY-02-02 cho
  thấy lượt developer thứ hai không ghi `file_change` nào mà `git diff` giữa
  hai ứng viên vẫn đổi `js/app.js` — tin `file_change` thì hàng ấy bị gán oan
  là false block.  Cả hai luật đều cần một phiên kế tiếp và hai commit còn
  phân giải được, nên tỉ lệ đo được là **chặn dưới**, không phải số thật.
* **miss** — reviewer `pass` trong khi cổng máy ở **cùng lượt** trượt một mục
  nằm trong hợp đồng của reviewer (`IN_CONTRACT`, lấy từ chính prompt
  `story-review.md`).  Mục ngoài hợp đồng (lint, TDD, `criteria have tests`,
  `no baseline regression`, `security`...) được **đếm riêng** và in ra, không
  gộp vào tỉ lệ sót — chặn một reviewer vì thứ nó được bảo đừng chấm là đo sai.
* **undecided** — không chấm được: dòng do harness tự sinh ("no changes to
  review"), phiên bị huỷ (`review:immutable`, `review:candidate`), phiên
  không trả JSON, hay lượt không có `gate:verdict`.  Không bao giờ tính là
  pass — đó là điều `Outcome.must_be_named` dạy ở tầng máy.

Nhận dạng findings dùng `Finding.id` (ADR-009 §1) nên một lời phàn nàn nhắc
lại chỉ đếm một lần.  Cảnh báo đã đo: `_digest` băm cả `body`, nên id **chỉ**
gộp khi câu chữ trùng khít; viết lại bằng từ khác cho ra id khác.  Con số
"gộp được bao nhiêu" vì thế là chặn dưới, nên `rates()` in cả hai: số mục
reviewer **khai** trong JSON (sau khi gộp theo id) và số dòng cổng **đã chặn
theo** (hợp text ∪ JSON, do phiên bản harness hôm ấy tách).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from .findings import Finding, SOURCE_REVIEWER, Trust
from .gate import CONTROLS, controls_in
from ..harness.observe import AGENT_RUN, NOTE, TOOL_RUN, Evidence, EvidenceStore

#: Mục cổng nằm trong hợp đồng của reviewer — theo `kit/prompts/story-review.md`:
#: "Do the tests actually test" (→ `real tests`, `tests verify story`),
#: "Must be green on the candidate" (→ `test`), "Behaviors to preserve … is a
#: `[block]` item" (→ `preservation`).  Prompt **cấm** nó chấm `criteria have
#: tests` ("the machine already cross-checked … do not re-count") và không giao
#: cho nó lint, TDD, baseline hay security.
IN_CONTRACT = ("test", "real tests", "tests verify story", "preservation")

#: Lý do một mục FAILED **không** nói "ứng viên có lỗi".  `tests verify story`
#: trượt vì ba lý do khác nhau: "still green without story code" là lỗi thật ở
#: ứng viên, còn hai lý do dưới là *thiếu bằng chứng* — không có lần chạy test ở
#: ứng viên, hay không có test nào mang mã tiêu chí để so ở SHA cha (việc của
#: mục `criteria have tests`, thứ prompt **cấm** reviewer chấm lại).  Đo trên
#: corpus: 17 trong 44 lần `tests verify story` trượt là hai lý do ấy; tính
#: chúng thành "reviewer bỏ sót" đẩy tỉ lệ sót từ 38,6 % lên 48,6 %.  Mục
#: `test` cũng vậy: "files changed since the most recent test run" là bằng
#: chứng cũ, không phải bộ test đỏ — 2 trong 3 lần `test` trượt trên một
#: `pass` của reviewer là lý do ấy.
NOT_A_DEFECT = ("no test run at candidate", "nothing to verify at parent SHA",
                "since the most recent test run")

#: Mục cổng nói về **đường ống**, không về ứng viên: guard không chạy tới,
#: bằng chứng ghi ở build khác.  Chúng chặn story, đúng, nhưng không xác nhận
#: một mục chặn của reviewer là thật — nên không tính là "tầng máy đồng ý".
PLUMBING = ("guard ran", "evidence matches candidate")

#: Sáu lớp một phán quyết có thể nhận.  Đóng: `classify` không trả tên khác.
CLASSES = (
    "clean pass",
    "miss",
    "block corroborated",
    "block uncorroborated",
    "false block",
    "undecided",
)

#: Lý do một phiên review không được tính — harness tự ghi khi nó xảy ra.
INVALID_RUNS = ("review:immutable", "review:candidate")

_SEV = {"block": "high", "stuck": "high", "should fix": "medium", "suggestion": "low"}


@dataclass(frozen=True)
class Judgement:
    """Một phiên review đã ghi, kèm thứ các tầng khác nói ở cùng ứng viên."""

    story: str
    attempt: int
    candidate: str
    seq: int
    verdict: str
    findings: tuple[Finding, ...]
    blocking: tuple[Finding, ...]
    acted: tuple[str, ...]
    session: str
    invalid: str
    #: (tên mục, kết cục, lý do) của cổng ở đúng lượt này.  `None` = không có
    #: `gate:verdict` — tầng khác chưa nói gì, và đó là *undecided*.
    gate_checks: tuple[tuple[str, str, str], ...] | None
    #: Tệp khác nhau giữa ứng viên này và ứng viên của phiên review kế tiếp,
    #: theo `git diff`.  `()` = cùng cây; `None` = chưa/không phân giải được.
    changed_next: tuple[str, ...] | None = None
    project: str = ""
    #: Client và model của **chính phiên này**, đọc từ `agent_run`.  Corpus
    #: đo lần đầu (2026-09-14) mang `""` ở cả hai: hai trường ấy chưa được ghi,
    #: nên 145 phiên là "qua mọi client", không phải của một client nào.  Hàng
    #: cũ vẫn đọc được — rỗng nghĩa là không biết, và báo cáo nói thế.
    client: str = ""
    model: str = ""

    @property
    def engine(self) -> str:
        """`client/model` để chẻ tỉ lệ; `?` khi bản ghi không nói."""
        return f"{self.client or '?'}/{self.model or '?'}"

    @property
    def scorable(self) -> bool:
        return bool(self.session) and not self.invalid and self.verdict != "" \
            and self.gate_checks is not None

    def failed(self, names: tuple[str, ...] | None = None) -> tuple[str, ...]:
        """Mục cổng nói **ứng viên có lỗi** — FAILED, và lý do là về code.

        `UNRUNNABLE` cũng chặn cổng (`Outcome.blocks`) nhưng nói "không chạy
        được", không nói "sai"; `NOT_A_DEFECT` là những lý do FAILED mà nội dung
        cũng chỉ là thiếu bằng chứng.  Tính cả hai thành lỗi thì vừa đẩy tỉ lệ
        sót lên vừa cho một mục chặn sai được "có tầng máy xác nhận".
        """
        return tuple(n for n, o, d in (self.gate_checks or ())
                     if o == "failed" and (names is None or n in names)
                     and not any(x in d for x in NOT_A_DEFECT))


def _git(repo: Path | str, *args: str) -> str | None:
    """stdout, hay `None` khi lệnh trượt — phân biệt "không khác gì" với
    "không đọc được", vì hai thứ ấy dẫn tới hai kết luận khác nhau."""
    try:
        p = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def changed_between(repo: Path | str, a: str, b: str) -> tuple[str, ...] | None:
    """Tệp khác nhau giữa hai ứng viên.  `()` = cùng cây; `None` = không biết.

    Đọc kho git của dự án, không đọc `file_change`: hook có thể không bắt được
    lần ghi (bash, script), và khi ấy "không thấy ghi" bị đọc thành "không sửa".
    """
    if not a or not b:
        return None
    if a == b:
        return ()
    for sha in (a, b):
        if _git(repo, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}") is None:
            return None
    out = _git(repo, "diff", "--name-only", a, b)
    if out is None:
        return None
    return tuple(sorted(x.strip() for x in out.splitlines() if x.strip()))


def _line_no(raw) -> int:
    m = re.match(r"\d+", str(raw or ""))
    return int(m.group(0)) if m else 0


def _finding(story: str, item: dict) -> Finding:
    """Một findings dict đã ghi → `Finding` (id ổn định theo ADR-009 §1)."""
    tag = str(item.get("tag", "")).strip().lower()
    return Finding.make(
        source=SOURCE_REVIEWER,
        trust=Trust.REVIEWER.value,
        severity=_SEV.get(tag, "low"),
        file=str(item.get("file", "")),
        line=_line_no(item.get("line")),
        body=str(item.get("why", "")).strip(),
        behavior_id=str(item.get("behavior_id", "")),
        scope=(story,),
    )


def _is_blocking(item: dict) -> bool:
    """Tag nào là tag chặn — do `implement.Verdict` định nghĩa, không kể lại ở đây.

    `verdict="pass"` để `blocking()` không thêm mục tổng hợp "nói block mà
    không liệt kê"; còn lại đúng bộ tag chặn/bế tắc của nó.
    """
    from ..phases.implement import Verdict
    return bool(Verdict("pass", [item]).blocking())


def _dedup(items: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """Nhắc lại một lời phàn nàn chỉ đếm một lần — khoá là `Finding.id`."""
    seen: set[str] = set()
    out = []
    for f in items:
        if f.id in seen:
            continue
        seen.add(f.id)
        out.append(f)
    return tuple(out)


def judgements(ev: Evidence, *, project: str = "") -> list[Judgement]:
    """Mỗi `tool_run review` đã ghi → một hàng, theo đúng thứ tự trên đĩa."""
    rows: list[Judgement] = []
    evs = ev.events
    idx = [i for i, e in enumerate(evs) if e.kind == TOOL_RUN and e.name == "review"]
    for n, i in enumerate(idx):
        e = evs[i]
        truoc = evs[idx[n - 1] + 1:i] if n else evs[:i]          # cửa sổ của phiên này
        run = next((x for x in reversed(truoc)
                    if x.kind == AGENT_RUN and x.name.endswith("-review")), None)
        vd = next((x for x in reversed(truoc)
                   if x.kind == NOTE and x.name == "review:verdict"), None)
        bad = next((x for x in truoc if x.kind == TOOL_RUN and x.name in INVALID_RUNS), None)
        gate = next((x for x in evs[i:] if x.kind == NOTE and x.name == "gate:verdict"), None)
        items = list((vd.detail.get("findings") or []) if vd else [])
        found = _dedup(tuple(_finding(ev.story_id, it) for it in items))
        block = _dedup(tuple(_finding(ev.story_id, it) for it in items if _is_blocking(it)))
        loi = (run.detail.get("error") or "") if run else ""
        rows.append(Judgement(
            story=ev.story_id,
            attempt=int(e.detail.get("attempt") or 0),
            candidate=str(e.detail.get("candidate") or ""),
            seq=e.seq,
            verdict=str(vd.detail.get("verdict") or "") if vd else "",
            findings=found,
            blocking=block,
            acted=tuple(e.detail.get("findings") or []),
            session=str(run.detail.get("session_id") or "") if run else "",
            client=str(run.detail.get("client") or "") if run else "",
            model=str(run.detail.get("model") or "") if run else "",
            invalid=bad.name if bad else (f"review could not run: {loi}" if loi else ""),
            gate_checks=None if gate is None else tuple(
                (str(c.get("name") or ""), str(c.get("outcome") or ""), str(c.get("detail") or ""))
                for c in (gate.detail.get("checks") or ())),
            project=project,
        ))
    return rows


def read_judgements(artifact_root: Path | str, *, project: str = "",
                    repo: Path | str | None = None) -> list[Judgement]:
    """Đọc mọi story của một dự án, và hỏi git đã đổi gì giữa hai ứng viên liền nhau.

    Không gọi model: `evidence/` và kho git, cả hai đã nằm trên đĩa.
    """
    root = Path(artifact_root)
    repo = Path(repo) if repo else root.parent
    store = EvidenceStore(root)
    out: list[Judgement] = []
    for story in store.stories():
        if story.startswith("plan-") or story == "PROBE":
            continue
        hang = judgements(store.read(story), project=project or repo.name)
        for k, r in enumerate(hang[:-1]):
            hang[k] = replace(r, changed_next=changed_between(repo, r.candidate,
                                                              hang[k + 1].candidate))
        out.extend(hang)
    return out


def classify(rows: list[Judgement]) -> list[tuple[Judgement, str, str]]:
    """(hàng, lớp, vì sao) — lớp luôn thuộc `CLASSES`, lý do luôn có chữ."""
    sau = _next_map(rows)
    return [(r, *_one(r, sau.get(id(r)))) for r in rows]


def _next_map(rows: list[Judgement]) -> dict[int, Judgement]:
    """Phiên review kế tiếp của **cùng story cùng dự án**, theo thứ tự trên đĩa."""
    nhom: dict[tuple[str, str], list[Judgement]] = {}
    for r in rows:
        nhom.setdefault((r.project, r.story), []).append(r)
    sau: dict[int, Judgement] = {}
    for cung in nhom.values():
        for k, r in enumerate(cung[:-1]):
            sau[id(r)] = cung[k + 1]
    return sau


def _one(r: Judgement, nxt: Judgement | None) -> tuple[str, str]:
    if not r.session:
        return "undecided", "no review session at this attempt — the line is the harness's, not a judgement"
    if r.invalid:
        return "undecided", f"session does not count: {r.invalid}"
    if r.verdict == "":
        return "undecided", "no JSON verdict recorded — nothing machine-readable to score"
    if r.gate_checks is None:
        return "undecided", "no gate:verdict at this attempt — the other layers said nothing"
    may = tuple(x for x in r.failed() if x != "review" and x not in PLUMBING)
    if r.blocking:
        dao = bool(nxt and nxt.scorable and not nxt.blocking)
        if dao and r.changed_next == ():
            # Nói đúng cái đã làm: cùng một SHA thì `changed_between` trả `()`
            # bằng so chuỗi, không chạy `git diff` — đừng viết như thể có chạy.
            cach = (f"same candidate {r.candidate[:7]}" if r.candidate == nxt.candidate
                    else f"git diff {r.candidate[:7]}..{nxt.candidate[:7]} is empty")
            return "false block", (f"reversed on an identical tree ({cach}): "
                                   f"seq {r.seq} block → seq {nxt.seq} pass")
        noi = tuple(f.file for f in r.blocking if f.file)
        # Mục chặn có thể trỏ tệp A mà nguyên nhân nó kể lại nằm ở tệp B; sửa B
        # là đã trả lời nó.  Đo trên todo-oc/STORY-01-01 seq=2659: mục trỏ
        # `e2e/story-01-01.spec.js` (không đổi) nhưng thân mục kể `index.html`
        # (đổi) — nên hàng ấy **không** được tính là false block.
        ke_ten = any(c in f.body for c in (r.changed_next or ()) for f in r.blocking)
        if (dao and r.changed_next and len(noi) == len(r.blocking)
                and not set(noi) & set(r.changed_next) and not ke_ten):
            return "false block", (f"next attempt passed and git diff "
                                   f"{r.candidate[:7]}..{nxt.candidate[:7]} never touches "
                                   f"{', '.join(sorted(set(noi)))}")
        if may:
            return "block corroborated", f"machine gate also failed: {', '.join(may)}"
        return "block uncorroborated", "review was the only failing gate check, and nothing reversed it"
    sot = r.failed(IN_CONTRACT)
    if sot:
        return "miss", f"passed a candidate the machine gate failed on: {', '.join(sot)}"
    if nxt and nxt.scorable and nxt.blocking and r.changed_next == ():
        # Không cần tầng máy: chính reviewer chặn đúng cây ấy ở phiên sau.
        # Cặp này chứng minh **bất nhất**; quy lỗi cho phán quyết *trước* là
        # một quy ước, nói rõ ở đây: lượt sau là lượt đường ống đi theo.
        return "miss", (f"self-reversed: the next session blocked the identical tree "
                        f"(seq {r.seq} pass → seq {nxt.seq} block, git diff empty)")
    # "Cổng đồng ý" phải nói ra cái nó **không kiểm được**: một mục trong hợp
    # đồng ở trạng thái unrunnable/unconfigured là chỗ một miss có thể đang nằm,
    # và im lặng về nó chính là lỗi `Outcome.must_be_named` sinh ra để chặn.
    khong_ro = tuple(n for n, o, _ in (r.gate_checks or ())
                     if n in IN_CONTRACT and o in ("unrunnable", "unconfigured"))
    ghi = []
    if may:
        ghi.append(f"failed outside the reviewer's contract: {', '.join(may)}")
    if khong_ro:
        ghi.append(f"in-contract checks that could not conclude: {', '.join(khong_ro)} "
                   f"({', '.join(sorted({o for n, o, _ in r.gate_checks or () if n in khong_ro}))})")
    return "clean pass", "gate agreed" + (f" ({'; '.join(ghi)})" if ghi else "")


def rates(scored: list[tuple[Judgement, str, str]]) -> dict[str, float | int]:
    """Hai tỉ lệ, cả hai in ra, không cái nào trốn sau một pass."""
    dem = {c: sum(1 for _, cls, _ in scored if cls == c) for c in CLASSES}
    chan = dem["false block"] + dem["block corroborated"] + dem["block uncorroborated"]
    qua = dem["clean pass"] + dem["miss"]
    ra: dict[str, float | int] = {"total": len(scored), **dem,
                                  "blocks scored": chan, "passes scored": qua}
    # Hàng chặn mà **hỏi được** câu "có bị đảo chiều không": phải có phiên kế
    # tiếp và hai ứng viên còn phân giải được trong kho git.  Hàng không hỏi
    # được không phải hàng đúng — nó là chỗ một false block có thể đang nằm,
    # nên tỉ lệ in cả hai mẫu số.
    hoi_duoc = sum(1 for r, cls, _ in scored
                   if cls.startswith(("block", "false")) and r.changed_next is not None)
    ra["blocks whose reversal was testable"] = hoi_duoc
    ra["false block rate"] = round(dem["false block"] / chan, 4) if chan else -1.0
    ra["false block rate (testable only)"] = (
        round(dem["false block"] / hoi_duoc, 4) if hoi_duoc else -1.0)
    ra["miss rate"] = round(dem["miss"] / qua, 4) if qua else -1.0
    # Số không phụ thuộc quy ước nào: cùng một cây, hai phiên liền nhau, bao
    # nhiêu lần đổi phán quyết.  Đây là độ **lặp lại** của người máy.
    sau = _next_map([r for r, _, _ in scored])
    cung_cay = [(r, sau[id(r)]) for r, _, _ in scored
                if r.changed_next == () and id(r) in sau
                and r.scorable and sau[id(r)].scorable]
    ra["same-tree consecutive pairs"] = len(cung_cay)
    ra["same-tree verdict reversals"] = sum(1 for a, b in cung_cay
                                            if bool(a.blocking) != bool(b.blocking))
    ra["undecided share"] = round(dem["undecided"] / len(scored), 4) if scored else -1.0
    # Nhắc lại gộp được bao nhiêu: `Finding.id` băm cả `body` nên đây là chặn dưới.
    khai = sum(len(r.findings) for r, _, _ in scored)
    hanh = sum(len(r.acted) for r, _, _ in scored)
    ra["findings declared (id-deduped)"] = khai
    ra["lines the gate acted on"] = hanh
    return ra


def qualification_table(test_file: Path | None = None) -> dict[str, dict[str, bool]]:
    """Bảng chứng nhận phán quyết: lớp -> control nào có, đọc bằng AST.

    Cùng bộ đọc với `gate.qualification_table()`.  Cài từ wheel không có
    `tests/` -> trả rỗng, báo cáo in `?` chứ không in 0.
    """
    path = test_file or Path(__file__).resolve().parents[2] / "tests" / "test_reviewer_qualification.py"
    return controls_in(path, CLASSES)


def report(roots: dict[str, Path | str]) -> str:
    """Markdown: bảng ba control, đếm theo lớp, hai tỉ lệ, và hàng dẫn chứng."""
    scored: list[tuple[Judgement, str, str]] = []
    for ten, root in roots.items():
        scored.extend(classify(read_judgements(root, project=ten)))
    bang = qualification_table()
    ra = [f"| class | {' | '.join(CONTROLS)} |", "|---|" + "---|" * len(CONTROLS)]
    for cls in CLASSES:
        cot = bang.get(cls)
        ra.append(f"| {cls} | " + " | ".join(
            ("?" if cot is None else ("✅" if cot[c] else "—")) for c in CONTROLS) + " |")
    so = rates(scored)
    ra.append("")
    ra.append("| project | " + " | ".join(CLASSES) + " |")
    ra.append("|---|" + "---|" * len(CLASSES))
    for ten in roots:
        hang = [j for j in scored if j[0].project == ten]
        ra.append(f"| {ten} ({len(hang)}) | " + " | ".join(
            str(sum(1 for _, c, _ in hang if c == cls)) for cls in CLASSES) + " |")
    ra.append(f"| **all ({len(scored)})** | " + " | ".join(
        f"**{so[cls]}**" for cls in CLASSES) + " |")
    # Chẻ theo client/model **chỉ khi** corpus có hơn một: một cột lặp lại
    # `?/?` không nói gì, và in nó ra đọc thành "đã chẻ rồi" (cùng quy ước với
    # mục token của báo cáo bench).
    dong_co = sorted({j[0].engine for j in scored})
    if len(dong_co) > 1:
        ra.append("")
        ra.append("| client/model | " + " | ".join(CLASSES) + " |")
        ra.append("|---|" + "---|" * len(CLASSES))
        for dc in dong_co:
            hang = [j for j in scored if j[0].engine == dc]
            ra.append(f"| {dc} ({len(hang)}) | " + " | ".join(
                str(sum(1 for _, c, _ in hang if c == cls)) for cls in CLASSES) + " |")
    elif dong_co:
        ra.append("")
        ra.append(f"Toàn corpus mang một `client/model`: `{dong_co[0]}` — "
                  "tỉ lệ dưới đây **không** chẻ được theo engine.")
    ra.append("")
    for k, v in so.items():
        ra.append(f"- {k}: {v}")
    for cls in ("false block", "miss", "block uncorroborated"):
        ra.append(f"\n**{cls}**")
        for r, c, why in scored:
            if c == cls:
                ra.append(f"- `{r.project}/{r.story}#{r.attempt}` seq={r.seq} "
                          f"cand={r.candidate[:7]} — {why}")
    return "\n".join(ra)


if __name__ == "__main__":                                      # pragma: no cover
    import sys
    args = sys.argv[1:]
    if not args:
        print(__doc__.splitlines()[0])
        print("dùng: python3 -m aisef.control.reviewer_qual <_bmad-output> [...]")
        raise SystemExit(2)
    print(report({Path(a).parent.name: a for a in args}))
