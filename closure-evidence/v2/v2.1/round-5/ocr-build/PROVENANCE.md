# Nguồn gốc binary Open Code Review v1.12.12: dựng lại từ commit ghim

Ngày 2026-10-15, 18:22 – 18:28 (+07); sửa và đo thêm ngày 2026-10-17 sau hai lượt rà soát độc lập (mục 13). Làn
`ocr-build`, nhánh `v21x/ocr-build`, cây gốc `f69124c`. AISEF 2.1 là **ứng viên**:
chưa phát hành, chưa được chủ sở hữu chấp nhận; tài liệu này không nói gì khác. Quyền hạn: mục 5 (đoạn đầu) của chỉ
thị chủ sở hữu ngày 2026-10-15: tải mã nguồn công khai của open-code-review tại đúng commit đã ghim và các phụ thuộc cần
để dựng, trong thư mục làm việc riêng; không thay bản cài hệ thống, không chạy script cài đặt toàn cục, không dùng thông
tin đăng nhập, không gọi provider trả tiền; ghi đủ commit, toolchain, phụ thuộc và lệnh; nếu không tái tạo byte-identical
thì báo khác biệt và mức bằng chứng, không tự tuyên bố nguồn gốc đã xác minh đầy đủ.

## 1. Kết quả một đoạn

Dựng `./cmd/opencodereview` từ checkout sạch của đúng commit `182898cf522da3d04157b422752d028417974e19` bằng Go 1.26.5
(bản mà binary nhúng), `-trimpath`, và bộ cờ liên kết theo Makefile/workflow của upstream, **cho ra đúng từng byte** binary
đã ghim: sha256 `bf38abf320ead4e106b71c15824463640207118f38e1c10c28a73b6839104af7`, 55 014 610 byte. Ba lần dựng ở ba
chỗ khác nhau (hai thư mục nguồn, một thư mục đầu ra thứ ba do công cụ tự tạo, ba GOCACHE nguội) đều ra cùng sha256; lượt
rà soát 2026-10-17 lặp lại ở một cặp thư mục nguồn mới với GOCACHE nguội mới và được ba lần nữa cùng sha256. Các đối chứng
đổi đúng một thứ cho ra sha256 khác. Mức đạt được: **(c) `IDENTICAL`** trên máy này, với toolchain này.

Điều này **không** có nghĩa là binary là artifact phát hành của upstream (mục 6), **không** nói ai đã dựng binary ghim,
ở đâu (mục 6), và không chứng minh toolchain độc lập (mục 7).

## 2. Ba mức, không gộp (theo yêu cầu của chủ sở hữu)

| Mức | Nội dung | Kết quả | Nguồn |
|---|---|---|---|
| **Binary tự khai phiên bản** (a) | `<exe> version`, hỏi trong môi trường sạch qua `aisef2.app.adapters._declared` | `open-code-review v1.12.12 (182898c) darwin/arm64`, `built at: 2026-10-05T00:00:00Z`; cổng chấp nhận | `ocr-provenance.json` `a_declared` |
| **Binary khớp hash đã ghim** (b) | sha256 của tệp = pin; build info Go nhúng trong tệp (`go version -m`, đọc tệp, không chạy) | sha256 khớp; `go1.26.5`, `-trimpath=true`, `CGO_ENABLED=0`, `GOOS=darwin GOARCH=arm64 GOARM64=v8.0`, `vcs.revision=182898cf…` (= commit ghim), `vcs.time=2026-10-05T06:34:14Z`, `vcs.modified=false`, 84 phụ thuộc | `ocr-provenance.json` `b_embedded`, `dependencies.tsv` |
| **Binary có nguồn gốc build được xác minh** (c) | sha256 của bản dựng lại từ commit ghim so với binary | **`IDENTICAL`** (3/3 lần dựng lượt đầu, 3/3 lượt rà soát), `cmp` byte-for-byte cũng trùng | `ocr-provenance.json` `c_rebuilt`, `build.log` |

Mức (a) và (b) là lời của chính tệp; chỉ mức (c) là phép đo do người kiểm chứng làm trên máy của mình. Mức (c) ở đây có
nghĩa chính xác là: *các byte này tái tạo được từ commit đó, qua toolchain đó, với các cờ đó, và các module mà `go.sum`
của upstream ghim*. Nó không nói lệnh nào đã tạo ra binary ghim (chỉ rằng lệnh này tạo ra đúng các byte ấy), ai đã dựng,
ở đâu, hay rằng toolchain là đáng tin (mục 6, 7).

