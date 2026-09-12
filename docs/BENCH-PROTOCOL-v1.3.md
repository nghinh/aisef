# Bench Protocol v1.3

Frozen 2026-09-12, supersedes v0.3.0 once results land.

## Conditions

Same as v0.3.0:

| Condition | Guards | ENV AISEF_* | settings.json | Scoring |
|-----------|--------|-------------|---------------|---------|
| `claude` (AISEF) | compiled hooks (write-scope, destructive, secret, git-stage, injection, process-ref, diff-scope, completion) | yes | yes | hidden-test F2P/P2P |
| `claude-bare` (control) | none | none | none | hidden-test F2P/P2P (same scorer) |

Optional weak-model column in v1.3 (gate under `tests.bench.run --client
<weak>` once results land; protocol frozen once both columns are committed).

## Dataset

30 bug-fix tasks mined from repo history (`tests/bench/tasks/`):

- **18 v0.3.0 tasks** (`bug-2-7-8-9`, `bug-4-5`, …, `bug-r2r1`):
  16 valid, 2 excluded (bug-6 needs Docker, bug-15 has invalid gold).
  Single-file fixes, 1–3 regression tests each.  Sample: simple bug-fix,
  obvious root cause from symptom.

- **12 v1.3 tasks** (`bug-a2-multi-*`, `bug-a2-state-*`, `bug-a2-sec-*`):
  all 12 valid, F2P=108 / P2P=750+ test coverage.  Distribution:
  - 4 multi-file refactor (`multi-1..4`): log parser, runlog, gate
    state, parallel-run state — 5+ src files each.
  - 4 state / concurrency (`state-1..4`): attempt-counting, no-op
    guard, interrupted state, gate pre-condition logic — 4–5 src files
    each.
  - 4 reviewer / scope / security (`sec-1..4`): MCP scope,
    guard-message contents, self-review exception, reviewer scope —
    4–6 src files each.

  Each v1.3 fix touches an average of 4.5 source modules; the
  previous v0.3.0 average was 1.4.  Tasks that fail P2P validation
  (gold does not make all surviving tests pass) are excluded.

Each task: base SHA (before fix), tests.patch (regression tests),
gold.patch (fix), prompt (symptom only, no answer).  Prompt lint: no
SHA, no fix commit name, no URL.

## Scorer

Same as v0.3.0 (`_runner._grade()`):

1. Revert any test files the agent touched
2. Apply hidden `tests.patch`
3. Commit candidate
4. Run `tools.test` at candidate SHA
5. Grade by F2P test names (fail-to-pass) and P2P stability
   (pass-to-pass)

PASS = all F2P green AND no P2P regressions.

## Runs

- 3 attempts per task per condition (v0.3.0 baseline)
- Interleaved per task: AISEF 3× then bare 3×, task order shuffled
- Weak-model column (v1.3): one attempt per task per condition with
  `--client opencode-gpt4-mini` (or equivalent); single run, not power-
  tested
- `pass@1` = fraction of attempts that PASS
- `pass@3` = 1 if any attempt PASS, 0 otherwise
- Stability = all 3 attempts same outcome

## Metrics

Same six as v0.3.0, plus:

7. **Weak-model pass@1** (v1.3 only): same scoring on a non-frontier
   model; documents whether the harness's value survives a quality drop
8. **Cost-difference ratio** = (AISEF cost − bare cost) / bare cost:
   the 7 % overhead reported in v0.3.0 is held as the baseline; v1.3
   re-runs the same metric on harder tasks so any change can be read
   against it

## Integrity

- Protocol SHA: `<filled at freeze>`
- Tasks committed and validated before any run
- No task or verifier modification after seeing results
- If forced to fix: invalidate + rerun both conditions for affected
  tasks

## Why harder tasks

