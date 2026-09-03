<!--
CANONICAL REQUIREMENTS — AI-SDLC Engineering Framework (AI-SEF)
Hợp nhất 2026-09-03 từ:
  - Bản đầu bài đầy đủ (54 mục): docs/requirements/full-brief.md
  - Bản chi tiết §12/§12A (bổ sung sau): docs/requirements/section-12-12A-detailed.md
Quy tắc: §12 ngắn trong bản đầy đủ được THAY bằng §12/§12A chi tiết. §12+12A là bổ sung, KHÔNG thay §1–11.
Ứng viên bổ sung nêu ở bảng §12 đầy đủ nhưng CHƯA nghiên cứu: "Addy Osmani Agent Skills" (candidate — qua scorecard §52 trước khi dùng).
Đây là source of truth cho traceability (North-Star §4). Không sửa nội dung gốc; chỉ hợp nhất.
-->

# ĐẦU BÀI XÂY DỰNG AI-SDLC ENGINEERING FRAMEWORK

## 1. Tên bài toán

**Nghiên cứu, thiết kế và xây dựng AI-SDLC Engineering Framework phục vụ phát triển phần mềm end-to-end bằng AI Coding Agents**

Tên gọi tạm thời: **AI Software Engineering Factory – AI-SEF**.

Framework phải cung cấp một phương pháp luận, bộ công cụ và agent harness thống nhất cho phép chuyển đổi:

**Business Idea / requirements.md → Product Specification → Architecture → UX/CX → Epics/Stories → Source Code → Verification → Security → Deployment → Operation → Support → Continuous Improvement**

trên nhiều AI development environment khác nhau như Claude Code, OpenCode, Google Antigravity, Codex và các nền tảng tương thích Agent Skills/MCP khác.

---

# 2. Bối cảnh và vấn đề cần giải quyết

Các AI coding agent hiện nay có khả năng sinh code rất mạnh nhưng tồn tại một số vấn đề cơ bản:

- dễ bắt đầu coding trước khi hiểu đầy đủ yêu cầu;
- tự đưa ra assumption mà không quản trị assumption;
- mất context giữa các session;
- thiếu tính nhất quán giữa PRD, architecture, story và implementation;
- tool/skill/MCP ngày càng nhiều gây context bloat và tool confusion;
- chưa có cơ chế thống nhất quản trị prompt, skill, agent, hook, sandbox và permission;
- thiếu traceability từ requirement tới code và test;
- dễ kết luận “đã hoàn thành” mà không có evidence;
- security thường được kiểm tra cuối vòng đời thay vì Security-by-Design;
- thiếu observability đối với chính hoạt động của AI agent;
- khó chuyển đổi giữa Claude, OpenCode, Antigravity và các agent environment khác;
- chưa có tiêu chuẩn chung để đánh giá một prompt, skill, MCP hay agent có thực sự nâng chất lượng hay chỉ làm tăng complexity.

Do đó cần xây dựng một framework ở cấp **AI Software Engineering Platform**, trong đó AI không chỉ “viết code”, mà tham gia có kiểm soát vào toàn bộ SDLC.

---

# 3. Mục tiêu tổng quát

Xây dựng một framework chuẩn hóa cho phép một dự án phần mềm mới có thể bắt đầu với tối thiểu:

`requirements.md`

và thực hiện gần như toàn bộ vòng đời phát triển phần mềm bằng hệ thống AI agents.

Framework phải tự động hoặc bán tự động:

1. phân tích và làm sạch yêu cầu;
2. xác định ambiguity, contradiction, missing requirements và assumption;
3. tạo Product Brief/PRD;
4. xác định FR/NFR;
5. xây dựng UX/UI/CX specification nếu cần;
6. xây dựng architecture và ADR;
7. threat modeling và security requirements;
8. phân rã thành Epic/Story;
9. kiểm tra Implementation Readiness;
10. lập kế hoạch implementation;
11. phát triển theo từng story;
12. viết và thực thi test;
13. review code độc lập;
14. kiểm tra security;
15. kiểm tra requirement coverage;
16. integration/E2E/performance/accessibility testing;
17. build và package;
18. tạo SBOM/provenance;
19. triển khai;
20. post-deployment verification;
21. observability;
22. tạo runbook và tài liệu vận hành;
23. hỗ trợ incident/debugging;
24. retrospective;
25. đồng bộ ngược các thay đổi về specification.

Mục tiêu không phải **“AI tự code 100% không cần kiểm soát”**, mà là:

> **Autonomous by default – governed by evidence – human approval based on risk.**

---

# 4. North-Star Principle

Framework phải đảm bảo:

> **Không một dòng code quan trọng nào được sinh ra mà không truy ngược được về requirement, design decision hoặc corrective action tương ứng.**

Và ngược lại:

> **Không một requirement được coi là hoàn thành nếu không truy ngược được tới implementation, verification evidence và acceptance result.**

Hình thành chuỗi traceability:

`REQ → Capability → UX/Architecture Decision → Epic → Story → Task → Code → Test → Security Control → Build → Deployment → Runtime Evidence`

---

# 5. Phương pháp luận nền tảng

## 5.1. BMAD là methodology core

Nghiên cứu sâu và sử dụng BMAD Method làm nền phương pháp luận chính.

BMAD hiện tổ chức quy trình theo Analysis → Planning → Solutioning → Implementation; artifact của phase trước trở thành context cho phase sau. V6 cũng đưa architecture lên trước việc tạo epics/stories để story được informed bởi các technical decisions.

Các thành phần BMAD cần kế thừa gồm:

- Analysis;
- Research;
- Product Brief/PRFAQ;
- PRD;
- UX;
- SPEC;
- Architecture;
- ADR;
- Epic/Story decomposition;
- Implementation Readiness Gate;
- Sprint Planning;
- Build;
- Code Review;
- Correct Course;
- Retrospective;
- Project Context;
- Test Architect;
- BMad Loop khi phù hợp.

Đặc biệt cần giữ nguyên triết lý:

**PRD nói WHAT/WHY; Architecture nói HOW; Story không được tự phát minh decision còn thiếu.**

BMAD hiện cũng xác định PRD là artifact tổ chức sở hữu; nếu downstream cần một quyết định mà PRD chưa có, phải cập nhật PRD rồi generate lại specification thay vì để downstream tự diễn giải.

---

# 6. Bổ sung Specification-Driven Development

Nghiên cứu và tiếp thu các nguyên lý phù hợp từ GitHub Spec Kit nhưng không tạo một workflow thứ hai cạnh tranh với BMAD.

GitHub Spec Kit hiện coi specification là source tạo ra implementation theo flow Spec → Plan → Tasks → Implement và hỗ trợ hàng chục coding agents, bao gồm Claude và Antigravity.

Cần áp dụng các tư tưởng:

**Specification as Source of Truth**

Code phải phục vụ specification chứ không để specification trở thành tài liệu chết.

**Executable Specifications**

Acceptance criteria, interface contracts, test criteria và quality gates phải có khả năng chuyển thành automated checks.

**Artifact Consistency**

Phải tự động phát hiện drift giữa:

PRD ↔ UX ↔ Architecture ↔ Stories ↔ Code ↔ Tests.

**Stable IDs**

Requirement/Capability/NFR/ADR/Story phải có ID bền vững để phục vụ traceability.

---

# 7. Agent Harness Architecture

Nghiên cứu kỹ DeepSeek Harness và các agent harness hàng đầu để thiết kế một **framework-owned harness abstraction**.

