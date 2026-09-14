# Tuyển cặp model↔CLI cho cột 2 (G5.3)

Sinh bằng `python3 -m tests.bench qualify --bao-cao`, 2026-09-14. Không sửa tay một con số nào ở đây: bảng là đầu ra của sổ phiên.

Giao thức đã ghim: [`docs/BENCH-PAIR-QUALIFICATION-PROTOCOL.md`](BENCH-PAIR-QUALIFICATION-PROTOCOL.md) §2 — digest vùng ghim `bcdf7705f37fb27d…`, giá trị đối chiếu ở `docs/closure-gate.json` → G5.3 → `protocol_sha256`. Ngưỡng **0,167** và cỡ mẫu **28** được ghim *trước* khi một phiên nào chạy; đó là thứ làm bảng này đọc được.

## 1. Bảng tuyển

| model | client | phiên tuyển | phiên hợp lệ | phiên bị cắt (cut) | tỉ lệ cắt (rate) | biên trên 95 % | hỏng hạ tầng (timeout/infra) | loại khỏi mẫu | phán quyết | qualifies | evidence |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| mycombo→MiniMax-M3 (khai 2026-09-14, xác nhận qua /v1/chat/completions) | opencode | 28 | 28 | 0 | 0,000 | 0,101 | 0 | 0 | QUALIFIED | có | `closure-evidence/bench-pair-qualification.jsonl` |

## 2. Vì sao mỗi dòng ra kết cục ấy

- **mycombo→MiniMax-M3 (khai 2026-09-14, xác nhận qua /v1/chat/completions) / opencode** → `QUALIFIED`: 0/28 phiên bị cắt = 0,000 ≤ 0,167 (biên trên 95 %: 0,101).

## 3. Tài nguyên đã tiêu — giá thì vắng, tài nguyên thì không

| model / client | phiên | turn | giờ phiên | token | USD |
|---|---:|---:|---:|---:|---|
| mycombo→MiniMax-M3 (khai 2026-09-14, xác nhận qua /v1/chat/completions) / opencode | 28 | 1375 | 2,04 | 86 614 836 | vắng mặt (nhà cung cấp báo 0,00) |

Cột USD của nhà cung cấp này là **vắng mặt giá**, không phải miễn phí — C-1 tiêu 88,9 triệu token và cũng báo 0,00.

## 4. Kết luận cho cột 2

Cột 2 chạy trên **mycombo→MiniMax-M3 (khai 2026-09-14, xác nhận qua /v1/chat/completions) / opencode** (luật chọn: tỉ lệ cắt thấp nhất, rồi ít hỏng hạ tầng hơn, rồi thứ tự chữ — docs/BENCH-PAIR-QUALIFICATION-PROTOCOL.md §2).

Sổ từng phiên: `closure-evidence/bench-pair-qualification.jsonl` (bản commit) và `.aisef-qual/qualification.jsonl` cùng cây làm việc của từng phiên (bị gitignore).

