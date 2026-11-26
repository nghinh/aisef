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

## E1/E2 (biên tập, không đổi hành vi) — sửa câu §3.1 "nothing else reads data" (mâu thuẫn nội tại với chính
bullet RUN của nó — hai split là cách đọc nhất quán duy nhất, đã triển khai đúng); ghi chú §4.3 `detail` là
prose-only (FAILED với detail rỗng hợp lệ — nếu owner muốn bắt buộc non-empty, đó là một dòng schema).

## Ghi nhận không cần amendment

- C2 (RUN-scope không đóng ở A/R — parity f3): đã thành scope-note trong docstring format4.py + nghĩa vụ
  fold-before-trust của G6. C4 (proof tươi trên probe cũ — parity f3, L7): ghi vào kế hoạch test W2c.
EOF
cd /Users/nghinh/Downloads/projects/ai-sdlc && git add aisef2/journal/format4.py docs/v2.3/drafts/G6-RESUME-DESIGN-DRAFT.md docs/v2.3/drafts/C-1-AMENDMENT-PROPOSALS.md && cat > /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/cmsg <<'EOF'
v2.3: adversarial review of the C-1 landing — SOUND; the contract gaps get dispositions, not silence

The independent review (390 adapter-free cells, 0 unpinned divergences, every tripwire proven to trip; evidence in
the private folder) is the flip-gate artifact the freeze record requires. Four CONFIRMED findings are all gaps of
the frozen CONTRACT, not implementation divergences. Dispositions landed: C1 (story/completed accepted after
run/end at append/reconstruct — the M2 asymmetry on exactly the event G6 trusts) -> G6 addendum makes
fold-before-trust NORMATIVE (reconstruct alone never sufficient; a fold-refused marker = tampering class, whole
resume refused) + amendment proposal A1 with exact wording and red-before obligations; C3 (R-GATE selective
citation) -> optional amendment A2; C2 (RUN-scope not closed at A/R, f3 parity) -> scope note in the format4
module docstring; C4 (fresh proof over stale probes, f3 parity, L7) -> W2c test-plan note. All amendment issuance
stays the owner's; no frozen text edited.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
git commit -F /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/cmsg && git push origin release/v2.3-big 2>&1 | tail -1