"""validation/v2/execution_order.py: the execution-order table is derived by its rule from a committed T0 sweep record,
and --check re-derives it (docs/v2.1/MUTATION-RUNNER-V2.md §7.2). Fixture: tests/v2/fixtures/execution_order/ — a toy
module and five rows in the sweep's own JSONL format (one for an earlier version of the module, one T0 FAIL)."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import execution_order as eo  # noqa: E402
from validation.v2 import mutation as m  # noqa: E402

FIXTURE = ROOT / "tests/v2/fixtures/execution_order"
A, B, C, D, E = (f"tests/v2/test_{x}.py" for x in "abcde")
TARGETS = {"aisef2/toy.py::f": [A, B, C], "aisef2/toy.py::g": [C, A], "aisef2/toy.py::h": [A, D, E]}
MEASURED_ON = "0123456789abcdef0123456789abcdef01234567"


def git(cwd: pathlib.Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", env=env,
                          check=True).stdout.strip()


class Table(unittest.TestCase):
    def setUp(self):
        self.root = root = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory())).resolve() / "repo"
        (root / "aisef2").mkdir(parents=True)
        (root / "evidence").mkdir()
        shutil.copy(FIXTURE / "toy.py", root / "aisef2/toy.py")
        git(root, "init", "-q", "-b", "main")
        self.enterContext(mock.patch.object(eo, "ROOT", root))
        self.enterContext(mock.patch.object(m, "V21_TARGETS", TARGETS))
        self.enterContext(mock.patch("builtins.print"))
        self.sweep, self.table = root / "evidence/T0-SWEEP.json", root / "order.json"

    def commit(self, *paths: str) -> str:
        git(self.root, "add", *paths)
        git(self.root, "commit", "-q", "-m", "x")
        return git(self.root, "rev-parse", "HEAD")

    def test_the_sweep_s_jsonl_becomes_its_record_unchanged_and_never_replaced(self):
        lines = (FIXTURE / "t0-sweep.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(eo.main(["--record", str(FIXTURE / "t0-sweep.jsonl"), MEASURED_ON, str(self.sweep)]), 0)
        rec = json.loads(self.sweep.read_text(encoding="utf-8"))
        self.assertEqual((rec["measured_on"], rec["rows"]), (MEASURED_ON, [json.loads(x) for x in lines]))
        with self.assertRaises(FileExistsError):
            eo.main(["--record", str(FIXTURE / "t0-sweep.jsonl"), MEASURED_ON, str(self.sweep)])
        with self.assertRaisesRegex(SystemExit, "MEASURED_ON must be a full commit id"):
            eo.main(["--record", str(FIXTURE / "t0-sweep.jsonl"), "33f4012", str(self.root / "other.json")])
        self.assertFalse((self.root / "other.json").exists())

    def test_the_table_follows_the_rule_from_a_committed_record_and_check_re_derives_it(self):
        eo.main(["--record", str(FIXTURE / "t0-sweep.jsonl"), MEASURED_ON, str(self.sweep)])
        with self.assertRaisesRegex(SystemExit, "evidence/T0-SWEEP.json is not a file committed at HEAD"):
            eo.main(["--write", str(self.sweep), str(self.table)])
        self.assertFalse(self.table.exists())
        self.commit("aisef2/toy.py", "evidence/T0-SWEEP.json")
        self.assertEqual(eo.main(["--write", str(self.sweep), str(self.table)]), 0)
        doc = json.loads(self.table.read_text(encoding="utf-8"))
        src = {"path": "evidence/T0-SWEEP.json", "sha256": hashlib.sha256(self.sweep.read_bytes()).hexdigest()}
        null = hashlib.sha256(m.null_mutant((self.root / "aisef2/toy.py").read_text(encoding="utf-8"), "f").encode())
        self.assertEqual((doc["rule"], doc["from"]), (eo.RULE, {**src, "measured_on": MEASURED_ON}))
        self.assertEqual(doc["orders"], {   # B is fastest; A and C tie at 3.0 s and keep their declared positions
            "aisef2/toy.py::f": {"files": [B, A, C], "seconds": [1.5, 3.0, 3.0], "from": src},
            "aisef2/toy.py::g": {"files": [C, A], "seconds": [3.0, 3.0], "from": src}})   # the earlier module's 0.1 s C row is not read
        self.assertEqual(doc["declared_order"], {   # D was never measured; E's T0 failed
            "aisef2/toy.py::h": f"no PASS T0 row on its null mutant {null.hexdigest()[:16]} for {[D, E]}"})
        self.assertEqual([m._order_problem(x, TARGETS[t]) for t, x in doc["orders"].items()], [None, None])   # main runs it
        self.assertEqual(eo.main(["--check", str(self.table)]), 0)

        tampered = {**doc, "orders": {**doc["orders"], "aisef2/toy.py::f": {**doc["orders"]["aisef2/toy.py::f"], "files": [A, B, C]}}}
        self.table.write_text(eo.render(tampered), encoding="utf-8")
        self.assertEqual(eo.check(self.table), [f"{self.table} is not what evidence/T0-SWEEP.json derives now — re-run --write"])
        eo.main(["--write", str(self.sweep), str(self.table)])

        rec = json.loads(self.sweep.read_text(encoding="utf-8"))   # a new measurement: B is now the slowest
        rec["rows"][1]["rows"][0]["seconds"] = 9.0
        self.sweep.write_text(eo.render(rec), encoding="utf-8")
        self.assertEqual(eo.check(self.table), ["evidence/T0-SWEEP.json is not a file committed at HEAD: the table is "
                                                "derived from a committed record only"])
        self.commit("evidence/T0-SWEEP.json")
        self.assertEqual(eo.check(self.table), [f"{self.table} is not what evidence/T0-SWEEP.json derives now — re-run --write"])
        eo.main(["--write", str(self.sweep), str(self.table)])
        self.assertEqual(json.loads(self.table.read_text(encoding="utf-8"))["orders"]["aisef2/toy.py::f"]["files"], [A, C, B])
        self.assertEqual(eo.check(self.table), [])

        (self.root / "aisef2/toy.py").write_text("def f(x):\n    return x + 2\n", encoding="utf-8")   # other bytes
        self.assertEqual(eo.table(self.root, "evidence/T0-SWEEP.json")["orders"], {})   # no row measured these
        self.table.write_text("[]", encoding="utf-8")
        self.assertRegex(eo.check(self.table)[0], "or its sweep record cannot be read")

    def test_the_runner_s_committed_reads_head_s_bytes_only(self):
        self.table.write_bytes(b"{}\n")   # exact bytes: committed() compares blobs, and write_text CRLFs \n on Windows
        self.assertEqual(m.committed(self.root, self.table, b"{}\n"), ("order.json", None))   # untracked
        head = self.commit("order.json")
        self.assertEqual(m.committed(self.root, self.table, b"{}\n"), ("order.json", head))
        self.assertEqual(m.committed(self.root, self.table, b"{ }\n"), ("order.json", None))   # not HEAD's bytes
        outside = self.root.parent / "order.json"
        self.assertEqual(m.committed(self.root, outside, b"{}\n"), (str(outside), None))
        shutil.copy(self.root / "aisef2/toy.py", self.root / "toy.py")   # HEAD:toy.py has aisef2/toy.py's bytes
        self.commit("toy.py", "aisef2/toy.py")
        raw = (self.root / "aisef2/toy.py").read_bytes()
        self.assertEqual(m.committed(self.root, self.root / "aisef2/toy.py", raw)[0], "aisef2/toy.py")
        self.assertEqual(m.committed(self.root / "aisef2", self.root / "aisef2/toy.py", raw), ("toy.py", None))   # not the top


if __name__ == "__main__":
    unittest.main()
