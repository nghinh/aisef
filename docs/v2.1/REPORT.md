# AISEF 2.1 — Báo cáo trạng thái (2026-10-06, bản sửa theo yêu cầu nghiệm thu; §0 cập nhật 2026-10-14; §0.9–§0.10 và §6 cập nhật 2026-10-15)

**Chưa đủ điều kiện phát hành 2.1.** Cách ly hệ điều hành: có mã opt-in, đã đo trong Linux guest và đã chạy một lượt
`aisef run` thật qua CLI thật với mô hình kịch bản (§0.4). Lượt live: ba lượt canary nhỏ với mô hình thật do chủ dự án
tự chạy ngày 2026-10-15 (§0.10; ≈ 0,599 USD là **ước tính**); **chưa có** lượt live nào của OCR, của vòng sửa review, của
`--parent`/`bundle continue` sau lỗi hay của cách ly với mô hình thật, và chưa có số đo đối chứng; CI Windows/Linux chưa
chạy cho 2.1 (chưa push). Cây `aisef2/` đã đổi sau bản ghi mutation B-03 (cửa sổ probe 2026-10-15, §0.9): bản ghi
mutation (§0.3), 19 hàng hiệu chuẩn, các bản ghi phái sinh và suite phải làm lại cho cây ấy. Suite đầy đủ theo commit: §5.
Không có gì được push, gắn tag, publish, deploy; không phiên kỹ thuật nào gọi provider trả tiền (ba lượt canary do chủ dự
án tự chạy trong terminal của mình). Chủ dự án chưa nghiệm thu, chưa duyệt phát hành, chưa duyệt ngân sách 140 USD của
chiến dịch, chưa duyệt B-02/B-04/B-08/B-10 — báo cáo này không thay cho những quyết định đó; B-09: §0.10.

Tài liệu đi kèm: [RED-SUITE.md](RED-SUITE.md) (từng test đỏ), [ADR-V2.1.md](ADR-V2.1.md),
[ANCHOR-THREAT-MODEL.md](ANCHOR-THREAT-MODEL.md), [USAGE-2.1.md](USAGE-2.1.md), [decisions/](decisions/) (hồ sơ B-01, B-04,
B-08, B-09, B-10), [STATUS.md](STATUS.md) (phát hiện → sửa, theo từng dòng).

## 0. Cập nhật 2026-10-14 — B-03 vòng 3–4 (quyết định 2026-10-12 của chủ dự án đã thực hiện; B-02, B-04, B-08, B-10 **chưa** được duyệt; B-09: §0.10)

**Ba trạng thái tách riêng** (không lấy cái này thay cái kia):

| Trục | Trạng thái | Căn cứ |
|---|---|---|
| Mutation B-03 | bản ghi V2.1: 528 target, 13.581 mutant, **0 mutant chưa quyết**; `MUTATION_VERDICT` **PASS** (`MUTATION-SUMMARY.json`, `v21_mutation_record.py --check` PASS) — đo trên cây `aisef2/` `1d4f0156…`, **đã đổi sau đó** (§0.9) | §0.3 |
| Tích hợp có cách ly (`aisef run` thật, mô hình kịch bản) | **đạt** ở M4 trên Linux guest | §0.4, `closure-evidence/v2/v2.1/e2e-linux/` (cây `427afeec…`) và `…/e2e-linux-final/` (cây `1d4f0156…`) |
| Hiệu quả / chất lượng với mô hình thật | **chưa đo** (ba lượt canary tầm thường chỉ cho thấy đường chạy) | §0.6, §0.8, §0.10 |
| Sẵn sàng phát hành 2.1 | **chưa** | §0.8 |

"KILLED" là **mutation** (test thật bắt được thay đổi nhỏ của mã). Nó không thay cho kiểm chứng tích hợp hay cho số đo
với mô hình thật. AUDITED/EQUIVALENT **không** phải kill và được báo riêng.

### 0.1 Chín mutant còn mở của 2026-10-12: quyết định đã áp dụng, đã làm, đã kiểm chứng (và chưa)

Quy tắc chủ dự án đặt cho vòng này: mục tiêu là chốt hành vi đúng và bằng chứng tương ứng; mutation chuyển PASS **không**
được dùng làm căn cứ chọn yêu cầu; audit ≠ KILLED; tái dùng kết quả cũ chỉ khi có căn cứ phụ thuộc cụ thể. Chỉ mục (từng
mutant: id duy nhất, vị trí mã, hành vi thay đổi, yêu cầu, quyết định áp dụng, cách kiểm chứng):
[decisions/B03-R3-INDEX.md](decisions/B03-R3-INDEX.md).

| # | Mutant (id = `target#index @ module-sha12` lúc `3dc827b`) | Quyết định áp dụng | Kết quả |
|---|---|---|---|
| 1–4 | `confine._judge#142/#143/#157/#158` (`devpts`, `mqueue` trong tuple loại trừ) | **chứng minh nguồn gốc, không dựa tên hay vị trí**: mount ghi được ngoài workspace chỉ được chấp nhận khi chứng minh là của sandbox (loại fs, nguồn = tên pseudo, super block không có trong bảng mount của host đọc *trước* phiên, nhóm peer, namespace) hoặc là một trong sáu node thiết bị `--dev` được cho phép; không xác định ⇒ từ chối ("chưa đủ điều kiện cách ly"). [B03-R3-conf.md](decisions/B03-R3-conf.md) | điều khoản cũ và 4 mutant của nó không còn; 118 mutant của `_owned` và các tên mới bị test của cả trường hợp được phép lẫn trường hợp thoát ra ngoài giết; bubblewrap 0.12.0 thật trong Linux guest: điều khoản cũ chấp nhận cả 12 dòng lệnh đo, 9 trong đó là đường ghi ra host |
| 5–6 | `confine.measure#40/#49` (`LANG` trong khoá môi trường truyền xuống) | **locale `C` cho tiến trình con thu bằng chứng**, ghi vào `rep["locale"]`; locale của phiên và của người dùng không đổi | kiểm môi trường **chính xác** tại điểm exec (mô phỏng) và với bwrap thật (guest); **chưa đo** thông báo dịch (image guest chỉ có `C`/`C.utf8`/`POSIX`) |
| 7–8 | `usage.no_progress#13/#23` (`story/commit` không còn kết thúc một lượt thử) | **miền = mọi journal mà các projection chấp nhận**: một lượt đã commit là tiến triển và không bao giờ bị báo; journal projection từ chối thì `--verify` từ chối ở ranh giới có tên (`_projection_refusal`, finding có kiểu). [B03-R3-usage.md](decisions/B03-R3-usage.md) | hàm cũ không còn (13/23 tan biến, **không** tính là KILLED); mutant của hàm mới bị giết bằng hành vi; ranh giới chạy trên 89 journal format 3 + journal smoke 2.0.0: 0 từ chối sai |
| 9 | `review_verify.detail#22` (`sort_keys`) | **giới hạn 1.500 ký tự chỉ áp dụng cho phần tóm tắt**; reproducer đầy đủ đã che bí mật nằm trong artifact `review-findings/…` tạo-một-lần, có tên trong dòng journal và trong manifest bằng chứng; không có artifact ⇒ `CAPABILITY_UNRUNNABLE`, mảnh bị cắt không bao giờ chặn story. [B03-R3-detail.md](decisions/B03-R3-detail.md) | 12.000 finding đối kháng (câu dài nhất 1.492); thông tin quyết định sau ký tự 1.500; bí mật (chuỗi, số, vắt ngang chỗ cắt); chạy thật |

Cũng thuộc chỉ thị và đã làm: `ProcessRange.release()` bị hai luồng gọi — sửa (một claim một chuyến bay, người chờ thăm dò,
`RLock` tái nhập theo đường gọi thật, lỗi có kiểu `ProcessTableError`; test điều phối luồng có kiểm soát, idempotent, sở
hữu tiến trình, không deadlock; [B03-R3-range.md](decisions/B03-R3-range.md)); một lượt `aisef run` thật qua CLI thật trong
Linux guest (§0.4); danh tính nhị phân OCR (§0.5); phân loại phát hiện của các module probe (§0.7); đường dẫn chính xác và
nguồn gốc của ba tệp probe trong `site-packages` (§0.7).

### 0.2 Lỗi sản phẩm tìm thêm khi kiểm chứng (ngoài chín mutant; mỗi cái có test của yêu cầu thật, đỏ trước / xanh sau)

| Lỗi | Ở đâu | Tìm bằng | Hồ sơ |
|---|---|---|---|
| `/dev/pts`, `/dev/mqueue`, `/dev`, `/dev/shm`, `/proc` **của chính host** bị chấp nhận là "ghi được ngoài workspace thì được" | `confine._judge` | bwrap thật, 12 biến thể | B03-R3-conf |
| từ chối sai hiếm: super block được giải phóng ở cuối phiên bị một mount host không liên quan dùng lại trước lần đọc thứ hai | `confine._probe` | review | B03-R3-conf §13 |
| `--verify` in VERIFIED / delivery PASS cho journal có chuỗi hợp lệ nhưng story commit hai lần | `verify.verify` | WP usage | B03-R3-usage |
| hai finding id đọc giống nhau cho cùng một tên artifact ⇒ review story thứ hai bị từ chối mọi lần; tệp làm việc của finder giữ nguyên bí mật; bí mật là chữ số viết thành số JSON còn nguyên | `review_verify.preserve`, `Reviewer._ocr`, `redacted` | review detail | B03-R3-detail |
| `ps` in U+2028/U+2029 thô; `str.splitlines()` cắt hàng: raise, lệnh bị cắt âm thầm, hoặc tiến trình bịa ra | `process_range._ps_table` | review, range-fu | B03-R3-range §11 |
| tiến trình có tên không phải UTF-8 làm cả bảng raise (Linux) | `process_range._linux_table` | range-fu, trong guest | B03-R3-range §11 |
| **gốc chứng minh sở hữu của chính runner mutation** nhận một dòng lệnh giả làm hàng: tiến trình có trước ranh giới bị xếp loại *được báo hiệu* (chạy khô) | `cleanup_authority._read` | range-fu | B03-R3-AUTH |
| sự kiện trong luồng phiên chứa U+2028/U+2029/U+0085 bị cắt và bỏ âm thầm | `client.read_session`, `usage.session_tokens`, `confine` readers, `lineage.reconcile` | range-fu, WP client | B03-R3-CLIENT |
| **một try của probe không có exit status được đọc như đã chạy**: marker `@@aisef-confine rc N` dính vào dòng cuối của lệnh không kết thúc bằng xuống dòng; canary không status = *không có vấn đề*; hai dòng văn bản bị đọc là (status, text) | `confine._sections/_judge` | review độc lập của survivor `_judge` [100] (vòng 4) | B03-R4-REVIEW |
| `_Posix.abort` để `ProcessLookupError`/`PermissionError` thoát ra khi anchor kết thúc giữa `poll()` và `killpg` ⇒ lỗi khởi động bị thay bằng lỗi này, anchor không được reap | `process_range._Posix.abort` | review độc lập (vòng 4) | B03-R4-REVIEW |


### 0.3 Bản ghi mutation V2.1 (`closure-evidence/v2/v2.1/MUTATION.json`, `MUTATION-SUMMARY.json`)