## 3. Mã nguồn

* Clone: `git clone https://github.com/alibaba/open-code-review` (8,5 s). `HEAD` mặc định của clone là `11ac6d4c…` (nhánh
  chính, không dùng; đọc lại 2026-10-17 từ `origin/HEAD`); checkout `--detach 182898cf522da3d04157b422752d028417974e19`.
* Tag `v1.12.12` là tag chú thích (annotated), `git rev-parse 'v1.12.12^{commit}'` = `182898cf522da3d04157b422752d028417974e19`.
  Đã kiểm, không giả định. Cây làm việc sạch (`git status --porcelain` rỗng). `git fsck --connectivity-only` không báo lỗi
  (chạy lại 2026-10-17: chỉ có dòng `dangling`, không có dòng lỗi).
* Giờ commit `2026-10-05T14:34:14+08:00` = `2026-10-05T06:34:14Z`, đúng bằng `vcs.time` trong binary.
* Chữ ký: tag mang chữ ký SSH, commit mang chữ ký PGP của GitHub (chỉ xác nhận khối chữ ký có mặt). **Chưa xác minh** hai
  chữ ký (máy không có `gpg`, không có khoá công khai/`allowed_signers`, và lượt này không được tải thêm gì).

## 4. Cờ dựng của upstream tại commit ghim, và những gì lệch

Đọc ở `182898c`, không suy từ nhớ:

| Tệp:dòng | Nội dung |
|---|---|
| `Makefile:14` | `GIT_COMMIT := $(shell git rev-parse --short HEAD)` |
| `Makefile:15` | `BUILD_DATE := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")` |
| `Makefile:19-22` | `LD_FLAGS := -X main.Version=$(VERSION) -X main.GitCommit=$(GIT_COMMIT) -X main.BuildDate=$(BUILD_DATE)` |
| `Makefile:24` | `RELEASE_LD_FLAGS := -s -w $(LD_FLAGS)` |
| `Makefile:26-30` | `GOOS=$(1) GOARCH=$(2) CGO_ENABLED=0 $(GO) build -ldflags "$(RELEASE_LD_FLAGS)" -o … ./cmd/opencodereview` |
| `.github/workflows/release.yml:14-16` | `container: image: golang:1.26.6` |
| `.github/workflows/release.yml:44-47` | `VERSION=${GITHUB_REF_NAME}`, `GIT_COMMIT=$(git rev-parse --short HEAD)`, `BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")`, `LD_FLAGS="-s -w -X main.Version=… -X main.GitCommit=… -X main.BuildDate=…"` |
| `.github/workflows/release.yml:52` | `go build -ldflags "${LD_FLAGS}" -o "${BIN_NAME}" ./cmd/opencodereview` |
| `cmd/opencodereview/version.go:12-17`, `root.go:81-92` | ba biến `Version`/`GitCommit`/`BuildDate` đặt bằng `-X`; `version` in chúng |

Không có `-trimpath`, không có `-buildvcs` đặt tay, không có `SOURCE_DATE_EPOCH` ở bất kỳ tệp dựng nào (Makefile,
workflow, `scripts/`, `.goreleaser*` không tồn tại). Bộ cờ đã dùng để dựng lại:

```
CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -trimpath -buildvcs=true \
  -ldflags "-s -w -X main.Version=v1.12.12 -X main.GitCommit=182898c -X main.BuildDate=2026-10-05T00:00:00Z" \
  -o ocr ./cmd/opencodereview
```

Tên biến, thứ tự và `-s -w` lấy từ upstream. **Ba giá trị `-X` lấy từ chính binary** (dữ liệu chuỗi trong tệp), không từ
upstream. `-trimpath` lấy từ build info của binary. Hai điều này là chỗ bản dựng của binary ghim khác với đường dựng phát
hành của upstream:

* **`-trimpath`**: upstream không dùng; binary có. Đối chứng không `-trimpath` (mục 5): build info lúc đó **có** dòng
  `-ldflags=…` (đúng luật của toolchain: có `-trimpath` thì không ghi), và binary nhúng đường dẫn tuyệt đối của cây nguồn
  và của module cache, nên sha256 và kích thước của đối chứng này **phụ thuộc nơi đặt thư mục**, không so được giữa các
  máy (mục 5).
