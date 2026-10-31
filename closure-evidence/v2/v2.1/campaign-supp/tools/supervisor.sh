#!/bin/zsh
# supervisor.sh C TOOLS: keep the disk watchdog alive until the campaign is done, so disk protection is CONTINUOUS and
# does not depend on the AI's wake cycle. Every 60 s: if no `watchdog.sh <C>` process is running, respawn it. Exits
# only when C/campaign.done appears. A detached daemon (nohup); touches nothing but the watchdog. Added 2026-10-29 per
# owner instruction ("Giám sát phải liên tục ... sửa riêng monitor để duy trì bảo vệ, không đụng worker").
C=$1; TOOLS=$2
[[ -d $C && -d $TOOLS ]] || { echo "usage: supervisor.sh C TOOLS"; exit 2; }
while [[ ! -e $C/campaign.done ]]; do
  if ! pgrep -f "watchdog.sh $C" >/dev/null 2>&1; then
    nohup zsh $TOOLS/watchdog.sh $C >> $C/watchdog.out 2>&1 &
    echo "$(date -u +%FT%TZ) supervisor respawned watchdog (pid $!)" >> $C/supervisor.log
  fi
  sleep 60
done
echo "$(date -u +%FT%TZ) campaign.done present — supervisor exits" >> $C/supervisor.log
