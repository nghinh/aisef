# Công thức dựng và kiểm chứng binary Open Code Review

Công cụ kiểm chứng, **không phải mã sản phẩm**: `aisef2/` không import gì ở đây và không quyết định nào của một lượt
chạy đọc kết quả của nó. Việc của tài liệu này là tách bạch ba thứ mà trước đây bị gộp thành một câu ("dựng từ nguồn,
khớp pin"), và nói rõ phần nào còn thiếu.

## 1. Ba lớp, không bao giờ gộp

| Lớp | Là gì | Ai viết ra | Cho biết | Không cho biết |
|---|---|---|---|---|
| **(a) Tự khai** | dòng `open-code-review v1.12.12 (182898c) darwin/arm64` do `<exe> version` in | người dựng, bằng `-ldflags -X` lúc liên kết | binary tự nhận là gì | nó được dựng từ đâu. Với `-trimpath`, Go **không ghi** `-ldflags` vào build info, nên cả cờ đặt ra chuỗi đó cũng không còn dấu vết |
| **(b) Metadata nhúng** | build info mà toolchain Go ghi vào tệp: `go version -m` (đọc tệp, không chạy nó) | lệnh `go build`, từ checkout của người dựng | Go 1.26.5, `GOOS/GOARCH`, `-trimpath=true`, `vcs.revision`, `vcs.time`, `vcs.modified`, 84 module phụ thuộc kèm `h1:` | rằng checkout ấy là nguồn upstream nguyên vẹn; tệp tự mang metadata của chính nó |
| **(c) Dựng lại được** | sha256 của bản dựng từ đúng commit ghim, offline, so với sha256 của binary | người kiểm chứng, trên máy của mình | **bằng chứng duy nhất** rằng các byte *tái tạo được* từ nguồn + toolchain + cờ nào (cùng byte ⇒ lệnh này tạo ra đúng các byte đó) | lệnh nào đã tạo ra binary ghim, ai và ở đâu đã dựng nó; toolchain có độc lập không (một toolchain bị nhiễm cho cùng byte hai lần); chữ ký của tag và commit; so với artifact phát hành của upstream; `BuildDate` mô tả điều gì (ba giá trị `-X` lấy từ chính binary); nền tảng khác `darwin/arm64` và máy khác máy này |

sha256 của tệp là sự thật về **byte**, bất kể nguồn gốc; đó là thứ pin của operator đặt tên và thứ giai đoạn review kiểm
trước khi chạy (`review_ocr.pinned`). Không lớp nào trong (a)/(b) biến sha256 thành bằng chứng về nguồn gốc.

Cổng của sản phẩm (V2.1, làn ocr-gate) kiểm theo thứ tự, **trước mọi lệnh review**, cả advisory lẫn fix-loop:
`pinned` (đường dẫn tuyệt đối, đọc được, sha256 = pin) → `declared` (`<exe> version` trong môi trường sạch, so version
và commit với `review_ocr.OCR`) → mới đến preview và review; sau lượt chạy, `coverage` còn so
`manifest.execution.ocr_version`. Bản ghi phiên (`s["identity"]`) ghi điều binary tự khai và ghi rõ đó là lời tự khai,
không phải bằng chứng dựng.

## 2. Cái được ghim

| | |
|---|---|
| Kho | `https://github.com/alibaba/open-code-review` |
| Tag / commit | `v1.12.12` / `182898cf522da3d04157b422752d028417974e19` |
| Binary duy nhất đã dùng | `darwin/arm64`, 55 014 610 byte, sha256 `bf38abf320ead4e106b71c15824463640207118f38e1c10c28a73b6839104af7`, mtime 2026-10-06 14:32 |
| Vị trí | thư mục scratchpad của phiên (`ocr-build/ocr-v1.12.12-darwin-arm64`); macOS dọn `/tmp` sau vài ngày, định danh là pin chứ không phải đường dẫn |
| Nền tảng khác | chưa có binary, chưa có pin cho Linux/Windows; `version` chưa được hỏi ở đó. Cổng hỏi trong môi trường sạch (`PATH=/usr/bin:/bin`, HOME rỗng, không `APPDATA`/`LOCALAPPDATA`) và stdout với stderr chung một luồng: một dòng cảnh báo in trước dòng version làm cổng từ chối (đóng khi lỗi, đúng quy tắc "dòng đầu phải là dòng version") — cần một lượt có binary thật trên nền tảng đó trước khi ghim |

## 3. Đã đo gì (2026-10-15; (a) và (b) bằng `inspect_binary.py` trên bản ghim, (c) ở lượt dựng lại buổi chiều)

**(a) Tự khai** — chấp nhận bởi cổng: `v1.12.12`, `182898c` (dạng ngắn, là tiền tố của commit ghim), `darwin/arm64`.
Ba chuỗi `v1.12.12`, `182898c`, `2026-10-05T00:00:00Z` có trong tệp như dữ liệu (không tính ra lúc chạy): mỗi chuỗi có
đúng 1 lần xuất hiện NGOÀI chuỗi build info mà toolchain nhúng (hai dấu hiệu bao quanh của `runtime/debug`; build info
tự nó đã chứa `v1.12.12` ở dòng `mod` và 7 ký tự đầu của `vcs.revision`, nên chỉ lần ngoài đó mới tính; tệp chứa build
info hai lần, nên trong tệp là 3/3/1 lần). Chuỗi
`built at` là 00:00:00Z đúng, trong khi `vcs.time` là 06:34:14Z cùng ngày: ngày do người dựng điền, không phải giờ commit.

**(b) Nhúng** — `go1.26.5`, `path github.com/alibaba/open-code-review/cmd/opencodereview`, `mod … v1.12.12` (không
có sum), `-trimpath=true`, `CGO_ENABLED=0`, `GOOS=darwin GOARCH=arm64 GOARM64=v8.0`, `vcs=git`,
`vcs.revision=182898cf522da3d04157b422752d028417974e19` (**bằng commit ghim**), `vcs.time=2026-10-05T06:34:14Z`,
`vcs.modified=false`, 84 phụ thuộc. Không có dòng `-ldflags` (đúng như luật của toolchain khi có `-trimpath`: kiểm
trên mã `cmd/go/internal/load/pkg.go` của Go 1.26.5 và trên một module thử cùng toolchain — có `-trimpath` thì không ghi,
bỏ `-trimpath` thì ghi). Bảng ký hiệu Go bị cắt (`go tool nm` chỉ thấy 132 ký hiệu undefined): suy luận là đã dùng
`-ldflags "-s -w"`, nhưng chính cờ đó cũng không ghi lại. Chữ ký: `codesign` adhoc, `linker-signed`, `Identifier=a.out`.

**(c) Dựng lại — `IDENTICAL`** (lượt dựng lại buổi chiều 2026-10-15; hồ sơ đầy đủ:
`closure-evidence/v2/v2.1/round-5/ocr-build/PROVENANCE.md`, `ocr-provenance.json`, `build.log`, `dependencies.tsv`).

* Nguồn: `git clone https://github.com/alibaba/open-code-review`, checkout `--detach 182898cf522da3d04157b422752d028417974e19`;
  tag chú thích `v1.12.12` được kiểm là trỏ đúng commit đó (`v1.12.12^{commit}`), cây sạch. Hai chữ ký (SSH trên tag, PGP của
  GitHub trên commit) **chưa** kiểm: máy không có `gpg` hay khoá công khai.
* Toolchain: `go1.26.5 darwin/arm64` (Homebrew), đúng bản nhúng trong binary; `GOTOOLCHAIN=local`.
* Phụ thuộc: 84 module tải qua `proxy.golang.org`, kiểm với `go.sum` của upstream; kiểm chéo thêm với `sum.golang.org`
  (go.sum bỏ đi và sinh lại: 168 dòng, 0 dòng khác `go.sum` của upstream). `go mod verify`: `all modules verified`.
* Lệnh: `CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -trimpath -buildvcs=true -ldflags "-s -w -X main.Version=v1.12.12
  -X main.GitCommit=182898c -X main.BuildDate=2026-10-05T00:00:00Z" ./cmd/opencodereview`, ngoại tuyến, GOCACHE nguội.
* Kết quả: sha256 `bf38abf320ead4e106b71c15824463640207118f38e1c10c28a73b6839104af7`, 55 014 610 byte, **trùng binary ghim**,
  `cmp` trùng từng byte, `go version -m` khác nhau 0 dòng. Ba lần dựng (hai thư mục nguồn, một thư mục đầu ra do công cụ tạo,
  ba GOCACHE nguội) cùng sha256; lượt rà soát 2026-10-17 dựng thêm ba lần ở cặp thư mục mới, GOCACHE nguội mới: cùng sha256. Đối chứng: đổi `BuildDate` đúng 1 giây ⇒ `bc1b5064…895c` (cùng giá trị ở bốn thư mục nguồn: mang đi được); bỏ
  `-trimpath` ⇒ sha256 khác, nhưng **con số phụ thuộc đường dẫn** (binary nhúng đường dẫn cây nguồn và module cache): `4b52379a…69ed`
  từ `src`, `bafc4fda…5534` từ `src-b`, cùng cờ cùng nguồn; không dùng nó làm giá trị tham chiếu.
* Cờ của upstream (đọc tại commit ghim): `Makefile:19-24`, `Makefile:26-30`, `.github/workflows/release.yml:44-52` đặt
  `-s -w -X main.Version -X main.GitCommit -X main.BuildDate`, **không** `-trimpath`, và workflow phát hành chạy trong
  `golang:1.26.6` (`release.yml:14-16`). Binary ghim có `-trimpath` và `go1.26.5`; `BuildDate` của nó là một ngày không có giờ.
  Từ văn bản ấy (không phải từ đo): artifact phát hành của tag này, nếu do workflow đó dựng, sẽ khác binary ghim. Binary
  ghim vì vậy **không được chứng tỏ là artifact phát hành của upstream**. Ai đã dựng nó, ở đâu: **bằng chứng không trả
  lời** (build info không có trường người dựng; chỉ có mtime tệp 2026-10-06 14:32:45 và một bộ khung `modcache/` rỗng cạnh
  nó, phù hợp với một bản dựng cục bộ nhưng không chứng minh; xem PROVENANCE.md mục 6).

Mức đạt được: *các byte này tái tạo được từ commit ghim, qua `go1.26.5`, với các cờ trên, và các module mà `go.sum` ghim*
(tất cả trên một máy, một bản toolchain).
Chưa được xác minh: ai và ở đâu đã dựng binary ghim (chỉ có phiên bản chuỗi `go1.26.5` là chung); toolchain độc lập (bản dựng
lại dùng bản Homebrew `go1.26.5`, sha256 các công cụ ở PROVENANCE.md mục 9; một toolchain bị nhiễm cho cùng byte hai lần);
chữ ký của tag/commit; so với artifact phát hành của upstream (không tải; từ văn bản workflow dự kiến sẽ khác, chưa
đo); ba giá trị `-X` lấy từ chính binary nên phép dựng lại không nói `BuildDate` mô tả điều gì; Linux/Windows.

Lượt thử trước cùng ngày (buổi sáng) dừng ở `NOT_PERFORMED` vì máy khi ấy không có cây nguồn (clone upstream chỉ còn
`.git/objects` rỗng), module cache có 438 thư mục và 0 tệp, và làn không được dùng mạng; đó là lịch sử, không phải trạng thái
hiện tại.

Hệ quả cho nhãn "dựng từ nguồn (`-trimpath`)": nay được (c) đỡ ở mức `IDENTICAL` trên máy này; vẫn không được hiểu là
artifact upstream, không nói ai dựng, và vẫn chưa có phép so với artifact upstream. Các chỗ đang dùng nhãn (không sửa ở
làn này, việc của chủ sở hữu): `docs/v2.1/REPORT.md:146-147` và `:292`, `docs/v2.1/ADR-V2.1.md:118`,
`docs/v2.1/USAGE-2.1.md:163`, docstring `aisef2/app/review_ocr.py:27-28`; và khoá `policy` của
`closure-evidence/v2/v2.1/round-3/OCR-IDENTITY-2026-10-13.json` trích `docs/v2.1/UPSTREAM-RESEARCH.md` cho một câu mà tệp
đó **không có** (nó chỉ có dòng 19, ghim). Bảng đầy đủ: PROVENANCE.md mục 12.

## 4. Công thức (chạy ở máy có nguồn và mạng MỘT lần, hoặc module cache đủ)

Môi trường cô lập: mọi thứ nằm trong một thư mục làm việc riêng, không đụng `~/go`, `~/Library/Caches/go-build`, cấu hình
`go` của người dùng hay `/tmp` hệ thống. (Bản trước của công thức dùng `MC=$(go env GOMODCACHE)`: làm theo nguyên văn thì
84 module đổ vào `~/go/pkg/mod`.)

```sh
W=...                 # thư mục làm việc RIÊNG, rỗng; EXE=...  binary cần kiểm
SRC=$W/src
export GOENV=off GOTOOLCHAIN=local GOFLAGS=-mod=readonly GOTELEMETRY=off \
       GOMODCACHE=$W/gomodcache GOCACHE=$W/gocache GOPATH=$W/gopath TMPDIR=$W/tmp
mkdir -p "$TMPDIR"
git clone https://github.com/alibaba/open-code-review "$SRC"
git -C "$SRC" checkout --detach v1.12.12
test "$(git -C "$SRC" rev-parse HEAD)" = 182898cf522da3d04157b422752d028417974e19   # tag đúng commit ghim?
test -z "$(git -C "$SRC" status --porcelain)"                                     # sạch
go version                                                                         # go1.26.5 (bản nhúng)
(cd "$SRC" && go list -deps ./cmd/opencodereview >/dev/null)
                                                                                   # cần mạng MỘT lần: tải 84 module vào $GOMODCACHE
python3 -P validation/v21/ocr/inspect_binary.py "$EXE" --source "$SRC" --modcache "$GOMODCACHE" \
        --ldflags "-s -w -X main.Version=v1.12.12 -X main.GitCommit=182898c -X main.BuildDate=2026-10-05T00:00:00Z" \
        --out ocr-provenance.json
rm -rf "$TMPDIR"/aisef-ocr-rebuild-*          # công cụ KHÔNG xoá thư mục tạm của nó: ≈733 MB mỗi lần (GOCACHE nguội + binary)
```

Phiên bản chạy được từng bước, kèm kết quả đo: `closure-evidence/v2/v2.1/round-5/ocr-build/build-commands.sh` (và
PROVENANCE.md mục 11 nói phần nào đã chạy lại, phần nào chưa).

`inspect_binary.py` dựng `./cmd/opencodereview` offline (`GOPROXY=off`, `GOTOOLCHAIN=local`, `-mod=readonly`) với đúng
`CGO_ENABLED/GOOS/GOARCH/-trimpath` mà build info của binary khai, rồi so sha256. Kết quả của `c_rebuilt.status`:

| Giá trị | Nghĩa |
|---|---|
| `IDENTICAL` | cùng byte ⇒ lớp (c) đạt: các byte tái tạo được từ commit ghim bằng các cờ đã đưa, trên máy và toolchain này. Không nói ai hay ở đâu đã dựng binary, và không thay cho phép so với artifact của upstream |
| `DIFFERENT` | không kết luận giả mạo: thường là `--ldflags` khác (giá trị `-X` của version/commit/ngày, `-s -w`), toolchain khác, hay `GOARM64`. Đọc `argv` đã dùng, thử lại với cờ khác |
| `NOT_PERFORMED` | thiếu nguồn, sai commit, checkout bẩn, hoặc module cache rỗng — kèm lý do |
| `BUILD_FAILED` | `go build` lỗi — kèm đuôi stderr |

**Cờ của bản dựng gốc (trước đây ghi là chưa biết): nay đã đo.** `-ldflags` không có trong binary (`-trimpath`) và không có
trong kho này; tên biến và `-s -w` nằm ở tệp phát hành của upstream tại commit ghim (`Makefile:19-24`, `release.yml:47`):
`-s -w -X main.Version=… -X main.GitCommit=… -X main.BuildDate=…`. Ba giá trị là dữ liệu mà binary giữ: `v1.12.12`,
`182898c`, `2026-10-05T00:00:00Z`; `-trimpath` lấy từ build info của binary (upstream không dùng). Bộ cờ ghi ở lệnh trên cho
`IDENTICAL` (mục 3(c)); đổi một ký tự của `BuildDate` hay bỏ `-trimpath` cho `DIFFERENT`. Không còn là chỗ chưa biết; cái
còn chưa biết là *người dựng gốc đã gõ lệnh gì, ai và ở đâu* (không cần thiết để tái tạo byte).

Cơ chế của công cụ đã được tự kiểm trên một module thử (cùng toolchain, ngoài kho): cùng cờ ⇒ `IDENTICAL`, đổi một giá
trị `-X` ⇒ `DIFFERENT`, module cache rỗng ⇒ `NOT_PERFORMED`. Đó là tự kiểm của công cụ, không phải bằng chứng về OCR; bằng
chứng về OCR là lượt chạy ở mục 3(c) (kết quả `IDENTICAL`, kèm đối chứng đổi một thứ cho `DIFFERENT`).

## 5. Chạy công cụ trên binary đang có

```sh
python3 -P validation/v21/ocr/inspect_binary.py /abs/path/ocr --out ocr-provenance.json
```

Không cần `--source`: ghi (a), (b) và `c_rebuilt.status = NOT_PERFORMED`. Lệnh `version` được hỏi bằng chính
`aisef2.app.adapters._declared` (môi trường sạch, HOME rỗng) nên kết quả (a) là cái mà cổng của sản phẩm sẽ thấy.
Yêu cầu: `go` trên PATH (đọc build info). Không dùng mạng, không đụng kho, không gọi mô hình.
