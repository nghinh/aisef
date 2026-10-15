#!/bin/bash
# Lệnh đã chạy thật trong lượt dựng lại OCR v1.12.12 (2026-10-15, 18:22 - 18:28 giờ +07). Đây là bản ghi, viết lại
# từ các tệp env.sh / build.sh / control.sh và lịch sử lệnh của lượt; chạy lại được trên máy có mạng và go1.26.5.
# Không có binary, không có module cache trong thư mục này.
W=<thư mục làm việc riêng, rỗng>              # đã dùng: <scratchpad>/m21/ocr-build-2
PIN=182898cf522da3d04157b422752d028417974e19
EXE=<binary đã ghim>                          # sha256 bf38abf320ead4e106b71c15824463640207118f38e1c10c28a73b6839104af7

# --- 0. môi trường: không đụng gì của hệ thống; GOSUMDB và GOPROXY để mặc định ---
export PATH=/opt/homebrew/bin:/usr/bin:/bin     # go go1.26.5 darwin/arm64 (Homebrew), git 2.53.0
export GOENV=off                                # không đọc tệp cấu hình go của người dùng
export GOMODCACHE=$W/gomodcache GOCACHE=$W/gocache GOPATH=$W/gopath
export GOFLAGS=-mod=readonly GOTOOLCHAIN=local GOTELEMETRY=off GIT_TERMINAL_PROMPT=0
unset GOPROXY GOSUMDB GONOSUMDB GONOSUMCHECK GOPRIVATE GONOPROXY GOINSECURE GOWORK
#   => GOPROXY=https://proxy.golang.org,direct   GOSUMDB=sum.golang.org   (mặc định của go1.26.5)

# --- 1. binary đang kiểm: sao chép trước, băm lại ---
cp "$EXE" "$W/bin/ocr-pinned"; shasum -a 256 "$W/bin/ocr-pinned"            # bf38abf3...04af7, 55014610 byte

# --- 2. nguồn (mạng: chỉ git clone này) ---
git clone https://github.com/alibaba/open-code-review "$W/src"
git -C "$W/src" rev-parse 'v1.12.12^{commit}'                               # phải in $PIN
git -C "$W/src" checkout --detach "$PIN"
test "$(git -C "$W/src" rev-parse HEAD)" = "$PIN" && test -z "$(git -C "$W/src" status --porcelain)"
git clone --no-checkout "$W/src" "$W/src-b" && git -C "$W/src-b" checkout --detach "$PIN"   # bản thứ hai, thư mục khác

# --- 3. module (mạng: chỉ proxy.golang.org; go.sum của kho đầy đủ nên GOSUMDB không bị hỏi) ---
cd "$W/src"
go list -deps -f '{{with .Module}}{{.Path}}@{{.Version}}{{end}}' ./cmd/opencodereview   # tải 84 module
go list -m all                                                                           # đồ thị: 151 module + module chính
go mod verify                                                                            # all modules verified

# --- 4. dựng, OFFLINE (GOPROXY=off GOSUMDB=off), GOCACHE nguội riêng mỗi bản, cờ theo upstream + -trimpath ---
LD="-s -w -X main.Version=v1.12.12 -X main.GitCommit=182898c -X main.BuildDate=2026-10-05T00:00:00Z"
export GOPROXY=off GOSUMDB=off CGO_ENABLED=0 GOOS=darwin GOARCH=arm64
( cd "$W/src"   && GOCACHE=$W/gocache-a go build -trimpath -buildvcs=true -ldflags "$LD" -o "$W/out-a/ocr" ./cmd/opencodereview )
( cd "$W/src-b" && GOCACHE=$W/gocache-b go build -trimpath -buildvcs=true -ldflags "$LD" -o "$W/out-b/ocr" ./cmd/opencodereview )
shasum -a 256 "$W/out-a/ocr" "$W/out-b/ocr"; cmp "$W/bin/ocr-pinned" "$W/out-a/ocr"

# --- 5. đối chứng: đổi ĐÚNG MỘT thứ ---
( cd "$W/src" && GOCACHE=$W/gocache-a go build -trimpath -buildvcs=true \
    -ldflags "-s -w -X main.Version=v1.12.12 -X main.GitCommit=182898c -X main.BuildDate=2026-10-05T00:00:01Z" \
    -o "$W/out-c1/ocr" ./cmd/opencodereview )                                             # ngày +1 giây
( cd "$W/src" && GOCACHE=$W/gocache-a go build -buildvcs=true -ldflags "$LD" -o "$W/out-c2/ocr" ./cmd/opencodereview )  # không -trimpath

# --- 6. công cụ của kho, từ cây làm việc của lượt này (HEAD f69124c), TMPDIR trong $W ---
export TMPDIR=$W/tmp
unset GOPROXY GOSUMDB GOFLAGS GOMODCACHE GOCACHE CGO_ENABLED GOOS GOARCH
/opt/homebrew/bin/python3 -P validation/v21/ocr/inspect_binary.py "$W/bin/ocr-pinned" --source "$W/src" --modcache "$W/gomodcache" \
    --ldflags "$LD" --out closure-evidence/v2/v2.1/round-5/ocr-build/ocr-provenance.json

# --- 7. kiểm chéo go.sum với sum.golang.org (mạng: chỉ sum.golang.org; module đã ở cache, không tải lại) ---
mkdir "$W/sumdb-check" && git -C "$W/src" archive HEAD | tar -x -C "$W/sumdb-check"
cd "$W/sumdb-check" && rm go.sum
GOFLAGS=-mod=mod go list -deps -f '{{with .Module}}{{.Path}}@{{.Version}}{{end}}' ./cmd/opencodereview   # go.sum mới: 168 dòng
comm -23 <(sort go.sum) <(sort "$W/src/go.sum")                                                         # dòng không có trong go.sum của upstream: 0
