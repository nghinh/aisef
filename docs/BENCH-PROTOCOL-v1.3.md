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

**Điều kiện dừng sớm, chốt trước:** nếu hai task đầu của cột 2 đều 6/6 PASS ở cả
hai điều kiện thì model mới cũng chạm trần trên bộ dữ liệu này — dừng, báo, và
đừng đốt hai giờ nữa để lấy một cột toàn số 1,00. Trần dữ liệu là kết quả, và
nó phải được báo như một kết quả.
