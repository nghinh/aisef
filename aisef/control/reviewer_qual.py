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


# ── G2.4b: bốn thuộc tính của một lần chặn chỉ-do-người-máy ──────────────
#
# Hợp đồng đóng dự án (`docs/PROJECT-CLOSURE-GATE.md` §5) không hỏi "tỉ lệ sai
# là bao nhiêu" — nó đã biết, và chủ dự án đã phán là tỉ lệ ấy **không** thành
# mục chặn vô điều kiện. Nó hỏi bốn câu khác, và ba câu đầu trả lời được bằng
# cách **chạy** cơ chế chứ không bằng cách đọc lời hứa. Hàm dưới đây làm thế:
# nó tự dựng một kho bằng chứng tạm, ký một miễn trừ, rồi xem cổng nói gì.

#: Một lần chặn "chỉ do người máy": tập mục **chặn cổng** của lượt ấy đúng bằng
#: `{"review"}`. Đọc được từ một sự kiện `gate:verdict` duy nhất, không cần
#: suy luận, vì mỗi mục trong bản ghi mang cả `outcome` lẫn `kind` (ADR-005 V4).
JUDGE_ONLY = "blocking checks == {'review'}"

PROPERTIES = {
    "G2.4b-i": "a judge-only block is explicitly identifiable in evidence",
    "G2.4b-ii": "it is distinguishable from deterministic blocking",
    "G2.4b-iii": "it has a human escape / override path",
    "G2.4b-iv": "it cannot masquerade as a deterministic guarantee",
}


def _gate_records(roots: dict[str, Path | str]) -> dict:
    """Đếm trên `gate:verdict` đã ghi: bao nhiêu lượt chặn, bao nhiêu chỉ do
    người máy, và mục nào thiếu `kind`. Không git, không model — chỉ đọc sổ."""
    from .outcome import Outcome
    tong = chan = rieng = so_muc = thieu_kind = 0
    theo_kind: dict[str, int] = {}
    theo_du_an: dict[str, dict[str, int]] = {}
    for ten, root in roots.items():
        store = EvidenceStore(Path(root))
        d = theo_du_an.setdefault(ten, {"gate_records": 0, "blocking": 0, "judge_only": 0})
        for story in store.stories():
            for e in store.read(story).of(NOTE, "gate:verdict"):
                muc = [c for c in (e.detail.get("checks") or []) if isinstance(c, dict)]
                if not muc:
                    continue                    # bản ghi trước V4: không có kết cục từng mục
                tong += 1
                d["gate_records"] += 1
                for c in muc:
                    so_muc += 1
                    k = str(c.get("kind") or "")
                    theo_kind[k or "(none)"] = theo_kind.get(k or "(none)", 0) + 1
                    thieu_kind += 0 if k else 1
                try:
                    khoa = {str(c.get("name")) for c in muc
                            if Outcome(str(c.get("outcome"))).blocks}
                except ValueError:
                    continue                    # kết cục lạ: không đoán
                if khoa:
                    chan += 1
                    d["blocking"] += 1
                    if khoa == {"review"}:
                        rieng += 1
                        d["judge_only"] += 1
    return {"gate_records": tong, "blocking_records": chan, "judge_only_records": rieng,
            "judge_only_share": round(rieng / chan, 4) if chan else -1.0,
            "checks_recorded": so_muc, "checks_by_kind": theo_kind,
            "checks_without_kind": thieu_kind, "by_corpus": theo_du_an}


