#!/bin/bash
# Các bước của lượt dựng lại OCR v1.12.12 (2026-10-15, 18:22 - 18:28 +07), viết lại thành một tập lệnh chạy được ở lượt
# rà soát 2026-10-17. Đây KHÔNG phải tập lệnh đã chạy nguyên khối: lượt gốc gõ từng lệnh, chỉ có ba tệp trợ giúp
# (scripts-as-run/env.sh, build.sh, control.sh - nguyên văn, kèm sha256 trong PROVENANCE.md mục 11). Bản này dựng lại cùng
# lệnh từ ba tệp đó và từ nhật ký (build.log), theo ĐÚNG thứ tự trong build.log (kiểm chéo sumdb TRƯỚC công cụ).
#
#   W=<thư mục làm việc riêng, rỗng>  EXE=<binary đã ghim>  [OUT=<tệp json>]  bash build-commands.sh [bước ...]
#
# Không có bước nào => chạy 1..8. Bước cần MẠNG: 2 (github.com), 3 (proxy.golang.org), 6 (sum.golang.org, có thể qua
# proxy.golang.org; xem PROVENANCE.md mục 8). Các bước 1, 4, 5, 7, 8 chạy ngoại tuyến khi 2 và 3 đã xong.
# Mỗi bước là một subshell với môi trường Go dựng lại từ đầu: không có cd hay biến Go nào rò sang bước sau.
# Không có binary, không có module cache trong thư mục bằng chứng này.
set -eu
: "${W:?đặt W = thư mục làm việc riêng, rỗng}" "${EXE:?đặt EXE = đường dẫn binary đã ghim}"
PIN=182898cf522da3d04157b422752d028417974e19
SHA=bf38abf320ead4e106b71c15824463640207118f38e1c10c28a73b6839104af7   # sha256 của binary đã ghim
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)                      # gốc kho aisef (có validation/v21/ocr/)
OUT=${OUT:-$W/ocr-provenance.json}          # never the committed record: a run of this script writes beside its own work

goenv() {      # = scripts-as-run/env.sh; GOSUMDB và GOPROXY để mặc định (proxy.golang.org,direct / sum.golang.org)
  export PATH=/opt/homebrew/bin:/usr/bin:/bin GOENV=off GOMODCACHE="$W/gomodcache" GOCACHE="$W/gocache" \
         GOPATH="$W/gopath" GOFLAGS=-mod=readonly GOTOOLCHAIN=local GOTELEMETRY=off GIT_TERMINAL_PROMPT=0 HOME="$W/home"
  mkdir -p "$W/home"       # 2026-10-17: GOTELEMETRY=off does not stop Go's local telemetry counters; a HOME of its own does
  unset GOPROXY GOSUMDB GONOSUMDB GONOSUMCHECK GOPRIVATE GONOPROXY GOINSECURE GOWORK
}
offline() { export GOPROXY=off GOSUMDB=off CGO_ENABLED=0 GOOS=darwin GOARCH=arm64; }
ld() { echo "-s -w -X main.Version=v1.12.12 -X main.GitCommit=$1 -X main.BuildDate=${2:-2026-10-05T00:00:00Z}"; }

build() (      # build NHÃN NGUỒN RA  (= scripts-as-run/build.sh); GOCACHE nguội riêng mỗi nhãn
  goenv; offline; export GOCACHE="$W/gocache-$1"; cd "$2"
  go build -trimpath -buildvcs=true -ldflags "$(ld "$(git rev-parse --short HEAD)")" -o "$3/ocr" ./cmd/opencodereview
  shasum -a 256 "$3/ocr"; stat -f '%z bytes' "$3/ocr")

control() (    # control NHÃN NGUỒN NHÃN-GOCACHE RA LDFLAGS [cờ go build]  (= scripts-as-run/control.sh): đổi ĐÚNG MỘT thứ
  goenv; offline; export GOCACHE="$W/gocache-$3"; cd "$2"; echo "control=$1"
  go build -buildvcs=true "${@:6}" -ldflags "$5" -o "$4/ocr" ./cmd/opencodereview
  shasum -a 256 "$4/ocr"; stat -f '%z bytes' "$4/ocr")

