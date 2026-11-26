# C-1 — các đề xuất amendment sau adversarial review (2026-11-26)

**Status: ĐỀ XUẤT cho owner.** C-1 đã đóng băng (amendments/C-1-FORMAT-4-FREEZE.md); mọi thay đổi là amendment
có ngày, có phạm vi, do owner ban hành — tài liệu này tự nó không sửa gì. Nguồn: lượt adversarial review độc lập
của landing 0cd6cc57 (toàn văn + probe script: aisef-private-evidence/2026-11-26-advrev-f4/; cũng chính là
artifact "independent adversarial review of the transition invariants" mà điều kiện flip của ruling §1 đòi —
verdict tổng: SOUND, 390 ô đối chiếu adapter-free, 0 lệch không-ghim; 4 lỗ hổng CONFIRMED đều là lỗ của CONTRACT,
không phải lệch triển khai).

## A1 — §4.5 `story/completed` cần biên `run/end` (C1 — lỗ duy nhất có hệ quả xuôi dòng)

- **Đo được:** marker append SAU `run/end` được writer + reconstruct chấp nhận (chỉ fold từ chối) — tái sinh
  đúng bất đối xứng M2 trên chính sự kiện G6 tin. Input tái lập trong probe.py.
- **Chữ amendment đề xuất (một dòng, soi gương luật của §4.4):** "`story/completed` MUST appear before
  `run/end` — the completed-story marker of a closed run is written at finalize, never appended to a closed
  journal; violation refused at the append and reconstruct sites (rule+kind+seq)."
- **Nghĩa vụ kèm:** red-before test (input C1 của probe), đổi `_completed4` thêm biên (một nhánh, soi
  `_attestation4`), tripwire hiện có không đổi. Hàng rào tạm đã dựng KHÔNG chờ amendment: G6 addendum
  2026-11-26 biến fold-before-trust thành ràng buộc chịu tải (từ chối cả lớp này ở verify-time).

## A2 (tùy chọn) — R-GATE: decision phải cite ĐỦ mọi `gate/check` của gate đó (C3)

- **Đo được:** decision `passed:true` chỉ cite check pass (bỏ check fail cùng gate) được chấp nhận — đúng chữ
  đã freeze ("any cited gate/check"), kernel luôn cite đủ (M3), nhưng gần như miễn phí để lách với journal
  dựng tay. **Chữ đề xuất:** "a `gate/decision` MUST cite every prior `gate/check` of its gate."
- Chi phí: một vòng đếm tại `_gate4` + red-before test. Không chạm hành vi kernel thật.

### A2 — CẬP NHẬT sau Phase-1 proof (2026-11-26, owner ruling §2 CONDITIONAL GO): KHÔNG triển khai được
### trong cách đọc đã nêu; cần amendment chính xác dưới đây trước khi đổi authority

**Kết luận đo được (file:line):** chữ A2 gốc ("every prior gate/check of its gate") và mọi biến thể
"span kể từ decision cùng-gate trước đó" đều từ-chối journal mà kernel VIẾT THẬT hoặc mà thiết kế v2.3
đã cố định là hợp lệ — vi phạm đúng điều ruling §2 cấm. Ba chứng cứ:

1. **Gate id không phải là biên scope.** Trường `gate` là khóa gộp duy nhất ở tầng format
   (`event.py:217-219`, `Cite(GATE_CHECK, True, "gate")`), nhưng kernel chỉ có MỘT gate id — `GATE = "story"`
   (`orchestrate/gate.py:10`) — cho mọi story, mọi attempt. Scope thật của một decision là MỘT STORY ATTEMPT
   (`checks` khởi tạo mỗi attempt tại `story_runner.py:226`, decision cite đúng list đó tại `:449`); attempt đó
   KHÔNG hiện diện trong payload: `gate/check` = {gate, check, passed, detail}, không `story_id` — story chỉ nằm
   trong chuỗi `check` theo quy ước `f"{story_id}:{stage}"` (`gate.py:16`), không phải contract (consumer
   `app/feedback.py:86-87` đã phải parse prefix này — bằng chứng quy ước, không phải schema).
