# RC-SCHEDULE-PROTOTYPE — xếp việc worker cho chiến dịch mutation RC (study, 2026-11-26)

**Loại:** nghiên cứu lập lịch (owner directive 2026-11-26 P4). KHÔNG đổi code runner, KHÔNG đổi
quy tắc qualification, KHÔNG đổi record format. Target là đơn vị nguyên tử (không chia qua
worker — shard mutant-level owner đã từ chối, quyết định 7).

**Công cụ + bằng chứng chạy:** `aisef-private-evidence/2026-11-26-rc-schedule/{schedule_proto.py,report.txt}`
(python3 stdlib, tái lập bằng `python3 schedule_proto.py`).
**Đầu vào:** `aisef-private-evidence/2026-11-25-accel-plan/per_target.json` (E5, 37 target đo thật)
+ khung RC từ `docs/v2.3/ACCELERATED-DELIVERY-PLAN.md` §5 (registry 994 target, cửa sổ RC 02/02 ≈ 108–120h wall).

## 1. Phương pháp

- **37 target đo thật (E5):** dùng nguyên số đo — unlevered = `total_s`; levered = `total_s − sim_saved`
  (sim_saved = mô phỏng reorder kill-list trên chính timings E5, §5a).
- **957 target còn lại của registry:** NGOẠI SUY, mọi con số gắn nhãn **ƯỚC TÍNH**:
  - Giây/mutant = trung bình gộp của tập đo **LOẠI 2 giant** (`run.py::execute`,
    `story_runner.py::_attempt`) = **100,6 s/mutant** (720 mutant / 35 target). *Giả định:*
    hai giant là outlier về kích thước kill-set chứ không phải cấu trúc chi phí mỗi mutant,
    nên pool phi-giant dự báo tốt hơn cho target chưa đo. **ƯỚC TÍNH.**
  - Số mutant/target chưa biết → dùng **median tập đo = 14 mutant/target** (chọn median vì
    phân bố n lệch phải nặng). **ƯỚC TÍNH.**
  - Chiết khấu lever cho target ngoại suy = tỉ lệ gộp đo được
    `Σ sim_saved / Σ total_s = 64,1%`. **ƯỚC TÍNH** (benchmark bounded 2 target: 67,8%; mô phỏng
    toàn E5: 62% — 64,1% là tỉ lệ gộp đúng của per_target.json).
- **Mô phỏng:** list scheduling (target kế tiếp → worker nhẹ tải nhất) theo 3 kịch bản:
  (a) thứ tự đến kiểu E5 (baseline mất cân bằng), (b) LPT theo chi phí unlevered,
  (c) LPT theo chi phí levered.
- **Đối chiếu plan §5(c):** model ra 15.278 mutant / **474 giờ-worker unlevered (ƯỚC TÍNH)** —
  số mutant THẤP hơn 27.901 của plan (median-based, chưa có bucket kill-set của registry) nhưng
  giờ-worker rơi đúng dải 430–480 của plan (giây/mutant của model cao hơn bù lại). Đóng góp của
  study là độ phân giải per-target, không phải tổng.

## 2. Baseline E5 (37 target, 4 worker) — mất cân bằng thật

| Cách xếp | Makespan | Spread | Utilization |
|---|---|---|---|
| E5 thật (static partitioning) | 52,3h | 44,0h | 50% |
| Mô phỏng arrival-order | 49,1h | 40,3h | 51% |
| Mô phỏng LPT unlevered | 48,7h | 38,7h | 51% |
| Mô phỏng LPT levered | 17,7h | 16,3h | 50% |

Trên tải E5, xếp kiểu gì cũng chạm sàn giant (`execute` 48,7h): **LPT chữa spread, lever chữa sàn.**

## 3. Bảng 4/6/8 worker — toàn chiến dịch RC 994 target (mọi dòng = ƯỚC TÍNH vì chứa ngoại suy)

