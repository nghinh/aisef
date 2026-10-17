# AISEF 2.1 — Quyết định kiến trúc (nhánh `v2.1/foundation`, 2026-10-06)

Nguồn: chỉ thị của chủ dự án trong phiên 2026-10-06 (đề xuất cải tiến + báo cáo 360°); "chỉ thị 2026-10-15, mục N" là chỉ thị lần
thứ tư của ngày ấy, nguyên văn ở `closure-evidence/v2/v2.1/round-5/OWNER-DIRECTIVE-2026-10-15-B.md` (commit `8e6f583`, nay đã nằm trong cây này). Mỗi quyết định nêu: vấn đề đã đo,
quyết định, phương án bị loại, hệ quả, và cái **không** tuyên bố. Giữ nguyên: một đường quyết định, taxonomy owner, journal
format 3, ràng buộc candidate↔evidence, chính sách commit/rollback. Không viết lại khung, không nhập orchestrator ngoài.

---

## ADR-1 — Probe chạy trên interpreter của kernel với `-I -S`; test của developer chạy venv riêng

**Đã đo (2.0.0, 610a593):** một `.pth` mà mã test ghi vào site-packages của `<out>/probe-python` được **thực thi bên trong**
probe `python_callable_v2` (cờ `-I -B` không tắt `site`) — kênh để mã ứng viên chạm controller giữ khoá HMAC.
Reproducer: `tests/v2/test_v21_identity.py::PthChannel` (cùng kịch bản chạy trên 610a593 cho `True`).

**Quyết định.** Mọi lần khởi chạy của probe đang hoạt động (controller, agent, subject của `cli_invocation`,
`python_callable_v2`, `process_effect`) thêm `-S`. `ExecutionEnv.interpreter` = `sys.executable` (ngoài thư mục lượt
chạy). Test của developer chạy `<out>/test-python` (`StoryInputs.test_interpreter`). RunSpec ghi cả `python` (của probe)
và `test-python`.

**Loại:** băm cây venv trước mỗi probe (TOCTOU, mã test chạy cùng user); chỉ tách venv (đường dẫn đoán được, mã test biết
`sys.executable` của chính nó). **Probe Cycle-1 (`python_callable.py`, không còn hoạt động) không đổi** — digest của nó là
lịch sử đã niêm phong.

**Không tuyên bố:** đây **không** là sandbox. Mã test chạy dưới user của người vận hành và vẫn có thể sửa interpreter của
máy hoặc gói aisef đã cài; sandbox OS (V2-05) là việc riêng.

## ADR-2 — Ba danh tính tách rời (ARCHITECTURE-EXCEPTION-V2-007)

**Vấn đề.** 2.0.0: `probe_digest` = sha256 các tệp nguồn probe; spec id, semantic hash, plan, approval-qua-plan, bản ghi
hiệu chuẩn đều buộc vào nó. Sửa một chú thích trong probe ⇒ đổi mọi spec id ⇒ mọi bundle phải buộc lại, mọi bản ghi phái
sinh đỏ (**chưa đo**: tuyên bố "chỉ thêm `-S` làm đỏ 37 test" không có bản ghi đo đã commit; bản ghi V2-007 ghi
UNMEASURED).

**Quyết định.** Ba danh tính:

| Danh tính | Định nghĩa | Ai buộc vào |
|---|---|---|
| ngữ nghĩa contract | `contract_hash` (không đổi) | approval |
| năng lực probe | `DIGEST = sha256(json([PROBE_ID, CAPABILITY_VERSION, CLASSES]))` | spec, semantic hash, plan |
| byte đang chạy | `EXECUTION_DIGEST` = sha256 các nguồn probe (công thức cũ) | hàng hiệu chuẩn (check 9), RunSpec |

Sửa byte mà không đổi điều quan sát ⇒ spec/approval/plan giữ nguyên, nhưng **phải chứng minh lại hiệu chuẩn** (test
`ThreeIdentities.test_the_shipped_calibrations_name_every_class_at_the_bytes_that_run_now` đỏ cho tới khi
`release_calibration.py --write` chạy lại). Đổi điều quan sát (lớp mới, ngữ pháp stimulus, luật verdict) ⇒ tăng
`CAPABILITY_VERSION` bằng tay (file_artifact đã lên 2 khi thêm `python_imports`).

