# AISEF 2.1 — Hướng dẫn sử dụng và di trú từ 2.0.0

Áp dụng cho nhánh `v2.1/foundation` (`2.1.0.dev0`, **chưa phát hành**). Mọi lệnh dưới đây không gọi provider, trừ
`aisef run` không kèm `--check`/`--verify`.

## 1. Từ con số không đến một lượt chạy kiểm tra được (không cần API nội bộ)

```bash
aisef bundle init --example calc-1-story --out calc
```
Lệnh này viết `calc/authoring.json` và các tệp của repo mẫu vào `calc/repo/`. Biến `calc/repo` thành repo git và commit — commit đó là baseline:

```bash
git -C calc/repo init -q -b main
```
```bash
git -C calc/repo add -A
```
```bash
git -C calc/repo commit -q -m baseline
```
Niêm phong: mọi hash và spec id được tính bằng constructor của kernel; **chưa có approval nào**:
```bash
aisef bundle seal calc/authoring.json --repo calc/repo --out calc/bundle.json
```
Đọc từng tiêu chí trước khi duyệt:
```bash
aisef bundle explain calc/bundle.json
```
Người duyệt — một con người, đặt tên `human:<tên>` — duyệt **từng** contract:
```bash
aisef bundle approve calc/bundle.json --contract BC-ADD --approver human:alice --out calc/approved.json
```
Kiểm tra READY (approval, chín phép admission với hiệu chuẩn đi kèm bản phát hành, độ phủ theo yêu cầu/mệnh đề):
```bash
aisef bundle lint calc/approved.json
```
```bash
aisef run --check --project calc/approved.json --settings settings.json --repo calc/repo
```
Ví dụ 3 story (hai loại probe, hai obligation PRESERVE): `--example calc-3-stories`. Định dạng soạn:
[`bundle-authoring.schema.json`](bundle-authoring.schema.json). Mọi lệnh `aisef bundle` viết **tệp mới**, không bao giờ
ghi đè; mã thoát 0 xong / 1 lint NOT_READY / 2 từ chối.

## 2. Di trú bundle 2.0.0

Spec id đổi một lần (ba danh tính, [ADR-2](ADR-V2.1.md)). Bundle 2.0.0 nạp vào 2.1 bị từ chối với gợi ý:
```bash
aisef bundle migrate old-2.0.0-bundle.json --out migrated.json
```
Chỉ `plan` được buộc lại theo contract đã duyệt của chính nó; requirement, contract, approval, facts không đổi; không
cần duyệt lại. Một obligation mà không bản phát hành nào biết đến bị từ chối, không đoán.

## 3. Settings: khoá tuỳ chọn mới (vắng = đúng hành vi 2.0.0)

```json
"review": {"policy": "fix-loop", "min_severity": "high"},
"prices": {"currency": "USD", "input_per_mtok": 1.32, "cache_read_per_mtok": 0.044, "cache_write_per_mtok": 1.32,
           "output_per_mtok": 3.96, "source": "<trang giá>", "effective_date": "YYYY-MM-DD"}
```
- `review` vắng ⇒ review advisory như 2.0.0. `fix-loop` ⇒ một finding có **reproducer** mà probe của AISEF tái hiện ở
  candidate, mức ≥ `min_severity`, sẽ chặn story (REVIEW_FINDING, retry trong giới hạn REVIEW) và nội dung được đưa cho
  developer ở lượt sau. Finding không tái hiện được: chỉ ghi lại để người phân loại.
- `prices` vắng ⇒ `usage.cost.value = null`, `status: unknown` — không bao giờ 0.

## 4. Sau một lượt chạy

- Lượt chạy in `evidence_anchor` (và ghi vào tệp mới với `--anchor-out FILE`); **giữ nó nơi developer không ghi được**
  — ngoài thư mục run thôi là chưa đủ khi developer chạy cùng user ([ANCHOR-THREAT-MODEL.md](ANCHOR-THREAT-MODEL.md)). Kiểm:
```bash
aisef run --verify --project bundle.json --out run1 --expect-anchor <anchor>
```
- `RUN.json` có thêm `usage` (token theo lớp, request, retry, thời gian, tiền nếu có giá) và `no_progress` (retry lặp lại
  đúng các lỗi cũ — chỉ báo cáo).
- Thư mục: `<out>/test-python` (venv cho test của developer; probe **không** chạy trên nó), `<out>/EVIDENCE.json`.

