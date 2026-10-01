"""SS-81 family, owner section 5 — qualify the nop/baseline collection strategy on the REAL managed Python image.

The kernel appends `--continue-on-collection-errors` to a pytest control run so one file's import error cannot hide
every other file's tests. That is not assumed to work: this runs the kernel's own `run_tool` sandbox path in the pinned
image (pytest 9.1.1, non-root, no network), on a project whose file A cannot import the story's module at the parent
and whose file B holds a tautological criterion test, and records what the proof model concludes — with the strategy
and, as the control, without it. No model call.

    python3 validation/collection_strategy_qualification.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aisef.config import DEFAULTS, Config                                    # noqa: E402
from aisef.control import proof                                             # noqa: E402
from aisef.harness import capabilities, tools                               # noqa: E402
from aisef.harness.testlog import parse                                     # noqa: E402

OUT = ROOT / "closure-evidence/hardening/w1/ss81/COLLECTION-STRATEGY-QUALIFICATION.json"
A = "tests/test_a.py::test_AC_S_01_1_x"
B = "tests/test_b.py::test_AC_S_01_2_y"


def main() -> int:
    image = capabilities.profile_by_stack("python").image
    cmd = "python -m pytest -v -p no:cacheprovider"
    cfg = Config({**DEFAULTS, "tools.test": cmd, "sandbox.image": image, "sandbox.use_docker": True})
    rows = {}
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        (proj / "tests").mkdir()
        (proj / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n', encoding="utf-8")
        (proj / "tests/test_a.py").write_text("from src.a import f          # src/a.py: this story's, absent at the parent\n\n"
                                              "def test_AC_S_01_1_x():\n    assert f() == 1\n", encoding="utf-8")
        (proj / "tests/test_b.py").write_text("def test_AC_S_01_2_y():\n    assert True                 # verifies nothing\n",
                                              encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
        for label, extra in (("with_strategy", tools.collection_continuation_args(cmd)), ("runner_default", [])):
            res = tools.run_tool("test", proj, config=cfg, extra_args=extra)
            rec = parse(res.stdout + "\n" + res.stderr).to_evidence()
            rec["unrunnable"] = res.unrunnable
            states = proof.classify(rec, [A, B], ["src/a.py"], added=["src/a.py"])
            green = [t for t, (p, _) in states.items() if p is proof.Proof.GREEN_EXECUTED]
            rows[label] = {"extra_args": extra, "exit": res.exit_code, "collection_aborted": rec["collection_aborted"],
                           "output_complete": rec["output_complete"], "collection_errors": rec["collection_errors"],
                           "test_ids": rec["test_ids"],
                           "states": {t: {"state": p.value, "why": w} for t, (p, w) in states.items()},
                           "control_verdict": "FAILED (tautology observed green)" if green else
                                              ("PASSED" if all(p in proof.PROVES_RED for p, _ in states.values()) else "UNRUNNABLE (no proof)"),
                           "tail": "\n".join((res.stdout + res.stderr).strip().splitlines()[-6:])}
        ver = subprocess.run(["docker", "run", "--rm", image, "python", "-m", "pytest", "--version"],
                             capture_output=True, text=True).stdout.strip() or "?"
    w, d = rows["with_strategy"], rows["runner_default"]
    req = {
        "strategy_is_the_flag_the_kernel_appends": w["extra_args"] == [tools.PYTEST_CONTINUE],
        "file_b_executes_although_file_a_fails_to_collect": B in w["test_ids"] and not w["collection_aborted"],
        "tautology_observed_green_and_control_fails": w["states"][B]["state"] == "GREEN_EXECUTED" and w["control_verdict"].startswith("FAILED"),
        "file_a_bound_to_the_story_only": w["states"][A]["state"] == "RED_COLLECTION_BOUND_TO_STORY",
        "every_ac_has_an_explicit_state": set(w["states"]) == {A, B},
        "control_without_strategy_aborts_and_proves_nothing": d["collection_aborted"] and d["states"][B]["state"] == "COLLECTION_ABORTED"
                                                              and not d["control_verdict"].startswith("PASSED"),
    }
    rec = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "image": image,
           "image_id": subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip(),
           "pytest_in_image": ver, "command": cmd, "runs": rows, "requirements": req, "pass": all(req.values())}
    OUT.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    for k, v in req.items():
        print(("ok " if v else "!! ") + k)
    print("collection strategy qualified:", rec["pass"], "|", ver, "|", image)
    return 0 if rec["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
