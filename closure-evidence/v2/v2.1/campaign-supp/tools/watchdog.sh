#!/bin/zsh
# watchdog.sh C: every 300 s, append progress.py's JSON line to $C/progress.log, and enforce the owner's disk tiers
# (decision 2026-10-28):
#   < 15 GiB free : WARN — logged to $C/disk.log (early notice; nothing stops).
#   < 10 GiB free : graceful STOP — create $C/STOP; each worker stops after its current target (nothing in progress cut).
#   <  6 GiB free : protect the floor — SIGTERM only the mutation.py run processes whose cwd is one of THIS campaign's
#                   worker worktrees ($C/w<N>), checked with lsof right before the signal (INV-MUTATION-AUTHORITY: the
#                   controller view signals, never a worker). Finished targets stay in the records; the in-progress one
#                   is not evidence. Nothing is ever deleted; user data and goe-* are never touched.
# Ends when $C/campaign.done exists.
C=$1; [[ -d $C && -s $C/queue.txt ]] || { echo "usage: watchdog.sh C"; exit 2; }
free_gib() { df -g /System/Volumes/Data | awk 'NR==2{print $4}'; }
while [[ ! -e $C/campaign.done ]]; do
  /opt/homebrew/bin/python3 $C/progress.py $C --json >> $C/progress.log 2>&1
  f=$(free_gib)
  (( f < 15 )) && echo "$(date '+%FT%T%z') WARN disk $f GiB free (< 15)" >> $C/disk.log
  if (( f < 10 )) && [[ ! -e $C/STOP ]]; then
    echo "$(date '+%FT%T%z') disk $f GiB free (< 10): STOP created, workers stop after their current target" | tee -a $C/disk.log > $C/STOP
  fi
  if (( f < 6 )); then
    for p in $(pgrep -f "validation/v2/mutation.py run"); do
      cwd=$(lsof -a -p $p -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
      case "$cwd" in
        $C/w[0-9]*) kill -TERM $p && echo "$(date '+%FT%T%z') disk $f GiB free (< 6): SIGTERM $p (mutation.py run, cwd $cwd)" >> $C/disk.log ;;
        *) echo "$(date '+%FT%T%z') not signalled: $p (cwd ${cwd:-unknown}) is not a worker of this campaign" >> $C/disk.log ;;
      esac
    done
  fi
  sleep 300
done
