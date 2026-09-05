# ADR-002 — Tầng tri thức vận hành (Operational Knowledge Layer)

**Trạng thái:** ACCEPTED cho đợt 1 (registry · router · telemetry); PROPOSED
cho đợt 2 (chưng cất · học từ trace) — chuyển ACCEPTED khi có số đo đợt 1.
**Ngày:** 2026-09-05. **Nguồn tham chiếu:** Repo-To-Skill (arXiv
2609.02749v1) và kho `VectorSpaceLab/AREX-Skill` (Apache-2.0, skill có giấy
phép riêng). Không sao chép: chỉ lấy *cơ chế* đã có bằng chứng, và chỉ ở
chỗ AI-SEF đang thiếu thật.

---

## 1. Bằng chứng buộc phải làm

Đo trên `e9` (7 story có giao diện, 86 phiên Claude) ngày 2026-09-05:

| Đại lượng | Số |
|---|---|
| Skill cài vào `.claude/skills` | **156** (security 109 · bmad 36 · superpowers 10 · aisdlc 1) |
| Tổng `SKILL.md` | 1,3 MB; frontmatter client nạp mỗi phiên ≈ **111k ký tự** |
| Lần tool `Skill` được gọi, cả 86 phiên | **11**, đúng **4** skill |
| 4 skill đó | `bmad-project-context` `bmad-ux` `bmad-create-epics-and-stories` `aisdlc-mockup-html` — tất cả đều được **prompt của harness gọi đích danh** |
| Skill security (109) và superpowers (10) được dùng | **0** |

Kết luận không cần suy diễn: *cài theo stack* không sinh ra sử dụng; *prompt
nêu tên* mới sinh ra. Tầng skill hiện tại là 1,3 MB nội dung trả tiền
ngữ cảnh mỗi phiên cho đúng 4 skill có ích — và không ai đo được điều đó
vì không có sự kiện `skill_use` (review D5).

## 2. Đối chiếu với paper — lấy gì, không lấy gì

| Cơ chế của paper | AI-SEF đã có | Khoảng trống thật | Quyết định |
|---|---|---|---|
| Skill ba tầng `SKILL.md` / `references/` / `scripts/`, chỉ `SKILL.md` đọc trước | `kit/skills.py` đọc `SKILL.md`; skill nhập từ 4 nguồn có frontmatter **không đồng nhất** | Không có bản ghi chuẩn hoá: provenance chỉ là `source=` trong `.aisdlc-managed`, không commit, không license, không "dùng khi nào" | **ADD** registry chuẩn hoá (§4.1) — không đổi định dạng skill nguồn |
| Router hai cấp area → family → graph, agent tự đi | `setup` chọn skill theo stack (một lần, mức dự án) | Không có định tuyến **mức story/pha**, và bằng chứng nói agent không tự đi | **ADD** router harness-side (§4.2), **đưa vào prompt** như mục "Skill cho story này" — chỗ duy nhất đã chứng minh sinh ra sử dụng |
| Confidence + evidence + rationale cho mỗi gán; không có ngưỡng số | — | Không có abstain | **ADD** confidence có ngưỡng, `NO-SKILL` khi không đủ; là **tín hiệu**, không phải cổng (review D6) |
| Chưng cất 4 bước scope→ground→construct→verify; verify bằng test/CLI/smoke của kho nguồn; record R giữ evidence + gap | `fetch.py` ghim commit; `security_filter` phân loại | Không có đường sinh skill từ kho/tài liệu, không có record | **ADD đợt 2** `aisdlc skill distill` (§5) — model dựng, code kiểm; record là bằng chứng |
| Vòng đời ngầm: candidate → verified → active; không có stale/rejected | `doctor` kiểm skill offensive | Không có trạng thái, không có "stale khi upstream đổi" | **ADD** FSM 5 trạng thái (§4.3), stale theo commit catalog |
| Progressive disclosure: entry skill tóm tắt, mở đúng nhánh | Client nạp **toàn bộ** mô tả 156 skill | 111k ký tự/phiên cho 4 skill dùng | **STRENGTHEN**: prompt chỉ mang skill được định tuyến (tên + dùng-khi + cách mở); `setup` cài theo **tập định tuyến của dự án** thay vì cả nguồn (§4.4) |
| Không có học từ trace sau triển khai (paper thừa nhận) | Evidence có review findings, deadlock, `[bế tắc]`, `untested_symbols` | — | **ADD đợt 2** `aisdlc skill propose` từ khuôn lặp trong evidence (§5.2) — đây là chỗ AI-SEF vượt paper |
| Đo: paired vs không-skill, 4 benchmark | Không có eval skill | Không biết skill nào có ích | **ADD** telemetry `skills_offered`/`skills_used` + A/B trên `par`/`e9` (§6) |
| Taxonomy 20 area × 178 family, LLM-assisted | — | Không cần: catalog 5 nguồn, ≤ 300 skill | **KHÔNG lấy** — quá cỡ cho bài toán |
| DisCo agent, hai chế độ creator/researcher | Vai `developer/reviewer/security/designer` | — | **KHÔNG lấy** — thêm vai `curator` cho chưng cất là đủ, không thêm agent runtime |