Không phụ thuộc cứng vào DeepSeek Harness do dự án hiện vẫn ở trạng thái developer preview và có cảnh báo breaking changes.

Tuy nhiên cần kế thừa triết lý quan trọng:

> **Minimal Agent Loop + Everything Else as Plugin**

DeepSeek Harness giữ core loop gần như chỉ còn “call model → execute tools → repeat”; hook, policy, compaction, retry, sandbox, permission, subagent, persistence và UI/telemetry đều nằm ngoài loop dưới dạng plugin/capability.

Harness của framework tối thiểu phải quản lý được:

- system prompt;
- runtime prompt;
- context assembly;
- model provider;
- model routing;
- tools;
- MCP;
- skills;
- hooks;
- policies;
- permission;
- sandbox;
- session;
- persistence;
- memory;
- compaction;
- retry/recovery;
- subagents;
- parallel tool execution;
- cancellation;
- human approval;
- structured outputs;
- telemetry;
- audit trail;
- cost/token accounting.

---

# 8. Sandbox và Permission Model

Áp dụng mô hình **deny-by-default / least privilege**.

Tách riêng:

**Capability** – agent có tool gì.

**Sandbox** – tool được tác động tới phạm vi nào.

**Approval** – hành động nào cần người phê duyệt.

**Policy** – điều kiện nào cho phép/không cho phép.

Có ít nhất các execution profiles:

`READ_ONLY`

`WORKSPACE_WRITE`

`TEST_EXECUTION`

`NETWORK_RESTRICTED`

`DEPLOY_STAGING`

`DEPLOY_PRODUCTION`

`PRIVILEGED_SECURITY_TEST`

DeepSeek Harness cũng tách sandbox policy và approval policy thay vì coi chúng là một khái niệm duy nhất.

Các thao tác như:

- destructive database operation;
- production deployment;
- secret access;
- external email/message;
- cloud infrastructure changes;
- security offensive operation;

phải có policy/gate riêng.

---

# 9. Context Engineering Layer

Context phải được coi là **tài nguyên hữu hạn cần được quản trị**, không phải tập hợp tất cả file rồi nhồi vào prompt.

Xây dựng Context Policy gồm:

### Global Context

Nguyên tắc chung của framework.

### Organization Context

Coding standards, security policies, architecture standards, compliance.

### Project Context

Tech stack, conventions, architecture, repo structure.

### Epic Context

Capability và architectural constraints liên quan.

### Story Context

Chỉ context cần thiết để implement story.

### Tool Context

Documentation/code information được lấy on-demand.

Áp dụng:

- progressive disclosure;
- semantic retrieval;
- code graph;
- stable context references;
- summarization/compaction;
- context freshness;
- staleness detection;
- context budget;
- provenance của từng context fragment.

Không đưa hàng trăm skills/tool descriptions vào system context của tất cả agent.

---

# 10. Skill Architecture

Sử dụng **Agent Skills open standard** làm canonical format nếu có thể.

Agent Skills định nghĩa skill dưới dạng thư mục có `SKILL.md`, metadata và các resource/script bổ sung; đây là format mở và đã được nhiều agent ecosystem sử dụng.

Mỗi Skill phải được coi như **software component**, không phải một file prompt tùy ý.

Mỗi skill cần có:

- ID;
- name;
- semantic version;
- description/routing metadata;
- role;
- lifecycle phase;
- applicable tech stack;
- prerequisites;
- allowed tools;
- security classification;
- context cost;
- source/provenance;
- license;
- owner;
- test suite;
- benchmark;
- compatibility matrix;
- quality score.

Thiết lập quy trình:

`Discover → Analyze → Security Scan → Deduplicate → Adapt → Test → Benchmark → Approve → Version → Publish → Observe → Deprecate`

---

# 11. Skill Governance

Không được cài tất cả public skills một cách mặc định.

Cần xây dựng:

**Skill Registry**

Kho skill đã được phê duyệt.

**Skill Router**

Chọn skill dựa trên role + task + stack + phase.

**Skill Linter**

Kiểm tra Agent Skills specification, metadata, context size, conflict và anti-pattern.

**Skill Eval**

Đánh giá A/B có skill và không có skill.

**Skill Security Scanner**

Phát hiện instruction injection, destructive command, secret exfiltration, network access bất thường.

**Skill Dependency Management**

Lock version, provenance và checksum.

**Skill Conflict Resolution**

Xử lý trường hợp nhiều skill đưa ra nguyên tắc trái nhau.

Các nghiên cứu 2026 cho thấy routing metadata yếu, skill body phình to và packaging lỗi xuất hiện phổ biến trong public Agent Skills; vì vậy framework bắt buộc phải có lint/evaluation thay vì tin tưởng trực tiếp skill tải từ Internet.

---


<!-- §12 (bảng tóm tắt bản đầy đủ, giữ để ghi nhận ứng viên Addy Osmani + Spec Kit portability) -->
# 12. Các Skill/Repository bắt buộc nghiên cứu

| Nguồn | Mục đích | Định hướng sử dụng |
|---|---|---|
| BMAD Method | Product/Agile/AI-driven SDLC | Methodology Core |
| andrej-karpathy-skills | Engineering discipline | Core principles |
| UI UX Pro Max | UI/UX design intelligence | UX agent |
| Anthropic Cybersecurity Skills | Cybersecurity knowledge | Curated security catalog |
| obra/superpowers | TDD/debug/review/subagents | Development discipline |
| GitHub Spec Kit | Spec-driven development | Concepts & portability |
| Agent Skills specification | Skill portability | Canonical Skill format |
| DeepSeek Harness | Agent harness architecture | Architecture reference |
| Addy Osmani Agent Skills | Production engineering practices | Candidate skills |
| Các repository do chủ đầu tư cung cấp | Existing knowledge | Evaluate/migrate |
| Existing framework/project do chủ đầu tư cung cấp | Internal baseline | Gap analysis & reuse |

---


<!-- §12 + §12A CHI TIẾT (bản bổ sung — 25 tiêu chí nghiên cứu, 12.1–12.13, 12A baseline) -->

# 12. Danh mục Repository và nguồn tham khảo bắt buộc

Đơn vị thực hiện phải nghiên cứu trực tiếp source code, documentation, architecture, issues, releases và các implementation pattern của các repository dưới đây.

Không được chỉ đọc README hoặc sử dụng mô tả thứ cấp.

Kết quả nghiên cứu từng repository phải chỉ ra:

- mục tiêu và triết lý thiết kế;
- kiến trúc;
- workflow;
- agent model;
- context management;
- skills;
- plugins;
- hooks;
- tools;
- MCP;
- sandbox;
- permission;
- subagents;
- observability;
- evaluation;
- ưu điểm;
- nhược điểm;
- mức trưởng thành;
- security risk;
- context/token overhead;
- license;
- khả năng sử dụng trong enterprise;
- khả năng hỗ trợ Claude/OpenCode/Antigravity/Codex;
- thành phần nên reuse;
- thành phần nên adapt;
- thành phần không nên sử dụng;
- overlap với các repository khác.

---

## 12.1. BMAD Method — Methodology Core

**Repository**

https://github.com/bmad-code-org/bmad-method

**Vai trò dự kiến**

Methodology Core của toàn bộ AI-SDLC Framework.

Phải nghiên cứu đặc biệt:

