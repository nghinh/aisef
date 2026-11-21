"""L1-QUAL (W1-DESIGN §3, §7; CODE-AUDIT #104, #3): the shipped calibration rows and the record the release cites are
bound to their inputs, mechanically.

#104 (a): the shipped identity tuples (`aisef2/app/calibrations.py`) equal the tuples derived from the catalog in BOTH
directions. Red-before: `tests/v2/test_v21_identity_bytes.py` checks one direction only, so an extra hand-added row
passes it; the two-way check fails on it.
#104 (b) / #3: `release_calibration.resolve()` binds each row to its fixture-tree sha256: one negative fixture byte
reports that row INVALIDATED (and no other), with `calibrations.py` byte-unchanged; a tampered record, a changed
`calibrations.py`, an uncommitted or rewritten v2.3 record, a dirty-tree record and a repository without the v2.2.0
commit never resolve as current. `--write` re-demonstrates, appends a v2.3 record and leaves `calibrations.py` alone
when its rows do not change; once committed that record is MEASURED.

Every case that edits a file does it in a throwaway clone of this repository (objects shared read-only, only the data
`resolve()` reads checked out); the real tree is never written. Evidence: docs/v2.3/evidence/l1-qual/README.md.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
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

from validation.qualification import release_calibration as rc  # noqa: E402

DATA = ("closure-evidence/v2/release/", "tests/v2/fixtures/calibration/", "aisef2/app/calibrations.py", "pyproject.toml",
        ".gitignore")
V220 = "closure-evidence/v2/release/V2.2.0-PROBE-CALIBRATIONS.json"
NEG = "tests/v2/fixtures/calibration/file_artifact/exists/negative/checkout/app/other.toml"


def _git(cwd: pathlib.Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, encoding="utf-8", check=True,
                          env={**os.environ, **(env or {})}).stdout.strip()


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def data_clone():
    """A throwaway clone of this repository at HEAD (`--shared`: objects read, never written), with only the data
    resolve() reads checked out; release_calibration.ROOT points at it while the context lasts."""
    head = _git(ROOT, "rev-parse", "HEAD")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        t = pathlib.Path(tmp) / "clone"
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(ROOT), str(t)], check=True, capture_output=True)
        _git(t, "sparse-checkout", "set", "--no-cone", *("/" + p for p in DATA))
        _git(t, "checkout", "-q", "--detach", head)
        with mock.patch.object(rc, "ROOT", t):
            yield t


def commit(t: pathlib.Path) -> str:
    """Commit the clone's working tree with plumbing only (no hook, no signing, no config of the user's)."""
    _git(t, "add", "-A")
    who = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    sha = _git(t, "commit-tree", "--no-gpg-sign", _git(t, "write-tree"), "-p", "HEAD", "-m", "test", env=who)
    _git(t, "update-ref", "HEAD", sha)
    return sha


def two_way(shipped: list, derived: list) -> list[str]:
    """#104 (a): the shipped tuples are the derived ones, both directions, no duplicate."""
    out = [f"shipped, not derived: {r[:3]}" for r in shipped if r not in derived]
    out += [f"derived, not shipped: {r[:3]}" for r in derived if r not in shipped]
    return out + (["a shipped row is duplicated"] if len(set(shipped)) != len(shipped) else [])


