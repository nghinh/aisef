# ROADMAP-2.2 — WAVE-2 SPEC (FROZEN 2026-11-04)

Owner directive 2026-11-04 (duyệt khép Đợt 1 + khởi công Đợt 2). Spec này đông cứng phạm vi + tiêu chí nghiệm thu
cho CẢ đợt theo chế độ LÔ (CLAUDE.md). Không đổi scope giữa đợt. Nguồn trạng thái: `docs/ROADMAP-2.2-CHECKLIST.md`.

## 0. Ràng buộc owner (bất biến của đợt)

- **C2 là cổng của paid run.** Không có live paid run (B1 trả tiền, B7) tới khi C2 CHỨNG MINH được kiểm soát chi phí
  bằng diễn tập offline (fake client vượt trần ⇒ run DỪNG; fake thiếu token ⇒ fail-closed). Trần 2 lượt paid ≤ **$60**.
- **Không giảm phạm vi mutation, không nới tiêu chí nghiệm thu để làm đẹp.** Evidence trước + sau mỗi thay đổi.
- **Không tuyên bố CI tổng thể PASS khi job bắt buộc còn đỏ.** Phân loại rõ: lỗi thật / flaky / platform limit / sealing
  đỏ-chủ-đích.
- **Không reseal toàn bộ record-currency, không tag v2.2** nếu chưa có phê duyệt riêng.
- Authority/invariant KHÔNG đổi ở C3a/C4/C9 (và ở mọi mục đợt này).
- Báo cáo cuối đợt: commit SHA, CI, mutation, live PASS/FAIL, verification, chi phí USD thật, blocker, QĐ cần owner.
  KHÔNG tự sang Đợt 3.

## 1. Lane M — Mutation registry (owner item 1, KHÔNG paid)

**Vì sao:** 259 survivor của wave 1 gần như toàn bộ nằm ở CODE MỚI; kill test đã tồn tại nhưng chưa đăng ký. Đăng ký =
sửa `validation/v2/mutation.py` TARGETS (thay đổi registry, owner đã duyệt). Không đăng ký = để hở coverage code mới ⇒
vi phạm "không giảm phạm vi".

**Kill test đã có → target:**
| Kill file | Target được thêm |
|---|---|
| `tests/v2/test_v22_client_pin_fence.py` | client.py::session, client.py::environment, settings.py::load |
| `tests/v2/test_v22_tripwire.py` | run.py::execute, adapters.py::Reviewer._ocr, **(mới)** app/tripwire.py::* |
| `tests/v2/test_v22_authoring_lint.py` | bundle_cli.py::lint, bundle_cli.py::seal, bundle.py::load |
| `tests/v2/p0/test_invariants_runtime.py` | run.py::execute, verify.py::verify, **(mới)** invariants/registry.py::{arm_runtime,register_runtime,runtime_mechanism_digest,require_armed}, **(mới)** verify.py::_invariant_problems |

**Target MỚI** (code mới có mutant, đăng ký để KHÔNG giảm phạm vi — nêu rõ trong báo cáo cho owner): `aisef2/app/tripwire.py`
(needles_of/scan_repo/scan_text/_bundle_hit/refusal), `aisef2/invariants/registry.py` các hàm arming mới,
`aisef2/app/verify.py::_invariant_problems`.

**Cách làm (an toàn, idiom sẵn có):** thêm một khối `for _t in (...): TARGETS[_t] = [*TARGETS[_t], _W1_KILLS...]` sau khi
registry V2.1 dựng xong, có comment nêu owner directive 2026-11-04. Đăng ký target mới theo cùng pattern `_V21_REG`.

**Nghiệm thu lane M:**
- [ ] `mutation.py t0 <target>` PASS cho mọi kill set mới (xanh trên cây chưa mutate) TRƯỚC khi chạy dài.
- [ ] Re-measure các target bị ảnh hưởng + target mới, COPY tree + baseline xanh, env guard (PATH không opencode + XDG
      scratch), T0 trước. Phân loại từng survivor: **KILLED / SURVIVED / EQUIVALENT** (equivalent phải có lập luận ghi
      trong record, không tự tuyên bố).
- [ ] Evidence TRƯỚC (`closure-evidence/v2/v2.2/WAVE1-MUTATION.json` đã có) + SAU (record mới) đều lưu; record seal
      KHÔNG ghi đè.
- [ ] Số killed tăng thực; survivor còn lại hoặc EQUIVALENT (có lập luận) hoặc là finding mở (báo owner).

## 2. Lane CI — Root-cause 4 nhóm đỏ tồn đọng (owner item 2, KHÔNG paid)

Phân loại + xử lý nguyên nhân gốc. KHÔNG allowlist ngoại lệ mới nếu chưa chứng minh không ảnh hưởng product correctness.

| Nhóm đỏ | Chân | Giả thuyết loại | Hành động |
|---|---|---|---|
| `test_v21_mutation_runner.Proc.*` ×2 (`leaked` KeyError) | ubuntu mọi phiên | lỗi thật của test (API đổi) hoặc runner | đọc, xác định `leaked` key đến từ đâu, sửa nguyên nhân gốc |
| `test_v21_confine.FailClosed` (RangeEscaped: sleeper sống) | nhảy chân | flaky teardown (đua process) | đo, phân biệt flaky vs lỗi thật; sửa gốc, không skip |
| `test_v21_read_set.ToyRecord` (opened set lệch) | 3.11/3.12/macos | lỗi thật hoặc platform | đọc, xác định `data`/`tests/...` thừa-thiếu |
| `sealing` job | master/tag | **đỏ-chủ-đích** (record-currency chưa reseal) | GIỮ đỏ; KHÔNG reseal (quyền owner) |

