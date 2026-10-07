# AISEF 2.1 — Báo cáo trạng thái (2026-10-06, bản sửa theo yêu cầu nghiệm thu)

**Chưa đủ điều kiện phát hành.** A–E **chưa hoàn thành**: không có cách ly hệ điều hành, không có lượt chạy live nào
(OCR với mô hình thật, developer thật), không có số đo đối chứng, và suite đầy đủ còn đỏ ở các test so bản ghi niêm
phong (§5). Không có gì được push, gắn tag, publish, deploy; không chạy provider trả tiền. Chủ dự án chưa nghiệm thu,
chưa duyệt phát hành, chưa duyệt ngân sách 140 USD — báo cáo này không thay cho những quyết định đó.

Tài liệu đi kèm: [RED-SUITE.md](RED-SUITE.md) (từng test đỏ), [ADR-V2.1.md](ADR-V2.1.md),
[ANCHOR-THREAT-MODEL.md](ANCHOR-THREAT-MODEL.md), [USAGE-2.1.md](USAGE-2.1.md), [decisions/](decisions/) (hồ sơ B-01, B-04,
B-08, B-09, B-10), [STATUS.md](STATUS.md) (phát hiện → sửa, theo từng dòng).

## 1. HEAD và trạng thái từng nhánh

| Nhánh | HEAD | Trạng thái |
|---|---|---|
| `v2.1/foundation` | xem `git log -1` (commit chứa báo cáo này; mã cuối `b72e51e`) | local, chưa push. Gồm hai nhánh chủ đề đã merge: `v21/review` (`181d68e`), `v21/continue` (`872e83c`) |
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
**M5** đã kiểm chứng live (provider thật) · **M6** chưa làm hoặc thực sự bị chặn. Không mục nào đạt M5. "Mức đạt" là mức
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
| F | cách ly Linux tối thiểu | **M6** | §6 | chưa có mã cách ly nào trên nhánh |

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
sử là thật.

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
| claim đã lấy, child chưa bắt đầu | claimant đã mất ⇒ thế hệ mới thay thế **có bằng chứng** (claim cũ giữ nguyên); claimant còn sống hoặc ở máy khác ⇒ từ chối, chỉ thay khi người vận hành nêu sha256 của claim |
| child đã bắt đầu rồi chết | không bao giờ bị thay; dòng dõi nối tiếp từ child |
| hai tiến trình cùng yêu cầu | đúng một lấy được (`O_EXCL`), bên kia không tiêu gì |
| child xong, yêu cầu continue lặp lại | từ chối, chỉ tới child — cũng đo qua CLI thật |

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
| HEAD cuối của 2.1 | 2.1 | chạy sau commit này (một commit không chứa được kết quả suite của chính nó): kết quả và lý do skip nằm trong báo cáo gửi chủ dự án |

Các commit `51f2eb5` … `b72e51e` của 2.1 **chưa có suite đầy đủ riêng**; kết quả của `4fd070a` không đại diện cho chúng.

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

- **Không có cách ly hệ điều hành** (§3). Cách ly Linux tối thiểu chưa làm; phản hồi của tôi bị hệ thống dừng hai lần khi
  soạn phần này, nên không có mã nào trên nhánh. Đã đo môi trường (chưa phải bằng chứng cách ly): host macOS không có backend
  nào; Docker Desktop (server linux/arm64) có Linux guest; trong container `python:3.14-slim-trixie@sha256:3353bb7e…`,
  bwrap 0.12.0 chạy được với uid 1000 (user namespace, network namespace, `--tmp-overlay`) **chỉ khi** container được nới
  `seccomp=unconfined`, `apparmor=unconfined`, `systempaths=unconfined` — tức nới chính ranh giới của container. Chưa có:
  báo cáo user/mount/network/capability/socket và thao tác bị từ chối chứng minh ranh giới.
- Không có lượt live nào: hiệu quả, chất lượng finding, chi phí thật — không biết.
- Anchor chỉ có nghĩa khi bản tin cậy nằm ngoài tầm ghi của developer; hiện chưa có nơi đó.
- Tiến trình con tách session thoát việc dọn dẹp.
- Mất điện / OS sập không được mô phỏng; trên macOS `fsync` không ép cache của ổ.
- Luật neo: một stimulus **mới** bị xếp sai mệnh đề vẫn có thể được neo sai (ADR-7).
- Module mới của 2.1 (`lineage`, `usage`, `review_ocr`, `review_verify`, `bundle_cli`) chưa là mục tiêu mutation.
- Suite chỉ chạy trên macOS; CI Windows/Linux chưa chạy cho 2.1 (chưa push).

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
| B-09 | ngân sách E2 (đề nghị 140 USD) | duyệt / giảm / không | canary nhỏ trước chiến dịch — [hồ sơ](decisions/B-09-CANARY-THEN-CAMPAIGN.md) |
| B-10 | nơi đăng tài liệu công khai | A README tự chứa / B repo docs công khai / C host khác / D public repo | A — [hồ sơ](decisions/B-10-PUBLIC-DOCS.md) |
| F | ranh giới cách ly Linux | (a) container là ranh giới (`--network none`, cap-drop, mount chỉ đọc, user không root), không bwrap lồng; (b) bwrap trong container đã nới seccomp/apparmor; (c) máy/VM Linux riêng | (a), **chưa đo**: không phải nới ranh giới của container; (c) khi cần chạy song song |
| — | nơi giữ anchor tin cậy | commit đã ký / kho append-only / máy khác | commit đã ký trong repo riêng của người vận hành |