## 5. Lượt chạy dừng giữa chừng: nối tiếp, không chạy lại từ đầu

```bash
aisef bundle continue bundle.json --from-run run1 --out continued.json
```
```bash
aisef run --project continued.json --repo run1/repo --parent run1 --settings settings.json --out run2
```
Baseline mới = commit cuối mà journal của `run1` xác nhận; các story đã giao thành story `CARRIED` (VERIFY) được kernel
chứng minh lại mà không gọi developer. Bundle/kernel khác ⇒ từ chối (đó là dự án mới, không phải nối tiếp).

Bảo đảm (đã đo bằng SIGKILL thật, `test_v21_continue_integrity`):
- **Một run được nối tiếp đúng một lần.** `--parent` tạo độc quyền `run1/CONTINUED-BY.json` ngay trước khi run bắt đầu;
  run thứ hai (đồng thời hay sau) bị từ chối, nêu tên run đã nối. Ngoài tệp đó, bằng chứng của `run1` giữ nguyên từng byte.
- **Run bị giết vẫn nối được.** `RUN.started.json` được ghi một lần trước mọi việc (danh tính bundle/kernel/plan/settings);
  thiếu `RUN.json` thì `continue` đọc nó, báo `recorded: false`.
- **Không commit/merge lặp, không mất nghĩa vụ.** Merge mà journal chưa commit bị bỏ ra (báo `in_flight`); mỗi story được
  commit đúng một lần trong cả dòng dõi; nghĩa vụ đã giao được chứng minh lại (CARRIED), phần còn lại được giao.
- **Không mất, không đếm đôi chi phí.** `usage` của mỗi run chỉ đếm luồng phiên của chính nó; `run2/RUN.json` ghi
  `lineage_usage` = dòng dõi của run trước + của mình, mỗi run một lần. Chi phí của một run bị giết không bao giờ là
  `known` (bước đang chạy khi bị giết có thể thiếu): tổng dòng dõi khi đó là `null`.
- **Đuôi journal bị cắt** (mất điện giữa một lần ghi; một tín hiệu không cắt được: mỗi sự kiện là một `write` + `fsync`):
  dùng phần đầu đã kiểm chuỗi hash, báo `torn_tail: true`, sự kiện bị cắt coi như chưa xảy ra. Một dòng hỏng ở giữa ⇒ từ chối.
- **Tiến trình của run bị giết.** Watchdog của mỗi process range giết cả nhóm khi controller mất (đo: 2 tiến trình probe
  sống lúc kill, 0 còn lại sau 0,1 s).

Khác với resume tại chỗ: không có gì của `run1` được chạy tiếp hay ghi thêm vào journal của nó; `run2` là một lượt chạy
mới, journal mới, bắt đầu từ commit cuối đã xác nhận — công việc đang dở trong `run1` (một phiên, một merge chưa commit)
được làm lại từ đầu, và chi phí của nó vẫn được tính trong dòng dõi.

## 6. Thay đổi có thể làm hỏng quy trình cũ

| Thay đổi | Ảnh hưởng | Việc cần làm |
|---|---|---|
| spec id (ba danh tính) | bundle 2.0.0 bị từ chối | `aisef bundle migrate` |
| `<out>/probe-python` → `<out>/test-python` | script đọc đường dẫn cũ | đổi tên; probe chạy trên interpreter của aisef |
| `--check` clone repo như lượt chạy thật | một khoá git không "inert" trong repo của bạn không còn làm `--check` báo sai lý do | không |
| endpoint `http://` chỉ cho loopback (phân tích host thật) | `http://localhost.evil.example` bị từ chối | dùng https |
| preflight không theo redirect | endpoint trả 3xx ⇒ OPAQUE | dùng URL cuối cùng |
| phiên bản `2.1.0.dev0` | gate phát hành từ chối mọi bản dev | đúng chủ ý |

## 7. Giới hạn đã biết (đừng hiểu quá)

- Không có sandbox: developer và mã test chạy dưới user của người vận hành (V2-05 mở).
- `--verify` không có anchor chỉ chứng minh nhất quán.
- Review CONFIRMED không chứng minh người review đọc đúng yêu cầu.
- Bộ chuyển OCR chưa chạy với nhị phân thật; chưa nối vào `aisef run`.
- Chưa có số đo hiệu quả so với agent chạy trực tiếp — xem [EXPERIMENT-PLAN.md](EXPERIMENT-PLAN.md).
