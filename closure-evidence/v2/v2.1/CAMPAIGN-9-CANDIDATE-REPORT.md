# AISEF 2.1 — báo cáo ứng viên sau campaign 9 (2026-10-20)

Nhánh `v2.1/probe-window`, HEAD `a7a23ef0`, snapshot đo `4ec961e` (cây mã `69b0ea9`). Báo cáo trung thực cho chủ dự án.
**Chưa** push/tag/publish/release/reseal; **không** tự ghi nhận nghiệm thu. Đây là ứng viên để chủ dự án **duyệt**, không
phải bản đã nghiệm thu.

## 1. Kết luận một dòng

Bản 2.1 **chạy đúng** ở mọi phép đo thật tôi làm được (0 regression mã trên hai HĐH, kernel valid 18/18 run thật với
model trả tiền, không rò khoá, không chạm store người dùng). Nhưng nó **chưa PASS sạch** ở hai điểm đã-biết, đã ghi đầy
đủ bằng chứng, và là **quyết định của chủ dự án**, không phải của tôi: (a) 85 survivor mutation chưa pin ở mã mới; (b) các
record sealed cần reseal cho 2.1. Thêm một **phát hiện** cần chủ dự án phân loại: đua PL-7 ở teardown timeout của `aisef run`.

## 2. Bảng trạng thái

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Bản ghi mutation 2.1 | XONG — **FAIL trung thực** (449 audited / **85 unpinned**), `--check` xác nhận tái lập + cây HEAD khớp | `MUTATION.json`, `MUTATION-SUMMARY.json`, `mutation/SURVIVOR-AUDITS.json` (8fae707b) |
| Kiểm toán survivor (534) | XONG — 344 AUDITED / 57 EQUIVALENT / 85 nợ test / 48 carried; hai lớp chặn giả mạo ĐẠT | `campaign-9/SURVIVOR-AUDIT-SUMMARY.md`, `survivor-audits/` (0ee530b8) |
| Record dẫn xuất (7) | XONG — gen 7/7, diff vs sealed phần lớn là digest mã; 3 delta ngữ nghĩa cho owner | `candidate-evidence/CANDIDATE-EVIDENCE-8fae707b.tar.gz` (008c0073) |
| Read-set / reach ở head cuối | XONG — 0 target/kill-test/closure đổi từ snapshot → 0 target lật, **không cần campaign bù** | mục 4 |
| Cổng lint | XONG — `ruff check .` xanh | f666bdfb |
| Bộ test macOS (py3.14) | XONG — Ran 7929; 15 fail = 13 reseal + 2 môi trường; **0 regression**; leak sạch; v1_evidence_guard PASS | `$SP/m21/c9/macos_suite.out` |
| Bộ test Docker Linux | XONG — Ran 7929; 14 fail + 2 err = 13 reseal + 3 môi trường; **0 regression**; owned at_exit=0 escaped=0 | `$SP/m21/c9/suite-linux-out/` |
| CLI + OCR thật offline | XONG — PASS (OCR open-code-review v1.12.12, 3× delivery PASS, read-back OK) | `$SP/m21/c9/cli_ocr.out` |
| E2E guest Linux | XONG — hardened **PASS**; X1 1 fail = **phát hiện PL-7** (teardown timeout) | `$SP/m21/c9/e2e/out/e2e-{X1,hardened}.json` |
| Bundle ứng viên LedgerLock | XONG — migrate 53 kept/6 withheld; APPROVE.sh (owner ký) kiểm = READY + load OK; **không ký** | `ledgerlock-candidate/` (b9c3f24e) |
| E2 chiến dịch thật (18 run) | XONG — mycombo/9router; kernel **valid 18/18**; an toàn xác nhận | `e2/campaign-real/` (142b15f7) |
| Backlog 85 nợ test | XONG — ghi, ưu tiên rò bí mật diagnostics; không chặn pin | `BACKLOG-OWED-KILL-FILES.md` (aa73142d) |
| offline_groups (mockup/references) | **BỎ QUA có lý do** — máy chưa có playwright node_modules + references clones (đúng owner item-6) | mục 7 |

## 3. Bản ghi mutation — vì sao FAIL trung thực

Campaign 9 (snapshot `4ec961e`): **16.080 mutant, 15.546 KILLED, 534 SURVIVED, 0 TIMEOUT/INFRA/NOT_RUN**, 614 target
accounted exactly once. Trong 534 survivor: 449 đã audit (372 AUDITED quan sát-được-nhưng-không-ai-phụ-thuộc + 77
EQUIVALENT chứng minh từ mã), **85 chưa pin** (hành vi quan sát được mà bộ test không bắt — phản biện mù từ chối gọi là
tương đương). `v21_mutation_record.py` ⇒ `MUTATION_VERDICT: FAIL` vì 85 > 0. Theo đúng quyết định owner 2026-10-19 (a):
ghi giới hạn + ghim, **không** PASS giả. `--check`: lỗi DUY NHẤT là verdict; không "not what the kept artifacts derive",
không "HEAD mismatch" ⇒ bản ghi tái lập được và cây HEAD khớp FINAL_HEAD. Kiểm toán bắt và loại 2 vị trí `cli_invocation`
mà audit campaign cũ remap **che** một gap mới (quy tắc "duyệt bị ảnh hưởng bởi thay đổi ngữ nghĩa chỉ là lịch sử").