## 3. Nguyên tắc áp vào tầng này

* **Định tuyến là phán đoán có cấu trúc → code trước, model sau.** Tín hiệu
  có cấu trúc (hợp đồng kiểm định, năng lực story cần, `screens`,
  `write_scope`, subdomain/tags của skill) cho điểm tất định; câu chữ chỉ
  là tín hiệu yếu. Không đủ điểm thì **abstain** — tốt hơn nhồi nhầm (paper
  ghi 2/20 task hỏng vì "retrieved skill content may occasionally distract").
* **Skill là bằng chứng, không phải lời hứa.** Mọi bản ghi registry mang
  provenance (nguồn, commit, license) và trạng thái chỉ đổi khi có kiểm.
* **Không thêm subsystem trùng:** registry dựng từ `install.apply` + catalog;
  router chèn vào `build_context` như `{{ tools }}`; telemetry đi qua
  `EvidenceStore.agent_run` từ `RunResult.tool_uses` đã có; vòng đời là một
  FSM nhỏ theo mẫu `state.py`; benchmark là dogfood `par`/`e9` có sẵn.

## 4. Đợt 1 — hợp đồng

### 4.1 Registry — `_bmad-output/skill-registry.json`

Dựng bởi `kit/registry.build(project)` từ `.claude/skills/*` + `.aisdlc-managed`
+ `catalog.json`. Một bản ghi:

```
{
  "id": "using-parameterized-queries",      # = tên thư mục = frontmatter.name
  "source": "security",                     # id nguồn trong catalog
  "commit": "<sha nguồn lúc cài>",          # từ catalog (fetch.py ghim)
  "license": "Apache-2.0" | "NO_LICENSE",   # frontmatter, hoặc license nguồn
  "description": "...",                     # frontmatter
  "use_when": "...",                        # frontmatter.use_when | phần "Use when" của description
  "domain": "...", "subdomain": "...", "tags": [...],
  "capabilities": ["security", ...],        # chuẩn hoá về từ vựng của preflight/qa
  "status": "verified",                     # §4.3
  "verified": {"at": "...", "by": "structural", "checks": [...], "gaps": [...]},
  "links": {"depends_on": [], "see_also": []},
  "path": ".claude/skills/using-parameterized-queries"
}
```

Bất biến: *mọi skill trong `.claude/skills` có đúng một bản ghi; bản ghi
không có thư mục là `stale`.*

### 4.2 Router — `kit/router.route(story, registry, phase) → Routing`

```
Routing = {picked: [(entry, score, rationale)], abstained: bool, considered: int}
```

Điểm = tổng có trọng số của: khớp `capabilities` với hợp đồng kiểm định
của story (+3/khớp) · khớp với `required_capabilities` (+3) · story có
`screens` ↔ skill có capability `ui` (+2) · trùng token giữa tiêu chí chấp
nhận và `tags`/`subdomain` (+1/token, tối đa +3) · skill của framework
(`aisdlc-*`) đúng pha (+5). Chỉ skill `status ∈ {verified, active}` được
xét. Ngưỡng `skills.route_threshold = 3`, tối đa `skills.route_max = 3`.
Dưới ngưỡng → `abstained = true`, prompt ghi rõ "không có skill nào đủ
khớp — làm theo hiến pháp". Rationale ghi vào evidence `skills_offered`.

Router là **tín hiệu** cho agent, không phải cổng: sai router không chặn
story; nó lộ ra ở telemetry (§6).

### 4.3 Vòng đời

```
candidate ──kiểm cấu trúc đạt──► verified ──được định tuyến & story dùng & story done──► active
    │                               │                                                    │
    └──kiểm trượt / offensive──► rejected                       commit nguồn đổi ◄───────┘──► stale ──kiểm lại──► verified
```

