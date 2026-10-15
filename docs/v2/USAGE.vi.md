*[English](USAGE.md) · Tiếng Việt*

# AISEF 2.0 — dùng runtime V2 (`aisef run`)

AISEF 2.0 điều phối và kiểm chứng sản phẩm một cách tất định, gắn với bằng chứng, cho việc làm phần mềm có trợ giúp
của AI. `aisef run` thực thi một kế hoạch đã được chủ dự án phê duyệt trên một repository git: với mỗi story, một phiên
developer (client OpenCode, trên đúng một route model cố định) sửa code, và kernel V2 quyết định — dựa trên các probe
độc lập kiểm tra sản phẩm, không bao giờ dựa trên lời của developer — story đó được giao, chạy lại hay rollback. Mọi
quyết định được ghi vào một journal chuỗi băm (hash-chained) mà thư mục chạy lưu lại, và `aisef run --verify` kiểm
một lần chạy đã xong đối chiếu với journal đó.

## Cài đặt

```bash
pip install aisef==2.0.0
```

Cần Python 3.11 trở lên, `git` 2.31 trở lên và — cho một lần chạy thật — client `opencode` trên `PATH` cùng một
endpoint provider tương thích OpenAI, có key nằm trong biến môi trường do bạn đặt tên. `aisef run --check` không cần
hai thứ sau.

## Một lần chạy cần gì

**Một project bundle** (`aisef-v2-project/1`, một file JSON): mọi thứ mà lần chạy dùng để chứng minh dự án.

| trường | chứa gì |
|-------|---------|
| `name`, `description` | cách developer được giới thiệu về dự án |
| `requirements_document` | `{path, sha256}` — file yêu cầu trong repository tại baseline của kế hoạch (UTF-8, LF), được kiểm tra trước khi chạy bất cứ thứ gì |
| `product_roots` | tên thư mục cấp cao nhất chứa mã nguồn của dự án (`["pkg", "tests"]`) |
| `requirements`, `contracts`, `approvals` | các đối tượng Requirement, BehaviorContract và ContractApproval (phê duyệt của con người) của kernel, mỗi đối tượng được niêm phong bằng hash |
| `plan` | Plan: commit baseline và các nghĩa vụ chứng minh (criterion, ProductProofSpec, story, vai trò INTRODUCE / PRESERVE / VERIFY) |
| `facts` | với mỗi criterion, các sự thật công khai developer được biết: `requirement`, `section`, `clause`, `clause_text`, `subject` |
| `stories` | với mỗi story, `depends_on` và các đường dẫn `tests` mà developer của story đó viết |

Khi nạp, mọi niêm phong được kiểm lại, mỗi contract phải có phê duyệt của con người gắn nó với từng requirement nó
trích dẫn, và mọi contract được biên dịch với các probe của bản phát hành này; một kế hoạch nêu một spec mà không
contract nào đã duyệt biên dịch ra sẽ bị từ chối. Trước khi chạy, kế hoạch phải qua kiểm duyệt tĩnh (static admission
— chín phép kiểm của kernel). AISEF 2.0 chạy bundle; nó không soạn bundle.

**Thiết lập lần chạy** (`aisef-v2-run/1`, một file JSON). Mọi trường đều bắt buộc — không có giá trị mặc định:

```json
{
  "format": "aisef-v2-run/1",
  "client": "opencode",
  "route": "myprovider/my-model",
  "provider": {"name": "myprovider", "endpoint": "https://api.example.com/v1", "api_key_env": "MYPROVIDER_API_KEY",
               "served_model": "my-model", "listed_owner": null, "model_limit": {"context": 200000, "output": 32768}},
  "client_env": ["MYPROVIDER_API_KEY"],
  "budget": {"provider_requests": 60, "turns": 700, "input_tokens": 60000000, "output_tokens": 400000},
  "max_turns_per_session": 80,
  "limits": {"DEVELOPER": 2, "PLAN": 0, "ENVIRONMENT": 1, "PROVIDER": 1, "INTEGRATION": 0, "REVIEW": 1, "SECURITY": 1},
  "timeouts_s": {"developer": 2400, "reviewer": 900, "tool": 120, "probe": 60},
  "preflight": {"chat_probes": 2}
}
```