85 nợ tập trung ở mã **mới/viết lại trong cửa sổ sửa**: `bundle_cli` (đường migrate/seal/assess của ngữ nghĩa approval
PM-9) và `lineage` (kế toán dòng dõi/usage) — các trường báo cáo người-vận-hành kiểm theo giá trị nhưng không theo
khoá/cấu trúc. Một mục an ninh: `diagnostics.Sink.__init__` (bỏ phần tử bộ redaction ⇒ bí mật JSON-escaped lọt artifact;
mã đúng, chỉ chưa pin). Tất cả ở `BACKLOG-OWED-KILL-FILES.md`.

## 4. Read-set / reach — vì sao không cần campaign bù

Giữa snapshot `4ec961e` và HEAD: `aisef2/` 0 tệp, `tests/` 0 tệp, `validation/v2/` 0 tệp đổi (chỉ 4 doc + 3 tệp
`validation/experiments/` của bộ E2). Nên read-set và reach của mọi target **y hệt** ở head cuối; không target nào "lật";
đây chính là điều 614 target `reused_after_mechanical_proof` đã chứng minh từng-cái trong bản ghi.

## 5. Hai bộ test đầy đủ — 0 regression, phân loại từng lỗi

Mỗi bên Ran 7929. **13 fail CHUNG cả macOS và Linux** là RED-SUITE record-binding (Q0 checker calibration, freeze-manifest,
plan-correction, k-nowork, c2-orchestration ×2, c2-p5 ×2, p5-proposal, Q5-comparison, conformance-ruling): đỏ **vì** record
sealed đã trôi so với cây 2.1 — **chờ owner reseal**, không phải lỗi. Giống hệt drift `candidate_evidence` ghi.

Còn lại là môi trường (đã **đo**, không phải lỗi mã):
- macOS `c2_delivery HistoricalAttempt4`: `opencode.db` thật của máy có session tạo sau attempt-4.
- macOS `read_set.Merge`: TMPDIR mặc định dưới `/var`→`/private/var`; **đã xác minh**: đặt TMPDIR sạch thì PASS, mặc định thì FAIL.
- Linux `test_cli … path`: container không có `node`.
- Linux `mutation_runner.Proc` ×2 err: pid-namespace/procps container thiếu key `leaked`.

Kỷ luật process: macOS leak sạch (at_exit=0, escaped=0), v1_evidence_guard PASS, cây sạch sau; Linux owned at_exit=0 escaped=0.

## 6. E2E guest Linux — phát hiện PL-7 (cần owner phân loại)

Hardened profile **PASS** (0 fail). X1 profile (seccomp off, cái bwrap cần) 1 scenario fail: `S3t` — khi session **timeout**,
teardown của kernel báo `RangeEscaped` pid 1681 và `REFUSED` delivery, **dù** mọi check khác xác nhận không process nào sống
sót (re-looks []). Đây là **đua PL-7** (child bị bắt lúc đang thoát, dưới tải). Baseline implementer (B03-R3-E2E.md run1/2)
S3t sạch. Mutation runner đã vá lớp này (RangeEscaped-đã-biến-mất giữ outcome) nhưng **teardown của `aisef run` kernel vẫn
REFUSED** ⇒ timeout dưới tải có thể FAIL delivery oan. **Fail-closed (an toàn)**, nhạy timing. Cùng lớp "fix release()".

## 7. E2 chiến dịch thật — kernel đúng, an toàn, so sánh ở n=3

18 run thật trên mycombo/9router (owner duyệt 2026-10-18, khoá có trong env). **valid = true cả 18.** An toàn đã xác nhận:
secret scan 0/277 tệp chứa giá trị khoá; `store_stat $HOME before == after: True` (không chạm store người dùng);
`refused_identity 0` mọi arm (preflight identity giữ); replay exit 0 (manifest niêm phong tái lập). 53,8M token vào /
642K ra, cost=null.

| workload | arm | giao 12/12 (trên 3 rep) | escaped_defects | false_rollbacks |
|---|---|---:|---:|---:|
| w1-a | direct | 1 | **2** | 0 |
| w1-a | aisef / aisef+ | 1 / 1 | 0 / 0 | 1 / 1 |
| w2 | direct | 3 | 0 | 0 |
| w2 | aisef / aisef+ | 1 / 3 | 0 / 0 | 1 / 0 |