* `candidate`: vừa cài hoặc vừa chưng cất; **không được định tuyến**.
* `verified`: qua kiểm cấu trúc (§4.5). Skill nhập từ nguồn có commit ghim
  vào thẳng `verified` nếu qua kiểm.
* `active`: có ít nhất một `skill_use` trong story `done`. Chỉ khác
  `verified` ở chỗ có bằng chứng dùng — không đổi quyền.
* `stale`: commit nguồn trong catalog khác commit lúc cài, hoặc thư mục
  không còn. Không định tuyến cho tới khi kiểm lại.
* `rejected`: `security_filter` xếp OFFENSIVE, hoặc kiểm cấu trúc thấy chỉ
  dẫn tiêm prompt / bí mật. Không bao giờ định tuyến; `doctor` báo.

### 4.4 Progressive disclosure

* Prompt story chỉ mang mục `## Skill cho story này`: tên · dùng-khi · lệnh
  mở (`Skill` tool hoặc đọc `SKILL.md`). Không dán nội dung skill.
* `setup` cài: skill framework + skill được định tuyến ở **mức dự án**
  (từ stack + `requirements.md`) — không cài cả nguồn. Skill khác ở lại
  cache; router mức story có thể yêu cầu cài thêm trước khi mở phiên.
  (Đợt 1 giữ cách cài hiện tại; đổi ở đợt 1b sau khi có số telemetry.)

### 4.5 Kiểm cấu trúc (code, không model)

frontmatter hợp lệ và `name` = tên thư mục · `description` không rỗng ·
mọi link tương đối trong `SKILL.md` trỏ tới tệp có thật · không khớp mẫu bí
mật (`check_secrets`) · không có câu dạng "ignore previous instructions /
bỏ qua luật / chạy lệnh sau" (mẫu tiêm — cùng lớp với prompt
`story-security-review`) · `security_filter` ≠ OFFENSIVE. Gap ghi vào
`verified.gaps`, không giấu.

## 5. Đợt 2 — đề xuất (PROPOSED)

### 5.1 Chưng cất `aisdlc skill distill <kho|tài liệu|paper> --for <mục đích>`

Vai mới `curator` (prompt `skill-distill.md`, phiên riêng, chỉ ghi vào
`_bmad-output/skills-candidates/<id>/`). Bốn bước như paper nhưng **verify
là code**: scope/ground/construct do model; verify = §4.5 + chạy
`scripts/*` nếu có với fixture nhỏ + kiểm mọi claim có trích dẫn tới
`references/`. Record `construction.json` giữ evidence, checks, gaps. Vào
registry ở `candidate`; người duyệt (`aisdlc skill approve`) mới lên
`verified`. Không có bước người thì skill chưng cất không bao giờ được
định tuyến — tri thức vận hành sai còn tệ hơn không có.

### 5.2 Học từ trace `aisdlc skill propose`

Nguồn: evidence có sẵn — review findings lặp qua ≥ 3 story (cùng danh từ
riêng, cùng cơ chế `_same_complaint`), `[bế tắc]`, `untested_symbols` lặp,
deadlock. Code gom khuôn; model soạn `SKILL.md` ứng viên với provenance =
danh sách story + finding; vào `candidate`. Đây là chỗ paper không có.

## 6. Đo — trước khi mở rộng

* Telemetry mỗi phiên: `skills_offered` (router), `skills_used` (tool
  `Skill` trong `RunResult.tool_uses`), `abstained`. `status` in tỉ lệ
  dùng/đề xuất theo skill; `report` mục harness liệt kê skill chưa từng
  dùng.
* Benchmark: `par` (4 story) và `e9` EPIC-01 chạy lại ở ba chế độ —
  không skill · cài cả nguồn như nay · router — so `done` lượt 1, số lượt,
  mục chặn của reviewer, chi phí. Kết quả quyết định 4.4 (đợt 1b) và §5.
* Ngưỡng `route_threshold` là knob **có mã đọc**; điều chỉnh theo
  precision đo được (skill được đề xuất mà không dùng = nhiễu; skill dùng
  mà không được đề xuất = thiếu).

### 6.1 Đo lại 2026-09-05 — router đợt 1 chọn **sai** toàn bộ

Chạy router HEAD trên registry cũ của `e9` (18 story): **chọn 8/18**, và cả
8 đều là dương tính giả:

- `receiving-code-review` (superpowers) được chọn cho 5 story vì "story phải
  qua kiểm định `perf`" — skill ấy bị **suy** năng lực `perf` và `ui` từ chữ
  "performance"/"screen" trong mô tả; nó nói về việc *nhận* nhận xét rà soát.