`route` có dạng `<provider>/<model>` và là model duy nhất client được dùng (cả model chính lẫn model nhỏ); client được
báo model của route và `model_limit` của nó. `served_model` là tên model mà provider báo là đang phục vụ route (một
router có thể báo tên upstream: route `9router/ds/deepseek-v4-pro` được phục vụ dưới tên `deepseek-v4-pro`), còn
`listed_owner`, khi khác null, là owner mà danh sách model phải ghi — không bao giờ là alias của router trỏ sang model
khác. Cấu hình riêng của client (`opencode.json` dưới `XDG_CONFIG_HOME` hoặc `~/.config/opencode/`) phải gửi provider
tới đúng `endpoint`, nếu không lần chạy bị từ chối trước mọi request; `api_key_env: null` lấy key từ cấu hình đó (giá
trị trực tiếp hoặc `{env:VAR}`).
`client_env` liệt kê các biến của người vận hành mà client được nhận; phần môi trường còn lại được dựng từ một danh
sách cố định (PATH, HOME, locale, XDG và thư mục tạm, lấy giá trị của chính người vận hành), không thừa kế nguyên khối
— nên client vẫn chạy với thư mục home, cấu hình OpenCode toàn cục và mạng của người vận hành. `limits` là số lần chạy
lại mà mỗi chủ sở hữu lỗi được dùng. Key chỉ được đọc lúc chạy và không bao giờ được ghi ra đâu; giá trị của
`client_env` và key của provider (từ 8 ký tự) bị che khỏi log phiên.

## Lệnh

```bash
aisef run --check  --project bundle.json --settings run.json --repo ./myproject   # đầu vào + kiểm duyệt; không gửi request nào tới provider
aisef run          --project bundle.json --settings run.json --repo ./myproject --out ./runs/r1
aisef run --verify --project bundle.json --out ./runs/r1                          # dựng lại một lần chạy đã xong từ journal
```

Mã thoát: **0** kết luận giao hàng là PASS (`--check`: sẵn sàng; `--verify`: VERIFIED) · **1** FAIL hoặc NOT_REACHED
(`--verify`: REFUTED) · **2** bị từ chối trước khi chạy — một đầu vào không thoả, kế hoạch chưa được kiểm duyệt, hoặc
một identity stop; không phiên nào được mở.

Một lần chạy, theo thứ tự: repository được clone (không bao giờ bị ghi) tại baseline của kế hoạch và file yêu cầu được
kiểm tra; kế hoạch được kiểm duyệt; một trình thông dịch probe riêng được tạo (một venv không có pip và không có gói
site của máy); **preflight** liệt kê các model của provider và gửi `chat_probes` lần completion rất nhỏ (tối đa 16 token) — route chỉ
được chứng thực nếu mọi câu trả lời đều do đúng model đã khai phục vụ, dưới cùng một fingerprint triển khai, nếu không
lần chạy dừng (identity stop) trước mọi phiên; rồi các story chạy theo thứ tự phụ thuộc. Ngân sách được tính lại từ
bằng chứng (ledger preflight, journal, luồng phiên) trước và trong mọi phiên; chạm trần — hoặc chi tiêu không đối soát
được — sẽ kết thúc lần chạy, và một phiên bị dừng khi tới giới hạn lượt.

## Thư mục chạy

`--out` phải chưa tồn tại; một thư mục chạy không bao giờ được dùng lại, và không gì trong đó bị xoá.

| đường dẫn | là gì |
|------|------------|
| `RUN.json` | bản ghi: kết luận giao hàng và lý do, kết quả từng story, sổ ProductProof, ngân sách, các phiên, `main` cuối cùng, digest của journal — được ghi dù lần chạy kết thúc vì bất cứ điều gì (một exception, một lần ngắt) |
| `run/journals/aisef-run.jsonl` | journal thô (format 3, chuỗi băm): nguồn quyết định duy nhất cho mọi kết luận |
| `repo/` | bản clone của dự án: `main` là sản phẩm đã giao, mọi candidate và lần merge đều được giữ |
| `preflight/` | ledger và quan sát của preflight |
| `sessions/` | mỗi phiên model một luồng sự kiện |
| `probe-python/` | trình thông dịch probe của lần chạy |

`delivery_verdict` là **PASS** chỉ khi mọi story của kế hoạch đều commit, ngân sách không chạm trần và không story
nào bị từ chối; **NOT_REACHED** khi không story nào tới được cổng của nó. `plan_quality_verdict` luôn là
`NOT_CLAIMED` trong 2.0.

## 2.0 khẳng định gì, và không khẳng định gì

Khẳng định: điều phối và kiểm chứng sản phẩm tất định, gắn với bằng chứng. Trong một phép chứng minh, mã candidate
(thứ developer viết) chỉ chạy trong tiến trình agent của probe; kết luận do một controller không bao giờ import nó đưa
ra, qua một kênh đã xác thực, nên trong một lần đánh giá candidate không thể ghi kết luận hay kênh của nó (lỗ giữa các
lần đánh giá được nêu ở Giới hạn đã biết). Nhưng nó vẫn khai sai được về chính nó — mã thoát, giá trị trả về — nên một
candidate viết ra để làm vậy, hoặc nhận ra mình đang bị probe, có thể làm một sản phẩm hỏng ra kết quả SATISFIED (kết
luận hành vi đạt của probe): bảo đảm nằm ở kênh, không nằm ở giá trị mà mã đang bị kiểm khai. Bằng chứng thô của lần
chạy được giữ nguyên.

