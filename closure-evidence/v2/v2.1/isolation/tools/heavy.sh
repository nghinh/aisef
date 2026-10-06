#!/bin/zsh
# heavy.sh <label> <cmd...>: run one heavy job (full test suite, mutation, Q4/Q5 runs, qualification dry runs) only while
# holding the machine-wide heavy lock, so no two heavy jobs overlap (standing rule: never the full suite concurrently
# with mutation). The lock is a directory (atomic mkdir); a lock whose holder pid is gone is stale.
L=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/heavy.lock
LABEL=$1; shift
while ! mkdir $L 2>/dev/null; do
  if [[ -f $L/pid ]] && ! ps -p $(cat $L/pid) >/dev/null 2>&1; then rm -rf $L; continue; fi
  sleep 20
done
echo $$ > $L/pid; echo "$LABEL since $(date '+%F %T')" > $L/who
"$@"; RC=$?
rm -rf $L
exit $RC
