"""B03-R3 conf: what the write clause of `confine._judge` at an earlier revision said of the reports the Linux guest
recorded, beside what the tree's says (decisions/B03-R3-conf.md §3).

    python3 -B validation/v21/sandbox/r3_conf_old_judge.py <revision> docs/v2.1/evidence/sandbox/r3-conf/scenarios-X1.json

The earlier `aisef2/app/confine.py` is read with `git show <revision>:aisef2/app/confine.py` and loaded under another
module name; its `_judge` is given each record's report as it is (the rows hold `at`, `access` and `fs`, which is all
that clause read). Nothing is written and nothing is run but git."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from aisef2.app import confine as new  # noqa: E402


def load_old(revision: str):
    text = subprocess.run(["git", "-C", str(ROOT), "show", f"{revision}:aisef2/app/confine.py"], capture_output=True,
                          text=True, check=True).stdout
    with tempfile.TemporaryDirectory() as t:
        path = pathlib.Path(t) / "old_confine.py"
        path.write_text(text, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("old_confine", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    revision, record = argv
    old = load_old(revision)
    scenarios = json.loads(pathlib.Path(record).read_text(encoding="utf-8"))["record"]
    for name, rec in sorted(scenarios.items()):
        rep = rec["report"]
        tries = {k: (v["exit"], v["output"]) for k, v in rep["tried"].items()}
        ws = pathlib.PurePosixPath(rec["workspace"])
        verdict = {}
        for label, module in (("old", old), ("new", new)):
            problems = module._judge(rep, "tok", "", tries, rec["home"], ws)
            refused = [p for p in problems if p.startswith(("writable outside", "cannot establish"))]
            verdict[label] = "refuses" if refused else "accepts"
        print(f"{name:28s} {revision[:7]}: {verdict['old']:8s} tree: {verdict['new']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
