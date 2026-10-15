# Nguồn gốc binary Open Code Review v1.12.12: dựng lại từ commit ghim

Ngày 2026-10-15, 18:22 – 18:28 (+07). Làn `ocr-build`, nhánh `v21x/ocr-build`, cây gốc `f69124c`. AISEF 2.1 là **ứng viên**:
chưa phát hành, chưa được chủ sở hữu chấp nhận; tài liệu này không nói gì khác. Quyền hạn: mục 5 (đoạn đầu) của chỉ
thị chủ sở hữu ngày 2026-10-15: tải mã nguồn công khai của open-code-review tại đúng commit đã ghim và các phụ thuộc cần
để dựng, trong thư mục làm việc riêng; không thay bản cài hệ thống, không chạy script cài đặt toàn cục, không dùng thông
tin đăng nhập, không gọi provider trả tiền; ghi đủ commit, toolchain, phụ thuộc và lệnh; nếu không tái tạo byte-identical
thì báo khác biệt và mức bằng chứng, không tự tuyên bố nguồn gốc đã xác minh đầy đủ.

## 1. Kết quả một đoạn

Dựng `./cmd/opencodereview` từ checkout sạch của đúng commit `182898cf522da3d04157b422752d028417974e19` bằng Go 1.26.5
(bản mà binary nhúng), `-trimpath`, và bộ cờ liên kết theo Makefile/workflow của upstream, **cho ra đúng từng byte** binary
đã ghim: sha256 `bf38abf320ead4e106b71c15824463640207118f38e1c10c28a73b6839104af7`, 55 014 610 byte. Ba lần dựng ở ba
chỗ khác nhau (hai thư mục nguồn, một thư mục đầu ra thứ ba do công cụ tự tạo, ba GOCACHE nguội) đều ra cùng sha256. Hai
đối chứng đổi đúng một thứ cho ra sha256 khác. Mức đạt được: **(c) `IDENTICAL`** trên máy này, với toolchain này.

Điều này **không** có nghĩa là binary là artifact phát hành của upstream (mục 6), và không chứng minh toolchain độc lập
(mục 7).

## 2. Ba mức, không gộp (theo yêu cầu của chủ sở hữu)

| Mức | Nội dung | Kết quả | Nguồn |
|---|---|---|---|
| **Binary tự khai phiên bản** (a) | `<exe> version`, hỏi trong môi trường sạch qua `aisef2.app.adapters._declared` | `open-code-review v1.12.12 (182898c) darwin/arm64`, `built at: 2026-10-05T00:00:00Z`; cổng chấp nhận | `ocr-provenance.json` `a_declared` |
| **Binary khớp hash đã ghim** (b) | sha256 của tệp = pin; build info Go nhúng trong tệp (`go version -m`, đọc tệp, không chạy) | sha256 khớp; `go1.26.5`, `-trimpath=true`, `CGO_ENABLED=0`, `GOOS=darwin GOARCH=arm64 GOARM64=v8.0`, `vcs.revision=182898cf…` (= commit ghim), `vcs.time=2026-10-05T06:34:14Z`, `vcs.modified=false`, 84 phụ thuộc | `ocr-provenance.json` `b_embedded`, `dependencies.tsv` |
| **Binary có nguồn gốc build được xác minh** (c) | sha256 của bản dựng lại từ commit ghim so với binary | **`IDENTICAL`** (3/3 lần dựng), `cmp` byte-for-byte cũng trùng | `ocr-provenance.json` `c_rebuilt`, `build.log` |

Mức (a) và (b) là lời của chính tệp; chỉ mức (c) là phép đo do người kiểm chứng làm trên máy của mình. Mức (c) ở đây có
nghĩa chính xác là: *các byte này là kết quả của commit đó, qua toolchain đó, với các cờ đó, và các module mà `go.sum` của
upstream ghim*. Nó chưa nói ai đã dựng, ở đâu, hay rằng toolchain là đáng tin (mục 7).

## 3. Mã nguồn

* Clone: `git clone https://github.com/alibaba/open-code-review` (8,5 s). `HEAD` mặc định của clone là `11ac6d4c…` (nhánh
  chính, không dùng); checkout `--detach 182898cf522da3d04157b422752d028417974e19`.
