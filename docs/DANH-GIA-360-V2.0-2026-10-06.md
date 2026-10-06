# AISEF 2.0 — Đánh giá 360°

**Ngày**: 2026-10-06 · **Bản mã**: master `f044194` (= 2.0.0 tại tag `v2.0.0` → `ca26313`, cộng tài liệu viết sau
phát hành) · **Bản phát hành**: `aisef 2.0.0` trên PyPI, 2026-10-05T23:49Z

Báo cáo này thay vai trò của [`DANH-GIA-360-2026-09-12.md`](DANH-GIA-360-2026-09-12.md) (viết cho 1.x) cho dòng 2.0.
Cách làm: 11 mặt, mỗi mặt một người đánh giá **chỉ đọc** (không ghi file, không đổi git, không chạy `opencode`,
`aisef run` hay bộ test, không gọi provider) và một người **kiểm chứng đối kháng** mở lại từng bằng chứng được dẫn;
sau đó một người phản biện tìm mâu thuẫn giữa các mặt, và năm câu hỏi còn hở được trả lời riêng — 28 tác tử, 2 173
lệnh công cụ, không lệnh nào vi phạm giới hạn (đã soát transcript). Mọi con số dưới đây đọc từ mã, git hoặc bằng chứng
trong repo tại `f044194`; chỗ nào chưa đo ghi là **chưa đo**. Ba điểm then chốt tôi đo lại tận tay trong phiên này:
cơ chế `.pth` (§3.4), chế độ hiển thị của repo (§3.9) và bộ số liệu kích thước (§2).

> **Giới hạn của chính báo cáo này.** Cả 28 người đánh giá đều là tác tử Claude — cùng họ model đã đồng tác giả
> 486/487 commit của 2.0. Họ đo từ bằng chứng sơ cấp và người kiểm chứng sửa sai cho nhau (mọi người kiểm chứng đều
> hạ hoặc giữ điểm; trung bình 4,8 → 4,45), nhưng điểm mù chung của một họ model không loại trừ được. Một người đọc
> ngoài dự án vẫn là phép kiểm còn thiếu.

---

## 1. Kết luận trong một trang

**Lõi quyết định của 2.0 tốt thật, và hồ sơ trung thực hiếm thấy.** Mỗi sự kiện quyết định có đúng một chỗ ghi; chủ
sở hữu lỗi và quyền chạy lại nằm trong một bảng phân loại do mã cưỡng chế; journal chuỗi băm được kiểm chứng sai
khác 100 000/100 000 vết; kênh phán quyết của probe dùng HMAC, tiến trình riêng, hỏng thì đóng; bản trên PyPI trùng
từng byte với bản RC đã đóng băng và dựng lại được. Thất bại — RC1 bị loại, hai smoke trả tiền không đạt, một lỗ hổng
giới hạn developer — đều được ghi thành phát hiện có mã số, không bị chạy lại cho xanh.

**Nhưng ba vấn đề lớn đang mở:**

1. **Giá trị của 2.0 chưa được chứng minh bằng một lần chạy đạt.** 0 trong 8 lượt chạy live của V2 đạt
   `delivery_verdict PASS`; chỉ một lượt chạy trên đúng bản 2.0.0 (smoke #2: 6/7 story, phát hành nhờ miễn trừ của chủ
   dự án), trên một workload (LedgerLock, đã được dọn còn 4 file), một route, một máy macOS. Con số "59/59, 0 chấp nhận
   sai" là **tự nhất quán** với chính 59 spec của bundle — trong cùng lượt đó review của model tìm ra 5 lỗi thật (tái
   hiện được, precision 5/5), cả 5 vẫn vào `main` vì review chỉ mang tính tham khảo; và developer đã đọc được stimulus
   ẩn trước khi story cuối commit. Không có đối chứng với agent trần, không có đơn giá USD.
2. **Tuyên bố cốt lõi "mã ứng viên không thể điều khiển kênh phán quyết" chỉ đúng trong một lần đánh giá.** Venv của
   probe nằm trong thư mục chạy và ghi được; controller chạy với `-I -B` nhưng không `-S`, nên một file `.pth` do mã ứng
   viên (hoặc phiên developer) cài vào sẽ chạy bên trong controller đang giữ khoá HMAC — tôi đã tái hiện cơ chế này
   (§3.4). Developer chạy với HOME, PATH, cấu hình OpenCode toàn cục và mạng của người vận hành; lỗ hổng
   DEVELOPER-CONFINEMENT-GAP-001 tái diễn ngay trong smoke phát hành mà hồ sơ không ghi.
3. **Người ngoài không dùng được.** Không có công cụ soạn bundle (bundle thật duy nhất: 149 726 byte, 59 contract, dựng
   bằng ≥3 970 dòng script nội bộ không ship); bundle gãy khi probe đổi một byte (kể cả docstring); repo GitHub hiện
   **private** nên mọi liên kết công khai trả 404; trang PyPI 2.0.0 vẫn tả 1.x; không có đường phát hành bản vá 2.0.1
   (công cụ phát hành cứng `RC2`/`2.0.0`). (Repo private là chủ ý — chủ dự án đặt ngày 2026-10-06; việc còn lại là
   xử lý các liên kết công khai đang trỏ vào nó.)

**Ưu tiên một câu**: phát hành 2.0.1 để vá lỗ `.pth` và nói đúng sự thật trên PyPI, rồi dồn 2.1 vào **sự thật sản
phẩm** — người khác soạn được bundle, một điểm dữ liệu thứ hai có đối chứng và có giá tiền — **trước** khi thêm bất kỳ
tầng kiểm chứng offline nào; độ sâu kiểm chứng kernel đã đi trước xa so với bằng chứng live có thể biện minh.

| Mặt | Mức | Điểm (sau kiểm chứng) |
|---|---|---|
| 3.1 Kiến trúc kernel | **khá** | 6 / 10 |
| 3.2 Chất lượng mã | trung bình (từng hàm: tốt; khả năng sửa đổi: kém) | 5 |
| 3.3 Độ chặt của kiểm chứng | trung bình | 5 |
| 3.4 Bảo mật và cách ly | trung bình | 4,5 |
| 3.5 Hiệu quả thực tế và kinh tế | **yếu** | 3 |
| 3.6 Trải nghiệm người dùng | **yếu** | 3 |
| 3.7 Phát hành và vận hành | trung bình | 5,5 |
| 3.8 Quy trình và chi phí làm ra 2.0 | trung bình | 5 |
| 3.9 Thị trường | **yếu** | 3 |
| 3.10 Rủi ro, nợ kỹ thuật, lộ trình | trung bình | 4 |
| 3.11 Độ chính xác tài liệu và tuyên bố công khai | trung bình | 5 |
| **Trung bình** | | **4,45** |