- BMAD V6 architecture;
- agents;
- workflows;
- BMad Method/BMM;
- BMad Builder/BMB;
- Test Architect/TEA;
- BMad Loop;
- project context;
- Product Brief;
- PRD;
- UX;
- Architecture;
- ADR;
- Epics;
- Stories;
- Implementation Readiness;
- Sprint Planning;
- Code Review;
- Correct Course;
- Retrospective;
- greenfield;
- brownfield;
- scale-adaptive workflow.

BMAD không được coi đơn thuần là một tập prompt.

Cần coi BMAD là **process/methodology kernel** để framework mở rộng xung quanh.

---

# 12.2. Andrej Karpathy Skills

**Repository**

https://github.com/multica-ai/andrej-karpathy-skills

**Vai trò dự kiến**

Engineering Constitution và behavior guidelines cho coding agents.

Nghiên cứu đặc biệt các nguyên tắc:

- Think Before Coding;
- Simplicity First;
- Surgical Changes;
- Goal-Driven Execution;
- assumptions management;
- minimal changes;
- measurable success criteria.

Các nguyên tắc phù hợp cần được chuẩn hóa thành framework-level Engineering Constitution thay vì chỉ copy một `CLAUDE.md`.

---

# 12.3. UI/UX Pro Max Skill

**Repository**

https://github.com/nextlevelbuilder/ui-ux-pro-max-skill

**Vai trò dự kiến**

Capability augmentation cho:

- UX Agent;
- UI Designer Agent;
- Frontend Agent;
- Design Review Agent.

Repository hiện có integration cho nhiều coding environment, bao gồm Claude, OpenCode và Antigravity.

Cần nghiên cứu:

- design-system generator;
- UX guidelines;
- styles;
- color systems;
- typography;
- accessibility;
- supported technology stacks;
- framework integration;
- cách repository đóng gói cùng một capability cho nhiều agent environment.

Không được sử dụng repository này thay thế BMAD UX methodology.

BMAD quyết định **quy trình thiết kế**.

UI/UX Pro Max đóng vai trò **knowledge/capability augmentation**.

---

# 12.4. Anthropic Cybersecurity Skills

**Repository do chủ đầu tư cung cấp**

https://github.com/mukul975/anthropic-cybersecurity-skills

Cần kiểm tra đồng thời upstream/source lineage và tình trạng repository tại thời điểm nghiên cứu.

**Vai trò dự kiến**

Nguồn cybersecurity skill để xây dựng curated Security Skill Registry.

Không được cài toàn bộ cybersecurity skills vào tất cả agent.

Phải phân loại tối thiểu thành:

- Secure Coding;
- AppSec;
- DevSecOps;
- Cloud Security;
- Threat Modeling;
- Detection;
- Incident Response;
- Vulnerability Analysis;
- Offensive Security;
- Red Team;
- AI Security.

Các skill offensive/dual-use phải có riêng:

- authorization;
- isolated sandbox;
- tool restriction;
- network restriction;
- logging;
- approval policy.

---

# 12.5. DeepSeek Harness

**Repository**

https://github.com/deepseek-ai/deepseek-harness

**Vai trò dự kiến**

Reference architecture quan trọng nhất cho Agent Harness Layer.

DeepSeek Harness hiện sử dụng kiến trúc:

**Everything is a Plugin**

và đang ở trạng thái developer preview, vì vậy phải nghiên cứu sâu nhưng không được hard-dependency toàn bộ framework vào implementation này.

Cần reverse-engineer:

- core agent loop;
- plugin system;
- tools;
- policies;
- permissions;
- hooks;
- sandbox;
- context management;
- session;
- persistence;
- compaction;
- retries;
- subagents;
- UI;
- observability;
- lifecycle;
- extension mechanism.

Mục tiêu là rút ra **Harness Abstraction** chung, không đơn thuần fork DeepSeek Harness.

---

# 12.6. GitHub Spec Kit

**Repository**

https://github.com/github/spec-kit

**Vai trò dự kiến**

Nguồn tham khảo cho Specification-Driven Development.

Spec Kit coi specification là artifact trung tâm và tổ chức flow từ specification tới planning, tasks và implementation.

Cần nghiên cứu:

- constitution;
- specify;
- clarify;
- plan;
- tasks;
- implementation;
- specification lifecycle;
- executable specification;
- agent portability;
- template system.

Không xây một quy trình Spec Kit song song BMAD.

Cần chọn lọc các best practices của Spec Kit để tăng cường BMAD.

---

# 12.7. Superpowers

**Repository**

https://github.com/obra/superpowers

**Vai trò dự kiến**

Nguồn engineering discipline cho Development Loop.

Nghiên cứu đặc biệt:

- Test-Driven Development;
- systematic debugging;
- brainstorming;
- implementation planning;
- verification-before-completion;
- code review;
- subagent-driven development;
- parallel agents;
- git worktrees.

Chỉ hấp thụ các capability bổ sung cho phần engineering execution.

Không duplicate Product/BA/Architecture workflows đã có trong BMAD.

---

# 12.8. Agent Skills Open Specification

**Repository**

https://github.com/agentskills/agentskills

**Documentation**

https://agentskills.io/

**Vai trò dự kiến**

Canonical Skill Format của framework.

Agent Skills là open format để đóng gói instructions, scripts và resources thành capability có thể được nhiều agent client sử dụng.

Framework cần ưu tiên compatibility với standard này để tránh lock-in vào Claude.

---

# 12.9. Context7

**Repository**

https://github.com/upstash/context7

**Vai trò dự kiến**

Dynamic Documentation Retrieval.

Context7 cung cấp documentation và code example theo version thay vì phụ thuộc hoàn toàn vào model training knowledge.

Phải benchmark cả:

- MCP mode;
- CLI/Skill mode;
- direct tool integration nếu có.

Không mặc định MCP là lựa chọn tốt nhất.

---

# 12.10. Serena

**Repository**

https://github.com/oraios/serena

**Vai trò dự kiến**

Semantic Code Intelligence / IDE for Agent.

Serena cung cấp symbol-level retrieval, editing, refactoring và reference analysis thông qua language-server-backed capabilities.

Nghiên cứu sử dụng cho:

- find symbol;
- find references;
- structural understanding;
- precise editing;
- refactoring;
- large-codebase navigation.

---

# 12.11. GitNexus

**Repository chính cần nghiên cứu**

https://github.com/abhigyanpatwari/GitNexus

**Vai trò dự kiến**

Repository Knowledge Graph / Code Graph / Change Impact Engine.

GitNexus xây knowledge graph từ codebase và hỗ trợ:

- symbol context;
- dependency graph;
- execution processes;
- impact analysis;
- change detection;
- graph queries;
- MCP;
- Skills;
- Claude hooks;
- multi-repository analysis.

Repository hiện cũng công bố hỗ trợ Claude Code, OpenCode, Antigravity và các MCP-compatible clients.

Phải đánh giá kỹ overlap giữa:

**Serena**

và

**GitNexus**

Theo hypothesis ban đầu:

**Serena → semantic IDE/code operation**

**GitNexus → global codebase knowledge graph/change impact**

Framework có thể sử dụng cả hai nếu benchmark chứng minh chúng bổ sung cho nhau.

---

# 12.12. Playwright MCP

**Repository**

https://github.com/microsoft/playwright-mcp

**Vai trò dự kiến**

Browser automation và UI/E2E verification.

Cần đặc biệt benchmark hai cách:

**Playwright MCP**

versus

**Playwright CLI + Agent Skills**

Playwright hiện tự lưu ý rằng coding agents có thể hưởng lợi từ CLI + Skills do giảm lượng tool schema/accessibility tree phải đưa vào context.