**Không tuyên bố:** digest khớp **không** chứng minh hai lần thực thi tương đương hành vi; băm AST cũng không. Bằng chứng là
tương phản hiệu chuẩn trên fixture đã commit. Kỷ luật tăng version là trách nhiệm review, không máy nào kiểm: ba probe
(`cli_invocation`, `process_effect`, `python_callable_v2`) đã đổi hành vi từ 2.0.0 mà `CAPABILITY_VERSION` vẫn 1 (D-2: chủ dự án
chấp nhận giới hạn này ngày 2026-10-18 và giữ `CAPABILITY_VERSION` 1, `closure-evidence/v2/v2.1/round-5/OWNER-ANSWERS-2026-10-18.md`,
USAGE-2.1 §2; 50 trong 53 approval được giữ vẫn chỉ dựa vào luật phiên bản).

**Di trú:** spec id của 2.0.0 đổi một lần → `aisef bundle migrate` buộc lại `plan` và ghi một bundle **ứng viên mới** (bản
gốc không bị sửa). Một approval chỉ được mang sang khi nó còn buộc đúng hash **và** không có thay đổi capability đã khai báo
(`CAPABILITY_CHANGES`) chọn trúng contract của nó (chỉ thị 2026-10-15, mục 1); approval của contract bị chọn bị giữ lại và
là việc duyệt lại của chủ dự án. LedgerLock 2.0.0: 59 spec, 67 obligation; 53 trong 59 approval được giữ, **sáu** contract
bị giữ lại (D-1: chủ dự án đã nêu bốn và quyết giữ sáu ngày 2026-10-18). Lần ghi trước, "admit 9/9, không duyệt lại", là phép đo trước khi `migrate` thôi
giữ approval chỉ vì hash: ứng viên chưa nạp được cho tới khi sáu contract được duyệt lại, và admission thật chỉ chứng minh
được sau khi hiệu chuẩn sinh lại. Bằng chứng cũ giữ nguyên byte.

**Trạng thái của ngoại lệ:** **ĐÃ DUYỆT** — chủ dự án phê duyệt B-01 trong chat ngày 2026-10-06; kỹ thuật chép nguyên
văn vào `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` (seq 4) theo chỉ thị của chủ dự án "Ghi quyết định này vào sổ
quyết định hiện có" — chủ dự án **không ký** sổ đó hay bản ghi ngoại lệ. Bản ghi:
[`closure-evidence/v2/v2.1/ARCHITECTURE-EXCEPTION-V2-007.json`](../../closure-evidence/v2/v2.1/ARCHITECTURE-EXCEPTION-V2-007.json),
nối vào lineage phê duyệt của RFC bằng
[`AISEF-V2-RFC-AMENDMENT-V2-007.json`](../../closure-evidence/v2/v2.1/AISEF-V2-RFC-AMENDMENT-V2-007.json); RFC sửa ở
§5.1, §8, §9.1.1, §12 (check 6, 9), §35 và Review 2, không đổi hàng nào của bảng đóng băng. **Áp dụng trước khi được
duyệt** (`919a271` 2026-10-06 11:27 +07, `06d4e62`, `4d4c53a`): bản ghi nói rõ điều đó và không ghi lùi ngày. Phê duyệt
kiến trúc không xác nhận implementation đã đúng — tương thích, migration và ràng buộc evidence vẫn phải kiểm chứng (B-03).

## ADR-3 — `--verify` dựng lại mọi trường có thể nâng verdict; manifest + anchor

**Đã đo:** sửa riêng `RUN.json` (bỏ `budget_stop`, đặt PASS) vẫn VERIFIED trên 2.0.0. **Quyết định:** outcome lấy từ
journal; settings buộc vào journal bằng cách dựng lại `runspec_hash`; chi tiêu dựng lại từ luồng phiên + ledger preflight;
story bắt đầu mà không kết thúc = bị từ chối; trường chỉ có trong record **chỉ được hạ** verdict. `EVIDENCE.json` băm record
(JSON chuẩn hoá), journal, mọi phiên, preflight và các tệp `review-findings/` (nếu có: B-03 vòng 3, mục 5); digest của nó là **anchor** in ra cho người vận hành giữ ngoài thư mục;
`--verify --expect-anchor` bác bỏ cả việc viết lại nhất quán toàn thư mục. Không đổi format journal.
**Không tuyên bố:** không có anchor thì verify chỉ chứng minh *nhất quán*, không chứng minh *xác thực*.