---

## 2. Số liệu nền

| Hạng mục | Giá trị | Nguồn |
|---|---|---|
| Kernel `aisef2/` | **14 143 dòng · 85 file** (probe 4 173; journal 1 857; runtime 1 597; app 1 370; quality 1 244; orchestrate 1 171) | `find aisef2 -name '*.py' \| xargs cat \| wc -l` |
| Kiểm thử V2 `tests/v2/` | 43 075 dòng · 195 file (75 là fixture) — **3,05×** kernel | như trên |
| Công cụ kiểm chứng `validation/` | 35 041 dòng (v2 12 176; qualification 18 401) — 2,48× kernel | như trên |
| Bằng chứng `closure-evidence/v2/` | **1 244 file · 144,3 MiB** (≈198× số byte kernel) | `du`, `find` |
| 1.x vẫn ship trong wheel | `aisef/` 41 073 dòng = 74 % Python được ship; **33/34** lệnh con là V1 | `aisef --help`, `parser.py` |
| Lịch sử | RFC 2026-09-21 → PyPI 2026-10-05: **≈15 ngày**; 487 commit kể từ 1.7.6, 74 commit chạm kernel | `git log` |
| Tác giả | **487/487** commit cùng một danh tính; 486 có trailer đồng tác giả Claude (3 thế hệ model) | `git log --format=%an` |
| Bộ test trên RC2 (hermetic) | **5 454 test, 0 lỗi, 80 bỏ qua**; CI: ubuntu 3.11–3.14 5 454 (90 skip), macOS 5 454 (92), Windows 5 451 (173) | `s5-rc2/suite-hermetic-1565bcc.txt`, `production/ci/joblogs/` |
| Trong đó test V2 | 1 714 / 5 406 hàm `test_` tĩnh (32 %); 581 hàm V2 nằm trong file đọc bằng chứng/harness | `grep 'def test_'` |
| Mutation S2 (phạm vi phát hành) | 261 target · **6 463/6 463** — chỉ **5** target đo lại ở head cuối, 256 dùng lại sau "chứng minh cơ học" | `S2-MUTATION-SUMMARY.json` |
| Mutation tích luỹ (Q2) | 701 target · 18 297 mutant · 10 sống (đều ở `tests/v2/refmodel`, đã kiểm duyệt) · 216/721 hàm kernel không có target | `Q0-Q3-RC2/Q2/*.json` |
| Q4 (khác biệt so với mô hình tham chiếu) | 100 000/100 000 — **cùng generator, cùng seed, cùng 5 431 248 sự kiện** ở C2-final, RC1, RC2; journal không đổi từ `c11615a` | `Q4-*/DIFFERENTIAL.json` |
| Q5 (tái hiện corpus) | 12/12 — 12 fixture, 31 lời gọi model **theo kịch bản** | `Q5-RC2/` |
| Lượt chạy live V2 | **8 sự kiện, 0 PASS**; 5 có phiên model; 1 trên bản 2.0.0 | §3.5 |
| Smoke #2 (bản 2.0.0) | 6/7 commit (1 không cần developer) · ProductProof 66/67 · acceptance 59/59 · **RELEASE_SMOKE_PASS NO**, miễn trừ | `smoke-2/RESULT.json` |
| Chi tiêu smoke #2 | 18 812 251 input (91,4 % cache) · 313 380 output (78 % reasoning) · 270 lượt · 15 phiên · 3 832 s | `smoke-2/run-1/RUN.json` |
| Chi tiêu live V2 cộng dồn | 298 080 321 input · 1 623 191 output · 3 028 bước | session logs |
| Giá tiền | **chưa đo** — mọi bước `cost = 0`, không có bảng giá | — |
| Bundle thật duy nhất | 149 726 byte · 15 requirement · 59 contract · 59 approval · 67 obligation · 194 niêm phong | `LEDGERLOCK-PROJECT.json` |
| Độ phủ requirement của contract | **30/54 mệnh đề** (55,6 %); 16 mệnh đề không thể cưỡng chế đầy đủ | `p10_contracts.py:430-533` |
| Mutant độc lập (26, viết trước contract) | **8 sống sót qua cả 59 contract** (30,8 %) | `P0` mutant set |
| Backlog 2.1 | 38 mục: 1 high, 11–12 medium, 24 low; **19/38** không có reproducer | `docs/v2/V2.1-BACKLOG.md` |
| Repo GitHub | **PRIVATE** — chủ dự án đặt 2026-10-06; `github.com/nghinh/aisef`, API, raw: 404 khi không đăng nhập | `gh repo view`, curl |
| Tải PyPI | 7 963/tháng (đến 2026-10-04, trước 2.0.0; 91 % rơi vào ngày phát hành) | pypistats |
| Người dùng ngoài | **0** | — |

---

## 3. Đánh giá mười một mặt

### 3.1 Kiến trúc kernel — **khá** (6/10)

**Mạnh.**
- **Một đường quyết định duy nhất**: `aisef run` → `app/cli.run` → `app/run.execute` →
  `orchestrate/story_runner.run_story`; `story/commit`, `story/rollback`, `failure/observed`, `gate/decision`,
  `proof/verified` mỗi loại đúng một chỗ ghi.
- **Tách mặt phẳng giữ được trong mã**: `product/` là lá (chỉ import `arch` và `errors`); spec không mang sự thật của
  plan; `semantic_hash` bỏ qua văn xuôi và id. V2 không import gì từ V1; V1 gọi V2 qua đúng một import lười.
- **Sở hữu lỗi cưỡng chế bằng máy**: 22 mã lỗi, 7 chủ; quyền chạy lại chỉ sống trong bảng phân loại; journal từ chối
  giá trị do nơi gọi tự đặt.