def _exercise_waiver() -> list[tuple[str, bool]]:
    """Ký thật một miễn trừ trên kho tạm và xem cổng nói gì (iii + iv).

    Chạy cơ chế thay vì khai là có: một bảng kiểm tra nói "đã cài đặt" mà không
    bấm thử là lời khai, đúng thứ `qualification_table` sinh ra để không làm.
    """
    import tempfile
    from .gate import REVIEW_WAIVER, evaluate
    from .outcome import Outcome
    from ..harness.observe import Event

    sha, sid = "a" * 40, "S-01"
    chan = ["[block] src/a.py:10 — loses data on save"]
    kw = dict(changed=["src/a.py"], write_scope=["src"], screens=[], contract=[],
              review_blocking=chan, candidate=sha)
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(Path(tmp), candidate=sha)
        store.file_change(sid, "src/a.py")
        store.tool_run(sid, "test", ok=True)
        store.tool_run(sid, "lint", ok=True)

        def muc(ten: str, **over):
            g = evaluate(sid, EvidenceStore(Path(tmp)).read(sid), **{**kw, **over})
            return next(c for c in g.checks if c.name == ten), g

        def ky(reason: str, candidate: str = sha):
            store.record(sid, Event(kind=NOTE, name=REVIEW_WAIVER, ok=False,
                                    detail={"reason": reason, "by": "audit",
                                            "candidate": candidate}))

        # Thứ tự có chủ ý: hai miễn trừ **không hợp lệ** ký trước, để phép kiểm
        # "vẫn chặn" không thể ăn may nhờ một miễn trừ hợp lệ ký trước đó.
        truoc, _ = muc("review")
        ky("")
        khong_ly_do, _ = muc("review")
        ky("signed for another build", candidate="b" * 40)
        khac_ung_vien, _ = muc("review")
        ky("the judge misread the test layer")
        mien, _ = muc("review")
        store.tool_run(sid, "lint", ok=False, detail={"tail": "E501"})
        lint, g_lint = muc("lint")
        review_khi_lint_do, _ = muc("review")
        return [
            ("without a waiver the judge-only block is FAILED and blocks",
             truoc.outcome is Outcome.FAILED and truoc.outcome.blocks),
            ("a waiver with no reason is ignored",
             khong_ly_do.outcome is Outcome.FAILED),
            ("a waiver signed for another candidate does not apply",
             khac_ung_vien.outcome is Outcome.FAILED),
            ("a signed waiver makes the check WAIVED, and WAIVED does not block",
             mien.outcome is Outcome.WAIVED and not mien.outcome.blocks),
            ("the waived check names the person and the reason",
             "audit" in mien.detail and "misread" in mien.detail),
            ("the waived check is WAIVED, not PASSED, in the record",
             mien.as_dict()["outcome"] == "waived"),
            ("the waived check keeps kind=model-judge",
             mien.as_dict()["kind"] == "model-judge"),
            ("a waiver cannot rescue a deterministic check",
             lint.outcome is Outcome.FAILED and not g_lint.passed
             and review_khi_lint_do.outcome is Outcome.WAIVED),
            ("the waiver is read from evidence, and the check points at the event",
             bool(mien.evidence) and not truoc.evidence),
        ]