* **`BuildDate`**: upstream điền giờ lúc chạy (`date -u +%Y-%m-%dT%H:%M:%SZ`); binary mang `2026-10-05T00:00:00Z`, một
  ngày không có giờ, do người dựng đặt. Nó không phải thời điểm dựng (tệp mtime 2026-10-06 14:32:45) và cũng không phải
  giờ commit (06:34:14Z).

## 5. Đối chứng (đổi đúng một thứ)

| | Khác biệt | sha256 | Byte |
|---|---|---|---|
| Binary ghim | | `bf38abf3…04af7` | 55 014 610 |
| Dựng A (thư mục `src`, GOCACHE nguội) | | `bf38abf3…04af7` | 55 014 610 |
| Dựng B (thư mục `src-b`, GOCACHE nguội riêng) | thư mục nguồn khác | `bf38abf3…04af7` | 55 014 610 |
| Dựng C (công cụ `inspect_binary.py`, thư mục tạm riêng, HOME riêng) | đường dẫn đầu ra, GOCACHE | `bf38abf3…04af7` | 55 014 610 |
| Dựng A', B', D' (2026-10-17: cặp thư mục mới `replay/src`, `replay/src-b`; GOCACHE nguội mới; D' là công cụ) | thư mục nguồn, GOCACHE | `bf38abf3…04af7` (cả ba) | 55 014 610 |
| Đối chứng 1: `BuildDate` +1 giây, có `-trimpath` | một ký tự của một cờ `-X` | `bc1b5064…895c` | 55 014 610 |
| – cùng đối chứng 1 dựng từ `src-b` (2026-10-17) | thư mục nguồn | `bc1b5064…895c` (**trùng**) | 55 014 610 |
| – cùng đối chứng 1 dựng từ `replay/src` và từ `replay/src-b` (2026-10-17) | thư mục nguồn | `bc1b5064…895c` (**trùng**, cả hai) | 55 014 610 |
| Đối chứng 2: không `-trimpath`, dựng từ `src` | bỏ `-trimpath` | `4b52379a…69ed` | 55 245 778 |
| – cùng đối chứng 2 dựng từ `src-b` (2026-10-17) | thư mục nguồn | `bafc4fda…5534` (**khác**) | 55 245 778 |
| – cùng đối chứng 2 dựng từ `replay/src` (2026-10-17) | thư mục nguồn | `a0ebc754…6055` (**khác**) | 55 262 290 |
| – cùng đối chứng 2 dựng từ `replay/src-b` (2026-10-17) | thư mục nguồn | `08db280a…27d2` (**khác**) | 55 262 290 |

Hai kết luận, tách nhau:

* **Đối chứng 1 là phép đo mang đi được.** Có `-trimpath`, kết quả không phụ thuộc thư mục nguồn (A = B = C = A' = B' = D'
  đều là `bf38abf3…`, và bốn lần dựng đối chứng 1 ở bốn thư mục nguồn cùng ra `bc1b5064…`), nên một người khác có cùng toolchain, cùng commit, cùng module và cùng cờ phải
  thấy đúng các sha256 trong bảng, và phép so nhạy với đúng một ký tự của một cờ `-X`. Vì vậy khớp byte cũng ràng buộc các
  giá trị `-X` và `-s -w`, dù binary không ghi cờ.
* **Đối chứng 2 chỉ nói "khác", không là giá trị tham chiếu.** Không có `-trimpath`, binary nhúng đường dẫn tuyệt đối; đếm
  bằng `grep -a -o`: bản đối chứng 2 từ `src` chứa chuỗi đường dẫn cây nguồn 117 lần và chuỗi đường dẫn module cache 1297
  lần, bản từ `src-b` chứa chuỗi `src-b/` 117 lần; binary ghim và bản dựng A đều 0 lần cả hai. Cùng một nguồn, một
  toolchain, một bộ cờ, đổi chỗ đặt thư mục là ra bốn sha256 khác nhau (bảng trên). Một người rà soát độc lập, dựng đối
  chứng này ở thư mục khác, cũng báo nhận hash khác (`e07053a1…`); con số của người đó không được đo lại ở đây. Chỉ kết luận định tính đứng được: bỏ `-trimpath`
  thì sha256 khác binary ghim và build info có thêm dòng `-ldflags`; mọi con số của đối chứng 2 đều gắn với đường dẫn.

`go version -m` của binary ghim và của bản dựng A khác nhau 0 dòng (ngoài đường dẫn tệp). Trong ba lần dựng lượt đầu, ba
GOCACHE đều nguội (A, B, và của công cụ); lượt rà soát cũng vậy.

