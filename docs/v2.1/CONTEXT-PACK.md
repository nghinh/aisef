# D4 — Gói ngữ cảnh do controller dựng cho lượt thử lại của developer

Trạng thái: **M4** — gói tới developer qua CLI `aisef` thật (`validation/v21/cli_integration/run.sh` tại `80f4437`, cây
sạch: nhị phân Open Code Review thật, git thật; developer và mô hình của OCR là kịch bản). Bước cuối của `run.sh`
(`readback.py`) tính lại hai prompt developer của run1 từ journal của nó: sha256 **trùng** `prompt_sha256` trong
`RUN.json` và trùng tệp prompt client giả nhận; lượt 2 mang gói; mọi seq gói trích được đọc lại đúng story, đúng loại;
journal không chứa gói ([evidence/cli-integration-80f4437.out](evidence/cli-integration-80f4437.out), cùng các bước và mã
thoát như `b72e51e`). Offline (M3): `tests/v2/test_v21_context_pack.py`, gồm `run.execute` với client giả và phát lại
journal smoke-2. Hiệu quả trên mô hình thật: **M6** — cần lượt chạy live trả tiền, chưa có ngân sách. Thay đổi nằm trong
`aisef2/app/` (`feedback.py`, `adapters.py`): cần mutation và tái thẩm định ngoài snapshot đang đo.

Nhãn nguồn: **CODE** (đọc mã, có file:dòng), **README** (tài liệu của repo), **EXPERIMENT** (đo trên bằng chứng đã
ghi), **INFERENCE** (suy luận, chưa đo).

## 1. Bằng chứng cần

### 1.1 MiMo-Code `6babeb0b98f9`: ngữ cảnh đưa cho agent khi dựng lại, nén, thử lại

- **CODE** `packages/cli/src/session/prompt.ts:835-844`: dựng lại từ checkpoint khi tràn ngữ cảnh (tự động) hoặc
  `/rebuild`; không có checkpoint thì rơi về nén (compaction).
- **CODE** `session/checkpoint.ts:1252-1597` `renderRebuildContext` ghép, mỗi phần có trần riêng (`checkpoint.push_caps`,
  `:1322`, `:1340`, `:1346`, `:1351`, `:1365-1366`):
  - do controller giữ: actor đang chạy (`:1360`, `:1458-1470`), tin nhắn người dùng nguyên văn (`:1362-1397`),
    "Recent activity" của đuôi phiên — chỉ tên công cụ và đối số, bỏ kết quả, ≤ 200 dòng, đối số ≤ 80 ký tự
    (`session/tail-digest.ts:3-15`, `:39-45`);
  - lẫn: sổ task (`:1337`, `:1424-1451`) — controller lưu trong DB (`TaskRegistry`, `:630`), nhưng nội dung do agent ghi
    qua công cụ task (`tool/task.ts:109`, `:199-200` — agent tự đánh dấu task xong);
  - do agent viết: `checkpoint.md` (`:1339-1342`, `:1453-1456`; người viết là subagent checkpoint-writer,
    `agent/prompt/checkpoint-writer.txt:1`), ghi chú phiên, bộ nhớ dự án và toàn cục (`:1344-1358`, `:1477-1489`).
  - phần lấy từ tệp ghi đường dẫn (`File:`, `:1419-1421`); ranh giới dựng lại trước bị loại để không lồng đệ quy
    (`:1376-1385`; `tail-digest.ts:47-56`).
- **CODE** nén: `session/compaction.ts:215-224` gói bản tóm tắt do mô hình viết (`agent/prompt/compaction.txt:1-23`) vào
  `<conversation-summary>`, thay lịch sử.
- **CODE** thử lại: `session/retry.ts:198-213` phân loại lỗi vận chuyển theo scope/kind; `session/processor.ts:955-1005`
  nối tiếp bước đang dở từ lịch sử phiên — không dựng ngữ cảnh mới.
- **INFERENCE** từ `checkpoint.ts:1419-1489`: nội dung do agent viết vào ngữ cảnh dựng lại dưới cùng tiêu đề "auto-loaded
  session context" với phần do controller giữ, không có nhãn quyền uy.

