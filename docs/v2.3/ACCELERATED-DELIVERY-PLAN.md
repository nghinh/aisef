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
             CODE-FREEZE → B2-ORACLE-SIGNED [OD] → B2-MEASURE → RC-FREEZE → XPLAT-QUAL
             → REL-GOV-OBSERVED → OWNER-PUBLISH-AUTH → PUBLISH
```

**Cái 4 track mua được:** E3, A2-primitives, E7, L2-LIFECYCLE, D2, cụm quality/tripwire không tranh file, toàn bộ
L5-EARLY, B6a và B2-prep **rời khỏi spine và chạy NGAY HÔM NAY** thay vì xếp hàng sau exit W2/W3/W4. Gate theo đợt
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
| **PRODUCT** | L5-EARLY (ngay); L5-AUTHOR (B6*,B4); L5-FEEDBACK (G4); L5-GATEWAY (B5); L6-EVAL (B2 prep ngay, measure sau CODE-FREEZE); L6-RELEASE | B6b/B4 ← C-6 (BUNDLE-FORMAT-2); G4 ← C10/G10; B5 ← E1,A2,C8,D1 |

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
9. **B2 PREP** (L6-EVAL prep): dựng `validation/v23/ground_truth/**` corpus offline + soạn protocol B2 (freeze
   trước khi đo); chưa tốn tiền, chưa cần external.
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
  + security verification + reproducibility + B2 external evaluation. Không gate nào bị bỏ; không bằng chứng dở
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
| 29/12–04/01 | #6 signed-CI; D3→C7; BUNDLE-FORMAT-2 freeze (QĐ #71+S3); **B2 protocol freeze** |
| 05/01–11/01 | Batch CORE-exit (≈W2 gate); G3; C10/G10; B6a→B6b |
| 12/01–18/01 | C6; G6; C1+C3b (built, OFF); V21-41; D1–D3 acceptance (batch SEC-exit ≈W3 gate) |
| 19/01–25/01 | B4; G4; **B5 bắt đầu**; batch ORCH-exit (≈W4 gate) |
| 26/01–01/02 | B5 land; batch PROD-exit (≈W5 gate); **B2-ORACLE-SIGNED [owner]**; **CODE-FREEZE** |
| 02/02–08/02 | **Chiến dịch mutation RC** (~50h wall/4w với lever, dự phòng 5 ngày; gồm đo sạch 33 target dirty + _attempt) + B2-MEASURE |
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
5. **Phụ thuộc ngoài W6** — ≥3 repo đại diện + ≥2 evaluator độc lập + B2-SPEND: lead time tuyển chọn nằm ngoài
   engineering; không khởi động tuần này thì mốc 26/01 (oracle signed) vỡ.

**Gói quyết định owner #1 (quyết một lần, mỗi mục có default):**
| # | Quyết định | Default đề xuất |
|---|---|---|
| 1 | OD-B1B (re-pin B1 manifest hay chờ RC đo sạch) | chờ RC (fail-closed giữ nguyên) |
| 2 | PIN-57: giữ 3 checker ngoài registry hay amendment re-pin | giữ ngoài (gói transition đã soạn, §10.4 báo cáo) |
| 3 | Ký execution-order table trích dẫn đo E5 (lever 62%) | ký sau benchmark bounded tuần 01/12 |
| 4 | B2-SPEND: danh sách ≥3 repo ngoài + ≥2 evaluator + cap chi phí | owner cung cấp ứng viên; engineering đề xuất 2 dogfood (todo-oc, todo-cli) làm seed nội bộ, KHÔNG thay thế repo ngoài |
| 5 | Các QĐ tại freeze, nhận defaults: V21-57(keep), V21-24/25/70/71b(keep), V21-54(A), S4(build), #71(ii)+S3(A), V21-61b/58(keep) | nhận toàn bộ defaults |
| 6 | C3b thresholds (ratify trước khi bật) + W3 guest/server cho bwrap canary | ratify ở SEC-exit |
| 7 | Shard mutant-level 2 target nóng (thiết kế record mới) | KHÔNG làm trong v2.3 trừ khi lever (3) không đủ |

Mọi điều khoản charter §4 giữ nguyên: không false PASS, không allowlist masking, evidence append-only, không đổi
master/tag/PyPI tới ủy quyền cuối, không giảm scope v2.3, không dời capability bắt buộc sang v2.4 vì lịch.