## 6. So với artifact phát hành của upstream: không làm. Ai đã dựng binary ghim: không biết

Không tải artifact phát hành, `sha256sum.txt` hay attestation của upstream (ngoài phạm vi quyền: chỉ nguồn và module).
Vậy **không có phép so** nào với artifact upstream. Từ văn bản của workflow (mục 4), không phải từ đo đạc: workflow phát
hành chạy trong `golang:1.26.6` (binary ghim là `go1.26.5`), không có `-trimpath`, và ghi giờ lúc chạy vào `BuildDate`;
nên artifact phát hành của tag này, nếu do workflow đó dựng, **sẽ khác** binary ghim ở ít nhất build info và byte. Điều
duy nhất rút ra được: binary ghim **không được chứng tỏ là artifact phát hành của upstream**. Đây là dự đoán, chưa đo.

**Ai dựng binary ghim, ở đâu, bằng toolchain nào: bằng chứng không trả lời.** Build info không có trường người dựng hay
máy dựng; `codesign` chỉ cho `Identifier=a.out`, `adhoc`, `linker-signed` (mặc định của bộ liên kết arm64). Chỉ có ba dấu
vết, đều yếu và không kết luận:

1. tệp mtime `2026-10-06 14:32:45`, nằm trong thư mục scratchpad của dự án (`ocr-build/`). mtime là lúc tệp đến đĩa này,
   không phải lúc biên dịch; một tệp sao chép trông giống hệt;
2. cạnh nó là `ocr-build/modcache/`: một bộ khung thư mục rỗng (0 tệp), trong đó `charm.land`, `go.yaml.in`, `golang.org`
   mang giờ `2026-10-06 14:22`, mười phút trước tệp. Phù hợp với việc một module cache từng được điền ở đó; không chứng minh
   được;
3. bản ghi vòng 3, `closure-evidence/v2/v2.1/round-3/OCR-IDENTITY-2026-10-13.json` `not_shown[0]`, viết rằng binary là
   "a build the project made itself": lời tuyên bố của dự án, không kèm phép đo.

Ba dấu vết này **phù hợp với** một bản dựng cục bộ của dự án; chúng không chứng minh điều đó. Tài liệu này vì vậy không
nói "binary ghim là bản dựng của dự án", chỉ nói: *byte của nó tái tạo được từ nguồn công khai bằng phép dựng ở mục 4, và
nó không được chứng tỏ là artifact của upstream*.

## 7. Cái còn chưa được xác minh

1. **Toolchain không độc lập.** Bản dựng lại dùng `/opt/homebrew/bin/go` (bottle Homebrew, `go1.26.5 darwin/arm64`, chi
   tiết và sha256 ở mục 9). Phiên bản chuỗi bằng bản mà binary ghim nhúng (`go1.26.5`) — chỉ có thế là chung; **nơi và
   người đã dựng binary ghim không được ghi** (mục 6), nên không thể nói toolchain này là toolchain đã dựng nó. Khớp byte
   cho thấy phép dựng tất định, khớp nguồn, và toolchain này tạo ra đúng các byte đó; nó không chứng minh rằng chính
   toolchain là sạch (toolchain bị nhiễm sẽ cho ra cùng byte hai lần). Chưa so toolchain với bản của go.dev; sha256 ở mục
   9 được đo sau lượt dựng, không có băm trước đó.
2. **Nguồn chỉ được tin qua GitHub (HTTPS)** và qua mối nối tag → commit. Hai chữ ký (mục 3) chưa được kiểm.
3. **Phụ thuộc được tin qua `go.sum` của upstream**, đã kiểm chéo với `sum.golang.org` (mục 8). Cơ sở dữ liệu checksum là
   sổ chỉ-thêm công khai; nó xác nhận "đây là hash mà thế giới công khai đã thấy", không bảo đảm upstream không bị xâm
   phạm trước khi sổ ghi.
4. **Ba giá trị `-X` lấy từ chính binary.** Phép dựng lại chứng minh binary = f(commit, toolchain, cờ này); không chứng
   minh `BuildDate` mô tả đúng điều gì (xem mục 4).
