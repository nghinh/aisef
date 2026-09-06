"""Cổng story — điều kiện để một story được coi là xong.

Cổng đọc **bằng chứng**, không đọc lời agent kể. Agent nào cũng kết thúc
bằng câu "đã hoàn thành"; câu đó không mang thông tin. Thứ mang thông tin
là: có lần chạy test nào không, nó xanh hay đỏ, chạy trước hay sau lần sửa
cuối, cây git có nằm trong phạm vi không, màn hình thật có đủ component đã
hứa không.

Năm điều kiện, mỗi điều kiện trả lời được bằng dữ liệu có sẵn:

1. test xanh, và xanh **sau** lần sửa file cuối cùng;
2. lint sạch;
3. thay đổi nằm trong ``write_scope``;
4. màn hình khớp hợp đồng thị giác (chỉ story có giao diện);
5. rà soát độc lập không còn mục chặn;
6. không có test giả — test không khẳng định gì làm điều kiện 1 rỗng nghĩa;
7. bảo toàn (ADR-004 R4) — hành vi VERIFIED của story khác mà story này
   chạm tệp vẫn xanh ở đúng ứng viên; không kiểm được thì nói là không
   kiểm được, không nói là đạt.
8. không làm đỏ test có sẵn — test xanh ở baseline (trước khi story chạm
   vào) phải còn xanh và còn tồn tại ở ứng viên (ADR-004 R9).
9. test có kiểm được story (nop control, ADR-005 V3) — test mang mã tiêu
   chí phải **đỏ khi không có mã của story**: không xanh sẵn ở baseline
   (cấp 1, $0) và đỏ hoặc không tồn tại ở SHA cha với tệp test chép vào
   (cấp 2, một lần sandbox). Xanh cả hai nơi là một cái tên, không phải
   một phép kiểm.

Danh sách **đóng** tên mục là `CHECK_NAMES`; mỗi mục có `kind` (ai chấm —
`CHECK_KIND`) và `evidence` (seq sự kiện đã đọc); mỗi tên có ba control ở
`tests/test_gate_qualification.py`, bảng đọc bằng `qualification_table()`
(ADR-005 V9).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from ..harness.guardrails import check_completion, check_diff_scope
from .acceptance import ac_code, coverage as ac_coverage, missing as ac_missing
from .outcome import Check, Outcome
from .tdd import red_before_green
from .security import DEFAULT_BLOCKING
from ..harness.observe import FILE_CHANGE, GUARD_BLOCK, GUARD_SEEN, MOCKUP_MAP, NOTE, TOOL_RUN, Event, Evidence
from ..harness.testlog import MAX_IDS
from ..harness.tools import BASELINE_RUN, NOP_RUN

#: Tên mục cổng story — danh sách **đóng** (ADR-005 V9). Mọi `Check(...)` trong
#: tệp này phải dùng tên ở đây (test meta grep AST), và mỗi tên có ba control
#: positive · negative · env ở `tests/test_gate_qualification.py`. `<kind>` là
#: **họ** mục theo hợp đồng kiểm định: tên mục thật là tên loại (`e2e`,
#: `accessibility`, `perf`… — `phases/qa.py::KINDS` trừ unit/mockup-map/security
#: đã có mục riêng). Chừa chỗ: **"test có kiểm được story"** (nop control,
#: ADR-005 V3, luồng X3) — thêm `_nop_check` thì thêm tên vào đây và
#: `CHECK_KIND` cùng một commit, không thì test meta đỏ.
CHECK_NAMES = (
    "bằng chứng đúng candidate",
    "guard có chạy",
    "test",
    "không làm đỏ test có sẵn",
    "lint",
    "phạm vi ghi",
    "map mockup",
    "test thật",
    "tiêu chí có test",
    "coverage",
    "TDD",
    "<kind>",
    "bảo mật",
    "rà soát",
    "bảo toàn",
)

#: Ai chấm mục nào — một chỗ, giá trị thuộc `outcome.CHECK_KINDS`. Máy tất
#: định đọc kết quả runner; máy so cấu trúc (phạm vi tệp, tên test, DOM,
#: dấu vết guard, SHA); rà soát bảo mật; model làm giám khảo. Chưa mục nào
#: `human`.
CHECK_KIND = {
    "bằng chứng đúng candidate": "structural",
    "guard có chạy": "structural",
    "test": "deterministic",
    "không làm đỏ test có sẵn": "deterministic",
    "lint": "deterministic",
    "phạm vi ghi": "structural",
    "map mockup": "structural",
    "test thật": "structural",
    "tiêu chí có test": "structural",
    "coverage": "deterministic",
    "TDD": "deterministic",
    "<kind>": "deterministic",
    "bảo mật": "security",
    "rà soát": "model-judge",
    "bảo toàn": "deterministic",
}

#: Ba control chứng nhận một mục (Inspect `tests/scorer/*`, TB oracle/nop):
#: positive (bằng chứng tốt → PASSED/NOT_APPLICABLE có tên), negative/mutant
#: (bằng chứng xấu → FAILED, hay chặn khi thiết kế mục không có FAILED), env
#: (môi trường/cấu hình không cho kết luận → kết cục có tên, không phải đạt).
CONTROLS = ("positive", "negative", "env")

#: Bản ghi của `--verify-only --repeat k` (ADR-004 R13): phép kiểm nào đổi
#: kết cục giữa k lần chạy trên cùng SHA. Ghi ở `implement._repeat_note`.
REPEAT_NOTE = "verify-only.repeat"


@dataclass
class StoryGate:
    story_id: str
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(c.outcome.blocks for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.outcome.blocks]

    def summary(self) -> str:
        head = f"cổng story {self.story_id}: {'ĐẠT' if self.passed else 'KHÔNG ĐẠT'}"
        return "\n".join([head, *(c.line() for c in self.checks)])

    def feedback(self) -> str:
        """Phần đưa lại cho agent ở lượt thử tiếp theo."""
        return "\n".join(f"- {c.name}: {c.detail}" for c in self.failures)


def _stale_candidates(evidence: Evidence, candidate: str) -> list[str]:
    """Bản cũ mà **kết quả mới nhất** của một phép kiểm còn dính vào.

    So theo từng phép kiểm (kind + tên), không theo cả tệp bằng chứng: lượt
    trước để lại kết quả ở bản trước, và điều đó là bình thường — chạy lại
    trên bản mới là đủ. Cái không bình thường là phép kiểm **mới nhất** vẫn
    thuộc bản khác: nghĩa là mã đã đổi sau khi kiểm.
    """
    return sorted({str(e.detail["candidate"]) for e in _latest_per_check(evidence).values()
                   if str(e.detail["candidate"]) != candidate})


def _latest_per_check(evidence: Evidence) -> dict[tuple[str, str], Event]:
    """Kết quả **mới nhất** của từng phép kiểm (kind + tên) có khai bản —
    chính những sự kiện mục "bằng chứng đúng candidate" đọc, nên `evidence`
    của mục ấy trỏ vào đây."""
    moi_nhat: dict[tuple[str, str], Event] = {}
    for e in evidence.events:
        if e.kind in (TOOL_RUN, MOCKUP_MAP) and e.detail.get("candidate"):
            moi_nhat[(e.kind, e.name)] = e
    return moi_nhat


def _ten(tests: list[str], n: int = 5) -> str:
    return ", ".join(tests[:n]) + (f" (+{len(tests) - n})" if len(tests) > n else "")


def _flaky_ids(evidence: Evidence) -> list[str]:
    """Tên test đổi kết cục giữa k lần chạy trên cùng SHA (`--repeat k`)."""
    note = evidence.last(NOTE, REPEAT_NOTE)
    return [str(t) for t in (note.detail.get("flaky_ids") or [])] if note else []


def _khong_on_dinh(evidence: Evidence, name: str) -> str:
    """Lý do "không ổn định" cho mục ``name`` từ bản ghi `--repeat k`; rỗng
    nếu không có gì để nói.

    Mã không đổi giữa k lần mà kết cục đổi thì đó không phải đỏ (không có
    gì để sửa trong mã) và cũng không phải đạt (không chạy được ổn định) →
    UNRUNNABLE, nêu tên — lỗi 22: `autosave.spec.ts:210` nhạy tải máy làm
    e9 STORY-01-07 trượt lượt 3 rồi đo lại 10/10 xanh. Đỏ ở **mọi** lần
    (`stable_red`) là đỏ thật: không xếp vào đây, lần cuối đỏ và mục "test"
    chấm FAILED như thường. Phép kiểm không in tên test (lint, `qa:<kind>`)
    so cả phép: `ok` đổi giữa các lần là không ổn định.
    """
    note = evidence.last(NOTE, REPEAT_NOTE)
    if note is None:
        return ""
    d = note.detail
    if name == "test" and d.get("stable_red"):
        return ""
    lat = _flaky_ids(evidence) if name == "test" else []
    if not lat and name not in (d.get("flaky_checks") or []):
        return ""
    return (
        f"không ổn định qua {d.get('k')} lần chạy trên cùng SHA"
        + (f": {_ten(lat)}" if lat else "")
        + " — không chạy được ổn định không phải trượt, cũng không phải đạt"
    )


def _la(test_id: str) -> str:
    """Tiêu đề lá của một test id: phần sau dấu `>` cuối, bỏ mã `AC_…:` đứng đầu."""
    la = test_id.rsplit(">", 1)[-1].strip()
    if ":" in la and la.split(":", 1)[0].replace("_", "-").upper().startswith("AC-"):
        la = la.split(":", 1)[1].strip()
    return la


def _baseline_check(evidence: Evidence, candidate: str) -> Check:
    """Mục "không làm đỏ test có sẵn" (ADR-004 R9).

    Mục "test" chỉ nói lần chạy cuối xanh hay đỏ. Đỏ vì test **mới** của
    story (TDD, đang đỏ đúng nghĩa) và đỏ vì test **có sẵn** vừa bị làm hỏng
    trông y hệt nhau ở đó — mà cách sửa khác nhau, và cái thứ hai là hồi quy
    cần gọi đúng tên. Nên so hai danh sách tên: test xanh ở baseline (harness
    chạy trước phiên developer, `test:baseline`) với lần test mới nhất ở ứng
    viên. Xanh trước mà đỏ hoặc mất sau → hồi quy, nêu tên. Test đã đỏ sẵn ở
    baseline không tính — nói ra là không tính.

    Kết cục theo đúng bất biến: không có baseline vì **chưa khai lệnh test**
    hay reporter **không in tên** là chưa cấu hình (không đạt, không chặn,
    phải hiện ra); baseline **không chạy được** (công cụ chưa cài) là không
    chạy được (chặn với lý do môi trường, không phải "story làm đỏ"); tắt
    bởi `verify.baseline` hay harness không ghi baseline nào là không áp
    dụng, có nói lý do. Test **mất** là hồi quy: xoá hay đổi tên test có sẵn
    phải là quyết định khai trong story, mà story chưa có chỗ khai — không
    suy được thì không cho qua, và nói rõ vì sao.
    """
    ten = "không làm đỏ test có sẵn"
    goc = evidence.last(TOOL_RUN, BASELINE_RUN)
    if goc is None:
        return Check(ten, Outcome.NOT_APPLICABLE,
                     "harness không ghi baseline nào (chạy tay, nhật ký cũ) — không so được")
    doc = [goc.seq]     # sự kiện đã đọc: baseline, rồi lần test ở ứng viên
    if goc.detail.get("disabled"):
        return Check(ten, Outcome.NOT_APPLICABLE, "tắt bởi cấu hình `verify.baseline`", evidence=doc)
    if goc.detail.get("skipped"):
        return Check(ten, Outcome.UNCONFIGURED, f"không có baseline: {goc.detail['skipped']}", evidence=doc)
    if goc.detail.get("unrunnable"):
        return Check(ten, Outcome.UNRUNNABLE,
                     f"baseline không chạy được ({goc.detail['unrunnable']}) — không so được test có sẵn",
                     evidence=doc)
    if not goc.detail.get("test_format"):
        return Check(ten, Outcome.UNCONFIGURED, str(goc.detail.get("test_note") or "")
                     or "không đọc được tên test ở baseline — dùng reporter in tên "
                        "(`node --test`, `vitest --reporter=verbose`, `pytest -v`, CTRF)",
                     evidence=doc)

    # Lần test ở ứng viên: sau baseline, và đúng bản đang chấm (có candidate
    # thì không nhận lần chạy tay không khai bản).
    sau = [e for e in evidence.of(TOOL_RUN, "test")
           if e.seq > goc.seq and (not candidate or e.detail.get("candidate") == candidate)]
    if not sau:
        return Check(ten, False, "chưa có lần test nào ở ứng viên sau baseline — không so được",
                     evidence=doc)
    moi = sau[-1]
    doc.append(moi.seq)
    if moi.detail.get("unrunnable"):
        return Check(ten, Outcome.UNRUNNABLE,
                     f"lần test ở ứng viên không chạy được ({moi.detail['unrunnable']}) — không so được",
                     evidence=doc)
    if not moi.detail.get("test_format"):
        return Check(ten, Outcome.UNCONFIGURED, str(moi.detail.get("test_note") or "")
                     or "không đọc được tên test ở ứng viên — dùng reporter in tên", evidence=doc)

    goc_ids = list(goc.detail.get("test_ids") or [])
    khong_xanh = set(goc.detail.get("failed_ids") or []) | set(goc.detail.get("skipped_ids") or [])
    xanh_goc = [t for t in goc_ids if t not in khong_xanh]
    # `--repeat k`: test đổi kết cục giữa k lần ở ứng viên không phải "làm
    # đỏ" — mục "test" đã ghi UNRUNNABLE nêu tên; ở đây không tính, và nói ra.
    lat = _flaky_ids(evidence)
    do = set(moi.detail.get("failed_ids") or []) - set(lat)
    con = set(moi.detail.get("test_ids") or [])
    lam_do = [t for t in xanh_goc if t in do]
    # ponytail: testlog cắt danh sách ở MAX_IDS — bộ test lớn hơn thế thì
    # "mất" không kết luận được (tên có thể nằm ngoài phần cắt), chỉ so đỏ.
    cat = len(goc_ids) >= MAX_IDS or len(con) >= MAX_IDS
    # Đổi tên ≠ mất: cùng tiêu đề lá (phần sau dấu `>` cuối) còn ở ứng viên
    # thì test vẫn đó, chỉ mang tên nhóm/mã khác. e9 01-07 lượt 2 (2026-09-06):
    # developer thêm mã `AC_STORY_01_01_6:` vào bốn test có sẵn để đóng GAP
    # của story khác — cổng đọc thành "mất 4 test". Xoá thật thì tiêu đề lá
    # cũng mất, vẫn bị bắt.
    la_con = {_la(t) for t in con}
    doi_ten = [] if cat else [t for t in xanh_goc if t not in con and _la(t) in la_con]
    mat = [] if cat else [t for t in xanh_goc if t not in con and _la(t) not in la_con]
    if lam_do or mat:
        loi = []
        if lam_do:
            loi.append(f"làm đỏ {len(lam_do)} test xanh ở baseline: {_ten(lam_do)}")
        if mat:
            loi.append(f"mất {len(mat)} test có ở baseline: {_ten(mat)} — xoá hay đổi tên "
                       "test có sẵn phải là quyết định khai trong story; bằng chứng không "
                       "suy được nên tính là hồi quy")
        return Check(ten, False, "; ".join(loi), evidence=doc)
    do_san = list(goc.detail.get("red_before") or goc.detail.get("failed_ids") or [])
    if doi_ten:
        return Check(ten, True, f"{len(doi_ten)} test đổi tên nhưng còn tiêu đề lá, không tính là mất: {_ten(doi_ten)}",
                     evidence=doc)
    if do_san:
        return Check(ten, True, f"{len(do_san)} test đã đỏ sẵn ở baseline, không tính: {_ten(do_san)}",
                     evidence=doc)
    if lat:
        return Check(ten, True, f"{len(lat)} test không ổn định không tính ở đây (xem mục test): {_ten(lat)}",
                     evidence=doc)
    if cat:
        return Check(ten, True, f"danh sách test bị cắt ở {MAX_IDS} tên — chỉ so được test đỏ, không so được test mất",
                     evidence=doc)
    return Check(ten, True, evidence=doc)


def _nop_check(evidence: Evidence, story_id: str, *, acceptance: int, candidate: str) -> Check:
    """Mục "test có kiểm được story" — nop control (ADR-005 V3).

    Câu hỏi của Terminal-Bench (nop < 1), BERBench (`base_fail`) và Agentless
    (reproduction test): **không có mã của story thì test của story phải
    đỏ**. `TDD` chỉ hỏi "có một lần đỏ bất kỳ trước lần xanh cuối" — một lần
    đỏ vì lỗi cú pháp cũng qua. Ở đây hỏi thẳng hai cấp, cấp rẻ trước:

    **Cấp 1 ($0, từ `test:baseline` R9):** test mang `AC-<story>-i` xanh ở
    ứng viên mà đã xanh ở baseline — cùng tên, hoặc tên cũ mất và tiêu đề
    lá (`_la`) còn nguyên, tức đổi tên để gắn mã — là "gắn mã vào test có
    sẵn" (lỗi 23 → 24: developer gắn mã vào bốn test có sẵn để cổng thôi
    kêu): nó xanh **trước khi story viết dòng nào**, nên không kiểm được gì
    của story. Không nới cho trường hợp "story chỉ sửa/đổi tên test có sẵn"
    dù thân test có thể đã đổi: bằng chứng $0 chỉ thấy tên, mã tiêu chí là
    hợp đồng theo **tên** (mục *tiêu chí có test*), và cấp 2 — thứ nhìn
    được thân test — không phải lúc nào cũng chạy (`verify.nop` tắt, không
    dựng được SHA cha). Nới ở đây là để lọt đúng lớp lỗi V3 sinh ra để
    bắt; cách sửa rẻ (một lượt): viết test **mới** mang mã, giữ test có sẵn
    nguyên tên. Không bắt oan: test mới trùng tiêu đề lá với test có sẵn
    **còn nguyên tên** ở ứng viên là hai test khác nhau — để cấp 2 xét.
    Baseline của lượt chạy lại đứng ở bản của chính story (`parent` ≠
    `base_ref`, e9 01-07 lần chạy 3) thì mọi test của story đã xanh sẵn —
    cấp 1 không so được, nói ra, cấp 2 quyết (worktree ở đúng điểm rẽ).

    **Cấp 2 (`test:nop`, harness chạy sau đóng băng):** ở SHA cha với tệp
    test story thêm/sửa chép vào, test mang mã phải **đỏ hoặc không tồn
    tại** — lỗi import ở SHA cha là đỏ, và là hợp lệ. Xanh → FAILED nêu tên.
    Kết cục khác theo bất biến: nop không chạy được → UNRUNNABLE; reporter
    không in tên (chỉ biết bộ test đỏ, không biết của ai) → UNCONFIGURED;
    story không thêm/sửa tệp test, tắt bởi `verify.nop`, hay harness không
    ghi nop nào (nhật ký trước V3) → NOT_APPLICABLE có lý do.
    """
    ten = "test có kiểm được story"
    goc = evidence.last(TOOL_RUN, BASELINE_RUN)
    sau = [e for e in evidence.of(TOOL_RUN, "test")
           if (goc is None or e.seq > goc.seq)
           and (not candidate or e.detail.get("candidate") == candidate)]
    moi = sau[-1] if sau else None

    # Test mang mã tiêu chí **xanh** ở ứng viên — đối tượng của cả hai cấp.
    ac: list[str] = []
    if moi is not None and moi.detail.get("test_format") and acceptance > 0:
        do = set(moi.detail.get("failed_ids") or []) | set(moi.detail.get("skipped_ids") or [])
        xanh_moi = [t for t in moi.detail.get("test_ids") or [] if t not in do]
        for tests in ac_coverage(story_id, acceptance, xanh_moi).values():
            ac.extend(t for t in tests if t not in ac)

    # ---- cấp 1
    cap1 = ""
    if ac and goc is not None and goc.detail.get("test_format"):
        re_nhanh, cha = str(goc.detail.get("base_ref") or ""), str(goc.detail.get("parent") or "")
        if re_nhanh and cha and re_nhanh != cha:
            cap1 = (f"cấp 1 không so được: baseline chạy ở {cha[:7]} — bản của chính story "
                    f"(lượt chạy lại), không phải điểm rẽ {re_nhanh[:7]}")
        else:
            goc_ids = list(goc.detail.get("test_ids") or [])
            khong_xanh = set(goc.detail.get("failed_ids") or []) | set(goc.detail.get("skipped_ids") or [])
            xanh_goc = {t for t in goc_ids if t not in khong_xanh}
            con = set(moi.detail.get("test_ids") or [])
            gan = [t for t in ac if t in xanh_goc]
            cat = len(goc_ids) >= MAX_IDS or len(con) >= MAX_IDS
            la_mat = set() if cat else {_la(t) for t in xanh_goc if t not in con}
            doi = [t for t in ac if t not in goc_ids and _la(t) in la_mat]
            loi = []
            if gan:
                loi.append(f"gắn mã vào test có sẵn: {len(gan)} test mang mã tiêu chí đã xanh ở "
                           f"baseline với đúng tên này — xanh trước khi story viết dòng nào: {_ten(gan)}")
            if doi:
                loi.append(f"đổi tên test có sẵn để mang mã: {len(doi)} test đã xanh ở baseline dưới "
                           f"tên cũ — mã tiêu chí thành một cái tên, không phải một phép kiểm: {_ten(doi)}")
            if loi:
                return Check(ten, False, "; ".join(loi) + ". Viết test mới cho tiêu chí, giữ test có sẵn nguyên tên")

    # ---- cấp 2
    nop = evidence.last(TOOL_RUN, NOP_RUN)
    if nop is None:
        return Check(ten, Outcome.NOT_APPLICABLE,
                     "harness không chạy nop nào (chạy tay, nhật ký trước ADR-005 V3) — không so được")
    d = nop.detail
    if d.get("disabled"):
        return Check(ten, Outcome.NOT_APPLICABLE, "tắt bởi cấu hình `verify.nop`")
    if d.get("skipped"):
        if "files" in d and not d["files"]:
            return Check(ten, Outcome.NOT_APPLICABLE, "story không thêm/sửa tệp test")
        return Check(ten, Outcome.UNCONFIGURED, f"không có nop: {d['skipped']}")
    if d.get("unrunnable") and not d.get("test_format"):
        return Check(ten, Outcome.UNRUNNABLE,
                     f"nop ở SHA cha không chạy được ({d['unrunnable']}) — không so được")
    cha = str(d.get("parent") or "")[:7] or "cha"
    if moi is None:
        return Check(ten, False, "chưa có lần test nào ở ứng viên — chưa biết test nào xanh để so với SHA cha")
    if d.get("test_format") and moi.detail.get("test_format") and acceptance > 0:
        if not ac:
            return Check(ten, False, "chưa có test nào mang mã tiêu chí xanh ở ứng viên — không có gì "
                                     "để kiểm ở SHA cha (xem mục tiêu chí có test)")
        khong = set(d.get("failed_ids") or []) | set(d.get("skipped_ids") or [])
        xanh_nop = {t for t in d.get("test_ids") or [] if t not in khong}
        van_xanh = [t for t in ac if t in xanh_nop]
        if van_xanh:
            return Check(ten, False, f"test không kiểm được gì — xanh cả khi không có mã của story "
                                     f"(SHA cha {cha}): {_ten(van_xanh)}")
        return Check(ten, True, f"{len(ac)} test mang mã tiêu chí đỏ hoặc không tồn tại ở SHA cha {cha}"
                                + (f"; {cap1}" if cap1 else ""))
    if nop.ok:
        return Check(ten, False, f"bộ test xanh ở SHA cha {cha} với tệp test của story chép vào — "
                                 f"test của story không kiểm được gì ({_ten(list(d.get('files') or []), 3)})")
    if acceptance <= 0:
        return Check(ten, True, f"bộ test đỏ ở SHA cha {cha} — story không khai tiêu chí, không so theo mã")
    return Check(ten, Outcome.UNCONFIGURED,
                 "không đọc được tên test — chỉ biết bộ test đỏ ở SHA cha, không biết có phải test của "
                 "story; dùng reporter in tên (`node --test`, `vitest --reporter=verbose`, `pytest -v`)")


def evaluate(
    story_id: str,
    evidence: Evidence,
    *,
    changed: list[str],
    write_scope: list[str],
    screens: list[str],
    contract: list[str] | None = None,
    review_blocking: list[str] | None = None,
    review_ran: bool = True,
    security=None,
    block_severities=None,
    guard_expected: bool = False,
    acceptance: int = 0,
    coverage_min: float | None = None,
    added_tests: list[str] | None = None,
    candidate: str = "",
    preservation: list[dict] | None = None,
) -> StoryGate:
    """Chấm một story từ bằng chứng đã ghi.

    ``candidate`` là SHA của bản đang chấm (ADR-004 R1). Truyền vào thì
    bằng chứng ghi ở bản khác **không được dùng để chấm**, và cổng nói ra
    điều đó thay vì im lặng chấm bằng số liệu của mã đã không còn. Rỗng =
    không kiểm (chạy tay, nhật ký cũ).

    ``preservation`` là hành vi VERIFIED của story khác mà story này chạm
    tệp (ADR-004 R4, `implement.preservation_items`). Rỗng = không áp dụng,
    nên chỗ gọi cũ không đổi kết cục.
    """
    gate = StoryGate(story_id=story_id)

    stale = _stale_candidates(evidence, candidate) if candidate else []
    moi_nhat = _latest_per_check(evidence)
    if not candidate:
        gate.checks.append(Check(
            "bằng chứng đúng candidate", Outcome.NOT_APPLICABLE,
            "không truyền candidate — không kiểm được bằng chứng thuộc bản nào",
        ))
    elif stale:
        gate.checks.append(Check(
            "bằng chứng đúng candidate", Outcome.UNRUNNABLE,
            f"stale: ghi ở {', '.join(s[:7] for s in stale)}, "
            f"ứng viên hiện tại là {candidate[:7]} — chạy lại phép kiểm trên bản này",
            evidence=[e.seq for e in moi_nhat.values() if str(e.detail["candidate"]) != candidate],
        ))
    else:
        gate.checks.append(Check("bằng chứng đúng candidate", True,
                                 evidence=[e.seq for e in moi_nhat.values()]))
    if candidate:
        # Sau khi đã nói ra, bỏ hẳn: một phép kiểm của bản khác không được
        # âm thầm làm mục nào đó thành đạt.
        evidence = evidence.for_candidate(candidate)

    # Hook sinh ra ≠ hook chạy. Claude Code chỉ đọc `.claude/settings.json`
    # của cây nó đứng; worktree không có thư mục ấy (dự án không commit) thì
    # story chạy với zero guard — và bằng chứng trông y hệt agent ngoan, vì
    # không có gì để ghi. Nay guard tự ghi `GUARD_BLOCK`/`FILE_CHANGE`, nên
    # "guard chưa từng đánh giá một thao tác ghi nào" là điều đo được.
    if not guard_expected:
        gate.checks.append(Check(
            "guard có chạy", Outcome.NOT_APPLICABLE,
            "chưa biên dịch hook cho client này — không kỳ vọng",
        ))
    else:
        # Dấu vết đầu tiên là đủ để trả lời "hook có tới không".
        dau_vet = evidence.of(GUARD_SEEN) or evidence.of(GUARD_BLOCK) or evidence.of(FILE_CHANGE)
        gate.checks.append(Check(
            "guard có chạy", evidence.guard_reached,
            "" if evidence.guard_reached else (
                "guard chưa đánh giá thao tác ghi nào trong phiên — hook không "
                "tới được worktree? (.claude/ chưa commit, hoặc --settings không "
                "được truyền). Story không ghi gì cũng rơi vào đây, và đó là đúng."
            ),
            evidence=[dau_vet[0].seq] if dau_vet else [],
        ))

    completion = check_completion(evidence)
    last_test = evidence.last(TOOL_RUN, "test")
    # `completion` đọc lần test cuối và tệp sửa **sau** nó — trỏ đúng hai thứ ấy.
    doc_test = ([last_test.seq] + [e.seq for e in evidence.of(FILE_CHANGE) if e.seq > last_test.seq]
                if last_test is not None else [])
    lat = _khong_on_dinh(evidence, "test")
    if last_test is not None and last_test.detail.get("unrunnable"):
        gate.checks.append(Check("test", Outcome.UNRUNNABLE, str(last_test.detail["unrunnable"]),
                                 evidence=doc_test))
    elif lat:
        gate.checks.append(Check("test", Outcome.UNRUNNABLE, lat, evidence=doc_test))
    else:
        gate.checks.append(Check("test", completion.allowed, completion.reason.split("\n")[0],
                                 evidence=doc_test))
    gate.checks.append(_baseline_check(evidence, candidate))

    lint = evidence.last(TOOL_RUN, "lint")
    if lint is None:
        gate.checks.append(Check("lint", False, "chưa chạy lint lần nào"))
    elif lint.detail.get("skipped"):
        gate.checks.append(
            Check("lint", Outcome.UNCONFIGURED, str(lint.detail["skipped"]), evidence=[lint.seq])
        )
    elif _khong_on_dinh(evidence, "lint"):
        gate.checks.append(Check("lint", Outcome.UNRUNNABLE, _khong_on_dinh(evidence, "lint"),
                                 evidence=[lint.seq]))
    else:
        gate.checks.append(
            Check("lint", lint.ok, "" if lint.ok else str(lint.detail.get("tail", ""))[:300],
                  evidence=[lint.seq])
        )

    # Suy từ tham số (`changed`, `write_scope` — cây git do `run_attempt` đọc),
    # không từ sự kiện: `evidence` rỗng, và rỗng là đúng.
    scope = check_diff_scope(changed, write_scope)
    gate.checks.append(Check("phạm vi ghi", scope.allowed, scope.reason))

    if not screens:
        gate.checks.append(Check("map mockup", Outcome.NOT_APPLICABLE, "story không có giao diện"))
    else:
        maps = {e.name: e for e in evidence.of(MOCKUP_MAP)}
        doc_map = [maps[s].seq for s in screens if s in maps]
        missing_runs = [s for s in screens if s not in maps]
        if missing_runs:
            gate.checks.append(
                Check("map mockup", False, f"chưa đối chiếu: {', '.join(missing_runs)}", evidence=doc_map)
            )
        else:
            failed = [s for s in screens if not maps[s].ok]
            detail = ""
            if failed:
                first = maps[failed[0]].detail
                detail = (
                    f"{failed[0]} thiếu: "
                    + ", ".join(first.get("missing", []) + first.get("missing_data_roles", []))
                )
            gate.checks.append(Check("map mockup", not failed, detail, evidence=doc_map))

    fake = evidence.last(TOOL_RUN, "qa:fake-tests")
    if fake is not None and not fake.ok:
        files = fake.detail.get("files") or []
        gate.checks.append(
            Check("test thật", False,
                  f"{len(files)} test không có khẳng định nào: {', '.join(files[:3])}",
                  evidence=[fake.seq])
        )
    else:
        gate.checks.append(Check("test thật", True, evidence=[fake.seq] if fake is not None else []))

    # Tiêu chí có test (G5): mã `AC-<story>-<i>` phải nằm trong tên một test
    # của lần chạy xanh cuối — tên đọc từ output runner, không từ lời agent.
    # Không đọc được tên test là **chưa cấu hình** reporter, không phải lỗi
    # story và không phải đạt.
    xanh = [e for e in evidence.of(TOOL_RUN, "test") if e.ok]
    last_green = xanh[-1] if xanh else None
    doc_xanh = [last_green.seq] if last_green is not None else []
    if acceptance <= 0:
        gate.checks.append(Check("tiêu chí có test", Outcome.NOT_APPLICABLE, "story không khai tiêu chí"))
    elif last_green is None:
        gate.checks.append(Check("tiêu chí có test", False, "chưa có lần test xanh"))
    elif not last_green.detail.get("test_format"):
        gate.checks.append(Check(
            "tiêu chí có test", Outcome.UNCONFIGURED,
            str(last_green.detail.get("test_note") or "")
            or "không đọc được tên test từ output runner — dùng reporter in tên "
               "(`node --test`, `vitest --reporter=verbose`, `pytest -v`, CTRF)",
            evidence=doc_xanh,
        ))
    else:
        thieu = ac_missing(story_id, acceptance, list(last_green.detail.get("test_ids") or []))
        gate.checks.append(Check(
            "tiêu chí có test", not thieu,
            "" if not thieu else
            f"chưa có test mang mã {', '.join(ac_code(story_id, i) for i in thieu)} — "
            f"mỗi tiêu chí cần ít nhất một test đặt tên theo mã của nó",
            evidence=doc_xanh,
        ))

    # coverage.min (G10b): số đọc từ output runner. Không có số là runner
    # chưa bật coverage — nói đúng chỗ sửa, không tính là đạt.
    if coverage_min is not None:
        cov = last_green.detail.get("coverage") if last_green else None
        if last_green is None:
            gate.checks.append(Check("coverage", Outcome.UNCONFIGURED, "chưa có lần test xanh để đo"))
        elif cov is None:
            gate.checks.append(Check(
                "coverage", Outcome.UNCONFIGURED,
                "runner chưa in coverage — thêm `--coverage` (vitest/c8) hoặc `--cov` (pytest) vào lệnh test",
                evidence=doc_xanh,
            ))
        else:
            nguong = coverage_min * 100
            gate.checks.append(Check(
                "coverage", float(cov) >= nguong,
                f"{float(cov):.0f}%" if float(cov) >= nguong else f"{float(cov):.0f}% < {nguong:.0f}%",
                evidence=doc_xanh,
            ))

    # TDD (G8): story thêm test thì phải có một lần đỏ trước lần xanh cuối.
    if added_tests is not None:
        if not added_tests:
            gate.checks.append(Check("TDD", Outcome.NOT_APPLICABLE, "story không thêm test"))
        else:
            gate.checks.append(Check(
                "TDD", red_before_green(evidence),
                "" if red_before_green(evidence) else
                f"test xanh ngay lần đầu — chưa chứng minh nó kiểm được gì "
                f"({', '.join(added_tests[:3])}). Viết test trước, chạy thấy đỏ, rồi mới viết code.",
                evidence=[e.seq for e in evidence.of(TOOL_RUN, "test")],   # thứ tự đỏ/xanh đọc trên cả dãy
            ))
    # Nop control (ADR-005 V3) ngay sau TDD: cùng câu hỏi, hỏi thẳng hơn.
    gate.checks.append(_nop_check(evidence, story_id, acceptance=acceptance, candidate=candidate))

    # Hợp đồng kiểm định của story. Loại chưa cấu hình được ghi là **chưa
    # cấu hình**, không phải đạt — nó chặn ở cổng trước triển khai, và ở
    # đây nó phải hiện ra để người đọc biết chỗ trống nằm đâu.
    for kind in contract or []:
        if kind in ("unit", "mockup-map", "security"):
            continue  # đã có mục riêng ở trên
        # `run_suite` ghi `qa:<kind>`; tên trần là của lần chạy tay/`aisdlc tool`.
        # e9 2026-09-05: e2e/perf/accessibility chạy thật và xanh mà cổng báo
        # "chưa cấu hình" vì chỉ tìm tên trần.
        ran = evidence.last(TOOL_RUN, f"qa:{kind}") or evidence.last(TOOL_RUN, kind)
        if ran is None:
            gate.checks.append(Check(kind, Outcome.UNCONFIGURED, kind=CHECK_KIND["<kind>"]))
        elif ran.detail.get("skipped"):
            gate.checks.append(Check(kind, Outcome.UNCONFIGURED, str(ran.detail["skipped"]),
                                     kind=CHECK_KIND["<kind>"], evidence=[ran.seq]))
        elif _khong_on_dinh(evidence, f"qa:{kind}"):
            gate.checks.append(Check(kind, Outcome.UNRUNNABLE, _khong_on_dinh(evidence, f"qa:{kind}"),
                                     kind=CHECK_KIND["<kind>"], evidence=[ran.seq]))
        else:
            gate.checks.append(Check(
                kind, ran.ok, "" if ran.ok else str(ran.detail.get("tail", ""))[:200],
                kind=CHECK_KIND["<kind>"], evidence=[ran.seq],
            ))

    # Bảo mật: chưa chạy thì **chưa cấu hình**, không phải đạt. Bỏ mục
    # này khi không có kết quả sẽ làm cổng im lặng ở đúng chỗ nó phải
    # nói to nhất. Đọc `security` (kết quả phiên rà soát, tham số) chứ không
    # đọc sự kiện → `evidence` rỗng, và nói rỗng; `rà soát` bên dưới cũng vậy
    # (`review_blocking` là lời reviewer đã lọc ở `run_attempt`).
    if security is None:
        gate.checks.append(
            Check("bảo mật", Outcome.UNCONFIGURED, "chưa cấu hình rà soát bảo mật")
        )
    elif security.error:
        gate.checks.append(Check("bảo mật", False, security.error))
    else:
        chan = security.blocking(block_severities or DEFAULT_BLOCKING)
        gate.checks.append(Check(
            "bảo mật",
            not chan,
            "" if not chan else f"{len(chan)} mục chặn: {chan[0].line()[:200]}",
        ))

    if not review_ran:
        gate.checks.append(Check("rà soát", False, "chưa rà soát độc lập"))
    else:
        blocking = review_blocking or []
        gate.checks.append(
            Check(
                "rà soát",
                not blocking,
                "" if not blocking else f"{len(blocking)} mục chặn: {blocking[0][:200]}",
            )
        )

    gate.checks.append(_preservation_check(evidence, preservation or [], candidate))
    # `kind` đóng dấu một chỗ từ bảng, không rải ở từng mục; tên ngoài bảng
    # không có kind — test meta chặn tên lạ, nên ở đây không đoán.
    for c in gate.checks:
        c.kind = c.kind or CHECK_KIND.get(c.name, "")
    return gate


def _preservation_check(evidence: Evidence, preservation: list[dict], candidate: str) -> Check:
    """Mục "bảo toàn" (ADR-004 R4): hành vi VERIFIED của story khác mà story
    này chạm tệp phải **còn xanh ở đúng ứng viên này**.

    Ba kết cục, không có kết cục thứ tư. Đỏ → FAILED; sổ hành vi tự suy
    REOPENED (`regressed_by` = story này) từ chính bằng chứng cổng đang đọc,
    nên không ghi tay lần hai. Không có bằng chứng ở ứng viên — test không
    mang mã, `qa` bỏ qua, màn chưa đối chiếu — → UNRUNNABLE: "không kiểm
    được" không phải "đạt". Còn lại → PASSED.

    Bằng chứng phải **mang đúng SHA**: sự kiện không khai bản (`for_candidate`
    giữ lại) không được dùng ở đây, vì mục này hỏi đúng câu "bản này có làm
    hỏng không", và một lần chạy không rõ bản nào không trả lời được.
    """
    if not preservation:
        return Check("bảo toàn", Outcome.NOT_APPLICABLE,
                     "story không chạm hành vi VERIFIED nào của story khác")

    doc: list[int] = []     # sự kiện đã đọc ở đúng ứng viên

    def at_candidate(kind: str, name: str):
        runs = [e for e in evidence.of(kind, name)
                if not candidate or str(e.detail.get("candidate") or "") == candidate]
        if runs and runs[-1].seq not in doc:
            doc.append(runs[-1].seq)
        return runs[-1] if runs else None

    test = at_candidate(TOOL_RUN, "test")
    ids = ([str(t) for t in test.detail.get("test_ids") or []]
           if test is not None and test.detail.get("test_format") else [])
    failed = {str(t) for t in test.detail.get("failed_ids") or []} if test is not None else set()

    do, thieu = [], []
    for it in preservation:
        bid, kind, owner = str(it.get("id") or ""), str(it.get("kind") or ""), str(it.get("story") or "")
        if kind == "ac":
            i = int(bid.rsplit("-", 1)[-1]) if bid.rsplit("-", 1)[-1].isdigit() else 0
            tests = ac_coverage(owner, i, ids).get(i, []) if i else []
        elif kind in ("fr", "nfr"):
            # Yêu cầu xanh khi tiêu chí của story **đã xác minh nó** xanh — cùng
            # luật với sổ (`source.story`), không phải story sở hữu trên giấy.
            via = str(it.get("via") or owner)
            tests = [t for t in ids if f"AC-{via}-" in t.replace("_", "-")]
        elif kind == "qa":
            ran = at_candidate(TOOL_RUN, bid)
            if ran is None or ran.detail.get("skipped"):
                thieu.append(bid)
            elif not ran.ok:
                do.append(bid)
            continue
        elif kind == "mockup":
            m = at_candidate(MOCKUP_MAP, bid.split(":", 1)[-1])
            if m is None:
                thieu.append(bid)
            elif not m.ok:
                do.append(bid)
            continue
        else:
            thieu.append(bid)
            continue
        if not tests:
            thieu.append(bid)
            continue
        red = [t for t in tests if t in failed]
        if red:
            do.append(f"{bid} ({red[0]})")

    if do:
        return Check("bảo toàn", Outcome.FAILED,
                     f"hồi quy: {', '.join(do[:3])}{'…' if len(do) > 3 else ''} — hành vi đã "
                     "VERIFIED của story khác đỏ ở ứng viên này; sửa code cho nó xanh lại, "
                     "không sửa test của nó", evidence=doc)
    if thieu:
        return Check("bảo toàn", Outcome.UNRUNNABLE,
                     f"chưa kiểm được ở ứng viên {candidate[:7] or 'này'}: "
                     f"{', '.join(thieu[:3])}{'…' if len(thieu) > 3 else ''} — không có test "
                     "mang mã / kiểm định bỏ qua / màn chưa đối chiếu; không kiểm được không phải đạt",
                     evidence=doc)
    return Check("bảo toàn", True, f"{len(preservation)} hành vi của story khác còn xanh", evidence=doc)


def qualification_table(test_file: Path | None = None) -> dict[str, dict[str, bool]]:
    """Bảng chứng nhận mục cổng (ADR-005 V9, T10): tên → control nào đã có.

    Đọc **AST** của `tests/test_gate_qualification.py` — lớp có `TEN = "<tên>"`
    và phương thức `test_positive*` / `test_negative*` / `test_env*` — không
    chép tay vào mã, vì bảng chép tay là lời kể về test chứ không phải test.
    Bản cài từ wheel không có thư mục `tests/` → trả rỗng, báo cáo in `?`,
    không in 0 (0 là "đã đếm, không có").
    """
    path = test_file or Path(__file__).resolve().parents[2] / "tests" / "test_gate_qualification.py"
    if not path.is_file():
        return {}
    table = {name: dict.fromkeys(CONTROLS, False) for name in CHECK_NAMES}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.ClassDef):
            continue
        ten = next((n.value.value for n in node.body
                    if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                    and any(isinstance(t, ast.Name) and t.id == "TEN" for t in n.targets)), None)
        if ten not in table:
            continue
        for fn in node.body:
            if isinstance(fn, ast.FunctionDef):
                for ctl in CONTROLS:
                    if fn.name.startswith(f"test_{ctl}"):
                        table[ten][ctl] = True
    return table