class ShippedRows(unittest.TestCase):
    def test_the_shipped_rows_are_the_catalog_s_in_both_directions(self):
        self.assertEqual(two_way(rc.shipped_rows(), rc.derived_rows()), [])
        self.assertEqual(len(rc.shipped_rows()), 19)

    def test_red_before_an_extra_hand_added_row_passes_the_one_way_test_and_fails_the_two_way_check(self):
        from aisef2.app.calibrations import CALIBRATIONS
        from tests.v2 import test_v21_identity_bytes as old
        extra = {**CALIBRATIONS[0], "observation_class": "hand_added"}
        with mock.patch.object(old, "CALIBRATIONS", (*CALIBRATIONS, extra)):
            run = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(unittest.defaultTestLoader.loadTestsFromName(
                "tests.v2.test_v21_identity_bytes.ThreeIdentities.test_the_shipped_calibrations_name_every_class_at_the_bytes_that_run_now"))
        self.assertTrue(run.wasSuccessful() and run.testsRun == 1)                     # red-before: the old test passes
        with data_clone() as t:
            p = t / rc.SHIPPED_REL
            p.write_text(p.read_text(encoding="utf-8").replace("CALIBRATIONS = (\n", "CALIBRATIONS = (\n    "
                                                                 + json.dumps(extra, sort_keys=True) + ",\n"), encoding="utf-8")
            self.assertEqual(two_way(rc.shipped_rows(), rc.derived_rows()), ["shipped, not derived: ('probe.file_artifact', "
                                                                             f"'{extra['probe_digest']}', 'hand_added')"])
            rel, state, basis = rc.resolve()
            self.assertEqual((rel, state), (V220, "INVALIDATED"))
            self.assertIn(f"probe.file_artifact hand_added: in {rc.SHIPPED_REL}, not in the record", basis)


class Resolve(unittest.TestCase):
    def test_this_tree_cites_the_v2_2_0_record_by_identity_never_as_measured(self):
        self.assertEqual(rc.resolve(), (V220, "VERIFIED_REUSE", "identical-inputs:V2.2.0"))
        self.assertEqual((rc.RECORD_REL, rc.STATE, rc.BASIS), rc.resolve())
        self.assertEqual(rc.state_problems(), [])
        from validation.v23 import impact
        self.assertEqual((rc.STATES, rc.BASE), (impact.STATES, impact.BASE))

    def test_one_negative_fixture_byte_invalidates_that_row_only_and_calibrations_py_is_untouched(self):
        with data_clone() as t:
            shipped = _sha(t / rc.SHIPPED_REL)
            with open(t / NEG, "ab") as f:
                f.write(b"#")
            rel, state, basis = rc.resolve()
            self.assertEqual((rel, state), (V220, "INVALIDATED"))
            self.assertEqual(basis.split("; "), [basis])                               # exactly one reason ...
            self.assertTrue(basis.startswith("probe.file_artifact exists: the negative fixture tree is not the record's"), basis)
            self.assertEqual(_sha(t / rc.SHIPPED_REL), shipped)                         # ... and the kernel unchanged
            with mock.patch.multiple(rc, RECORD_REL=rel, STATE=state, BASIS=basis):
                self.assertEqual(rc.state_problems(), [f"{rel}: INVALIDATED — {basis}"])

    def test_a_record_or_calibrations_py_changed_never_resolves_as_current(self):
        cases = {
            # a tamper that makes the record agree with a changed fixture: refused by the v2.2.0 bytes, not by the digest
            "tampered to match": ("record", lambda d, t: d["fixtures"]["tests/v2/fixtures/calibration/file_artifact/exists"]
                                  .update(negative=rc._sha_tree(t / NEG.rsplit("/checkout", 1)[0])),
                                  f"{V220} differs from its committed bytes at v2.2.0"),
            "a row's digest": ("record", lambda d, t: d["rows"][0].update(probe_digest="0" * 64),
                               f"{V220} differs from its committed bytes at v2.2.0"),
            "calibrations.py": ("shipped", None, f"probe.file_artifact exists: in the record, not in {rc.SHIPPED_REL}"),
        }
        for name, (what, change, why) in cases.items():
            with self.subTest(name), data_clone() as t:
                with open(t / NEG, "ab") as f:
                    f.write(b"#")
                if what == "record":
                    d = json.loads((t / V220).read_text(encoding="utf-8"))
                    change(d, t)
                    (t / V220).write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
                else:
                    p = t / rc.SHIPPED_REL
                    p.write_text(p.read_text(encoding="utf-8").replace('"probe_digest": "dcdfe80e', '"probe_digest": "0cdfe80e', 1),
                                 encoding="utf-8")
                rel, state, basis = rc.resolve()
                self.assertEqual((rel, state), (V220, "INVALIDATED"))
                self.assertIn(why, basis)

    def test_without_the_v2_2_0_commit_nothing_resolves(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rc, "ROOT", pathlib.Path(tmp)):
            for p in DATA:                                       # the same data, outside any repository
                src, dst = ROOT / p, pathlib.Path(tmp) / p
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, dst) if src.is_dir() else shutil.copyfile(src, dst)
            self.assertEqual(rc.resolve()[1:], ("UNRESOLVED", "basis v2.2.0 is not in this repository (shallow clone or no git)"))
        self.assertEqual(rc.resolve("2.2.0rc1")[1], "UNRESOLVED")
        self.assertEqual(rc.resolve("1.9.0")[1:], ("UNRESOLVED", "no calibration record of a version <= 1.9.0"))

    def test_a_v2_3_record_is_measured_only_committed_once_and_from_a_clean_tree(self):
        with data_clone() as t:
            new = "closure-evidence/v2/release/V2.2.0-PROBE-CALIBRATIONS-2.json"
            d, head = json.loads((t / V220).read_text(encoding="utf-8")), _git(t, "rev-parse", "HEAD")
            uncommitted = (new, "UNRESOLVED", f"{new} is not committed (a v2.3 record counts once committed)")
            d["identity"] = {"round": "v2.3", "measured_on": head, "dirty": True}
            (t / new).write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            self.assertEqual(rc.resolve(), uncommitted)
            commit(t)
            self.assertEqual(rc.resolve(), (new, "UNRESOLVED", f"{new} was written from a dirty tree"))
            _git(t, "reset", "-q", "--hard", head)
            d["identity"]["dirty"] = False
            (t / new).write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            self.assertEqual(rc.resolve(), uncommitted)
            commit(t)
            self.assertEqual(rc.resolve(), (new, "MEASURED", f"v2.3-measured@{head}"))
            (t / new).write_text((t / new).read_text(encoding="utf-8") + " ", encoding="utf-8")
            self.assertEqual(rc.resolve(), (new, "INVALIDATED", f"{new} differs from its committed bytes at HEAD"))
            commit(t)
            self.assertEqual(rc.resolve(), (new, "INVALIDATED", f"{new} was rewritten after it was committed (a record is written once)"))