5. **Chỉ `darwin/arm64`, chỉ máy này.** Không có dựng lại cho Linux/Windows; không có binary Linux/Windows để so; hệ điều
   hành, phiên bản Go khác (kể cả `1.26.6` của upstream) chưa thử. Mọi lần dựng đều trên cùng một máy, cùng một bản
   Homebrew: chúng xác nhận tính tất định trên máy này, không xác nhận tính tái tạo giữa các máy hay các toolchain.
6. **Không so với artifact phát hành upstream** (mục 6).
7. **Ai dựng binary ghim, ở đâu: không biết** (mục 6).
8. **Mạng không có bản ghi gói**: tập máy chủ đã chạm (mục 8, 9) suy từ lệnh đã chạy và nội dung cache, không từ một vết mạng.
9. **Chưa chạy OCR với mô hình thật** (không thuộc làn này; không chạy sản phẩm với binary ở đây ngoài lệnh `version`
   mà `inspect_binary.py` hỏi trong môi trường sạch).

## 8. Phụ thuộc và cơ sở dữ liệu checksum

`dependencies.tsv`: 84 module (đúng bằng số `dep` trong build info), mỗi dòng gồm đường dẫn, phiên bản, `h1:` trong binary
ghim, và bốn phép so (`same`/`DIFF`) với: `h1` trong binary dựng lại; dòng module (không `/go.mod`) trong `go.sum` của
upstream; dòng trong `go.sum` do chính `go` sinh lại từ `sum.golang.org`; phiên bản trong `go list -m all`. Kết quả: 84/84
`same` ở cả bốn. `module-graph-go-list-m-all.txt` là đồ thị đầy đủ của `go list -m all` (151 module cộng module chính); 67
module trong đó không được liên kết vào binary này (chỉ nằm ở đồ thị: nền tảng khác, kiểm thử).

Hai điều về `GOSUMDB`:

* Lần tải đầu (84 module) **không hỏi** `sum.golang.org`: `go.sum` của upstream đã có hash cho mọi module, và `go` kiểm
  tệp tải về với `go.sum` (chỉ hỏi sumdb khi thiếu dòng). Thư mục `cache/download/sumdb` lúc đó chưa tồn tại. `go mod verify`
  (ngoại tuyến) in `all modules verified`.
* Vì vậy đã làm thêm một phép kiểm chéo độc lập, trên bản sao cây nguồn (không đụng checkout): bỏ `go.sum`, chạy
  `go list -deps ./cmd/opencodereview` với `GOFLAGS=-mod=mod` và `GOSUMDB` mặc định. `go` tra 84 module trên cơ sở dữ liệu
  `sum.golang.org` (84 tệp `lookup` trong cache), không lỗi, `go.mod` không đổi, và sinh `go.sum` 168 dòng; **0 dòng** trong
  đó không có trong `go.sum` của upstream (upstream còn 42 dòng khác: các module hoặc `/go.mod` chỉ có trong đồ thị đầy đủ).
  **Đường đi mạng của phép tra này không được ghi.** Trước khi truy cập sumdb, `go` hỏi `GOPROXY` tại
  `<proxy>/sumdb/sum.golang.org/supported` và, nếu proxy trả 200, đi qua proxy chứ không nối thẳng (`go1.26.5`,
  `cmd/go/internal/modfetch/sumdb.go:184-216`). Với `GOPROXY` mặc định, máy này vì vậy có thể chỉ chạm `proxy.golang.org`
  chứ không chạm trực tiếp `sum.golang.org`; cache lưu dưới tên cơ sở dữ liệu nên không phân biệt được. Bản trước của tài
  liệu này viết "chỉ tới sum.golang.org"; điều đó không được chứng minh. Cả hai máy chủ đều thuộc phạm vi mục đích "để
  `go.sum` được kiểm" mà chỉ thị nêu (`GOSUMDB` mặc định).

## 9. Môi trường, lệnh, thời lượng

