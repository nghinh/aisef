#!/bin/zsh
# Campaign-2 event watch: per-file scan of worker logs (new matching lines only), disk, STOP.log, one digest per run.
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
C=$SP/m21/c2; M=$SP/mon
PAT='"class": "(INFRA|TIMEOUT|NOT_RUN)"|STOPPED|DISK |STOP file|RUNNER_EXCEPTION before|killed; classes .*(TIMEOUT.: [1-9]|INFRA.: [1-9]|NOT_RUN.: [1-9])| ERROR |escaped=[1-9]|harness_orphans=[0-9]+->[1-9]'
[[ -e $M/prev ]] || grep -H -n -E "$PAT" $C/c2-w*.log | sort > $M/prev
n=0; hi=0; lastf=0; t0=$(date +%s); dg=0
while true; do
  grep -H -n -E "$PAT" $C/c2-w*.log | sort > $M/cur
  comm -13 $M/prev $M/cur > $M/new
  KNOWN='kill not confirmed: the mutant again FAIL (FAIL|ERROR): test_(a_client_directory_that_holds_home_or_the_workspace_is_refused|the_cli_refuses_anchor_paths_it_would_not_write)'
  k=$(grep -c -E "$KNOWN" $M/new); (( k > 0 )) && echo "known temp-path-signature INFRA +$k (total $(grep -c -E "$KNOWN" $M/cur))"
  grep -v -E "$KNOWN" $M/new | sed "s#^$C/##" | cut -c1-300
  mv $M/cur $M/prev
  f=$(df -g /System/Volumes/Data | awk 'NR==2{print $4}')
  (( f < 15 && f != lastf )) && echo "DISK $f GiB free (swap $(sysctl -n vm.swapusage | awk '{print $6}'))"; lastf=$f
  [[ -s $C/STOP.log ]] && echo "STOP.log: $(tail -1 $C/STOP.log)"
  l15=$(sysctl -n vm.loadavg | awk '{printf "%d", $4}')
  (( l15 >= 30 && ! hi )) && { echo "LOAD 15-min $(sysctl -n vm.loadavg)"; hi=1; }
  n=$((n+1))
  if (( ! dg && $(date +%s) - t0 >= 1500 )); then dg=1
    tail -1 $C/progress.log | /usr/bin/python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('progress', d['at'], 'finished', d['targets_finished'], 'running', d['targets_running'], 'classes', d['mutants_classified'], 'free', d['free_gib'], 'rate', d['realized_s_per_ub_s'], 'eta_h', d['eta_h'])"; echo "load $(sysctl -n vm.loadavg) swap $(sysctl -n vm.swapusage | awk '{print $6}') fseventsd $(top -l 1 -pid $(pgrep -x fseventsd | head -1) -stats mem 2>/dev/null | tail -1)" 2>/dev/null || true
  fi
  [[ -e $C/campaign.done ]] && { echo "campaign.done"; exit 0; }
  sleep 60
done