## ADR-4 — PRESERVE của story đã commit được chứng minh ở candidate (V21-38)

Lỗi hồi quy do developer gây ra được tìm **trước merge**: CONTRACT_UNSATISFIED, owner DEVELOPER, retry được, tiêu chí được
đưa vào prompt retry. Chứng minh lại sau merge vẫn giữ, cho thay đổi do chính merge gây ra (INTEGRATION). Chi phí: mỗi spec
PRESERVE được chứng minh hai lần mỗi story.

## ADR-5 — `python_imports`: import đếm bằng cú pháp (V21-37)

Lớp mới của `file_artifact` (`ast`, loại import tương đối, tệp không parse ⇒ không có số đếm). Hợp đồng LedgerLock sửa đổi
chỉ là **bản nháp chưa duyệt**, hai phương án (A: danh sách §10 trừ `unittest` vì bất biến IX; B: toàn stdlib) — chủ dự án
chọn và duyệt. **Không thấy:** `importlib.import_module`/`__import__`.

## ADR-6 — Định dạng soạn bundle + công cụ (mục tiêu 3)

`aisef-v2-authoring/1` = bundle trừ những gì kernel dẫn xuất. `seal` dùng chính constructor của kernel; **không bao giờ
duyệt**; `approve` một contract mỗi lệnh, `human:<tên>`. **Không tuyên bố:** công cụ không biết ai gõ lệnh — giữ bundle và
lệnh ngoài tầm developer agent.

## ADR-7 — Review: tìm thì tự do; chặn chỉ khi probe tái hiện VÀ contract đã duyệt neo kỳ vọng

