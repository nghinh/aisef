# ADR-011 — Không xây sandbox riêng cho provider `local`

Ngày: 2026-09-13. Trạng thái: **ACCEPTED**. Thay cho mục S1 còn treo từ
2026-09-05 ("PoC `sandbox-exec` / `unshare`").

## Bối cảnh đo được

Bảng [hợp quy sandbox](SANDBOX-CONFORMANCE.md) (06/09, mỗi ô là một lần chạy
thật) nói thẳng provider `local` đứng ở đâu:

| Phép thử | docker | local |
|---|---|---|
| S1 chặn mạng | ✅ | ✗ |
| S2 hệ tệp chỉ đọc | ✅ | ✗ |
| S3 không ghi ngoài workspace | ✅ | ✅ |
| S4 bí mật máy chủ không vào trong | ✅ | ✗ |
| S5 timeout không để lại tiến trình | ✅ | ✅ |

`local` khai `unsupported` cho `network_none`, `read_only_fs`, `non_root`,
`secrets_absent` — và **khai đúng**: mọi lần chạy qua nó đều bị đánh dấu
`degraded`, `doctor` in ra thiếu bảo đảm nào, cổng `pre-deploy` không nhận bằng
chứng degraded.

## Quyết định

**Không** xây lớp cách ly riêng cho `local`. Dự án nhạy cảm chạy **Docker**.

Ba lý do, theo thứ tự sức nặng:

1. **Một sandbox nửa vời nguy hiểm hơn không có sandbox.** `sandbox-exec` của
   macOS bị Apple đánh dấu deprecated từ nhiều bản trước và không có hợp đồng
   ổn định; `unshare` trên Linux cần quyền hoặc user namespace mà nhiều máy CI
   tắt. Một lớp chạy-được-trên-máy-tôi sẽ khai `network_none: native` ở chỗ nó
   thật sự chỉ chặn được một nửa — và bất biến "khai đúng năng lực" là thứ đắt
   nhất trong kho này.
2. **Chỗ nó bảo vệ đã có cổng khác canh.** `write-scope`, `diff-scope`,
   `egress`, `secret` là guard tất định chạy ở mọi provider; chúng chặn *ý định*
   của agent. Sandbox chặn *hậu quả* khi guard bị vượt. Với model hiện tại, đo
   trên 45 phiên của cohort C-1: **0 lần agent thử ghi ngoài phạm vi**, 1 lần
   chạm guard `destructive` và đó là dọn `__pycache__`.
3. **Hai nền tảng, hai hiện thực, vĩnh viễn.** Chi phí bảo trì rơi vào đúng chỗ
   dự án này yếu nhất: không có máy Linux để kiểm hằng ngày (bài học Windows
   ngày 12/09 — ba lỗi chỉ lộ ra trên CI).

## Hệ quả

- `local` giữ nguyên: chạy được, khai thiếu, đánh dấu `degraded`.
- Dự án nhạy cảm: bật Docker. `doctor` nói rõ khi daemon không chạy.
- Bảng hợp quy vẫn in cột `local` với dấu ✗ — không được sửa thành "—" hay bỏ
  cột: người đọc phải thấy cái mình không có.
- Mở lại quyết định này khi: có người dùng ngoài cần chạy trên máy không có
  Docker **và** chấp nhận trả tiền bảo trì cho hai hiện thực, hoặc khi một cơ
  chế cách ly có hợp đồng ổn định xuất hiện trên cả hai nền tảng.

## Cái **không** quyết định ở đây

ADR này không nới bất kỳ cổng nào: bằng chứng degraded vẫn không qua được
`pre-deploy`, và `sandbox.allow_degraded` vẫn là lựa chọn tường minh của dự án
chứ không phải mặc định im lặng.