Do đó framework không được mặc định chọn MCP.

---

# 12.13. Các repository bổ sung

Trong quá trình nghiên cứu, đơn vị thực hiện bắt buộc phải tiếp tục tìm kiếm các repository/framework khác thuộc các nhóm:

- autonomous coding agents;
- agent harness;
- AI-SDLC;
- software factory;
- specification-driven development;
- context engineering;
- code knowledge graph;
- Agent Skills;
- MCP gateway;
- sandbox;
- policy engine;
- agent observability;
- prompt evaluation;
- agent evaluation;
- software testing agents;
- AppSec agents;
- browser agents;
- DevSecOps agents.

Repository mới chỉ được bổ sung vào framework sau khi đi qua Technology/Skill Evaluation Scorecard.

Không lựa chọn dựa trên GitHub Stars đơn thuần.

---

# 12A. Baseline Project đã triển khai trước đây

Bên cạnh các open-source repository, bắt buộc phải nghiên cứu project đã được chủ đầu tư triển khai trước đây:

```text
/Users/nghinh/Downloads/vnpt-ai-driven-platform/
```

Tên tham chiếu:

**VNPT AI Driven Platform – Existing Baseline**

Project này phải được coi là:

> **Existing Implementation Baseline / Internal Reference Architecture**

chứ không chỉ là tài liệu tham khảo.

---

## 12A.1. Yêu cầu reverse-engineer project baseline

Trước khi thiết kế framework mới phải phân tích toàn bộ project:

```text
/Users/nghinh/Downloads/vnpt-ai-driven-platform/
```

Bao gồm tối thiểu:

- repository structure;
- documentation;
- architecture;
- agents;
- prompts;
- skills;
- plugins;
- hooks;
- MCP;
- context policies;
- coding guidelines;
- workflows;
- orchestration;
- sandbox;
- permissions;
- subagents;
- state/session;
- memory;
- evaluation;
- testing;
- CI/CD;
- observability;
- security;
- deployment;
- scripts;
- configuration;
- dependencies.

---

# 12A.2. Không xây mới trước khi thực hiện Gap Analysis

Phải xây dựng:

**Current State**

từ:

`vnpt-ai-driven-platform`

↓

so sánh với:

- BMAD;
- DeepSeek Harness;
- Spec Kit;
- Agent Skills;
- Superpowers;
- Karpathy Skills;
- Serena;
- GitNexus;
- Context7;
- Playwright;
- UI/UX Pro Max;
- Cybersecurity Skills;
- các best practices khác.

↓

tạo:

**Gap Analysis**

↓

tạo:

**Target Architecture**

---

# 12A.3. Phân loại thành phần của baseline

Mỗi thành phần trong:

```text
/Users/nghinh/Downloads/vnpt-ai-driven-platform/
```

phải được phân loại:

### KEEP

Đã tốt, tiếp tục sử dụng.

### IMPROVE

Có giá trị nhưng cần nâng cấp.

### REFACTOR

Đúng concept nhưng implementation cần viết lại.

### REPLACE

Có giải pháp tốt hơn.

### MERGE

Có thể hợp nhất với capability từ framework khác.

### DEPRECATE

Không còn cần thiết.

### MISSING

Framework mới cần bổ sung nhưng baseline chưa có.

Không được rewrite toàn bộ từ đầu nếu không chứng minh được lợi ích.

---

# 12A.4. Architecture Decision Record

Mọi quyết định thay thế thành phần đã tồn tại trong baseline phải có ADR.

Ví dụ:

```text
ADR-XXX

Existing:
VNPT implementation A

Candidate:
DeepSeek Harness implementation B

Decision:
KEEP / ADAPT / REPLACE

Reason:
...

Benchmark:
...

Migration impact:
...

Risk:
...

Rollback:
...
```

---

# 12A.5. Reuse First

Nguyên tắc bắt buộc:

> **Understand → Evaluate → Reuse → Improve → Replace only when justified**

Không áp dụng:

> Find a popular GitHub project → replace existing implementation.

Framework mới phải kế thừa tối đa:

- kinh nghiệm đã có;
- patterns đã kiểm chứng;
- automation đang hoạt động;
- internal conventions;
- existing project knowledge.

---

# 12A.6. Baseline Deliverable

Sau khi nghiên cứu project:

```text
/Users/nghinh/Downloads/vnpt-ai-driven-platform/
```

phải sinh tối thiểu:

```text
docs/research/internal-baseline/
├── executive-summary.md
├── current-architecture.md
├── repository-map.md
├── agent-inventory.md
├── skill-inventory.md
├── prompt-inventory.md
├── hook-inventory.md
├── mcp-inventory.md
├── context-analysis.md
├── harness-analysis.md
├── security-analysis.md
├── observability-analysis.md
├── technical-debt.md
├── strengths.md
├── weaknesses.md
├── gap-analysis.md
├── reuse-plan.md
├── migration-plan.md
└── target-recommendations.md
```

---

# 12A.7. Thứ tự nghiên cứu bắt buộc

Không bắt đầu implementation framework mới ngay.

Thực hiện theo thứ tự:

```text
1. Reverse-engineer vnpt-ai-driven-platform
                 ↓
2. Reverse-engineer BMAD
                 ↓
3. Reverse-engineer DeepSeek Harness
                 ↓
4. Research Spec Kit / Agent Skills / Superpowers
                 ↓
5. Research Skills ecosystem
                 ↓
6. Research MCP/Tool ecosystem
                 ↓
7. Comparative Analysis
                 ↓
8. Gap Analysis
                 ↓
9. Define AI-SDLC principles
                 ↓
10. Design Target Architecture
                 ↓
11. Define Canonical Meta-Model
                 ↓
12. Build PoC
                 ↓
13. Benchmark
                 ↓
14. Refine
                 ↓
15. Implement Framework
```

---

# 12A.8. Nguyên tắc chống “Framework Frankenstein”

Một yêu cầu đặc biệt của bài toán là tránh xây framework theo kiểu:

```text
BMAD
+ 100 skills
+ 20 MCP
+ DeepSeek Harness
+ Spec Kit
+ Superpowers
+ ...
```

rồi gọi đó là framework.

Mỗi capability chỉ được tồn tại nếu trả lời được:

**Why does this exist?**

**Which problem does it solve?**

**Which agent uses it?**

**At which SDLC phase?**

**When is it loaded?**

**What is its context cost?**

**What is its security impact?**

**What alternative was evaluated?**

**What benchmark proves its value?**

Framework cuối cùng phải có kiến trúc thống nhất, không phải aggregation của các open-source projects.
<!-- §13–54 (bản đầy đủ) -->

# 13. Karpathy Engineering Constitution

Tích hợp các nguyên tắc từ `andrej-karpathy-skills` vào Engineering Constitution:

1. Think Before Coding.
2. Simplicity First.
3. Surgical Changes.
4. Goal-Driven Execution.

Repo này nhấn mạnh việc không tự giả định, tránh over-engineering, chỉ sửa phần trực tiếp phục vụ yêu cầu và chuyển task thành success criteria có thể verify.

Framework phải mở rộng thành:

**Evidence Before Claims**

Agent không được kết luận “done”, “fixed”, “works” nếu chưa có verification evidence.

**Understand Before Modify**

Không sửa module chưa hiểu dependencies.

**Smallest Correct Change**

Ưu tiên minimal blast radius.

**Tests Reproduce Before Fix**

Bug phải có reproduction khi khả thi.

**No Silent Assumptions**

Assumption phải được ghi nhận.

