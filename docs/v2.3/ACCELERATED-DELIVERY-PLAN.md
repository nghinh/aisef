# AISEF v2.3 — KẾ HOẠCH GIAO HÀNG TĂNG TỐC (owner directive 2026-11-25: đổi CHIẾN LƯỢC THI CÔNG, không đổi scope/trust)

Mục tiêu: **v2.3.0 cuối tháng 2/2027** (mốc làm việc: 2027-02-26), đủ mọi gate bắt buộc của RELEASE-CHARTER §2.
Nguồn sự thật không đổi: `DEPENDENCY-DAG.md` (cạnh [S]/[F]/[G], quyền sở hữu file §4, R10), `MASTER-CHECKLIST.md`
(147 ID), `RELEASE-CHARTER.md`. Tài liệu này KHÔNG thay DAG — nó tái nhóm các lane thành 4 track chạy song song và
đặt lịch; mọi cạnh cứng của DAG giữ nguyên hiệu lực.

## 1. DAG tới hạn theo capability (spine) và điều 4 track mua được

Xương sống [S]/[F] KHÔNG thể rút ngắn bằng song song hóa (mỗi mắt xích là hợp đồng ngữ nghĩa/bàn giao file, không
phải gate đợt):

```
B1-evidence (đóng W1b)
   └─ FORMAT-4 freeze (E6, L2-JOURNAL)  ←←← MẮT XÍCH NHỊP ĐỘ CỦA TOÀN KẾ HOẠCH
        ├─ E2/E4 (L2-ACCOUNTING) ─ C8 (L3-CLIENT, bàn giao client.py) ─ D3 ─ C7 ─ C6 ─┐
        ├─ E1 ∥ (E7→A2-INT) ─ #6 signed-CI                                            ├─ CODE-FREEZE
        ├─ C5 (L4-PARALLEL) ─ G6 / C1                                                 │
        └─ BUNDLE-FORMAT-2 ─ C10/G10 ─ G4; B6a→B6b→B4; B5                             ┘
             CODE-FREEZE → RC-FREEZE → XPLAT-QUAL
             → REL-GOV-OBSERVED → OWNER-PUBLISH-AUTH → PUBLISH

             (dòng cũ: CODE-FREEZE → B2-ORACLE-SIGNED [OD] → B2-MEASURE → RC-FREEZE — cạnh B2 đã gỡ
              [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md])
```

**Cái 4 track mua được:** E3, A2-primitives, E7, L2-LIFECYCLE, D2, cụm quality/tripwire không tranh file, toàn bộ
L5-EARLY, B6a ~~và B2-prep~~ [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md] **rời khỏi spine và chạy NGAY HÔM NAY** thay vì xếp hàng sau exit W2/W3/W4. Gate theo đợt
(mỗi wave một lần đóng băng + requalify cả cây) được thay bằng **gate theo batch capability** (mục 4).

## 2. Bốn track — lane, file ownership, hợp đồng giao diện