2. **Tiền đề "kernel luôn cite đủ (M3)" SAI trên nhánh contained-fault E5.** Helper có thể ghi `gate/check`
   rồi raise TRƯỚC khi runner bắt được seq: `merge.py:44-60` (`reprove` — `prove()` tại `:52` raise ở vòng ≥2
   làm mất các check `:56` đã ghi ở vòng trước; `prove` raise được qua `run_probe`/`scope.acquire`,
   `proof.py:80-112`); cùng dạng cho comprehension `review.py:43-46` và `security.py:51-52`. Handler E5
   (`story_runner.py:409-443`) chỉ ghi thêm MỘT check theo stage, decision `:449` cite `checks` đã bắt được —
   journal khi đó chứa gate/check cùng-gate, cùng-span, KHÔNG được cite, và M7 của FORMAT-4-DESIGN-DRAFT đã
   hợp-pháp-hóa đuôi fault này như chuỗi production. (Decision nhánh này luôn `passed: false`.)
3. **Span liền kề vỡ dưới C5-PARALLEL.** C5 (DRAFT implementation-ready, viết TRÊN C-1 đã đóng băng, không
   mở lại schema) chủ định cho append của nhiều story đan xen qua một `LockedRun` (C5 draft §3.4; fact C11:
   StoryState per-story, bảng RUN story-blind) — check của story B nằm hợp lệ TRONG span của decision story A
   dưới cùng gate id "story" mà không được A cite.

**Chữ amendment chính xác cần owner ban hành (hai phần, f4-only theo mẫu CR-3):**

> A2′ (schema): In format 4, `gate/check` and `gate/decision` each gain required field `story_id` (non-empty
> string). Formats 1–3 never admit the field (CR-3). The kernel's `orchestrate/gate.py` writes it from the
> value it already closes over.
>
> A2′ (rule, replacing A2's proposed sentence): A format-4 `gate/decision` with `passed: true` MUST cite
> every `gate/check` carrying the same (`gate`, `story_id`) appended after the latest prior `gate/decision`
> of the same (`gate`, `story_id`) (after `run/begin` when none exists); refusal at append AND reconstruct
> naming event, seq and rule. A `gate/decision` with `passed: false` is EXEMPT from completeness — the E5
> contained-fault tail legitimately strands helper-emitted checks (evidence item 2) — and stays subject to
> R-GATE as frozen. The C3 attack dies for passing decisions (hiding a failed check refuses the decision);
> hiding a check under an already-failing decision changes no authority.

**Nghĩa vụ kèm khi triển khai A2′:** red-before (input C3 của probe); negative controls — passing decision
bỏ sót check FAIL và bỏ sót check PASS cùng (gate, story_id)-span đều bị từ chối; pinned-ACCEPTED controls —
multi-gate, retry (span attempt sau tính từ decision attempt trước, cùng story), hai story đan xen kiểu C5,
và đuôi fault E5 (decision false bỏ sót check bị strand); golden-corpus parity (10 fixture + delegation f1–f3
không đổi); proof pattern phát xạ kernel đường thành công (`story_runner.py:226-449`: mọi check đều vào
`checks` khi không có exception — đã kiểm từng call site 2026-11-26).

**Phương án thay thế owner có thể chọn:** gia cố kernel leak-proof (try/finally bắt seq trong
`reprove`/`review`/`scan`) làm completeness vô-điều-kiện đúng trên nhánh fault — nhưng là thay đổi kernel
ngoài tầng validation f4 của C-1, và KHÔNG chữa việc thiếu khóa scope (chứng cứ 1, 3): A2′ (schema) vẫn cần.

## E1/E2 (biên tập, không đổi hành vi) — sửa câu §3.1 "nothing else reads data" (mâu thuẫn nội tại với chính
bullet RUN của nó — hai split là cách đọc nhất quán duy nhất, đã triển khai đúng); ghi chú §4.3 `detail` là
prose-only (FAILED với detail rỗng hợp lệ — nếu owner muốn bắt buộc non-empty, đó là một dòng schema).

## Ghi nhận không cần amendment

- C2 (RUN-scope không đóng ở A/R — parity f3): đã thành scope-note trong docstring format4.py + nghĩa vụ
  fold-before-trust của G6. C4 (proof tươi trên probe cũ — parity f3, L7): ghi vào kế hoạch test W2c.

---

**Trạng thái có ngày (append 2026-11-26, không sửa chữ đề xuất ở trên):** A1 — BAN HÀNH + triển khai
(amendments/C-1-A1-STORY-COMPLETED-BEFORE-RUN-END.md, cách đọc ABANDONED được owner chấp nhận). A2′ — BAN HÀNH +
tích hợp `f0c230f3` (amendments/C-1-A2-GATE-COMPLETENESS.md, Option A, review disposition trong phụ lục).
E1/E2 — **APPROVED** (owner ruling 2026-11-26 §5) qua amendment có ngày amendments/C-1-E1-E2-EDITORIAL.md,
phi hành vi, không required field mới.
