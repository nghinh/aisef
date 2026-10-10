#!/bin/zsh
# watchdog.sh C: every 300 s, append progress3.py's JSON line to $C/progress.log. Disk: below 12 GiB free it creates
# $C/STOP (each worker stops after its current target: nothing in progress is cut); below 6 GiB it stops the running
# `mutation.py run` processes under control, as campaign 1 was stopped (SIGTERM; their finished targets stay in their
# records, the target in progress is not evidence): only a process whose command line is `... validation/v2/mutation.py
# run ...` AND whose cwd is one of this campaign's worker worktrees ($C/c2-w<N>), checked with lsof right before the
# signal. Ends when $C/campaign.done exists.
C=$1; [[ -d $C && -s $C/queue.txt ]] || { echo "usage: watchdog.sh C"; exit 2; }
free_gib() { df -g /System/Volumes/Data | awk 'NR==2{print $4}'; }
while [[ ! -e $C/campaign.done ]]; do
  /opt/homebrew/bin/python3 $C/progress3.py $C --json >> $C/progress.log 2>&1
  f=$(free_gib)
  if (( f < 12 )) && [[ ! -e $C/STOP ]]; then
    echo "$(date '+%FT%T%z') disk $f GiB free (< 12): STOP created, workers stop after their current target" | tee -a $C/STOP.log > $C/STOP
  fi
  if (( f < 6 )); then
    for p in $(pgrep -f "validation/v2/mutation.py run"); do
      cwd=$(lsof -a -p $p -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
      case "$cwd" in
        $C/c2-w[0-9]*) kill -TERM $p && echo "$(date '+%FT%T%z') disk $f GiB free (< 6): SIGTERM $p (mutation.py run, cwd $cwd)" >> $C/STOP.log ;;
        *) echo "$(date '+%FT%T%z') not signalled: $p (cwd ${cwd:-unknown}) is not a worker of this campaign" >> $C/STOP.log ;;
      esac
    done
  fi
  sleep 300
done