Mô hình đe doạ: người vận hành đáng tin; mã sinh ra có thể sai hoặc "lách". Không khẳng định: tổng quát hoá cho mọi
loại workload, vượt trội so với V1, chất lượng model, cô lập đa người thuê có tính thù địch, cô lập hoàn toàn trước
một tiến trình độc hại của cùng người dùng hệ điều hành, bảo vệ trước chủ máy. Probe chạy với thư viện chuẩn và chính
mã nguồn của candidate (không có phụ thuộc bên thứ ba của dự án). Review của model chỉ mang tính tham khảo và không bao
giờ chặn; scanner (`ruff`, nếu đã cài) cũng chỉ tham khảo.

Nền tảng: `aisef run` được hỗ trợ trên Linux và macOS; mọi lần chạy thật đến nay đều trên macOS (Linux được kiểm trong
CI với client và provider giả). Trên Windows gói cài được và bộ test của kernel chạy được, nhưng một lần `aisef run`
thật không thuộc phạm vi khẳng định của 2.0.

## Giới hạn đã biết

- **Criterion đọc mã Python bằng mẫu theo dòng có thể bác bỏ mã đúng.** Trong smoke phát hành 2.0, một story đúng bị
  rollback vì một criterion "stdlib only" coi một dòng docstring bắt đầu bằng `from …` là một câu lệnh import
  (S6-SMOKE-2-FALSE-ROLLBACK-S10A). Kernel dừng an toàn — không mã nào trượt một spec của bundle lọt vào `main` — nhưng
  story đó không được giao. Criterion nhận biết cú pháp được lên kế hoạch cho 2.1 (V21-37).
- **Hồi quy phát hiện sau merge không quay về developer.** Nó thuộc INTEGRATION và không được chạy lại, nên developer
  không được biết criterion bị hỏng và không có lượt chạy lại (V21-38, kế hoạch 2.1).
- **Nghiệm thu chỉ tương đối với spec của bundle.** "0 chấp nhận sai" nghĩa là không story nào trượt chính contract
  của nó mà vẫn được giao. Trong smoke phát hành, review của model tìm ra 5 lỗi tái hiện được nằm ngoài 59 spec; chúng
  đã được giao vì review chỉ mang tính tham khảo.
- **Developer không bị giới hạn.** Client chạy dưới user hệ điều hành của người vận hành, với HOME, PATH, thư mục XDG,
  cấu hình OpenCode toàn cục (plugin, MCP server) và mạng của người đó. Trong smoke phát hành, các phiên developer đã
  đọc ra ngoài worktree — scratch của probe, journal đang chạy, bundle chứa stimulus của phép chứng minh, kernel đã cài
  — trước khi một story commit (V21-02).
- **Interpreter của probe ghi được.** Controller của probe chạy venv của lần chạy với `-I` nhưng không `-S`, nên một
  file `.pth` do test hoặc phiên developer cài vào site-packages của nó sẽ chạy bên trong các controller sau, nơi giữ
  khoá của kênh. Khẳng định về kênh kết luận đúng trong một lần đánh giá, không đúng giữa các lần đánh giá (V21-28;
  bản vá dự kiến ở 2.0.1).
- **`--verify` chứng minh tính nhất quán, không chứng minh tính xác thực.** Chuỗi băm không có khoá và `RUN.json` nằm
  cạnh nó; kết quả từng story, điểm dừng ngân sách và lỗi story được đọc từ `RUN.json`, và viết lại nhất quán cả hai
  vẫn VERIFIED (V21-30).

Toàn bộ backlog 2.1, kèm trạng thái tái hiện của từng mục: [V2.1-BACKLOG.md](V2.1-BACKLOG.md).

## Chuyển từ AISEF 1.x

- `aisef run` giờ là V2. Lệnh thực thi của V1 là `aisef legacy run …`, cùng các tuỳ chọn như `aisef run` của 1.x;
  vòng cải tiến là `aisef legacy improve …`; mọi lệnh V1 khác giữ nguyên.
- Dự án V1 không phải bundle V2: V2 chạy các behaviour contract đã duyệt và một kế hoạch đã qua kiểm duyệt tĩnh, không
  chạy file story của V1. 2.0 không có chuyển đổi tự động.
- V2 không ghi gì vào repository của dự án; kết quả của nó là thư mục chạy và nhánh `main` của bản clone.
