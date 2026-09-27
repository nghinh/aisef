#!/bin/zsh
# Q4 — the fresh 100,000-trace differential on ONE exact candidate (owner's P8 / QP-8 EXECUTION AUTHORIZATION §4, §18-§25):
# ten chunks of 10,000 seeds, each a separate worker process inside its own owned process range, at most W at once,
# no shared mutable control state (each chunk owns its seed range and its output file); the subject frozen before the
# first trace, F1-F11 and the V1 guard measured before and after, disk / memory / worker liveness sampled throughout.
#
#   validation/qualification/q4_run.sh [W]        # default 5 workers
set -u
A=/Users/nghinh/Downloads/projects/ai-sdlc; cd $A
W=${1:-5}
OUT=$A/closure-evidence/v2/Q4
SP=${AISEF_SCRATCH:-/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad}
LOG=$SP/q4-logs; mkdir -p $LOG $OUT/chunks $OUT/owned
KT=4d6081940f5b9dae47439f73f0157161e028d804
stamp() { date '+%F %T'; }
DIRTY=$(git status --porcelain | grep -v '^?? closure-evidence/v2/Q4/\|^ M closure-evidence/v2/Q4/\|^?? closure-evidence/v2/P8-RUN-HISTORY.json\|^ M closure-evidence/v2/P8-RUN-HISTORY.json' || true)
[ -z "$DIRTY" ] || { echo "REFUSED: the working tree is dirty outside Q4's output:"; echo "$DIRTY"; exit 1; }
[ "$(git rev-parse HEAD:aisef2)" = "$KT" ] || { echo "REFUSED: HEAD's aisef2 tree is not the candidate's $KT"; exit 1; }
[ -f $OUT/CALIBRATION.json ] && python3 -P -c "import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))['all_detected'] else 1)" $OUT/CALIBRATION.json \
  || { echo "REFUSED: no calibration with every defect detected (q4_aggregate.py --calibrate first)"; exit 1; }
ls $OUT/chunks/chunk-*.json >/dev/null 2>&1 && { echo "REFUSED: chunk records exist — a rerun is a new attempt: pass ATTEMPT=N"; [ -n "${ATTEMPT:-}" ] || exit 1; }
ATTEMPT=${ATTEMPT:-1}
echo "[$(stamp)] Q4: 10 x 10000 traces, $W workers, attempt $ATTEMPT, kernel tree $KT, HEAD $(git rev-parse --short HEAD)"
# 1. the subject, frozen before the first trace (the design pilot runs here; it is not counted)
[ -f $OUT/SUBJECT.json ] || python3 -P validation/qualification/q4.py --freeze || { echo "REFUSED: the subject could not be frozen"; exit 1; }
# 2. F1-F11, the V1 guard and W0 before the first trace
python3 -P validation/qualification/q4_aggregate.py --conformance start || { echo "REFUSED: conformance at start"; exit 1; }
# 3. the resource monitor: disk, memory, worker liveness, output completeness, every 15 s until told to stop
python3 -P - $OUT $LOG "$KT" <<'PYEOF' &
import json, os, pathlib, subprocess, sys, time
out, log, kt = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
stop = log / "monitor.stop"
samples, started = [], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
def mem_free_mb():
    try:
        txt = subprocess.run(["vm_stat"], capture_output=True, text=True, encoding="utf-8").stdout
        page = int(txt.split("page size of")[1].split("bytes")[0])
        free = sum(int(ln.split(":")[1].strip().rstrip(".")) for ln in txt.splitlines() if ln.startswith(("Pages free", "Pages inactive", "Pages speculative")))
        return free * page // 2**20
    except Exception:
        return None
def workers():
    try:
        txt = subprocess.run(["ps", "-axo", "pid=,rss=,command="], capture_output=True, text=True, encoding="utf-8").stdout
        rows = [ln.split(None, 2) for ln in txt.splitlines() if "q4.py --chunk" in ln and "grep" not in ln]
        return [{"pid": int(r[0]), "rss_mb": int(r[1]) // 1024, "chunk": r[2].split("--chunk")[1].split()[0]} for r in rows]
    except Exception:
        return None
while not stop.exists():
    st = os.statvfs(out)
    samples.append({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "disk_free_mb": st.f_bavail * st.f_frsize // 2**20,
                    "mem_free_mb": mem_free_mb(), "workers": workers(), "chunk_files": sorted(p.name for p in (out / "chunks").glob("chunk-*.json")),
                    "kernel_tree_unchanged": subprocess.run(["git", "rev-parse", "HEAD:aisef2"], capture_output=True, text=True, encoding="utf-8").stdout.strip() == kt})
    time.sleep(15)
rec = {"record": "AISEF V2 — Q4 resource monitor (§23)", "started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
       "interval_s": 15, "samples": len(samples), "disk_free_mb_min": min(s["disk_free_mb"] for s in samples) if samples else None,
       "mem_free_mb_min": min((s["mem_free_mb"] for s in samples if s["mem_free_mb"] is not None), default=None),
       "workers_max": max((len(s["workers"] or []) for s in samples), default=0), "worker_rss_mb_max": max((w["rss_mb"] for s in samples for w in (s["workers"] or [])), default=None),
       "kernel_tree_unchanged_throughout": all(s["kernel_tree_unchanged"] for s in samples), "chunk_files_at_end": samples[-1]["chunk_files"] if samples else [],
       "series": samples}
(out / "RESOURCES.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
PYEOF
MON=$!
rm -f $LOG/monitor.stop
# 4. the ten chunks, W at a time, each inside its own owned process range; a chunk's exit status is kept, nothing is retried here
run_chunk() {
  K=$1
  echo "[$(stamp)] chunk $K start (attempt $ATTEMPT)"
  python3 -P validation/v2/owned_run.py --out $OUT/owned/chunk-$K.attempt-$ATTEMPT.json -- \
    python3 -P validation/qualification/q4.py --chunk $K --attempt $ATTEMPT > $LOG/chunk-$K.attempt-$ATTEMPT.log 2>&1
  RC=$?
  echo "[$(stamp)] chunk $K end rc=$RC: $(tail -1 $LOG/chunk-$K.attempt-$ATTEMPT.log)"
  echo $RC > $LOG/chunk-$K.attempt-$ATTEMPT.rc
  [ "$(git rev-parse HEAD:aisef2)" = "$KT" ] || echo "[$(stamp)] STOP: the kernel tree changed during chunk $K"
}
running() { local n=0; for P in $PIDS; do kill -0 $P 2>/dev/null && n=$((n + 1)); done; echo $n; }   # chunk workers alive, by pid (a script has no job table)
PIDS=()
for K in $(seq 0 9); do
  while [ $(running) -ge $W ]; do sleep 5; done
  run_chunk $K &
  PIDS+=($!)
done
for P in $PIDS; do wait $P; done
touch $LOG/monitor.stop; wait $MON
# 5. after the last trace: the kernel tree, the tree's cleanliness, F1-F11 and the V1 guard again
[ "$(git rev-parse HEAD:aisef2)" = "$KT" ] || { echo "STOP: the kernel tree changed during the run"; exit 3; }
python3 -P validation/qualification/q4_aggregate.py --conformance end || { echo "STOP: conformance at end"; exit 3; }
FAILS=$(cat $LOG/chunk-*.attempt-$ATTEMPT.rc | grep -vc '^0$' || true)
echo "[$(stamp)] chunks finished: $FAILS non-zero exit(s); aggregating"
python3 -P validation/qualification/q4_aggregate.py; RC=$?
echo "[$(stamp)] aggregation rc=$RC"
exit $RC