| | số lượng |
|---|---|
| target (mỗi cái được tính đúng một lần) | **528** — 472 theo đợt 5 (`289885e`, toàn bộ 528 ở một snapshot), 43 theo đợt 6 (`a770fbb`), 1 theo đợt 7 (`853da4a`), 12 theo đợt 8 (`5df323a`) |
| mutant | **13,581** |
| **KILLED** (một FAIL tái hiện, có kiểm chứng đối chứng) | **13,388** |
| SURVIVED, có audit theo vị trí | **193** — **136 AUDITED** (khác biệt có thật, không người đọc nào dựa vào; nêu từng người đọc, từng ngoại lệ) + **57 EQUIVALENT** (chứng minh từ mã). **Không phải kill; báo riêng.** |
| SURVIVED, **chưa quyết** | **0**. Chín mutant mở của 2026-10-12 không còn trong danh sách vì mã chứa chúng đã bị thay theo quyết định (điều khoản `devpts`/`mqueue` của `_judge`, khoá `LANG` của `measure`, hàm `no_progress`, câu lệnh `sort_keys` của `detail`): **không** mutant nào trong số đó được tính là KILLED, và không mutant nào được chọn yêu cầu vì chuyển PASS (§0.1) |
| TIMEOUT / INFRA / NOT_RUN | **0 / 0 / 0** (hai TIMEOUT của đợt 5 ở `_Posix.abort` đã được giết bằng một test không cần tiến trình) |
| tiêu chí tái dùng | đóng băng, không đổi; mỗi kết quả giữ gắn commit/snapshot/runner/bộ kill/môi trường |

Lịch sử các lượt đo (bản ghi của từng chiến dịch giữ nguyên, byte cho byte, ở `mutation-workers/`): chiến dịch 2 (`5719f1f`,
466 target, 12,448 mutant, 58.9 giờ) → sửa runner (`c4c1720`) → chiến dịch 3 (`f860e57`, 199 target) → vòng 2 (42
mutant) → chiến dịch 4 (`b5c2457`, 28 target, 1,378 mutant) → **chiến dịch 5 (`289885e`, tất cả 528 target / 13,566
mutant ở một snapshot, 5 worker, 24.3 giờ: 13,361 KILLED, 203 SURVIVED, 2 TIMEOUT, 0 INFRA, 0 NOT_RUN)** → vòng 4:
review độc lập + kiểm lại 122 audit mang sang bằng 18 agent (hai bản mù mỗi lô) → **chiến dịch 6 (`a770fbb`, 56 target /
1,419 mutant, 55 phút: 1,393 KILLED, 26 SURVIVED, 0 TIMEOUT)** → hai agent kiểm 3 audit mới, một test mới và một test được
siết → **chiến dịch 7 (`853da4a`, 3 target / 448 mutant)** → lượt chạy suite đầy đủ ở `1043186` thấy hai lệnh gọi tiến
trình con thiếu `encoding="utf-8"` (quy tắc của chính suite, lỗi 99) trong hai tệp kill đã ghim → sửa đúng hai từ khoá,
T0 hai cặp, manifest rev 8 → **chiến dịch 8 (`5df323a`, 12 target / 680 mutant: 673 KILLED, 7 SURVIVED đều đã có audit, 0
TIMEOUT/INFRA/NOT_RUN; mỗi mutant có đúng lớp của lần đo trước)**. Chi tiết và căn cứ: `campaign-5/`, `campaign-6/`,
`campaign-7/`, `campaign-8/`, [decisions/B03-R4-REVIEW.md](decisions/B03-R4-REVIEW.md), [MUTATION-RUNNER-V2.md](MUTATION-RUNNER-V2.md) §19–§20.