def judge_only_audit(roots: dict[str, Path | str] | None = None) -> dict:
    """Bảng kiểm tra G2.4b, máy đọc được — nguồn của
    `closure-evidence/judge-only-audit.json`.

    Bốn thuộc tính, mỗi thuộc tính là một danh sách `(câu, đúng/sai)`; `holds`
    là `all(...)` của chúng, `all_hold` là `all` của bốn. `roots` (tên dự án →
    `_bmad-output`) thêm phần `measured` đo trên bằng chứng đã ghi; không có
    `roots` thì `measured` là `None` — cài từ wheel không mang corpus theo, và
    nói "không đo được" khác nói "không có lần nào".
    """
    from .gate import CHECK_KIND, CHECK_NAMES, REVIEW_WAIVER, judge_only, review_waiver
    from .outcome import CHECK_KINDS, Outcome

    do = _gate_records(roots) if roots else None
    if do is not None:
        # Hai mẫu số, hai câu hỏi, in cả hai: `judge_only_share` là "trong các
        # lượt **cổng** chặn, bao nhiêu lượt người máy chặn một mình";
        # `review_sessions` là bảng của `rates()` — trong các lần **reviewer**
        # chặn, bao nhiêu lần không tầng nào xác nhận (`block uncorroborated`).
        # 17/122 và 21/57 là hai số khác nhau của cùng một corpus, không phải
        # một số bị tính sai.
        scored: list[tuple[Judgement, str, str]] = []
        for ten, root in roots.items():
            scored.extend(classify(read_judgements(root, project=ten)))
        do["review_sessions"] = rates(scored)
        do["corpora"] = sorted(roots)
        do["denominators"] = {
            "judge_only_share": "judge-only gate records ÷ gate records that blocked",
            "review_sessions.block uncorroborated": (
                "review sessions whose block no other layer corroborated ÷ `blocks "
                "scored`. PROJECT-CLOSURE-GATE quotes 21 of 57 (36.8 %) measured on the "
                "four todo* corpora; adding marks-cli moves the denominator, not the "
                "numerator."),
        }
    judge = [n for n, k in CHECK_KIND.items() if k == "model-judge"]
    try:
        Finding.make(source=SOURCE_REVIEWER, trust=Trust.AGENT.value, severity="high",
                     body="an agent observation")
        agent_bi_chan = False
    except ValueError:
        agent_bi_chan = True
    chay = _exercise_waiver()
    tt: dict[str, dict] = {
        "G2.4b-i": {"mechanism": "note `gate:verdict` records every check with its "
                                "`outcome` and `kind` (ADR-005 V9), so the blocking set "
                                "of one attempt is read from one event",
                    "assertions": [
                        ("the judge-only test is a named predicate over one record, "
                         f"not a reading of prose: `gate.judge_only` — {JUDGE_ONLY}",
                         callable(judge_only)),
                        ("every recorded check carries a kind",
                         do is None or do["checks_without_kind"] == 0),
                        ("the corpus contains judge-only blocks to identify",
                         do is None or do["judge_only_records"] > 0),
                        ("`reviewer_qual.classify` names the same thing per review "
                         "session as `block uncorroborated`",
                         "block uncorroborated" in CLASSES)]},
        "G2.4b-ii": {"mechanism": "`gate.CHECK_KIND` classifies every name in "
                                  "`CHECK_NAMES` into one of `outcome.CHECK_KINDS`",
                     "assertions": [
                         ("every gate check has a kind",
                          set(CHECK_KIND) == set(CHECK_NAMES)),
                         ("every kind is from the closed vocabulary",
                          all(k in CHECK_KINDS for k in CHECK_KIND.values())),
                         ("`review` is the only model-judge check", judge == ["review"]),
                         ("the other checks are deterministic, structural or security",
                          {k for n, k in CHECK_KIND.items() if n != "review"}
                          <= {"deterministic", "structural", "security"}),
                         ("the kinds are distinguishable in the record too, not only "
                          "in code", do is None or len(do["checks_by_kind"]) > 1)]},
        "G2.4b-iii": {"mechanism": f"`{REVIEW_WAIVER}` — a person signs an override at a "
                                   f"named candidate via `aisef gate <story> "
                                   f"--waive-review --reason ...`; `gate.review_waiver` "
                                   f"reads it and nothing else does",
                      "assertions": [
                          ("the override is a callable mechanism, not a description",
                           callable(review_waiver)),
                          *chay[:5]]},
        "G2.4b-iv": {"mechanism": "the override produces `Outcome.WAIVED`, a distinct "
                                  "symbol that is `counts_as_done` but never `PASSED`, "
                                  "and it is consulted only in the `review` branch",
                     "assertions": [
                         ("WAIVED and PASSED are different outcomes with different marks",
                          Outcome.WAIVED is not Outcome.PASSED
                          and Outcome.WAIVED.mark != Outcome.PASSED.mark),
                         ("an advisory finding cannot be authored with agent trust "
                          "(ADR-007 §3, same posture as `contract_authority`)",
                          agent_bi_chan),
                         *chay[5:]]},
    }
    for p in tt.values():
        p["assertions"] = [[c, bool(ok)] for c, ok in p["assertions"]]
        p["holds"] = all(ok for _, ok in p["assertions"])
    for pid, p in tt.items():
        p["statement"] = PROPERTIES[pid]
    from datetime import datetime, timezone
    return {
        "criterion": "G2.4b",
        "generated": datetime.now(timezone.utc).date().isoformat(),
        "statement": "a judge-only block is identifiable, distinguishable, overridable, "
                     "and cannot masquerade as deterministic",
        "judge_only_definition": JUDGE_ONLY,
        "regenerate": "python3 -m aisef.control.reviewer_qual --audit "
                      "<project>/_bmad-output [...]",
        "properties": tt,
        "all_hold": all(p["holds"] for p in tt.values()),
        "measured": do,
    }


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
    audit = args and args[0] == "--audit"
    if audit:
        args = args[1:]
    if not args and not audit:
        print(__doc__.splitlines()[0])
        print("dùng: python3 -m aisef.control.reviewer_qual [--audit] <_bmad-output> [...]")
        raise SystemExit(2)
    roots = {Path(a).parent.name: a for a in args}
    if audit:
        import json
        print(json.dumps(judge_only_audit(roots or None), ensure_ascii=False, indent=1))
    else:
        print(report(roots))
