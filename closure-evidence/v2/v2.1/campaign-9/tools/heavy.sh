#!/bin/zsh
# heavy.sh NAME COMMAND...: runs COMMAND under the machine-wide heavy lock (one heavy job at a time: the T0 sweep, the
# read-set recorder, a campaign). Recreated 2026-10-18: the earlier file was cleared by macOS from the scratchpad; a copy
# is committed beside the campaign-9 tools. The lock is a directory; its owner file names the job and the pid.
SPD=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
NAME=${1:?name}; shift
L=$SPD/heavy.lock.d
until mkdir $L 2>/dev/null; do
  # a lock whose owner process is gone is stale
  o=$(cut -d' ' -f2 $L/owner 2>/dev/null); [[ -n $o ]] && ! kill -0 $o 2>/dev/null && rm -rf $L && continue
  sleep 30
done
echo "$NAME $$ $(date '+%F %T')" > $L/owner
trap 'rm -rf $L' EXIT INT TERM
"$@"
