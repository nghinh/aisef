#!/bin/bash
# controls: same source, same toolchain, ONE thing changed. usage: control.sh LABEL OUTDIR "<ldflags>" [go build flags...]
set -u
W=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21/ocr-build-2
. $W/env.sh
LABEL=$1; OUT=$2; LD=$3; shift 3
export GOCACHE=$W/gocache-a GOPROXY=off GOSUMDB=off CGO_ENABLED=0 GOOS=darwin GOARCH=arm64
cd $W/src
echo "control=$LABEL"; echo "go build $* -ldflags \"$LD\" -o $OUT/ocr ./cmd/opencodereview"
go build "$@" -ldflags "$LD" -o "$OUT/ocr" ./cmd/opencodereview; echo "exit=$?"
shasum -a 256 "$OUT/ocr"; stat -f '%z bytes' "$OUT/ocr"
