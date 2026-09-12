# ADR-010 — Bài học từ MiMo-Code: cái nhận, cái bác, và cái đo rồi bỏ

Ngày 2026-09-12. Trạng thái: **accepted** cho ba mục đã thực hiện; phần còn lại
là PROPOSED có điều kiện đo kèm theo.

Không ghi đè ADR nào. Phần bộ nhớ mở rộng [ADR-007](ADR-007-scoped-advisory-memory.md)
và [ADR-008](ADR-008-paired-memory-harness.md) thay vì viết lại chúng.

## Bối cảnh

[MiMo-Code](https://github.com/XiaomiMiMo/MiMo-Code) (Xiaomi, MIT + `USE_RESTRICTIONS.md`,
TypeScript/Bun, **fork của OpenCode**, 13,1k sao, 725 issue mở) giải quyết đúng
những bài toán AISEF đang mở: bộ nhớ xuyên phiên, chưng cất kỹ năng từ việc lặp
lại, phán xét hoàn thành, gộp lệnh gọi công cụ. Câu hỏi không phải "MiMo có gì"
mà "cái nào **đo được** là cải thiện AISEF mà không làm yếu mô hình tin cậy,
bằng chứng, cách ly và kiểm định tất định".

Nghiên cứu đọc mã nguồn, tài liệu kiến trúc, prompt của `/dream` và `/distill`,
và **bảng issue** — bằng chứng âm tính quan trọng ngang bằng chứng dương.

### Giấy phép, nói trước vì nó quyết định hình thức tiếp thu