- **Mặt phẳng ghi chép tốt**: append-only, fsync, chuỗi băm, 6 projection là fold thuần, không đọc đồng hồ.

**Yếu.**
- **Danh tính probe = băm byte mã nguồn** (kể cả docstring): mọi plan bị hàn vào đúng byte của kernel; vá một chú
  thích trong `probe/protocol.py` là mọi bundle của người dùng bị từ chối, và công cụ rebind không được ship. Băm lại
  bỏ sót `runtime/process_range.py`, `range_anchor.py` — mã quyết định quan sát có thể đổi mà danh tính không đổi.
- **Lỗ định tuyến ở mức thiết kế**: obligation PRESERVE của story trước chỉ được chứng minh **sau merge**, nơi mọi thất
  bại thuộc INTEGRATION, không chạy lại. Trong runner tuần tự, cây đã merge **bằng** cây ứng viên — nên mọi lỗi sau
  merge đều tái hiện được ở bước ứng viên, nơi nó lẽ ra là lỗi DEVELOPER có phản hồi. (Smoke #2 không phải hồi quy do
  developer: nguyên nhân là spec bắt nhầm docstring, V21-37; lỗ định tuyến là V21-38, riêng biệt.)
- **Bị "đóng băng bởi bằng chứng"**: writer journal copy-paste (format2/format3 trùng 0,92), 5 bản `_probe_digest()`
  chép nhau, probe đang dùng phụ thuộc 25 hàm private của probe đã bị thay thế; ≈1 100 dòng ship nhưng không chạm tới
  được từ `aisef run` (`cohort`, `invariants`, `journal/writer`, `runtime/repair`).
- **Lỗi môi trường thoát khỏi bảng phân loại**: `InvariantError` là `BaseException` và bị ném cho cả lỗi git thường
  (`workspace.py:157-159`), trong khi biên của app chỉ bắt `Exception` — một lỗi git thoáng qua làm hỏng cả lượt chạy
  thay vì thành lỗi ENVIRONMENT có thể chạy lại.
- `app/` (vỏ sản phẩm, 1 370 dòng) ra đời 2026-10-03, ≈53 giờ trước khi RC2 đóng băng, và nằm ngoài RFC; không có
  đường resume (`--out` phải mới tinh), nên cơ chế §19/§20.2 của kernel không bao giờ chạy.

### 3.2 Chất lượng mã — **trung bình** (5/10; từng hàm ≈7, khả năng sửa đổi ≈3)

**Mạnh.** 735 hàm, trung vị 6 dòng; chú thích kiểu 86 % tham số / 96 % giá trị trả về; 0 `type: ignore`, 0 TODO,
0 `assert`; 38 lớp exception có kiểu; ràng buộc kiến trúc được mã hoá thành luật tĩnh có hiệu chuẩn
(`NO_PROSE_CONTROL`, `RETRYABLE_ONLY_IN_TAXONOMY`…); stdlib-only giữ được ở kernel, test và harness.

**Yếu.**
- **Ràng buộc bằng chứng theo cả file**: 65/85 file (94,6 % số dòng kernel) bị digest sha256 nguyên file trong bản ghi
  mutation; sửa một byte trong `cli_invocation.py` làm vô hiệu 85 target / 1 763 mutant. Bản vá RC2 38 dòng tốn
  **3 giờ 42 phút** đến S5 PASS và ≈12,7 giờ đến PyPI (gồm smoke trả tiền), kèm 756 679 dòng bằng chứng mới (81 % là
  chunk Q4 sinh máy).
- **1 011 dòng Python nằm trong hằng chuỗi** (chương trình con của probe) — lint và kiểu không thấy; `_UNITTEST_RUNNER`
  (129 dòng) không có cả mutation target.
- **Điểm nóng độ phức tạp** ở đúng đường hay đổi nhất: `story_runner._attempt` 170 dòng (C901 31; backlog vẫn ghi 29),
  `app/run.execute` 120 dòng; tham số `run` trung tâm không có kiểu ở 33/34 chỗ, 58 truy cập thuộc tính private.
- Cổng lint là di sản V1 (F/B/E9); lời hứa "mở thêm từng họ luật sau 1.3.0" chưa bao giờ thực hiện; 247 dòng kernel
  quá 120 ký tự; 665 `noqa` vô dụng; harness có 165 file chèn `sys.path`.

### 3.3 Độ chặt của kiểm chứng — **trung bình** (5/10)

**Mạnh.** Mutation fail-closed và gắn digest (0/701 bản ghi lệch với cây phát hành); mỗi checker Q0 phải bác được một
fixture xấu và một bản đột biến luôn-PASS của chính nó; Q4 cấm mô hình tham chiếu import kernel và so ba cách; bộ test
chạy hermetic trên đúng RC với kiểm tra rò tiến trình; chính công cụ kiểm chứng cũng có 62 target mutation.

**Yếu — phần lớn là kiểm mã với chính nó.**
- **Xanh offline đã hai lần không đoán được hành vi live**: RC1 qua suite, CI, Q0–Q5, mutation (preflight.run 119/119
  bị giết) và diễn tập offline — rồi chết ở preflight sau 12,1 giây vì thiếu `stream:false` (một quirk dự án **đã biết
  và đã xử lý** ở harness V1, `provider_preflight.py:69`). Diễn tập RC2 commit STORY-02-01; lượt live rollback nó.
- **Vỏ sản phẩm `aisef2/app` nằm ngoài mọi bậc hành vi Q1–Q5**; Q5 chạy `orchestrate` với model theo kịch bản.
- **Q4 ở RC1/RC2 là phát lại**: cùng generator, cùng seed, journal không đổi — nó xác nhận tính tất định, không tìm
  được gì mới; generator dùng chính `encode/link` của kernel; mô hình tham chiếu chưa từng chạy trên journal thật.
- **Toán tử mutation hẹp**: không xoá câu lệnh, không đổi số/biên, không bỏ keyword argument, không đổi handler; 30 %
  mutant S2 là "chuỗi rỗng"; mutation về bản chất không phát hiện được **hành vi bị thiếu** — đúng lớp lỗi của
  `stream:false`.
