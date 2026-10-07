#!/bin/zsh
# V2.1 (F): measure the developer-session confinement INSIDE a Linux container, on a macOS host with Docker Desktop.
# It proves each claim by a denied operation and reports, honestly, which container boundary each needs loosened for
# bubblewrap to set up its namespaces at all. Run under the machine-wide heavy lock (it uses docker):
#   zsh /private/tmp/.../heavy.sh "sandbox measure" zsh validation/v21/sandbox/run.sh OUT_DIR
# OUT_DIR must not exist. Never runs the real opencode; never calls a provider.
set -u
HERE=${0:A:h}; W=${HERE:h:h:h}; OUT=${1:?OUT_DIR}
[[ ! -e $OUT ]] || { print "OUT_DIR exists"; exit 2; }
mkdir -p $OUT
BASE='python:3.14-slim-trixie@sha256:3353bb7e9ae99c7cce6cad2b2f2b174e8f22813ac43e3b13e7a742627d2b01d8'
IMG=aisef-sandbox-measure

print "== host"
docker version --format 'docker {{.Server.Version}} server {{.Server.Os}}/{{.Server.Arch}}'
print "host: $(uname -srm)  (this host runs no Linux backend itself; the guest below is a Docker Desktop VM container)"

print "== build $IMG (pinned $BASE)"
cat > $OUT/Dockerfile <<DOCKER
FROM $BASE
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap git libcap2-bin util-linux \\
 && rm -rf /var/lib/apt/lists/* && useradd -m -u 1000 op
DOCKER
docker build -q -t $IMG -f $OUT/Dockerfile $OUT || { print "build failed"; exit 1; }

# a host-side listener the sandbox must not reach, and a snapshot of host pids the sandbox must not see
( exec 3<>/dev/null; python3 -c '
import socket,sys,time
s=socket.socket(); s.bind(("127.0.0.1",0)); s.listen(1)
open(sys.argv[1],"w").write(str(s.getsockname()[1]))
t=time.time()
while time.time()-t<120:
    try:
        s.settimeout(1); c,_=s.accept(); c.close()
    except socket.timeout: pass
' $OUT/host.port ) & LISTENER=$!
while [[ ! -s $OUT/host.port ]]; do sleep 0.1; done
HOST_PORT=$(cat $OUT/host.port)
HOST_PIDS=$(ps -A -o pid= | tr -s ' ' | tr '\n' ',' | cut -c1-80)
print "host listener on 127.0.0.1:$HOST_PORT; host-gateway seen from the container as host.docker.internal"

run_profile() {  # name  network  extra-docker-flags...
  local name=$1 net=$2; shift 2
  print "\n== profile $name (network=$net) flags: $*"
  docker run --rm \
    --add-host=host.docker.internal:host-gateway \
    -e PROFILE=$name -e NETWORK=$net -e SECCOMP="${SECCOMP:-default}" -e APPARMOR="${APPARMOR:-default}" \
    -e SYSTEMPATHS="${SYSTEMPATHS:-default}" -e HOST_PORT=$HOST_PORT -e HOST_GATEWAY=host.docker.internal \
    -e HOST_PIDS="$HOST_PIDS" \
    --user 1000:1000 --cap-drop ALL --pids-limit 512 --memory 1g \
    -v $W:/repo:ro -v $HERE/measure.py:/measure.py:ro \
    "$@" \
    $IMG python3 /measure.py > $OUT/$name.json 2> $OUT/$name.err
  local rc=$?
  if [[ $rc -ne 0 ]]; then print "  (container exited $rc; stderr:)"; sed 's/^/  /' $OUT/$name.err | tail -8; fi
  python3 - $OUT/$name.json <<'PY'
import json,sys
try: r=json.load(open(sys.argv[1]))
except Exception as e: print(f"  no JSON report: {e}"); sys.exit()
m=r["measure"]
print(f"  bwrap ran: {'yes' if not any('did not run' in p for p in m['problems']) else 'NO'}; measure problems: {len(m['problems'])}")
for p in m["problems"][:12]: print(f"    - {p}")
d=r.get("denials",{})
for k,v in d.items():
    s = "not-started(bwrap unavailable)" if not v.get("started") else f"exit {v['exit']}: {v.get('out','')[:70]}"
    print(f"  deny {k}: {s}")
c=r.get("controls",{}); h=r.get("host",{})
print(f"  control workspace_writable: {c.get('workspace_writable')}")
print(f"  control fake_client_runs: {c.get('fake_client_runs')}")
print(f"  host after run: runtime_unchanged={h.get('runtime_unchanged')} anchor_unchanged={h.get('anchor_unchanged')} written_in_run_dir={h.get('written_in_run_dir')}")
PY
}

# the matrix: which of the container's own boundaries must be loosened for bwrap to set up its user/mount namespaces.
# default == nothing loosened (the hardened container). Each later profile loosens one more axis.
run_profile P1-default none
SECCOMP=unconfined run_profile P2-seccomp none --security-opt seccomp=unconfined
SECCOMP=unconfined APPARMOR=unconfined run_profile P3-seccomp-apparmor none \
  --security-opt seccomp=unconfined --security-opt apparmor=unconfined
SECCOMP=unconfined APPARMOR=unconfined SYSTEMPATHS=unconfined run_profile P4-all none \
  --security-opt seccomp=unconfined --security-opt apparmor=unconfined --security-opt systempaths=unconfined
# the same loosening but the session shares the container's network: egress is then NOT confined (reported)
SECCOMP=unconfined APPARMOR=unconfined SYSTEMPATHS=unconfined run_profile P5-all-net-host host \
  --security-opt seccomp=unconfined --security-opt apparmor=unconfined --security-opt systempaths=unconfined

kill $LISTENER 2>/dev/null
print "\n== done; per-profile JSON in $OUT/*.json"
