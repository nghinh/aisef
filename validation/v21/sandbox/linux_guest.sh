#!/bin/zsh
# V2.1 (F; owner 2026-10-08, item 5): the Linux guest checks (linux_guest.py a, b, c) and the two test modules
# (test_v21_confine, p4/test_process_range) in Docker Desktop's Linux VM on a macOS host. One container at a time.
#   zsh validation/v21/sandbox/linux_guest.sh TREE PROCPS_DIR OUT_DIR
# TREE: the tree to measure, mounted read-only at /repo (a git archive of a commit). PROCPS_DIR: `ps` and
# `libproc2.so.0` copied (docker cp) from a local Debian trixie image that ships procps: the measure image has no
# `ps`, which cleanup_authority reads. Uses only local images; pulls and builds nothing; no network in the guest;
# never runs opencode; calls no provider. OUT_DIR must not exist.
set -u
TREE=${1:?TREE}; PROCPS=${2:?PROCPS_DIR}; OUT=${3:?OUT_DIR}
[[ ! -e $OUT ]] || { print "OUT_DIR exists"; exit 2; }
mkdir -p $OUT
IMG=aisef-sandbox-measure
# every container: discarded, docker-init as PID 1 (reaps what is orphaned to it), no network, uid 1000 without
# capabilities, bounded pids/memory/CPU, the tree and the two procps files read-only
BASE=(--rm --init --network none --user 1000:1000 --cap-drop ALL --pids-limit 512 --memory 1g --cpus 2 -w /repo
      -v $TREE:/repo:ro -v $PROCPS/ps:/usr/local/bin/ps:ro -v $PROCPS/libproc2.so.0:/usr/lib/aarch64-linux-gnu/libproc2.so.0:ro)
# what bubblewrap needs on this guest kernel (SANDBOX-LINUX.md §3, profile X1): Docker's seccomp filter off, system
# paths unmasked; AppArmor left as is (not in this kernel)
X1=(--security-opt seccomp=unconfined --security-opt systempaths=unconfined)
# the processes the checks did not start: two canaries before the boundary (one in this shell's group, one in a
# session of its own) and one after it, all children of this shell, never of the harness
ENTRY='mkdir -p /tmp/g; H=/repo/validation/v21/sandbox/linux_guest.py
python3 -B $H canary early &
setsid python3 -B $H canary early-setsid &
(until [ -e /tmp/g/boundary ]; do sleep 0.1; done; sleep 1.5; python3 -B $H canary late & wait) &
python3 -B $H "$0"'

{
  print "== host: $(uname -srm); $(sw_vers -productName 2>/dev/null) $(sw_vers -productVersion 2>/dev/null)"
  docker version --format 'docker client {{.Client.Version}}; server {{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}'
  docker info --format 'guest: {{.OperatingSystem}}; kernel {{.KernelVersion}}; {{.NCPU}} CPUs; {{.MemTotal}} bytes; cgroup v{{.CgroupVersion}}; security {{.SecurityOptions}}'
  docker image inspect $IMG --format "image: $IMG {{.Id}} created {{.Created}} {{.Os}}/{{.Architecture}}"
  print "tree: $TREE"; print "procps: $(shasum -a 256 $PROCPS/ps $PROCPS/libproc2.so.0 | awk '{print $1}' | tr '\n' ' ')"
  print "base flags: ${BASE[*]}"; print "X1 flags: ${X1[*]}"
  for prof in hardened X1; do
    [[ $prof == X1 ]] && F=($X1) || F=()
    print "== guest view, $prof:"
    docker run $BASE $F $IMG sh -c 'echo "kernel $(uname -srvm)"; echo "uid $(id -u) gid $(id -g)"; grep -E "^(Seccomp|NoNewPrivs|CapEff|CapBnd):" /proc/self/status | tr "\n" " "; echo;
      echo "max_user_namespaces $(cat /proc/sys/user/max_user_namespaces)"; bwrap --version; sha256sum /usr/bin/bwrap; python3 -VV; ps --version;
      bwrap --unshare-user --unshare-pid --die-with-parent --ro-bind / / --proc /proc true && echo "bwrap starts: yes" || echo "bwrap starts: no"'
  done
} > $OUT/environment.txt 2>&1

run() {  # name  flags...  -- command...
  local name=$1; shift
  local -a flags; while [[ $1 != -- ]]; do flags+=($1); shift; done; shift
  print "== $name: docker run ${BASE[*]} ${flags[*]} $IMG $*" >> $OUT/commands.txt
  local t0=$(date +%s)
  docker run $BASE $flags $IMG "$@" > $OUT/$name.out 2> $OUT/$name.err
  print "   exit $? in $(( $(date +%s) - t0 )) s" >> $OUT/commands.txt
}
run a $X1 -- sh -c "$ENTRY" a
run b -- sh -c "$ENTRY" b
run c $X1 -- sh -c "$ENTRY" c
run d-test_v21_confine -- python3 -B -m unittest -v tests.v2.test_v21_confine
run d-test_process_range -- python3 -B -m unittest -v tests.v2.p4.test_process_range
print "done: $OUT"