---

# 14. Superpowers Engineering Discipline

Nghiên cứu `obra/superpowers`, đặc biệt:

- Test-Driven Development;
- systematic debugging;
- root-cause tracing;
- verification-before-completion;
- requesting code review;
- receiving code review;
- git worktrees;
- parallel agents;
- subagent-driven development.

Superpowers hiện tổ chức development workflow quanh TDD, systematic debugging, verification và independent review.

Không duplicate phần product planning đã do BMAD đảm nhiệm.

---

# 15. UI/UX/CX Engineering

Sử dụng BMAD UX làm methodology.

UI UX Pro Max và các design skills khác làm knowledge/capability augmentation.

UI UX Pro Max hiện hỗ trợ design-system generation và nhiều coding environment, bao gồm Claude, Antigravity và OpenCode.

Framework phải tạo được:

- UX strategy;
- user journeys;
- information architecture;
- interaction model;
- design principles;
- design tokens;
- typography;
- color;
- component system;
- responsive behavior;
- accessibility;
- empty/loading/error states;
- micro interaction;
- content guidelines;
- UX acceptance criteria.

Phải kiểm tra:

- multi-viewport;
- responsive;
- WCAG;
- keyboard;
- focus;
- contrast;
- reduced motion;
- layout stability;
- performance.

---

# 16. Security Skill Strategy

`anthropic-cybersecurity-skills` chứa hơn 800 skill thuộc hàng chục domain và bao gồm cả defensive lẫn offensive/dual-use techniques.

Do đó:

**Không cài toàn bộ vào global agent.**

Phân chia:

### AppSec Skills

Cho Developer/Test/Security Agent.

### DevSecOps Skills

CI/CD, secrets, dependency, container, IaC.

### Threat Modeling Skills

STRIDE/attack surface/data-flow.

### Cloud Security Skills

Theo stack.

### AI Security Skills

Nếu ứng dụng có AI.

### Red Team Skills

Chỉ chạy trong isolated security profile có authorization.

---

# 17. MCP/Tool Architecture

Không mặc định “càng nhiều MCP càng tốt”.

Áp dụng nguyên tắc:

> **Built-in capability → CLI + Skill → MCP → Custom Integration**

và chọn phương án có context overhead, security surface và operational complexity thấp nhất nhưng vẫn đáp ứng yêu cầu.

Mỗi MCP phải được đánh giá theo:

- capability;
- quality;
- latency;
- context/token overhead;
- security;
- maintenance;
- offline support;
- data egress;
- platform compatibility;
- licensing;
- overlap với MCP khác.

---

# 18. MCP/Tool Baseline

## Context7

Dùng để lấy documentation/version-specific API mới.

Context7 hiện hỗ trợ cả CLI + Skills và MCP; có thể lấy tài liệu theo library/version thay vì dựa vào knowledge cũ của model.

Khuyến nghị: ưu tiên CLI+Skill khi coding agent hỗ trợ tốt; dùng MCP khi native integration đem lại lợi ích.

## GitNexus

Dùng cho:

- repository knowledge graph;
- dependency analysis;
- architecture exploration;
- execution flow;
- blast-radius;
- change impact;
- multi-repository relationship.

GitNexus xây graph từ AST/import/call relationship và cung cấp `context`, `impact`, `detect_changes`, hybrid search cùng multi-repo support.

## Serena

Dùng cho:

- symbol-level navigation;
- semantic editing;
- reference lookup;
- refactoring;
- LSP-backed code intelligence.

Serena cung cấp semantic retrieval/editing ở mức symbol thay cho chỉ grep/line-based manipulation.

GitNexus và Serena không được xem là hai sản phẩm loại trừ nhau:

**GitNexus = system/code graph understanding.**

**Serena = semantic IDE operations.**

Router lựa chọn dựa trên task.

## Playwright

Dùng cho:

- E2E;
- browser verification;
- visual verification;
- accessibility;
- UI acceptance.

Đặc biệt cần benchmark **Playwright MCP vs Playwright CLI + Skills**. Chính tài liệu Playwright hiện lưu ý coding agents có thể phù hợp với CLI+Skills hơn do giảm schema/context overhead.

---

# 19. Multi-Agent Organization

Framework phải hỗ trợ tối thiểu các agent role:

| Agent | Trách nhiệm |
|---|---|
| Orchestrator | Điều phối lifecycle |
| Product Owner | Business value và priorities |
| Product Manager | Product definition/PRD |
| Business Analyst | Requirement analysis |
| Research Agent | Domain/market/technical research |
| Scrum Master | Epic/Story/Sprint |
| UX Designer | User experience |
| UI Designer | Visual/design system |
| CX Designer | End-to-end customer journey |
| Solution Architect | System architecture |
| Security Architect | Threat/security architecture |
| Data/AI Architect | Khi dự án cần |
| Developer | Implementation |
| Frontend Specialist | Front-end |
| Backend Specialist | Backend/API |
| Mobile Specialist | Mobile |
| Database Specialist | DB |
| Test Architect | Test strategy |
| QA Agent | Functional verification |
| Code Reviewer | Independent review |
| AppSec Reviewer | SAST/security review |
| DevSecOps Agent | CI/CD/IaC |
| SRE Agent | Reliability/observability |
| Release Agent | Packaging/release |
| Support Agent | Incident/support |
| Technical Writer | Technical documentation |
| Auditor | Traceability/compliance |

Không phải project nào cũng khởi tạo toàn bộ agent.

**Agent Router** phải chọn team phù hợp dựa trên project profile.

---

# 20. Subagent Strategy

Subagent phải có:

- bounded context;
- bounded tools;
- bounded permissions;
- rõ nhiệm vụ;
- structured output;
- độc lập context khi cần;
- parent-child trace;
- maximum depth;
- token/cost budget;
- timeout;
- cancellation;
- audit.

Đối với các nhiệm vụ nhạy cảm, subagent phải chạy isolated process/container.

DeepSeek Harness hiện cũng hỗ trợ cả in-process và out-of-process subagent; out-of-process child có thể tách runtime/model/tools khỏi parent.

---

# 21. Canonical AI-SDLC Workflow

Framework phải chuẩn hóa workflow tối thiểu:

### Phase 0 — Bootstrap

`requirements.md`

↓

Project Classification

↓

Risk/Profile Detection

↓

Technology/Compliance Constraints

### Phase 1 — Discovery

Requirement analysis

↓

Ambiguity/Conflict detection

↓

Research

↓

Product Brief / PRFAQ khi cần

### Phase 2 — Product Definition

PRD

↓

FR/NFR

↓

Personas/Journeys

↓

Acceptance framework

### Phase 3 — Experience Design

UX

↓

CX

↓

UI

↓

Design System

↓

Accessibility specification

### Phase 4 — Solution Architecture

Architecture

↓

ADR

↓

Data Architecture

↓

Integration Architecture

↓

Deployment Architecture

### Phase 5 — Secure-by-Design

Data classification

↓

Threat Model

↓

Security requirements

↓

Privacy requirements

↓

Security test strategy

### Phase 6 — Work Decomposition

Capabilities

↓

Epics

↓

Stories

↓

Acceptance Criteria

↓

Dependencies

### Phase 7 — Implementation Readiness Gate

Kiểm tra:

- requirement completeness;
- unresolved assumptions;
- architecture completeness;
- UX completeness;
- security completeness;
- story testability;
- dependency consistency.

Output:

`PASS / CONCERNS / FAIL`

### Phase 8 — Story Development Loop