MIT cho mã; `USE_RESTRICTIONS.md` là ràng buộc **cách dùng** (cấm dùng cho mục
đích quân sự, tấn công mạng, thu thập dữ liệu cá nhân trái phép, "thực thi tự
động hành động rủi ro cao mà không có giám sát của con người"), không phải ràng
buộc phát hành. Nhưng nó nói "và mọi sản phẩm phái sinh", nên **chép mã kéo
theo ràng buộc ấy vào AISEF**.

Quyết định: **học pattern, không chép mã**. Không dòng nào của MiMo-Code vào
`aisef/`. Mọi thứ dưới đây là thiết kế viết lại từ đầu, có dẫn nguồn ý tưởng.

## Ma trận fit/gap

| Năng lực MiMo | Giải bài toán gì | MiMo làm thế nào | AISEF đã có? | Khoảng trống | Rủi ro an ninh | Quyết định |
|---|---|---|---|---|---|---|
| **Retry coordinator** | Phân biệt lỗi hồi phục được với lỗi vô vọng | Tách *scope* (request/live-step) khỏi *kind* (network/stream/server/rate_limit/terminal); rate_limit theo `Retry-After`; cấm replay step đã có side effect | Một phần: `INFRA_STATUSES` phẳng, thử lại **ngay** | 429 đốt sạch ngân sách hạ tầng trong vài giây | thấp | **ADOPT — đã làm** |
| **BM25/FTS5 cho truy hồi bộ nhớ** | Xếp hạng bản ghi khi ngân sách chỉ chứa vài dòng | SQLite FTS5, token phrase-quote, **OR-join** (AND làm rỗng gần như mọi truy vấn nhiều từ trên kho 80 tài liệu), sàn điểm lọc nhiễu | Đếm từ trùng × 10 + hạng tin cậy | Không IDF, không chuẩn hoá độ dài | **có**: BM25 thưởng tần suất ⇒ bản ghi nhồi từ khoá leo hạng | **REJECT (đã đo)** — xem §3 |
| **`/dream` — hợp nhất bộ nhớ** | Biến vết chạy thành tri thức bền | Prompt thủ công: quỹ đạo là nguồn sự thật, bộ nhớ là chỉ mục; chỉ thăng cấp khi có câu nói tường minh/quyết định thiết kế/lặp lại; ngày tuyệt đối; giữ id phiên; xoá cái đã bị phủ định; ≤200 dòng | `aisef memory` có vòng đời + provenance, **không** có hợp nhất | Không có đường từ bằng chứng đã kiểm → bộ nhớ | trung bình (đầu độc) | **ADAPT — PROPOSED** §4 |
| **`/distill` — việc lặp → kỹ năng** | Đóng gói quy trình lặp lại | Prompt thủ công, cửa sổ 30 ngày, kiểm kê tài sản có sẵn trước, "không có gì lặp thì đừng tạo gì" | `aisef skill` có registry + router; không có chưng cất | Không có đường từ quỹ đạo → kỹ năng ứng viên | **cao** (kỹ năng sinh ra từ quỹ đạo độc) | **DEFER** §5 |
| **Auto-dream / auto-distill theo lịch** | Tự học không cần người | Chạy nền mỗi 7/30 ngày, gác bằng `memory.disable_write` | Không | — | cao | **REJECT** §6 |
| **Checkpoint + session resume** | Sống sót qua giới hạn ngữ cảnh | `checkpoint.md` tự động, tái dựng ngữ cảnh | Không (AISEF dùng phiên mới mỗi story) | — | — | **REJECT** §6 |
| **Task tree (T1, T1.1…) + stop-gate** | Theo dõi việc con trong phiên | `task/gate.ts`: chặn dừng khi còn task mở, **giới hạn 2 lần nhắc**, fail-open khi DB lỗi | FSM story + scheduler + guard `completion` | Không | — | **REJECT làm trạng thái chuẩn** — §6; một ý đã có sẵn ở AISEF |
| **`exec` / tool_script (QuickJS)** | Gộp nhiều lệnh gọi công cụ trong một lượt | Guest QuickJS không Node/fetch/timer; công cụ chủ vẫn qua permission; **loại trừ công cụ điều khiển luồng** (task/skill/workflow/session); trần 50/500 lệnh, 8 song song, 64 MiB, 30 phút | Không | Có thể giảm lượt/token | **cao** | **EXPERIMENT P2** §7 |
| **Mix of Harness (bàn giao giữa harness)** | Một harness bế tắc thì đổi harness | Codex CLI/Claude Code CLI đóng gói thành **skill**; "Try-Best detector" phát hiện vòng lặp năng suất thấp rồi tạm dừng để người chọn | Nhiều client, chọn **trước** khi chạy; không bàn giao giữa chừng | Phát hiện bế tắc **trong** một lượt | thấp | **EXPERIMENT P2** §8 |
| **MiMo làm client thứ ba** | Thêm lựa chọn thực thi | — | Claude + OpenCode hạng nhất | MiMo là fork OpenCode ⇒ adapter có thể gần dùng được | **cao**: bộ nhớ/checkpoint gốc phá vỡ bảo đảm phiên mới | **DEFER có điều kiện** §9 |
| **`memory.cc_index`** — nạp transcript Claude Code vào bộ nhớ | Tận dụng lịch sử công cụ khác | Đọc `~/.claude/projects` | Không | — | **cao**: rò dữ liệu chéo dự án; MiMo issue #1671 OOM khi đọc transcript lớn | **REJECT** |
| **Alias + khớp tên tường minh cho skill** | Định tuyến skill | Khớp chính xác tên/alias ⇒ điểm cố định cao; loại stopword gồm cả nhãn khuôn mẫu; stem số nhiều; bigram cho chữ Hán | Router hai tín hiệu + abstain | Không có alias | thấp | **DEFER** — `skills.offer` đang tắt vì **hai** lần A/B cho gain 0; đầu tư thêm đi ngược bằng chứng |

## §3 — BM25: đo rồi bác, và phép đo ở lại

Giả thuyết ban đầu xếp BM25 vào P0. Nó không sống sót phép đo.

Bộ đo cũ (`aisef.memory_bench`) **không trả lời được câu hỏi**: recall 1,0 và 0
lần lấy nhầm, nên mọi cách chấm đều hoà. Dựng `framework/bench/memory_rank` đo
đúng thứ cách chấm quyết định — bản ghi nào thắng khi ngân sách chỉ chứa vài
dòng — trên hai họ dữ liệu **dựng để mâu thuẫn nhau**:

| cách chấm | Họ A (mồi nhồi từ khoá) | Họ B (bản ghi đúng chỉ chia sẻ một từ hiếm) |
|---|---|---|
| đếm từ trùng (hiện tại) | MRR **0,944** | 0,556 |
| BM25 | 0,870 | **0,611** |
| trùng từ riêng biệt × IDF | 0,889 | 0,556 |

`precision@3` = 1,00 ở cả ba cách, cả hai họ. Chỉ MRR nhúc nhích, thứ hạng
**đảo chiều giữa hai họ**, trên 12 truy vấn. Đó là nhiễu, không phải kết quả.

Thêm một lý do không thuần hiệu năng: BM25 là cách chấm **duy nhất thưởng tần
suất**, nên một bản ghi nhồi từ khoá leo hạng — mà đầu độc bộ nhớ là mô hình đe
doạ thật của tầng này. Đổi cách chấm ở đây là đổi một bề mặt an ninh để lấy một
cải thiện chưa đo được.

Đọc đúng mức: **ở quy mô bộ nhớ của AISEF, hàm xếp hạng chưa quan trọng.** Khi
kho đủ lớn để nó quan trọng, phép đo cách một lệnh.

## §4 — `dream` phiên bản AISEF: hợp nhất từ **bằng chứng**, không từ hội thoại

MiMo hợp nhất từ quỹ đạo hội thoại. AISEF có thứ mạnh hơn hẳn và đã tất định:
sổ bằng chứng gắn SHA, phát hiện của reviewer/security có `contract_authority`,
kết cục cổng, sổ hành vi VERIFIED/GAP/REOPENED, và quyết định của con người ở
tám cổng.

Thiết kế đề xuất (**chưa làm**, cần đo trước khi bật):

```
bằng chứng đã gắn SHA + phát hiện reviewer + kết cục cổng + quyết định người
          ↓  (deterministic: đọc sổ, không gọi model)
ứng viên bộ nhớ, mỗi cái mang source.ref + digest
          ↓  (kiểm provenance/scope/trust — mã, không phải model)
ACTIVE / UNVERIFIED / STALE / SUPERSEDED
```

Kỷ luật lấy nguyên từ `/dream` vì nó đúng: chỉ thăng cấp khi có **lặp lại hoặc
phát biểu tường minh**; ngày tương đối đổi thành tuyệt đối; giữ id nguồn ở cuối
mỗi mục; xoá mục đã bị phủ định; giữ kho đặc và ngắn.

Khác một điểm cốt tử: **bản tóm tắt của model không tự động thành quyền uy.**
Ở MiMo, `/dream` là một phiên agent ghi thẳng vào `MEMORY.md`. Ở AISEF, bước
sinh ứng viên phải là **mã đọc sổ**, còn model chỉ được dùng để *diễn đạt* —
và mọi ứng viên vẫn đi qua `_validate` hiện có.

Điều kiện bật: đo theo ADR-008 (cặp có/không) trên corpus thật, chỉ số chính là
**tỉ lệ lặp lại cùng một lỗi**. Không đạt thì không bật.

## §5 — `distill`: hoãn, và nêu rõ vì sao

Đường "việc lặp → kỹ năng" hấp dẫn, nhưng ba bằng chứng của chính kho này nói
chưa phải lúc:

1. `skills.offer` **tắt** sau hai lần A/B cho gain 0 (ADR-003 §6).
2. Đo trên e9: 156 skill cài vào, tool `Skill` được gọi **11 lần cho 4 skill**,
   tất cả đều do prompt gọi đích danh — *cài không sinh ra dùng*.
3. Kỹ năng sinh từ quỹ đạo là bề mặt tấn công mới: một quỹ đạo độc thành tri
   thức thủ tục có hiệu lực.

MiMo tự đặt đúng rào cho việc này ("không có gì lặp thì đừng tạo gì; tạo ra một
tài sản để biện minh cho lần chạy là sai"), nhưng rào ấy do **model** giữ. Ở
AISEF rào phải là mã. Hoãn cho tới khi có bằng chứng skill tạo ra gain.

## §6 — Bác bỏ, kèm bằng chứng từ chính bảng issue của MiMo

Ba cơ chế nghe hấp dẫn nhưng bảng issue cho thấy giá của chúng:

| Cơ chế | Bằng chứng |
|---|---|
| Checkpoint tự động + resume | #1915 "Checkpoint rebuild reinjects hard resume after completed work, causing main-agent keep-alive loop"; #1866/#1867 "Checkpoint-writer infinite loop — sub-agent never executes tools" |
| Bộ nhớ tự nạp/tự ghi liên tục | #1351 "Memory leak: 6–10GB RAM, triggers OOM kill on 16GB system"; #1854 "OOM 10–20GB: unbounded `message.summary.diffs` + prune skipped while checkpoint-writer + history.backfill" |
| Nạp transcript công cụ khác | #1671 "crashes on launch — Claude Code import reads large transcripts whole-file and OOMs" |
| Chuẩn hoá đường dẫn bộ nhớ | #908, #1455 "Memory system fails to load on Windows — path outside memory layout" (tên người dùng không ASCII); #1571 "memory_fts empty on Windows: path separator mismatch"; #1641/#2361 "reconcile skips all files" |

Nhóm cuối đáng chú ý nhất với AISEF: **tầng bộ nhớ chết ở khâu xác thực đường
dẫn, và Windows là nơi nó chết.** Hôm nay kho này vừa sửa bốn lỗi cùng lớp
(bug 71–74). Kết luận cho AISEF: mọi mã bộ nhớ mới phải đi qua `_compat`, dùng
`safe_path`, và **có phép thử giả lập Windows** chứ không chờ CI.

Thêm một ý AISEF **đã có** nên không cần nhập: stop-gate của MiMo giới hạn 2
lần nhắc và fail-open khi hạ tầng lỗi. Guard `completion` của AISEF đã theo
đúng nguyên tắc ấy — ALLOW khi test `unrunnable`/`skipped`, vì chặn ở đó chỉ
đốt lượt mà agent không sửa được. Không đổi gì.

## §7 — `exec`/tool_script: thí nghiệm P2, và một nguyên tắc đáng giữ sẵn

Nếu AISEF từng gộp lệnh gọi công cụ, nguyên tắc của MiMo đáng chép nguyên
(bằng lời, không bằng mã): **công cụ đổi trạng thái điều khiển luồng không bao
giờ được nằm trong script gộp**. MiMo loại `task`, `skill`, `workflow`, `cron`,
`session` khỏi `exec` vì chúng đổi trạng thái hội thoại/lịch trình. Bản dịch
sang AISEF: `aisef tool *` có thể gộp; `aisef gate`, `aisef approve`, `run`,
`improve` thì không.

Giữ P2: lợi ích (ít lượt, ít token) chưa đo, còn giá (một runtime khách mới,
provenance của lệnh con, khả năng lách guard) thì chắc chắn.

## §8 — Phát hiện vòng lặp năng suất thấp: khoảng trống thật

Tín hiệu bế tắc mà MiMo liệt kê, đối chiếu AISEF:

| Tín hiệu | AISEF |
|---|---|
| N lần lỗi liên tiếp cùng loại công cụ | không có |
| **Không đổi tệp nào quá X phút/lượt** | chỉ phát hiện **sau khi phiên kết thúc** (bug 68/69/70) |
| Quá nhiều lần nén ngữ cảnh | không áp dụng (phiên mới mỗi story) |
| Không cải thiện qua các lần chạy test | một phần: `improve` dừng khi cải thiện ≤ 0 |
| Chi phí vượt 80 % ngân sách | có từ hôm nay (`BudgetGuard`), nhưng chặn ở cổng chứ không cảnh báo sớm |
| Thiếu artifact bắt buộc ở đầu ra | có (cổng máy) |

Khoảng trống thật: **trong** một phiên, AISEF không biết agent đang giậm chân.
Một lượt 35 turn/491 giây không ghi gì (đo hôm nay trên `sec-2` lượt 3) chỉ bị
phát hiện khi đã trả tiền xong. Đây là P2 vì nó cần hook mức tool để đếm.

## §9 — MiMo làm client thứ ba: hoãn, có điều kiện mở

MiMo là fork của OpenCode, nên adapter OpenCode của AISEF có thể chạy được với
ít sửa đổi — đó là lý do **kỹ thuật** để thử. Ba lý do để hoãn:

1. Lộ trình của chính AISEF xếp "client thứ ba" vào nhóm *không làm bây giờ*:
   nó tốn bề mặt bảo trì mà không trả lời câu hỏi nào đang mở.
2. MiMo mang **trạng thái không do AISEF kiểm soát**: bộ nhớ, checkpoint, lịch
   sử phiên. Một story mới phải là phiên mới; nếu MiMo tiêm checkpoint của phiên
   trước vào thì bảo đảm cốt lõi của AISEF vỡ **im lặng**.
3. Bảng issue cho thấy chính tầng ấy đang lỗi nhiều nhất.

Điều kiện mở (phép thử **MIMO-MEMORY-ISOLATION**, phải viết trước khi viết
adapter): với `MIMOCODE_HOME` trỏ vào thư mục rỗng và `memory.disable_write`
bật, hai phiên liên tiếp trên cùng dự án phải **không** chia sẻ một ký tự nào
của phiên trước — kiểm bằng cách trồng một chuỗi canary ở phiên 1 và chứng minh
nó vắng mặt trong prompt/ngữ cảnh của phiên 2. Không chứng minh được thì MiMo
không thành client hạng nhất, và câu ấy ở lại trong bảng năng lực.

## Đã thực hiện trong ADR này

| Thay đổi | Cam kết giữ | Cách tắt |
|---|---|---|
| `rate_limit` thành exit status riêng, ngoài nhóm thử-lại-ngay | Không đổi ngữ nghĩa cổng; 429 vẫn không tính vào ngân sách chất lượng | trả `INFRA_STATUSES` về hai phần tử |
| `retry_delay_seconds` đọc `Retry-After` từ lời nhà cung cấp, trần 300 s | Không đoán khi nhà cung cấp im lặng | `MAX_RETRY_DELAY_SECONDS = 0` |
| `framework/bench/memory_rank` | Phép đo ở lại kể cả khi kết luận là "không đổi gì" | — |

## Rủi ro và cách hoàn nguyên

Ba thay đổi đều là sửa nhỏ, đảo ngược được bằng một commit. Không cái nào đụng
vào cổng, bằng chứng, hay vòng đời story. Không cái nào thêm phụ thuộc.

## Cái ADR này **không** kết luận

Chưa đo: `dream` phiên bản bằng chứng (§4), phát hiện bế tắc trong phiên (§8),
`exec` gộp công cụ (§7), MiMo làm client (§9). Mỗi cái có điều kiện đo viết sẵn
ở mục của nó. Không cái nào được bật vì "MiMo có".