step1() ( goenv                                   # binary đang kiểm: sao chép trước, băm lại
  cp "$EXE" "$W/bin/ocr-pinned"; shasum -a 256 "$W/bin/ocr-pinned"
  test "$(shasum -a 256 "$W/bin/ocr-pinned" | cut -d' ' -f1)" = "$SHA")

step2() ( goenv                                   # nguồn (MẠNG: chỉ git clone này)
  git clone https://github.com/alibaba/open-code-review "$W/src"
  test "$(git -C "$W/src" rev-parse 'v1.12.12^{commit}')" = "$PIN"            # tag đúng commit ghim? (đo, không giả định)
  git -C "$W/src" checkout --detach "$PIN"
  test "$(git -C "$W/src" rev-parse HEAD)" = "$PIN"; test -z "$(git -C "$W/src" status --porcelain)"
  git clone --no-checkout "$W/src" "$W/src-b"; git -C "$W/src-b" checkout --detach "$PIN")   # bản thứ hai, từ bản đầu (cục bộ)

step3() ( goenv; cd "$W/src"                      # module (MẠNG: proxy.golang.org; go.sum của kho đầy đủ nên không cần hỏi sumdb)
  go list -deps -f '{{with .Module}}{{.Path}}@{{.Version}}{{end}}' ./cmd/opencodereview   # tải 84 module
  go list -m all                                  # đồ thị: 151 module + module chính
  go mod verify)                                  # all modules verified

step4() {                                         # dựng ngoại tuyến, hai thư mục nguồn, hai GOCACHE nguội
  build a "$W/src" "$W/out-a"; build b "$W/src-b" "$W/out-b"
  cmp "$W/bin/ocr-pinned" "$W/out-a/ocr"; cmp "$W/bin/ocr-pinned" "$W/out-b/ocr"; echo "IDENTICAL (a, b)"
}

step5() {                                         # đối chứng 1 (ngày +1 giây) và 2 (không -trimpath), từ thư mục nguồn thứ nhất
  control c1 "$W/src" a "$W/out-c1" "$(ld 182898c 2026-10-05T00:00:01Z)" -trimpath
  control c2 "$W/src" a "$W/out-c2" "$(ld 182898c)"
}

step6() ( goenv                                   # kiểm chéo go.sum với sumdb, trên bản sao cây nguồn (MẠNG)
  rm -rf "$W/sumdb-check"; mkdir "$W/sumdb-check"; git -C "$W/src" archive HEAD | tar -x -C "$W/sumdb-check"
  cd "$W/sumdb-check"; rm go.sum
  GOFLAGS=-mod=mod go list -deps -f '{{with .Module}}{{.Path}}@{{.Version}}{{end}}' ./cmd/opencodereview   # go.sum mới: 168 dòng
  test "$(comm -23 <(sort go.sum) <(sort "$W/src/go.sum") | wc -l | tr -d ' ')" = 0)   # dòng không có trong go.sum upstream: 0

step7() ( cd "$ROOT"                              # công cụ của kho (TMPDIR trong $W: công cụ KHÔNG xoá thư mục tạm của nó)
  test -f validation/v21/ocr/inspect_binary.py
  env -i PATH=/opt/homebrew/bin:/usr/bin:/bin TMPDIR="$W/tmp" /opt/homebrew/bin/python3 -P \
      validation/v21/ocr/inspect_binary.py "$W/bin/ocr-pinned" --source "$W/src" --modcache "$W/gomodcache" \
      --ldflags "$(ld 182898c)" --out "$OUT")

step8() {                                         # THÊM ở lượt rà soát 2026-10-17: hai đối chứng ở bước 5, nhưng từ thư mục nguồn thứ hai
  control c1b "$W/src-b" b "$W/out-c1b" "$(ld 182898c 2026-10-05T00:00:01Z)" -trimpath   # mong đợi: = c1 (không phụ thuộc đường dẫn)
  control c2b "$W/src-b" b "$W/out-c2b" "$(ld 182898c)"                                  # mong đợi: KHÁC c2 (nhúng đường dẫn tuyệt đối)
}

mkdir -p "$W"/bin "$W"/tmp "$W"/out-{a,b,c1,c2,c1b,c2b}
steps=("$@"); [ ${#steps[@]} -gt 0 ] || steps=(1 2 3 4 5 6 7 8)
for s in "${steps[@]}"; do echo "== bước $s $(date -u +%FT%TZ)"; "step$s"; done