AISEF lấy: ghép do controller, có trần theo phần, có trích nguồn, bỏ kết quả công cụ, không đưa lại đầu ra của lần
dựng trước. AISEF bác (đã quyết trong [UPSTREAM-RESEARCH.md](UPSTREAM-RESEARCH.md)): trạng thái do agent viết
(`checkpoint.md`; sổ task, `tool/task.ts:199-200` — agent tự đánh dấu task xong).

Khác bối cảnh: MiMo dựng lại **trong một phiên dài** khi tràn ngữ cảnh. AISEF mở **phiên mới cho mỗi lượt** (**CODE**
`aisef2/app/adapters.py` `Developer.implement` gọi `client.session` mỗi lần) và mỗi lượt checkout lại từ cha
(`aisef2/orchestrate/story_runner.py:164-181`, `merger.base()`). Câu hỏi của AISEF hẹp hơn: một phiên thử lại được
cho biết gì.

### 1.2 AISEF hôm nay cho developer gì

- **CODE** `adapters.py` `Developer.implement`: `feedback.task` (mệnh đề yêu cầu); khi có lỗi trước đó thêm
  `feedback.retry_feedback`, chỉ đọc `failure/observed` và bản ghi `proof/verified`, `probe/evaluated` ngay trước nó
  (`feedback.py` `retry_feedback`), cộng finding review đã xác nhận (V2.1).
- **CODE** mỗi lượt bắt đầu ở cha; candidate trước không còn trong cây làm việc (`story_runner.py:180`), nhưng vẫn là
  commit của repo (`orchestrate/workspace.py:136` `git worktree add` dùng chung kho đối tượng).
- **CODE** nối tiếp: `bundle_cli.py` `continue_from` chạy lại các story còn lại "như cũ"; developer của run con chỉ đọc
  journal của run con (`adapters.py`, `self.run.events`) — lỗi của cùng story trong run cha không được kể.

### 1.3 Đo trên bằng chứng đã ghi (chỉ đọc)

Công cụ: `validation/v21/context_gap.py`; đầu ra: [evidence/context-gap.out](evidence/context-gap.out) (tại `80f4437`).
Điều journal biết là **EXPERIMENT** (đọc từ journal). Điều developer **được kể**: smoke-2 là **EXPERIMENT** (mục 1); cycle-2
P10 là **CODE**, chưa tính lại — prompt do harness `validation/qualification/c2_p9.py` dựng, ở commit thực thi của từng
attempt (sha256 trùng bản ghi `LEDGERLOCK-REGRESSION.json`): attempt 2 (`1f992ba`, `:230-247`) và 3 (`06ceb23`,
`:422-439`) chỉ kể mã lỗi và mệnh đề; attempt 4 (`e49226b`, `:222-259`, `:480-490`) là `retry_feedback` H-RETRY-001 —
lỗi và bản ghi proof trước nó. Không bản nào đọc proof đã đạt hay mệnh đề đã admit.

1. **Biết chính xác developer được kể gì.** 8/8 prompt developer của smoke-2 (2.0.0, mô hình thật) được tính lại bằng chính
   mã 2.0.0 (`git archive v2.0.0`) từ phần journal trước mỗi request: sha256 **trùng** `prompt_sha256` mà run ghi.
2. **STORY-04-02 lượt 3** được kể hai lần REFUTED; lần thứ hai "candidate d8bab70…" — đó là **chính cha**. Journal biết
   lượt 2 "the developer changed nothing" (seq 1474) và proof chạy trên cha (seq 1482). (Bản ghi `RUN.json` còn biết lượt
   2 dừng ở trần 80 lượt sau 806 s; journal không có điều này.)
3. Trên **16 lượt thử lại** của 4 run có journal (smoke-2, cycle-2 P10 attempt 2–4): 13 có mệnh đề đã **đạt** ở candidate
   trước (verdict đúng kỳ vọng của plan — REFUTED với hợp đồng MUST_NOT_HOLD như S-3.4-a — verifier đồng ý) mà không
   được kể; 9 có mệnh đề **không có proof** ở lượt trước (ở smoke-2: lượt dừng sau lỗi đầu tiên) mà không được kể; 2
   có cha được gọi là "candidate".
