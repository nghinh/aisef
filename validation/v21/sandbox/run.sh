#!/bin/zsh
# V2.1 (F): measure the model-session confinement INSIDE a Linux container, on a macOS host with Docker Desktop.
# It records each claim as the operation tried and what happened (measure.py: denials / tmpfs_only / by_design /
# controls), and reports which of the container's own boundaries must be loosened — one axis at a time and in
# combination — for bubblewrap to set up its namespaces at all. Run under the machine-wide heavy lock (it uses docker):
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
print "measured tree: $(git -C $W rev-parse HEAD); uncommitted paths: $(git -C $W status --porcelain | wc -l | tr -d ' ')"
git -C $W status --porcelain | sed 's/^/  /'

print "== build $IMG (pinned $BASE)"
cat > $OUT/Dockerfile <<DOCKER
FROM $BASE
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap git libcap2-bin util-linux \\
 && rm -rf /var/lib/apt/lists/* && useradd -m -u 1000 op
DOCKER
docker build -q -t $IMG -f $OUT/Dockerfile $OUT || { print "build failed"; exit 1; }
print "== guest (the image's own view of the Docker Desktop VM kernel)"
docker run --rm --user 1000:1000 $IMG sh -c 'echo "kernel: $(uname -srm)"; \
  if [ -e /sys/module/apparmor ]; then echo "apparmor: in kernel"; else echo "apparmor: not in this kernel (/sys/module/apparmor absent)"; fi; \
  echo "max_user_namespaces: $(cat /proc/sys/user/max_user_namespaces)"; \
  echo "bubblewrap package: $(dpkg-query -W -f "\${Version}" bubblewrap)"; bwrap --version'

# a host-side listener the sandbox must not reach (the container's own processes and sockets are measure.py's)
( exec 3<>/dev/null; python3 -c '
import socket,sys,time
s=socket.socket(); s.bind(("127.0.0.1",0)); s.listen(1)
open(sys.argv[1],"w").write(str(s.getsockname()[1]))
t=time.time()
while time.time()-t<900:
    try:
        s.settimeout(1); c,_=s.accept(); c.close()
    except socket.timeout: pass
' $OUT/host.port ) & LISTENER=$!
while [[ ! -s $OUT/host.port ]]; do sleep 0.1; done
HOST_PORT=$(cat $OUT/host.port)
print "host listener on 127.0.0.1:$HOST_PORT; host-gateway seen from the container as host.docker.internal"

run_profile() {  # name  network  extra-docker-flags...
  local name=$1 net=$2; shift 2
  print "\n== profile $name (network=$net) flags: $*"
  docker run --rm \
    --add-host=host.docker.internal:host-gateway \
    -e PROFILE=$name -e NETWORK=$net -e SECCOMP="${SECCOMP:-default}" -e APPARMOR="${APPARMOR:-default}" \
    -e SYSTEMPATHS="${SYSTEMPATHS:-default}" -e HOST_PORT=$HOST_PORT -e HOST_GATEWAY=host.docker.internal \
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
for group in ("denials", "network", "observed", "tmpfs_only", "by_design", "controls"):
    for k,v in r.get(group,{}).items():
        if isinstance(v, list): print(f"  {group} {k}: {v[:2]}"); continue
        s = "not-started(bwrap unavailable)" if not v.get("started") else f"exit {v['exit']}: {' | '.join(v.get('out','').splitlines())[:110]}"
        print(f"  {group} {k}: {s}")
print(f"  after (outside the sandbox): {json.dumps(r.get('after',{}), sort_keys=True)}")
PY
}

# the matrix: which of the container's own boundaries must be loosened for bwrap to set up its user/mount namespaces.
# default == nothing loosened (the hardened container). P2-P4 loosen cumulatively; X1/X2 single out the axes.
run_profile P1-default none
SECCOMP=unconfined run_profile P2-seccomp none --security-opt seccomp=unconfined
SECCOMP=unconfined APPARMOR=unconfined run_profile P3-seccomp-apparmor none \
  --security-opt seccomp=unconfined --security-opt apparmor=unconfined
SECCOMP=unconfined APPARMOR=unconfined SYSTEMPATHS=unconfined run_profile P4-all none \
  --security-opt seccomp=unconfined --security-opt apparmor=unconfined --security-opt systempaths=unconfined
SYSTEMPATHS=unconfined run_profile X2-systempaths none --security-opt systempaths=unconfined
SECCOMP=unconfined SYSTEMPATHS=unconfined run_profile X1-seccomp-systempaths none \
  --security-opt seccomp=unconfined --security-opt systempaths=unconfined
# the session shares the container's network (what a run uses: it must reach its provider): egress is NOT confined
SECCOMP=unconfined APPARMOR=unconfined SYSTEMPATHS=unconfined run_profile P5-all-net-host host \
  --security-opt seccomp=unconfined --security-opt apparmor=unconfined --security-opt systempaths=unconfined
SECCOMP=unconfined SYSTEMPATHS=unconfined run_profile X3-seccomp-systempaths-net-host host \
  --security-opt seccomp=unconfined --security-opt systempaths=unconfined

kill $LISTENER 2>/dev/null
print "\n== done; per-profile JSON in $OUT/*.json"