- **Kernel không bao giờ giao ra defect**: aisef/aisef+ escaped_defects = 0; khi developer làm dở, nó rollback (fail-closed)
  thay vì giao. Arm **direct giao ra 2 defect** ở workload khó w1-a.
- **Giá phải trả**: kernel tốn ~4–7× token và có **false rollback** (rollback cả run mà oracle dễ tính có thể nhận).
- **w1-a khó cho MỌI arm** ⇒ ở n=3, non-determinism của model lấn át hiệu ứng arm; nên chạy thêm rep, chưa phải kết luận.
- 6 "fail" đều là kernel rollback đúng một plan có story không commit; **không** phải lỗi kernel.

## 8. offline_groups — vì sao bỏ qua

Nhóm `mockup` (cần playwright node_modules) và `references` (cần các clone của `references/PINS.md`) **chưa cài trên máy
này**. Hai bộ test đầy đủ cũng đã skip chúng (thiếu `node`, thiếu clone). Theo đúng owner item-6 (2026-10-15): chạy nếu
làm được offline, nếu không thì nêu lý do — đây là **bỏ qua có lý do**, không phải fail.

## 9. Thời gian — giờ máy (đo) tách giờ sửa

**Giờ máy (wall, đo thật, chạy nền — ~0 token model của tôi):**

| việc | giờ máy |
|---|---|
| Campaign 9 (đo mutation, đã xong trước) | ~34 giờ |
| Bản ghi mutation `--write` | ~48 phút |
| Bản ghi mutation `--check` | ~50 phút |
| Record dẫn xuất (candidate_evidence, gồm K-NOWORK) | ~22 phút |
| Bộ test macOS | 89 phút (5366 s) |
| Bộ test Docker Linux | ~70–90 phút (cgroup CPU 4735 s) song song |
| CLI + OCR thật | ~5 phút |
| E2E guest Linux (2 profile) | ~6 phút |
| E2 chiến dịch 18 run | ~2 giờ (driver 7023 s reps 2–3 + rep 1 ~26 phút) |

**Giờ sửa / phân tích của tôi (không phải giờ máy):** gộp 449 audit về bản ghi trung thực (viết + 2 lần kiểm chặn giả mạo);
sửa 1 dòng `e2_launch.py` (`os.nice(0)`→`getpriority`, EPERM macOS); 5 lỗi lint vặt; phân loại từng lỗi test (đo lại
`read_set` với TMPDIR sạch; đọc traceback 2 HĐH); dựng APPROVE.sh LedgerLock + kiểm. Đây là giờ sửa nhỏ; phần lớn lịch là
**chờ giờ máy**, không phải sửa. Không có con số dự báo nào bị dùng làm giờ đã-đo.

## 10. Giới hạn còn CHẶN nghiệm thu (quyết định của owner, không phải của tôi)

1. **Mutation 85 chưa pin** — bản ghi FAIL trung thực. Owner đã chọn (a) ghi + ghim; viết 85 kill file là backlog. Nếu
   owner muốn PASS sạch trước nghiệm thu thì phải viết (đặc biệt `diagnostics` rò bí mật) rồi đo lại scope ảnh hưởng.
2. **Reseal record 2.1** — 13 RED-SUITE đỏ cho tới khi owner reseal Q0-calibration (checker 52→54), AUTHORITY-INVENTORY
   (rows 245→247 + ACTIVE_V2_AUTHORITY), C2-P5 verdict, và các digest plan/proposal/conformance. `candidate_evidence` đã
   suy dẫn bản sẽ-ghi; reseal là lệnh owner (một số record write-once).
3. **PL-7 teardown `aisef run`** — owner phân loại: chấp nhận (fail-closed) hay vá như mutation runner đã vá.
4. **E2 n=3 chưa đủ kết luận** — nếu muốn khẳng định hiệu ứng arm, cần thêm rep (w1-a khó, phương sai lớn). Owner adopt
   approval thật (APPROVE.sh w1-a/w2 + `--adopt-owner`) rồi replay để chốt chủ thể.

## 11. Commit lượt này (nhánh `v2.1/probe-window`)

```
a7a23ef0 fix(e2): e2_launch.py nice via getpriority (EPERM macOS)
142b15f7 E2 real campaign (18 runs): evidence + honest reading
aa73142d backlog: 85 owed kill files (owner (a), not a blocker)
b9c3f24e LedgerLock candidate bundle (migrate; not signed) + APPROVE.sh
f666bdfb chore(lint): ruff check . green
008c0073 candidate evidence: 7 derived records diffed vs sealed
8fae707b mutation record — honest FAIL, 85 unpinned (owner (a))
```

Còn của owner (không tự quyết): D-OCR-1, V21-65, PM-9 chọn tệp nhị phân, PM-13 handshake, B-02, B-04, B-08, B-09 bậc 2c/3,
B-10, F, RM-3; + 4 giới hạn mục 10.

Ghi 2026-10-20.