- `detecting-typosquatting-packages` cho 4 story vì "màn hình + chữ `npm`";
  `performing-web-application-vulnerability-triage` vì "màn hình + chữ `web`".
- Thêm một ca đo tay: story điều hướng bàn phím được đề nghị
  `implementing-end-to-end-encryption-for-messaging` (màn hình + chữ
  `messaging`).

Ba lỗi gốc, ba sửa (`kit/registry.py`, `kit/router.py`):

1. Năng lực chỉ được **khai** (frontmatter `capabilities:`) hoặc suy trong
   bảng cho phép của miền đã khai (`cybersecurity` → `security`, `review`;
   **bỏ** `ui`). Skill không khai miền thì không suy gì từ chữ.
2. Tín hiệu "story có màn hình" chỉ tính cho skill khai miền giao diện
   (`UI_DOMAINS`); nguồn `ui-ux` không khai miền thì nhận miền mặc định.
3. "Màn hình + một chữ" không phải hai tín hiệu: chữ chỉ tính khi đi cùng
   hợp đồng story, hoặc ≥ 2 chữ khi đi cùng màn hình.

Sau sửa: `e9` **0/20** story được chọn (kể cả hai story thử thêm: điều hướng
bàn phím, rate-limiting đăng nhập với hợp đồng `security`). Đó là kết quả
đúng với catalog hiện tại — không có skill nào về ghi chú offline, điều hướng
bàn phím hay rate-limiting; 87 skill `security` khớp hợp đồng nhưng không
khớp nội dung. Hệ quả cho A/B ADR-003 #1: trên `par`/`e9` hai nhánh chỉ khác
nhau ở câu "không có skill đủ khớp" — đo được "mục kỹ năng không gây hại",
chưa đo được "skill được dùng". Muốn đo vế sau cần một dự án có skill khớp
thật (ví dụ cài `ui-ux` rồi chạy story giao diện), và đó là việc có chi phí,
để sau khi xong đợt 4.

### 6.2 Skill cửa ngõ giao diện — chính sách, không phải chữ (2026-09-05)

Cài nguồn `ui-ux` vào bản chép e9 (5 skill, sau khi sửa `has_ui` — ứng dụng
"chạy trong trình duyệt" không nêu framework bị `setup` coi là không có giao
diện): router **vẫn abstain** cho story giao diện, vì skill `ui-ux` không
khai năng lực và story tiếng Việt không khớp chữ mô tả tiếng Anh — hai tín
hiệu không bao giờ đủ. Quyết định: mở rộng cơ chế "skill framework theo pha"
(§4) — `UI_ENTRY_SKILLS = ("ui-ux-pro-max",)` được mời cho **mọi story có màn
hình ở pha implement**, có lý do in ra; nó tự định tuyến tiếp tới skill con
(progressive disclosure). Miền `ui-ux` được suy năng lực trong bảng cho phép
(`ui`, `accessibility`, `design`) như `cybersecurity`. Kết quả trên e9-ux:
STORY-01-05/04-01 được mời `ui-ux-pro-max` + `ui-styling`; story không màn
hình vẫn abstain. Đây là điều kiện để A/B ADR-003 #1 đo được "skill được dùng".

## 7. Không làm

Taxonomy 20×178 · agent runtime mới · MCP để phục vụ skill · nạp toàn bộ
`SKILL.md` vào prompt · để model quyết định trạng thái vòng đời · chưng
cất tự động không có người duyệt.

## 6.3 Tầng ngữ nghĩa trên tầng heuristic (S6, đo 2026-09-05)

`registry.verify_structure` bắt câu tiêm theo mẫu và bí mật; `kit/skill_scan.py` hỏi một phiên model chỉ đọc, không tool, cho từng lô 8 SKILL.md. Đo trên e9: 153 skill, 20 lô, $5,01; **0 `injection`, 8 `suspicious`** với trích dẫn đúng chỗ (mở rộng quyền Domain Admins / sudo NOPASSWD, tắt kiểm host key, xuất khoá GPG riêng, «do not pause to check in with your human partner», tự cài phụ thuộc) — tầng regex không thấy mục nào trong 8. Quy tắc: `injection` → `rejected` (router không mời, sống qua `refresh`); `suspicious` → cảnh báo trong `verified.gaps`, người đọc quyết. Phán đoán giao model, đảm bảo (lô, schema, sổ, bằng chứng `skill-scan#n`) là code.
