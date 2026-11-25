# PIN-57 — các ứng viên tu chính án chính xác cho owner (owner directive 2026-11-26, P0)

**Status: DRAFT — các ứng viên để owner chọn và ban hành; tự nó không cho phép gì.**
**Tu chính án này KHÔNG có hiệu lực cho tới khi owner ban hành nó với các digest chính xác đã điền**
(cột "sha sau khi sửa" của bảng digest mỗi phương án, cộng digest của entry ledger mới). Theo PIN-57 ruling §4
(2026-11-25): "No implied approval is granted" — tài liệu này không đăng ký, không re-pin, không nới lỏng gì.
Mọi sha đo tại HEAD `466c9f945863a4d1df8d90e57f8975a0d8192f85` (release/v2.3-big), ngày 2026-11-26.
Bằng chứng nguồn: `docs/v2.3/evidence/PIN-57-MODULE-ROLES.md` (đo tại `bc8668f0…`; blob của file test pin
không đổi giữa hai HEAD — kiểm lại 2026-11-26).

---

## 1. Phát biểu bài toán (10 dòng)

1. Ba checker v2.3 đã dựng xong, có fixture known-bad committed, nhưng KHÔNG nằm trong `cc.REGISTRY` (57 mục):
   `f5_gate`, `f5_recorder`, `released_evidence` — `validation/v2/checker_calibration.py:680` (`V23_CHECKERS`).
2. Chúng phủ BỐN module: `validation/v23/{impact,ci_gate,observe,released_evidence_guard}.py` (PIN-57-MODULE-ROLES.md §1, bảng).
3. `f5_gate` quyết định verdict CẢ HAI chiều (accept qua VERIFIED_REUSE, refuse qua rc tier / `--check --states`) — §2.3, §2.5.
4. `released_evidence` quyết định verdict chiều REFUSE (bước bắt buộc `tests.yml:68`, fail-closed) — §4.3, §4.5.
5. `f5_recorder` là non-checker như đang nối dây (không gate nào truyền `--observations`; authority pinned "none") — §3.3, §3.5.
6. Quy tắc Q0P-2 (`validation/v23/q0_round.py:165-183`) hôm nay nêu đúng bốn module đó đỏ: "validation/v23 module with no calibration".
7. KHÔNG có mặc định xanh: đăng ký (57→60) làm đỏ 2 dòng pin của `tests/v23/test_v23_q0_round.py` (:73, :223);
   giữ ngoài làm đỏ danh sách đóng Q0P-2 và vi phạm NOT_AUTHORIZED của seq 13 (`LEDGER-SEQ-13-DRAFT-R6.md:38`) — §1 "The live red".
8. Seq 13 đã committed (entry 13 trong `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json`) và bất biến
   ("any change of this draft after it is committed (a later ruling is a new draft file)"), nên MỌI phương án cần entry ledger MỚI (seq 14).
9. Khoảng trống hiện hành: ba Checker object + fixture của chúng không được test nào chạy khi chưa đăng ký (sweep anti-gaming
   chỉ quét `cc.REGISTRY`) — §5 fact 3; đồng thời calibration sống tại HEAD là **54/57** (3 red là wait đã biết), không phải 56/57 — §5 fact 1.
10. Ba ứng viên dưới đây là các tu chính án CHÍNH XÁC cho quyết định đó; lựa chọn là của owner, tài liệu này không khuyến nghị.

---

## 2. PHƯƠNG ÁN A — ĐĂNG KÝ: `REGISTRY` += ba checker (57 → 60)

### 2.1 Sửa code (1 file sản phẩm)

`validation/v2/checker_calibration.py` (blob `56bf4453ad02aa907e39c4b8e0942c3387775915`):
sau dòng 680 (`V23_CHECKERS: tuple[...] = (_f5_gate, _f5_recorder, _released_evidence)`) thêm đúng một dòng:

```python
REGISTRY += list(V23_CHECKERS)
```

