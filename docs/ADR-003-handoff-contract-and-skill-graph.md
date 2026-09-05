# ADR-003 — Bàn giao có hợp đồng và đồ thị kỹ năng: đối chiếu Repo-To-Skill, AREX-Skill, OpenAI Swarm

**Trạng thái:** PROPOSED — từng mục ADOPT/ADAPT chuyển ACCEPTED khi có test
đỏ-khi-hoàn-nguyên **và** số đo so với baseline (§6). Mở rộng ADR-002.
**Ngày:** 2026-09-05. **Yêu cầu:** "chỉ bổ sung những gì thực sự tạo thêm giá
trị, không tạo subsystem trùng lặp, không thay đổi các bất biến cốt lõi".

Nhãn: **FACT** = đọc được từ nguồn hoặc từ mã (kèm tệp:dòng); **INFER** =
suy luận; **REC** = khuyến nghị.

---

## 1. Nguồn đã đọc — cái gì là sự thật

### 1.1 Paper Repo-To-Skill (arXiv 2609.02749v1) — FACT

- Định tuyến: "the model starts with the router description, follows the
  relevant area-to-family path, opens the selected repository graph, and
  loads only the skills, references, or scripts needed for the current
  step". Từ chối khớp yếu: "Keyword-only, dependency-only,
  optional-integration, and example-only matches are rejected". Không ép
  đường: "does not force a route when no family is a close fit". **Không
  có ngưỡng số** cho confidence — chỉ đòi "a rationale, repository evidence,
  and confidence".
- Kiểm trước khi nhận: "DisCo checks each graph's content and usability
  using assertion-backed cases and safe repository-native examples, tests,
  CLI checks, tiny-fixture checks, or smoke scripts when available"; "No
  skill is admitted on the strength of its sources alone". Construction
  record giữ "the evidence used, the checks performed, and any unresolved
  gaps".
- Đo: MLE-bench 75 task, any-medal 72,89 % có skill / 31,11 % không;
  PaperBench 20 task 39,59 / 29,45; FrontierCS 188 task 77,14 / 70,63;
  PassNet 200 task 1,531 / 1,343. Baseline là *cùng agent, không skill*;
  **không** có baseline "kho nguồn nhét thẳng vào ngữ cảnh" hay "retrieval".