| | |
|---|---|
| Máy | macOS 26.5.2 (25F84), arm64 |
| Go | `go1.26.5 darwin/arm64`, `/opt/homebrew/bin/go` (liên kết tới `../Cellar/go/1.26.5/bin/go`); `GOROOT=/opt/homebrew/Cellar/go/1.26.5/libexec`; `GOTOOLCHAIN=local`, `GOENV=off`. Chi tiết toolchain bên dưới bảng |
| git, Python | git 2.53.0; Python 3.14.7 (`/opt/homebrew/bin/python3 -P`) |
| Biến Go | `GOFLAGS=-mod=readonly`, `GOPROXY` và `GOSUMDB` mặc định lúc tải (`proxy.golang.org,direct`; `sum.golang.org`), `GOPROXY=off GOSUMDB=off` lúc dựng; `GOMODCACHE`, `GOCACHE`, `GOPATH` trong thư mục riêng; `CGO_ENABLED=0 GOOS=darwin GOARCH=arm64` (`GOARM64=v8.0` mặc định) |
| Mạng | `github.com` (clone); `proxy.golang.org` (84 module + `go.mod` của đồ thị; có thể cả truy vấn sumdb, mục 8); `sum.golang.org` (kiểm chéo, trực tiếp hoặc qua proxy, không biết). Suy từ lệnh đã chạy và nội dung cache (không có `cache/vcs` trong module cache, tức không dùng đường `direct` VCS dự phòng), **không từ bản ghi gói mạng** |
| Thời lượng | clone 8,5 s; tải module 9,6 s (+ `go list -m all` 1,6 s); dựng A 30 s, B 28 s (GOCACHE nguội); công cụ 33,6 s (gồm hỏi `version` và một lần dựng); kiểm chéo sumdb 3,5 s; tổng từ lúc sao chép binary đến khi công cụ xong: 5 phút 29 s. Lượt rà soát 2026-10-17 (bước 1, 4, 5, 7, 8 của `build-commands.sh` bằng `/bin/bash` 3.2, ngoại tuyến, GOCACHE nguội): 2 phút 45 s tổng; hai lần dựng nguội ở bước 4 khoảng 66 s |
| Đĩa | lượt đầu: module cache 237 MB; GOCACHE 680 MB – 1,3 GB mỗi cái; nguồn 72 MB; thư mục làm việc 3,3 GB; còn trống 17 GiB lúc xong (ngưỡng 10 GiB). Lượt rà soát: 17 GiB trước, 11 GiB sau lượt replay (4,0 GB), 15 GiB sau khi xoá thư mục replay (thư mục này do lượt rà soát tạo, đã xoá; nhật ký và JSON của nó còn trong `ocr-build-2/logs/`) |

Toolchain, đo ngày 2026-10-17 (sau lượt dựng 2026-10-15; chỉ đọc, không chạy lệnh nào có tác dụng phụ):

* `GOROOT/VERSION` = `go1.26.5`, dòng thứ hai `time 2026-07-01T21:24:27Z`.
* sha256 (đầy đủ):
  * `libexec/bin/go` `3f947495f00cb7f8088a5cfd694da8dc43869b33f5e7377b048fb18922ffb7e0`
  * `libexec/pkg/tool/darwin_arm64/compile` `a4b63e08a3bba5029e9c638652e1678bf254490c7690d3906298f7a9f17f2a1e`
  * `libexec/pkg/tool/darwin_arm64/link` `9bb5a9fb397bf302698a302b965ce39d9467b55529075aa09ac8a9eba16d5e98`
  * `libexec/pkg/tool/darwin_arm64/asm` `6400bab034d6e70effa03c8a4844a0c602701d85f5e5726fbb6689ba2597e3b5`
  * `libexec/pkg/tool/darwin_arm64/cgo` `20e66866eaf4deca72db8f29895df551dd013bbaf01792d8160eea56376a5d3a`
* Homebrew (`Cellar/go/1.26.5/INSTALL_RECEIPT.json`): tap `homebrew/core`, `stable 1.26.5`, `poured_from_bottle: true`,
  `built_as_bottle: true`, `arch: arm64`, Homebrew `6.0.8-30-g6557697`, `installed_on_request: true`, `changed_files: []`.
  Bottle cài `2026-08-01 19:53` (mtime của thư mục `Cellar/go/1.26.5` và của `INSTALL_RECEIPT.json`); `bin/go` và `VERSION`
  mang mtime `2026-07-02 04:24:27 +07`. Cả hai ngày trước lượt dựng (2026-10-15) và trước mtime của binary ghim
  (2026-10-06). Chưa có băm của các tệp này lấy trước lượt dựng; mtime không đổi là dấu hiệu, không phải bằng chứng.
* Chưa so với bản của go.dev; không biết toolchain nào đã dựng binary ghim (mục 6, 7.1).

Lệnh: `build-commands.sh` (đã sửa 2026-10-17, chạy được, `bash -n` sạch; mục 11). Nhật ký rút gọn: `build.log`. Công cụ:
`validation/v21/ocr/inspect_binary.py` ở `f69124c`, chạy với `--source`, `--modcache` và `--ldflags` ở mục 4.