v0.3.0 reported 100 % pass@1 for the 16 simple tasks on both AISEF and
bare; the 7 % AISEF cost overhead was the only signal that the harness
adds anything.  v1.3 doubles the dataset to 30 tasks, half of which
require the agent to reason across more than one module, before any
column is run.  A null result on v1.3 ("AISEF and bare both score
100 %") would be a more meaningful null than the v0.3.0 result because
the floor of difficulty is higher.

---

## Addendum C-1 — real non-frontier model (frozen 2026-09-12, before the run)

Written and committed **before** the run it describes, so that the design
cannot be adjusted to the result.

### Why this cohort exists

v0.3.0 answered "does the harness change the outcome for a frontier model on
easy tasks" with a clean null (100 % vs 100 %). The v1.3 simulator answered
nothing about guards by construction, and said so. The open question — the one
the whole harness rests on — is whether guards change anything when the agent
is **not** frontier. That needs a real model with real hooks.

### Conditions

| | AISEF | control |
|---|---|---|
| client | `opencode` | `opencode` |
| guards | compiled hooks + plugin | none |
| `AISEF_*` env | yes | no |
| model | identical in both branches | identical in both branches |
| scorer | hidden F2P/P2P, unchanged from v0.3.0 | same |

Anything that differs between the two branches other than the harness itself
makes the comparison unreadable; `--model` is threaded into both branches for
that reason, and a test pins it.

### Dataset and design

The 12 A-2 tasks, unchanged, bytes pinned by `tests/bench/tasks/MANIFEST.sha256`.
Three attempts per task per condition, interleaved per task (AISEF ×3, then
control ×3), task order shuffled with a **recorded seed** so the sequence can
be rebuilt.

### What this cohort can and cannot say

- **Can**: whether the harness changes pass@1 / pass@3, turn count and guard
  activity for this model on this dataset.
- **Cannot**: anything about a frontier model — that column (B-3) needs
  credentials this environment does not have, and stays open.
- **Cannot**: cost. The provider behind this alias reports `cost: 0` for every
  step, so the dollar column is *absent*, not zero. Turns and wall-clock are
  the resource metrics here, and the report must say which is which.
- **Cannot**: name the model that answered. OpenCode's JSON stream carries no
  model or provider field (probed 2026-09-12), and the configured default is a
  routing alias whose backing model varies between calls. What is recorded is
  the alias that was *asked for* — a declaration, not an observation, and
  labelled as such wherever it appears.

### Stopping rule

`--max-usd` cuts at task boundaries only, so every task that ran, ran its full
design. Any task not run is printed by name. A truncated dataset is reported as
truncated.

### Cách đợt đo thật sự chạy (ghi lúc đang chạy, 2026-09-12)

Lượt phóng đầu tiên chạy cả 12 task trong một tiến trình nền và **bị kill sau
~35 phút** (harness dọn tác vụ nền dài, không phải lỗi của bench). Hai task đã
xong đủ thiết kế, task thứ ba dở dang.

Đợt được chạy tiếp theo **lô hai task một lần**, và task dở dang được chạy lại
**từ đầu** chứ không nối tiếp — nửa bộ lượt của một task là một thiết kế khác,
không phải cùng một thiết kế bị ngắt.

Đính chính, ghi ngay khi phát hiện: lô đầu tiên được gọi là
`run-both bug-a2-multi-3 bug-a2-multi-1` nhưng **chạy multi-1 trước** — bộ lọc
task duyệt theo thứ tự dataset chứ không theo thứ tự tham số. Thứ tự trong các
lô vì thế là thứ tự dataset, không phải thứ tự của hạt giống 1312 (hạt giống
ấy chỉ chi phối lượt phóng đầu tiên, tức hai task `sec-4`, `sec-3`). Mã đã sửa
để nêu tên là chạy theo thứ tự đã nêu, và câu này ở lại đây vì đợt đo không
chạy dưới bản đã sửa. `results.jsonl` là sổ nối thêm nên dòng cũ vẫn nằm đó; công cụ đọc lấy
dòng **cuối cùng** cho mỗi `(task, điều kiện, lượt)`, đúng với cây làm việc còn
trên đĩa.

Hệ quả phải nói ra: các phiên không chạy liền một mạch trong cùng một khung giờ.
Với một alias định tuyến có thể đổi mô hình nền giữa các lần gọi, đó là một
biến không kiểm soát được — và là thêm một lý do để báo cáo không rút ra kết
luận mạnh hơn dữ liệu.

### Lời khai model cho cột 1 (chủ dự án, 2026-09-12 trong lúc đang chạy)

Chủ dự án khai: mô hình nền sau alias `9router/mycombo` **đang là MiniMax-M2.7**.

Đây là **lời khai**, không phải quan sát: luồng JSON của OpenCode không mang
tên model, nên dữ liệu của cột 1 ghi `9router/mycombo` ở mọi dòng và không thể
tự xác nhận điều trên. Trường `note` của các dòng ấy để trống vì trường này
chưa tồn tại lúc cột 1 bắt đầu; dán nhãn ngược vào dữ liệu đã đóng băng là việc
không được làm, nên lời khai ở lại đây, kèm ngày giờ.

Ràng buộc kéo theo, đã thống nhất với chủ dự án: **không đổi mô hình nền trong
lúc một cột đang chạy**. Đổi giữa chừng thì nửa cột đo model này, nửa kia đo
model khác, mà mọi dòng vẫn ghi cùng một chuỗi — hỏng không cứu được. Cột 2 chỉ
bắt đầu sau khi cột 1 đóng, và mang nhãn `--note "mycombo→<tên model>"`.


### Cột 2 — quy trình, viết trước khi chạy

Cột 1 chạy trên `9router/mycombo` với model nền **MiniMax-M2.7** (lời khai chủ
dự án). Cột 2 giữ nguyên **mọi thứ khác** và chỉ đổi model nền sau alias.

Bốn bước, theo thứ tự, không rút gọn:

1. Chủ dự án đổi model sau alias `mycombo` và **nói ra tên model mới** — harness
   không tự đọc được cấu hình của 9router, nên tên ấy là lời khai và phải được
   ghi là lời khai.
2. Chạy:

   ```
   nohup python3 -m tests.bench run-both <12 task theo đúng thứ tự cột 1> \
       --client opencode --attempts 3 --note "mycombo→<tên model> (khai <ngày>)" &
   ```

   Thứ tự task **giữ nguyên như cột 1**. Xáo lại là đổi một biến không cần đổi.
3. Đóng đợt: `python3 -m tests.bench report --cohort "<tên model>"` và
   `python3 -m tests.bench analyze`.
4. So hai cột **theo từng task**, không so hai con số tổng: 12 task với n = 3
   không đủ mẫu để một hiệu số tổng có nghĩa.

**Chế độ trần lượt phải giữ nguyên như cột 1.** Cột 1 chạy khi adapter OpenCode
chưa thi hành `run.max_turns` — chế độ thật của nó là *chỉ đồng hồ 1800 s chặn*,
và một phiên đã chạy 61 lượt ([O-10](BENCH-OBSERVATIONS-C1.md)). Từ 13/09 adapter
giết tiến trình tại trần. Nếu cột 2 chạy có trần thì hai cột khác chế độ và hết
so được, nên `tests/bench/_runner.py` khai `TRAN_LUOT = 0` cho **cả hai** nhánh,
có phép thử ghim. Muốn đổi con số ấy thì phải sửa mục này trước, không sửa mã trước.

**Điều kiện dừng sớm, chốt trước:** nếu hai task đầu của cột 2 đều 6/6 PASS ở cả
hai điều kiện thì model mới cũng chạm trần trên bộ dữ liệu này — dừng, báo, và
đừng đốt hai giờ nữa để lấy một cột toàn số 1,00. Trần dữ liệu là kết quả, và
nó phải được báo như một kết quả.

## Bộ dữ liệu v1.4 — sửa đúng một đề bài, sau khi C-1 đã đóng

Ngày 13/09, **sau** khi cohort C-1 đóng (không sửa giữa đợt: xem
[O-2](BENCH-OBSERVATIONS-C1.md)).

`bug-a2-sec-2` có đề bài đọc được **hai nghĩa**, và hai nhánh đã đọc ra hai nghĩa
khác nhau: "thông báo … cắt bỏ danh sách phạm vi được phép … agent không biết
mình được phép ghi đâu" có thể hiểu là *câu thông báo in thiếu* (đúng — test ẩn
gọi tên `check_diff_scope`) hoặc *phạm vi tính sai* (sai chỗ — và là cách đọc tự
nhiên nếu agent đang sống trong một phiên có `AISEF_WRITE_SCOPE` thật). Nhánh
AISEF đi vào `effective_scope` cả hai lượt có ghi tệp; nhánh trần đi vào
`check_diff_scope` và qua. Một đề bài mà điều kiện thí nghiệm đổi được cách đọc
là **lỗi của bộ dữ liệu**, không phải kết quả về harness.