- **Kiểm định spec chỉ hỏi "spec có thể fail không", không hỏi "spec có bác nhầm không"**: S-10-a được QUALIFIED trên
  một bản tham chiếu + một mutant, rồi bác nhầm một story đúng.
- Độc lập của mô hình tham chiếu chỉ ở mức import: cùng danh tính git, cùng họ model, sửa cùng commit với projection.
- 80/90/92/173 test bỏ qua không được liệt kê ở đâu (CI chạy `-q`); một số chỉ chạy trên máy của tác giả.
- Q0–Q3 chạy Linux + Windows, **không có macOS** — nền tảng duy nhất từng chạy live.

### 3.4 Bảo mật và cách ly — **trung bình** (4,5/10)

**Mạnh.** Mỗi lần đánh giá có khoá HMAC 256 bit và nonce mới; controller đọc rồi xoá khoá khỏi `request.json` trước
khi tiến trình đối tượng tồn tại; stdout/stderr của đối tượng bị chuyển hướng nên không tự in được dòng giao thức;
giả mạo/cắt cụt/viết lại đều kết thúc HARNESS_FAILED/REFUTED/INDETERMINATE, không bao giờ SATISFIED (20 test tấn
công). Cấu hình git được cách ly khỏi mọi thứ developer có thể cài. Settings không có mặc định; chuỗi cung ứng mạnh
(0 phụ thuộc, OIDC, byte trên PyPI = RC đóng băng, có attestation PEP 740). Quét 1 244 file bằng chứng: không thấy bí
mật theo các định dạng đã biết.

**Yếu.**
- **Lỗ `.pth` qua venv probe (mức cao).** `app/run.py:116-123` tạo venv probe trong thư mục chạy, ghi được bởi chính
  người dùng; mọi controller chạy `[interpreter, "-I", "-B", …]` (ví dụ `cli_invocation.py:854`) — `-I` không tắt
  `site`, nên file `.pth` trong `site-packages` của venv **được thực thi**. Test của developer chạy trên đúng
  interpreter đó (`story_runner.py:257-259`), và controller của implementer và verifier dùng chung nó
  (`proof.py:89→92`). Tôi tái hiện trong scratchpad: venv dựng y như `run.py`, một `.pth` ghi file đánh dấu, chạy
  `python -I -B -X utf8=1 -c pass` → **file đánh dấu xuất hiện**; thêm `-S` → không. Backlog xếp mục này (V21-28)
  "low, not measured" — cần nâng lên high. Chưa đo một vụ giả mạo end-to-end trong `aisef run` thật.