Finding có thể kèm **reproducer** (hành vi mệnh đề yêu cầu, theo ngữ pháp probe); AISEF chạy bằng probe của chính nó, đã
hiệu chuẩn, ở candidate. CONFIRMED ⇔ probe bác hành vi đã nêu. Nhưng CONFIRMED chỉ chứng minh candidate *không làm* điều
finding nói — **không** chứng minh yêu cầu đòi điều đó. Theo chỉ thị của chủ dự án ("finding tái hiện được nhưng kỳ vọng
sai requirement không tự trở thành blocker"), chặn còn cần **neo** (`review_verify.anchor`), quyết định chỉ từ contract đã
duyệt và mệnh đề đã niêm phong của bundle, không bao giờ từ chữ của reviewer:

| Trạng thái | Khi nào |
|---|---|
| ANCHORED | contract đã duyệt của mệnh đề được trích, cùng subject, quan sát mọi khoá được kỳ vọng và đều kỳ vọng đúng giá trị của finding; giá trị đó là *hằng* của mệnh đề: ≥ 2 contract với stimulus khác nhau, hoặc 1 contract mà văn bản mệnh đề nêu đúng giá trị và không số nào khác |
| CONTRADICTS_APPROVED | một contract đã duyệt của yêu cầu, cùng subject, **cùng stimulus**, kỳ vọng khác; hoặc hằng của mệnh đề khác giá trị finding nêu |
| UNANCHORED | mọi trường hợp khác (không contract nào khai báo mệnh đề; không cùng subject/khoá; contract của mệnh đề kỳ vọng các giá trị khác nhau ⇒ kết quả phụ thuộc đầu vào) |

`fix-loop`: CONFIRMED ∧ ANCHORED ∧ mức ≥ `min_severity` ⇒ REVIEW_FINDING (giới hạn REVIEW làm vòng sửa có biên), nội
dung vào prompt retry. Đo trên bundle LedgerLock 2.0.0: 4/5 lỗi smoke #2 neo được (R-9/2, R-9/3 ×2, R-9/5); lỗi thứ năm
trích R-7/1 (contract quan sát tệp, không quan sát mã thoát) ⇒ UNANCHORED, chỉ phân loại. Finding hiểu sai `add(2,2)=5`
và `snapshot thiếu tệp → 4` không chặn.

**Toàn vẹn.** Reviewer chụp HEAD và mọi tệp của checkout trước finder; so lại sau finder và sau các probe kiểm chứng. Đổi
⇒ bỏ mọi finding, CAPABILITY_UNRUNNABLE. Kiểm chứng chạy ở SHA đã chụp.

**Trạng thái kiểm chứng của một finding** (cửa sổ probe, chỉ thị 2026-10-15 mục 3–4): `CONFIRMED` (probe bác hành vi đã nêu),
`NOT_REPRODUCED` (**chỉ** khi probe `SATISFIED`), `INDETERMINATE` (probe chạy mà không quyết được), `UNVERIFIABLE` (không
chạy được hay không quyết được vì công cụ: spec vô nghĩa, probe `UNRUNNABLE`, hết hạn, lồng quá 63 tầng). Chỉ `CONFIRMED`
cùng ANCHORED chặn; một kiểm tra không thực hiện được hay không đủ kết luận không bao giờ là bằng chứng rằng finding
không tái hiện. Một regex do reviewer (hay tác giả spec) cấp khớp trong một worker dưới `timeouts_s.probe`; hết hạn hay
lỗi là `UNRUNNABLE`/`UNVERIFIABLE`, không bao giờ `REFUTED` hay `NOT_REPRODUCED`. Bản ghi cũ được đọc như đã viết.

**OCR** (v1.12.12 = 182898c, Apache-2.0) là một finder, chạy như tiến trình ngoài: binary ghim theo sha256, route chỉ qua
biến OCR_LLM_* (không `--provider`, không tệp cấu hình, HOME riêng), phạm vi do AISEF tính từ journal. Coverage do AISEF kiểm
(module review_ocr). Không đủ ⇒ dưới `fix-loop`: CAPABILITY_UNRUNNABLE (lỗi provider ⇒ PROVIDER_UNAVAILABLE). Token của OCR
vào ngân sách của run qua một luồng phiên; không báo token ⇒ "unaccounted" ⇒ run dừng chi tiêu. Danh tính binary
(pin, rồi dòng `version` tự khai) được kiểm **hai lần**: ngay đầu `aisef run` (trước claim, clone, preflight và mọi phiên;
từ chối có cấu trúc, mã thoát 2) và trước mọi lệnh review (kiểm soát lúc dùng, không bị lần nhìn sớm thay thế). Settings
**không có** `review` ⇒ luật 2.0.0 (advisory), ghi rõ trong record.

**Đã kiểm chứng:** offline với finder giả (6 nhóm trường hợp, `test_v21_review_chain`); với **nhị phân OCR thật** (sha256
khớp pin; byte tái tạo được từ commit đã ghim trên một máy — REPORT §0.5, không nói ai dựng tệp ghim): preview, và một
lượt review đầy đủ mà mô hình là server giả trên loopback (manifest thật COMPLETE theo luật của adapter, finding có
reproducer được đọc). **Chưa:** mô hình thật.

**Không tuyên bố:** neo không quyết định được một stimulus **mới** có thuộc điều kiện của mệnh đề hay không — reviewer gọi
tệp hỏng là "lỗi I/O" (R-9/3) vẫn neo được (đo bằng `test_known_limit_a_new_stimulus_under_the_wrong_clause_anchors`).
Stimulus mà một contract đã duyệt quyết định khác thì bị bắt (CONTRADICTS_APPROVED).

## ADR-8 — Nối tiếp thay cho resume tại chỗ; đối soát thay cho giả định; chi phí không biết là `null`

Journal có schema đóng; resume tại chỗ cần đổi format. Thay vào đó `aisef bundle continue`: baseline = commit cuối journal
xác nhận; obligation đã giao thành story VERIFY mà kernel chứng minh lại, không gọi developer (một lượt review mà luật
K-NOWORK-001 của chủ dự án giữ — không đổi); `aisef run --parent` ghi dòng dõi. Bằng chứng của lượt cũ không bị sửa (chỉ
thêm tệp claim). Quy tắc (module `aisef2/app/lineage.py`):

- **Journal hoàn tất ≠ đồng bộ ≠ nguyên tử ≠ tác dụng.** Một append là `write` + `fsync`: hoàn tất khi `write` trả đủ byte,
  đồng bộ khi `fsync` trả về — sống qua việc tiến trình bị giết; trước mất điện thì tuỳ thiết bị (trên macOS `fsync` không
  ép cache của ổ, `F_FULLFSYNC` không dùng) — *không* nguyên tử (chết giữa lần ghi để lại dòng cuối bị cắt). Một sự kiện ghi lại một tác dụng đã
  xảy ra; thiếu nó không có nghĩa tác dụng chưa xảy ra. *(Rút lại nhận định trước đó — "SIGKILL không thể cắt giữa dòng" —
  trong commit 7e0aac0: sai; một tín hiệu chết người có thể làm lần ghi ngắn, và nhận định ấy lẫn tính hoàn tất với tính
  nguyên tử.)*
- **Đối soát.** Mọi thứ journal không xác nhận được nhận diện với git và danh tính thao tác của journal (merge của kernel
  cho candidate đã chứng minh; candidate trong worktree của kernel); không nhận diện được ⇒ từ chối trừ khi người vận hành
  bỏ ra có tên. Request không có result mà luồng phiên *đọc được* ⇒ chi phí unknown ⇒ không mở phiên trả tiền nào trừ khi
  người vận hành chấp nhận (`--accept-unaccounted`, ghi lại; R4: chủ dự án giữ như vậy ngày 2026-10-18). Bằng chứng *có mặt mà không đọc được*
  (journal, ledger, luồng phiên, record hay claim; một journal đọc được mà không phải cái `RUN.json` nêu; một tổ tiên mà
  record nêu nhưng thư mục đã mất) là chi phí chưa xác định mà **không cờ nào chấp nhận**: `aisef run --parent` từ chối
  trước clone, admission và preflight, tổng chi phí là `null`, phần đã biết của từng run còn nguyên (chỉ thị 2026-10-15
  mục 2). Chi tiêu đã biết của dòng dõi tính vào trần của run mới.
- **Claim có thế hệ, quyết định bằng bằng chứng**, lấy trước request provider đầu tiên; child đã bắt đầu không bao giờ bị
  thay thế; thay thế child chưa bắt đầu khi claimant chắc chắn đã mất hoặc khi người vận hành nêu sha256 của claim — lời
  khẳng định ấy thay *claim*, không làm biết chi tiêu của một child mà bằng chứng không đọc được.
- `RUN.started.json` cho phép nối tiếp một lượt bị giết trước khi ghi record. `usage` của mỗi run chỉ đếm luồng phiên của
  nó; `lineage_usage` cộng mỗi run một lần; chi phí của run bị giết không bao giờ `known`.

Đo bằng SIGKILL thật ở điểm đồng bộ xác định cho từng cửa sổ (request: trước khi client chạy / đã gửi chưa có usage / có
usage chưa có result; commit: candidate / merge; append journal: trước write / ghi ngắn / sau write trước fsync / sau
fsync; claim: trước / sau `run.begin`; claimant còn sống / ở máy khác / đã mất; hai run cùng lúc) —
`test_v21_continue_integrity`. **Không đo:** mất điện hay OS sập (cửa sổ trước `fsync` chỉ khác biệt ở đó). Mô hình đe
doạ của anchor: [ANCHOR-THREAT-MODEL.md](ANCHOR-THREAT-MODEL.md).

## ADR-9 — Thí nghiệm: niêm phong trước khi tiêu

Manifest niêm phong, cặp chỉ khác một biến, cánh trực tiếp do harness chụp, evaluator ẩn + quét rò rỉ, replay offline.
Không có lượt trả tiền nào khi chưa có ngân sách duyệt ([EXPERIMENT-PLAN.md](EXPERIMENT-PLAN.md)).

## ADR-10 — Làn phát hành theo phiên bản; lịch sử bằng chứng không bao giờ ghi đè

`release_rc`/`v2_release_gate`/`release_calibration` theo phiên bản pyproject; bản ghi 2.0.0 giữ tên. Nhánh này là
`2.1.0.dev0` (bản build không bao giờ tự nhận là 2.0.0). Bản ghi mới được đánh số (`…-PROBE-CALIBRATIONS-2.json`), không ghi
đè. Các test buộc bản ghi phái sinh vào cây hiện tại (proposal P5, rebind, acceptance C2-P5, kiểm định checker, mutation,
inventory thẩm quyền) **đỏ có chủ đích** tới vòng tái thẩm định 2.1 — xem [STATUS.md](STATUS.md) §4.