Đã sửa: đề bài nói rõ đây là **câu thông báo** của guard, và nói thẳng "phạm vi
*tính* đúng — chỉ câu chữ báo lại là thiếu". Không tiết lộ hàm nào, thứ tự nào —
phần ấy vẫn là việc của agent.

**Truy vết được cho C-1:** byte đề bài mà C-1 đã chạy là
`4ff8dc71d6a1991ac10f173da4f35f1a04bfc70b99447eafcac78fa8d9f9bc16`
(`bug-a2-sec-2/prompt.md`); bản v1.4 là
`ab5d21f039f45d6089b9a414093cc3bbea03b395edf2a3bf2110b17ba58fb72b`. Mọi task
khác **không đổi một byte**. Muốn dựng lại C-1 nguyên trạng thì `git checkout`
`MANIFEST.sha256` và `prompt.md` ở commit trước bản vá này.

**Hệ quả cho so sánh:** cột 2 (đổi model) chạy trên **v1.4**, nên `sec-2` của cột
2 **không so được** với `sec-2` của cột 1. Báo cáo cột 2 phải nói rõ điều đó ở
chính dòng task ấy, và 11 task còn lại vẫn so được.

### Hình dạng khó của bộ dữ liệu, đo trên C-1

Con số hữu ích cho người thiết kế đợt sau: trong 12 task, chỉ **4 task phân biệt
được hai điều kiện**.