## 10. Vị trí các thứ để lại

Thư mục làm việc (chưa xoá, đĩa còn hơn 10 GiB; macOS dọn `/tmp` sau vài ngày):
`<scratchpad>/m21/ocr-build-2/` gồm `src` (checkout `182898c`), `src-b`, `gomodcache`, `gocache*`, `bin/ocr-pinned`,
`out-a`, `out-b`, `out-c1`, `out-c2`, `out-c1b`, `out-c2b`, `tmp/` (thư mục tạm của công cụ), `sumdb-check`, `logs/`.
Không có binary hay module cache nào trong kho; thư mục này chỉ có văn bản.

**`inspect_binary.py` không xoá thư mục tạm của nó** (`tempfile.mkdtemp(prefix="aisef-ocr-rebuild-")`, dòng 151, không có
chỗ dọn): mỗi lần chạy để lại khoảng 733 MB tại `$TMPDIR`: 680 MB là GOCACHE mặc định dưới HOME của công cụ
(`Library/Caches/go-build`), 52 MiB là binary dựng lại. Lượt đầu để lại `ocr-build-2/tmp/aisef-ocr-rebuild-p2xbga8u` (đo
lại 2026-10-17: 733 MB); lượt replay để lại một thư mục cùng cỡ (đã xoá cùng thư mục replay). Người chạy phải tự xoá; chạy công cụ với
`TMPDIR` trong thư mục làm việc (như `build-commands.sh` bước 7) để việc đó không chạm đường dẫn hệ thống.

## 11. Tệp trong thư mục này

| Tệp | Là gì |
|---|---|
| `PROVENANCE.md` | tài liệu này |
| `ocr-provenance.json` | đầu ra của `inspect_binary.py` ở lượt đầu (2026-10-15). Không ghi đè ở lượt rà soát; lượt chạy lại 2026-10-17 cho cùng nội dung ngoài 4 trường: `binary.path`, tên thư mục tạm trong `c_rebuilt.argv`, `checked_at`, `tool.tree` |
| `build-commands.sh` | các bước viết lại thành một tập lệnh chạy được (`W=… EXE=… bash build-commands.sh [bước…]`). **Không phải tập lệnh đã chạy nguyên khối.** Đã đối chiếu 2026-10-17: `bash -n` sạch; bước 1, 4, 5, 7, 8 chạy lại ngoại tuyến trong thư mục mới và cho kết quả đã nêu ở mục 5; bước 2, 3, 6 (cần mạng) **không** chạy lại |
| `scripts-as-run/env.sh`, `build.sh`, `control.sh` | ba tệp trợ giúp đã chạy thật ở lượt đầu, nguyên văn (chứa đường dẫn tuyệt đối của thư mục làm việc). sha256: `env.sh` `2d4dcc8ba17a08f6040b5d5859ed1d9d0047416926402e7173607f030aa07d9f`, `build.sh` `b209e272888734b553a914146c501b0d8486f61018149cf9520a7262ac58dbd0`, `control.sh` `ef7b0a98e2e82dc1275d8245235991b0385ce39142d512a4c4537fbe10bd5531`. Các lệnh clone, `go list`, `go mod verify`, kiểm chéo sumdb và công cụ được gõ tay; dòng lệnh của chúng lấy từ `clone.log`, `inspect-run.log` và `build.log` của lượt đó |
| `build.log` | nhật ký rút gọn, có phần thêm ngày 2026-10-17 |
| `dependencies.tsv`, `module-graph-go-list-m-all.txt` | mục 8 |

Khác biệt đã biết giữa `build-commands.sh` và lượt gốc: `build.sh` gốc tính `GitCommit` bằng `git rev-parse --short HEAD`
(bản viết lại cũng vậy); dòng gọi công cụ gốc là `env PATH=… python3 -P …` với `TMPDIR` trong thư mục làm việc (bản viết lại
dùng `env -i`, công cụ tự dựng môi trường Go của nó nên kết quả không đổi, đã thấy ở lượt replay); thứ tự bước theo `build.log`
(kiểm chéo sumdb 11:26:53Z trước công cụ 11:27:22Z).

## 12. Chỗ khác còn nói về nguồn gốc binary (không sửa trong làn này)