class Write(unittest.TestCase):
    def test_write_writes_nothing_while_the_record_is_current(self):
        with data_clone() as t, mock.patch.object(rc, "calibrate_all", side_effect=AssertionError("re-demonstrated")):
            def files():
                return {str(p.relative_to(t)): _sha(p) for p in t.rglob("*") if p.is_file() and ".git" not in p.relative_to(t).parts}
            before = files()
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(rc.main(["--write"]), 0)
            self.assertIn("VERIFIED_REUSE (identical-inputs:V2.2.0) — nothing written", out.getvalue())
            self.assertEqual(files(), before)

    def test_an_invalidated_record_is_re_demonstrated_into_a_new_v2_3_record_and_the_kernel_is_left_alone(self):
        with data_clone() as t:
            shipped = _sha(t / rc.SHIPPED_REL)
            with open(t / NEG, "ab") as f:
                f.write(b"# still not app/config.toml\n")
            commit(t)                                                                   # a committed fixture change
            self.assertEqual(rc.resolve()[1], "INVALIDATED")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(rc.main(["--write"]), 0)
            new = "closure-evidence/v2/release/V2.2.0-PROBE-CALIBRATIONS-2.json"
            self.assertIn(f"wrote {new}; {rc.SHIPPED_REL} unchanged (same rows)", out.getvalue())
            self.assertEqual(_sha(t / rc.SHIPPED_REL), shipped)
            doc = json.loads((t / new).read_text(encoding="utf-8"))
            self.assertEqual((doc["verdict"], doc["identity"]["round"], doc["identity"]["dirty"], doc["identity"]["supersedes"]["state"]),
                             ("CALIBRATED", "v2.3", False, "INVALIDATED"))
            self.assertEqual(rc.resolve()[1], "UNRESOLVED")                              # not committed yet
            commit(t)
            self.assertEqual(rc.resolve(), (new, "MEASURED", f"v2.3-measured@{doc['identity']['measured_on']}"))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rc.main(["--write"]), 0)                               # current again: nothing written
            self.assertFalse((t / "closure-evidence/v2/release/V2.2.0-PROBE-CALIBRATIONS-3.json").exists())


if __name__ == "__main__":
    unittest.main()
