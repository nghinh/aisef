#!/opt/homebrew/bin/python3 -P -B
"""The E2 dry run's scripted client (installed by tools/dryrun.py setup as <scratch>/client/opencode, never under the
real client's install directories). It answers `opencode run --format json --model M --title T --dir D PROMPT` the way
the kernel reads a session (one text event, one step_finish with tokens) and `--version`; it never opens a socket.

A developer session copies the workload's reference tree (<this dir>/ref/<workload>/<story>/, a copy of
closure-evidence/v2/v2.1/e2/dry-run/reference/) into --dir: `developer <story>` copies that story's slice (the
kernel's sessions, one story at a time), `developer direct` copies every story's slice in order (the direct arm's one
session). The workload is detected from the files present (treesum/ -> w1, infrastructure/ci/evidence_discipline.py ->
w2). With AISEF_DRYRUN_WRONG=<story> the slice ref/<workload>/wrong-<story>/ is copied over that story's: a deliberate
defect, so an escaped defect (direct) and a rollback (aisef arms) appear in the records. A reviewer session answers
{"findings": []}. Nothing here reads the prompt."""
import json
import os
import pathlib
import shutil
import sys

argv = sys.argv[1:]
if argv == ["--version"]:
    print("0.0.0-dry-run-fake")
    raise SystemExit(0)
title, cwd = argv[argv.index("--title") + 1], pathlib.Path(argv[argv.index("--dir") + 1])
REF = pathlib.Path(__file__).resolve().parent / "ref"
WRONG = os.environ.get("AISEF_DRYRUN_WRONG", "")
role, _, story = title.partition(" ")


def copy_tree(src: pathlib.Path) -> None:
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        dst = cwd / f.relative_to(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dst)


text = "done"
if role == "developer":
    w = "w1" if (cwd / "treesum").is_dir() else "w2" if (cwd / "infrastructure" / "ci" / "evidence_discipline.py").is_file() else None
    if w is None:
        print(json.dumps({"type": "text", "part": {"text": "fake client: unknown workload in " + str(cwd)}}))
        raise SystemExit(1)
    stories = sorted(p.name for p in (REF / w).iterdir() if p.is_dir() and p.name.startswith("S"))
    for s in stories if story == "direct" else [story]:
        copy_tree(REF / w / s)
        if s == WRONG and (REF / w / f"wrong-{s}").is_dir():
            copy_tree(REF / w / f"wrong-{s}")
    text = f"wrote {w} {'/'.join(stories if story == 'direct' else [story])}" + (f" (wrong: {WRONG})" if WRONG else "")
elif role == "reviewer":
    text = '{"findings": []}'
print(json.dumps({"type": "text", "part": {"text": text}}))
print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 120, "output": 7, "reasoning": 3,
                                                             "cache": {"read": 10, "write": 0}}}}))
