#!/bin/bash
# usage: build.sh LABEL SRCDIR OUTDIR [extra go build flags...]   -- offline (GOPROXY=off), cold GOCACHE per label
set -u
W=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21/ocr-build-2
. $W/env.sh
LABEL=$1; SRC=$2; OUT=$3; shift 3
export GOCACHE=$W/gocache-$LABEL GOPROXY=off GOSUMDB=off CGO_ENABLED=0 GOOS=darwin GOARCH=arm64
LD="-s -w -X main.Version=v1.12.12 -X main.GitCommit=$(git -C $SRC rev-parse --short HEAD) -X main.BuildDate=2026-10-05T00:00:00Z"
cd $SRC
echo "label=$LABEL src=$SRC start=$(date -u +%FT%TZ)"
echo "go build -trimpath -buildvcs=true -ldflags \"$LD\" $* -o $OUT/ocr ./cmd/opencodereview"
s=$(date +%s)
go build -trimpath -buildvcs=true -ldflags "$LD" "$@" -o "$OUT/ocr" ./cmd/opencodereview
rc=$?
echo "exit=$rc seconds=$(( $(date +%s)-s )) end=$(date -u +%FT%TZ)"
shasum -a 256 "$OUT/ocr"; stat -f '%z bytes' "$OUT/ocr"