4. **Developer tự đi tìm** (bộ phân loại regex trên lời gọi công cụ, đếm lời gọi khớp): 4/16 phiên tìm lại việc của lượt
   trước (21 lời gọi: `git reflog`/`fsck`, git nêu sha của một candidate trước — lời gọi chỉ nêu cha không tính, vì
   candidate trùng cha là lượt không đổi gì — hoặc đọc stream phiên trước), 2/16 đọc journal đang chạy (15), 4/16 chạm
   vật liệu proof ẩn (25), 5/16 đọc mã nguồn khung hoặc bundle (77); 4 lượt thử lại không đổi gì. Smoke-2 lượt 2: 88 lời
   gọi, 80 lượt, không đổi gì — 6 lời gọi về việc của lượt trước (git trên candidate trước hoặc đọc stream phiên trước),
   10 đọc journal (cả phân tích `plan/frozen`), 12 chạm vật liệu proof ẩn (scratch của probe, `request.json` hoặc worktree
   của verifier).

### 1.4 Kết luận về nhu cầu

- **Có bằng chứng (EXPERIMENT + CODE):** ở 15/16 lượt thử lại đã ghi, journal giữ sự thật về lượt trước mà developer
  không được kể (2 lượt smoke-2: EXPERIMENT; 13 lượt P10: điều journal giữ là EXPERIMENT, điều không được kể là CODE của
  harness); ở 4/16, developer tiêu 21 lời gọi công cụ để tự khôi phục việc của lượt trước, 2/16 đọc thẳng journal đang
  chạy.
- **Chỉ là INFERENCE:** rằng kể ra sẽ đổi kết quả (tỉ lệ đạt, số lượt, việc săn tìm). Đo cần lượt chạy live trả tiền → M6.
- **Gói này không giải được:** bước nào của probe thất bại — journal chỉ giữ verdict và reason
  (`closure-evidence/v2/cycle2/PROBE-DIAGNOSTIC-GAP-001.json`). Việc săn vật liệu ẩn
  (`DEVELOPER-CONFINEMENT-GAP-001.json`) chỉ đóng được bằng cách ly (F, M6); gói không tuyên bố làm giảm nó.
- **Nối tiếp:** CODE cho thấy mất thông tin; không có bản ghi nối tiếp nào mà story còn lại đã có lỗi → INFERENCE, không
  làm (§4).

## 2. Thiết kế

`aisef2/app/feedback.py` `context_pack(events, story_id, project, secrets)` → văn bản; chỉ `Developer.implement` gọi, chỉ
khi thử lại, chèn giữa `retry_feedback` và "Fix the implementation.". Rỗng (chưa lượt nào kết thúc) ⇒ prompt **giống hệt
từng byte** bản trước.

| Thuộc tính | Cách giữ | Test (`tests/v2/test_v21_context_pack.py`) |
|---|---|---|
| Do controller dựng, từ journal | đọc `story/begin`, `story/admitted`, `provider/request` (DEVELOPER) và `provider/result` của nó, `proof/verified` (chỉ candidate, criterion, verdict, agreement), `story/end` | `RecordedSmoke2`, `ThroughTheRun` |
| Nói gì | mỗi lượt trước, mới nhất trước: cha; kết quả developer (văn bản adapter); candidate, hoặc "chính cha — lượt đó không đổi gì"; mệnh đề **đạt** (verdict = kỳ vọng của plan cho mệnh đề đó, verifier đồng ý — mệnh đề của bất kỳ story nào, vì PRESERVE của story đã commit cũng được chứng minh ở candidate; mệnh đề plan không biết thì không bao giờ đạt); mệnh đề **không có proof ghi lại** trong lượt đó (không nói nguyên nhân: lượt có thể dừng trước proof, hoặc ngay ở probe của nó — PROBE_MISMATCH, PROBE_INVALID_SPEC). Lượt hiện tại bắt đầu lại ở cha; candidate trước là commit của repo | `test_what_an_earlier_attempt_left…`, `test_only_the_attempt_s_candidate_counts…`, `Expectation`, `test_no_proof_recorded_is_all_it_says…` |
| Trích nguồn | mỗi dòng kèm `(journal seq …)`; điều vắng mặt trích khoảng seq của lượt | `test_every_item_cites…` (seq có thật, đúng story, đúng loại) |
| Tất định | sắp theo seq, mệnh đề theo tên; không thời gian, môi trường, ngẫu nhiên | `test_an_identical_journal_gives_identical_bytes…` |
| Có biên | `PACK_MAX` 4000 ký tự (prompt là một phần tử argv; dòng lệnh Windows ≤ 32 767), `PACK_LIST` 12 tên/dòng, `PACK_ATTEMPTS` 4 lượt gần nhất, kết quả developer cắt đúng 300 ký tự; cắt theo dòng nguyên, có dấu; lượt mới nhất đứng trước nên biên cắt lượt cũ nhất | `test_it_is_bounded`, `test_at_the_real_bound_the_latest_attempts_are_kept…` |
| Không chứa vật liệu ẩn, bí mật | không đọc `probe/evaluated`, `tool/*`, `gate/check`, `tests/*`, stream phiên; không spec id, semantic hash; story khác bị loại; bí mật của run → `[REDACTED]` | `test_it_never_holds_proof_material…`, `test_a_review_result_is_never_taken…` |
| Không phải quyền uy | tiêu đề "context only — no verdict, approval or budget reads it"; không ghi vào journal; trong `aisef2/` chỉ `feedback.py` và `adapters.py` nhắc tới nó | `test_it_is_labelled…`, `ThroughTheRun` (journal không chứa nó) |
| Tóm tắt do agent viết | **không có** | — |