* Tag `v1.12.12` là tag chú thích (annotated), `git rev-parse 'v1.12.12^{commit}'` = `182898cf522da3d04157b422752d028417974e19`.
  Đã kiểm, không giả định. Cây làm việc sạch (`git status --porcelain` rỗng). `git fsck --connectivity-only` không báo lỗi.
* Giờ commit `2026-10-05T14:34:14+08:00` = `2026-10-05T06:34:14Z`, đúng bằng `vcs.time` trong binary.
* Chữ ký: tag mang chữ ký SSH, commit mang chữ ký PGP của GitHub. **Chưa xác minh** hai chữ ký (máy không có `gpg`, không
  có khoá công khai/`allowed_signers`, và lượt này không được tải thêm gì).

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
upstream. `-trimpath` lấy từ build info của binary. Hai điều này là chỗ người dựng gốc khác với đường dựng phát hành của
upstream:

* **`-trimpath`**: upstream không dùng; binary có. Đối chứng không `-trimpath`: sha256 `4b52379a…69ed`, 55 245 778 byte
  (+231 168 byte), và build info lúc đó **có** dòng `-ldflags=…` (đúng luật của toolchain: có `-trimpath` thì không ghi).
* **`BuildDate`**: upstream điền giờ lúc chạy (`date -u +%Y-%m-%dT%H:%M:%SZ`); binary mang `2026-10-05T00:00:00Z`, một
  ngày không có giờ, do người dựng đặt. Nó không phải thời điểm dựng (tệp mtime 2026-10-06 14:32) và cũng không phải giờ
  commit (06:34:14Z).

## 5. Đối chứng (đổi đúng một thứ)

| | Khác biệt | sha256 | Byte |
|---|---|---|---|
| Binary ghim | | `bf38abf3…04af7` | 55 014 610 |
| Dựng A (thư mục `src`, GOCACHE nguội) | | `bf38abf3…04af7` | 55 014 610 |
| Dựng B (thư mục `src-b`, GOCACHE nguội riêng) | thư mục nguồn khác | `bf38abf3…04af7` | 55 014 610 |
| Dựng C (công cụ `inspect_binary.py`, thư mục tạm riêng, HOME riêng) | đường dẫn đầu ra, GOCACHE | `bf38abf3…04af7` | 55 014 610 |
| Đối chứng 1 | `BuildDate` +1 giây | `bc1b5064…895c` | 55 014 610 |
| Đối chứng 2 | không `-trimpath` | `4b52379a…69ed` | 55 245 778 |

`go version -m` của binary ghim và của bản dựng A khác nhau 0 dòng (ngoài đường dẫn tệp). Đối chứng 1 cho thấy phép so
nhạy với đúng một ký tự của một cờ `-X`; vì vậy khớp byte cũng ràng buộc các giá trị `-X` và `-s -w`, dù binary không ghi
cờ. Trong ba lần dựng, ba GOCACHE đều nguội (A, B, và của công cụ).

## 6. So với artifact phát hành của upstream: không làm, và vì sao dự kiến sẽ khác

Không tải artifact phát hành, `sha256sum.txt` hay attestation của upstream (ngoài phạm vi quyền: chỉ nguồn và module).
Vậy **không có phép so** nào với artifact upstream. Từ văn bản của workflow (mục 4), không phải từ đo đạc: workflow phát
hành chạy trong `golang:1.26.6` (binary ghim là `go1.26.5`), không có `-trimpath`, và ghi giờ lúc chạy vào `BuildDate`;
nên artifact phát hành của tag này, nếu do workflow đó dựng, **sẽ khác** binary ghim ở ít nhất build info và byte. Binary
ghim, vì thế, là bản dựng của dự án này từ nguồn của upstream, không phải bản của upstream; nhãn ấy khớp với
`closure-evidence/v2/v2.1/round-3/OCR-IDENTITY-2026-10-13.json` (`not_shown[0]`).

## 7. Cái còn chưa được xác minh

1. **Toolchain không độc lập.** Bản dựng lại dùng `/opt/homebrew/bin/go` (Homebrew, `go1.26.5 darwin/arm64`), cùng máy mà
   binary ghim được dựng (mtime 2026-10-06 14:32). Khớp byte cho thấy phép dựng tất định và khớp nguồn; nó không chứng
   minh rằng chính toolchain là sạch (toolchain bị nhiễm sẽ cho ra cùng byte hai lần). Chưa so toolchain với bản của go.dev.
