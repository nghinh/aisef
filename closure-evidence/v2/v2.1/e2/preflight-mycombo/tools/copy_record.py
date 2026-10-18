"""Copy the probe record (as run, unedited; the secret scan found the key in none of it), the settings it ran with, the
tools and the listing extracts into the lane's worktree under closure-evidence/v2/v2.1/e2/. Prints each copy's sha256."""
import hashlib
import pathlib
import shutil

S = pathlib.Path(__file__).resolve().parent
E = pathlib.Path("/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/wf_830a4f0d-db8-1/closure-evidence/v2/v2.1/e2")
P = S / "preflight-mycombo"
plan = {
    "preflight-mycombo": [P / n for n in ("started.txt", "finished.txt", "exit.txt", "run.stdout", "run.stderr", "argv.json",
                                          "env-names.txt", "store-before.json", "store-after.json")] + [S / "probe-settings.json"],
    "preflight-mycombo/run": [P / "run" / n for n in ("RUN.json", "RUN.started.json", "EVIDENCE.json")],
    "preflight-mycombo/run/preflight": [P / "run/preflight" / n for n in ("PREFLIGHT.json", "LEDGER.jsonl")],
    "preflight-mycombo/tools": [S / n for n in ("run_probe.py", "build_calc.py", "gen_settings.py", "filter_listing.py",
                                                "filter_minimax.py", "inspect_record.py", "validate_settings.py", "copy_record.py")],
    "listing": [S / "listing" / n for n in ("models-mycombo.json", "models-minimax.json", "listing-http.txt", "listing-when.txt")],
}
renamed = {S / "stubbin/opencode": E / "preflight-mycombo/tools/stubbin-opencode.sh",
           S / "xdg/opencode/opencode.json": E / "preflight-mycombo/tools/xdg-opencode.json"}
for rel, files in plan.items():
    (E / rel).mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copyfile(f, E / rel / f.name)
for src, dst in renamed.items():
    shutil.copyfile(src, dst)
for p in sorted(E.rglob("*")):
    if p.is_file():
        print(hashlib.sha256(p.read_bytes()).hexdigest()[:16], p.relative_to(E).as_posix())