- **Developer không bị giới hạn.** Client nhận HOME, PATH, XDG thật của người vận hành, plugin và MCP toàn cục của
  OpenCode (110/195 lệnh bash trong smoke #2 đi qua plugin `rtk` của người vận hành), và mạng; không có mã nào hạn chế
  mạng. Trong smoke #2, 4 phiên đã ra ngoài workspace (69 lời gọi): đọc scratch của probe, `protocol.log`, worktree
  của verifier, journal đang chạy, bundle có stimulus ẩn và mã nguồn kernel đã cài — **trước** khi STORY-04-02 commit.
  Hồ sơ phát hành không ghi lần tái diễn này của DEVELOPER-CONFINEMENT-GAP-001.
- **Toàn vẹn bằng chứng giả định không có kẻ ghi cùng người dùng**: chuỗi băm không khoá, genesis toàn số 0; `RUN.json`
  nằm cùng thư mục ghi được; `--verify` lấy `budget_stop`, `story_errors` từ `RUN.json` (V21-30: sửa riêng `RUN.json`
  vẫn VERIFIED).
- **Che bí mật hẹp**: chỉ khớp chính xác giá trị ≥8 ký tự và chạy ngoài `finally` — một lần ngắt làm luồng phiên không
  được che.
- **Cổng con người khi phát hành là mềm**: môi trường `pypi` không có người duyệt bắt buộc (OBS-PUB-1); "uỷ quyền của
  chủ dự án" là một chuỗi JSON trong repo; 0/30 action bên ngoài được ghim SHA, action publish chạy theo nhánh di động
  với `id-token: write`; `conformance.yml` cài gói npm không ghim trong môi trường có `ANTHROPIC_API_KEY`.
- Nhỏ: kiểm tra endpoint bằng tiền tố chuỗi (`http://localhost.evil.example` lọt); preflight đi theo redirect và mang
  theo header Authorization; trên macOS một tiến trình double-fork có thể thoát khỏi vùng quản lý (suy ra từ mã, chưa
  đo).

### 3.5 Hiệu quả thực tế và kinh tế — **yếu** (3/10)

**Mạnh.** Smoke #2 bắt đầu từ chỉ có requirements và giao 6/7 story trên model thật; chi tiêu được kế toán đầy đủ và
dựng lại được (`--verify` VERIFIED, 1 834 sự kiện, 0 chi tiêu không đối soát); story đã thoả sẵn không phải trả tiền
developer lần hai.

**Yếu.**
- **Bảng lượt chạy chuẩn** — 8 sự kiện, 0 PASS:

  | Lượt | Route | Kết quả |
  |---|---|---|
  | cycle-1 P10 ×2 | 9router/mycombo | NOT_REACHED (plan không được nhận, 0 lời gọi model) |
  | cycle-2 attempt 1 | 9router/mycombo | mất bản ghi (bộ quét bí mật của harness báo nhầm); 99,2 M input |
  | attempt 2 | 9router/mycombo | FAIL, 3/9 commit, 96,9 M input |
  | attempt 3 | deepseek-v4-pro (attested) | FAIL, 4/7, acceptance 19/59 |
  | attempt 4 | deepseek-v4-pro | FAIL, 4/7, acceptance 51/59; NO_GO |
  | smoke #1 (RC1, bị loại) | deepseek-v4-pro | dừng ở preflight sau 12,1 s (lỗi của chính preflight) |
  | smoke #2 (RC2 = 2.0.0) | deepseek-v4-pro | FAIL, 6/7, miễn trừ → phát hành |

- **n = 1**: một workload, một model, một client (OpenCode 1.18.31), một router, macOS; workload phát hành **chính là**
  workload phát triển (contract BC-V22-* lặp qua cycle 2 và 4 attempt), và đã được dọn từ 1 353 file còn 4 sau khi hai
  lần chạy trên repo thật thất bại 4/7 vì văn xuôi V1 cũ (V21-03 vẫn mở).
- **"0 chấp nhận sai" là tự nhất quán**: acceptance chạy lại đúng 59 spec của bundle bằng đúng probe đó. Review của
  model trong lượt đó tìm 5 lỗi (repair-tail/snapshot trên file thiếu thoát 0 thay vì 3; crash UnicodeDecodeError,
  ValueError, KeyError) — **cả 5 tái hiện được trên `main` cuối**, precision 5/5, và đều bị chuyển thành "advisory".
  Contract chỉ phủ 30/54 mệnh đề của requirements; 8/26 mutant độc lập sống qua cả 59 contract.
- **Không có đối chứng**: không có nhánh agent trần cho V2; dữ liệu đối chứng duy nhất (V1, C-1 và C-2) cho thấy không
  hơn mà tốn ≈1,5× token.
- **Không quy được ra tiền**: mọi bước giá 0; "provider_requests" đếm **phiên** (19), không đếm lời gọi HTTP (270
  lượt). 97 % input không cache của toàn chiến dịch rơi vào hai lượt thất bại trên alias `mycombo` (không cache).
- **Lãng phí tập trung**: STORY-04-02 ăn 60 % input; một phiên chạm trần 80 lượt, đốt 7,0 M input mà không sửa gì —
  vì phản hồi giấu stimulus nên developer quay sang "dịch ngược" framework (đọc mã kernel, bundle, journal); review
  tốn 1,79 M input cho một story không có việc.

### 3.6 Trải nghiệm người dùng — **yếu** (3/10)

**Mạnh.** Settings tường minh, từ chối có thông điệp cụ thể; `aisef run --check` là cổng offline thật (chín phép kiểm
duyệt, niêm phong, git, baseline, sha256 của requirements); mã thoát có tài liệu; wheel cài sạch đã chạy được
`--check/run/--verify` offline với client giả.

**Yếu.**
- **Không có đường soạn bundle được hỗ trợ**: không CLI, không schema, không template, không ví dụ ship; ngữ pháp
  stimulus/observable của 18 lớp quan sát chỉ có trong docstring của probe (3 152 dòng). Một bundle 1 story tối thiểu
  (≈2 KB) dựng được — nhưng chỉ bằng constructor nội bộ, theo công thức trong một file test không ship.
  Ước tính thời gian đến lần chạy đầu cho người ngoài giỏi: ≈1 ngày cho đồ chơi 1 story nếu tìm ra công thức; vài
  tuần cho dự án thật (**ước tính**, chưa đo).
- **Bộ nạp không chịu được đầu vào sai**: 5/8 kiểu sai thoát ra thành traceback với mã 1 (trùng mã FAIL); 3 lỗi đọc
  sai âm thầm (`product_roots: "app"` thành `('a','p','p')`).
- **`--check` báo sai lý do**: repo có một khoá git config phổ biến (VS Code, git-lfs, `core.hooksPath`…) bị báo "không
  chứa baseline" thay vì lý do thật (6/6 khoá thử).
- **CLI lẫn lộn**: 33/34 lệnh là V1; `plan`, `verify`, `doctor`, `--project` mang nghĩa V1 trùng tên khái niệm V2;
  `aisef doctor` trên máy sạch thoát 2 (OBS-PUB-2).
- **Phạm vi hẹp không nói từ đầu**: đối tượng là module Python, probe chỉ stdlib, test của developer chỉ `unittest`,
  chỉ OpenCode (một phiên bản từng chạy), provider phải có `/models`, phản hồi không stream và trả đúng tên model.
- Trang PyPI 2.0.0 tả 1.x (tóm tắt "input is docs/requirements.md", 19/19 liên kết tương đối, không có classifier).

### 3.7 Phát hành và vận hành — **trung bình** (5,5/10)

**Mạnh.** Bản dựng tái lập đã được đo nhiều lần (RC2 staging, rebuild, release run, tải về từ PyPI — cùng digest);
chỉ đúng byte của RC đóng băng mới publish được (`sha256sum -c` + `release_rc --verify-dist`); trusted publishing;
cài sạch trên Linux và Windows; sự cố runner được ghi kèm id, không chạy lại cho xanh; `RUN.json` ghi trong `finally`.

**Yếu.**
- **Công cụ phát hành dùng một lần**: `release_rc.py:37-39` cứng `RC="RC2"`, `VERSION="2.0.0"`; không có quy trình
  vá, hotfix hay yank (yank 2.0.0 sẽ khiến `pip install aisef` về 1.7.6, nơi `aisef run` là V1).
- **Đường găng CI**: job Windows 68,4 phút trên 69,1 phút của cả lượt phát hành; không job nào có `timeout-minutes`;
  hai sự cố runner trong ba ngày.
- **Vận hành gần như mù**: một lượt 64 phút in ra 814 byte (chỉ JSON cuối); không có tiến độ, không resume; `--verify`
  chứng minh nhất quán nội bộ, không chứng minh tính xác thực.
- Kiểm tra sau phát hành chỉ chạy trên macOS và không chạy đường sản phẩm (`aisef run --check/run/--verify`) từ bản
  cài PyPI.
- Tài liệu phát hành cũ: `RELEASE-PROCESS.md:31` vẫn nói phiên bản "stays 1.7.6", `:104` nói cổng "fails today".

### 3.8 Quy trình và chi phí làm ra 2.0 — **trung bình** (5/10)

**Mạnh.** Mọi quyết định truy được về bản ghi có ngày và digest; kết quả xấu được ghi như kết quả (NO_GO, RC bị loại,
smoke thất bại); chính sách "không chạy lại, phân loại mọi thất bại" đã bắt được một lỗi kernel phán sai tiềm ẩn
(P7-FINDING-001); kiểm toán trước khi viết mã đã dừng đúng chỗ (WP-6.2 → V2-005); review đối kháng trước RC tìm ra 3
blocker mới; quy trình tự sửa tuyên bố sai của chính nó công khai (S2-VERIFY-1/2, S6-LINT-1).

**Yếu.**
- **Không cân xứng**: bằng chứng ≈198× số byte kernel; trong 368 commit kể từ RFC: kernel 74, test 189, harness 196,
  bằng chứng 260. Cổng nặng nhất (C2: 15 578 mutant, Q4 100k) ký "Problems: none" cho một ứng viên **chưa có vỏ sản
  phẩm** (B12) và có kênh phán quyết giả mạo được (B1) — hai blocker nghiêm trọng chỉ lộ ra hai ngày sau.
- **Luật cứng bị nới khi nó cắn**: "single paid run" → "one attempt only" → "exactly one smoke" → thêm smoke #2 → miễn
  trừ smoke #2; G7 trượt 4 tiêu chí; hiến chương không có điều khoản miễn trừ.
- **Chuỗi uỷ quyền phát hành có kẽ hở**: RELEASE-DECISIONS seq 3 ghi rõ tạo tag và duyệt `pypi` vẫn là việc của chủ dự
  án; tag được tạo theo phán quyết "FINAL RELEASE EXECUTION" chỉ được trích trong bản ghi production, chưa vào sổ
  append-only.
- **Công cụ đã gây hại máy người vận hành**: SIGKILL 170 tiến trình người dùng (Dock, Finder, Chrome) ở P4; mutant chạy
  client thật 14 lần ở S2.
- **Bus factor = 1**: một con người, một danh tính commit; phán quyết trước hiến chương chỉ còn là tiêu đề commit
  (V21-16); "append-only" từng bị sửa tại chỗ (b6f0233, 7b85df9); agent từng phá một điều cấm của hiến chương (OBS-S4-1).

### 3.9 Thị trường — **yếu** (3/10)

**Mạnh.** Khác biệt kỹ thuật có thật: sự thật sản phẩm từ contract do người duyệt, kiểm bằng probe tất định do harness
sở hữu, qua kênh mã ứng viên không giả được (trong một lần đánh giá), và một journal dựng lại được phán quyết; 0 phụ
thuộc, MIT, byte tái lập — hợp với người mua chú trọng kiểm toán; không khoá vào một hãng model.

**Yếu.**
- **Repo `nghinh/aisef` đang PRIVATE — do chủ dự án đặt ngày 2026-10-06** (đo: `gh repo view` → `PRIVATE`; HTML, API,
  raw đều 404 khi không đăng nhập; không tác tử nào đổi nó). Hệ quả cần xử lý: mọi liên kết "View on GitHub", "Docs",
  "Release evidence" trên aisef.io, salekit và trang PyPI đang trỏ vào 404, và luận điểm "tự kiểm chứng lấy" không
  kiểm được từ bên ngoài cho tới khi bằng chứng được công bố ở nơi khác.
- **Không có tín hiệu chấp nhận**: 0 người dùng ngoài; lượt tải theo sự kiện phát hành (27 lượt trong 9 ngày không phát
  hành); trang PyPI 2.0.0 tả 1.x.
- **Bảng so sánh đối thủ trong salekit không có nguồn**: 36/44 ô "No", 0 trích dẫn; một số ô bị tài liệu công khai của
  đối thủ phản bác (theo người đánh giá có mạng; người kiểm chứng không lặp lại được offline).
- **Gánh nặng soạn bundle**: ≈8,4 contract cho mỗi story, viết tay; phạm vi hẹp (OpenCode, Python, probe stdlib) loại
  phần lớn đội dùng Claude Code/Codex/Cursor và phần lớn dự án Python có phụ thuộc.
- Landing hiển thị `delivery_verdict PASS` mẫu — chưa lượt live nào tạo ra nó.

### 3.10 Rủi ro, nợ kỹ thuật, lộ trình — **trung bình** (4/10)

**Mạnh.** Nợ được ghi kỹ (38 mục, cột reproducer, đường dẫn bị ảnh hưởng, luật phát hành); V2 tách khỏi V1 ở mức mã
(0 import) nên tách V1 ra là rẻ; nhánh treo chỉ có 3, mỗi nhánh 1 commit, không chạm kernel đã ship.

**Yếu.**
- **Backlog thiếu đúng các mục chặn việc dùng**: soạn bundle, tương thích bundle qua phiên bản, brownfield, route thứ
  hai, chạy live Linux/Windows — 0/38 mục. Backlog không có ưu tiên, công sức hay người phụ trách.
- **Xếp hạng sai**: V21-28 (`.pth`) "low" (§3.4); câu "mỗi mục đều có reproducer" sai — 19/38 không có.
- **Nâng cấp sẽ làm gãy mọi bundle**: sửa V21-37 cần đổi probe ⇒ đổi spec id ⇒ mọi plan phải rebind.
- **Phụ thuộc ngoài không có phiên bản**: định dạng sự kiện JSON của OpenCode được phân tích tay; mới chỉ một phiên bản
  OpenCode, một router.
- Cấu hình duy nhất từng chạy live (macOS + Python 3.14.7) không có trong ma trận CI (macOS chỉ 3.12).
- Workload đánh giá duy nhất đã "lộ đề": stimulus ẩn của LedgerLock đã commit công khai trong cây phát hành.

### 3.11 Độ chính xác tài liệu và tuyên bố công khai — **trung bình** (5/10)

**Mạnh.** **Mọi con số tiêu đề khớp đúng bản ghi sơ cấp, không làm tròn lên** (5 454; ma trận CI; 261 · 6 463/6 463;
Q0–Q3; Q4 100 000; Q5 12/12; 7 story, 67 obligation, 59/59, 6/7); các đếm cấu trúc (chín phép kiểm duyệt, chín bất
biến, bảy chủ lỗi, bốn loại probe) đúng trong mã; mọi liên kết tương đối trong README/USAGE đều trỏ đúng.

**Yếu — khoảng một phần tư tuyên bố cơ chế sai hoặc thiếu ngữ cảnh** (≈55 tuyên bố: 26 đúng, 15 sai, 4 không có căn
cứ, 10 đúng nhưng gây hiểu lầm). Phần lớn nằm trong tài liệu viết sau phát hành (README, README.vi, landing, salekit,
`USAGE.vi.md`) — xem §4, đã sửa trong cùng commit với báo cáo này. Trang PyPI và metadata của 2.0.0 không sửa được nếu
không phát hành bản mới; repo không có file `LICENSE` dù khai "MIT".

---

## 4. Tuyên bố công khai đã sửa trong phiên này

| Tuyên bố cũ | Sự thật (bằng chứng) | Sửa thành |
|---|---|---|
| developer sửa mã "inside a confined workspace" | chạy với HOME/PATH/XDG, plugin, MCP, mạng của người vận hành; smoke #2 đọc ra ngoài workspace (§3.4) | nói rõ không giới hạn; thêm vào giới hạn đã biết (V21-02) |
| `--verify` dựng lại "từ journal mà thôi" | `verify.py:41-44` lấy `story_outcomes`, `budget_stop`, `story_errors` từ `RUN.json` (V21-30) | "kiểm `RUN.json` đối chiếu journal chuỗi băm, dựng lại verdict, sổ ProductProof, `main` cuối" |
| Preservation: "mọi hành vi story trước đã chứng minh được chứng minh lại" | `merge.py:38-51` chỉ lấy obligation PRESERVE | "obligation của chính story và PRESERVE của các story đã commit" |
| mã ứng viên "không thể tự chế kết quả probe" | đúng trong một lần đánh giá; `.pth` vào venv chung vượt qua được (§3.4) | giới hạn phạm vi + nêu lỗ đã biết, vá ở 2.0.1 |
| "no incorrect code reached the delivered product" | 5 lỗi review tìm thấy, tái hiện được, đã vào `main` (§3.5) | "không mã nào trượt một trong 59 spec vào `main`; 5 lỗi ngoài spec do review tìm thấy đã ship" |
| "0 false acceptances" (không phạm vi) | so với chính 59 spec của bundle | thêm "so với 59 spec của chính bundle" |
| dòng smoke ghi ✓ như một PASS | `RELEASE_SMOKE_PASS NO`, delivery FAIL, 4/9 ngưỡng trượt, miễn trừ | ghi FAIL + miễn trừ |
| "0 survivors" (mutation) | 5/261 target đo lại ở head cuối, 256 dùng lại | thêm phạm vi |
| "a reproducer for every item" | 19/38 mục không có | "each with its reproducer status" |
| probe "one-token" | `max_tokens` 16 | "tiny (≤16 tokens)" |
| "live run claimed on Linux and macOS" | mọi lượt live đều trên macOS; Linux chỉ có client giả trong CI | "supported on Linux and macOS; live runs so far on macOS" |
| "The model you declared is the model that answers" | so tên model tự báo **một lần** ở preflight | thêm "checked at preflight" |
| mẫu CLI `delivery_verdict PASS` | chưa lượt live nào đạt | ghi "illustrative" |
| salekit: "No other framework ties verification to a frozen candidate" | không có nguồn | bỏ câu; bảng so sánh ghi rõ chưa có nguồn |

**Chưa sửa (cần bản phát hành mới hoặc quyết định của chủ dự án)**: trang PyPI 2.0.0, file `LICENSE`, các liên kết
GitHub trên trang công khai (repo đã private), nguồn cho từng ô trong bảng so sánh của salekit.

---

## 5. Việc còn tồn tại, xếp theo mức

**P0 — trước khi có người dùng thứ nhất (2.0.1)**

| # | Việc | Công sức | Vì sao |
|---|---|---|---|
| 1 | Chạy controller và test runner với `-S` (hoặc băm cây venv trước mỗi probe; venv riêng cho test của developer) | nhỏ + mutation có mục tiêu | đóng cơ chế duy nhất đã đo để mã ứng viên chạm kênh phán quyết (§3.4) |
| 2 | Trang PyPI đúng 2.0: README V2 làm long description, liên kết tuyệt đối, summary/classifier, thêm `LICENSE` | vài giờ + một lượt phát hành | trang công khai duy nhất đang hoạt động nói sai sản phẩm |
| 3 | Làn vá 2.0.x: tham số hoá `release_rc.py`/`v2_release_gate.py` theo phiên bản; runbook vá (3 tầng: tài liệu / mã ngoài kernel / kernel) và runbook yank | 1–2 ngày | hiện không phát hành nổi 2.0.1 nếu không sửa công cụ |
| 4 | Người duyệt bắt buộc cho môi trường `pypi`, bảo vệ tag `v*`, ghim SHA mọi action; ghi phán quyết "FINAL RELEASE EXECUTION" vào RELEASE-DECISIONS (seq 4) | < 1 giờ + quyết định của chủ dự án | cổng con người hiện là chuỗi JSON (§3.7, §3.8) |
| 5 | Repo đã được đặt private (chủ ý): gỡ hoặc thay mọi liên kết GitHub trên aisef.io, salekit và `project.urls` của PyPI; nếu muốn giữ luận điểm "tự kiểm chứng", công bố báo cáo phát hành và bằng chứng tóm tắt ở nơi công khai | giờ | mọi liên kết công khai đang 404 (§3.9) |

**P1 — 2.1, sự thật sản phẩm**

| # | Việc | Công sức |
|---|---|---|
| 6 | V21-37 + V21-38 cùng lúc: tiêu chí import theo AST; chứng minh PRESERVE của story trước **ở bước ứng viên** (lỗi DEVELOPER, có phản hồi) | M |
| 7 | Công cụ bundle: API công khai + `aisef bundle init/seal/lint/rebind`, ví dụ ship kèm, tài liệu ngữ pháp contract cho 18 lớp quan sát; danh tính probe = phiên bản + băm AST không docstring | L |
| 8 | Chính sách review: không chặn, nhưng **đưa phát hiện thành phản hồi cho developer**, ghi vào journal, đo precision (smoke #2: 5/5) | S–M |
| 9 | Bậc "độ đặc hiệu" cho spec: mỗi spec phải SATISFIED trên ≥2 cài đặt đúng độc lập + đối chứng âm cú pháp | S–M |
| 10 | Corpus "ghi thật" phát lại qua đường sản phẩm (`app.run.execute`, parser client thật, preflight) từ các luồng đã có trong smoke | M |
| 11 | Điểm dữ liệu thứ hai **có giá tiền**: cùng bundle, model khác (0 dòng mã) + lặp lại DeepSeek để đọc phương sai; ghi bảng giá, báo USD/story | 1–2 lượt trả tiền |
| 12 | Giới hạn developer: ít nhất kiểm toán "tầm với" vào `RUN.json` và đưa bundle ra khỏi thư mục cha của workspace; sau đó sandbox thật cho cả macOS và Linux (V21-02/06) | S → L |
| 13 | Bộ nạp an toàn: mọi lỗi đầu vào → mã 2 kèm đường dẫn JSON; `--check` trả đúng lý do B4; endpoint qua `urlparse`; `redact` trong `finally`; lỗi git → ENVIRONMENT | S |

**P2 — 2.2 và quy trình**

| # | Việc |
|---|---|
| 14 | Tách 1.x thành `aisef-legacy` (hoặc chỉ giữ `aisef legacy …`); `doctor` biết V2 |
| 15 | Client thứ hai (Claude Code hoặc Codex CLI); probe chạy với phụ thuộc đã khoá của dự án |
| 16 | Định vị lại thành **nhân kiểm chứng / cổng chấp nhận** dùng được cho PR của bất kỳ agent nào (CI check), thay vì chỉ là orchestrator một client |
| 17 | Chính sách phát hành cân xứng: tầng vá, một canary live rẻ ở **đầu** mỗi RC, ngân sách trả tiền cộng dồn có điểm dừng |
| 18 | Ăn kiêng bằng chứng: digest + tóm tắt trong git, luồng phiên thô và chunk Q4 sang release asset/LFS; tách test đọc bằng chứng khỏi bộ unit |
| 19 | Mutation: ràng buộc theo AST của từng hàm thay vì sha256 nguyên file; thêm toán tử xoá câu lệnh, biên số, handler |
| 20 | Giảm bus factor: runbook người bảo trì trong repo; một người review kernel không phải chủ dự án mỗi bản minor |

**Không làm bây giờ (nói ra để khỏi bị hút vào)**: thêm bậc Q, chạy lại Q4 với cùng seed, mở rộng mutation trước khi có
điểm dữ liệu live thứ hai; sandbox Windows; "cohort" niêm phong — chưa có workload thứ hai thì cohort vô nghĩa.

---

## 6. Lộ trình đề xuất

- **2.0.1 (≈1 tuần, ≈$0 provider)**: P0 #1–#5 + #13. Kiểm định theo tầng: mutation có mục tiêu cho file đổi, Q0,
  suite, CI, cài sạch; **một canary live 1 story** trước khi gắn tag thay cho smoke đầy đủ.
- **2.1 (≈3–6 tuần, 1–3 lượt trả tiền)**: #6–#12. Thước đo xong: một người ngoài dựng bundle cho một dự án 3 story
  không cần đọc mã nguồn; LedgerLock trên repo **không dọn** đạt 7/7; một route thứ hai được attest; USD/story được báo.
- **2.2**: #14–#16, rồi mới tới sandbox hai hệ điều hành và mở rộng probe.

---

## 7. Bảng chỉ số theo dõi (cập nhật mỗi bản phát hành)

| Chỉ số | 2.0.0 | Mục tiêu 2.1 |
|---|---|---|
| Lượt live đạt `delivery_verdict PASS` (không miễn trừ) | 0 / 8 | ≥ 1 trên workload chưa từng thấy |
| Workload × route × hệ điều hành đã chạy live | 1 × 1 × macOS | ≥ 2 × 2, có Linux |
| Lỗi do review tìm thấy mà vẫn vào `main` | 5 (smoke #2) | đo và báo cạnh 59/59 |
| Mệnh đề requirement được contract phủ | 30 / 54 | báo bằng máy trong `RUN.json` |
| Đọc ra ngoài workspace của developer | 69 lời gọi / 4 phiên | 0 (hoặc được báo) |
| USD / story giao được | chưa đo | có |
| Thời gian từ bản vá đến PyPI | ≈12,7 giờ (RC2) | < 1 ngày, không sửa công cụ phát hành |
| Người dùng ngoài | 0 | ≥ 1 đối tác thiết kế |
| Mục backlog có reproducer | 19 / 38 | tất cả mục ≥ medium |

---

## 8. Rủi ro

| Rủi ro | Khả năng | Tác động |
|---|---|---|
| Phán quyết giả qua `.pth` trong venv probe — `--verify` không phát hiện được | thấp–trung bình | nghiêm trọng |
| Developer "học tủ" theo stimulus ẩn đọc được, làm phồng ProductProof | trung bình (đã xảy ra) | cao |
| Người dùng mới nhận tỉ lệ giao thấp hơn xa 6/7 trên dự án/model khác | cao | cao |
| Nâng 2.0 → 2.1 làm gãy mọi bundle đang có | cao (V21-37 đổi probe) | cao với người dùng đầu tiên |
| OpenCode đổi định dạng sự kiện hoặc provider đổi fingerprint → mọi lượt dừng | trung bình | cao (dù đóng an toàn) |
| Phát hành ngoài ý muốn: ai có quyền push + tag là publish được | thấp | cao (PyPI không cho tải lại số phiên bản) |
| Uy tín sụp ngay lần đánh giá đầu: 404, bảng so sánh không nguồn, smoke FAIL hiển thị như ✓ | cao | cao |
| Bus factor một người; tri thức nằm trong tiêu đề commit và bộ nhớ agent | trung bình | cao |
| Miễn trừ thành thói quen: tiêu chí "tuyệt đối" bị nới khi cắn | trung bình | uy tín của mọi cổng sau |

---

## 9. Những gì chưa đo

- Giá tiền thật của bất kỳ lượt V2 nào (cần hoá đơn hoặc bảng giá 9router).
- Một vụ giả mạo end-to-end qua `.pth` trong `aisef run` thật (mới đo cơ chế).
- Thời gian đến lần chạy đầu của một người ngoài; công sức của con người khi soạn và duyệt 59 contract (59 approval mang
  cùng một dấu thời gian).
- Hành vi live trên Linux, Windows, model/route/phiên bản OpenCode khác.
- Danh sách test bị bỏ qua theo từng nền tảng; độ phủ dòng/nhánh của kernel.
- Đối chiếu ProductProof 66/67 (S-13-g chưa giao) với acceptance 59/59 trên `main` cuối: bản ghi không lưu kết quả từng
  spec nên chưa giải thích được hành vi đó tới `main` bằng đường nào.
- Lượt tải của 2.0.0 (dữ liệu pypistats dừng ở 2026-10-04).