2. **Nguồn chỉ được tin qua GitHub (HTTPS)** và qua mối nối tag → commit. Hai chữ ký (mục 3) chưa được kiểm.
3. **Phụ thuộc được tin qua `go.sum` của upstream**, đã kiểm chéo với `sum.golang.org` (mục 8). Cơ sở dữ liệu checksum là
   sổ chỉ-thêm công khai; nó xác nhận "đây là hash mà thế giới công khai đã thấy", không bảo đảm upstream không bị xâm
   phạm trước khi sổ ghi.
4. **Ba giá trị `-X` lấy từ chính binary.** Phép dựng lại chứng minh binary = f(commit, toolchain, cờ này); không chứng
   minh `BuildDate` mô tả đúng điều gì (xem mục 4).
5. **Chỉ `darwin/arm64`, chỉ máy này.** Không có dựng lại cho Linux/Windows; không có binary Linux/Windows để so; hệ điều
   hành, phiên bản Go khác (kể cả `1.26.6` của upstream) chưa thử.
6. **Không so với artifact phát hành upstream** (mục 6).
7. **Chưa chạy OCR với mô hình thật** (không thuộc làn này; không chạy sản phẩm với binary ở đây ngoài lệnh `version`).

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
  `go list -deps ./cmd/opencodereview` với `GOFLAGS=-mod=mod` và `GOSUMDB` mặc định. `go` tra 84 module trên
  `sum.golang.org` (84 tệp `lookup` trong cache), không lỗi, `go.mod` không đổi, và sinh `go.sum` 168 dòng; **0 dòng** trong
  đó không có trong `go.sum` của upstream (upstream còn 42 dòng khác: các module hoặc `/go.mod` chỉ có trong đồ thị đầy đủ).
  Đây là truy cập mạng thứ ba, chỉ tới `sum.golang.org`, cùng mục đích "để `go.sum` được kiểm" mà đề bài nêu.

## 9. Môi trường, lệnh, thời lượng

| | |
|---|---|
| Máy | macOS 26.5.2 (25F84), arm64 |
| Go | `go1.26.5 darwin/arm64`, `/opt/homebrew/bin/go` (Homebrew); `GOTOOLCHAIN=local`, `GOENV=off` |
| git, Python | git 2.53.0; Python 3.14.7 (`/opt/homebrew/bin/python3 -P`) |
| Biến Go | `GOFLAGS=-mod=readonly`, `GOPROXY` và `GOSUMDB` mặc định lúc tải (`proxy.golang.org,direct`; `sum.golang.org`), `GOPROXY=off GOSUMDB=off` lúc dựng; `GOMODCACHE`, `GOCACHE`, `GOPATH` trong thư mục riêng; `CGO_ENABLED=0 GOOS=darwin GOARCH=arm64` (`GOARM64=v8.0` mặc định) |
| Mạng | `github.com` (clone), `proxy.golang.org` (84 module + `go.mod` của đồ thị), `sum.golang.org` (kiểm chéo). Không gì khác |
| Thời lượng | clone 8,5 s; tải module 9,6 s (+ `go list -m all` 1,6 s); dựng A 30 s, B 28 s (GOCACHE nguội); công cụ 33,6 s (gồm hỏi `version` và một lần dựng); kiểm chéo sumdb 3,5 s; tổng từ lúc sao chép binary đến khi công cụ xong: 5 phút 29 s |
| Đĩa | module cache 237 MB; GOCACHE 680 MB – 1,3 GB mỗi cái; nguồn 72 MB; thư mục làm việc 3,3 GB; còn trống 17 GiB lúc xong (ngưỡng 10 GiB) |

Lệnh đầy đủ: `build-commands.sh`. Nhật ký rút gọn: `build.log`. Công cụ: `validation/v21/ocr/inspect_binary.py` ở `f69124c`,
chạy với `--source`, `--modcache` và `--ldflags` ở mục 4.

## 10. Vị trí các thứ để lại

Thư mục làm việc (chưa xoá, đĩa còn hơn 10 GiB; macOS dọn `/tmp` sau vài ngày):
`<scratchpad>/m21/ocr-build-2/` gồm `src` (checkout `182898c`), `src-b`, `gomodcache`, `gocache*`, `bin/ocr-pinned`,
`out-a`, `out-b`, `out-c1`, `out-c2`, `tmp/` (thư mục tạm của công cụ), `sumdb-check`, `logs/`. Không có binary hay module
cache nào trong kho; thư mục này chỉ có văn bản.