Story Context

↓

Impact Analysis

↓

Implementation Plan

↓

Test First khi phù hợp

↓

Implementation

↓

Local verification

↓

Independent Review

↓

Fix

↓

Re-verify

### Phase 9 — Integration Verification

Unit Test

↓

Integration Test

↓

Contract Test

↓

E2E

↓

Accessibility

↓

Performance

↓

Security

### Phase 10 — Release Readiness

Requirement Traceability

↓

Dependency Scan

↓

SAST/DAST

↓

SBOM

↓

License

↓

Supply Chain

↓

Release Gate

### Phase 11 — Deployment

Staging

↓

Smoke Test

↓

Production approval

↓

Deploy

↓

Post-deployment Verification

### Phase 12 — Operate

Logs/Metrics/Traces

↓

SLO/SLI

↓

Incident

↓

Root Cause

↓

Corrective Action

### Phase 13 — Learn

Retrospective

↓

Lessons Learned

↓

Update Specification

↓

Update Skills/Prompts/Playbooks

↓

Framework Eval Dataset

---

# 22. Human-in-the-Loop theo mức độ rủi ro

Không hard-code human approval ở mọi bước.

Xây dựng **Autonomy Level**:

### L0 — Advisory

AI chỉ phân tích.

### L1 — Draft

AI tạo artifact, người duyệt.

### L2 — Execute with Approval

AI lập kế hoạch, xin approval trước action.

### L3 — Autonomous Workspace

AI tự làm trong sandbox và quality gates.

### L4 — Autonomous Delivery

AI có thể merge/deploy staging nếu tất cả gate pass.

### L5 — Controlled Production Autonomy

Chỉ dành cho domain/project được phê duyệt.

Autonomy level phải phụ thuộc:

`Risk × Environment × Tool × Data × Project maturity`

---

# 23. AI Engineering Constitution

Mỗi project phải thừa hưởng một bộ constitution tối thiểu:

1. Specification before implementation.
2. No silent assumptions.
3. Context is a budget.
4. Least privilege.
5. Security by design.
6. Tests are evidence.
7. Evidence before completion.
8. Minimal blast radius.
9. Simplicity over speculative abstraction.
10. Independent verification.
11. Trace everything important.
12. Reproducible builds.
13. No secret in prompt/code/log.
14. Maintain spec-code consistency.
15. Humans control high-risk decisions.

Constitution phải được version-control.

---

# 24. Prompt Engineering Standard

Xây dựng Prompt Standard cho toàn framework.

Một operational prompt tối thiểu phải mô tả:

`ROLE`

`OBJECTIVE`

`INPUT`

`CONTEXT`

`CONSTRAINTS`

`POLICIES`

`ALLOWED TOOLS`

`EXPECTED OUTPUT`

`SUCCESS CRITERIA`

`VERIFICATION`

`ESCALATION`

Không đưa coding guidelines hàng nghìn dòng vào mọi prompt.

Prompt phải composable và testable.

---

# 25. Prompt/Skill/Agent Evals

Mọi thay đổi prompt/skill/harness quan trọng phải qua regression evaluation.

Áp dụng tư tưởng:

> **Prompt-as-Code / Skill-as-Code / Agent-as-Code**

Mỗi component phải:

- versioned;
- reviewed;
- tested;
- benchmarked;
- observable;
- reversible.

Xây dựng benchmark corpus gồm:

- feature implementation;
- bug fixing;
- refactoring;
- migration;
- greenfield;
- brownfield;
- frontend;
- backend;
- API;
- database;
- security;
- performance;
- ambiguous requirements;
- conflicting requirements;
- large repository.

So sánh:

`Baseline Agent`

vs.

`Agent + Framework`

---

# 26. Chỉ số đánh giá AI Agent

Đo ít nhất:

### Outcome

- task success;
- acceptance pass rate;
- requirement coverage;
- escaped defect.

### Engineering

- test pass rate;
- code review findings;
- regression;
- security vulnerabilities;
- change blast radius;
- maintainability.

### Agent

- retries;
- failed tool calls;
- intervention count;
- assumption count;
- hallucinated API;
- context overflow;
- context utilization;
- tool-selection accuracy.

### Efficiency

- token/task;
- cost/story;
- latency/story;
- tool calls/story;
- wall-clock completion.

### Reliability

- first-pass success;
- reproducibility;
- rollback/rework rate.

---

# 27. Observability

Mọi execution của agent phải được trace.

Chuẩn hóa theo OpenTelemetry khi phù hợp. OpenTelemetry cung cấp vendor-neutral traces, metrics và logs.

Agent trace tối thiểu:

`project.id`

`session.id`

`agent.id`

`role`

`model`

`prompt.version`

`skill.id/version`

`tool`

`tool.arguments.classification`

`tool.duration`

`tool.result`

`policy.decision`

`sandbox.profile`

`tokens.input/output`

`cost`

`retry`

`artifact`

`story.id`

`commit`

`test.result`

`security.result`

Không log secrets hoặc sensitive prompt content ngoài policy.

---

# 28. AI-SDLC Dashboard

Xây dựng dashboard cho:

- project lifecycle;
- artifact status;
- requirements coverage;
- story status;
- active agents;
- agent trace;
- context utilization;
- model/token cost;
- quality gates;
- test results;
- security findings;
- deployment status;
- DORA metrics;
- framework effectiveness.

DORA hiện sử dụng năm software delivery metrics gồm change lead time, deployment frequency, failed deployment recovery time, change fail rate và deployment rework rate.

---

# 29. Secure Software Development Standards

Framework cần thiết kế mapping và evidence phù hợp với:

### NIST SSDF

NIST SP 800-218 là baseline Secure Software Development Framework; NIST hiện có SP 800-218A cho GenAI và draft SSDF 1.2.

### OWASP

- OWASP ASVS 5.0;
- OWASP SAMM;
- OWASP Top 10;
- OWASP API Security;
- OWASP LLM/Agentic Security khi có AI.

ASVS 5.0 hiện là stable release của OWASP Application Security Verification Standard.

### Software Supply Chain

- SLSA 1.2;
- SBOM;
- signed artifacts;
- provenance;
- dependency pinning;
- vulnerability scanning.

SLSA 1.2 hiện là version được phê duyệt hiện hành và chuẩn hóa provenance/security guarantees của software supply chain.

### OpenSSF

Dùng OpenSSF Scorecard để đánh giá dependency/repository security posture khi phù hợp.

---

# 30. ISO/Industry Alignment

Framework cần có khả năng mapping tới:

**ISO/IEC/IEEE 12207:2017**  
Software lifecycle processes.

**ISO/IEC 25010:2023**  
Software/product quality model gồm 9 quality characteristics.

**ISO/IEC 27001:2022**  
Information Security Management System.

**ISO/IEC 42001:2023**  
AI Management System khi tổ chức sử dụng hoặc phát triển hệ thống AI.

Không nhất thiết chứng nhận framework theo các ISO này, nhưng artifact/process/control phải có khả năng trace/mapping.

---

# 31. Software Quality Gates

Definition of Done của một story không chỉ là “code chạy”.

Có ít nhất:

### Gate Q1 — Specification

Acceptance criteria rõ ràng.

### Gate Q2 — Architecture

Không vi phạm architecture/ADR.

### Gate Q3 — Build

Build thành công.

### Gate Q4 — Static Quality

Lint/typecheck/code quality.

### Gate Q5 — Tests

Required tests pass.

### Gate Q6 — Code Review

Independent review pass.