Đột biến tay (không phải chiến dịch mutation của kernel): `validation/v21/context_pack_mutants.py` chạy trên bản sao của
HEAD, baseline xanh trước, 12 đột biến các dòng của `context_pack` (bỏ kỳ vọng, mặc định SATISFIED cho mệnh đề lạ, kỳ vọng
chỉ của story này, bỏ điều kiện verifier đồng ý, cắt 299/301/1000, redact sau khi cắt, thứ tự cũ trước, trần 5 lượt, mọi
mệnh đề là "không có proof", proof sau thay proof đầu): **12/12 bị giết** tại `80f4437`
([evidence/context-pack-mutants.out](evidence/context-pack-mutants.out)).

Gói nằm trong prompt, nên đã được ràng buộc bằng `prompt_sha256` của phiên (`adapters.py`) và dựng lại được từ journal —
không cần trường bản ghi mới.

Đầu ra trên smoke-2 (phát lại offline, không phải bằng chứng của lượt chạy): phần 3 của
[evidence/context-gap.out](evidence/context-gap.out).

## 3. Gói này không phải là

- không phải checkpoint hay resume phiên; không phải `checkpoint.md` của MiMo; không có tóm tắt của agent;
- không phải chẩn đoán probe; không lộ stimulus; không đổi verdict, ngân sách, chính sách thử lại, định dạng journal;
- không đóng khoảng hở cách ly. **OD-3** (`docs/implementation/v2/cycle2/H-CONTEXT-AUTHORITY-001-DESIGN.md`): seq và sha
  trong văn bản developer thấy là khoá tìm kiếm khi không có cách ly (một phiên đã in bản ghi `probe/evaluated` theo seq
  được trích). Gói chỉ trích seq của `story/begin`, `provider/result`, `proof/verified` và khoảng seq của lượt, không trích
  bản ghi probe nào, không thêm loại định danh mới ngoài những gì `retry_feedback` đã đưa. OD-3 vẫn là quyết định của chủ
  dự án; nếu bỏ khoá tìm kiếm khỏi văn bản developer thì trích dẫn của gói đi theo.

## 4. Chưa làm

- **Nối tiếp** (lượt của cùng story trong run cha): chưa có bằng chứng cần đã ghi; nếu làm, đọc journal của run cha qua
  `app/lineage`.
- **Lý do dừng phiên trong journal**: chi tiết "changed nothing" bỏ `stopped` (`adapters.py`, `Implemented(O.FAILED…)`),
  nên gói không nói được "hết lượt". Sửa một dòng nhưng đổi văn bản journal — để riêng.
- **Hiệu quả trên mô hình thật**: M6.
- **Mutation** cho các dòng mới của `aisef2/app/feedback.py` và `adapters.py`: ngoài snapshot đang đo.