Làn này không sửa `docs/` hay mã sản phẩm. Với bằng chứng ở trên, các chỗ dưới đây có thể giữ ở mức "(c) `IDENTICAL` trên
máy này, không phải artifact upstream, không biết ai dựng"; chưa chỗ nào trong `docs/` hay `aisef2/` trỏ tới tài liệu này. Việc sửa là của chủ sở hữu.

| Tệp:dòng | Câu hiện có | Ghi chú |
|---|---|---|
| `docs/v2.1/REPORT.md:146-147` | "`v1.12.12 (182898c)` dựng từ nguồn (`-trimpath`), sha256 `bf38abf3…04af7` khớp pin … Chưa so với artifact phát hành upstream" | được (c) đỡ ở mức `IDENTICAL` trên máy này; không nói "ai dựng"; nên trỏ tới `closure-evidence/v2/v2.1/round-5/ocr-build/PROVENANCE.md` |
| `docs/v2.1/REPORT.md:292` | "build từ nguồn với `-trimpath`" | như trên |
| `docs/v2.1/ADR-V2.1.md:118` | "nhị phân OCR thật build từ commit đã ghim" | như trên; "build từ" ở đây = tái tạo được từ, không phải một bản ghi về lúc dựng |
| `docs/v2.1/USAGE-2.1.md:163` | "nhị phân thật (build từ commit đã ghim)" | như trên |
| `aisef2/app/review_ocr.py:27-28` (docstring) | "Exercised against the real binary built from that commit" | như trên; ngoài phạm vi làn (không sửa mã sản phẩm), và bằng chứng đột biến đánh số theo dòng của `aisef2/` (`L41 …`) nên đổi dòng làm lệch bằng chứng |
| `docs/v2.1/UPSTREAM-RESEARCH.md:19` | chỉ ghi pin (commit, tag, giấy phép, cách dùng) | **không có** câu "built from source … with -trimpath" |
| `closure-evidence/v2/v2.1/round-3/OCR-IDENTITY-2026-10-13.json`, khoá `policy` | trích `docs/v2.1/UPSTREAM-RESEARCH.md` cho "built from source (tag v1.12.12 = 182898c) with -trimpath" | **trích dẫn treo**: tệp được trích không có câu đó. `not_shown[0]` ("a build the project made itself") là lời tuyên bố của dự án, không phải phép đo (mục 6). Bản ghi vòng 3 là bằng chứng đã đóng băng: không sửa, chỉ ghi chú |

## 13. Lịch sử sửa

**2026-10-17, sau hai lượt rà soát độc lập** (5 phát hiện của mỗi người, trùng nhau một phần, cộng một điều tự phát hiện khi
sửa). Thay đổi so với bản ngày 2026-10-15 (commit `891cd20`):

* `build-commands.sh` viết lại: hết lỗi cú pháp (`W=<…>`), mỗi bước một subshell (không rò `cd` hay biến Go), bước công cụ
  chạy từ gốc kho bằng `env -i`, môi trường Go dựng lại ở mỗi bước, thứ tự theo `build.log`, tiêu đề nói rõ đây là bản
  viết lại; thêm ba tệp gốc `scripts-as-run/`.
* Bỏ các câu khẳng định ai/ở đâu đã dựng binary ghim ("là bản dựng của dự án", "cùng máy mà binary ghim được dựng", và
  câu tương ứng trong thông điệp commit `891cd20`: "so the pinned binary is this project's own build of upstream source");
  thay bằng mục 6 và 7. Thông điệp commit không sửa (không viết lại lịch sử); commit sửa này nêu lại.
* Đối chứng 2: đo thêm hai chỗ khác, chứng minh sha256 phụ thuộc đường dẫn; đối chứng 1 đo thêm hai chỗ, trùng.
* Toolchain: thêm GOROOT, sha256 của `go`, `compile`, `link`, `asm`, `cgo`, `VERSION`, biên nhận Homebrew.
* Mục 12 liệt kê file:line của các chỗ nói theo cách cũ; mục 10 nói công cụ để lại thư mục tạm; `BUILD-RECIPE.md` mục 4 có
  biến thể cô lập.
* Tự phát hiện: đường đi mạng của phép kiểm chéo sumdb (mục 8) từng được viết là "chỉ tới sum.golang.org"; không có bằng
  chứng, và `go` ưu tiên đi qua proxy. Đã sửa. Cũng bỏ "Không gì khác" khỏi hàng Mạng (không có bản ghi gói).
* Đã chạy lại, không đổi kết quả: ba lần dựng nguội, công cụ, `git fsck`, `origin/HEAD`.