### Gate Q7 — Security

Required security scans pass.

### Gate Q8 — Integration

Không phá system.

### Gate Q9 — Traceability

Requirement được cover.

### Gate Q10 — Evidence

Có evidence chứng minh hoàn thành.

Agent không được bypass gate bằng narrative statement.

---

# 32. Brownfield First-Class Support

Framework không chỉ phục vụ greenfield.

Đối với repository hiện hữu phải thực hiện:

Repository Ingestion

↓

Code Graph

↓

Architecture Reverse Engineering

↓

Convention Discovery

↓

Test Baseline

↓

Security Baseline

↓

Technical Debt Baseline

↓

Project Context

↓

Change Impact

trước implementation.

BMAD cũng yêu cầu đối với established project phải đọc codebase và tài liệu hiện hữu thay vì tạo architecture mới không phù hợp.

---

# 33. Platform Independence

Không viết methodology trực tiếp dưới dạng `.claude/...`.

Xây dựng một **Canonical Framework Representation**.

Ví dụ:

`framework/agents/`

`framework/skills/`

`framework/prompts/`

`framework/hooks/`

`framework/policies/`

`framework/workflows/`

`framework/templates/`

`framework/mcp/`

`framework/evals/`

`framework/standards/`

Sau đó có adapter:

`adapters/claude/`

`adapters/opencode/`

`adapters/antigravity/`

`adapters/codex/`

...

Adapter compile/generate canonical definition thành native artifact của từng platform.

---

# 34. Claude Adapter

Sinh:

- CLAUDE.md;
- `.claude/agents`;
- `.claude/skills`;
- commands;
- plugins;
- hooks;
- MCP configuration;
- permission configuration.

Claude hiện tách khá rõ CLAUDE.md, Skills, subagents, hooks, MCP và plugins; đây là mô hình tốt để tham khảo cho canonical abstraction.

---

# 35. OpenCode Adapter

Sinh native:

- Agents;
- Skills;
- Plugins;
- Hooks;
- MCP;
- permissions;
- project instructions.

OpenCode hiện cung cấp plugin API với hooks vào prompt/model/tool/session lifecycle và có hệ thống Skills/MCP riêng.

---

# 36. Antigravity Adapter

Sinh:

- skills;
- agents;
- rules;
- hooks;
- MCP configuration;
- permission/policy;
- plugin bundle.

Antigravity hiện hỗ trợ plugin có thể đóng gói skills, background subagents, rules, MCP và hooks; SDK còn hỗ trợ declarative deny-by-default policy, lifecycle hooks, subagents và observability.

Điều này khẳng định framework nên có canonical abstraction tương ứng thay vì thiết kế theo Claude rồi “port” sang các nền tảng khác.

---

# 37. MCP Security

MCP phải được quản trị như external dependency/API.

Mỗi MCP cần:

- allowlisted server;
- exact version;
- tool allowlist;
- authentication policy;
- secret isolation;
- network policy;
- timeout;
- rate limit;
- audit;
- trust classification.

Không expose toàn bộ tool của MCP cho mọi agent.

MCP specification tiếp tục tăng cường authorization/security requirements; do đó framework phải cô lập implementation MCP phía sau Tool Gateway thay vì để mỗi project tự cấu hình tự do.

---

# 38. Tool Gateway

Xây dựng optional **Tool Gateway** nằm giữa agents và MCP/tools.

Nhiệm vụ:

Agent

↓

Tool Router

↓

Policy Engine

↓

Permission

↓

Secret Broker

↓

Sandbox

↓

MCP/CLI/API

↓

Output Sanitizer

↓

Telemetry

↓

Agent

Qua đó có thể thay đổi MCP mà không thay prompt/agent.

---

# 39. Artifact Graph

Không coi artifacts là tập Markdown rời rạc.

Xây dựng Artifact Graph:

`REQ-xxx`

→ `CAP-xxx`

→ `NFR-xxx`

→ `ADR-xxx`

→ `EPIC-xxx`

→ `STORY-xxx`

→ `TEST-xxx`

→ `COMMIT`

→ `BUILD`

→ `DEPLOY`

Mỗi artifact lưu:

- ID;
- version;
- source;
- generated-by;
- approved-by;
- dependencies;
- supersedes;
- status;
- evidence.

---

# 40. Change Management

Khi requirements thay đổi:

Change Request

↓

Impact Analysis

↓

Affected Requirements

↓

Affected Architecture

↓

Affected UX

↓

Affected Stories

↓

Affected Code

↓

Affected Tests

↓

Regeneration/Reconciliation

Không cho phép sửa PRD nhưng để story/code cũ mà không cảnh báo.

---

# 41. Documentation-as-Code

Framework phải generate/maintain:

- README;
- architecture;
- ADR;
- APIs;
- data model;
- configuration;
- developer guide;
- deployment guide;
- operations guide;
- troubleshooting;
- runbook;
- incident procedures;
- support knowledge base.

Documentation phải được kiểm tra drift trong CI.

---

# 42. CI/CD Integration

Framework phải cung cấp reusable CI pipelines cho:

- lint;
- type check;
- unit tests;
- integration;
- E2E;
- SAST;
- SCA;
- secrets;
- container;
- IaC;
- SBOM;
- licenses;
- provenance;
- build;
- signed release;
- staging deployment;
- production gate.

---

# 43. Reproducibility

Mỗi AI-generated change phải có khả năng tái dựng được ở mức hợp lý:

- model/provider recorded;
- prompt version;
- skills version;
- tool versions;
- MCP versions;
- environment;
- dependency lock;
- input artifact versions;
- test evidence.

Không yêu cầu model output deterministic tuyệt đối, nhưng phải deterministic về **process và acceptance**.

---

# 44. Repository Structure chuẩn

Một project sinh bởi framework tối thiểu dự kiến:

```text
project/
├── requirements.md
├── .ai/
│   ├── constitution/
│   ├── project-context/
│   ├── policies/
│   ├── agents/
│   ├── skills/
│   ├── prompts/
│   ├── hooks/
│   ├── workflows/
│   ├── mcp/
│   └── evals/
├── docs/
│   ├── product/
│   ├── ux/
│   ├── architecture/
│   ├── adr/
│   ├── security/
│   ├── operations/
│   └── support/
├── specs/
├── epics/
├── stories/
├── tests/
├── src/
├── infra/
└── evidence/
```

Các adapter có thể generate `.claude`, `.opencode`, `.agents`... từ `.ai`.

---

# 45. AI-SDLC CLI

Xây dựng CLI thống nhất, ví dụ:

```text
aisdlc init
aisdlc analyze
aisdlc plan
aisdlc design
aisdlc architect
aisdlc secure
aisdlc decompose
aisdlc readiness
aisdlc build
aisdlc review
aisdlc verify
aisdlc release
aisdlc deploy
aisdlc operate
aisdlc retro
aisdlc doctor
aisdlc eval
```

CLI phải abstract platform phía dưới.

Ví dụ:

`aisdlc build --agent claude`

`aisdlc build --agent opencode`

`aisdlc build --agent antigravity`

nhưng output/process semantics phải tương đương.

---

# 46. Model Independence

Framework phải support:

- Anthropic;
- OpenAI;
- Google;
- DeepSeek;
- open-source/on-premise models;
- OpenAI-compatible endpoints.

Xây dựng **Model Capability Profile**:

- coding;
- reasoning;
- context;
- vision;
- tool use;
- structured output;
- latency;
- price;
- privacy.

Agent Router có thể dùng model khác nhau cho:

