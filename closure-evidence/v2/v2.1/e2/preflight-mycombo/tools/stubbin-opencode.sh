#!/bin/sh
# Lane PF stub: stands in for the client on the PATH the preflight-only run is given. The real binary is never on that
# PATH. `--version` answers so client_identity() can name it; anything else refuses, so no session can ever start here.
case "$1" in
  --version) echo "stub-0.0.0 (lane PF: not the client; the run is preflight-only)"; exit 0 ;;
  *) echo "stub opencode: refusing '$*' — this run must stop after the preflight" >&2; exit 97 ;;
esac