**Căn cứ phụ thuộc của kết quả được giữ** (quy tắc của chủ dự án, mục 6: "phải có căn cứ phụ thuộc cụ thể; không nới quy
tắc để tránh chi phí đo"). 472 kết quả của đợt 5 đứng vững ở cây cuối vì: (1) delta của tệp đích, bộ kill, closure test,
bộ sinh mutant (luật của chính bản ghi); (2) read-set **đo** ở chính cây cuối (166 tệp kill, mỗi tệp chạy riêng với audit
hook): thư mục nào bị liệt kê thì tập con trực tiếp của nó không đổi (delta tính "mọi tổ tiên" nên cờ 1.542 tệp; đọc
chính xác thì 0); tám target mở `confine.py`/`process_range.py` bằng `import` của tiến trình con, mà câu lệnh mức module
của hai tệp không đổi; (3) `trace_paths.py` — dấu đặt ở đúng ba hàm đổi (`_sections`, `_judge`, `_Posix.abort`) trong cây
bản sao của runner: không tệp kill nào ngoài ba tệp do vòng này viết (`test_v21_r3_judge_not_run`, `test_v21_r3_range_abort`, `test_v21_r4_probe_record`) đi qua hành vi đã đổi, kể cả trong tiến trình con tự dựng `env=`
(mà `reach.py` không thấy); (4) `diff_confine_old_new.py`: hai bản `_judge` trả cùng kết quả trên 20.000 đầu vào mà mọi try
đều báo status. **Không** phủ: một mutant của module KHÁC tự tạo ra đúng đầu vào đó (không thể: đầu ra probe đến từ tiến
trình bubblewrap do test cấp); đây là lập luận, không phải số đo.

**Đợt 8 — vì sao phải đo lại 12 target dù thay đổi chỉ là một từ khoá.** Hai tệp kill (`test_v21_r3_conf_policy.py`,
`test_v21_r4_probe_record.py`) bị ghim bằng sha256 trong manifest và nằm trong closure của từng target đăng ký chúng; đổi
byte là đổi căn cứ của kết quả. Không lập luận "chỉ là tham số giải mã": 12 target (680 mutant, đều trong `confine.py`)
được đo lại ở snapshot mới — kết quả giống lần trước từng mutant một. Căn cứ cho 516 target còn lại: ba delta (từ
`289885e`, `a770fbb`, `853da4a`) ở đúng commit đo read-set + đọc chính xác dữ liệu từng tệp kill đọc; mã sản phẩm
(`aisef2/`) và runner giống đợt 7 từng byte (`campaign-8/SCOPE.json`, `code_moved_since_campaign_7_read_set`). Read-set
được đo ở commit có đủ các bản ghi phái sinh (ba tệp đó nằm trong `mutation.COPY`; một tệp đã xoá ở HEAD không thể được
xoá nghi ngờ bằng phép đo ở HEAD).

### 0.3b Bảng: đã làm / đã kiểm chứng / chưa kiểm chứng / bị chặn

| Hạng mục | Đã làm | Đã kiểm chứng (bằng gì) | Chưa kiểm chứng | Bị chặn / chờ |
|---|---|---|---|---|
| 9 mutant mở (B-03) | chính sách + sửa + test (§0.1) | mutation 528 target ở một snapshot (đợt 5), review độc lập, 18 agent kiểm audit | Windows (CI chưa chạy) | — |
| Bản ghi mutation | `MUTATION.json` + `-SUMMARY.json` + `--check` | §0.3 (cây `1d4f0156…`) | cây sau cửa sổ probe (§0.9): target đổi/mới chưa đo | đo lại một lần ở cuối cửa sổ |
| Cách ly Linux | chính sách nguồn gốc; locale C; `aisef run` thật trong guest | guest Linux (bwrap 0.12.0, kernel 7.0.12-linuxkit): 12 dòng lệnh; 92/92 kiểm tra e2e ×2 | một lượt có **mô hình thật**; thông báo dịch; kernel/bwrap khác | ngân sách B-09 |
| `ProcessRange.release()` | sửa + test điều phối luồng | mutation (23 target ở đợt 6) + test | — | — |
| Ranh giới `--verify` và `no_progress` | sửa | 89 journal + smoke 2.0.0: 0 từ chối sai | journal format 4 (chưa có) | — |
| Reproducer đầy đủ trong artifact | thiết kế + sửa | 12.000 finding đối kháng; thật | một lượt OCR với mô hình thật | ngân sách B-09 |
| Bản ghi phái sinh 2.1 | sinh đúng thứ tự trên cây cuối (§0.5b) | công cụ tự kiểm từng cái | cây sau cửa sổ probe (§0.9): chưa tái sinh | tái sinh một lần, theo thứ tự phụ thuộc, sau hiệu chuẩn (§0.9) |
| Suite đầy đủ | chạy trên commit đã định (§5) | hermetic, `env -i`, không có `opencode` | cây sau cửa sổ probe (§0.9, §5): chưa chạy; trong guest Linux mới 84/405 module | chạy trên commit đã định, sau hiệu chuẩn |
| Phát hiện module probe | phân loại PM-1…13; **sửa trên nhánh ứng viên** (§0.9) | reproducer đo được, kỹ sư thứ hai chạy lại; test đỏ trước / xanh sau của từng làn | hiệu chuẩn lại 19 hàng, mutation, suite đầy đủ cho cây đã đổi | hiệu chuẩn một lần ở cuối cửa sổ; quyết định mở: backlog V21-54 … V21-74 |
| OCR với mô hình thật; chiến dịch đối chứng (E2) | — | — | **chưa đo** | B-09 |
### 0.4 Lượt `aisef run` thật trong sandbox Linux (mô hình kịch bản; chứng minh **tích hợp có cách ly**, không chứng minh hiệu quả với mô hình thật)

Tài liệu và bằng chứng: [decisions/B03-R3-E2E.md](decisions/B03-R3-E2E.md), `closure-evidence/v2/v2.1/e2e-linux/`. Bảng dưới đây
là của lượt đó (2026-10-13), chạy trên `9f336fb` (`aisef2/` `427afeec…`). Lượt chạy lại trên cây cuối `1d4f0156…` (commit
`2d01fe4`, 2026-10-15; hai tệp khác `427afeec…`: `confine._sections`/`_judge` và `process_range._Posix.abort`) nằm ở
`closure-evidence/v2/v2.1/e2e-linux-final/`: X1 và hardened đạt, cùng kịch bản và kiểm tra, mọi kết quả giống lượt đầu.

| Mục | Giá trị |
|---|---|
| máy chủ | macOS 26.5.2 (Darwin 25.5.0, arm64); Docker Desktop 4.91.0, engine 29.8.0 |
| guest | Linux 7.0.12-linuxkit aarch64, Debian 13.7, cgroup v2, Python 3.14.8, bubblewrap 0.12.0, git 2.47.3; image `aisef-sandbox-measure` cục bộ (không kéo, không dựng, không xoá) |
| cấu hình container | `--rm --init --network none --user 1000:1000 --cap-drop ALL --pids-limit 512 --memory 1g --cpus 2`, cây mã bind chỉ đọc; profile **X1** thêm `seccomp=unconfined` + `systempaths=unconfined` (cần để bwrap lồng chạy), profile **hardened** (không nới) kiểm chứng việc **từ chối** |
| đường mã | `python3 -m aisef` → `aisef2/app/cli.py::run` → `run.execute` → `confine.measure` (trước request provider đầu tiên) → preflight → `adapters` → `client.session` → `confine.wrap` → bwrap; `--verify --expect-anchor` |
| mô hình / provider | client là một script Python đặt tên `opencode` trong PATH của guest (không phải client thật); provider là điểm cuối loopback chỉ trả lời preflight; **không có phí, không có request nào từ phiên** |
| kết quả | 11 kịch bản, 88/88 kiểm tra (X1) + 4/4 (hardened), hai lần chạy giống nhau (0 khác biệt về kiểm tra và dữ kiện) |
| đã chứng minh | đường thành công (mỗi phiên là PID 1 = bwrap với đúng `confine.argv`; verify VERIFIED với anchor); ghi ngoài phạm vi bị từ chối (EROFS) hoặc rơi vào tmpfs của sandbox và vắng trên host, mỗi từ chối có lượt đối chứng không cách ly thành công; tiến trình con (nền, bỏ qua SIGINT/SIGTERM, `setsid`) chết cùng phiên cả khi hết giờ; bằng chứng/anchor: đúng anchor VERIFIED, sai anchor / sửa một chữ số / viết lại nhất quán REFUTED (trên bản sao) |
| **chưa** chứng minh | hiệu quả hay chất lượng với mô hình thật; mạng của phiên (`network: host` không cách ly: container không có đường ra); bất kỳ thứ gì ngoài Linux guest này; Windows |
| tài nguyên của chiến dịch | `goe-postgres-1` và `goe-valkey-1` được liệt kê trước, không đụng, vẫn `Up (healthy)` sau; không dừng, không xoá, không prune |

Hai chỗ bằng chứng khác với chỉ thị: (1) bản ghi phiên không mang dòng lệnh bwrap (`confinement` chỉ là chuỗi
`bwrap network=host[ workspace=read-only]`; `RUN.json.confinement.argv` là của phép *đo*), nên việc phiên chạy trong bwrap
được chứng minh *từ bên trong* (PID 1 và argv của nó so với `confine.argv(...)` tính lại); (2) hai trong sáu đích của S2
không phân biệt được trong cấu hình S1 (cây gắn chỉ đọc, site-packages thuộc root), nên S2 chạy từ bản sao kernel ghi
được với venv ghi được, kèm lượt đối chứng không cách ly.

### 0.5 Nhị phân Open Code Review, ba tệp probe trong `site-packages`, hiện tượng log OpenCode Desktop

* **OCR**: sha256 `bf38abf3…04af7` **khớp pin**; `version` in `open-code-review v1.12.12 (182898c) darwin/arm64`. Ba lớp
  bằng chứng, không gộp (`validation/v21/ocr/BUILD-RECIPE.md`): (a) **tự khai** — dòng `version`, do người dựng đặt;
  (b) **metadata nhúng** — `go1.26.5`, `-trimpath=true`, `vcs.revision` = commit ghim, `vcs.modified=false`; (c) **dựng
  lại được** — `NOT_PERFORMED` (không có nguồn upstream, module cache 0 tệp, không mạng, `-ldflags` của bản dựng gốc chưa
  biết). Nhãn "dựng từ nguồn (`-trimpath`)" từng ghi ở đây là lời của dự án: phù hợp (a) và (b), chưa được chứng minh.
  Chưa so với artifact phát hành upstream (không có pin nào để so). Chỉ nhị phân darwin/arm64 của máy này; guest không có
  OCR (OCR bị từ chối cùng cách ly). Từ cửa sổ probe (§0.9) cổng hỏi `version` của binary **trước mọi lệnh review**. Không
  có lượt OCR với mô hình thật. `closure-evidence/v2/v2.1/round-3/OCR-IDENTITY-2026-10-13.json`.
* **Ba tệp probe** (rỗng, 0 byte, `nghinh:admin`, sinh 2026-10-07 17:28:29 / 17:33:53 / 19:39:42; không phải tệp của
  gói nào; sự cố `closure-evidence/v2/v2.1/incidents/2026-10-07-site-packages-probe-files`, trạng thái **mở**; **không
  xoá**: chưa có duyệt cho đúng ba đường dẫn này):
  `/opt/homebrew/lib/python3.14/site-packages/.aisef-confine-probe-b0d66e9a5990b6d3`,
  `/opt/homebrew/lib/python3.14/site-packages/.aisef-confine-probe-1162885dab73b67c`,
  `/opt/homebrew/lib/python3.14/site-packages/.aisef-confine-probe-924d088566af3a41`. Nguồn gốc (bằng chứng trong thư mục
  sự cố): test của `confine.measure` chạy trên macOS với bwrap giả chạy probe **không cách ly**, nên thử "ghi vào site của
  interpreter" thành công vào site-packages thật; bản `_probe` lúc đó tự xoá tệp, nhưng các lượt chạy tay-mutant bị driver
  giết ở hạn 150 s (hai lượt TIMEOUT ở 17:28–17:34 và một lượt ở 19:39; log của driver nêu nonce của tệp thứ ba) bỏ qua
  dòng xoá. Từ `3c5f136` sản phẩm **không bao giờ xoá** tệp như vậy (nêu tên và từ chối lượt); từ `373a723` child của test
  trỏ `sysconfig`/`__file__` vào thư mục tạm.
* **Thay đổi của kho OpenCode** (`~/.local/share/opencode`) trong chiến dịch 5: tiến trình OpenCode Desktop `a7141900` thoát
  lúc 11:01:54Z (dòng log của chính nó, mtime `opencode.db` 133 ms sau, `-wal`/`-shm` được checkpoint đi). Không phải kết
  quả của chiến dịch (không worker nào khởi động `opencode`). **Không biết** ai/cái gì đóng tiến trình đó.
  `campaign-5/results/STORE-ATTRIBUTION.md`.


### 0.5b Bản ghi phái sinh 2.1 (đúng thứ tự phụ thuộc, sinh trên cây cuối đã commit)

Thứ tự: `P5 proposal` → `P5 falsifiability` → `PLAN-V2.2 correction 1` → `P2 static admission` → **`MUTATION.json` +
`-SUMMARY.json`** → `Q0-CHECKER-CALIBRATION` (checker `mutation` chạy trên bản ghi thật) → `C2-P5-ACCEPTANCE-REVERIFICATION`
→ `K-NOWORK-001-REHEARSAL` → `Q5-KERNEL-COMPARISON` → `CONFORMANCE-RULING`. Mỗi bản ghi viết một lần, tự kiểm bằng công cụ
sinh ra nó; không bản ghi nào được viết để làm xanh một test. Kết quả từng bước và suite nằm trong
`closure-evidence/v2/v2.1/round-4/` (ghi **sau** khi bản ghi mutation được viết: một commit không chứa được kết quả
của chính nó) và trong báo cáo gửi chủ dự án.

### 0.6 Trạng thái từng cải tiến học từ OpenResearch, open-code-review, MiMo-Code (tách: đã tích hợp / đã kiểm chứng / lợi ích chưa đo)

Từng hàng nguồn → commit → test (88 hàng, kể cả hàng bị từ chối): [TRACEABILITY.md](TRACEABILITY.md). Dưới đây là phần cô
đọng theo từng cải tiến. "Kiểm chứng" nói **bằng gì**; chưa cải tiến nào có số đo lợi ích với mô hình thật (ba lượt canary, §0.10,
chỉ chạy đường chạy trên workload tầm thường), nên cột cuối là "chưa đo" (trừ chi phí: một ước tính).

| Nguồn | Cải tiến | Tích hợp vào `aisef run` | Kiểm chứng (bằng gì, mức) | Lợi ích với mô hình thật |
|---|---|---|---|---|
| open-code-review | bộ chuyển OCR có phiên bản; finding chỉ chặn khi AISEF tái hiện **và** contract đã duyệt neo kỳ vọng; thiếu manifest ⇒ INDETERMINATE | có (`review.finder: "ocr"`, **mặc định tắt**; từ chối khi dùng chung cách ly) | mutation; `test_v21_review*`; CLI thật + nhị phân v1.12.12 (sha256 khớp pin) với mô hình kịch bản (M4); bằng chứng cho các lỗi tìm được ở vòng 3 (artifact reproducer, tên artifact, bí mật) | **chưa đo**: chất lượng/độ phủ finding với mô hình thật; 4/5 lỗi lịch sử neo được, lỗi thứ năm vẫn lọt theo luật neo |
| open-code-review + MiMo-Code | nối tiếp từ journal (`bundle continue`, `run --parent`), claim theo thế hệ, đối soát git | có | mutation; SIGKILL thật ở 13 điểm; CLI thật (M4); bắt được một lỗi thật (`b72e51e`) | **chưa đo**; resume tại chỗ **không làm** (cần format journal mới) |
| open-code-review + MiMo-Code | sổ chi phí, "không biết ≠ 0", `no_progress` | có; `no_progress` **chỉ báo cáo**, không chặn | mutation; `test_v21_continue_usage`; vòng 3: miền = mọi journal projection chấp nhận, ranh giới `--verify` có tên (M3–M4) | ước tính ≈ 0,599 USD cho ba lượt canary (§0.10; telemetry × bảng giá công bố, không phải hóa đơn); giá thật: **chưa đối chiếu** |
| MiMo-Code | gói ngữ cảnh do controller dựng cho lượt thử lại — **không** phải checkpoint (P-5.3a vẫn **MỞ**) | có, trong một run | mutation; đo trên 16 lượt thử lại đã ghi; CLI thật (M4) | **chưa đo**: hiệu quả sửa lỗi (cần lượt trả tiền, B-09) |
| OpenSandbox | cách ly Linux tối thiểu (bwrap), opt-in | opt-in; **một lượt `aisef run` thật có cách ly đã chạy trong Linux guest** (mô hình kịch bản, §0.4) | mutation + guest (M4) + e2e (M4) | **chưa đo**: ranh giới với phiên của mô hình thật; mạng của phiên không cách ly |
| OpenResearch | harness thí nghiệm đối chứng: manifest niêm phong, cặp một biến, evaluator ẩn | **không** thuộc đường sản phẩm (công cụ riêng) | `test_v21_experiment` (replay offline, M3) | chiến dịch đối chứng (E2) **chưa chạy**: ngân sách B-09 và sandbox cho evaluator ẩn |

Quy tắc đọc: mutation **không** thay kiểm chứng tích hợp; kiểm chứng tích hợp bằng mô hình kịch bản **không** phải số đo
với mô hình thật. Mỗi hàng ở trên có trạng thái riêng; không gộp OCR, gói ngữ cảnh, cách ly Linux và harness đối chứng.

### 0.7 Phát hiện của các module probe (phân loại 2026-10-14; **đã sửa trên nhánh ứng viên ở cửa sổ probe 2026-10-15**, §0.9 — sửa probe = hiệu chuẩn lại, một cửa sổ trả một lần; hiệu chuẩn chưa làm)

Hồ sơ đầy đủ, mỗi mục có reproducer đo được và được một kỹ sư thứ hai chạy lại từ cây sạch:
[decisions/B03-R3-PROBE-MODULE-FINDINGS.md](decisions/B03-R3-PROBE-MODULE-FINDINGS.md). Phân loại theo quy ước của chủ dự
án (lỗi cần sửa / giới hạn đã biết / quyết định của chủ dự án):

| Loại | Mục | Tóm tắt |
|---|---|---|
| **Lỗi cần sửa** | PM-1 | chủ thể dưới thư mục không có `__init__.py` không bao giờ được định vị ⇒ UNRUNNABLE (trước khi tách B1 là REFUTED cho cùng cấu trúc) |
| | PM-2 | bước `fault` đứng trước bước `subprocess` được nhận nhưng không bao giờ phát tới tiến trình con (`fired: false`) và kịch bản bị phán trên lượt không lỗi ⇒ một sản phẩm hỏng dưới lỗi vẫn SATISFIED |
| | PM-3, PM-4 | `ast.parse` raise `RecursionError`/`MemoryError` trên tệp hợp lệ lồng sâu thoát khỏi `observe`/`run_probe`; chi tiết `x.py:None` |
| | PM-6 (thấp) | `open(harness.log)` không bọc và NUL trong argv được nhận |
| | PM-11 | tệp UTF-8 có BOM bị coi là `unparsable` dù CPython biên dịch được ⇒ một giới hạn của parser bị REFUTED và tính cho developer; `grep_count` bỏ sót khớp neo `^` ở dòng đầu |
| **Quyết định của chủ dự án** | PM-5 | câu trả lời tiến trình chủ thể chuyển tiếp (mã thoát, giá trị) là lời khai của chính chủ thể: mã ứng viên đối kháng làm một sản phẩm hỏng thành SATISFIED (backlog V21-26 từng ghi "không có PASS giả"; đã đo khác và được đính chính ở cửa sổ này) |
| | PM-7 | `EXECUTION_DIGEST` không phủ `process_range.py`, `range_anchor.py`, `product/outcome.py`: sửa chúng giữ nguyên mọi hàng hiệu chuẩn "hợp lệ" — **đã có ví dụ sống** (`process_range.py` bị sửa ở 5 commit của vòng 3–4 — `6296315`, `0917ff7`, `5cd5cdd`, `9c7b080`, `257a233` — mà 19/19 hàng vẫn hợp lệ) |
| | PM-8, PM-9, PM-13 | `Observation.detail` bị bỏ cho OBSERVED (đã ghi PROBE-DIAGNOSTIC-GAP-001); đếm 0 trên tập rỗng là SATISFIED; regex lồng lượng từ trong tiến trình kernel làm treo lượt |
| **Giới hạn đã biết** | PM-10, PM-12 | chẩn đoán thẩm mỹ; `file_artifact` quyết định cửa sổ thời gian sau khi đọc (REFUTED trên một lần đọc hoàn tất khi máy tải cao) |

Cửa sổ đã mở trên nhánh ứng viên (§0.9): PM-1, PM-2, PM-3/4, PM-6, PM-11 sửa chung; PM-7 trong cùng lần đổi digest;
PM-8, PM-9, PM-13 theo quyết định của chủ dự án ngày 2026-10-15
(`closure-evidence/v2/v2.1/round-5/OWNER-DECISIONS-2026-10-15.md` §B); PM-5 là một mô tả giới hạn (§6), không phải sửa.
**Còn lại**: hiệu chuẩn lại 19 hàng + Q-checker liên quan, đo mutation, suite đầy đủ, và các quyết định mở của cửa sổ
(backlog V21-54 … V21-74).

### 0.8 Phát hành, hiệu quả với mô hình thật, và những gì chưa được duyệt

* **Không** push, tag, publish, deploy; không phiên kỹ thuật nào gọi provider trả tiền (ba lượt canary: chủ dự án tự
  chạy, §0.10); Docker Desktop và `goe-postgres-1`, `goe-valkey-1` không bị dừng hay đụng tới (chỉ `docker run --rm` của
  image đo cục bộ, qua một script).
* **Sẵn sàng phát hành 2.1: chưa.** CI Windows/Linux chưa chạy (cần push); B-02 (2.0.1), B-04 (contract S-10-a của
  LedgerLock), B-08 (K-NOWORK-001), B-10 (nơi đăng tài liệu) **chưa được duyệt** và không được tự động coi là đã duyệt;
  B-09: phần canary đã chạy theo chat 2026-10-15, chiến dịch 140 USD chưa duyệt (§0.10).
* **Hiệu quả với mô hình thật: chưa đo.** Bằng chứng tích hợp dùng mô hình kịch bản; ba lượt canary dùng mô hình thật trên
  workload tầm thường (§0.10) cho thấy đường chạy, không phải hiệu quả. Số đo hiệu quả cần lượt trả tiền có đối chứng
  (B-09).
* **Ba tệp probe trong `site-packages`**: đường dẫn chính xác và nguồn gốc ở §0.5; việc xoá cần duyệt đúng ba đường dẫn.

### 0.9 Cửa sổ probe 2026-10-15 — nhánh ứng viên `v2.1/probe-window` (`2d01fe4` → `f69124c`)

Cây `aisef2/` đổi từ `1d4f0156…` (cây của bản ghi mutation §0.3, của suite `45554e0`, của e2e §0.4 — lượt `e2e-linux-final/`; lượt `e2e-linux/` đầu tiên chạy trên `427afeec…` — và của canary §0.10)
sang `168ad7d4…`. Nguồn thay đổi: các mục lỗi PM-1, 2, 3, 4, 6, 11 và RV-1, RV-2 (§0.7); các quyết định của chủ dự án
ngày 2026-10-15 cho PM-5, PM-7, PM-8, PM-9, PM-13 và họ lineage
(`closure-evidence/v2/v2.1/round-5/OWNER-DECISIONS-2026-10-15.md` §B); cổng danh tính OCR; công cụ chạy suite trong guest
Linux. Hành vi người dùng thấy, từng mục, với tên trạng thái trong mã: [USAGE-2.1.md](USAGE-2.1.md) §5 và §8.

| Mục | Đã làm trên nhánh ứng viên | Commit | Test (đỏ trên mã trước cửa sổ, xanh sau) |
|---|---|---|---|
| PM-1 | module dưới thư mục không có `__init__.py` được định vị theo tên từng thành phần (trước: `UNRUNNABLE`) | `9d62ba6` | `test_v21_r3_probe_namespace` |
| PM-2 | bước `fault` trước bước `subprocess` bị từ chối ở admission (`INVALID_SPEC`); `FAULTED = (call, expect_raises)` | `7724789` | `test_v21_kills3_T19b`, `test_probe_process_effect_units` |
| PM-3, PM-4 | giới hạn parser (`RecursionError`/`MemoryError`) là `UNRUNNABLE` có kiểu, không phải exception; dòng không nêu ghi `?` | `fa15e88`, `c72cc9f` | `test_v21_fa_parser_limits`, `test_v21_python_imports` |
| PM-6 | lỗi mở `harness.log` là `HARNESS_FAILED` có kiểu; NUL trong argv `subprocess` của `process_effect` không có lớp | `6dc9821` | `test_v21_pm6_host_faults` |
| PM-7 | `EXECUTION_DIGEST` của bốn probe phủ `product/contract.py`, `product/outcome.py`, `runtime/process_range.py`, `runtime/range_anchor.py` — đo; là danh tính, không phải quyền, và không phát hiện hồi quy | `1c7108a`, `fa15e88`, `c72cc9f`, `e34e6dd` | `test_v21_probe_sources`, `test_v21_pm7_file_artifact_sources` |
| PM-9 | một lựa chọn không có tệp nào là chủ thể vắng; `CAPABILITY_VERSION` của `file_artifact` 2 → 3 | `06f8018` | `test_v21_fa_empty_selection` |
| PM-11 | BOM UTF-8 đầu tệp không phải nội dung; BOM + cookie khác UTF-8 là syntax error như CPython | `fa15e88`, `c72cc9f` | `test_v21_python_imports` |
| PM-13 | vòng khớp regex của `grep_count` chạy trong worker dưới `timeouts_s.probe`; hết hạn là `UNRUNNABLE`, không bao giờ `REFUTED` | `06f8018`, `2063ccb` | `test_v21_fa_grep_worker`, `test_v21_fa_grep_runpath` |
| RV-1, RV-2, họ RV-1 | reproducer lồng quá 63 tầng là một lý do có kiểu; INDETERMINATE không bị nói là "không tái hiện"; dữ liệu mô hình/ứng viên viết là một verdict hay một lý do, không phải exception | `72db8ca`, `65c6725`, `be12463`, `c6b52d9` | `test_v21_r5_review_deep_input`, `test_v21_r5_review_indeterminate`, `test_v21_r5_probe_model_data` |
| Cổng OCR | hỏi `version` trước mọi lệnh review; tự khai khác bằng chứng dựng; công cụ + công thức | `eca3493`, `e3ec434`, `43bb58d` | `test_v21_ocr_gate`, `test_v21_ocr_declared` |
| PM-8 | `<out>/probe-observations/` cho người vận hành; không thẩm quyền quyết định; che bí mật của run; giới hạn cùng user | `07f27d3`, `6c6a6b1` | `test_v21_pm8_diagnostics`, `test_v21_pm8_diagnostics_run` |
| Lineage | `UNREAD`, mã `EVIDENCE_*`, `--expect-anchor`, `continue` hợp lệ như `--verify`, chi phí unknown cho journal không đọc được | `042a245`, `1501d17`, `4d245f4`, `d3b6cd9` | `test_v21_pw_lineage_continue`, `…_unread`, `…_spend` |
| Công cụ suite trong guest | `validation/v21/sandbox/linux_suite.sh`, `linux_suite_guest.py` (suite hoặc tập con, trong container) | `ff6be69`, `2155228` | `test_v21_linux_suite_guest` |
| PM-5 | mô tả một giới hạn: docstring và `WEAKEST_PATH` của ba probe không còn nói chủ thể "builds no fact" (không đổi hành vi); §6 | `f69124c` | — (giữ cụm "isolation, not a sandbox" mà test ghim) |

**Trạng thái bằng chứng: đã làm trên nhánh ứng viên, bằng chứng đo chưa có.** Mỗi thay đổi hành vi có test đỏ trước, xanh
sau, do làn của nó chạy trên cây của làn. Tại `f69124c` chưa có (kiểm: `closure-evidence/v2/v2.1/round-5/` chỉ có bảng
quyết định):

* **hiệu chuẩn**: `aisef2/app/calibrations.py` còn 19 hàng ở `EXECUTION_DIGEST` cũ (cli_invocation 5, process_effect 3,
  python_callable_v2 7, file_artifact 4); `aisef bundle lint` trên `calc-1-story` báo `NOT_READY` ở kiểm tra
  `9. probe_calibration` (đo trên `f69124c`, USAGE-2.1 §1) cho tới một lần `release_calibration.py --write`;
* **mutation**: target mới và target đổi thân (đăng ký đề nghị của từng làn; `validation/v2/mutation.py` chưa sửa);
* **suite đầy đủ** và các bản ghi phái sinh ràng buộc cây (P5-PLAN-V2.2-PROPOSAL, P5-FALSIFIABILITY,
  C2-P5-ACCEPTANCE-REVERIFICATION, PLAN-V2.2-CORRECTION-1, Q5-KERNEL-COMPARISON, CONFORMANCE-RULING, bản ghi
  C2-ORCHESTRATION, bản ghi K-NOWORK-001, bảng execution order): đỏ có chủ đích cho tới khi tái sinh một lần theo thứ tự
  phụ thuộc — kiểm cuối từng làn ghi các test này xanh ở nền;
* e2e trong guest Linux, CI Windows/Linux, mô hình thật.

Mọi bằng chứng gắn cây `1d4f0156…` (mutation 528 target, suite `45554e0`, e2e §0.4 lượt `e2e-linux-final/`, kernel của canary §0.10) mô tả cây
trước cửa sổ, không phải cây này. Các quyết định mở của cửa sổ là các hàng V21-54 … V21-74 của
[V2.1-BACKLOG.md](../v2/V2.1-BACKLOG.md); tài liệu này không quyết thay chủ dự án.

### 0.10 Canary B-09 với mô hình thật (2026-10-15; `closure-evidence/v2/v2.1/canary/`)

Route `9router/ds/deepseek-v4-pro`, client `opencode` 1.18.31, macOS không cách ly, cây `aisef2/` `1d4f0156…`, CLI
`python3 -m aisef`. Chủ dự án tự chạy ba script trong terminal của mình (05:52–05:59 +07).

| Bậc | Workload | Kết quả | `usage.cost.value` (USD, **ước tính**) |
|---|---|---|---|
| 1 | preflight thật, dừng ngay sau preflight | ATTESTED (`served_model` `deepseek-v4-pro`); 4 request; dừng theo ngân sách (`max_provider_requests: 4 of 4`) ⇒ `delivery_verdict` `NOT_REACHED` — điểm dừng đúng thiết kế, không phải lỗi sản phẩm | 0,008423 |
| 2 | `calc-1-story` (1 story, contract `python_callable` BC-ADD), review advisory | PASS, S1 `COMMIT`, `--verify` VERIFIED (68 sự kiện); reviewer 5 bước, `findings: []` | 0,159152 |
| 2b | `calc-3-stories`, `review.fix-loop` (`finder: model`) | PASS, S1–S3 `COMMIT`, 5/5 nghĩa vụ SATISFIED, VERIFIED (212 sự kiện); 3 reviewer, `findings: []` — vòng sửa **không bao giờ kích hoạt** | 0,431394 |
| | | tổng | **0,598969** (≈ 0,599) |

* **Là ước tính, không phải hóa đơn.** Mỗi số là telemetry token do client báo (`unaccounted: []`) nhân bảng giá peak công
  bố của DeepSeek (nguồn và ngày nằm trong từng `settings-*.json`) — một chặn trên cho một route do 9router phục vụ, giá của
  nó không biết ở đây. Chưa đối chiếu hóa đơn hay dashboard của provider.
* **Thẩm quyền: đúng những gì hồ sơ ghi** (`canary/APPROVAL-TRACE.md`). Chủ dự án, chat 2026-10-14T22:23:49Z (05:23:49 +07
  ngày 15): "Đồng ý chạy model thật" — trả lời một đề xuất canary bậc 1–2, trần 5 USD; con số 5 USD là của đề xuất (chủ dự
  án không nhắc lại). 22:57:49Z: "Tôi uỷ quyền cho bạn toàn quyền chạy các lệnh cần thiết" — không nêu trần hay lượt trả
  tiền nào. `RELEASE-DECISIONS.json` không có mục B-09; hồ sơ B-09 vẫn ghi "ĐỀ XUẤT, CHƯA DUYỆT" và không bị sửa. Bậc 2b
  rộng hơn chữ của hồ sơ ("một lượt calc 1 story"), trong trần 5 USD, do chủ dự án tự chạy.
* **Phần trần còn lại không phải một phép chạy.** 5 − 0,599 ≈ 4,40 USD không cấp phép thí nghiệm nào thêm: không lượt trả
  tiền nào được phép ngoài bậc 1, 2, 2b; lượt kế cần chủ dự án duyệt tường minh. Chiến dịch 140 USD: chưa quyết.
* **Preflight là 4 request** (3 chat probe + 1 listing), không phải 3 như hồ sơ B-09 viết; bậc 1 được đặt trần 4. (Hồ sơ
  `docs/v2.1/decisions/B-09-CANARY-THEN-CAMPAIGN.md` và `EXPERIMENT-PLAN.md` chưa sửa: ngoài phạm vi tài liệu này. Sau
  canary, các câu sau **không còn đúng**: `B-09-CANARY-THEN-CAMPAIGN.md:3` "Chưa có lượt chạy trả tiền nào", dòng 14 và 21
  (preflight 3 request; `budget.provider_requests = 3`) và `EXPERIMENT-PLAN.md:3` "Không lượt chạy trả tiền nào đã được
  thực hiện". `docs/v2.1/TRACEABILITY.md:491` và `docs/v2.1/research/TRACEABILITY.json:1163` ghim bằng kiểm cơ học câu "ĐỀ XUẤT, CHƯA DUYỆT" của
  hồ sơ B-09 (mặc định đọc ở commit đầu của bảng, `c9c736f`; `--at HEAD` đọc ở cây hiện tại): đổi câu đó làm kiểm `--at HEAD`
  đỏ cho tới khi bảng được cập nhật.)
* **Cho thấy:** đường cài → seal → approve → lint → `run --check` → `run` → `--verify` đi hết với mô hình thật, client thật
  và preflight thật, trên workload tầm thường (≈ 0,14 USD và ≈ 70 s mỗi story). **Không cho thấy:** vòng sửa, một REFUTED
  thật, `--parent` sau lỗi, OCR, cách ly Linux với mô hình thật, hiệu quả so với agent trực tiếp, workload cỡ LedgerLock.
* **Phát hiện C-1:** repo giao có `__pycache__/*.pyc` trong `main` (backlog V21-39).

## 1. HEAD và trạng thái từng nhánh

| Nhánh | HEAD | Trạng thái |
|---|---|---|
| `v2.1/foundation` | xem `git log -1` (commit chứa báo cáo này; mã cuối `534435f`: `confine.py`, `process_range.py`, `mutation.py` (dữ liệu), tệp kill và `trace_paths.py` đổi sau `b72e51e`) | local, chưa push. Gồm hai nhánh chủ đề đã merge: `v21/review` (`181d68e`), `v21/continue` (`872e83c`) |
| `v2.1/probe-window` | `f69124c` (`aisef2/` `168ad7d4…`) | local, chưa push, chưa merge; nền `2d01fe4`; ứng viên của cửa sổ probe 2026-10-15 (§0.9) |
| `v21p/context` | xem `git log -1` | local, chưa push, chưa merge: D4 ([CONTEXT-PACK.md](CONTEXT-PACK.md)). Mang thay đổi mã `f15026b`, `80f4437`, `1899bb0`, `7797061` trong `aisef2/app/` (`feedback.py`, `adapters.py`) — sau `b72e51e`; cần mutation và tái thẩm định ngoài snapshot đang đo |
| `release/v2.0.1-prep` | `f006d3d` | local, chưa push; bản vá 2.0.1 chuẩn bị, **chưa đủ điều kiện phát hành** (§5) |
| `master`, `docs/v2` | `610a593` | không đổi trong phiên này (2.0.0 + tài liệu) |
| `v21/confine`, `v21/decisions`, `v21/evidence` | `633b6a7` | trống (không commit nào), có thể xoá |

Checkout chính (`docs/v2`) có các tệp chưa commit trong `closure-evidence/v2/cycle2/` và
`validation/qualification/c2_closure_audit.py` từ một phiên trước — phiên này không động tới.

## 2. Bảng mức hoàn thành

Mức: **M1** đã triển khai module · **M2** đã tích hợp vào đường chạy sản phẩm (`aisef run` / `aisef bundle`, cùng một
đường quyết định `_attempt`) · **M3** đã kiểm chứng offline (test; developer và provider giả) · **M4** đã kiểm chứng bằng
công cụ thật (CLI `aisef` thật, nhị phân Open Code Review thật, git thật, SIGKILL thật — **mô hình vẫn là kịch bản**) ·
**M5** đã kiểm chứng live (provider thật) · **M6** chưa làm hoặc thực sự bị chặn. Không hàng nào của bảng này được ghi ở M5:
ba lượt canary (§0.10) chạy đường seal → approve → lint → run → `--verify` với mô hình thật, client thật và preflight thật
trên workload tầm thường, và chưa được tách thành mức đạt từng hàng (vòng sửa, OCR, `--parent` sau lỗi, cách ly Linux với
mô hình thật: chưa). "Mức đạt" là mức
cao nhất có bằng chứng; mục ở M3/M4 đã qua M1–M2, trừ E1 và A9–A10 (công cụ riêng, không thuộc `aisef run`).

| # | Hạng mục | Mức đạt | Bằng chứng | Còn thiếu |
|---|---|---|---|---|
| A1 | `.pth` của venv test không chạy trong probe | M3 | `test_v21_identity.PthChannel` (trên 2.0 nó chạy) | không có ranh giới OS (§3) |
| A2 | `--verify` dựng lại mọi trường nâng verdict; anchor | **M4** | `test_v21_verify`; CLI thật: `--verify --expect-anchor` VERIFIED (§4) | nơi giữ anchor tin cậy: của người vận hành (§4.3) |
| A3–A5 | input sai kiểu, endpoint loopback, `--check` clone như lượt chạy | M4 (A5), M3 (A3, A4) | `test_v21_inputs`, `RepositoryRefusal`; CLI thật: `--check` ready | — |
| A6–A7 | preflight không theo redirect; luồng phiên bị che dù ngắt | M3 | `test_v21_transport` | preflight thật trong §4 chỉ tới loopback, không có redirect |
| A8 | `git diff` lỗi ⇒ RESOURCE_ACQUISITION_FAILED | M3 | `test_v21_orchestration.DiffFailure` | — |
| A9–A10 | công cụ phát hành theo phiên bản; metadata 2.x; LICENSE | M4 (build + `packaging_check` local) | `test_v21_release_lane` | CI, staging, RC: **M6** (chủ dự án) |
| A11 | bản vá 2.0.1 | M3 | suite trên `f006d3d` (§5) | test đỏ so bản ghi; CI/RC/Q0–Q5/tag: **M6** |
| B1 | PRESERVE của story đã commit chứng minh ở candidate | M3 | `PreserveAtCandidate`, ORCH_9 | — |
| B3 | lớp `python_imports` | M3 | `test_v21_python_imports` | contract S-10-a sửa: **M6** (B-04) |
| B4–B5 | `aisef bundle init/seal/approve/lint/…`, độ phủ mệnh đề | **M4** | `test_v21_bundle_tools`; CLI thật: seal → approve ×7 → lint READY | — |
| B6 | ba danh tính | M3 | `test_v21_identity.ThreeIdentities` | phê chuẩn V2-007: **M6** (B-01) |
| C1 | finding chỉ chặn khi AISEF tái hiện **và** contract đã duyệt neo kỳ vọng | **M4** | `test_v21_review`, `test_v21_review_chain`; CLI thật: OCR tìm finding ⇒ tái hiện ⇒ ANCHORED ⇒ chặn ⇒ sửa ⇒ review lại sạch ⇒ COMMIT | chất lượng finding của mô hình thật: **M6** (B-06, ngân sách) |
| C2 | OCR v1.12.12 nối vào `aisef run` (`review.finder: "ocr"`) | **M4** | nhị phân thật: preview, khoảng rỗng, review đầy đủ với mô hình kịch bản (`RealBinary` ×3, §4.1) | OCR với mô hình thật: **M6** |
| C3 | vòng sửa có biên, có ngân sách | M4 | `FixLoop`; CLI thật: hai lượt | — |
| D1 | nối tiếp lượt chạy (`bundle continue`, `run --parent`), claim theo thế hệ, đối soát với git | **M4** | `test_v21_continue_integrity` (SIGKILL ở 13 điểm đồng bộ + hai run cùng lúc); CLI thật: §4.2 — bắt được một lỗi (`b72e51e`) | resume tại chỗ: **M6** (không làm: cần format journal mới) |
| D2 | usage/chi phí: không biết ≠ 0; chi phí chưa đối soát chặn phiên trả tiền | **M4** | `test_v21_continue_usage`; CLI thật: `--parent` bị từ chối, `--accept-unaccounted` ghi lại | giá thật: **M6** |
| D3 | `no_progress` (chỉ báo cáo) | M3 | `test_v21_continue_usage.Usage` | — |
| D4 | gói ngữ cảnh do controller dựng cho lượt thử lại ([CONTEXT-PACK.md](CONTEXT-PACK.md)) | **M4** | cần: đo trên 16 lượt thử lại đã ghi (`validation/v21/context_gap.py`); `test_v21_context_pack`; CLI thật tại `7797061`: prompt developer của run1 tính lại từ journal trùng `prompt_sha256`, lượt 2 nhận gói, seq trích đọc lại đúng, journal không chứa gói (bước read-back của `run.sh`, `evidence/cli-integration-7797061.out`) | hiệu quả với mô hình thật: **M6** (lượt chạy trả tiền); nối tiếp: chưa làm (chưa có bằng chứng cần) |
| D5 | tệp anchor an toàn (`--anchor-out`) | M4 | `AnchorThreatModel`; CLI thật: tệp 0444 | nơi giữ tin cậy (§4.3) |
| E1 | harness thí nghiệm | M3 | `test_v21_experiment` (replay offline) | công cụ riêng, không thuộc đường sản phẩm |
| E2 | chiến dịch đối chứng | **M6** | — | ngân sách chưa duyệt (B-09) |
| F | cách ly Linux tối thiểu (bwrap, opt-in) | **M4** ranh giới (harness độc lập) + **M4** một lượt `aisef run` thật có cách ly (mô hình kịch bản) / M3 nối dây / **M6** lượt có mô hình thật | M3: `test_v21_confine` (từng phép kiểm; đường thành công với phép đo giả lập); M4: `validation/v21/sandbox` + [evidence/sandbox](evidence/sandbox/) trong container Linux thật, mỗi claim là một thao tác đã thử ([SANDBOX-LINUX.md](SANDBOX-LINUX.md)); M4: [decisions/B03-R3-E2E.md](decisions/B03-R3-E2E.md) (CLI thật trong guest, 92/92 kiểm tra ×2, có lượt đối chứng không cách ly) | lượt `aisef run` với **mô hình thật** có cách ly: **M6**; mạng của phiên **không** được cách ly (lượt chạy chỉ dùng `network: host`; `none` chỉ để đo); bwrap lồng chỉ chạy khi nới seccomp + systempaths của container (§6) |

## 3. Phạm vi chính xác của bảo đảm (thay câu "developer không còn sửa được kết quả kiểm tra")

Câu cũ sai phạm vi và được rút lại. Điều đã đo:

- `.pth` do mã của developer hay test ghi vào venv test **không chạy** trong probe (interpreter của kernel, `-I -S`).
- Sửa `RUN.json` hay bất kỳ trường nào nâng verdict ⇒ `--verify` **REFUTED** (verdict dựng lại từ bằng chứng).
- Viết lại nhất quán cả thư mục lượt chạy **sau khi lượt chạy kết thúc** ⇒ REFUTED, **chỉ khi** người vận hành đưa anchor
  đúng từ nơi developer không ghi được (`--expect-anchor`).

Điều **không** có: ranh giới hệ điều hành. Developer và mã test chạy dưới user của người vận hành, nên vẫn có thể: sửa mọi
tệp user đó ghi được (interpreter và gói đã cài nếu ghi được; thư mục lượt chạy *trong lúc* chạy, trước khi anchor được
tính; tệp anchor nếu để trong tầm ghi); đọc mọi tệp user đó đọc được, gồm stimulus ẩn của một thí nghiệm
(DEVELOPER-CONFINEMENT-GAP-001); để lại tiến trình con đã tách
session (`setsid`) sống sau lượt chạy (đo: §4.2). Anchor chứng minh **toàn vẹn** so với một giá trị, không chứng minh lịch
sử là thật. Và: mã của chủ thể trả lời hộ chính nó (mã thoát, giá trị trả về) — một sản phẩm hỏng có thể ra `SATISFIED`
(PM-5; §6, [ANCHOR-THREAT-MODEL.md](ANCHOR-THREAT-MODEL.md)).

## 4. Bằng chứng chạy xuyên suốt đường sản phẩm

`validation/v21/cli_integration/run.sh` trên `b72e51e`, cây sạch (output đầy đủ:
[evidence/cli-integration-b72e51e.out](evidence/cli-integration-b72e51e.out)). CLI `aisef` thật của cây; **nhị phân Open
Code Review v1.12.12 thật** (`182898c`, darwin-arm64, sha256 `bf38abf3…b6839104af7`, build từ nguồn với `-trimpath`);
preflight HTTP thật tới một provider OpenAI-compatible trên loopback (`fakeprov.py`, cũng đóng vai mô hình của OCR theo
kịch bản); developer giả (`fake_opencode.py`) trên PATH đã loại mọi thư mục có `opencode` thật; HOME/XDG riêng.

**Ranh giới live:** mô hình của OCR và developer là kịch bản. Không có request nào tới provider thật, không token trả tiền.
Điều chưa biết: OCR với mô hình thật có tìm ra finding, viết reproducer đúng dạng, và tốn bao nhiêu (B-06, B-09).

### 4.1 Chuỗi review (`aisef run`, cùng một đường quyết định)

Lượt `run1`: seal → approve ×3 → lint READY → `--check` ready → run: lượt 1 developer cộng ba đối số như hai ⇒ OCR thật
review khoảng `base..candidate`, gọi `code_comment` với reproducer ⇒ AISEF tự chạy reproducer bằng probe của nó ⇒
CONFIRMED ⇒ neo vào contract đã duyệt BC-USAGE-* (R-CLI/1.2) ⇒ ANCHORED ⇒ REVIEW_FINDING (trần REVIEW) ⇒ prompt lượt 2 có
finding ⇒ developer sửa ⇒ OCR review lại, sạch ⇒ COMMIT ⇒ `--verify --expect-anchor` VERIFIED.

| Trường hợp | Hành vi | Kiểm chứng |
|---|---|---|
| finding đúng yêu cầu, tái hiện, neo được | chặn; sửa trước merge | CLI thật (trên) + `FixLoop` |
| tái hiện nhưng kỳ vọng không có contract đã duyệt nào neo (UNANCHORED) hoặc trái contract đã duyệt (CONTRADICTS_APPROVED) | ghi lại, **không** tự chặn | `NotABlocker` ×2 |
| không tái hiện được | không chặn | `NotABlocker` |
| partial, hết token, schema manifest không hỗ trợ, timeout (chi phí unknown), lỗi provider | INDETERMINATE ⇒ không bao giờ là "sạch"; fix-loop: lỗi năng lực, hoặc ProviderOutage; advisory: ghi, không chặn | `IncompleteReview` ×6 |
| khoảng rỗng (story không đổi gì) | OCR thật trả `skipped`, 0 token, không gọi mô hình ⇒ review hoàn tất của "không có gì" | `RealBinary` (nhị phân thật) + `NothingToReview` |
| candidate đổi trong lúc review (tệp sửa, commit mới, nhị phân không đúng pin) | review bị loại, không tới main | `CandidateChangedDuringReview` ×3 |
| hết vòng sửa mà lỗi còn | ROLLBACK | `FixLoop` |

`RealBinary` cần `AISEF_TEST_OCR_EXE` nên **skip trong suite hermetic**; chạy riêng trên `b72e51e`: 3/3 OK (preview đọc
đúng; khoảng rỗng skipped không gọi mô hình; review đầy đủ với mô hình kịch bản).

### 4.2 Nối tiếp và toàn vẹn

Lượt `run2` (dự án hai story): S1 COMMIT; developer S2 báo usage rồi **SIGKILL thật** tiến trình `aisef run` (exit 137;
không `finally` nào chạy; `RUN.json` vắng, `RUN.started.json` có) ⇒ `aisef bundle continue`: S1 mang sang, `unaccounted`:
request seq 113 (S2, DEVELOPER) không có result ⇒ `run --parent` **bị từ chối** (exit 2: chi phí chưa đối soát) ⇒ `run
--parent --accept-unaccounted`: CARRIED + S2 COMMIT, `accepted_unaccounted` ghi trong record ⇒ `bundle continue run2` lần
nữa **bị từ chối** (đã có child BEGUN) ⇒ `--verify` run3 VERIFIED; `lineage_usage.cost` = unknown (không bao giờ là tổng
từng phần).

**Lỗi tìm được bằng chính bước này** (test offline không bắt): `--verify --out run3` (đường dẫn tương đối) REFUTED — "the
record's spend is not what the evidence re-derives". Claim lưu đường dẫn tuyệt đối, verifier nhận tương đối ⇒ run tự đếm
mình là anh em bị thay thế ⇒ spend tính hai lần. Sửa ở `lineage_account` (`b72e51e`), reproducer đỏ trước sửa.
Hành vi ghi nhận: lượt bị từ chối vẫn để lại claim (ENDED_UNBEGUN) — lượt sau thay thế nó bằng bằng chứng (claimant đã
mất), không xoá; lượt bị từ chối xuất hiện trong dòng dõi với 0 chi tiêu.

**Journal (rút lại nhận định cũ).** "Append một dòng và fsync nên SIGKILL không thể cắt giữa dòng" là sai. Mỗi sự kiện là
một `os.write` + `fsync`: *ghi hoàn tất* khi `write` trả đủ byte (ghi ngắn ⇒ lỗi, cắt lại, writer bị khoá); *đã đồng bộ* khi
`fsync` trả về — sống qua việc tiến trình bị giết; trước mất điện thì tuỳ thiết bị (trên macOS `fsync` không ép cache của
ổ — `F_FULLFSYNC` — không dùng; không test nào mô phỏng mất điện hay OS sập); *không nguyên tử*: chết giữa lần ghi để lại
dòng cuối bị cắt — reader trả prefix hợp lệ + `torn_tail`, và trường `type` (cuối dòng trong mã hoá chuẩn) thường mất;
*tác dụng bên ngoài* của sự kiện cuối (request đã gửi, commit, merge) **không bao giờ được coi là chưa xảy ra**.

| Cửa sổ gián đoạn (điểm đồng bộ, SIGKILL thật) | Continue làm gì |
|---|---|
| request đã ghi, client chưa chạy | biết: 0 |
| request đã gửi, chưa có usage / có usage chưa có result | chi phí **unknown**; không mở phiên trả tiền trừ khi người vận hành chấp nhận (ghi lại) — cũng đo qua CLI thật |
| candidate đã commit, chưa có sự kiện | nhận diện bằng worktree `wt-<story>` của kernel; không vào baseline; story phát triển lại |
| merge đã đẩy main, story chưa commit trong journal | nhận diện bằng merge của kernel (cha thứ hai + "merge <sha12>") cho candidate đã chứng minh; không vào baseline; story chạy lại; main cuối có đúng các story đã giao, không story nào commit hai lần trong dòng dõi |
| commit không gì nhận diện | **từ chối**; chỉ bỏ ra khi người vận hành nêu `--leave-out-unidentified` (báo cáo ghi) |
| append journal: trước write / ghi ngắn / sau write trước fsync / sau fsync | dòng cắt ⇒ `torn_tail`, tác dụng của nó vẫn được đối soát với git |
| claim đã lấy, child chưa bắt đầu (`ENDED_UNBEGUN`: chính `RUN.json` nói run kết thúc trước khi bắt đầu; `UNBEGUN`: không có bằng chứng nào, hoặc journal 0 byte và không có bản ghi) | claimant đã mất ⇒ thế hệ mới thay thế **có bằng chứng** (claim cũ giữ nguyên); claimant còn sống hoặc ở máy khác ⇒ từ chối, chỉ thay khi người vận hành nêu sha256 của claim |
| child đã bắt đầu rồi chết | không bao giờ bị thay **khi journal của child đọc được**; dòng dõi nối tiếp từ child |
| bằng chứng của child có mà không đọc được (`UNREAD`: thư mục không tìm kiếm được, journal không mở/dựng lại được, liên kết trỏ vào hư không, `RUN.json` nêu journal có sự kiện mà journal vắng) | không bị thay bằng bằng chứng, kể cả khi claimant đã mất; chỉ thay khi người vận hành nêu sha256 của claim (ghi cùng nguyên nhân); một lần đọc hỏng không bao giờ giải phóng hay lấy một claim |
| hai tiến trình cùng yêu cầu | đúng một lấy được (`O_EXCL`), bên kia không tiêu gì |
| child xong, yêu cầu continue lặp lại | từ chối, chỉ tới child — cũng đo qua CLI thật |

**Cửa sổ probe (§0.9) thu hẹp những gì `bundle continue` nhận.** Trên cây trước đó nó chỉ cần journal dựng lại được chuỗi
hash, và coi một `RUN.json` không đọc được như vắng (rơi xuống `RUN.started.json`); một bằng chứng của child không đọc
được bị coi là chưa bắt đầu và bị thay thế (đo ở `becf3c0`: 3/3 biến thể). Nay: cùng luật của `--verify` (đọc được, là
journal mà `RUN.json` nêu, dựng lại được, qua các projection của writer — dòng cuối bị cắt vẫn là ngoại lệ được duyệt),
mỗi cách hỏng có mã (`EVIDENCE_UNREADABLE`, `_MALFORMED`, `_INTEGRITY`, `_PROJECTION`, `_MISSING`, `_MISMATCH`), thêm
`--expect-anchor` (`anchor_checked`). Chi tiết và bảng mã: [USAGE-2.1.md](USAGE-2.1.md) §5. Không có `--expect-anchor`,
một continuation chỉ chứng minh nhất quán và không đối chiếu `EVIDENCE.json` với thư mục (backlog V21-54).

Tiến trình của lượt bị giết (đo): probe nhận diện theo process group và pid của candidate — đều biến mất (watchdog của
range anchor `killpg` nhóm của nó khi controller chết). Tiến trình con đã `setsid` **không** bị kiểm soát: sống sau lượt
chạy (một lượt bình thường phát hiện nó là "escaped").

### 4.3 Anchor

Ba nơi tách biệt: **tạo** — cuối lượt chạy, sha256 của manifest bằng chứng, in ra và ghi `--anchor-out`; **giữ bản tin
cậy** — của người vận hành, ở nơi developer không ghi được (hiện cùng user ⇒ cần nơi ngoài: commit đã ký, kho
append-only, máy khác — có điều kiện, chưa làm); **verifier lấy expected** — chỉ từ `--expect-anchor` do người vận hành đưa,
không bao giờ đọc từ thư mục lượt chạy. Tệp anchor: `O_CREAT|O_EXCL|O_NOFOLLOW`, 0444, fsync; đường dẫn đã có ⇒ exit 2;
symlink ⇒ từ chối; lỗi ghi ⇒ exit 2; tệp dở dang không bao giờ hợp lệ (`read_anchor` đòi đúng 64 hex + xuống dòng).
Chi tiết: [ANCHOR-THREAT-MODEL.md](ANCHOR-THREAT-MODEL.md).

## 5. Suite đầy đủ theo commit

Máy: macOS Darwin 25.5.0 arm64, Python 3.14.7 (`/opt/homebrew/bin/python3`). Lệnh: `python3 -P validation/v2/owned_run.py
--out … -- python3 -m unittest discover -s tests` trong worktree tách rời đúng SHA, `env -i`, HOME/XDG mới, PATH không có
thư mục chứa `opencode`, dưới khoá nặng toàn máy. Kết quả mỗi commit chỉ đại diện cho chính commit đó.

| Commit | Nhánh | UTC | Kết quả |
|---|---|---|---|
| `919a271` | 2.1 | 04:27 → 05:05 | Ran 5507, 62 F, 80 skip |
| `d622e71` | 2.1 | 05:12 → 05:51 | Ran 5550, 76 F + 2 E, 80 skip |
| `c0ec1a5` | 2.0.1 | 05:52 → 06:30 | Ran 5496, 8 F, 80 skip (3 lỗi thật sửa ở `5e46fe9`) |
| `6634d6d` | 2.1 | 06:31 → 07:09 | Ran 5555, 18 F, 80 skip |
| `4fd070a` | 2.1 | 09:33 → 10:20 | Ran 5598, 18 F, 82 skip — đúng 18 lỗi của [RED-SUITE.md](RED-SUITE.md) |
| `5e46fe9` | 2.0.1 | — | lượt bị huỷ, **không có kết quả**; HEAD đã sang `f006d3d` |
| `f006d3d` | 2.0.1 (HEAD) | 10:21 → 11:00 | Ran 5497, **4 F**, 80 skip — bốn so bản ghi niêm phong (mutation ×2, K-NOWORK-001, conformance): [RED-SUITE.md](RED-SUITE.md) cuối tệp. Lý do skip: lượt `-v` trên chính commit này, kết quả trong báo cáo gửi chủ dự án |
| HEAD cuối của 2.1 (vòng 4) | 2.1 | chạy sau commit này, trên đúng SHA đã định (một commit không chứa được kết quả suite của chính nó): `closure-evidence/v2/v2.1/round-4/SUITE.md` và báo cáo gửi chủ dự án; nếu một commit sau đó đổi bằng chứng, các checker phụ thuộc bằng chứng được xác minh lại trên HEAD mới và kết quả của commit cũ không được gán cho HEAD mới |

Các commit `51f2eb5` … `b72e51e` của 2.1 **chưa có suite đầy đủ riêng**; kết quả của `4fd070a` không đại diện cho chúng.
Cây của cửa sổ probe (§0.9, `f69124c`) **chưa có suite đầy đủ**: kết quả `45554e0` (7.305 test, OK) là của cây `1d4f0156…`.

**Suite trong guest Linux** (`validation/v21/sandbox/linux_suite.sh`, 2026-10-15): chạy `unittest discover` (toàn bộ hoặc
tập con) trên cây `git archive` trong một container (image cục bộ `aisef-sandbox-measure`, Python 3.14.8, bubblewrap
0.12.0, `--network none`, profile X1). Đã đo 84 trên 405 module (1.354 trên 7.309 test) qua bốn lượt ≤ 10 phút: hai lệch
Linux thật — 9 test đỏ ở `v2.test_v21_read_set` (recorder đếm đôi mỗi lần khởi chạy con trên Linux) và `MUT_SAFE_6` giả
định host đông tiến trình — và một nhóm skip do thiếu node (backlog V21-73, V21-74). Các con số là của làn `linux-suite`; báo cáo kết quả của làn
chưa được commit (công cụ và test giữ bộ chạy thì đã). Đây **chưa** là suite đầy đủ trong guest; ước tính 50–65 phút
(± 30 %) từ các số đo lấy lúc host tải 49–123: một cận trên, chưa đo lúc máy rảnh.

**Test đỏ:** từng test, kỳ vọng/thực tế, artifact, công cụ sinh và căn cứ phân loại: [RED-SUITE.md](RED-SUITE.md). Không
test nào bị bỏ, nới hay đổi oracle.

**Bộ evidence ứng viên** (`validation/v21/candidate_evidence.py`, ngoài repo; không phải bản niêm phong, không được ai đọc
để quyết định), sinh trên `b72e51e` ở cây sạch: 7/7 bản ghi sinh được, không bản nào giống bản niêm phong. K-NOWORK-001
vẫn "REPRODUCED AND CORRECTED" trên kernel 2.1; Q0 48/52 (bốn checker chờ mutation, P2, inventory); acceptance C2-P5 ứng
viên: `PROBLEMS` (proposal không hiện hành; guard hiệu chuẩn đỏ vì hai thẩm quyền mới) — sau khi ánh xạ ngược 124 danh
tính probe theo luật `rebind`, phần không được dung sai là engine digest. Bảng sha256 và đường khác nhau:
[RED-SUITE.md](RED-SUITE.md) cuối tệp. Bộ đầu tiên (`a399224`) viết trong repo nên làm nhiễu chính các checker nó quan
sát — bị loại; công cụ giờ từ chối mọi đường ra trong repo.

## 6. Giới hạn còn tồn tại

- **Cách ly OS cho phiên model: có mã opt-in, đo bằng thao tác đã thử** ([SANDBOX-LINUX.md](SANDBOX-LINUX.md),
  `aisef2/app/confine.py`, `validation/v21/sandbox`, đo ở `764dfa2`). Trong container `python:3.14-slim-trixie@sha256:3353bb7e…`
  trên Docker Desktop (kernel guest `7.0.12-linuxkit`, không có AppArmor), bwrap 0.12.0 (uid 1000) **chỉ chạy khi**
  container nới `seccomp=unconfined` **và** `systempaths=unconfined` (đo từng trục: X1 chạy; X2, P2, P3 không) — tức
  nới chính ranh giới của container. Khi chạy, phép đo của kernel dùng đúng dòng lệnh của phiên (client + worktree của
  `<out>/repo`): phiên chỉ **ghi** được workspace; **đọc** (chỉ đọc) hệ thống, thư mục của client, `<out>/repo/.git` (nằm
  trong run directory: bản clone của lượt chạy), thư mục cấu hình client và `read_only` (hệ thống gồm cả `/usr`: interpreter
  hay kernel cài dưới `/usr`, `/usr/local` đọc được); phiên reviewer **không ghi được gì** của host — checkout nó review
  cũng bind chỉ đọc (ghi, `chmod` đều `Read-only file system`). Bị từ chối: đọc file khác của
  run directory, verifier, `~/.ssh`, dữ liệu auth của client; ghi runtime, kernel, git dir (`Read-only file system`);
  tạo user namespace mới; thấy tiến trình của container (PID namespace riêng); tiến trình `setsid` sống sau phiên
  (tiến trình thấy lúc bwrap vừa trả về được nhìn lại tới 1 s, vì namespace PID có thể còn đang bị kernel dọn:
  ở `764dfa2` 0/2000 lần đo báo nhầm, `teardown-race-*.json`; lần nhìn đầu thấy nó ở cả hai cấu hình — gộp bốn lượt
  ở `3e0409c` và `764dfa2`: không socket 2/2000, có socket 8/2000, không kết luận khác biệt; tiến trình ngủ của probe
  sống 120 s, quá giới hạn 60 s của probe cộng 1 s đó, nên một survivor thật không thể tự hết giờ trước lần nhìn cuối).
  Capability = 0, NoNewPrivs = 1 (đọc từ `/proc`). Ghi anchor/run-dir **thành công vào tmpfs riêng** của sandbox, file
  thật không đổi — không phải "bị từ chối". **Mạng**: `network: none` cắt mạng nhưng phiên cũng không tới được provider
  — chỉ để đo, settings từ chối cho lượt chạy; `host` (lượt chạy dùng) thì egress **không** bị cách ly và abstract unix
  socket của netns dùng chung; chưa có egress allowlist. Khi xin cách ly mà không cấp được thì run/`--check`/phiên
  **từ chối trước request provider** (fail-closed); không dùng chung với `review.finder: ocr` (OCR gọi mô hình ngoài
  phiên của client). **Đã có** (vòng 3): một lượt `aisef run` thật có cách ly trong Linux guest với mô hình kịch bản (§0.4). **Chưa**: lượt với
  mô hình thật; không coi nested-bwrap thay cho profile container (khuyến nghị F giữ nguyên). `confine.py` là mutation target (30 target; §0.3).
- Lượt live: chỉ ba lượt canary tầm thường (§0.10). Hiệu quả so với agent trực tiếp, chất lượng finding của OCR và của vòng
  sửa review, chi phí của workload cỡ LedgerLock — không biết.
- **Mã của chủ thể trả lời hộ chính nó (PM-5) — mô tả một giới hạn, không phải chấp nhận rủi ro.** Kênh của probe do
  controller giữ và được xác thực; **nội dung** những câu trả lời mà tiến trình của chủ thể đưa về chính nó (mã thoát,
  giá trị trả về, ngoại lệ ném) thì không: mã của ứng viên chạy trong tiến trình đó. Mã viết để trả lời hộ chính nó, hoặc
  nhận ra mình đang bị probe (`sys.flags.isolated`, môi trường bị lọc), biến được một sản phẩm hỏng thành `SATISFIED` — đo
  trên cả ba probe chạy chủ thể: `closure-evidence/v2/v2.1/round-3/probes/repro-5.py.txt` (đối chứng trung thực REFUTED
  ×3, ứng viên viết để trả lời hộ SATISFIED ×3); một ứng viên chỉ đọc `sys.flags.isolated` cũng SATISFIED ×3, y hệt trên
  cây nguồn của tag `v2.0.0` (OWNER-DECISIONS-2026-10-15.md, PM-5; đo trên cây nguồn, không phải wheel PyPI). *Người vận
  hành thấy:* `delivery_verdict` PASS, `aisef run --verify --expect-anchor` in VERIFIED, journal ghi COMMIT. *Người dùng
  cuối* cài sản phẩm và chạy thì gặp traceback hay mã thoát 1. Bản ghi probe chỉ giữ verdict (không giữ mã thoát mà chủ
  thể đã khai), nên không dấu vết nào nói điều đó; reviewer chạy cùng probe cho reproducer nên một finding thật cũng có
  thể không được CONFIRMED (đọc mã, chưa đo). *Tần suất: chưa đo* — 0 trường hợp quan sát được trong 3 phiên developer của
  attempt 4 (chạm tới tài liệu của probe: một đọc nguồn, một đọc scratch, hai tìm probe trên máy; không phiên nào đổi gì)
  và trong 4 phiên developer của canary tier 2/2b (1 + 3); N nhỏ, workload tầm
  thường, **không phải bằng chứng vắng mặt**. Biện pháp thật nằm ở chỗ khác trong backlog: V21-02 (developer đọc được
  ngoài workspace), B-07 (sandbox V2-05), F (ranh giới cách ly), review độc lập. Câu công khai "mã đang bị kiểm không thể
  tự chế ra kết quả đạt" (`README.md:45`, `README.vi.md:45`, `docs/v2/USAGE.md:110`, `docs/v2/USAGE.vi.md:113`,
  `landingpage/index.html:846`) quá rộng so với phép đo này; sửa chúng không thuộc báo cáo này (backlog V21-26).
