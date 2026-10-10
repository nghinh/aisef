"""end_record.py REPO C ACCOUNT OUT: campaign 2's end record and its evidence pack, from the run's own files.

Writes OUT/ (closure-evidence/v2/v2.1/campaign-2/results): xz copies of the merged record, the four worker records and
logs, progress and disk logs, a tar.xz of the owned_run records; the store before/after snapshots; the runner's
--check output; ACCOUNT.json; CAMPAIGN-2-END.json with every file's sha256 (and its uncompressed sha256)."""
import datetime, hashlib, json, lzma, pathlib, sys, tarfile

repo, C, A, out = (pathlib.Path(a) for a in sys.argv[1:5])
out.mkdir(parents=True, exist_ok=True)
sha = lambda b: hashlib.sha256(b).hexdigest()
files = {}


def put(src, name, compress):
    raw = src.read_bytes()
    data = lzma.compress(raw, preset=6) if compress else raw
    (out / name).write_bytes(data)
    files[name] = {"sha256": sha(data), "bytes": len(data)} | ({"uncompressed_sha256": sha(raw), "uncompressed_bytes": len(raw)}
                                                              if compress else {})


put(A / "MUTATION.json", "MUTATION.json.xz", True)
for w in range(1, 5):
    put(C / f"c2-w{w}.record.json", f"c2-w{w}.record.json.xz", True)
    put(C / f"c2-w{w}.log", f"c2-w{w}.log.xz", True)
for name in ("progress.log", "disk.log"):
    put(C / name, name + ".xz", True)
for name in ("store-before.json", "store-after.json", "store-after.at"):
    put(C / name, name, False)
put(A / "check.out", "check.out", False)
put(A / "ACCOUNT.json", "ACCOUNT.json", False)
owned = sorted((C / "owned").glob("*.json"))
with tarfile.open(out / "owned.tar.xz", "w:xz") as t:
    for f in owned:
        t.add(f, arcname=f"owned/{f.name}")
files["owned.tar.xz"] = {"sha256": sha((out / "owned.tar.xz").read_bytes()), "bytes": (out / "owned.tar.xz").stat().st_size}

acc = json.loads((A / "ACCOUNT.json").read_text(encoding="utf-8"))
rec = json.loads((A / "MUTATION.json").read_text(encoding="utf-8"))
unclassified = [{"target": t["target"], "mutant": r["mutant"], "class": r["class"],
                 "files": [f["file"] for f in r["files"] if "role" not in f and f["outcome"] not in ("PASS", "FAIL")]}
                for t in rec["targets"] for r in t["results"] if r.get("class") not in ("KILLED", "SURVIVED")]
own = [json.loads(f.read_text(encoding="utf-8")) for f in owned]
check = (A / "check.out").read_text(encoding="utf-8").splitlines()
before = json.loads((C / "store-before.json").read_text()); after = json.loads((C / "store-after.json").read_text())
ended = datetime.datetime.fromtimestamp((C / "campaign.done").stat().st_mtime, datetime.timezone.utc)
started = datetime.datetime.fromisoformat((C / "campaign.started").read_text().strip().replace("Z", "+00:00"))
end = {
    "record": "AISEF V2.1 — CAMPAIGN 2 END (B-03b)",
    "snapshot": json.loads((repo / "closure-evidence/v2/v2.1/campaign-2/CAMPAIGN-2-START.json").read_text())["snapshot"],
    "started": started.isoformat().replace("+00:00", "Z"), "ended": ended.isoformat(timespec="seconds").replace("+00:00", "Z"),
    "wall_hours": round((ended - started).total_seconds() / 3600, 2),
    "targets": acc["targets_with_a_result"], "manifest_targets": acc["manifest_targets"],
    "mutants": acc["mutants_classified"], "manifest_mutants": acc["manifest_mutants"], "classes": acc["classes"],
    "from": acc["from"], "merge_problems": acc["problems"],
    "unclassified": unclassified,
    "check_at_snapshot": {"how": "campaign-2/tools/check_at_snapshot.sh: the merged record copied into a fresh detached "
                                 "worktree at the snapshot, `mutation.py --check` under env -i (PATH without opencode)",
                          "exit": int(check[-1].split()[-1]),
                          "unaudited_survivors": sum("unaudited survivor" in l for l in check),
                          "unclassified_lines": sum("neither killed nor survived" in l for l in check),
                          "other_failures": [l for l in check if l.startswith("FAIL") and "unaudited survivor" not in l
                                             and "neither killed nor survived" not in l]},
    "ownership": {"runs": len(own), "escaped": sum(len(o["escaped"]) for o in own),
                  "released_empty": sum(bool(o["released_empty"]) for o in own),
                  "harness_orphans_after": sum(o["harness_orphans_after"] for o in own)},
    "operator_store": {"changed": sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)),
                       "why": "store_stat.py (os.stat only) — the after snapshot was taken at store-after.at with the "
                              "committed isolation/tools/store_stat.py (same sha256 as release/s5-rc2's) because the "
                              "scratch copy the driver called had been removed by the host's /tmp cleanup; the two "
                              "changes are the operator's OpenCode desktop app (pid 9792, running throughout): its log "
                              "(run a7141900, projects harness/devsecops) and its tool-output pruning at 2026-10-10 "
                              "09:00:01 +07; opencode.db, -wal, -shm, auth.json and opencode.json unchanged"},
    "files": files,
    "notes": "results/NOTES.md (what happened during the run: monitor defect, TIMEOUTs, the temp-path INFRA, disk/swap)",
}
(out / "CAMPAIGN-2-END.json").write_text(json.dumps(end, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: end[k] for k in ("started", "ended", "wall_hours", "targets", "mutants", "classes", "check_at_snapshot",
                                      "ownership")} | {"unclassified": len(unclassified), "operator_store": end["operator_store"]["changed"]},
                 ensure_ascii=False, indent=1))
