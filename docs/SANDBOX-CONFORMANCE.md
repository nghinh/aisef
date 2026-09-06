# Hợp quy sandbox

Sinh bởi `python3 -m tests.sandbox_conformance`, ngày **2026-09-06**. Mỗi ô là **một lần chạy thật** trên provider ấy (kèm thời gian); không ô nào suy từ khai báo. Docker chạy khi daemon có (`docker info`); Local luôn chạy — cột Local ✗ ở S1–S4 là điều bảng này phải nói ra: chạy thẳng trên máy không bảo đảm gì (bất biến 10).

| Phép thử | Chứng minh | docker | local |
|---|---|---|---|
| S1 `wget -T 3 -O- https://example.com` ở WORKSPACE_WRITE | mạng bị chặn, kể cả DNS | ✅ 10048 ms | ✗ 9 ms |
| S2 `sh -c 'echo x > x'` ở READ_ONLY | không ghi được workspace | ✅ 3593 ms | ✗ 12 ms |
| S3 `sh -c 'touch /etc/x'` ở WORKSPACE_WRITE | không ghi được ngoài workspace | ✅ 7138 ms | ✅ 18 ms |
| S4 `env` ở WORKSPACE_WRITE; harness đặt canary `AISEF_*`/`ANTHROPIC_*`/`AWS_*` ngoài `spec.env` | bí mật máy chủ không vào trong | ✅ 6965 ms | ✗ 18 ms |
| S5 `sleep 9999`, timeout 2 s | thoát 124, `timed_out`, không để lại container | ✅ 3461 ms | ✅ 2013 ms |

## Bảo đảm khai (`ExecutionProvider.guarantees`)

Bậc đọc: `READ_ONLY` cho `read_only_fs`, `WORKSPACE_WRITE` cho phần còn lại. `no_host_mount` không bậc nào đòi — mount worktree là thiết kế.

| Bảo đảm | docker | local |
|---|---|---|
| network_none | native | unsupported |
| read_only_fs | native | unsupported |
| non_root | native | unsupported |
| no_host_mount | unsupported | unsupported |
| secrets_absent | native | unsupported |

## Quan sát

- **docker S1** ✅ — exit 1, `wget: bad address 'example.com'`
- **docker S2** ✅ — exit 1, `sh: can't create x: Read-only file system`
- **docker S3** ✅ — exit 1, `touch: /etc/x: Permission denied`
- **docker S4** ✅ — exit 0
- **docker S5** ✅ — exit 124, timed_out, `quá 2s`, container còn lại: 0
- **local S1** ✗ — exit 127, `[Errno 2] No such file or directory: 'wget'` — provider khai `network_none=unsupported`: kết quả là hoàn cảnh máy, không phải bảo đảm
- **local S2** ✗ — exit 0 — provider khai `read_only_fs=unsupported`: kết quả là hoàn cảnh máy, không phải bảo đảm
- **local S3** ✅ — exit 1, `touch: /etc/x: Permission denied` — provider khai `non_root=unsupported`: kết quả là hoàn cảnh máy, không phải bảo đảm
- **local S4** ✗ — exit 0 — provider khai `secrets_absent=unsupported`: kết quả là hoàn cảnh máy, không phải bảo đảm
- **local S5** ✅ — exit 124, timed_out, `quá 2s`