- **Cửa sổ probe để lại các giới hạn có tên** (USAGE-2.1.md §8; backlog V21-54 … V21-74): trần của một quan sát
  `grep_count` là `max(timeouts_s.probe, 30 s)`; một `within_s` dưới ≈ 0,1 s có thể lật so với 2.0.0; bộ nhớ worker ≈ 2,2
  lần đầu vào; một parser-limit refusal vẫn retry được trong `limits.ENVIRONMENT` và lời khắc phục chưa tới developer; chuỗi
  regex của `cli_invocation` chạy trong tiến trình kernel không hạn chót; `probe-observations/` đọc được bởi mọi tiến trình
  của user (không cách ly) và chỉ che giá trị bí mật của chính run; OCR chưa có bằng chứng dựng lại.
- **Phần dư của họ lineage** (USAGE-2.1.md §7; backlog V21-56): một `CR`/`LF` trong đường dẫn của thư mục chứa worktree
  `wt-<story>` làm `reconcile` không báo mục `candidate` (báo cáo thiếu một dòng; kế hoạch không đổi vì story đã giao lấy từ
  `story/commit` của journal); một dòng luồng phiên bắt đầu bằng `{`, không parse được và không phải dòng cuối, bị bỏ im lặng
  (0/176 dòng trong 8 luồng phiên mô hình thật của canary tier 2 và 2b); một `CR` trong tên một mount point làm bảng mount
  của host là `None` và mọi lượt có cách ly bị từ chối (fail-closed; do review đo trong guest, B03-R3-CLIENT, không đo lại).