Planning ≠ Coding ≠ Review ≠ Security ≠ Documentation.

---

# 47. Independent Reviewer Principle

Agent sinh code không phải reviewer cuối cùng của chính nó đối với change quan trọng.

Có thể sử dụng:

Developer Model A

↓

Reviewer Model B

↓

Test/Security Agent C.

Đối với critical path có thể áp dụng multi-model consensus nhưng phải benchmark cost/benefit trước khi mặc định bật.

---

# 48. Definition of Done của toàn bộ project

Một project chỉ được coi là hoàn thành khi:

- toàn bộ critical requirements có traceability;
- không còn unresolved blocker;
- required tests pass;
- security gates pass;
- build reproducible;
- deploy successful;
- post-deploy verification successful;
- observability hoạt động;
- runbook tồn tại;
- support handover hoàn thành;
- artifact không drift;
- evidence package được tạo.

---

# 49. Bộ Deliverables của bài toán framework

Đơn vị triển khai phải bàn giao tối thiểu:

### D1. Research Report

Đánh giá BMAD, DeepSeek Harness, Spec Kit, Agent Skills, Superpowers, Karpathy Skills, UI/UX skills, cybersecurity skills, MCP ecosystem và các framework/repo liên quan.

### D2. Reference Architecture

Kiến trúc AI-SDLC Framework.

### D3. Canonical Meta-Model

Agent/Skill/Prompt/Workflow/Policy/Hook/MCP/Artifact definitions.

### D4. AI-SDLC Methodology

Quy trình end-to-end.

### D5. Agent Library

Các role chuẩn.

### D6. Skill Registry

Bộ skills đã curate.

### D7. MCP/Tool Registry

Các MCP/tool đã curate.

### D8. Harness

Agent execution runtime hoặc abstraction.

### D9. Context Engine

Context policy/retrieval/compaction.

### D10. Security & Policy Engine

Sandbox/permission/policy.

### D11. Platform Adapters

Ít nhất:

- Claude;
- OpenCode;
- Antigravity.

### D12. Prompt/Skill Guidelines

Authoring standards.

### D13. Playbooks

Greenfield, Brownfield, Bugfix, Feature, Refactor, Migration, Incident.

### D14. Quality Gate Framework

Automated verification.

### D15. Eval Framework

Benchmark/regression.

### D16. Observability

Agent traces/metrics/dashboard.

### D17. AI-SDLC CLI

Project bootstrap/orchestration.

### D18. Reference Projects

Tối thiểu:

- web application;
- backend/API;
- brownfield project.

### D19. Documentation

Installation, development, governance, operations.

---

# 50. Acceptance Criteria cấp Framework

Framework chỉ được nghiệm thu khi chứng minh được tối thiểu:

### AC01

Một project mới chỉ có `requirements.md` có thể generate đầy đủ planning artifacts.

### AC02

Requirements được trace xuống stories, tests và implementation.

### AC03

Framework phát hiện requirement ambiguity/inconsistency.

### AC04

Framework không cho implementation bắt đầu khi critical readiness gate FAIL.

### AC05

Có thể implement cùng project trên ít nhất Claude, OpenCode và Antigravity.

### AC06

Không thay canonical specification khi đổi coding environment.

### AC07

Skill có thể được add/update/remove có version.

### AC08

Có automated skill evaluation.

### AC09

Tool/MCP được least-privilege theo agent.

### AC10

Dangerous action không thể tự bypass permission gate.

### AC11

Có sandbox execution.

### AC12

Agent không được declare completion nếu verification bắt buộc chưa chạy.

### AC13

Có independent code review.

### AC14

Có SAST/SCA/secret/dependency checks.

### AC15

Sinh SBOM/provenance.

### AC16

Có E2E/browser verification với UI project.

### AC17

Có requirement-to-test coverage report.

### AC18

Có agent traces/logs/metrics.

### AC19

Có token/cost metrics.

### AC20

Có reproducible benchmark so sánh baseline với framework.

### AC21

Brownfield project có thể được reverse-engineer trước khi modify.

### AC22

Change requirement sinh impact analysis.

### AC23

Framework phát hiện spec/code drift.

### AC24

Framework tạo deployment/runbook/support documentation.

### AC25

Có complete evidence package sau release.

---

# 51. KPI nghiên cứu và triển khai

Không đặt mục tiêu chung chung kiểu “AI coding tốt hơn”.

Phải chứng minh bằng KPI:

- giảm implementation lead time;
- tăng first-pass acceptance;
- giảm regression;
- giảm escaped defect;
- giảm security finding;
- giảm rework;
- giảm hallucinated API;
- giảm unnecessary diff;
- giảm human intervention/task;
- giảm token/task sau tối ưu context;
- tăng traceability coverage;
- tăng reproducibility;
- cải thiện DORA metrics.

Mọi claimed improvement phải có benchmark.

---

# 52. Nguyên tắc lựa chọn công nghệ

Mọi repo/skill/plugin/MCP được đề xuất phải được đánh giá theo scorecard:

| Tiêu chí | Nội dung |
|---|---|
| Functional Value | Có giải quyết vấn đề thực sự không |
| Quality Gain | Có benchmark chứng minh không |
| Context Cost | Tiêu tốn context bao nhiêu |
| Tool Complexity | Tăng tool confusion không |
| Security | Có tăng attack surface không |
| Privacy | Có data egress không |
| Portability | Hỗ trợ platform nào |
| Maintenance | Project có active không |
| Stability | Production hay preview |
| License | Có phù hợp enterprise không |
| Overlap | Trùng capability nào |
| Integration Cost | Chi phí tích hợp |
| Observability | Có đo được không |
| Reversibility | Có bỏ/thay được không |

Không lựa chọn công nghệ chỉ dựa vào star GitHub hoặc popularity.

---

# 53. Best Practices cốt lõi cần bổ sung

Framework phải áp dụng các nguyên tắc sau xuyên suốt:

**Spec-driven, không prompt-driven.**

**Artifact-driven context, không chat-history-driven.**

**Context-on-demand, không context dumping.**

**Skills lazy-loaded, không global-loaded.**

**Tools least-privilege, không expose-all.**

**Evidence-driven completion, không self-reported completion.**

**Independent verification, không self-review-only.**

**Security shift-left, không scan cuối dự án.**

**Policy-as-Code.**

**Prompt-as-Code.**

**Skill-as-Code.**

**Agent-as-Code.**

**Evaluation-as-Code.**

**Infrastructure-as-Code.**

**Documentation-as-Code.**

**Observability-by-Default.**

**Supply-Chain-by-Default.**

**Human governance proportional to risk.**

---

# 54. Kết quả cuối cùng kỳ vọng

Framework cuối cùng phải biến cách phát triển phần mềm từ:

> Người dùng prompt AI → AI viết code → người dùng kiểm tra thủ công

thành:

> **Intent → Governed Specification → Structured AI Team → Controlled Execution → Automated Evidence → Verified Software → Operable System**

Và trải nghiệm lý tưởng đối với một dự án mới là:

```text
requirements.md
       ↓
aisdlc init
       ↓
AI phân tích và chuẩn hóa yêu cầu
       ↓
PRD / UX / Architecture / Security
       ↓
Epics / Stories
       ↓
Readiness Gate
       ↓
Autonomous Story Loops
       ↓
Independent Verification
       ↓
Integration / Security / E2E
       ↓
Release Gate
       ↓
Deployment
       ↓
Observability + Support
       ↓
Retrospective + Continuous Learning
```

