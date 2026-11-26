# B2-SPEND — gói trình owner quyết (một quyết định, hạn ≤ 2026-12-08)

**Trạng thái:** ĐỀ XUẤT (soạn 2026-11-26, theo Decision 4 PROPOSED: "PREPARATION GO; EXTERNAL ACTION AND
SPENDING HOLD"). Chưa liên hệ ai, chưa chia sẻ tài liệu nào ra ngoài, chưa chi đồng nào, chưa clone repo ngoài.
Mọi hành động external/paid chỉ bắt đầu sau khi owner ban hành quyết định này qua kênh chính thức
(B2-GROUND-TRUTH-PROTOCOL-DRAFT §5.1). Con số tiền là ƯỚC TÍNH để owner đặt cap, không phải cam kết.

## 1. Ba repo đề cử (licenses, snapshots, acceptance harnesses)

Từ nghiên cứu read-only B2-REPO-FEASIBILITY.md (9 ứng viên, 4 domain); mỗi repo kèm license SPDX, SHA snapshot
tại release tag, và harness chạy test:

| Repo | License | Snapshot (tag → SHA) | Acceptance harness | Domain |
|---|---|---|---|---|
| kellyjonbrazil/jello | MIT | v1.6.1 → `b43c9b24605ce2fca7bb303cdd845f8e814c15fa` | stdlib unittest, CI 3 OS | CLI (JSON filter) |
| lepture/mistune | BSD-3-Clause | v3.4.0 → `f19057fdf339affb61ca63c7fe28df7a951ec588` | pytest (uv-locked); ground truth tựa CommonMark spec đóng băng | thư viện parse |
| msiemens/tinydb | MIT | v4.9.0 → `1e39ad3a2d9eca57efd9019fd089b5a04676da95` | pytest, CI 3 OS; probe Python-callable + file-artifact | data store |

Alternate (nếu owner muốn đổi slot): bottle 0.13.4 (web/WSGI) hoặc sqlite-utils 4.2.1 (CLI+data, Apache-2.0).
Giới hạn khai báo: slate một ngôn ngữ (Python) — SHOULD "≥2 ngôn ngữ" của §2.3 không đạt trong ràng buộc
probe-catalog; chấp nhận giới hạn này hoặc chỉ đạo tìm vòng 2 một CLI phi-Python (đánh đổi mốc 26/01).

**Checklist clone-time §2.3 — ĐÃ ĐO 2026-11-26 trên macOS** (directive P3 ủy quyền; kết quả đầy đủ:
`B2-CLONE-CHECKS.md`, log thô: aisef-private-evidence/2026-11-26-b2-clone-checks/): cả ba repo ĐẠT mọi tiêu chí —
tag khớp SHA ghim, LOC trong khung (7.023 / 9.237 / 4.665), suite xanh 0,35s / 3,53s / 1,25s (bar <10′),
không cần mạng khi chạy test, sha256 tar snapshot đã ghi, mỗi repo một acceptance probe VERIFIED từ ngoài clone.
Còn lại trước manifest: leg Linux (CI side), re-grep độc lập §2.3(5) tại thời điểm đề xuất, ghim toolchain.

## 2. Hai evaluator độc lập — tiêu chuẩn, nguồn, CoI

- **Tiêu chuẩn (Q2 default):** kỹ sư phần mềm chuyên nghiệp ≥3 năm, đọc được Python test suite, KHÔNG có đóng
  góp/lịch sử dogfood với AISEF, không quan hệ báo cáo với owner; đủ 25–30h trong cửa sổ 29/12–19/01.
- **Nguồn — ĐÃ NGHIÊN CỨU CÓ SỐ ĐO 2026-11-26** (hồ sơ riêng kèm ứng viên ĐÍCH DANH + rate + CoI screen
  từng người: `aisef-private-evidence/2026-11-26-b2-evaluators/EVALUATOR-SHORTLIST.md` — tên người giữ ngoài
  repo công khai, chưa liên hệ ai): kênh vừa túi mục tiêu là **Upwork (gồm hồ sơ VN/khu vực)** và thị trường
  VN trực tiếp; Codementor sát mép; **Toptal/Fiverr-hourly KHÔNG vừa** ($60–150+/h). 10 hồ sơ công khai, top-4
  có đoạn đánh giá phù hợp; một standby được đề xuất. Giới hạn khai báo: Upwork chặn fetch tự động nên cột
  ứng viên Upwork-native cần owner duyệt bằng phiên đăng nhập của chính owner.
- **CoI form (mỗi evaluator ký trước onboarding):** quan hệ với owner/dự án; đã từng thấy mã AISEF chưa; quan
  hệ với các repo ứng viên (maintainer/contributor = loại với repo đó); cam kết không dùng LLM có truy cập
  internet khi label (offline-only, §3.3).
- **Độc lập khi label (§3.3):** evaluator thấy BUNDLE yêu cầu + snapshot repo + harness label; KHÔNG thấy
  kernel, seeding recipe, nhãn của nhau (hash-commit rồi mới reveal, §3.5).

## 3. Thù lao + trần chi (SỐ ĐO 2026-11-26 — ruling §4: mục tiêu $1.500–2.500; $6.000 chỉ là trần ĐỀ XUẤT)

Khối lượng mỗi evaluator: onboarding+pilot ~6h, label 3 repo × ≥9 item ≈ 27 item × 45–60′ ≈ 20–27h,
hỗ trợ adjudication ~3h → **~30h/người** (60h tổng). Rate đo được (nguồn + ngày trong hồ sơ riêng):

| Kênh | Rate đo | Tổng 2×30h | Vừa mục tiêu $1.500–2.500? |
|---|---|---|---|
| Upwork mid-senior Python/QA (toàn cầu) | $20–45/h | $1.200–2.700 | VỪA ở ≤~$41/h |
| Upwork VN/khu vực senior | $20–35/h | $1.200–2.100 | VỪA thoải mái |
| VN trực tiếp (ITviec median ×1,5–2,5 freelance) | $15–35/h | $900–2.100 | VỪA NHẤT về giá (owner tự lo hợp đồng/escrow) |
| Codementor | $32–120/h | ≥$2.400 | sát mép |
| Toptal / Fiverr-hourly | $60–150+/h | $3.600–9.000+ | KHÔNG vừa |

**Cấu trúc đề xuất (trong mục tiêu):** Upwork fixed-price **$1.000–1.200/evaluator** (~$33–40/h cho scope 30h),
mỗi ghế 2 milestone: 40% khi onboarding + repo 1 label xong (≤05/01), 60% khi repo 2–3 + adjudication xong
(≤19/01); vet 3 chọn 2, người thứ ba làm standby văn bản (tùy chọn retainer onboarding ~$150–200); hai evaluator
label cùng thứ tự repo để drop giữa chừng thay người được ở ranh giới repo; drop sau 10/01 → thu scope đối xứng,
ghi là protocol deviation. **Trần:** $6.000 giữ nguyên là TRẦN ĐỀ XUẤT (ruling §4); chi kỳ vọng $2.000–2.600 gồm
phí nền tảng. Mọi dòng chi ghi `closure-evidence/v2/v2.3/B2-SPEND.json` (append-only, mở khi quyết); vượt trần =
một quyết định owner mới.

## 4. Bảo mật + điều khoản (Q7 default)

NDA phạm vi hẹp: không tiết lộ tài liệu chưa phát hành (bundle yêu cầu, seeding sau reveal, số đo trước báo
cáo); không hạn chế quyền nghề nghiệp khác; evaluator được nêu tên (hoặc ẩn danh theo nguyện vọng) trong
B2-ORACLE manifest. Không chuyển cho evaluator bất kỳ secret/credential nào — chỉ snapshot công khai + bundle.

## 5. Quy trình ủy quyền + lịch (theo §5.2, zero slack sau 08/12)

1. **≤08/12** — owner ban hành MỘT quyết định: slate 3 repo (+alternate swap nếu muốn) + kênh evaluator + cap
   + gật đầu clone-time checks. 2. 08–29/12 recruit (2 tuần + 1 tuần đệm lễ); engineering song song: Tier-0
   corpus + seeding + bundle cho repo đã duyệt (xong ≤05/01). 3. 29/12–05/01 onboarding + pilot Tier-0.
   4. 05–19/01 label độc lập (hash-commit→reveal). 5. 19–26/01 adjudication + assembly. 6. **26/01** owner ký
   B2-ORACLE-SIGNED. Đo lường: offline-only, `aisef grade` trên candidate dựng sẵn, không call trả phí (Q9);
   NO-GO tiền cam kết duy nhất: false-PASS P0/P1 (§4.3).

## 6. Dòng chữ ký owner cần (một lần)

> APPROVE B2-SPEND: slate = {jello v1.6.1, mistune v3.4.0, tinydb v4.9.0} [hoặc swap …]; evaluator qua kênh
> {a|b|c}, 2 người theo tiêu chuẩn §2; cap = $X; clone-time checks §1: GO; điều khoản §4 default. Ledger
> B2-SPEND.json mở từ ngày ký.