| nhóm | task | kết cục |
|---|---|---|
| chạm trần (cả hai nhánh 1,00) | `multi-1`, `multi-2`, `multi-3`, `sec-3`, `sec-4`, `state-4` | 6 task — không nói được gì về harness |
| bất khả (cả hai nhánh 0,00) | `state-1`, `state-2`, `multi-4` | 3 task — model không giải được, kể cả có harness |
| **phân biệt được** | `sec-1`, `sec-2`, `state-3` | 3 task |

Nghĩa là một cohort 12 task × 3 lượt tốn ~6 giờ chỉ cho ra **9 lượt có thông
tin**. Đợt sau nên tuyển task theo tiêu chí "đã từng có nhánh thắng nhánh kia",
chứ không tuyển theo cảm giác khó.

## Addendum C-1b — đóng băng 13/09, **trước** khi chạy

### Vì sao cần một đợt nữa, và vì sao nó **nhỏ hơn** chứ không lớn hơn

C-1 tốn ~6 giờ và chỉ cho **9 lượt có thông tin**: 6 task chạm trần ở cả hai
nhánh, 3 task bất khả ở cả hai nhánh, 3 task phân biệt được. Thêm task là mua
thêm phiên bị cắt; thêm **lượt trên đúng 3 task phân biệt được** là mua thêm
tín hiệu.

### Thiết kế