| Worker | (a) arrival, unlevered | (b) LPT, unlevered | (c) LPT, levered | Vừa cửa sổ 108–120h? |
|---|---|---|---|---|
| 4 | 118,6h (spread 0,2h) | **118,5h** (spread 0,0h) | **42,6h** (spread 0,0h) | unlev: vừa SÁT MÉP / lev: vừa, dư ~2,5× |
| 6 | 79,1h (spread 0,3h) | **79,0h** | **28,4h** | cả hai vừa |
| 8 | 59,4h (spread 0,3h) | **59,3h** | **21,3h** | cả hai vừa |

Utilization ≥ 99,7% ở mọi ô: 957 target nhỏ ngoại suy lấp đầy mọi khe, nên ở quy mô RC sự khác
biệt arrival vs LPT gần như biến mất — mất cân bằng kiểu E5 chỉ tái hiện khi tải bị chi phối bởi
ít target lớn (mục 2). LPT vẫn là lựa chọn mặc định vì miễn phí và không bao giờ tệ hơn.

## 4. Phân tích giants (số ĐO, không phải ước tính)

| Target | Unlevered | Levered |
|---|---|---|
| `aisef2/app/run.py::execute` | 48,7h | **17,7h** |
| `aisef2/orchestrate/story_runner.py::_attempt` | 30,5h | **15,1h** |

- Target nguyên tử ⇒ **không lịch nào thắng được max(giant):** sàn 48,7h unlevered / 17,7h levered
  ở MỌI số worker.
- Nhưng ở quy mô RC, giant chỉ trói makespan khi `tổng/giant < số worker`: unlevered
  474h/48,7h ≈ 9,7 worker; levered 170h/17,7h ≈ 9,6 worker (ƯỚC TÍNH). Tức là **ở 4 worker,
  makespan bị trói bởi NĂNG LỰC, không phải giant** — `execute` chỉ chiếm 41% makespan 4-worker
  unlevered (118,5h) và 42% makespan levered (42,6h). (Trên chính E5 thì giant CÓ chi phối:
  48,7h > 99,4h/4 = 24,8h.)
- Hệ quả: shard mutant-level cho 2 target nóng **không mua được gì dưới ~10 worker** — quyết
  định 7 (từ chối shard) vẫn thoải mái cho RC.

## 5. Khuyến nghị

**4 worker, LPT theo chi phí levered** (bảng phân công đầy đủ trong `report.txt`; mỗi worker
≈ 42,6h, spread ≈ 0: worker-1 nhận `execute` + đuôi nhỏ, worker-2 nhận `_attempt` + đuôi nhỏ).

**Chữ ký order-lever có đổi số worker cần cho cửa sổ 02/02 (~108–120h wall) không? CÓ, về biên an toàn:**
- **Không lever:** 4 worker = 118,5h (ƯỚC TÍNH) — nằm SÁT mép trên cửa sổ, zero margin; chỉ cần
  ngoại suy lệch (registry thật 27.901 mutant vs 15.278 của model) là vỡ cửa sổ ⇒ cần **6 worker**
  (79,0h) để có biên.
- **Có lever (owner ký E5 là measurement được trích dẫn, §5a):** **4 worker = 42,6h (ƯỚC TÍNH)** —
  vừa cửa sổ với biên ~2,5×, vẫn vừa kể cả khi ngoại suy thấp 2 lần.

Điều kiện kèm: giao thức RC đã chốt (mỗi-target-một-invocation + commit record xen giữa) giữ nguyên;
lever chỉ cần bảng order sinh từ per_target.json + chữ ký owner, không đổi code (ORD-4).

## 6. Hạn chế khai báo

- **Ngoại suy 957 target CHƯA ĐƯỢC KIỂM CHỨNG cho tới RC preflight:** số mutant/target thật và
  giây/mutant thật của phần registry chưa đo có thể lệch xa median/mean của 37 target E5 (vốn
  thiên về `run.py`/`story_runner.py`). Chạy lại `schedule_proto.py` với số preflight trước khi
  chốt cỡ fleet.
- Tỉ lệ lever 64,1% áp đồng loạt cho target ngoại suy là ƯỚC TÍNH gộp; per-target thực dao động
  0%–96% trong tập đo.
- Mô phỏng bỏ qua overhead ngoài per-target records (~4h trong 103,4h E5) và giả định worker
  đồng tốc; E5 chạy trên fleet không đồng nhất.