**Nghiệm thu lane CI:** mỗi nhóm có kết luận phân loại + (nếu lỗi thật/flaky) commit sửa gốc + CI xanh chân liên quan.
`sealing` vẫn đỏ-có-tên-riêng — KHÔNG tính vào "CI PASS".

## 3. Lane C2 — Trần ngân sách USD (owner item 3.1, GATE của paid)

**Đã có sẵn:** `aisef2/app/usage.py` (5 lớp `CLASSES`, `_usd`, cost=None khi unknown, không bao giờ 0) + `settings.prices`
(validated) + `usage` trong RUN.json. **C2 còn thiếu:** trần tiền SỐNG trong `Budget` (hiện chỉ 4 counter; cost chỉ hậu
kỳ).

**Phạm vi code:** `aisef2/app/client.py::Budget` (+ `settings.py` cho `max_cost` optional):
- Budget nhận `prices` + `max_cost` (optional). `spend()` tính thêm 5-lớp token + USD, **dùng chung
  `usage.session_tokens`/`_usd`** để live-budget và account hậu kỳ KHÔNG đọc stream khác nhau (ý định đã ghi trong
  usage.py).
- `reached()`/`exceeded()` enforce `max_cost` **fail-closed**: `max_cost` đặt mà cost bất kỳ phiên unknown
  (steps_without_tokens / phiên không xong step / preflight không đọc) ⇒ run DỪNG (như `unaccounted`).
- **Không `max_cost`/không prices ⇒ hành vi byte-identical hôm nay** (OPTIONAL key, charter "absent ⇒ exactly a 2.0.0 run").

**Nghiệm thu C2 (CHỨNG MINH trước paid):**
- [ ] Diễn tập offline fake client: usage vượt trần USD ⇒ `reached()` trả max_cost, run DỪNG đúng điểm.
- [ ] Fake phát 1 step thiếu token ⇒ fail-closed (run DỪNG vì cost unknown, KHÔNG coi là 0).
- [ ] Không đặt giá ⇒ RUN.json + hành vi không đổi (so byte với baseline).
- [ ] Unit test mới + full suite xanh + mutation target Budget.* re-measure.

## 4. Lane B3+G5 — demo không credential (owner item 3.3, KHÔNG paid)

`aisef demo`: fake developer xác định + probe thật + journal thật + `--verify` thật, KHÔNG credential; **bắt buộc kèm ca
escape** (defect ngoài scope lọt reviewer). Nghiệm thu: lệnh chạy sạch trên repo trống, in PASS + FAIL + escape; có test.

## 5. Lane C3a/C4/C9 — giảm retry/lãng phí (owner item 3.5, KHÔNG paid, KHÔNG đổi authority)

- **C3a:** `no_progress` (đã có trong usage.py) → 1 dòng text thuần vào retry prompt; KHÔNG authority.
- **C4:** candidate == base (so SHA) ⇒ skip quality/review/scan, route DEVELOPER failure tại điểm đo CANDIDATE, tái dùng
  probe result admission.
- **C9:** spend stuck-retry tính vào trần tiền C2.
Nghiệm thu: mỗi mục có test; `NO_SIDE_RETRY_COUNTER` và các static rule kernel vẫn xanh.

## 6. Lane PAID — B1 + B7 (owner item 3.2/3.4, CHỈ sau khi C2 chứng minh)

- **B1:** canary live PASS: `bundle init --example calc-1-story` repo sạch, route attested → `delivery_verdict PASS` +
  `--verify` VERIFIED + 0 escape. FAIL thì báo nguyên trạng.
- **B7:** đo cost-of-trust USD/story trên canary + 1 run trả tiền; tách productive vs trust (công thức E4 ≈ 15.21p +
  0.219q); công bố cả khi xấu.
- **Trần tổng 2 lượt ≤ $60.** Diễn tập offline trước. Subagent (nếu dùng) dặn rõ binary cấm + kiểm DB/log sau.

## 7. Findings (owner item 4, KHÔNG sửa kernel đợt này)

- **FINDING os.kill(pid,0) Windows:** lập finding + phân tích tác động TRƯỚC khi đề xuất sửa kernel. Kernel frozen.
- **freeze_manifest V2_007 sha256 lệch** + **Q5-KERNEL-COMPARISON stale:** giữ OPEN, chuẩn bị phương án có evidence.

## 8. ĐO CUỐI ĐỢT 2 (một lượt gộp)

ruff + full suite cây chính; `git status closure-evidence/` sạch; mutation targeted các module đợt 2 đổi; CI (phân loại,
KHÔNG tuyên bố PASS khi job bắt buộc đỏ); chi phí USD thật; tick checklist + Nhật ký; báo cáo owner theo item 5.

## Thứ tự thực thi (tôn trọng gate)

1. Lane M (đăng ký kill set) + launch re-measure nền — chạy song song các lane offline.
2. Lane CI root-cause (song song).
3. Lane C2 (code + chứng minh offline) — **phải xong & xanh trước paid**.
4. Lane B3+G5, C3a/C4/C9 (offline).
5. Lane PAID B1+B7 — chỉ sau C2 chứng minh, trần $60.
6. Findings item 7 (song song, chỉ phân tích).
7. ĐO CUỐI ĐỢT + báo cáo.
