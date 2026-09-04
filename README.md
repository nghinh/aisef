# AI-SDLC

Khung phát triển phần mềm bằng agent. Đầu vào của mỗi dự án là **một file**
`docs/requirements.md`; đầu ra là một ứng dụng chạy được, kèm bằng chứng
cho từng bước.

Nguyên tắc nền, xuyên suốt mọi quyết định trong kho này:

> **Cần phán đoán thì giao cho model. Cần đảm bảo thì viết code.**

Viết PRD, thiết kế kiến trúc, dựng mockup, viết code — đều cần phán đoán,
đều giao cho model. Còn "mọi yêu cầu phải có story phủ", "không được ghi
ra ngoài phạm vi", "test phải xanh sau lần sửa cuối" — đều có đáp án đúng,
nên đều là code. Hệ quả: **không bao giờ giao cho model việc giám sát
chính nó.**

## Cài

```bash
git clone <repo> ai-sdlc && cd ai-sdlc
./references/clone.sh          # nạp kho skill tham chiếu (một lần)
python3 -m unittest discover -s tests -q
```

Không có phụ thuộc Python nào ngoài thư viện chuẩn. Tuỳ chọn:
`docker` (cách ly khi chạy test), `playwright` (trích hợp đồng thị giác
từ mockup) — thiếu thì framework **nói thẳng là thiếu** chứ không giả vờ
vẫn kiểm được.

## Sáu bước

```bash
export A=/duong/dan/ai-sdlc/bin/aisdlc
cd /duong/dan/du-an-cua-ban

$A doctor                       # môi trường có đủ chưa
$A setup                        # dò stack, nạp skill, sinh CLAUDE.md + AGENTS.md
$A compile                      # nối guard vào client (hook / plugin)

$A plan                         # PRD → kiến trúc → UX → epic → story
$A gates                        # xem cổng nào đang chờ người
$A review prd                   # đọc artifact
$A approve prd                  # duyệt

$A mockup                       # mỗi màn hình một HTML + hợp đồng thị giác
$A approve mockups
$A approve readiness

$A run                          # hiện thực: epic tuần tự, story song song
$A qa                           # bộ kiểm định
$A devsecops                    # CI + Dockerfile + triển khai + runbook
$A pre-deploy                   # cổng cuối
$A report                       # báo cáo nghiệm thu từ bằng chứng
```

Chạy nhanh không cần người duyệt: `$A plan --auto-approve all`. Phê duyệt
tự động **luôn** được ghi dấu `auto` để về sau truy được tài liệu nào chưa
từng có người thật xem.

## Cổng

Tám cổng, mỗi cổng hai lớp. **Cổng máy** chạy trước — nó bắt được thứ máy
bắt tốt hơn người (chu trình phụ thuộc, yêu cầu không kiểm chứng được,
story không khai phạm vi ghi). **Cổng người** chạy sau, trên thứ đã sạch.

Phê duyệt là **trạng thái trên đĩa**, không phải câu hỏi trong phiên chat:
người duyệt có thể là người khác, lúc khác, trên máy khác. Bản ghi phê
duyệt gắn với **băm nội dung** artifact — sửa tài liệu sau khi duyệt thì
phê duyệt hết hiệu lực, và sửa tầng trên làm mọi tầng dưới thành `stale`.

## Guard

Bảy guard, mỗi guard là một lệnh trả mã thoát, nối vào ba mốc vòng đời:

| Mốc | Guard |
|---|---|
| trước mỗi tool | `write-scope` · `destructive` · `secret` · `git-stage` · `injection` |
| sau mỗi tool | `diff-scope` |
| khi agent định dừng | `completion` |

Guard nằm ở phía framework, không ở phía client — client không được tin.
Client nào không gắn được guard tiền kiểm (OpenCode hiện ở mức này) thì
`aisdlc verify` chạy lại toàn bộ trên diff, và báo cáo ghi rõ mức bảo đảm
thấp hơn thay vì im lặng.

## Chạy song song

Epic chạy tuần tự. Trong một epic, hai story chỉ được cùng đợt khi **hết
phụ thuộc** *và* **phạm vi ghi rời nhau** — thiếu điều kiện thứ hai thì hai
story cùng sửa một file và người thua là người merge sau. Mỗi story chạy
trong worktree git riêng; merge tuần tự cuối đợt. Conflict lúc merge không
được tự gỡ: nó là **bằng chứng `write_scope` khai sai**.

## Cấu trúc

```
aisdlc/
  cli.py            bộ lệnh, mọi lệnh gọi-một-lần, không daemon
  config.py         ngưỡng và cấu hình, có kiểu, có kiểm
  clients/          Claude Code · OpenCode; năng lực được **khai**, không giả định
  control/          cổng, phê duyệt, xếp lịch, worktree, chuẩn hoá tài liệu BMAD
  harness/          prompt · tool · sandbox · guard · quan sát · map mockup
  kit/              catalog skill, lọc bảo mật hai tầng, hiến pháp, prompt, skill riêng
  phases/           plan · mockup · implement · run · qa · deploy · report
docs/
  SOLUTION.md              giải pháp tổng thể và vì sao chọn như vậy
  EXECUTION-PLAN.md        kế hoạch thực thi, trạng thái từng hạng mục
  REQUIREMENTS-EVIDENCE.md R1–R14 → test chạy được
  SPIKE-REPORT.md          kết quả 7 spike kiểm chứng khả thi
```

## Bằng chứng, không tự khai

Mọi cổng đọc `_bmad-output/evidence/{story}.jsonl` — lần chạy test, lần
sửa file, lần gọi model kèm chi phí và độ trễ, lần đối chiếu mockup. Câu
"đã hoàn thành" của agent không được tính là gì cả.

Cụ thể, một story chỉ xong khi: test xanh **và** xanh sau lần sửa cuối ·
lint sạch · thay đổi nằm trong phạm vi khai báo · màn hình thật dựng đủ
component mockup đã hứa · rà soát độc lập (phiên khác, cấm sửa code) không
còn mục chặn · không có test nào rỗng khẳng định.
