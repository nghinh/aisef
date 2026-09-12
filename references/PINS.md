# Pinned references

Ngày clone: 2026-09-03. Clone `--depth 1`; commit là HEAD của default branch tại thời điểm clone.

| Repo | URL | Commit | Commit date | Default branch |
|---|---|---|---|---|
| bmad-method | https://github.com/bmad-code-org/bmad-method | `891c0abbc1128f318e098a566f925155022aef12` | 2026-09-02 | main |
| karpathy-skills | https://github.com/multica-ai/andrej-karpathy-skills | `2c606141936f1eeef17fa3043a72095b4765b9c2` | 2026-04-20 | main |
| ui-ux-pro-max | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | `58c220ff9d02be80523b06c03471925c52e8ab5d` | 2026-09-02 | main |
| cybersecurity-skills | https://github.com/mukul975/anthropic-cybersecurity-skills | `54a798831d2266a3ca61ce68a7acb80b81160d57` | 2026-08-31 | main |
| deepseek-harness | https://github.com/deepseek-ai/deepseek-harness | `49a606bc5b5934603f22a26957a07dc799ab0291` | 2026-09-02 | master |
| spec-kit | https://github.com/github/spec-kit | `a369c5c27f05ec51fe1667051cfe106f424975b5` | 2026-09-02 | main |
| superpowers | https://github.com/obra/superpowers | `b36e0829c6d0140e93cfef2ca599b1b07d4a7797` | 2026-08-12 | main |
| agentskills | https://github.com/agentskills/agentskills | `69ef37e9424c0a7ea9dd2293b559e43ec8176379` | 2026-08-09 | main |
| context7 | https://github.com/upstash/context7 | `6d777619c2777a79ad0754dc48b48845cb912bac` | 2026-09-02 | master |
| serena | https://github.com/oraios/serena | `813fd98f4fd32e0606cb52281467fc055e45a356` | 2026-09-02 | main |
| gitnexus | https://github.com/abhigyanpatwari/GitNexus | `b15ff2d888949e16834cb341e81f9345931dfc96` | 2026-09-02 | main |
| playwright-mcp | https://github.com/microsoft/playwright-mcp | `4c1fb03bad3bae379b0ae0e3d81d2660de56bd91` | 2026-08-31 | main |
| playwright-monorepo (sparse: packages/playwright-core/src/tools/mcp, packages/playwright/src/mcp) | https://github.com/microsoft/playwright | `e9163e238dcc3951b8cfbd45e0ebc8b6e3c4d194` | 2026-09-02 | main |

## License và quy mô (đếm 2026-09-03)

| Repo | License file | License (dòng đầu) | Files | Top-level |
|---|---|---|---|---|
| bmad-method | LICENSE | MIT License | 638 | AGENTS.md CHANGELOG.md CLAUDE.md CNAME CONTRIBUTING.md CONTRIBUTORS.md LICENSE README.md README_CN.md README_K |
| karpathy-skills | (none) | ? | 9 | CLAUDE.md CURSOR.md EXAMPLES.md README.md README.zh.md skills  |
| ui-ux-pro-max | LICENSE | MIT License | 672 | CLAUDE.md CODE_OF_CONDUCT.md CONTRIBUTING.md LICENSE README.id.md README.ko.md README.md README.vi.md README.z |
| cybersecurity-skills | LICENSE |                                  Apache  | 4532 | AGENTS.md ATTACK_COVERAGE.md CITATION.cff CODE_OF_CONDUCT.md CONTRIBUTING.md LICENSE README.fr.md README.md SC |
| deepseek-harness | LICENSE | MIT License | 8865 | AGENTS.md BENCHMARK.md BRAND_GUIDELINES.i18n.yaml BRAND_GUIDELINES.md BRAND_GUIDELINES.zh.md CLAUDE.md CONTRIB |
| spec-kit | LICENSE | MIT License | 551 | AGENTS.md CHANGELOG.md CITATION.cff CODE_OF_CONDUCT.md CONTRIBUTING.md DEVELOPMENT.md LICENSE README.md README |
| superpowers | LICENSE | MIT License | 194 | AGENTS.md CLAUDE.md CODE_OF_CONDUCT.md GEMINI.md LICENSE README.md RELEASE-NOTES.md assets docs gemini-extensi |
| agentskills | LICENSE |                                  Apache  | 138 | AGENTS.md CLAUDE.md CONTRIBUTING.md LICENSE README.md docs package.json skills-ref  |
| context7 | LICENSE | The MIT License (MIT) | 467 | LICENSE README.md SECURITY.md context7.json docs eslint.config.js gemini-extension.json i18n package.json pack |
| serena | LICENSE | MIT License | 1056 | AGENTS.md CHANGELOG.md CLAUDE.md CONTRIBUTING.md DOCKER.md Dockerfile LICENSE README-dev.md README.md compose. |
| gitnexus | LICENSE | PolyForm Noncommercial License 1.0.0 | 5183 | AGENTS.md ARCHITECTURE.md CHANGELOG.md CLAUDE.md CONTRIBUTING.md DoD.md Dockerfile.cli Dockerfile.web Document |
| playwright-mcp | LICENSE |                                  Apache  | 35 | CLAUDE.md CONTRIBUTING.md Dockerfile LICENSE README.md SECURITY.md cli.js config.d.ts index.d.ts index.js pack |

## Cảnh báo sớm (G0)

| # | Repo | Vấn đề | Ảnh hưởng |
|---|---|---|---|
| W1 | gitnexus | License **PolyForm Noncommercial 1.0.0** — cấm dùng cho mục đích thương mại. | Rủi ro cao cho enterprise (VNPT). Phải xử lý ở scorecard tiêu chí 4 và ADR Serena-vs-GitNexus. Baseline đang cài GitNexus (tùy chọn). |
| W2 | karpathy-skills | Không có file LICENSE; README mục "License" ghi "MIT". | Chấp nhận được nhưng ghi nhận; chỉ lấy nguyên tắc, không copy nguyên văn. |
| W3 | playwright-mcp | Repo chỉ là wrapper npm (35 file). Source thật ở monorepo `microsoft/playwright` tại `packages/playwright-core/src/tools/mcp`. | Clone sparse thêm `references/playwright-monorepo` để phân tích T3. |
| W4 | deepseek-harness | Monorepo 8 865 file (apps/, packages/, native/, python/, vendor/). | Phải khoanh vùng: packages/ + docs/ trước; vendor/ và snapshots/ bỏ qua. |
| W5 | cybersecurity-skills | 4 532 file, Apache-2.0, có ATTACK_COVERAGE.md. | Cần lineage check với upstream trước khi phân loại (12.4). |

## BMAD sub-modules (bổ sung G2, clone 2026-09-03)

BMAD Method (mục 12.1) đăng ký BMB/TEA/Loop như module ngoài trong `bmad-method@6.11.0/bmad-modules.yaml`; clone riêng để phủ yêu cầu 12.1.

| Repo | URL | Commit | Commit date | License (dòng đầu) | Files |
|---|---|---|---|---|---|
| bmad-builder (BMB) | https://github.com/bmad-code-org/bmad-builder | `4a1422274a2acb0fb0ec0511753da6263948f072` | 2026-08-31 | MIT License | 297 |
| bmad-tea (TEA) | https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise | `7ba2130193c473b53d2e323b4da9a80697eef88e` | 2026-09-01 | MIT License | 948 |
| bmad-loop (Loop) | https://github.com/bmad-code-org/bmad-loop | `d489c422d4e1ec3c7b8c49d59e627c46f5dd89ec` | 2026-08-29 | MIT License | 259 |