Quy tắc bất biến: **single-writer per file per phase** (DAG §4a/b); file nóng dùng chung đi theo LỊCH BÀN GIAO
dưới đây; R10 read-only (aisef2/cohort/**, 5 checker authority validation/v2, closure-evidence/** append-only);
INV-MUTATION-AUTHORITY; mọi byte aisef2/ đổi ⇒ F5 qualification của batch đó (KERNEL-COUPLING-01).

| Track | Lane (theo DAG) | Chờ hợp đồng |
|---|---|---|
| **CORE** | đóng W1b; L2-LIFECYCLE; L2-SIGN→L2-AUTH (A2); L2-PROBE-OS (E3)*; L2-JOURNAL (E6/FORMAT-4); L2-RECORD (E7); L2-ACCOUNTING (E2/E4); L2-CI (#6) | E2/E4 ← C-1; E1/A2-INT ← C-1,C-2; #6 ← C-2 |
| **SECURITY** | L3-SANDBOX (D1,D2,quality anti-gaming); L3-CLIENT (C8→C7/G3/D3); L3-PLATFORM (V21-41) | D1 ← E3; C8 ← client.py từ E2; V21-41 ← A2 |
| **ORCHESTRATION** | L4-PARALLEL (C5, BUNDLE-FORMAT-2); L4-REVIEWER (C6); L4-CONTEXT (C10/G10); L4-RESUME (G6); L4-MONITOR (C1,C3b) | **toàn track ← C-1 (FORMAT-4 freeze)** đúng luật directive |
| **PRODUCT** | L5-EARLY (ngay); L5-AUTHOR (B6*,B4); L5-FEEDBACK (G4); L5-GATEWAY (B5 — GIỮ trong scope); ~~L6-EVAL (B2 prep ngay, measure sau CODE-FREEZE)~~ [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md]; L6-RELEASE | B6b/B4 ← C-6 (BUNDLE-FORMAT-2); G4 ← C10/G10; B5 ← E1,A2,C8,D1 |

(*) E3 nằm ở W2/CORE theo wave nhưng là tiền đề cứng của SECURITY (`E3 → D1 [S/F]`): CORE staff E3 ĐẦU TIÊN.

**Hợp đồng phải freeze trước khi consumer chạy** (từ inventory; mỗi freeze kèm gói quyết định owner mặc định):
- **C-1 FORMAT-4** (journal/{format4,transitions}.py + event schema) — producer L2-JOURNAL; consumer E2/E4, E1, C7,
  C5, G6, C3b. Kèm QĐ V21-57 (default keep). *Mắt xích nhịp độ.*
- **C-2 A2 signing** (journal/sign.py, event.py, lineage.py; --verify --expect-pubkey) — consumer V21-41b, G6, B5,
  #6. Kèm V21-54 (default A).
- **C-3 ClientAdapter** (client_adapter.py: argv/config_endpoint/parse_stream/identity) — consumer C7,G3,D3,C1,C6,B4,B5.
- **C-4 Confinement D1–D3** (confine.py, keybroker.py) — consumer B5, C7, V21-11; QĐ S4 ở D1-freeze (default build).
- **C-5 E5 Stage lifecycle — ĐÃ frozen/landed.** C-7 F5/F5-ROUND — ĐÃ landed.
- **C-6 BUNDLE-FORMAT-2** (bundle.py) — consumer C10/G10, B6b/B4; QĐ #71+S3 ở freeze này.
- Bàn giao file nóng (thứ tự khóa): `lineage.py` L2-SIGN→L2-ACCOUNTING→L3-PLATFORM→L4-RESUME; `client.py`
  L2-ACCOUNTING→L3-CLIENT→L4-MONITOR; `run.py` L2-RECORD→L3-CLIENT(D1 hunks)→L4-PARALLEL/RESUME→L5-AUTHOR(--check);
  `story_runner.py` L2-ACCOUNTING(#39b)→L3-SANDBOX(Party)→L4-PARALLEL/MONITOR; `adapters.py` L3-SANDBOX→L4-CONTEXT→L5-FEEDBACK.

## 3. Việc bắt đầu NGAY (không chờ gì — mọi cạnh vào đã thỏa trên cây hiện tại)

1. **CORE/W1b:** đẩy nốt batch trust-gate (suite→push→CI→báo cáo) — đang chạy.
2. **L2-LIFECYCLE** (V21-27, V21-34, #26, `Merged.original`).
3. **L2-SIGN** — A2 primitives (#10; QĐ#1 đã quyết, COMPAT-MATRIX đã frozen).
4. **L2-PROBE-OS / E3** (+#16, V21-59/60/88) — mở đường SECURITY.
5. **L2-RECORD / E7** (refactor thuần, golden RUN.json byte-identity).
6. **L2-JOURNAL:** thiết kế FORMAT-4 + bảng transition → ĐÓNG BĂNG SỚM NHẤT CÓ THỂ (mắt xích nhịp độ); hunks
   event.py chờ L2-SIGN merge [F].
7. **SECURITY/D2** (Seatbelt macOS) + cụm quality anti-gaming/tripwire không tranh file (#79–#96 subset).
8. **PRODUCT/L5-EARLY** trọn gói (B6a module, V21-43/47/52/42b, #35–#37).
9. ~~**B2 PREP** (L6-EVAL prep): dựng `validation/v23/ground_truth/**` corpus offline + soạn protocol B2 (freeze
   trước khi đo); chưa tốn tiền, chưa cần external.~~ [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md — Tier-0 đã land thì giữ; không làm thêm việc B2-riêng trừ khi capability khác còn giữ yêu cầu.]
10. **Mutation order-table prototype** (mục 5a): sinh bảng execution-order từ per_target.json của E5, benchmark
    trên 2–3 target bounded, trình owner ký nguồn-trích-dẫn.

## 4. Kiểm chứng 3 tầng (thay gate theo wave)

- **Fast dev (<15'):** ruff + unit đích + contract test của lane + security-negative liên quan; chạy trên mỗi lane
  trước mọi merge nội bộ track.
- **Integration (per capability batch):** affected-package tests + 6 CI legs native + cross-lane compat + regression
  bắt buộc + **F5 targeted qualification của đúng các target batch đụng** (KERNEL-COUPLING-01: mọi target đổi =
  MEASURED, reuse = VERIFIED_REUSE, 0 UNRESOLVED, known-bad vẫn FAIL) + closure-evidence sạch. Một batch = một lần
  đo (LÔ) — không đóng băng cả cây, không requalify toàn bộ.
- **RC:** sealing đầy đủ + toàn bộ qualification bắt buộc + **chiến dịch mutation toàn diện** (ngân sách mục 5c)
  + security verification + reproducibility ~~+ B2 external evaluation~~ [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md]. Không gate nào KHÁC bị bỏ; không bằng chứng dở
  dang nào được dán QUALIFIED (chuẩn admissibility 455c6bbc).

## 5. Hiệu năng mutation — số đo thật từ E5 (1.880 mutant / 103,4 giờ đo được)

Profile tái lập được: `aisef-private-evidence/2026-11-25-accel-plan/{parse_e5.py,report.txt,per_target.json}`.
- **Phân bố chi phí:** top-2 target = 77% toàn chiến dịch (`run.py::execute` 49,0h/464 mutant; `_attempt`
  30,6h/696); top-10 = 95%. Overhead process/fixture chỉ 1,7% — không phải đòn bẩy. T0 3,9% — load-bearing
  (ORD-1/VS-6), không đụng. Bracket confirmed-kill 7,2% — BẮT BUỘC, chỉ báo giá, không đề xuất yếu đi.
- **(a) Đòn bẩy chính — reorder kill list theo tần suất giết lịch sử:** 79,3% thời gian nằm ở các file chạy TRƯỚC
  file giết; mô phỏng reorder trên chính timings đo được: **tiết kiệm ~63,7h = 62% (ƯỚC TÍNH)**. **ĐÃ BENCHMARK
  BOUNDED (2026-11-25, A/B cùng máy cùng lúc, 2 target `delivery`+`client_on_path`, 49 mutant): declared 76,2
  phút vs ordered 24,5 phút = tiết kiệm 67,8%, verdict hai bên GIỐNG HỆT (49/49 KILLED, 0 survivor) — bằng chứng
  tại aisef-private-evidence/2026-11-25-accel-plan/ordbench-{ba,bo}.log.** Runner ĐÃ hỗ trợ
  execution-order có trích dẫn nguồn đo (ORD-4, _order_problem): không đổi code, chỉ cần bảng order sinh từ
  per_target.json + **owner ký nhận E5 là measurement được trích dẫn**. Generator/detection/audit/provenance không
  đổi (survivor vẫn chạy đủ mọi file).
- **(b) Xếp việc LPT theo chi phí đã đo** (hết static partitioning — E5 đạt hiệu suất đóng gói 0,49): miễn phí.
- **(c) Ngân sách RC từ số thật:** registry 994 target ⇒ **27.901 mutant**; chiếu theo bucket kill-set-size đo được:
  **430–480 giờ-worker**, wall ~108–120h (4 worker) / ~54–60h (8 worker); critical path đơn lẻ = execute ~49h.
  **Với đòn bẩy (a) (ƯỚC TÍNH):** ~200 giờ-worker, wall ~50h (4w) / ~27h (8w), execute ~18h.
- **(d) Flag cho owner (không tự làm):** shard mutant-level cho 2 target nóng cần thiết kế record mới + ruling.
- **Giao thức RC đã chốt từ bài học E5:** mỗi-target-một-invocation + commit record xen giữa (hết dirty-identity).

## 6. Mốc tuần đến 2027-02-26 (giờ VN; mỗi mốc = capability-batch gate tầng Integration)

| Tuần | Mốc chính |
|---|---|
| 25/11–30/11 | Đóng batch trust-gate W1b (CI xanh, báo cáo); khởi động 10 việc mục 3; bảng order-table prototype |
| 01/12–07/12 | **FORMAT-4 design freeze** (gói QĐ owner #1 đính kèm); E3 + L2-LIFECYCLE land; benchmark order-table |
| 08/12–14/12 | **C-1 FORMAT-4 FREEZE** → mở ORCH track (thiết kế C5/#5) + E2/E4; A2-primitives + D2 land |
| 15/12–21/12 | E2/E4 land (batch CORE-2); **D1 bắt đầu** (E3 xong); E7 golden land |
| 22/12–28/12 | E1 + A2-INT; **C8 bắt đầu** (nhận client.py); C5 land (batch ORCH-1) |
| 29/12–04/01 | #6 signed-CI; D3→C7; BUNDLE-FORMAT-2 freeze (QĐ #71+S3); ~~**B2 protocol freeze**~~ [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md] |
| 05/01–11/01 | Batch CORE-exit (≈W2 gate); G3; C10/G10; B6a→B6b |
| 12/01–18/01 | C6; G6; C1+C3b (built, OFF); V21-41; D1–D3 acceptance (batch SEC-exit ≈W3 gate) |
| 19/01–25/01 | B4; G4; **B5 bắt đầu**; batch ORCH-exit (≈W4 gate) |
| 26/01–01/02 | B5 land; batch PROD-exit (≈W5 gate); ~~**B2-ORACLE-SIGNED [owner]**~~ [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md]; **CODE-FREEZE** |
| 02/02–08/02 | **Chiến dịch mutation RC** (~50h wall/4w với lever, dự phòng 5 ngày; gồm đo sạch 33 target dirty + _attempt) ~~+ B2-MEASURE~~ [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md] |
| 09/02–15/02 | XPLAT-QUAL (Linux+Windows+mac), reproducibility, release records, REL-GOV-OBSERVED |
| 16/02–26/02 | Buffer sửa NO-GO một vòng; OWNER-PUBLISH-AUTH; **PUBLISH ≤ 26/02** |

So sánh: lộ trình cũ = spine + **6 chu kỳ gate toàn-cây tuần tự** (mỗi exit: full suite ~1,6h + 6 CI legs + sealing
+ requalify, và KHÔNG lane wave sau nào chạy trước exit wave trước). Lộ trình mới = cùng spine, gate theo batch,
~9–10 lane rời spine chạy ngay ⇒ phần "chờ exit" biến mất; phần đo RC giảm 62% (ƯỚC TÍNH, chờ benchmark + chữ ký
owner). ETA chi tiết ngoài phần đo được là ước tính lịch, không phải cam kết đo.

## 7. Top-5 rủi ro lịch + gói quyết định owner (một gói, theo directive §6)

**Rủi ro:**
1. **FORMAT-4 freeze trượt** — mắt xích nhịp độ của cả ORCH + accounting; mitigations: staff mạnh nhất, freeze
   design-first, QĐ batch sẵn defaults.
2. **Trust-gate B1/REVERIF/ORCH đỏ tới RC** — nếu OD-B1B không quyết và RC campaign chưa chạy, b1/q0/currency giữ
   NOT QUALIFIED (đúng fail-closed) và dồn toàn bộ rủi ro xanh-hóa vào tuần 02/02.
3. **File nóng single-writer** (client.py, run.py, lineage.py, story_runner.py, adapters.py) — trễ một bàn giao là
   dây chuyền; lịch bàn giao ở mục 2 là hợp đồng, đổi phải qua integrator.
4. **Ngân sách RC** — 430–480 wh chưa lever; lever 62% là ƯỚC TÍNH chưa benchmark + cần owner ký trích dẫn E5;
   nếu không có lever, cần 8 worker (~60h wall) hoặc +2–3 ngày lịch.
5. ~~**Phụ thuộc ngoài W6** — ≥3 repo đại diện + ≥2 evaluator độc lập + B2-SPEND: lead time tuyển chọn nằm ngoài
   engineering; không khởi động tuần này thì mốc 26/01 (oracle signed) vỡ.~~ **RỦI RO ĐÃ RÚT — resolved-by-scope-change** [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md]: đánh giá external không còn trong scope release v2.3; owner tự tổ chức đánh giá sau phát hành (ruling §2). Không đánh số lại các rủi ro khác.

**Gói quyết định owner #1 (quyết một lần, mỗi mục có default):**
| # | Quyết định | Default đề xuất |
|---|---|---|
| 1 | OD-B1B (re-pin B1 manifest hay chờ RC đo sạch) | chờ RC (fail-closed giữ nguyên) |
| 2 | PIN-57: giữ 3 checker ngoài registry hay amendment re-pin | giữ ngoài (gói transition đã soạn, §10.4 báo cáo) |
| 3 | Ký execution-order table trích dẫn đo E5 (lever 62%) | ký sau benchmark bounded tuần 01/12 |
| 4 | ~~B2-SPEND: danh sách ≥3 repo ngoài + ≥2 evaluator + cap chi phí — **hạn chót 08/12** (back-calc từ mốc ký oracle 26/01: tuyển 2 tuần + đệm lễ 1 tuần + onboarding 1 tuần + labeling 2 tuần + adjudication 1 tuần; sau 08/12 là zero slack)~~ [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md — quyết định B2-SPEND và hạn chót 08/12 không còn tồn tại; zero USD đã chi] | ~~owner cung cấp ứng viên; engineering đề xuất 2 dogfood (todo-oc, todo-cli) làm seed Tier-0, KHÔNG thay thế repo ngoài~~ |
| 5 | Các QĐ tại freeze, nhận defaults: V21-57(keep), V21-24/25/70/71b(keep), V21-54(A), S4(build), #71(ii)+S3(A), V21-61b/58(keep) | nhận toàn bộ defaults |
| 6 | C3b thresholds (ratify trước khi bật) + W3 guest/server cho bwrap canary | ratify ở SEC-exit |
| 7 | Shard mutant-level 2 target nóng (thiết kế record mới) | KHÔNG làm trong v2.3 trừ khi lever (3) không đủ |
| 8 | A2/QA-1 — posture chữ ký: vendored Ed25519 thuần Python (RFC 8032, ~150 dòng, giữ `dependencies=[]`) hay `cryptography` (dependency runtime đầu tiên, wheel biên dịch) | vendored (draft A2 §QA-1; không tốn phí — là quyết định posture chuỗi cung ứng) |

Mọi điều khoản charter §4 giữ nguyên: không false PASS, không allowlist masking, evidence append-only, không đổi
master/tag/PyPI tới ủy quyền cuối, không giảm scope v2.3, không dời capability bắt buộc sang v2.4 vì lịch.

### 7.1 Trạng thái gói QĐ #1 — bản PROPOSED nhận 2026-11-26 (chưa phải authority)

Owner gửi "OWNER DECISION PACKAGE #1 (PROPOSED)" với điều khoản tự thân: *"These decisions become Owner authority
only when explicitly issued through the authorized Owner channel. Do not synthesize an Owner signature from this
draft."* Vậy: các hướng dưới đây được dùng làm **định hướng kỹ thuật** (công việc thuận chiều, đảo được), KHÔNG
ghi bản ghi authority/ledger nào từ bản này; mọi gate cần chữ ký owner (C-1/C-2 freeze, order-table ratification,
OD-B1B, PIN-57 amendment, B2 slate + cap) vẫn chờ bản ban hành chính thức.

| # | Hướng PROPOSED | Đã thi hành 2026-11-26 |
|---|---|---|
| 1 | OD-B1B: ACCEPT DEFAULT (chờ RC đo sạch; fail-closed dev reporting) | không đổi gì — trùng trạng thái hiện hành |
| 2 | PIN-57: CONDITIONAL GO — giữ ngoài registry NẾU chứng minh được vai trò non-checker từng module | PIN-57-MODULE-ROLES.md XONG: f5_recorder (observe.py) = non-checker CHỨNG MINH ĐƯỢC; f5_gate (ci_gate+impact) = verdict-determining HAI chiều; released_evidence_guard = verdict-determining chiều REFUSE → theo điều kiện của chính QĐ 2, hai module này cần đăng ký HOẶC ruling đích danh. Phát hiện cốt lõi: **không nhánh nào có default xanh** — đăng ký thì 2 test ghim PIN-57 đỏ, giữ ngoài thì Q0P-2 closed-list + R6 NOT_AUTHORIZED đỏ; live count hiện 54/57 (3 checker đỏ fail-closed: OD-B1B, currency, dirty). PIN-57 vì vậy cần ruling exact-digest của owner, không thể xử lý bằng default |
| 3 | Order-table: GO development + qualification proof; E5 timings = performance-study input; benchmark thêm target đại diện (survivor + long-running) trước khi ratify bảng RC | 6 nghĩa vụ chứng minh ghi nhận; benchmark bổ sung xếp lịch chạy nền (chưa chạy — tránh đụng commit window) |
| 4 | B2-SPEND: PREP GO / external HOLD — gói trước 08/12; Tier-0 + feasibility read-only ngay | B2-REPO-FEASIBILITY.md: 9 ứng viên, slate top-3 (jello MIT / mistune BSD-3 / tinydb MIT, có SHA snapshot) + 2 alternate; cờ: SHOULD "≥2 ngôn ngữ chính" không đạt trong ràng buộc probe-Python |
| 5 | Defaults: ACCEPT; FORMAT-4 ưu tiên freeze cao nhất; "không tự động certify C-1" | Q2/Q3 ĐO XONG (draft §13): R-COMMIT dạng nghiêm ngặt, R-SEALED dạng chính; draft hết mục STOP — thành freeze candidate chờ owner |
| 6 | C3b: DEFER ACTIVATION, not development; threshold ratify ở SEC-exit | không đổi gì — trùng kế hoạch §2 |
| 7 | Shard mutant-level: NO-GO for now | giữ nguyên default KHÔNG |
| 8 | A2/QA-1: CHỌN `cryptography` (không vendored Ed25519) + fail-closed + RFC vectors + no silent unsigned fallback | primitives đã land (`aisef2/journal/sign.py`, 16 test, vectors ghim từ văn bản RFC 8032): optional extra `aisef[signing]`, lazy import một chỗ, `SigningUnavailable` fail-closed; thành hard dependency CHỈ khi QĐ 8 ban hành tại C-2 freeze. Nghĩa vụ còn lại của QĐ 8 (reproducible wheels, offline-install test trên các nền hỗ trợ, escrow anchor off-box) = việc của C-2 freeze + L2-CI |

**Immediate actions của bản PROPOSED — trạng thái:** (1) leg macOS 3.12 tại bc8668f0: chẩn đoán = runner-capacity
("not acquired by Runner of type hosted", 3 notice thiếu capacity arm64; job chưa chạy bước nào — lỗi hạ tầng,
không phải code), đã rerun; (2) FORMAT-4 freeze prep + A2 primitives: ở trên; (3) E3/D2/E7/L5-EARLY/B2 Tier-0:
E7 và các lane chạm `run.py` xếp sau chữ ký order-table để không trả giá E5-scale hai lần (§5a); (4) gói B2-SPEND
trước 08/12: feasibility xong, phần evaluator slate + remuneration + cap cần input owner; (5) báo cáo tuần
critical-path: bắt đầu từ tuần này; (6) RC qualification/sealing/B2 external: giữ bắt buộc, không đổi.

### 7.2 OWNER DIRECTIVE 2026-11-26 — "ACCELERATED EXECUTION WITH UNLIMITED 9ROUTER TOKENS" (đã ban hành)

Hiệu lực ngay, qua kênh owner. Nội dung vận hành: trần token 9router/`mycombo` được gỡ cho phát triển v2.3
(KHÔNG gỡ kiểm soát security/evidence/release/chi tiêu ngoài); **CẤM DeepSeek tuyệt đối** (kể cả fallback/route
ẩn); song song hóa tối đa theo DAG + single-writer; chuẩn chất lượng §3 (adversarial review, red-before/
green-after, không commit khi suite đọc byte sống đang chạy); ưu tiên P0 trust-gates/CI → P1 FORMAT-4 freeze →
P2 A2 → P3 B2 → P4 mutation-perf; escalate CHỈ 5 loại (trust/arch xung khắc, chi ngoài ủy quyền token, privileged
ops/secrets, blocker release bất khả giảm, publish/tag/PyPI); "không coi proposal chưa ký là quyết định đã ban
hành" — gói QĐ #1 vẫn PROPOSED, riêng chất liệu QĐ 8 (backend `cryptography`, cấm vendored Ed25519) nay được
chỉ thị này ra lệnh trực tiếp ở P2, và clone-time checks B2 được P3 ủy quyền rõ (môi trường cách ly).

**Giới hạn báo cáo theo §1:** cấu hình local chỉ khai `mycombo` là model-name trên provider 9router
(~/.config/opencode/opencode.json — không có mention DeepSeek local); thành phần route thật nằm server-side
9router, local KHÔNG chứng minh được loại trừ DeepSeek ⇒ theo đúng điều kiện chỉ thị, **không lượt chạy trả phí
nào qua mycombo khởi động cho tới khi owner xác nhận thành phần combo (dashboard 9router) không chứa DeepSeek**.
**ĐÃ XÁC NHẬN 2026-11-26 (owner, kênh chat): combo `mycombo` không chứa DeepSeek** ⇒ gate paid-run qua
9router/`mycombo` MỞ theo chỉ thị (không trần token); các kiểm soát khác (evidence, release, chi ngoài token)
giữ nguyên. Chưa có lượt paid nào trong hàng đợi; lượt đầu tiên sẽ ghi lại model/provider identity theo §1.

### 7.3 OWNER RULING 2026-11-26 — "ACCELERATED EXECUTION, C-1 FREEZE AND ORDER-TABLE" (đã ban hành)

§1 **C-1 FREEZE APPROVED** — identities xác minh byte-exact (amendments/C-1-FORMAT-4-FREEZE.md), lane mở:
L2-JOURNAL, L2-ACCOUNTING (E2/E4), L4-PARALLEL (C5), L4-RESUME (G6) + ORCH đủ tiền đề; flip production cần
independent adversarial review + đủ negative controls; V21-57 KEEP. §2 **RULE-2 APPROVED**: hai benchmark nhận là
performance-study evidence (49/49 −67,8%; 56/56 −62,8% survivor-vững); E5 làm nguồn trích dẫn cho ordering (KHÔNG
làm dirty entries thành qualified); sửa round-writer để execution_order + declared order kiểm chứng độc lập;
negatives missing/stale/tampered/uncommitted/mismatched; tích hợp vào dev pipeline sau khi controls xanh; RC
ordered chưa QUALIFIED tới khi round-writer + source-bound checks xanh trên đúng RC source; KHÔNG shard. §3
**PIN-57 = OPTION C**: đăng ký+calibrate f5_gate + released_evidence (57→59), f5_recorder ngoài CHỪNG NÀO
observation chưa thể làm authority; chuẩn bị seq-14 exact (digest sau-patch + wiring tích lũy); dev+test được
phép, KHÔNG append ledger/thay pin tới khi owner duyệt bản cuối; 3 fail Q0 54/57 giữ hiển thị; ground_truth phải
được định đoạt rõ trong Q0 scope. §4 **B2**: slate jello/mistune/tinydb nhận về kỹ thuật (còn Linux +
independence-re-grep + toolchain đóng băng); giới hạn một-ngôn-ngữ chấp nhận cho planning (không tổng quát hóa
chéo ngôn ngữ); mục tiêu kinh tế $1.500–2.500, $6.000 chỉ là trần đề xuất; chuẩn bị ứng viên đích danh + rate;
KHÔNG engagement/chi/paid-trial/lộ tài liệu; gói cuối ≤08/12. §5 **A2**: cryptography xác nhận; hợp đồng cài đặt
với signing BẮT BUỘC cho run format-4 chuẩn; từ chối TRƯỚC preflight/network/journal/paid; wheelhouse offline +
3 OS native + reader cũ nguyên vẹn; chưa bật writer f4 production tới khi gate cài đặt + signing xanh. §6 tốc độ:
song song tối đa, worktree cách ly, không serialize sau PIN-57/B2-SPEND; ƯU TIÊN CODE hơn tài liệu kế hoạch.

### 7.4 OWNER RULING 2026-11-26 (thứ tư) — "C-1 AMENDMENT A2′ AND B2 EVALUATOR SOURCING" (đã ban hành, baseline 86de73d8)

§1 **A2′ APPROVED** với điều kiện chấp nhận: schema f4 gate/check+gate/decision bắt buộc story_id non-empty, bind
đúng attempt đang hoạt động (không phải chuỗi tùy ý), f1–3 nguyên vẹn byte+hành vi; completeness CHỈ cho
passed:true trong scope = sau decision trước của cùng (gate, story_id) hoặc biên attempt đầu; từ chối cite
duplicate/missing/cross-story/stale/invalid; cấm PASS rỗng bằng chứng; passed:false chỉ miễn completeness; ma trận
test bắt buộc (C3 red-before, omit PASS/FAIL, multi-gate/story, C5 interleave, retry boundaries, E5 fault tails,
story_id sai/cross-story/vacuous, A/R/F consistency, parity f1–3 + golden corpus); amendment dated scoped, KHÔNG
viết lại design frozen; adversarial review độc lập TRƯỚC khi chấp nhận tích hợp; file pin nào thay đổi → tính
transition chính xác + xin ủy quyền, không re-pin im lặng. §2 **A1: diễn giải ABANDONED được chấp nhận** (giữ
nghiêm; interrupt đầu hợp lệ; không rollback). §3 seq-14 acknowledged; 1–14 bất biến; 3 blocker Q0 giữ hiển thị;
không claim 59/59. §4 **B2 sourcing ZERO-USD**: được liên hệ ứng viên qua kênh nghề nghiệp công khai, xác nhận
availability/quals/rate/NDA, CoI, xin báo giá fixed-price không ràng buộc, trình top-2+backup; CẤM chia sẻ code/
bundle/label/secret; không subscription/hợp đồng/thanh toán; cap all-inclusive ĐÍCH $2.500 chờ duyệt slate+terms;
gói ≤08/12. §5 CORE-2 tiến hành (A2′, E2/E4, enum+vocabulary, projection tests, C5/G6 nơi interface ổn định);
single-writer; không bật writer f4 production trước các gate; RULE-2 chỉ với provenance tái lập; qualification
đích tại biên tích hợp; KHÔNG RC campaign. §6 chỉ nói 6-platform PASS khi CI đúng-HEAD kết luận; báo cáo kế =
commit thật + ma trận negative A2′ + tiến độ C5/G6 + Q0 + CI + B2 shortlist + dự báo critical-path.

### 7.5 OWNER DIRECTION 2026-11-26 — danh tính outreach B2 + cổng tích hợp A2′

§1: danh tính người gửi outreach B2 đã cấp (ghi trong hồ sơ riêng aisef-private-evidence/2026-11-26-b2-evaluators/
— không vào repo; năng lực cá nhân độc lập, không đại diện VNPT-IT/VGS); kênh ưu tiên Upwork/Codementor qua TÀI
KHOẢN XÁC THỰC CỦA OWNER; không tạo tài khoản, không lách xác thực, không nhãn hiệu VNPT; zero-USD giữ nguyên
(liên hệ không ràng buộc, screening, availability, báo giá — không hợp đồng/cam kết/chi). §2: KHÔNG tích hợp A2′
chỉ vì 79 test xanh — mỗi deviation trong 4 cái đã khai phải có: lệch chính xác so với ruling, hệ quả an
ninh/đúng đắn, bằng chứng negative-control, fix đề xuất hoặc amendment chính xác, disposition của reviewer độc
lập; deviation chưa giải quyết chạm schema/binding/completeness/E5-path/parity f1–3 = STOP; bypass trust-critical
→ fix + review lại trước tích hợp. §3: tiếp tục CORE-2/C5/G6/B2 nơi phụ thuộc cho phép; không báo CI PASS trước
khi workflow đúng-HEAD kết thúc; báo cáo kế = verdict review A2′ + 4 disposition + quyết định tích hợp + CI + độ
sẵn sàng outreach B2.

> [SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md]
> Ghi chú append-only cho §7.1–§7.5 (bản ghi lịch sử, giữ nguyên văn): mọi hạng mục B2 external trong các mục trên
> (B2-SPEND/slate/outreach/evaluator sourcing/oracle) đã bị gỡ khỏi scope release v2.3 bởi ruling owner 2026-11-26;
> không outreach nào từng được gửi, không tài khoản nào được tạo, zero USD đã chi. Không mục nào ở trên được coi là
> yêu cầu còn hiệu lực.

### 7.6 Scope change 2026-11-26: B2 external REMOVED — critical path tính lại

[SỬA ĐỔI SCOPE 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — xem amendments/SCOPE-B2-EXTERNAL-REMOVED.md]

**Critical path tính lại (thuần engineering — không còn mắt xích B2 nào):**

```
CORE-2 measured batch → W2c integration → C5/G6 (W4) → W3 → W5/B5 → CODE-FREEZE → RC campaign → PUBLISH
```

RC-FREEZE giờ chỉ còn các tiền đề: CODE-FREEZE, VERSION-BUMP-2.3.0, BUILD-REPRO-01, PUBLIC-DOCS (README) —
không có hạng mục B2 nào (DEPENDENCY-DAG §2, cạnh trực tiếp CODE-FREEZE → RC-FREEZE từ 2026-11-26).

**Quyết định owner còn MỞ (không còn mục B2 nào):**
- A2′ integration gate — verdict chưa có (§7.5 §2: review độc lập + disposition 4 deviation trước khi tích hợp);
- Order-table ratification — bảng RC chưa QUALIFIED tới khi round-writer + source-bound checks xanh trên đúng RC
  source (§7.3 §2);
- C-2 (A2 signing) freeze — gồm nghĩa vụ QĐ 8 còn lại (reproducible wheels, offline-install, escrow anchor off-box).

**Dự báo trung thực:** mốc cam kết **26/02/2027 KHÔNG đổi**. Phần sức làm W6 external-prep (tuyển chọn, protocol
freeze, oracle signing, B2-MEASURE) được chuyển về engineering, nên CODE-FREEZE **có thể** kéo sớm ~1 tuần so với
lịch mục 6 — đây là biên sớm-nhất-có-thể nêu dè dặt, KHÔNG phải cam kết ngày sớm hơn; mọi ETA ngoài phần đo được
vẫn là ước tính lịch (mục 6 giữ nguyên nguyên tắc đó). Không gate §5-charter nào yếu đi; không claim nào về
external validation/false-acceptance/cross-repo generalization được đưa ra.