| | |
|---|---|
| task | `sec-1`, `sec-2`, `state-3` — ba task duy nhất có nhánh thắng nhánh kia ở C-1 |
| lượt | **6** mỗi task mỗi điều kiện (C-1 là 3) |
| điều kiện | `opencode` (AISEF) vs `opencode-bare`, khác đúng một thứ |
| model | **vẫn MiniMax-M2.7** sau alias `mycombo` (lời khai chủ dự án 13/09) — đây **không** phải cột 2 |
| bộ dữ liệu | **v1.4** (`sec-2` đã sửa đề bài; hai task kia không đổi byte) |
| trần lượt | `TRAN_LUOT = 0` như C-1 |
| chạy lại khi hạ tầng hỏng | khai **1 lần** (`INFRA_RETRIES = 1`) — **thực tế không nổ lần nào**, xem [B-4](BENCH-OBSERVATIONS-C1B.md): phiên bị cắt vẫn cho `ok=True` nên `exit_status_of` trả `"ok"`. Đã sửa 13/09 nhưng sau khi đợt đã khởi động, nên **cả 36 lượt của C-1b chạy theo đúng định nghĩa lượt của C-1** |
| tổng | 3 × 6 × 2 = **36 lượt** |
| thời gian ước tính | **≈ 3 giờ** — suy từ thời gian phiên trung vị của đúng ba task này ở C-1 (sec-1 6,1 · sec-2 3,6 · state-3 4,9 phút/phiên). Commit `5506ba8` nói "a third of the time" so với C-1; đúng hơn là **một nửa** (2,9 giờ so với 5,8) — sửa ở đây vì thông điệp commit đã đẩy |

### Thứ đổi so với C-1, và vì sao nó không phải "làm đẹp kết quả"

**Phiên chết vì hạ tầng được chạy lại một lần.** Ở C-1, 20/24 lượt trượt có một
phiên bị CLI cắt giữa chừng — model in cú gọi công cụ mà CLI không phân giải
được. Tính chúng là "lượt trượt của agent" là sai về bản chất, và nó làm **cả
hai** nhánh xấu đi chứ không thiên vị nhánh nào. Bản vá 13/09 khiến adapter gọi
tên đúng kiểu hỏng ấy (`infra`), và bench chạy lại **một** lần trên cây làm việc
mới, ghi `bench:infra_retry` vào bằng chứng.

Vì sao không phải là nới scorer: scorer (F2P/P2P trên test ẩn) **không đổi một
dòng**. Cái đổi là định nghĩa "một lượt" — và nó đổi theo hướng *khắt khe hơn*
với sản phẩm, vì nhánh AISEF là nhánh có nhiều phiên bị cắt hơn (31 % so với
25 %), nên nó là nhánh được lợi ít hơn từ việc bỏ các phiên chết. Ghi ra để
người đọc tự kiểm hướng thiên vị.

**Hệ quả so sánh:** C-1b **không so trực tiếp** với C-1 (khác định nghĩa lượt,
khác byte đề bài `sec-2`). Nó trả lời một câu hẹp hơn: *trên ba task từng phân
biệt được, với phiên hạ tầng đã loại, harness có đổi kết cục không?*

### Nơi ghi: `.bench-c1b/`, không phải `.bench/`

`materialize()` **xoá cây cũ** trước khi dựng cây mới, nên chạy C-1b với
`--attempts 6` trong `.bench/` sẽ xoá đúng ba cây làm việc mà báo cáo C-1 đang
trích dẫn làm bằng chứng (`a1`–`a3` của `sec-1`, `sec-2`, `state-3`). Đó là mất
dữ liệu đo, không phải dọn rác.

C-1b vì vậy chạy với `AISEF_BENCH_DIR=.bench-c1b`: cây làm việc và
`results.jsonl` riêng. Bằng chứng C-1 không bị chạm một byte, và mỗi cohort có
một sổ riêng — đọc bảng thì trỏ `AISEF_BENCH_DIR` vào đúng sổ của cohort ấy.

### Điều kiện dừng và cách đọc

- Dừng sớm nếu **cả hai** nhánh đạt 6/6 trên cả ba task: trần dữ liệu, báo và dừng.
- Đọc **theo từng task**, không theo một con số tổng: n = 6 vẫn quá nhỏ cho
  một hiệu số tổng.
- Kết quả null vẫn là kết quả và vẫn được báo.