- Anchor chỉ có nghĩa khi bản tin cậy nằm ngoài tầm ghi của developer; hiện chưa có nơi đó.
- Tiến trình con tách session thoát việc dọn dẹp.
- Mất điện / OS sập không được mô phỏng; trên macOS `fsync` không ép cache của ổ.
- Luật neo: một stimulus **mới** bị xếp sai mệnh đề vẫn có thể được neo sai (ADR-7).
- Module mới của 2.1 (`lineage`, `usage`, `review_ocr`, `review_verify`, `bundle_cli`, `confine`) là mục tiêu mutation (§0.3).
- Suite đầy đủ chỉ chạy trên macOS (cho cây `1d4f0156…`); trong guest Linux mới đo 84/405 module (§5); CI Windows/Linux
  chưa chạy cho 2.1 (chưa push).

## 7. Quyết định cần chủ dự án (phương án và khuyến nghị)

| # | Quyết định | Phương án | Khuyến nghị |
|---|---|---|---|
| B-01 | ARCHITECTURE-EXCEPTION-V2-007 (ba danh tính) | phê chuẩn / bác | phê chuẩn — [hồ sơ](decisions/B-01-V2-007-THREE-IDENTITIES.md) |
| B-02 | phát hành 2.0.1 | (a) lập lại các bản ghi phái sinh đỏ bằng công cụ của chúng rồi qua CI/RC/Q0–Q5; (b) hoãn 2.0.1, gộp vào 2.1 | (a) nếu cần sửa an toàn sớm; nếu không, (b) |
| B-03a | engine digest admission (5 artifact) | (a) luật dung sai digest engine khi verdict không đổi; (b) bản ghi v2.1 mới | (b): giữ nguyên luật bất biến, thêm bản ghi mới |
| B-03b | mutation (320 target cũ, ~32 giờ một worker) | (a) phase mới trong `RECORDS`/`SUPERSEDED`; (b) chỉ target đổi AST | (a); thêm module mới của 2.1 làm target |
| B-03c | hai thẩm quyền PRODUCT_TRUTH mới (`bundle_cli.migrate`, `review_verify.verify`) | chấp nhận / chuyển vào `run_story` | chấp nhận: cả hai không commit/merge gì (migrate viết một bundle mới; verify chạy probe) — nhưng là quyết định thẩm quyền |
| B-03d | conformance lịch sử, item corpus Q5 | ruling nêu thay đổi 2.1 / corpus 2.1 mới | cả hai; không sửa bản 2.0 |
| B-04 | contract S-10-a của LedgerLock | A (danh sách §10, chặt hơn ở `unittest`) / B (toàn stdlib) | A — [hồ sơ](decisions/B-04-LEDGERLOCK-S-10-a.md) |
| B-08 | K-NOWORK-001: story không đổi gì vẫn một lượt review | giữ / bỏ | giữ (OCR khoảng rỗng tốn 0 token) — [hồ sơ](decisions/B-08-K-NOWORK-001-REVIEW.md) |
| B-09 | ngân sách E2 (đề nghị 140 USD): canary bậc 1–2b **đã chạy** (≈ 0,599 USD ước tính, §0.10); phần chiến dịch chưa quyết | duyệt / giảm / không | theo bậc, không 140 USD nguyên khối (OWNER-DECISIONS-2026-10-15.md, B-09; khuyến nghị, chưa duyệt) — [hồ sơ](decisions/B-09-CANARY-THEN-CAMPAIGN.md) |
| B-10 | nơi đăng tài liệu công khai | A README tự chứa / B repo docs công khai / C host khác / D public repo | A — [hồ sơ](decisions/B-10-PUBLIC-DOCS.md) |
| F | ranh giới cách ly Linux | (a) container là ranh giới (cap-drop, mount chỉ đọc, user không root, giữ seccomp; mạng chỉ tới provider qua egress allowlist — `--network none` thì phiên không tới được provider), không bwrap lồng; (b) bwrap trong container đã nới seccomp + systempaths (đo: X1, [SANDBOX-LINUX §3](SANDBOX-LINUX.md)); (c) máy/VM Linux riêng | (a), **chưa đo**: không phải nới ranh giới của container; (c) khi cần chạy song song |
| P-WIN | cửa sổ sửa module probe (PM-1, 2, 3/4, 6, 11 là lỗi; PM-5, 7, 8, 9, 13 là quyết định) | (a) một cửa sổ: sửa chung rồi hiệu chuẩn lại 19 hàng + checker liên quan; (b) từng mục; (c) giữ nguyên, ghi là giới hạn | (a) — [decisions/B03-R3-PROBE-MODULE-FINDINGS.md](decisions/B03-R3-PROBE-MODULE-FINDINGS.md) §4. **Đã thực hiện trên nhánh ứng viên (§0.9)**; còn hiệu chuẩn lại, mutation, suite |
| RV-1/2 | `reproducer_contract` raise `RecursionError` ở lồng ~3.000 tầng (fail-closed); câu NOT_REPRODUCED sai cho INDETERMINATE | sửa cùng cửa sổ probe / để nguyên | sửa cùng P-WIN (cùng họ PM-3). **Đã sửa trên nhánh ứng viên (§0.9)**; còn mở: giới hạn 63 (V21-67) và token trạng thái `NOT_REPRODUCED` (V21-66) |
| — | các quyết định mở của cửa sổ probe (không-retry của PM-3, duyệt lại approval PM-9, ReDoS, `within_s`, thống nhất UNRUNNABLE/REFUTED, cổng OCR sớm, `account_of`, `--expect-anchor` mặc định, đọc CRLF trên Windows…) | cột Disposition của backlog V21-39 … V21-74 | không quyết thay chủ dự án; mỗi hàng nêu các phương án và khuyến nghị của làn |
| RM-3 | xoá ba tệp probe trong `site-packages` (§0.5) | chủ dự án chạy đúng ba `rm` đã nêu / duyệt để phiên này chạy | chủ dự án tự chạy sau khi đối chiếu đường dẫn |
| — | nơi giữ anchor tin cậy | commit đã ký / kho append-only / máy khác | commit đã ký trong repo riêng của người vận hành |
