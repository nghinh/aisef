*[English](README.md) · Tiếng Việt*

# AISEF — AI Software Engineering Framework

AISEF làm phần mềm bằng coding agent và không tin lời agent. Gói trên PyPI, module Python và lệnh đều tên là
`aisef`.

Nguyên tắc nền, xuyên suốt mọi quyết định trong kho này:

> **Cần phán đoán thì giao cho model. Cần đảm bảo thì viết code.**

**AISEF 2.1** biến nguyên tắc đó thành runtime. `aisef run` thực thi một kế hoạch đã được chủ dự án phê duyệt trên một
repository git: với mỗi story, một phiên developer sửa code, và kernel V2 quyết định — dựa trên các probe độc lập kiểm
tra sản phẩm, không bao giờ dựa trên lời của developer hay test do chính developer viết — story được giao, chạy lại
hay rollback. Mọi quyết định được ghi vào một journal chuỗi băm, và `aisef run --verify` kiểm một lần chạy đã xong
đối chiếu với journal đó. 2.1 là cùng runtime V2 như 2.0, được kiểm định lại — xem [Có gì mới trong 2.1](#có-gì-mới-trong-21).

```bash
pip install aisef==2.1.0
```

- [Hướng dẫn dùng AISEF](docs/v2/USAGE.vi.md) · [English](docs/v2/USAGE.md)
- [Có gì mới trong 2.1](#có-gì-mới-trong-21) · [Thay đổi theo từng bản phát hành](CHANGELOG.md) · [Giới hạn đã biết](#giới-hạn-đã-biết-của-21)
- [RFC kiến trúc](docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md) · [Quy trình phát hành](docs/v2/RELEASE-PROCESS.md)
- [Framework 1.x (bề mặt legacy và công cụ lập kế hoạch)](#framework-v1-bề-mặt-legacy-và-công-cụ-lập-kế-hoạch)

## AISEF 2.1 làm gì

`aisef run` là đường thực thi có thẩm quyền. Một lần chạy, theo thứ tự:

1. **Đầu vào được niêm phong trước khi chạy bất cứ thứ gì.** Project bundle (yêu cầu, behaviour contract, phê duyệt
   của con người gắn chúng với nhau, kế hoạch) được nạp và mọi hash được kiểm lại; file yêu cầu phải đúng là file mà
   kế hoạch đã được duyệt theo; repository được clone tại baseline của kế hoạch và không bao giờ bị ghi.
2. **Kế hoạch được kiểm duyệt tĩnh.** Chín phép kiểm chạy trước khi gọi bất kỳ model nào; kế hoạch không qua bị từ chối
   kèm lý do.
3. **Route model được chứng thực.** Preflight liệt kê các model của provider và gửi vài probe rất nhỏ (≤16 token); route chỉ được
   chấp nhận nếu mọi câu trả lời đều do đúng model đã khai phục vụ, dưới cùng một fingerprint triển khai. Mọi trường hợp
   khác là *identity stop*: không phiên nào được mở.
4. **Story chạy theo thứ tự phụ thuộc.** Với mỗi story, phiên developer (OpenCode, trên đúng route đã chứng thực) sửa
   code trong git worktree riêng — một workspace, không phải sandbox: client chạy dưới user hệ điều hành của người vận
   hành (xem [Giới hạn đã biết](#giới-hạn-đã-biết-của-21)). Sau đó kernel chứng minh candidate:
   - **ProductProof** — các probe do harness sở hữu (gọi hàm Python, gọi CLI, hiệu ứng tiến trình, file artifact) kiểm
     từng behaviour contract trên candidate. Mã candidate chỉ chạy trong tiến trình agent của probe; kết luận do một
     controller không bao giờ import mã đó đưa ra, qua một kênh đã xác thực, nên trong một lần đánh giá mã đang bị
     kiểm không thể giả mạo một kết luận mà controller chấp nhận: mỗi dòng mang một xác thực dưới khoá mà nó không bao
     giờ có, và nhiều nhất nó chỉ chặn được quan sát của chính mình, việc đó được báo là lỗi harness, không phải
     SATISFIED (có một lỗ đã biết giữa các lần đánh giá, xem dưới). Nhưng nó vẫn khai sai được về chính nó — mã thoát,
     giá trị trả về — nên một candidate viết ra để làm vậy, hoặc nhận ra mình đang bị probe, có thể làm một sản phẩm
     hỏng ra kết quả SATISFIED (kết luận hành vi đạt của probe): bảo đảm nằm ở kênh, không nằm ở giá trị mà mã đang bị
     kiểm khai.
   - **Độ đầy đủ của test kỹ thuật** — test của developer phải chạy được, không rỗng và có liên quan; chúng là bằng
     chứng về chất lượng kỹ thuật, không bao giờ là bằng chứng sản phẩm đúng. Khi không quyết được tính rỗng, kết quả
     là INCOMPLETE và không bao giờ chặn.
   - **Bảo toàn** — sau khi merge, các nghĩa vụ của chính story và các nghĩa vụ PRESERVE của những story đã commit được
     chứng minh lại trên cây đã merge; một lần bị bác bỏ làm story bị rollback.
5. **Lỗi có chủ.** Mọi lỗi được định kiểu (PLAN, DEVELOPER, ENVIRONMENT, PROVIDER, INTEGRATION, REVIEW, SECURITY) và
   chỉ tiêu vào ngân sách chạy lại của chủ nó; một lần chạy lại cho developer biết, bằng sự thật công khai, criterion
   nào đã hỏng — không bao giờ lộ stimulus ẩn của phép chứng minh.
6. **Chi tiêu được đối soát, không ước lượng.** Request, lượt và token được tính lại từ bằng chứng trước và trong mọi
   phiên; chạm trần, hoặc chi tiêu không đối soát được, sẽ kết thúc lần chạy.
7. **Mọi thứ được giữ lại.** Thư mục chạy chứa journal thô, mọi candidate và lần merge trong bản clone, mọi luồng phiên
   và ledger preflight. `aisef run --verify` kiểm chuỗi băm và dựng lại kết luận giao hàng, sổ ProductProof và `main`
   cuối từ journal; kết quả từng story, điểm dừng ngân sách và lỗi story vẫn đọc từ `RUN.json` (V21-30).

Đứng sau là chín bất biến của kernel, được bật trong mọi lần chạy test — trong đó có *Requirement Authority* (chỉ
contract đã duyệt mới định nghĩa sự thật sản phẩm), *Independent Evidence* (tác nhân viết code không bao giờ định nghĩa
bằng chứng chứng nhận nó), *Typed Ownership*, *Immutable Provenance* và *No Prose As Control State* (không đầu ra nào
của model trở thành mã điều khiển). Xem [RFC kiến trúc](docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md) §4.

## Có gì mới trong 2.1

2.1 là một vòng kiểm định lại trên cùng runtime V2 của `aisef run` — tách controller/agent, journal chuỗi băm và
`aisef run --verify` không đổi về hình dạng; kernel sản phẩm `aisef2` tiến từ 2.0.0 mà không đổi diện mạo một lần chạy.
Từng thay đổi hành vi được truy vết trong [`docs/v2.1/REPORT.md`](docs/v2.1/REPORT.md) và
[`docs/v2.1/TRACEABILITY.md`](docs/v2.1/TRACEABILITY.md):

- **Criterion kế hoạch nhận biết cú pháp (V21-37).** Một criterion đọc mã Python không còn nhầm một dòng docstring bắt
  đầu bằng `from …` là import — lớp rollback-sai của 2.0 đã đóng. Một hồi quy phát hiện sau merge nay được trả về cho
  developer khi chính sách chạy lại cho phép, thay vì không thuộc về ai (V21-38).
- **Kênh verdict nay đúng giữa các lần đánh giá (V21-28).** Controller của probe chạy với `-S` cùng `-I`, nên một `.pth`
  cài vào site-packages không còn chạy bên trong controller sau — đóng ở mức cơ chế (việc giả mạo `.pth` đầu-cuối trong
  một `aisef run` thật chưa được đo).
- **Ba danh tính contract tách biệt.** Danh tính ngữ nghĩa của contract, phiên bản capability/API của probe và digest
  của byte đã chạy nay tách rời, nên `aisef bundle migrate` không còn mang theo một approval chỉ vì contract hash không
  đổi: nó báo `semantic_changes` / `needs_owner_reapproval`, và duyệt lại là hành động tường minh của chủ dự án. Giới hạn
  đã đo, chủ dự án chấp nhận (2026-10-18): trên bundle LedgerLock 2.0.0, 50 trong 53 approval được giữ chỉ dựa vào luật
  phiên bản capability, vì ba probe đổi hành vi mà không nâng phiên bản — là một giới hạn, không phải một khẳng định.
- **Phủ mutation đầy đủ** — 614/614 target, 0 MISSING (xem phần kiểm định bên dưới).

## Bắt đầu nhanh

Cần Python 3.11+, `git` 2.31+ và — cho một lần chạy thật — client [OpenCode](https://opencode.ai) trên `PATH` cùng một
endpoint provider tương thích OpenAI. `aisef run` được hỗ trợ trên **Linux và macOS**.

```bash
aisef run --check  --project bundle.json --settings run.json --repo ./myproject   # đầu vào + kiểm duyệt, không gửi request nào tới provider
aisef run          --project bundle.json --settings run.json --repo ./myproject --out ./runs/r1
aisef run --verify --project bundle.json --out ./runs/r1                          # dựng lại một lần chạy đã xong
```

- **`bundle.json`** (`aisef-v2-project/1`) — dự án: file yêu cầu, behaviour contract, phê duyệt của con người gắn mỗi
  contract với các yêu cầu của nó, kế hoạch (commit baseline và nghĩa vụ chứng minh của từng story), các sự thật công
  khai developer được biết, và với mỗi story các phụ thuộc và đường dẫn test.
- **`run.json`** (`aisef-v2-run/1`) — đúng một route model, danh tính provider, các trần ngân sách, giới hạn chạy lại
  theo chủ lỗi, timeout và giới hạn lượt. Không có giá trị mặc định.
- **Mã thoát** — `0` đã giao (PASS; `--check` sẵn sàng; `--verify` VERIFIED) · `1` chưa giao (FAIL hoặc NOT_REACHED;
  `--verify` REFUTED) · `2` bị từ chối trước khi chạy (một đầu vào không thoả, kế hoạch chưa được kiểm duyệt, identity
  stop).

Định dạng từng trường, thư mục chạy và mọi lý do từ chối: [docs/v2/USAGE.vi.md](docs/v2/USAGE.vi.md).

## 2.0 và 2.1 đã được kiểm định thế nào

2.1 là cùng runtime V2 được kiểm định lại — kernel sản phẩm `aisef2` (`5f34a3f3`) giống hệt 2.0 từng byte; không mã sản
phẩm nào bị đổi để chuẩn bị bản phát hành. Kiểm định riêng của 2.1: **độ phủ mutation 614/614 target, 0 MISSING** (97,41%
bị giết trong chiến dịch bổ sung); **phát hành lên PyPI ngày 2026-11-01**, wheel và sdist **giống hệt từng byte** với
release candidate đã đóng băng, kiểm lại sau khi tải lên; cổng mutation giữ nguyên **FAIL** với 7 survivor được chủ dự án
chấp nhận là rủi ro tồn dư có phạm vi. Bằng chứng 2.1:
[`closure-evidence/v2/v2.1/`](closure-evidence/v2/v2.1/), bắt đầu từ
[`V2.1-EXECUTIVE-HANDOVER.md`](closure-evidence/v2/v2.1/V2.1-EXECUTIVE-HANDOVER.md). Bảng dưới là kiểm định 2.0 của chính
kernel đó:

Bản ứng viên RC2 (`1565bcc`) được đóng băng cùng digest wheel và sdist, rồi kiểm định đúng như bản phát hành:

| phép kiểm | kết quả |
|---|---|
| toàn bộ bộ test, môi trường kín, trên đúng bản ứng viên | 5.454 test, 0 lỗi |
| CI | Linux (Python 3.11–3.14), macOS, Windows, lint, wheel — đều xanh |
| mutation testing phần mã quan trọng đã đổi | 261 target (5 đo lại trên mã cuối, 256 dùng lại sau phép chứng minh cơ học), 6.463 / 6.463 mutant bị diệt |
| các bậc kiểm định Q0–Q3 (toàn vẹn tĩnh, tuân thủ ngữ nghĩa, độ đầy đủ, tiêm lỗi) | GREEN trên Linux và Windows |
| Q4 — các projection điều khiển của kernel so với một mô hình tham chiếu độc lập, 100.000 lần chạy sinh ra | 100.000 / 100.000 khớp |
| Q5 — chạy lại thật một tập 12 lần chạy đã ghi, phát lại luồng model | 12 / 12 tái hiện, không lệch |
| build tái lập được | ba lần build lại độc lập trùng từng byte với wheel và sdist đã đóng băng |
| cài sạch | wheel đã cài: version, CLI, `aisef run --check / run / --verify` offline — PASS |
| smoke phát hành thật (một workload — LedgerLock, cũng là workload phát triển — 7 story, 67 nghĩa vụ chứng minh, một route model thật, macOS) | **RELEASE_SMOKE_PASS: NO** — giao hàng FAIL, 6/7 story commit, ProductProof 66/67, trượt 4/9 ngưỡng đăng ký trước; phát hành nhờ miễn trừ một lần của chủ dự án. Sản phẩm cuối thoả 59/59 spec nghiệm thu (0 chấp nhận sai, tính theo chính spec của bundle); review của model tìm ra 5 lỗi ngoài các spec đó, và chúng đã được giao — xem dưới |

Bằng chứng nằm trong [`closure-evidence/v2/release/`](closure-evidence/v2/release/), bắt đầu từ
[`V2.0-FINAL-RELEASE-REPORT.md`](closure-evidence/v2/release/V2.0-FINAL-RELEASE-REPORT.md).

## 2.1 khẳng định gì, và không khẳng định gì

**Khẳng định:** điều phối và kiểm chứng sản phẩm tất định, gắn với bằng chứng; trong một lần đánh giá, mã candidate
không thể điều khiển kênh kết luận (lỗ giữa các lần đánh giá được nêu dưới); bằng chứng thô của lần chạy được giữ lại
và kiểm lại được.

**Mô hình đe doạ:** người vận hành đáng tin; mã sinh ra có thể sai hoặc "lách".

**Không khẳng định:** tổng quát hoá cho mọi loại workload; chất lượng model; vượt trội so với V1; cô lập đa người thuê
có tính thù địch; cô lập hoàn toàn trước tiến trình độc hại của cùng người dùng hệ điều hành; bảo vệ trước chủ máy.
`plan_quality_verdict` luôn là `NOT_CLAIMED` trong 2.1.

### Giới hạn đã biết của 2.1

- **AISEF chạy bundle; nó không soạn bundle.** Project bundle V2 (contract, phê duyệt, kế hoạch) được chuẩn bị và
  phê duyệt bên ngoài `aisef run`; không có chuyển đổi tự động từ dự án 1.x. Một bundle 2.0.0 được buộc lại bằng
  `aisef bundle migrate`, lệnh này trả về những contract cần chủ dự án duyệt lại (xem [Có gì mới trong 2.1](#có-gì-mới-trong-21)).
- **Nghiệm thu chỉ tương đối với spec của bundle.** "0 chấp nhận sai" nghĩa là không story nào trượt chính contract
  của nó mà vẫn được giao. Trong smoke phát hành 2.0, review của model tìm ra 5 lỗi tái hiện được nằm ngoài 59 spec
  (crash, sai mã thoát ở những đường không contract nào chạm tới); chúng đã được giao vì review chỉ mang tính tham khảo.
- **Developer không bị giới hạn (V21-02, vẫn mở).** Client chạy dưới user hệ điều hành của người vận hành, với HOME,
  PATH, thư mục XDG, cấu hình OpenCode toàn cục (plugin, MCP server) và mạng của người đó. Trong smoke phát hành 2.0,
  các phiên developer đã đọc ra ngoài worktree — scratch của probe, journal đang chạy, bundle chứa stimulus, kernel đã
  cài — trước khi một story commit. 2.1 đã đóng lỗ hổng kênh verdict qua `.pth` ở mức cơ chế (bên dưới), nhưng giới hạn
  developer ở mức hệ điều hành vẫn mở; hãy giữ `evidence_anchor` của lần chạy ngoài thư mục run, nơi developer không ghi
  được ([ANCHOR-THREAT-MODEL.md](docs/v2.1/ANCHOR-THREAT-MODEL.md)).
- **Kênh verdict đúng ở mức cơ chế, không ở mức hệ điều hành.** Controller của probe nay chạy venv của lần chạy với
  `-I -S` (V21-28), nên một file `.pth` cài vào site-packages không còn chạy bên trong controller sau — lỗ hổng giữa các
  lần đánh giá của 2.0 đã đóng. AISEF vẫn chạy developer dưới user hệ điều hành của người vận hành, nên không khẳng định
  cách ly trước một tiến trình thù địch của cùng user ấy, và việc giả mạo `.pth` đầu-cuối trong một `aisef run` thật chưa
  được đo.
- **Toàn vẹn khi bị SIGKILL ngoài là có giới hạn (A-03).** Nếu `aisef run` bị SIGKILL trong cửa sổ hẹp giữa lúc gửi
  request provider và lúc ghi kết quả vào journal, tính toàn vẹn **nằm ngoài phạm vi được hỗ trợ của 2.1** — không khẳng
  định đã sửa hay đã kiểm chứng đầy đủ (chủ dự án quyết 2026-10-31). Mọi đường kết thúc bình thường (chạm ngân sách, chạm
  trần lượt, hết giờ, bị ngắt) đều che và giải phóng trong `finally` và được phủ.
- **`--verify` chứng minh tính nhất quán, không chứng minh tính xác thực.** Chuỗi băm không có khoá và `RUN.json` nằm
  cạnh nó trong cùng thư mục ghi được; viết lại nhất quán cả hai vẫn VERIFIED (V21-30).
- **Nền tảng.** `aisef run` thật được hỗ trợ trên Linux và macOS; mọi lần chạy thật đến nay đều trên macOS (Linux được
  kiểm trong CI với client và provider giả). Trên Windows gói cài được và bộ test của kernel chạy được, nhưng chạy thật
  không thuộc phạm vi khẳng định của 2.1.
- **Probe** chạy với thư viện chuẩn và chính mã nguồn của candidate (không có phụ thuộc bên thứ ba của dự án). Review
  của model và scanner (`ruff`, nếu đã cài) chỉ mang tính tham khảo, không bao giờ chặn.
- **Cổng mutation FAIL — 7 survivor được chấp nhận.** Verdict cổng mutation máy giữ nguyên FAIL (7 survivor chưa audit
  trong `client.py::session` và `story_runner.py::_attempt`); chủ dự án chấp nhận chúng là rủi ro tồn dư có phạm vi — không
  phải lỗi của một verdict, nghĩa vụ, bí mật, ranh giới truy cập hay toàn vẹn bằng chứng. Chi tiết:
  [`V2.1-KNOWN-LIMITATIONS.json`](closure-evidence/v2/v2.1/V2.1-KNOWN-LIMITATIONS.json).

Toàn bộ backlog 2.1, kèm trạng thái tái hiện của từng mục: [docs/v2/V2.1-BACKLOG.md](docs/v2/V2.1-BACKLOG.md). Đánh
giá 360° độc lập về 2.0: [docs/DANH-GIA-360-V2.0-2026-10-06.md](docs/DANH-GIA-360-V2.0-2026-10-06.md).

## Chuyển từ AISEF 1.x

- `aisef run` giờ là V2. Phần thực thi của V1 là `aisef legacy run …` (cùng tuỳ chọn như `aisef run` của 1.x), và vòng
  cải tiến là `aisef legacy improve …`. Mọi lệnh 1.x khác — `doctor`, `setup`, `plan`, `mockup`, `approve`, `qa`,
  `report`, … — giữ nguyên.
- Dự án V1 không phải bundle V2: V2 chạy các behaviour contract đã duyệt và một kế hoạch đã qua kiểm duyệt, không chạy
  file story của V1.
- V2 không ghi gì vào repository của dự án; kết quả của nó là thư mục chạy và nhánh `main` của bản clone.

## Cài từ mã nguồn

```bash
git clone https://github.com/nghinh/aisef && cd aisef && pip install -e .
python3 -m unittest discover -s tests -q   # toàn bộ bộ test; không mở container (tests/__init__.py)
```

Không có phụ thuộc Python nào ngoài thư viện chuẩn.

## Cấu trúc

```
aisef2/                 kernel và runtime V2
  app/                  thứ `aisef run` thực thi: bundle, settings, preflight, client, run, verify, CLI
  product/              thẩm quyền yêu cầu, behaviour contract, ProductProof spec
  probe/                probe do harness sở hữu (gọi hàm Python, gọi CLI, hiệu ứng tiến trình, file artifact)
  plan/                 nghĩa vụ của kế hoạch, kiểm duyệt tĩnh và theo story, plan drift
  runtime/              phạm vi lần chạy và story, sentinel kết thúc, run spec
  orchestrate/          story runner: một đường điều phối có thẩm quyền duy nhất
  control/              chủ sở hữu lỗi, khả năng chạy lại, định tuyến
  journal/              journal chỉ-ghi-thêm, chuỗi băm, và các projection của nó
  quality/              độ đầy đủ của test kỹ thuật
  invariants/           chín bất biến, bật ở mọi tầng test
aisef/                  framework 1.x: chuỗi lập kế hoạch, cổng, guard, thực thi legacy
docs/v2/                cách dùng, phát hành và backlog 2.1
closure-evidence/v2/    mọi bản ghi kiểm định của 2.0
```

---

## Framework V1 (bề mặt legacy và công cụ lập kế hoạch)

Toàn bộ phần dưới mô tả framework 1.x mà 2.0 vẫn ship. Chuỗi lập kế hoạch (`plan`, `mockup`, `approve`, `gates`, …)
và các công cụ giữ nguyên; phần thực thi chỉ chạy sau bề mặt legacy có tên rõ ràng, `aisef legacy run` /
`aisef legacy improve`, không bao giờ là mặc định. [Bộ nhớ dài hạn có phạm vi](docs/MEMORY.md) (`aisef memory`)
**mặc định TẮT và đã đóng băng** từ 12/09/2026 — chỉ là ngữ cảnh tư vấn, không phải bằng chứng cho cổng.

Đầu vào của mỗi dự án 1.x là **một file**, `docs/requirements.md`; đầu ra là một ứng dụng chạy được, kèm bằng chứng
cho từng bước. Hướng dẫn từng bước: [`docs/HUONG-DAN-SU-DUNG.md`](docs/HUONG-DAN-SU-DUNG.md).

Kho skill tham chiếu **không cần clone tay**: `aisef setup` tự lấy về `~/.cache/aisef/references` đúng commit mà
`aisef/kit/catalog.json` ghim (khoảng 91 MB, một lần cho mọi dự án). Máy ngoại tuyến hoặc CI trỏ sang chỗ khác bằng
`AISEF_REFERENCES=/duong/dan`, hoặc dùng `aisef setup --no-fetch`. Tuỳ chọn: `docker` (cách ly khi chạy test),
`playwright` (trích hợp đồng thị giác từ mockup) — thiếu thì framework **nói thẳng là thiếu** chứ không giả vờ vẫn
kiểm được.

### Điểm khác biệt: harness

Phần lớn công cụ agent là một prompt cộng một vòng lặp. AISEF là một **harness**:
lớp giàn giáo lúc chạy quanh model, quyết định model **thấy** gì, được **chạm**
vào đâu, thế nào là **xong**, và cái gì được **ghi lại** sau đó. Mọi thứ trong
kho này thuộc đúng một trong sáu nhóm harness, và chính danh sách ấy là thước
nghiệm thu của dự án.

| # | Nhóm harness | Chứa gì | Ở đâu |
|---|---|---|---|
| 1 | **Instructions & rule files** | hiến pháp kỹ thuật biên dịch ra `CLAUDE.md` / `AGENTS.md`, danh mục skill có ghim commit, bốn vai agent mỗi vai một phiên mới, prompt có version | `kit/`, `harness/routing.py` |
| 2 | **Tools** | ba tool sinh bằng chứng (`test`, `lint`, `sast`) agent gọi bằng `aisef tool <tên> --story S`, cộng tra tài liệu; mỗi tool kèm câu "khi nào gọi · đọc kết quả thế nào · khi nào KHÔNG gọi" | `harness/tools.py` |
| 3 | **Sandboxes & execution environments** | bốn bậc quyền, hợp đồng `ExecutionProvider`, năm **bảo đảm có tên** (`network_none`, `read_only_fs`, `non_root`, `no_host_mount`, `secrets_absent`); provider thiếu bảo đảm nào thì nói tên bảo đảm ấy, suy biến được dán nhãn chứ không im lặng | `harness/sandbox.py` |
| 4 | **Orchestration logic** | định tuyến vai với **reviewer ≠ developer**, máy trạng thái story, xếp đợt theo phụ thuộc *và* phạm vi ghi, gói bàn giao mà mỗi slot ngữ cảnh đều khai nguồn | `control/`, `phases/` |
| 5 | **Guardrails / hooks** | mười guard trên ba mốc vòng đời, mỗi guard là một lệnh độc lập trả mã thoát, biên dịch ra đúng thứ client hỗ trợ, khai ở một chỗ duy nhất | `harness/guardrails.py` |
| 6 | **Observability** | sự kiện có cấu trúc và có provenance, chi phí và độ trễ từng phiên, mọi phép kiểm gắn **SHA của ứng viên**, sổ hành vi, bản ghi bàn giao và phán quyết, kho benchmark | `harness/observe.py`, `control/ledger.py`, `tests/bench/` |

Hai hệ quả đáng nói thẳng. Guard nằm ở nhóm 5 phía framework, nên **client không
bao giờ được tin** — client không gắn được guard tiền kiểm thì mức bảo đảm thấp
hơn được ghi lại, không phải mặc định là ổn. Và nhóm 6 gắn mọi kết quả vào một
commit, nên "test đã xanh" luôn có nghĩa "xanh trên **bản này**", không phải
"xanh ở đâu đó lúc nào đó".

### Harness của harness: framework tự cải tiến framework

Một story qua cổng chưa phải phần khó. Phần khó là chuyện xảy ra **sau khi** epic
được tuyên bố xong: story sau lặng lẽ làm hỏng story trước, một tiêu chí có test
mà test ấy chưa từng kiểm nó, một khoảng trống nằm im vì không ai đi tìm.

AISEF trả lời bằng một vòng thứ hai bọc ngoài vòng thứ nhất (ADR-004, hấp thụ từ
dòng nghiên cứu *Harness-of-Harness* và đo lại tại đây):

- **Ứng viên đóng băng.** Mỗi lượt đóng băng một SHA; mọi phép kiểm ghi rõ nó
  chạy trên ứng viên nào. Bằng chứng ở SHA khác là *stale* — một kết cục khác
  hẳn với *trượt*.
- **Sổ hành vi.** Mỗi tiêu chí, yêu cầu, loại kiểm định và màn hình có một trạng
  thái: VERIFIED, GAP hay REOPENED. Sổ là **phép chiếu** từ bằng chứng, dựng lại
  mỗi lần, không phải nguồn sự thật thứ hai.
- **Vòng cải tiến có trần.** `aisef legacy improve --epic E` đọc sổ, sinh **một** story
  sửa cho một khoảng trống, chạy nó như story thường, rồi kiểm lại. Dừng bằng
  code: hết gap, hết trần vòng, cải thiện biên ≤ 0 nhiều vòng liền, vượt trần chi
  phí, hoặc chính kế hoạch bế tắc.
- **Bảo toàn.** Story chạm tệp thuộc hành vi đã xác minh của story khác thì
  những hành vi ấy phải còn xanh — kiểm ở cổng, không phải hy vọng.
- **Đối chứng âm cho test.** Test mang mã tiêu chí nhưng đã xanh sẵn trước khi
  story viết dòng nào thì không chứng minh gì; cổng phát hiện và nêu tên test.
- **Cổng được chứng nhận.** Cả 16 mục cổng đều có ba control (dương tính, âm
  tính/mutant, môi trường), nên "cổng có chấm đúng không" là câu hỏi trả lời
  được bằng một lệnh.

### Sáu bước

```bash
cd /duong/dan/du-an-cua-ban

aisef doctor                       # môi trường có đủ chưa
aisef setup                        # dò stack, nạp skill, sinh CLAUDE.md + AGENTS.md
aisef compile                      # nối guard vào client (hook / plugin)

aisef plan                         # PRD → kiến trúc → UX → epic → story
aisef gates                        # xem cổng nào đang chờ người
aisef review prd                   # đọc artifact
aisef approve prd                  # duyệt

aisef mockup                       # mỗi màn hình một HTML + hợp đồng thị giác
aisef approve mockups
aisef approve readiness

aisef legacy run                   # V1 hiện thực: epic tuần tự, story song song
aisef legacy run --verify-only --story STORY-01-07   # kiểm lại ứng viên đã đóng băng, không mở phiên developer
aisef qa                           # bộ kiểm định
aisef devsecops                    # CI + Dockerfile + triển khai + runbook
aisef pre-deploy                   # cổng cuối
aisef report                       # báo cáo nghiệm thu + sổ hành vi + INDEX.md
aisef evidence STORY-01-04         # lịch sử một story hay một hành vi (AC-…, FR-…, qa:e2e)
aisef issues --format csv          # bảng gap/hồi quy từ sổ hành vi → _bmad-output/ISSUES.csv
```

Chạy nhanh không cần người duyệt: `aisef plan --auto-approve all`. Phê duyệt
tự động **luôn** được ghi dấu `auto` để về sau truy được tài liệu nào chưa
từng có người thật xem.

### Brownfield (dự án đã có mã)

```bash
aisef baseline                     # phân tích mã hiện tại → _bmad-output/baseline.md
aisef baseline --provider graphify # dùng Graphify graph (cài: uv tool install graphifyy)
aisef baseline --incremental       # cập nhật graph sau merge
```

Khi `baseline.md` tồn tại, `aisef plan` tự chuyển sang chế độ delta: giữ
artifact có sẵn, thêm ngữ cảnh brownfield vào prompt, đổi intent thành
`"update"`, và slot `blast_radius` trong prompt story hiện impact analysis
từ đồ thị mã trước khi implement.

### Sau khi có code

```bash
aisef doc vitest --topic coverage --story STORY-01-02
```

Tra tài liệu thật của thư viện (context7, có cache) thay vì đoán tên API; có
`--story` thì lần tra vào bằng chứng. Khi yêu cầu đổi sau phát hành:

```bash
aisef change FR-3 "Slug phải giữ dấu gạch dưới"
```

Ghi vào `docs/requirements.md`, đánh dấu PRD (cổng `prd` và các cổng sau
thành stale), sinh story delta `STORY-CH-01` với `covers=[FR-3]` — story cũ
giữ nguyên `DONE`.

```bash
aisef legacy improve --epic EPIC-01 --max-loops 3      # [--auto] không dừng ở cổng người
```

Vòng cải tiến theo bằng chứng (ADR-004 R3): QA → sổ hành vi → **một** story
sửa cho một hành vi GAP/REOPENED (`STORY-RP-01` trong `EPIC-RP-01`, sinh bằng
code) → `run` như story thường → QA → mốc `loops[]` + `LOOP-REPORT-<n>.md`.
Dừng bằng code: hết gap, đủ `improve.max_loops`, cải thiện biên ≤ 0
`improve.flat_loops` vòng liền, vượt `improve.cost_cap_usd`, hay story sửa bế
tắc kế hoạch (trả người kèm lời reviewer). Trước mỗi vòng ≥ 2 cần
`aisef approve improve` trừ `--auto`.

```bash
aisef legacy run --verify-only --story STORY-01-07
```

Story trượt chỉ vì môi trường đo (e2e nhạy tải máy) thì không cần trả tiền
cho một phiên developer để dựng lại mã đã có (ADR-004 R13): lượt kiểm-lại
lấy ứng viên ở HEAD nhánh story, chạy lại đúng phép kiểm ✗/thiếu ở SHA ấy,
giữ rà soát và bảo mật đã có ở cùng SHA, chấm đủ cổng; đạt thì merge như lượt
thường, trượt thì `failed` và không ăn vào `run.max_retries`.

### Cổng

Tám cổng, mỗi cổng hai lớp. **Cổng máy** chạy trước — nó bắt được thứ máy
bắt tốt hơn người (chu trình phụ thuộc, yêu cầu không kiểm chứng được,
story không khai phạm vi ghi). **Cổng người** chạy sau, trên thứ đã sạch.

Phê duyệt là **trạng thái trên đĩa**, không phải câu hỏi trong phiên chat:
người duyệt có thể là người khác, lúc khác, trên máy khác. Bản ghi phê
duyệt gắn với **băm nội dung** artifact — sửa tài liệu sau khi duyệt thì
phê duyệt hết hiệu lực, và sửa tầng trên làm mọi tầng dưới thành `stale`.

### Guard

Mười guard, mỗi guard là một lệnh trả mã thoát, nối vào ba mốc vòng đời:

| Mốc | Guard |
|---|---|
| trước mỗi tool | `write-scope` · `destructive` · `secret` · `git-stage` · `injection` · `process-ref` (luật 6: không mã story/epic trong nguồn) · `egress` (chặn kết nối ra host không trong allowlist) · `tool-bypass` (chạy thẳng lệnh test/lint của dự án thay vì qua `aisef tool` — lượt chạy ấy không vào bằng chứng) |
| sau mỗi tool | `diff-scope` |
| khi agent định dừng | `completion` |

Guard nằm ở phía framework, không ở phía client — client không được tin.
Cả Claude Code và OpenCode đều đã **chứng minh bằng phép thử trên agent
thật** rằng guard chặn *trước* khi tool chạy, chứ không phải phát hiện
sau. Client nào không gắn được guard tiền kiểm thì `aisef verify` chạy
lại toàn bộ trên diff, và `aisef compile` ghi rõ mức bảo đảm thấp hơn
vào báo cáo thay vì im lặng — năng lực là thứ được **khai và kiểm**, mặc
định là "chưa chứng minh", không phải "chắc là được". Từ v1.0.0, OpenCode
là client **hạng nhất**: guard chặn được, hợp quy 10/10 (ngang Claude — xem
ADR-006 §4), và `--format json` cho luồng máy đọc được (tool, token, cost
theo nhà cung cấp). Một guard là ngoại lệ: plugin API của OpenCode không có
mốc chặn tương đương `Stop`, nên `completion` **không** được nối ở đó — báo
cáo biên dịch liệt nó vào hậu kiểm, và cổng story hỏi lại đúng câu ấy từ bằng
chứng: trượt story chứ không giữ được phiên lại.

### Lỗi thật đã gặp

189 lỗi tìm bằng đo trên agent thật, xếp theo mười một lớp nguyên nhân kèm phép hồi quy (179–185 do lần dogfood đầu tiên trên gói 1.7.2 công khai tìm ra, đã sửa ở 1.7.3; 186 do lần chạy thứ hai trên 1.7.3, đã sửa ở 1.7.4; 187 do replay sạch lần chạy ấy trên 1.7.4 với client OpenCode gốc, đã sửa ở 1.7.5; 188 do cùng replay ấy tiếp trên 1.7.5, đã sửa ở 1.7.6; 189 do cùng replay ấy tiếp trên 1.7.6, **còn mở** — đã tái tạo tất định, chưa sửa ở bản phát hành nào): `docs/FAILURE-TAXONOMY.md`. Lỗi mới thì thêm một dòng vào đó cùng commit với test. Thay đổi theo phiên bản, kèm việc phải làm khi nâng cấp: `CHANGELOG.md`.

Khung áp chuẩn ấy lên chính nó. `docs/PROJECT-CLOSURE-GATE.md` là hợp đồng do chủ dự án duyệt để tuyên bố dự án kỹ thuật hoàn tất, và `aisef closure` chấm 27 tiêu chí của nó từ bằng chứng trên đĩa, không gọi model. Trên 1.7.6 đạt 24/27; ba tiêu chí còn mở là xác nhận ngoài bởi một người ngoài dự án — thứ không việc nội bộ nào thay được. (1.7.2 đọc 23/27: lần dogfood đầu tiên tìm ra ba lỗi P1 — D-026, D-028, D-029 — đã sửa ở 1.7.3; lần chạy thứ hai trên 1.7.3 tìm ra D-032, đã sửa ở 1.7.4; replay sạch lần chạy ấy trên 1.7.4 tìm ra D-033, đã sửa ở 1.7.5; cùng replay ấy tiếp trên 1.7.5 tìm ra D-034, đã sửa ở 1.7.6.) Một bản phát hành được nhận diện bằng sản phẩm nó chứa — digest nội dung trên cây của tag và digest wheel/sdist trên PyPI — chứ không bằng commit đang là HEAD, nên ghi bằng chứng về một bản phát hành không làm mất hiệu lực chính bản ấy (D-022, sửa ở 1.7.2).

### Hợp quy client

Hook và plugin là tạo tác **biên dịch ra** — đúng cú pháp không có nghĩa là
client chạy chúng. Lỗi 31 là ví dụ mới nhất: bản cài từ wheel biên dịch ra hook
trỏ vào một đường dẫn không tồn tại, cú pháp đúng, và **không guard nào chạy**.
Unit test không bắt được lớp này theo định nghĩa. Bộ hợp quy chạy mười phép thử
trên client thật, worktree thật, guard thật, `.claude/` không commit:

```bash
AISEF_CONFORMANCE=1 python3 -m unittest tests.conformance -v
```

Kết quả ghép vào `docs/CONFORMANCE.md` — mỗi ô là một phiên agent, đọc từ
đĩa (tệp còn/mất), từ luồng `tool_use` và bằng chứng guard tự ghi, không từ
lời agent. Dự án thử và log thô từng phép giữ ở `.conformance/<client>/`
(đổi bằng `AISEF_CONFORMANCE_DIR`) để tra lại một ô ✗ mà không phải đoán.
Bộ chạy **không** thừa hưởng biến `CLAUDE_*` của phiên gọi nó — chạy hợp
quy từ bên trong một phiên Claude là chuyện có thật, và phiên con thừa hưởng
cờ của phiên cha thì đo sai. Cổng
phát hành của chính kho này đọc bảng đó bằng code
(`AISEF_RELEASE=1 python3 -m unittest tests.test_release_gate`): cột
`claude` phải đủ mười ô ✅ và bảng không cũ hơn 14 ngày. OpenCode là hạng
hai trong V1 — có cột, không chặn. CI: `.github/workflows/conformance.yml`
chạy tuần.

### Phát hành

Gói, module Python và lệnh cùng tên **`aisef`** (từ 0.2.0; bí danh `aisdlc` đã bị gỡ trong 0.3.0).
Điều kiện đọc bằng lệnh, không bằng cảm giác:

```bash
python3 -m unittest discover -s tests -q && AISEF_RELEASE=1 AISEF_ACCEPTANCE=<dự án nghiệm thu> python3 -m unittest tests.test_release_gate -q
```

`AISEF_ACCEPTANCE` trỏ vào dự án dogfood đã nghiệm thu (v0.1.0: `e9`, phạm vi
EPIC-01): cổng đọc `pre-deploy-report.json` (đạt, có phạm vi, miễn có lý do)
và phê duyệt `pre-deploy` trên đúng bản ấy. Không đặt thì bỏ qua có nêu tên —
không tính là đạt.

```bash
uv build && uvx twine check dist/*
```

Từ 2.0 quy trình phát hành là của V2: [docs/v2/RELEASE-PROCESS.md](docs/v2/RELEASE-PROCESS.md).
Chỉ tag đúng `vX.Y.Z` mới tới PyPI production, và chỉ sau khi ma trận test, cài
sạch artifact staging và cổng phát hành V2 (uỷ quyền của owner) đạt trong
`release.yml`; tag RC/dev (`v*rc*`, `v*-rc*`, `v*.dev*`) chạy `staging.yml`,
không bao giờ publish. `aisef run` là runtime V2; V1 chạy bằng `aisef legacy run`.
Cổng V1 ở trên giữ cho bề mặt legacy, không còn chặn hay cho phép một bản phát hành.

Kho hồi quy dogfood (`tests/dogfood/`, bật bằng `AISEF_DOGFOOD=1`) dựng lại
dự án thử `par` từ đầu vào trong kho và so với mốc đã đo — chạy trước mỗi tag.

#### Benchmark đã đo được gì

Bốn đợt đo, bốn kết quả null hoặc không kết luận được — báo ra vì null cũng là kết quả:

| đợt | model | task | AISEF pass@1 | trần pass@1 |
|---|---|---|---|---|
| v0.3.0 | frontier | dễ | 1,00 | 1,00 |
| v1.3 simulator | agent yếu theo kịch bản | 12 khó | — (guard không tham gia, theo thiết kế) | — |
| **C-1 (12/09/2026)** | **không frontier, thật** | **12 khó** | **0,64** | **0,69** |
| **C-2 (15/09/2026)** | **không frontier, thật, cặp đã tuyển theo G5.3** | **12 khó** | **0,97** | **1,00** — [KHÔNG KẾT LUẬN ĐƯỢC](docs/BENCH-REPORT-C2.md): 11/12 task hoà ở trần, không còn độ phân giải để đo khác biệt |

[C-1](docs/BENCH-REPORT-C1.md): 9/12 task hoà, AISEF kém 2 task và hơn 1 task;
với 3 lượt mỗi task thì −0,05 không phân biệt được với nhiễu. Nhánh có harness
tốn **hơn 44 % số lượt và 51 % thời gian** để tới cùng chỗ. Guard nổ **1 lần
trên 72 lượt**, và đó là lệnh dọn `__pycache__`. Không nhánh nào ghi một tệp nào
ra ngoài phạm vi.

Hai điều phải đọc kèm:

- **20 trong 24 lượt trượt, ở cả hai nhánh, là phiên bị CLI cắt** khi model in
  ra cú gọi công cụ mà nó không phân giải được. Cohort này đo lỗi tích hợp
  model↔CLI ít nhất ngang với đo harness.
- **Chế độ bench chạy một phiên agent, không reviewer, không bảo mật, không
  cổng.** Nên C-1 đo **tầng guard**, không đo **tầng cổng**. Chi phí đo được
  nằm ở tầng cổng: trên một dự án 10 story thật, **67 % token vào** rơi vào lượt
  bị cổng chặn, `review` chiếm 18/31 lần ([E4](docs/E4-COST-DECOMPOSITION.md)).

Nên định vị trung thực với bằng chứng hiện có: AISEF **không** làm agent giải
được nhiều hơn. Thứ nó làm được, đo được, là **không cho gọi việc chưa xong là
xong**, và để lại bằng chứng nói rõ vì sao.

#### Giới hạn đã biết của 1.x

Khai ở đây vì mọi claim phải có bằng chứng; thứ chưa chứng minh gọi là chưa
chứng minh (quyết định chủ đầu tư 2026-09-06, `docs/RELEASE-PLAN-v0.1.0.md` §0):

- **Corpus đóng dự án là `marks-cli`** (ruling 2 của chủ dự án trong
  `docs/PROJECT-CLOSURE-GATE.md`): 7/7 story done và đã merge, pre-deploy đạt
  với phạm vi khai rõ, cổng PRE_DEPLOY do chủ dự án ký ngày 14/09/2026 — các
  tiêu chí G4.1–G4.7 đều PASSED từ bằng chứng của dự án ấy. *Trước đây*
  (v0.1.0–v1.0.0) phạm vi nghiệm thu dogfood là EPIC-01 của `e9` (7 story);
  EPIC-02..05 của `e9` chưa từng chạy, và `e9` không còn trên đĩa.
- **OpenCode là client hạng nhất từ v1.0.0**: hợp quy 10/10 (ngang Claude,
  xem ADR-006 §4). *Mục này ghi một hạn chế đã biết — "OpenCode + Serena ghi
  `.serena/` ngoài `write_scope` khai; harness từ chối đúng" — cho tới
  2026-09-14. Hạn chế ấy đã đóng: `.serena` nằm trong `HARNESS_OWNED`, harness
  không còn từ chối ghi chú của chính MCP server nữa.*

  ```
  python3 -c "from aisef.harness.guardrails import HARNESS_OWNED; print('.serena' in HARNESS_OWNED)"   # → True
  git log --oneline -S'".serena"' -- aisef/harness/guardrails.py   # → ea4d035, phát hành ở v1.3.0
  ```

  Cái thay chỗ nó hẹp hơn: `HARNESS_OWNED` là danh mục cứng, không có khoá cấu
  hình để mở, nên **công cụ kế tiếp** ghi ra ngoài danh mục ấy vẫn cần một commit
  vào framework. Xem [ROADMAP-POST-1.0 § 3](docs/ROADMAP-POST-1.0.md).
- **Agent trong container chưa có cách ly credential** (S1 blocked): V1 chạy
  agent trên host, chỉ kiểm định trong container; `doctor`/`pre-deploy` nêu
  tên bảo đảm thiếu, không im lặng.
- **`mutation` ở môi trường nghiệm thu là KHÔNG CHẠY ĐƯỢC** (công cụ chưa cài);
  được miễn có lý do ở `verify.waiver_reason`, hiện ◇, không bao giờ thành ✅.
  `image-scan` cùng loại (docker scout đòi đăng nhập, trivy/grype vắng).
- **`skills.offer` tắt** (A/B không thấy gain) và **`skills.inline` đã gỡ** —
  hai lần A/B trên agent thật cho `used` 0/0 trong khi nhánh inline thêm ~8,8k
  ký tự prompt, nên cờ và mã bị gỡ ở 1.4.0; dự án cũ còn khai thì nạp được kèm
  cảnh báo. **`repo_map` tắt** (`context.max_repo_map_chars = 0`, A/B hoãn).
- **`coverage`**: harness đọc số từ runner (`--coverage`/`--cov`); dự án chưa
  bật thì mục cổng là ○ chưa cấu hình, không phải đạt.

### Khi cổng chặn

Cổng chặn là framework đang làm việc, không phải framework hỏng. Ba ca hay
gặp và cách xử đúng:

| Cổng báo | Nghĩa là | Làm gì |
|---|---|---|
| `mockup còn N chỗ chưa chốt` | mockup gặp câu hỏi chưa ai trả lời và **đánh dấu** thay vì tự quyết | trả lời câu hỏi (thường nằm ở `open_questions` của PRD/UX), sửa tài liệu, dựng lại mockup |
| `story đụng vào yêu cầu đang bị câu hỏi mở chặn` | epic gán một FR mà PRD ghi là chưa quyết được | trả lời câu hỏi, hoặc bỏ FR đó khỏi story |
| `merge đụng …` | hai story cùng sửa một file | `write_scope` khai sai — sửa ở story, **không** gỡ conflict cho xong |

`--force` có ở `approve` và `legacy run` cho trường hợp cố ý bỏ qua. Dùng nó là
một quyết định, và nó được ghi lại: bản ghi phê duyệt giữ ghi chú, báo cáo
nghiệm thu hiện đúng trạng thái từng cổng.

### Chạy song song

Epic chạy tuần tự. Trong một epic, hai story chỉ được cùng đợt khi **hết
phụ thuộc** *và* **phạm vi ghi rời nhau** — thiếu điều kiện thứ hai thì hai
story cùng sửa một file và người thua là người merge sau. Mỗi story chạy
trong worktree git riêng; merge tuần tự cuối đợt. Conflict lúc merge không
được tự gỡ: nó là **bằng chứng `write_scope` khai sai**.

### Cấu trúc gói 1.x

```
aisef/
  cli/              bộ lệnh chia theo pha, mọi lệnh gọi-một-lần, không daemon
  config.py         ngưỡng và cấu hình, có kiểu, có kiểm
  clients/          Claude Code · OpenCode; năng lực được **khai**, không giả định
  control/          cổng, phê duyệt, xếp lịch, worktree, chuẩn hoá tài liệu BMAD
  harness/          prompt · tool · sandbox · guard · quan sát · map mockup
  kit/              catalog skill, lọc bảo mật hai tầng, hiến pháp, prompt, skill riêng
  phases/           plan · mockup · implement · run · qa · deploy · report
docs/
  SOLUTION.md              giải pháp tổng thể và vì sao chọn như vậy
  EXECUTION-PLAN.md        kế hoạch thực thi, trạng thái từng hạng mục
  REQUIREMENTS-EVIDENCE.md R1–R14 → test chạy được
  SPIKE-REPORT.md          kết quả 7 spike kiểm chứng khả thi
```

### Bằng chứng, không tự khai

Mọi cổng đọc `_bmad-output/evidence/{story}.jsonl` — lần chạy test, lần
sửa file, lần gọi model kèm chi phí và độ trễ, lần đối chiếu mockup. Câu
"đã hoàn thành" của agent không được tính là gì cả.

Cụ thể, một story chỉ xong khi: test xanh **và** xanh sau lần sửa cuối ·
lint sạch · thay đổi nằm trong phạm vi khai báo · màn hình thật dựng đủ
component mockup đã hứa · rà soát độc lập (phiên khác, cấm sửa code) không
còn mục chặn · không có test nào rỗng khẳng định.