- Giới hạn tự khai: không học từ trace sau triển khai; skill là snapshot
  tĩnh; xây ~$40/kho; 2 task PaperBench **giảm** khi thêm skill ("may
  occasionally distract"); kho không khớp family thì để "unclassified".
- Đa agent **không** thuộc phương pháp: "The harness still governs how the
  agent researches, while skills determine what it knows when research
  begins". Trên FrontierCS, 102 task không gọi sub-agent vẫn lãi 5,54 điểm.

### 1.2 AREX-Skill (github.com/VectorSpaceLab/AREX-Skill) — FACT

- 5 000+ skill, 1 000 kho, 20 area, 178 family. Bố cục
  `skills/repositories/repo-skills/<repo>/` với `SKILL.md`, `references/`,
  `scripts/`. Có router + catalog; metadata gồm license, source commit,
  routing, provenance, version. Có hướng dẫn "Refreshing Repo Skills".
- Apache-2.0 ở mức kho; **license từng skill là thẩm quyền** (theo
  SKILL.md); DisCo CLI MIT.

### 1.3 OpenAI Swarm (github.com/openai/swarm) — FACT

- Nguyên thuỷ: `Agent(name, model, instructions, functions, tool_choice)`;
  **bàn giao = hàm trả về một Agent** (`return sales_agent`);
  `context_variables` là dict chảy qua mọi hàm; `Result(value, agent,
  context_variables)`; `Response(messages, agent, context_variables)`.
- Vòng chạy: "runs (almost) entirely on the client and… does not store
  state between calls"; lỗi gọi hàm thì "an error response will be appended
  to the chat so the Agent can recover gracefully"; có `max_turns`.
- Không có: lưu trạng thái, bộ nhớ, guardrail. Tự nhận "Educational
  framework"; **đã ngừng** — "Swarm is now replaced by the OpenAI Agents
  SDK". MIT.

---

## 2. Hiện trạng AI-SEF — cái gì đã có (FACT, tệp:dòng)

### 2.1 Hướng 1 — tri thức vận hành

| Đã có | Ở đâu |
|---|---|
| Đọc skill 3 lớp (`SKILL.md` + `references/` + `scripts/`), frontmatter không PyYAML | `kit/skills.py` |
| Nguồn ghim commit, license, tải về `~/.cache/ai-sdlc/references` | `kit/catalog.json`, `kit/fetch.py` |
| Registry: `SkillEntry` (provenance `commit`, `license`, `status`, `verified`), vòng đời `candidate→verified→active→stale→rejected`, **không** có cạnh vào `verified` mà không qua kiểm, không có cạnh ra khỏi `rejected`; `stale` khi commit đổi hoặc thư mục mất | `kit/registry.py` |
| Kiểm cấu trúc trước khi nhận: frontmatter, tên = thư mục, link tương đối tồn tại, không secret, không câu injection, lọc offensive | `kit/registry.py:verify_structure` |
| Router hai tín hiệu (paper §4.2 từ chối keyword-only), **abstain**, ngưỡng 3 / tối đa 3, skill framework theo pha, chỉ đưa tên/`use_when`/đường dẫn (progressive disclosure) | `kit/router.py` |
| Lệnh `aisdlc skill [--story]` | `cli.py:961` |
| Baseline đã đo: e9 **11 lượt gọi Skill / 86 phiên**; router trên 18 story e9: abstain 13/18 sau khi sửa dương tính giả (ADR-002 §1, §6) | `docs/ADR-002` |

**Chưa có:** router chưa nối vào prompt story; chưa có telemetry
`skills_offered`/`skills_used`; kiểm trước khi nhận chỉ là **cấu trúc**, chưa
chạy được gì; không có chưng cất; không có đề xuất skill từ trace.

### 2.2 Hướng 2 — bàn giao và điều phối

| Đã có | Ở đâu |
|---|---|
| Mỗi vai là **phiên mới**; `build_spec` **từ chối** `session_id` cho vai rà soát/bảo mật; reviewer READ_ONLY, cấm Write/Edit | `harness/routing.py:25–134` |
| Ranh giới ngữ cảnh có kiểm: `Prompt.render` ném `PromptError` khi thiếu slot, và khi slot rỗng trừ `allow_empty` | `harness/prompts.py:62–69` |
| Hợp đồng thực thi một lượt: tool cấm, thư mục, env (scope, story, workdir), model theo vai, `max_turns`, timeout | `clients/base.py:RunSpec` |
| Gói cho người rà soát dựng **từ đĩa**: story + hợp đồng + kiến trúc (`build_context`), diff từ git (`review_diff`), impact từ mã (`analyse_impact`) — **không** có văn bản của developer | `phases/implement.py:409–428` |
| Vòng lượt: `attempt.infra` có hạn mức riêng, `plan_defects` (reviewer đã kiểm chứng bế tắc), `deadlock_reason` (cùng ngữ cảnh → cùng kết quả), feedback = cổng + tối đa 10 finding | `phases/implement.py:800–880` |
| Đồ thị thực thi (epic tuần tự; trong epic theo đợt: không phụ thuộc + không đụng write_scope) **tách** khỏi FSM trạng thái và sổ nhật ký | `control/scheduler.py`, `control/state.py`, `control/journal.py` |
| Cách ly thân cây: HEAD trước/sau mỗi lượt; người rà soát sửa cây → hoàn nguyên + không tính lượt | `phases/implement.py:_head_of`, `_revert_reviewer_writes` |

**Sai lệch tài liệu (FACT):** `docs/SOLUTION.md:122, 251` nêu
`harness/subagent.py` — tệp **không tồn tại**; EXECUTION-PLAN 6.6 ghi đã gộp
vào `routing.py`. `Capability.SUBAGENT` khai NATIVE cho cả hai client
(`clients/claude_code.py:68`, `clients/opencode.py:56`) nhưng harness không
dùng.

---

## 3. Đối chiếu từng ý — lấy gì, không lấy gì

Cột "Chứng minh" là điều kiện để mục đó chuyển ACCEPTED.

### Hướng 1 — Operational Knowledge / Skill Graph

| # | Ý tưởng | Nguồn | Hiện có | Quyết định | Vì sao | Chứng minh |
|---|---|---|---|---|---|---|
| 1 | Router phân cấp + progressive disclosure, nối vào phiên agent | Paper §routing; AREX router | Router có, **chưa nối vào prompt** | **ADOPT** — nối `route()` vào prompt developer (mục "Kỹ năng có sẵn", tên + `use_when` + đường dẫn); ghi `skills_offered` + `abstained` vào `AGENT_RUN.detail`; `skills_used` = tên tool `Skill` trong luồng | Không nối thì cả tầng không có tác dụng, và **không đo được gì** — đây là tiền đề của mọi mục còn lại | A/B trên `par` (4 story × 2 nhánh có/không mục kỹ năng): `skills_used`/phiên, chi phí, số lượt, cổng qua. Quy tắc: bật mặc định chỉ khi cổng qua ≥ baseline và chi phí ≤ +15 % |
| 2 | Kiểm **chạy được** trước khi nhận (repo-native tests/CLI/smoke) | Paper §verify | Chỉ kiểm cấu trúc | **ADAPT (mức V1: biên dịch được)** — `verified` đòi thêm: mọi tệp trong `scripts/` phải parse được (`py_compile`, `sh -n`, `node --check`); ghi `Verification.checks[]`. Chạy thật (`--help` trong sandbox) để sau — §5.2 nói vì sao | Paper: "No skill is admitted on the strength of its sources alone" — cấu trúc đúng ≠ dùng được, cùng lớp lỗi với hook biên dịch đúng cú pháp mà client không chạy (G6) | Unit test: skill có script hỏng → ở lại `candidate`; đỏ khi hoàn nguyên. Số: bao nhiêu skill của `par`/`e9` rớt vì script không parse được |
| 3 | Construction record R | Paper §distill | — | **PROPOSED** (giữ ADR-002 §5) | Chỉ có nghĩa khi có chưng cất; chưng cất ~$40/kho theo paper, còn baseline dùng skill của ta là 11/86 phiên — chưa đáng | Sau khi #1 đo xong |
| 4 | Provenance / version / freshness | AREX metadata + refresh | Có: `commit`, `license`, `stale` khi commit đổi, `Registry.refresh` | **KEEP** — không thêm cơ chế | Đủ; catalog ghim commit là "version" | — |
| 5 | Confidence + abstain | Paper §routing | Có: điểm + rationale + abstain; paper cũng **không** dùng ngưỡng số | **KEEP**; thêm `abstained` vào telemetry (thuộc #1) | Đúng như paper | — |
| 6 | Taxonomy 20 area / 178 family | AREX | — | **REJECT** | Miền của ta là pha SDLC × stack; `domain/subdomain` trong registry đã đủ; taxonomy to là chi phí bảo trì, không phải giá trị | — |
| 7 | Học từ failure/recovery để đề xuất skill | Yêu cầu chủ đầu tư (paper **không** làm) | Evidence có `review_findings`, `[bế tắc]`, `GUARD_BLOCK`, `deadlock` | **PROPOSED → thí nghiệm offline** — `aisdlc skill propose`: gom finding lặp ở ≥2 story thành bản nháp SKILL.md `candidate`, provenance = id sự kiện; **không bao giờ** tự lên `active` | Đây là chỗ AI-SEF vượt paper, nhưng phải có khuôn lặp thật trước đã | Chạy offline trên evidence `par` + `e9` hiện có; ADOPT chỉ khi ra ≥1 cụm mà người đọc thấy đáng viết thành skill |

### Hướng 2 — Handoff / Multi-agent Orchestration

| # | Ý tưởng | Nguồn | Hiện có | Quyết định | Vì sao | Chứng minh |
|---|---|---|---|---|---|---|
| 8 | Bàn giao bằng "hàm trả về Agent" (model quyết ai chạy tiếp) | Swarm | Harness quyết (FSM + vòng lượt) | **REJECT** | Đối tượng bị giám sát sẽ chọn người giám sát mình — vi phạm "không để đối tượng bị giám sát tự giám sát" và "reviewer ≠ developer" | — |
| 9 | Handoff Contract hạng nhất | Swarm/Agents SDK | Hợp đồng đã có ở mức slot (`build_spec` + `Prompt.render` + `RunSpec`) nhưng **không ghi lại** ai nhận gì | **ADAPT** — sự kiện evidence `HANDOFF {from, to, attempt, slots: {tên: nguồn, ký tự}, truncated}` ghi khi dựng spec cho vai; báo cáo hiện chuỗi `dev#1 → reviewer → security → cổng ✗ → dev#2` | Thứ còn thiếu là **kiểm chứng được**: hôm nay không thể trả lời "người rà soát đã thấy gì" từ đĩa. Bất biến máy kiểm: gói cho reviewer/security chỉ có nguồn ∈ {git, code, artifact} — **không** có lời của developer | Test: mọi slot của reviewer/security có nguồn hợp lệ; đỏ khi cố đưa `result.text` vào. `test_meta`: kind có producer |
| 10 | Context Packet có schema riêng | Swarm `context_variables` | `Prompt.render` kiểm slot | **ADAPT gộp vào #9**, **REJECT** tầng schema mới | Slot đã là schema; thứ thiếu là **nguồn** của từng slot, không phải kiểu dữ liệu | Thuộc #9 |
| 11 | Execution/Handoff graph tách khỏi lifecycle graph | Agents SDK | Đã tách: scheduler ↔ FSM ↔ journal | **KEEP**; #9 làm đồ thị bàn giao **quan sát được** theo story | Không cần cấu trúc mới | — |
| 12 | Structured tool-error recovery | Swarm "append error to chat" | Client đã làm y thế với guard (stderr về agent); harness tách `infra` khỏi chất lượng, có `deadlock`, `plan_defects` | **KEEP**, REJECT cơ chế mới | Của ta mạnh hơn Swarm ở đúng chỗ Swarm không có (hạn mức riêng, phát hiện bế tắc) | — |
| 13 | Minimal orchestration kernel | Swarm run loop | `implement_story` + `run_epic` | **REJECT** như runtime | Swarm là vòng chat trong tiến trình; ta là CLI một-lượt, không daemon, mỗi vai một tiến trình client | — |
| 14 | `context_variables` chia sẻ, thay đổi được giữa các agent | Swarm | Gói dựng lại từ đĩa cho mỗi vai | **REJECT** | Dict chung là đúng con đường để lời khai của developer rò sang reviewer thành "sự thật" | — |
| 15 | Sub-agent do agent sinh | `Capability.SUBAGENT` | Khai NATIVE, không dùng | **REJECT cho V1**; giữ khai báo, ghi rõ "chưa dùng" | Paper: lợi ích skill không phụ thuộc sub-agent; vai-phiên-riêng của ta đã là "sub-agent" dưới quyền harness — và guard hook của client có chạy cho sub-agent không là điều **chưa kiểm** | Nếu sau này dùng: phép hợp quy C6 "sub-agent có qua guard" trước |

---

## 4. Bất biến giữ nguyên — và từng mục ADOPT/ADAPT tôn trọng thế nào

| Bất biến | #1 router vào prompt | #2 kiểm chạy được | #9 HANDOFF |
|---|---|---|---|
| 6 nhóm harness | thuộc `kit`/`context` | thuộc `kit` | thuộc `observe` |
| Evidence-first | ghi `skills_offered/used`, không tin lời agent | `Verification.checks` là kết quả chạy | sự kiện từ harness, không từ agent |
| Phiên mới mỗi story/vai | không đổi | — | không đổi |
| Reviewer ≠ developer | mục kỹ năng chỉ vào prompt developer | — | **được máy kiểm** (nguồn slot) |
| Guard phía harness, worktree, cổng người | không chạm | script chạy READ_ONLY sandbox | không chạm |
| CLI một lượt, không daemon | không chạm | không chạm | không chạm |
| Không tin client | `skills_used` đọc từ luồng, chỉ có ở client `MACHINE_OUTPUT` NATIVE (OpenCode: "không đo được", không giả vờ) | — | — |
| Router là **tín hiệu**, không phải cổng (ADR-002 §3) | giữ: abstain thì prompt không có mục | — | — |

---

## 5. Hợp đồng — cho ba mục sẽ làm

### 5.1 #1 Router vào prompt + telemetry
- `phases/implement.py:build_context` thêm slot `skills` = `Routing.prompt_section()`
  hoặc rỗng khi abstain (`allow_empty`). Prompt `story-implement.md` thêm
  mục "## Kỹ năng có sẵn" với câu: *chỉ mở khi cần; không đọc hết*.
- `observe.agent_run` nhận `skills_offered: list[str]`, `abstained: bool`;
  `skills_used` = tên `input.skill` của tool `Skill` trong `tool_uses`
  (Claude); OpenCode: `[]` + `skills_measurable=false`.
- Cấu hình `skills.offer` (mặc định **off** cho tới khi A/B xong).
- Test: prompt có mục khi router chọn, không có khi abstain; evidence ghi
  đúng; đỏ khi hoàn nguyên. `aisdlc status` in tỉ lệ `used/offered`.

### 5.2 #2 Kiểm scripts trước khi nhận — mức V1: **biên dịch được**, không chạy
- Số đo đổi quyết định: `par` có 120 skill / **148** tệp scripts, `e9` 156 /
  **201** (phần lớn `agent.py` của cybersecurity-skills). Chạy `--help` từng
  tệp trong sandbox với timeout 30 s là tới ~100 phút ở trường hợp xấu, và
  chạy script bên thứ ba trên host khi không có Docker là điều harness
  không được làm. Vì thế V1 kiểm **cú pháp**: `.py` → `py_compile`, `.sh` →
  `sh -n`, `.js/.mjs` → `node --check` (không có node thì không kết luận).
- `registry.verify_structure` thêm check `scripts: <n> tệp biên dịch được`;
  hỏng → gap `✗ scripts không biên dịch được: …` → ở lại `candidate`.
- Đây là mức thấp hơn paper ("assertion-backed cases … smoke scripts") và
  được ghi rõ là `ponytail:` — nâng lên smoke `--help` trong sandbox khi có
  hạng mục đo riêng và Docker là điều kiện tiên quyết.
- Test: `scripts/run.py` chứa `def (:` → không `ok`; script lành → có check.

### 5.3 #9 HANDOFF
- `observe.HANDOFF = "handoff"`; `EvidenceStore.handoff(story, *, frm, to,
  attempt, slots: dict[str, tuple[str, int]], truncated: list[str])`.
- Ghi ở `run_attempt` (→developer), `review_story` (→reviewer),
  `security_review` (→security). Nguồn hợp lệ: `artifact`, `git`, `code`,
  `gate`, `review`, `config`, `router`. Bất biến (test): với `to ∈ {reviewer,
  security}` không slot nào có nguồn `agent`.
- `report.py` mục "Chuỗi bàn giao" mỗi story.

---

## 6. Đo — trước khi mở rộng

| Mục | Baseline (đã có) | Số đo sau | Ngưỡng ACCEPT |
|---|---|---|---|
| #1 | e9: 11 Skill/86 phiên; par: 0 mục kỹ năng | par 4 story × {off, on}: `used/offered`, $/story, lượt, cổng qua | cổng qua ≥ baseline **và** $ ≤ +15 %; nếu `used` = 0 thì tắt mặc định và ghi lý do |
| #2 | registry hiện tại: X `verified` chỉ bằng cấu trúc | X' sau kiểm chạy; danh sách skill rớt | không có ngưỡng — mục này là *đúng đắn*, không phải *hiệu quả* |
| #9 | không có sự kiện | 100 % lượt có HANDOFF; 0 slot nguồn `agent` ở reviewer/security | bất biến, không phải số đo |
| #7 | — | số cụm finding lặp trên par + e9 | ≥ 1 cụm đáng viết thành skill → mở ADR-002 §5.2 |

Ngân sách: A/B #1 ≈ $4 (trong $120–180 đã duyệt).

---

## 7. Không làm (và vì sao, một dòng)

- Swarm làm runtime — đã ngừng phát triển, giáo dục, không có guardrail.
- Sub-agent do agent sinh — chưa có bằng chứng guard chạy cho sub-agent.
- Dict ngữ cảnh chung giữa các vai — kênh rò lời khai.
- Taxonomy area/family — miền khác, chi phí bảo trì không có người trả.
- Chưng cất kho → skill ($40/kho) — trước khi #1 chứng minh skill được dùng.
- Ngưỡng confidence số — paper cũng không; ta có abstain + rationale.

## 8. Sửa tài liệu

- `docs/SOLUTION.md:122, 251`: bỏ `harness/subagent.py`; ghi "mỗi vai là
  một phiên riêng do harness gọi (`harness/routing.py`)".