và viết lại khối chú thích :673-679 (khối hiện ghi "NOT YET in REGISTRY … until then q0_round's scope rule names the
four modules uncovered, truthfully red" — sau tu chính án nó sai sự thật, phải ghi lại là "registered under ledger seq 14").

### 2.2 Sửa test pin (bắt buộc kèm theo, cùng một ruling)

`tests/v23/test_v23_q0_round.py` (blob `8d518bf8f392300a6d5e280d74f6a2f3e360a5d6`, LF-sha256 pinned trong
`V23_PINNED` = `9b9433f33c1176367a80dd2a3144f37f8f3e2250d6cd62df9a3956bb3ca8c7cb`).

**Pin 1 — :73 (Q0RoundV23): KHÔNG đổi chữ, giá trị runtime đổi.**

```python
self.assertEqual(self.result["calibrated_count"], len(cc.REGISTRY))
```

Dòng này giữ nguyên văn bản; `len(cc.REGISTRY)` trở thành 60, nên nó xanh chỉ khi cả 60 calibrated
(hôm nay sống 54/57 → sau A là 57/60: vẫn đỏ vì 3 wait đã biết — xem 2.5).

**Pin 2 — :219 + :223 (Q0History): ĐỔI chữ.** Hiện tại:

```python
fewer = dict(self.result, checkers=self.result["checkers"][1:], calibrated_count=56)
...
    self.assertIn("calibrated 56 of 57 registered checkers", Q.problems(fewer, t, record_too=False))
```

Giá trị pin mới: `calibrated_count=59` và `"calibrated 59 of 60 registered checkers"`
(`fewer` bỏ 1 checker khỏi kết quả tổng hợp 60 ⇒ 59 of 60).

**Pin thứ ba KHÔNG được nêu tên trong đầu bài (phát hiện khi soạn):** lớp always-run `Q0Record`
(:165-247) dùng chính record v2.2 committed (`cls.result`, `calibrated_count=57`, 57 hàng checker) làm kết quả
"đã calibrate đủ" cho các round-trip của writer/checker:

* :234-235 — `self.assertEqual(Q.main(["--write"]), 0)` (writer phải viết được);
* :240 — `self.assertEqual(Q.main(["--check"]), 0)`.

Sau A, `problems()` thêm `"calibrated 57 of 60 registered checkers"` cho kết quả đó ⇒ cả hai đỏ dù không phải
"pin" được đặt tên. Sửa bắt buộc: `Q0Record.setUpClass` mở rộng `cls.result` bằng ba hàng calibrated tổng hợp
(`checker` = `f5_gate`/`f5_recorder`/`released_evidence`, `calibrated: true`, `fixture` = đường dẫn fixture committed)
và `calibrated_count=60` — giữ nguyên các literal pin ở :219/:223 làm chốt.

Dòng :189 (`stale = Q.render(dict(self.result, calibrated_count=56))`) và :405 (Q0Rules, f-string
`f"calibrated 0 of {len(cc.REGISTRY)} registered checkers"`) tự thích nghi, không sửa.
`tests/v2/test_v21_authority_limits.py:658` chỉ kiểm membership, không kiểm count — không sửa.

### 2.3 Dây nối (wiring) — hệ quả bắt buộc của việc sửa một file V23_PINNED

Sửa `tests/v23/test_v23_q0_round.py` phá `V23_PINS_HOLD` (`tests/v2/sealing_gate.py:61-78`): 12 test replay
bị un-skip tại HEAD và `Seq13Wiring`/`Q0Wiring` đỏ. Seq 13 cấm cả lối thoát
(`LEDGER-SEQ-13-DRAFT-R6.md:38`: "re-pinning or removing V23_PINNED" và "any wiring other than the named patch"
đều NOT_AUTHORIZED). Vì seq 13 bất biến, entry seq 14 của ruling này phải tự mang GATED_TEST_WIRING MỚI:

1. `tests/v2/sealing_gate.py` (blob `f6b64b5264fb55a6863145bc7722ec869d1f2535`): cập nhật một giá trị trong
   `V23_PINNED` — sha LF mới của `tests/v23/test_v23_q0_round.py` (thay `9b9433f3…`).
2. File MỚI `docs/v2.3/drafts/SEQ14-WIRING.patch`: sealing_gate.py của v2.2.0 + diff lũy kế (nội dung R6 + re-pin);
   sha256 LF của nó được GATED_TEST_WIRING của entry seq 14 nêu đích danh (tiền lệ: seq 13 nêu
   `SEQ13-WIRING-R6.patch` sha `25e7fc47…`).
3. `tests/v23/test_v23_rounds.py` (blob `a8eb0a0c7b3ae6c1644a854338ef3e4cae8099e4`, cũng V23_PINNED):
   `Seq13Wiring.test_the_applied_wiring_is_exactly_the_reviewed_patch_and_its_pins_hold` (:368-373) hiện khẳng định
   sealing_gate == v2.2.0 + patch R6 — phải học chấp nhận "v2.2.0 + patch seq-14 khi entry seq 14 committed";
   re-pin chính nó trong patch mới.
4. `tests/v23/test_v23_seq13_wiring.py` (blob `5891086854f9e98b8b01e639aadd79b497f9cb93`, KHÔNG pinned):
   các test pin hành vi patch (:99-110 — "the drafted pins are this tree's files: an edit of one without a new patch
   is red here") mở rộng cho patch seq-14.
5. `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` (blob `a33f2197bfcb00d064cb74e169b246343de77840`):
   owner append entry seq 14 (CIGOV-R1 cho phép append-only — `test_v23_released_evidence_guard.py:135`).
   Hành vi append là CỦA OWNER, như seq 13.

### 2.4 Nghĩa vụ calibration — fixture ĐÃ TỒN TẠI, không phải tạo mới

| checker | fixture committed | blob sha tại HEAD |
|---|---|---|
| `f5_gate` | `tests/v2/fixtures/known_bad/f5_gate.json` | `912daa2d1d080d9bfc1c608d473cff261ab3369d` |
| `f5_recorder` | `tests/v2/fixtures/known_bad/f5_recorder.json` | `cfa3798b476b79e53189ad3ed385af8144d8e65b` |
| `released_evidence` | `tests/v2/fixtures/known_bad/released_evidence.json` | `f978ebfb72c3935a18ab4cfc580d29baedb8a0d6` |

Sau đăng ký, các nghĩa vụ này tự động được thi hành — không cần test mới:
`Q0RoundV23.test_every_checker_has_a_committed_fixture_that_fails_it_for_the_named_reason` (:84-90) chạy mỗi hàng
(clean xanh + fixture bị từ chối đúng lý do), và các sweep anti-gaming :92-124 (always-PASS mutant, wrong-reason,
missing/stale fixture) quét `cc.REGISTRY` nên PHỦ LUÔN ba checker mới. Đây là chính khoảng trống §5 fact 3 được đóng.

### 2.5 Hệ quả dây chuyền (đỏ-trước/xanh-sau)

* Q0P-2: bốn module trở thành source của checker đã đăng ký ⇒ `v23_scope_problems` XANH (hết 4 dòng đỏ hiện tại).
* Quy tắc count: đỏ sống chuyển từ "4 module uncovered" + 54/57 thành **57/60** — A KHÔNG làm Q0RoundV23 xanh;
  ba red còn lại là wait đã biết (`b1_bindings` chờ OD-B1B, `currency_dag` chờ P5-PROPOSAL currency, `mutation` chờ F5 cut-over).
* Record vòng: `docs/v2.3/evidence/q0-round/Q0-CHECKER-CALIBRATION-V23.json` **chưa từng được viết** (không có trên HEAD —
  đo 2026-11-26), nên không có record nào phải re-derive; lần `--write` ĐẦU TIÊN (vẫn bị refuse tới khi ba wait sạch)
  sẽ mang 60 hàng, và `delta()` in `+ f5_gate`, `+ f5_recorder`, `+ released_evidence` cho owner duyệt.
* Replay v2.2.0 không bị đụng (chạy trên bytes v2.2.0); record v2.2 bất biến (`dropped()`/`contract_problems` không đổi).
* `checker_calibration.py` không phải mutation target, không trong V23_PINNED, không trong BOUND_SHA256 — sửa nó
  không kéo theo pin nào khác.

### 2.6 Bảng digest owner điền khi ban hành (PHƯƠNG ÁN A)

| file | blob sha TRƯỚC (HEAD 466c9f94) | thay đổi nội dung | sha SAU (owner điền) |
|---|---|---|---|
| `validation/v2/checker_calibration.py` | `56bf4453ad02aa907e39c4b8e0942c3387775915` | `REGISTRY += list(V23_CHECKERS)` + viết lại chú thích :673-679 | ________ |
| `tests/v23/test_v23_q0_round.py` | `8d518bf8f392300a6d5e280d74f6a2f3e360a5d6` | :219 `56`→`59`; :223 `"56 of 57"`→`"59 of 60"`; `Q0Record.setUpClass` +3 hàng tổng hợp | ________ |
| `tests/v2/sealing_gate.py` | `f6b64b5264fb55a6863145bc7722ec869d1f2535` | `V23_PINNED["tests/v23/test_v23_q0_round.py"]` = sha LF mới; (`…["tests/v23/test_v23_rounds.py"]` nếu mục 2.3(3) sửa file đó) | ________ |
| `tests/v23/test_v23_rounds.py` | `a8eb0a0c7b3ae6c1644a854338ef3e4cae8099e4` | `Seq13Wiring` chấp nhận patch seq-14 | ________ |
| `tests/v23/test_v23_seq13_wiring.py` | `5891086854f9e98b8b01e639aadd79b497f9cb93` | mở rộng test pin-patch cho seq-14 | ________ |
| `docs/v2.3/drafts/SEQ14-WIRING.patch` | (file mới) | v2.2.0 sealing_gate + diff lũy kế; sha được seq 14 nêu | ________ |
| `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` | `a33f2197bfcb00d064cb74e169b246343de77840` | owner append entry seq 14 (append-only, CIGOV-R1) | ________ |

Entry seq 14 của A phải nêu đích danh các mục NOT_AUTHORIZED của seq 13 mà nó thay thế cho đúng phạm vi này:
"re-pinning or removing V23_PINNED" (chỉ cho các file bảng trên) và "any wiring other than the named patch"
(patch seq-14 thay patch R6). A KHÔNG đụng `NOT_CHECKERS_V23`.

---

## 3. PHƯƠNG ÁN B — GIỮ NGOÀI REGISTRY VỚI THẨM QUYỀN + KIỂM SOÁT BÙ

### 3.1 Sửa code (1 file, V23_PINNED)

`validation/v23/q0_round.py` (blob `d74edb2b7ba483957710ad771e7d73eaab01a419`, LF-sha256 pinned trong
`V23_PINNED` = `038906381a500a0c40e179803078c471527f960b884644d34eea64b4ff85fccf`). Danh sách đóng hiện tại, :60-61:

```python
NOT_CHECKERS_V23 = frozenset({"validation/v23/__init__.py", "validation/v23/ledger_digest.py",
                              "validation/v23/q0_round.py", "validation/v23/replay_v22.py"})
```

Nội dung mới (ruling nêu đúng bốn file — ba checker phủ bốn module):

```python
NOT_CHECKERS_V23 = frozenset({"validation/v23/__init__.py", "validation/v23/ledger_digest.py",
                              "validation/v23/q0_round.py", "validation/v23/replay_v22.py",
                              # ledger seq 14 (PIN-57): owner-authorized non-registry validators, drift-pinned by
                              # tests/v23/test_v23_unregistered_checkers.py
                              "validation/v23/ci_gate.py", "validation/v23/impact.py",
                              "validation/v23/observe.py", "validation/v23/released_evidence_guard.py"})
```

Chính file này tuyên bố (:59): "The list is closed: adding a module to it is a new q0_round.py, so a new patch and
a new ruling" — ruling đó là entry seq 14 của B.

### 3.2 Kiểm soát bù BẮT BUỘC (khoảng trống evidence package §5 fact 3 nêu)

File test MỚI, always-run (không gate): **`tests/v23/test_v23_unregistered_checkers.py`** — ruling cho phép tạo nó.
Nghĩa vụ tối thiểu, cho TỪNG checker giữ ngoài:

* `cc.calibrate(make())["calibrated"] is True` cho `make` trong `cc.V23_CHECKERS` — tức clean xanh trên cây này,
  fixture committed (bảng 2.4, các blob y hệt) vẫn bị từ chối ĐÚNG lý do ghi, và always-PASS mutant bị loại
  (`cc.calibrate` tự chạy cả ba vế);
* pin danh tính: `{c().name for c in cc.V23_CHECKERS} == {"f5_gate", "f5_recorder", "released_evidence"}`
  (tuple không được teo đi trong im lặng);
* riêng `observe.py`, pin điều kiện §3.3 của evidence package: không caller nào truyền `observations=` cho
  `impact.classify` ngoài tham số CLI của chính `impact.py` (grep có chủ đích trong test — nối dây `--observations`
  vào bất kỳ gate nào là mở lại câu hỏi Decision-2, cần ruling mới).

File mới trong `tests/v23` không bị V23_PINNED/V23_GATED ràng (luôn chạy); chịu quét test_meta encoding như thường lệ.

### 3.3 Dây nối — y hệt cơ chế 2.3 vì `q0_round.py` là file V23_PINNED

Cùng 5 bước của 2.3, chỉ khác file bị re-pin: `V23_PINNED["validation/v23/q0_round.py"]` nhận sha LF mới
(file test Q0 KHÔNG sửa dưới B — cả hai pin giữ nguyên văn bản lẫn giá trị: registry vẫn 57, `"56 of 57"` vẫn đúng).
`Q0Scope` (:351-…) tự thích nghi: nó dựng cây tạm từ chính `Q.NOT_CHECKERS_V23` và chỉ đòi mỗi tên trong danh sách
tồn tại trên cây thật (:371) — bốn file tồn tại.

### 3.4 Hệ quả dây chuyền (đỏ-trước/xanh-sau)

* Q0P-2 XANH (bốn module vào danh sách đóng). Quy tắc count giữ 54/57 sống — Q0RoundV23 :73 vẫn đỏ vì ba wait
  đã biết, y như trước; B không đổi con số nào trong record.
* `run()`/`render()` không đổi ⇒ record vòng (chưa viết) không đổi nội dung tương lai; `delta()` không thêm hàng nào.
* Ba Checker object vẫn "ngủ" ngoài REGISTRY; sweep anti-gaming Q0RoundV23 :92-124 KHÔNG phủ chúng — kiểm soát bù 3.2
  là chỗ duy nhất ghim calibration trôi dạt của chúng, và nó always-run (mạnh hơn sweep round-gated về tần suất,
  yếu hơn về chỗ: không vào record Q0 nào).
* Căng thẳng chuẩn tắc phải được ruling giải quyết CHỮ RÕ: owner ruling 2026-11-22 §D đòi "every new validation/v23
  checker registered and calibrated" (ghi tại `checker_calibration.py:672-679`), và seq 13 NOT_AUTHORIZED
  (`LEDGER-SEQ-13-DRAFT-R6.md:38`) cấm "adding a module to NOT_CHECKERS_V23" và cấm "a validation/v23 module without
  a registered, calibrated checker". Entry seq 14 của B phải thay thế cả ba mệnh đề đó cho đúng bốn module này, theo
  đúng tiền lệ seq-13 đã xếp `q0_round.py` (verdict-determining chiều refuse by design) vào `NOT_CHECKERS_V23`
  với negative test riêng — evidence package §1 "Precedent".

### 3.5 Bảng digest owner điền khi ban hành (PHƯƠNG ÁN B)

| file | blob sha TRƯỚC (HEAD 466c9f94) | thay đổi nội dung | sha SAU (owner điền) |
|---|---|---|---|
| `validation/v23/q0_round.py` | `d74edb2b7ba483957710ad771e7d73eaab01a419` | `NOT_CHECKERS_V23` += 4 file (khối 3.1) | ________ |
| `tests/v23/test_v23_unregistered_checkers.py` | (file mới) | drift-pin 3.2 | ________ |
| `tests/v2/sealing_gate.py` | `f6b64b5264fb55a6863145bc7722ec869d1f2535` | `V23_PINNED["validation/v23/q0_round.py"]` = sha LF mới | ________ |
| `tests/v23/test_v23_rounds.py` | `a8eb0a0c7b3ae6c1644a854338ef3e4cae8099e4` | `Seq13Wiring` chấp nhận patch seq-14 | ________ |
| `tests/v23/test_v23_seq13_wiring.py` | `5891086854f9e98b8b01e639aadd79b497f9cb93` | mở rộng test pin-patch cho seq-14 | ________ |
| `docs/v2.3/drafts/SEQ14-WIRING.patch` | (file mới) | v2.2.0 sealing_gate + diff lũy kế; sha được seq 14 nêu | ________ |
| `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` | `a33f2197bfcb00d064cb74e169b246343de77840` | owner append entry seq 14 | ________ |

Hai dòng pin PIN-57: **cả :73 lẫn :223 giữ nguyên** (văn bản và giá trị).
`tests/v23/test_v23_q0_round.py` và `validation/v2/checker_calibration.py` KHÔNG được sửa dưới B
(trừ phi owner muốn xoá tuple `V23_CHECKERS` — không bắt buộc; drift-pin 3.2 cần nó tồn tại).

---

## 4. PHƯƠNG ÁN C — MIXED: đăng ký hai checker quyết định verdict, giữ recorder ngoài

Evidence package kết luận theo từng module (§2.5, §3.5, §4.5): `f5_gate` và `released_evidence` quyết định verdict
(A-và-R / R-only) — "non-checker role is not demonstrated"; `f5_recorder` có non-checker role ĐÃ chứng minh, kèm điều kiện.
C áp A cho hai cái đầu, B cho recorder:

* `validation/v2/checker_calibration.py`: `REGISTRY += [_f5_gate, _released_evidence]` (57 → **59**); tuple
  `V23_CHECKERS` thu lại thành `(_f5_recorder,)` (hoặc đổi tên `UNREGISTERED_V23`), chú thích :673-679 viết lại.
* `validation/v23/q0_round.py`: `NOT_CHECKERS_V23` += **chỉ** `"validation/v23/observe.py"` (impact/ci_gate/
  released_evidence_guard được phủ qua `sources` của checker đã đăng ký: `checker_calibration.py:584,638`).
* `tests/v23/test_v23_q0_round.py`: pin :73 giữ nguyên văn bản (giá trị → 59); :219 `calibrated_count=56` →
  `calibrated_count=58`; :223 → `"calibrated 58 of 59 registered checkers"`; `Q0Record.setUpClass` +2 hàng tổng hợp.
* `tests/v23/test_v23_unregistered_checkers.py` (mới): drift-pin 3.2 nhưng CHỈ cho `f5_recorder`, gồm pin điều kiện
  `--observations` (bắt buộc — đó là điều kiện §3.3 mà "retain" của recorder đứng trên).
* Dây nối: y 2.3, nhưng re-pin CẢ HAI file V23_PINNED bị sửa (`test_v23_q0_round.py` VÀ `q0_round.py`).
* Entry seq 14 của C thay thế đồng thời các mệnh đề NOT_AUTHORIZED của cả A lẫn B (re-pin V23_PINNED, patch mới,
  thêm observe.py vào NOT_CHECKERS_V23, "module without a registered, calibrated checker" cho riêng observe.py).
* Đỏ-trước/xanh-sau: Q0P-2 xanh; count sống 56/59 (ba wait cũ không đổi); record đầu tiên mang 59 hàng,
  `delta()` in `+ f5_gate`, `+ released_evidence`.

Bảng digest của C = bảng 2.6 ∪ 3.5 (bảy file sửa + hai file mới + ledger append; các blob "trước" y hệt đã nêu).

---

## 5. Bảng so sánh trung lập (lựa chọn là của owner)

| tiêu chí | A — đăng ký cả ba | B — giữ ngoài cả ba | C — mixed (gate+guard đăng ký, recorder ngoài) |
|---|---|---|---|
| Tư thế tin cậy | Cả ba vào Q0: sweep anti-gaming + fixture-currency round-gated phủ tự động; calibration vào record vòng, owner duyệt qua `delta()` | Ba checker ngủ ngoài record; drift-pin always-run (đủ ba vế của `cc.calibrate`) nhưng ngoài record Q0; cần ruling thay thế chữ rõ ruling 2026-11-22 §D | Hai module quyết định verdict vào Q0; recorder giữ đúng vai trò non-checker đã chứng minh (khớp verdict từng-module của evidence package §2.5/§3.5/§4.5) |
| Dòng pin PIN-57 | :73 giữ chữ (giá trị 57→60); :223 đổi chữ (56/57→59/60) + Q0Record +3 hàng | :73 và :223 giữ nguyên cả chữ lẫn giá trị | :73 giữ chữ (→59); :223 đổi (→58/59) + Q0Record +2 hàng |
| Khối lượng | 5 file sửa + 1 patch mới + 1 ledger append | 4 file sửa + 1 test mới + 1 patch mới + 1 ledger append | 6 file sửa + 1 test mới + 1 patch mới + 1 ledger append (lớn nhất) |
| File V23_PINNED bị sửa | 1–2 (test Q0; rounds nếu 2.3(3)) | 1–2 (q0_round.py; rounds nếu 2.3(3)) | 2–3 |
| Rủi ro chính | Sửa file test pin verdict (nghi thức cao nhất); pin thứ ba Q0Record lộ ra khi soạn — diff test lớn hơn đầu bài nêu | Khoảng cách chuẩn tắc với ruling §D; điều kiện observe (`--observations` không được nối) chỉ đứng trên drift-pin mới; sweep registry không phủ ba checker | Cộng cả hai mặt rủi ro; nhiều bộ phận chuyển động nhất trong một ruling |
| Điều không đổi ở mọi phương án | Q0RoundV23 :73 vẫn đỏ sau tu chính án cho tới khi ba wait đã biết sạch (OD-B1B, P5-PROPOSAL currency, F5 cut-over); record V23_REL chưa tồn tại — lần `--write` đầu vẫn chờ; seq 13 bất biến, mọi đường đều qua entry seq 14 + patch wiring mới | ← | ← |

---

*Soạn 2026-11-26 theo owner directive 2026-11-26 P0. Tài liệu này là bản nháp các ứng viên: không ứng viên nào có
hiệu lực cho tới khi owner ban hành nó như một entry ledger mới (seq 14) với mọi digest trong bảng tương ứng đã điền
bằng sha đo thật sau khi sửa, và authority bằng chính lời owner trích digest của ruling, theo đúng cơ chế seq 13.*

---

## Addendum 2026-11-26 (sau khi land B2 Tier-0 tooling): seq-14 phải phủ thêm 4 module ground_truth

`validation/v23/ground_truth/{__init__,corpus,labels,metrics}.py` (B2 prep, protocol §8 — KHÔNG phải checker
calibration-sense: không fixture known-bad committed, không gate nào tiêu thụ verdict của chúng hôm nay) làm danh
sách "module with no calibration" của Q0P-2 tăng 4→8 mục. Gate này vốn đỏ-có-chủ-đích (gated-only) — đo trước/sau:
không gate xanh nào lật. HỆ QUẢ cho tu chính án: dù owner chọn A, B hay C cho ba checker PIN-57, entry seq-14 cũng
phải định đoạt 4 module ground_truth — hợp lý nhất là NOT_CHECKERS_V23 += 4 file này dưới MỌI ứng viên (chúng là
tooling, không phải checker), kèm điều khoản: khi `corpus.py --check` trở thành gate tại B2 manifest (W6), nó vào
registry + calibration như một checker thật. Bảng digest của các ứng viên cần cập nhật q0_round.py tương ứng tại
thời điểm ban hành.
