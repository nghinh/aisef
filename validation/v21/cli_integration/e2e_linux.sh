#!/bin/zsh
# V2.1 (B-03 round 3, WP-E2E; owner 2026-10-12, item 7): a real `aisef run` — the real CLI — end to end in the Linux
# guest (Docker Desktop's VM on a macOS host), with a scripted client and a loopback provider: the success path, writes
# outside the allowed scope, an isolation that cannot be given, child processes, evidence and anchor. One container at
# a time, discarded; the driver is e2e_guest.py.
#   zsh validation/v21/cli_integration/e2e_linux.sh TREE PROCPS_DIR OUT_DIR ARCHIVE COMMIT
# TREE: the tree to run, mounted read-only at /repo — ARCHIVE (a `git archive` of COMMIT) extracted. PROCPS_DIR: `ps`
# and `libproc2.so.0` (see validation/v21/sandbox/linux_guest.sh: the image has no `ps`). Same container flags as
# linux_guest.sh; no network in any container; only the local image; pulls, builds and removes nothing; never runs
# opencode (the guest has none; the client is e2e_client.py) and calls no provider. Containers the harness did not
# start (a database, a cache) are listed in environment.txt and never touched. OUT_DIR must not exist; the evidence
# of each container comes out through its stdout (no writable host mount): e2e-<profile>.json and guest-<profile>/.
set -u
TREE=${1:?TREE}; PROCPS=${2:?PROCPS_DIR}; OUT=${3:?OUT_DIR}; ARCHIVE=${4:?ARCHIVE}; COMMIT=${5:?COMMIT}
[[ ! -e $OUT ]] || { print "OUT_DIR exists"; exit 2; }
mkdir -p $OUT
IMG=aisef-sandbox-measure; PROCPS_IMG=postgres:16.15
BASE=(--rm --init --network none --user 1000:1000 --cap-drop ALL --pids-limit 512 --memory 1g --cpus 2 -w /repo
      -v $TREE:/repo:ro -v $PROCPS/ps:/usr/local/bin/ps:ro -v $PROCPS/libproc2.so.0:/usr/lib/aarch64-linux-gnu/libproc2.so.0:ro)
X1=(--security-opt seccomp=unconfined --security-opt systempaths=unconfined)
DRIVER=/repo/validation/v21/cli_integration/e2e_guest.py
load() { print -r -- "host load average $(sysctl -n vm.loadavg) at $(date '+%Y-%m-%dT%H:%M:%S%z')"; }

{
  print "== host: $(uname -srm); $(sw_vers -productName 2>/dev/null) $(sw_vers -productVersion 2>/dev/null)"; load
  print "== docker version"; docker version
  docker info --format 'guest: {{.OperatingSystem}}; kernel {{.KernelVersion}}; {{.NCPU}} CPUs; {{.MemTotal}} bytes; cgroup v{{.CgroupVersion}}; security {{.SecurityOptions}}'
  print "== other containers running in the same VM (not started by this script)"; docker ps --format '{{.ID}} {{.Image}} {{.Status}}'
  docker image inspect $IMG --format "image: $IMG {{.Id}} created {{.Created}} {{.Os}}/{{.Architecture}}"
  print "tree: $TREE"; print "archive: $ARCHIVE sha256 $(shasum -a 256 $ARCHIVE | cut -c1-64); files $(tar -tf $ARCHIVE | grep -vc '/$')"
  print "tree files: $(find $TREE -type f | wc -l | tr -d ' ')"
  print "commit: $COMMIT tree $(git -C ${0:A:h} rev-parse "$COMMIT^{tree}")"
  print "procps: $(shasum -a 256 $PROCPS/ps $PROCPS/libproc2.so.0 | awk '{print $1}' | tr '\n' ' ')"
  print "base flags: ${BASE[*]}"; print "X1 flags: ${X1[*]}"
  print "driver: python3 -B $DRIVER run --profile <X1|hardened>   (X1: the container run with the X1 flags above; hardened: with none)"
  for prof in hardened X1; do
    [[ $prof == X1 ]] && F=($X1) || F=()
    print "== guest view, $prof:"
    docker run $BASE $F $IMG sh -c 'echo "kernel $(uname -srvm)"; echo "debian $(cat /etc/debian_version)"; echo "uid $(id -u) gid $(id -g) HOME $HOME";
      grep -E "^(Seccomp|NoNewPrivs|CapEff|CapBnd):" /proc/self/status | tr "\n" " "; echo; echo "max_user_namespaces $(cat /proc/sys/user/max_user_namespaces)";
      bwrap --version; sha256sum /usr/bin/bwrap; python3 -VV; git --version; command -v opencode || echo "opencode: absent from the guest";
      bwrap --unshare-user --unshare-pid --die-with-parent --ro-bind / / --proc /proc true && echo "bwrap starts: yes" || echo "bwrap starts: no"'
  done
  load
} > $OUT/environment.txt 2>&1

for prof in X1 hardened; do
  [[ $prof == X1 ]] && F=($X1) || F=()
  print "== $prof: docker run $BASE $F $IMG python3 -B $DRIVER run --profile $prof" >> $OUT/commands.txt
  print "   $(load)" >> $OUT/commands.txt
  t0=$(date +%s)
  docker run $BASE $F $IMG python3 -B $DRIVER run --profile $prof > $OUT/e2e-$prof.out 2> $OUT/e2e-$prof.err
  code=$?
  print "   exit $code in $(( $(date +%s) - t0 )) s; $(load)" >> $OUT/commands.txt
  awk '/^@@E2E-RESULT-BEGIN/{f=1;next} /^@@E2E-RESULT-END/{f=0} f' $OUT/e2e-$prof.out > $OUT/e2e-$prof.json
  mkdir -p $OUT/guest-$prof
  awk '/^@@E2E-TAR-BEGIN/{f=1;next} /^@@E2E-TAR-END/{f=0} f' $OUT/e2e-$prof.out | base64 -d | tar -xzf - -C $OUT/guest-$prof
  print "$prof: container exit $code; $(grep '^ "passed"' $OUT/e2e-$prof.json); $(grep -c '"passed": false' $OUT/e2e-$prof.json) failed entries"
done
print "done: $OUT"
