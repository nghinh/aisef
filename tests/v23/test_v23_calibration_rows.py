"""L1-QUAL (W1-DESIGN §3, §7; CODE-AUDIT #104, #3): the shipped calibration rows and the record the release cites are
bound to their inputs, mechanically.

#104 (a): the shipped identity tuples (`aisef2/app/calibrations.py`) equal the tuples derived from the catalog in BOTH
directions. Red-before: `tests/v2/test_v21_identity_bytes.py` checks one direction only, so an extra hand-added row
passes it; the two-way check fails on it.
#104 (b) / #3: `release_calibration.resolve()` binds each row to its fixture-tree sha256: one negative fixture byte
reports that row INVALIDATED (and no other), with `calibrations.py` byte-unchanged; a tampered record, a changed
`calibrations.py`, an uncommitted or rewritten v2.3 record, a dirty-tree record and a repository without the v2.2.0
commit never resolve as current. `--write` re-demonstrates only the rows whose inputs changed, carries the others
from the cited record, appends a v2.3 record and leaves `calibrations.py` alone when its rows do not change; once
committed that record is VERIFIED_REUSE (it carries rows), or MEASURED when every row was demonstrated in it.
L1Q-R1: the fixture-tree sha256 is the record's under POSIX and Windows Path order. L1Q-R3: the v2.3 round label is
never enough for MEASURED (a relabelled v2.2 record is INVALIDATED).

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
FIXTURES = "tests/v2/fixtures/calibration"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import release_calibration as rc  # noqa: E402

GEN = "validation/qualification/release_calibration.py"
DATA = ("closure-evidence/v2/release/", "tests/v2/fixtures/calibration/", "aisef2/app/calibrations.py", "pyproject.toml",
        ".gitignore", GEN)
V220 = "closure-evidence/v2/release/V2.2.0-PROBE-CALIBRATIONS.json"
NEW = "closure-evidence/v2/release/V2.2.0-PROBE-CALIBRATIONS-2.json"
EXISTS = "tests/v2/fixtures/calibration/file_artifact/exists"
NEG = f"{EXISTS}/negative/checkout/app/other.toml"


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


def pin_generator(t: pathlib.Path) -> str:
    """Commit the writer that runs (this tree's release_calibration.py) into the clone, as a maintainer commits it
    before `--write`; the commit is the record's measured_on."""
    (t / GEN).write_bytes((ROOT / GEN).read_bytes())
    return commit(t)


@contextlib.contextmanager
def counted_calibrations():
    """Every calibrate() call `calibrate_all` makes, as (probe id, class)."""
    from aisef2.probe import calibration
    calls, real = [], calibration.calibrate

    def counting(probe, cls, *a, **k):
        calls.append((probe.id, cls))
        return real(probe, cls, *a, **k)
    with mock.patch.object(calibration, "calibrate", counting):
        yield calls


class Ordered:
    """A real path that compares as `flavour` does: what sorted() over the platform's own Path objects gives."""

    def __init__(self, path: pathlib.Path, flavour):
        self.path, self.key = path, flavour(path.as_posix())

    def __lt__(self, other):
        return self.key < other.key

    def __getattr__(self, name):
        return getattr(self.path, name)


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


class FixtureTreeOrder(unittest.TestCase):
    def test_every_fixture_tree_has_the_record_s_sha_under_posix_and_windows_path_order(self):
        """L1Q-R1 red-before: `_sha_tree` walked sorted(Path objects); WindowsPath compares case-folded, so grep_count's
        NOTES.md and main.py swap and the v2.2.0 record resolved INVALIDATED on the Windows unit leg. The walk is ordered
        by the relative path's parts (case-sensitive: the order every v2.2 sha was written in) on every platform."""
        app = ROOT / FIXTURES / "file_artifact/grep_count/positive/checkout/app"
        names = sorted(p.name for p in app.iterdir())
        self.assertNotEqual(sorted(names, key=pathlib.PurePosixPath), sorted(names, key=pathlib.PureWindowsPath))
        fixtures = json.loads((ROOT / V220).read_text(encoding="utf-8"))["fixtures"]
        real = pathlib.Path.rglob
        for flavour in (pathlib.PurePosixPath, pathlib.PureWindowsPath):
            def rglob(self, *a, f=flavour, **k):
                return [Ordered(p, f) for p in real(self, *a, **k)]
            with self.subTest(flavour.__name__), mock.patch.object(pathlib.Path, "rglob", rglob):
                self.assertEqual({g: {s: rc._sha_tree(ROOT / g / s) for s in sides} for g, sides in fixtures.items()},
                                 fixtures)


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

    def test_a_v2_2_record_relabelled_v2_3_is_never_measured(self):
        """L1Q-R3 red-before: the round label was self-declared, so V2.2.0's bytes under a v2.3 identity, committed once
        from a clean tree, resolved MEASURED with no calibration run. MEASURED now needs this round's writer at
        measured_on (generator sha and its ROUND), measured_on's aisef2 tree, and measured_on an ancestor of the commit
        that added the record. The last case passes every check but the writer's round (v2.2.0's own writer and tree)."""
        cases = {
            "measured_on HEAD": ({"measured_on": "HEAD"}, f"the generator is not {GEN} at measured_on"),
            "no such commit": ({"measured_on": "0" * 40}, "measured_on '" + "0" * 40 + "' is not a commit"),
            "no measured_on": ({}, "measured_on None is not a commit"),
            "not a commit": ({"measured_on": "not-a-commit"}, "measured_on 'not-a-commit' is not a commit"),
            "v2.2.0's writer and tree": ({"measured_on": rc.BASE, "tree_of": rc.BASE}, f"{GEN} at measured_on is not the v2.3 writer"),
        }
        with data_clone() as t:
            head = _git(t, "rev-parse", "HEAD")
            for name, (identity, why) in cases.items():
                with self.subTest(name):
                    _git(t, "reset", "-q", "--hard", head)
                    d = json.loads((t / V220).read_text(encoding="utf-8"))
                    identity = {k: head if v == "HEAD" else v for k, v in identity.items()}
                    if "tree_of" in identity:
                        d["aisef2_tree"] = _git(t, "rev-parse", f"{identity.pop('tree_of')}:aisef2")
                    d["identity"] = {"round": "v2.3", "dirty": False, **identity}
                    (t / NEW).write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
                    commit(t)
                    rel, state, basis = rc.resolve()
                    self.assertEqual((rel, state), (NEW, "INVALIDATED"), basis)
                    self.assertIn(why, basis)

    def test_a_record_write_demonstrates_in_full_is_measured_only_committed_once_and_from_a_clean_tree(self):
        """A cited record with no trusted provenance carries nothing: --write demonstrates every class (2 calibrate()
        calls per row) and the record it writes is MEASURED once committed, never before, never dirty, never rewritten."""
        with data_clone() as t, counted_calibrations() as calls:
            head = pin_generator(t)
            with open(t / V220, "ab") as f:
                f.write(b" \n")                                     # not v2.2.0's bytes: nothing may be carried from it
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(rc.main(["--write"]), 0)
            self.assertIn(f"wrote {NEW} (19 re-demonstrated, 0 carried); {rc.SHIPPED_REL} unchanged", out.getvalue())
            self.assertEqual(len(calls), 2 * 19)
            _git(t, "checkout", "-q", "--", V220)
            good = (t / NEW).read_bytes()
            d = json.loads(good)
            self.assertEqual((d["identity"]["measured_on"], d["identity"]["carried"]), (head, []))
            uncommitted = (NEW, "UNRESOLVED", f"{NEW} is not committed (a v2.3 record counts once committed)")
            self.assertEqual(rc.resolve(), uncommitted)
            d["identity"]["dirty"] = True
            (t / NEW).write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            commit(t)
            self.assertEqual(rc.resolve(), (NEW, "UNRESOLVED", f"{NEW} was written from a dirty tree"))
            _git(t, "reset", "-q", "--hard", head)
            (t / NEW).write_bytes(good)
            self.assertEqual(rc.resolve(), uncommitted)
            commit(t)
            self.assertEqual(rc.resolve(), (NEW, "MEASURED", f"v2.3-measured@{head}"))
            (t / NEW).write_text((t / NEW).read_text(encoding="utf-8") + " ", encoding="utf-8")
            self.assertEqual(rc.resolve(), (NEW, "INVALIDATED", f"{NEW} differs from its committed bytes at HEAD"))
            commit(t)
            self.assertEqual(rc.resolve(), (NEW, "INVALIDATED", f"{NEW} was rewritten after it was committed (a record is written once)"))


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

    def test_one_changed_fixture_re_demonstrates_that_row_only_and_carries_the_others(self):
        """#104 (b) / L1Q-R4 red-before: --write re-demonstrated all 19 rows (38 calibrate() calls) for one changed
        fixture. Now exactly that row is demonstrated (its contrast, then (negative, negative) rejected); the other 18 are
        carried from the cited record, the new record names them and resolves VERIFIED_REUSE (reused verdicts are never
        MEASURED), and it stops being current when the record it carries from stops verifying."""
        with data_clone() as t, counted_calibrations() as calls:
            shipped = _sha(t / rc.SHIPPED_REL)
            with open(t / NEG, "ab") as f:
                f.write(b"# still not app/config.toml\n")
            head = pin_generator(t)                                                     # a committed fixture change
            self.assertEqual(rc.resolve()[1], "INVALIDATED")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(rc.main(["--write"]), 0)
            self.assertEqual(calls, [("probe.file_artifact", "exists")] * 2)
            self.assertIn(f"wrote {NEW} (1 re-demonstrated, 18 carried); {rc.SHIPPED_REL} unchanged (same rows)", out.getvalue())
            self.assertEqual(_sha(t / rc.SHIPPED_REL), shipped)
            doc, old = (json.loads((t / p).read_text(encoding="utf-8")) for p in (NEW, V220))
            self.assertEqual((doc["verdict"], doc["identity"]["round"], doc["identity"]["dirty"], doc["identity"]["supersedes"]["state"]),
                             ("CALIBRATED", "v2.3", False, "INVALIDATED"))
            self.assertEqual((doc["identity"]["measured_on"], doc["identity"]["supersedes"]["path"]), (head, V220))
            self.assertEqual(rc._rows(doc["rows"]), rc._rows(old["rows"]))
            self.assertEqual({g: v for g, v in doc["fixtures"].items() if g != EXISTS}, {g: v for g, v in old["fixtures"].items() if g != EXISTS})
            self.assertNotEqual(doc["fixtures"][EXISTS], old["fixtures"][EXISTS])
            carried = doc["identity"]["carried"]
            self.assertEqual((len(carried), ["probe.file_artifact", "exists"] in carried), (18, False))
            self.assertEqual(rc.resolve()[1], "UNRESOLVED")                              # not committed yet
            commit(t)
            self.assertEqual(rc.resolve(), (NEW, "VERIFIED_REUSE", f"v2.3-measured@{head}; 18 of 19 rows carried from {V220} by identical inputs"))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rc.main(["--write"]), 0)                               # current again: nothing written
            self.assertFalse((t / "closure-evidence/v2/release/V2.2.0-PROBE-CALIBRATIONS-3.json").exists())
            self.assertEqual(len(calls), 2)
            with open(t / V220, "ab") as f:
                f.write(b" \n")
            rel, state, basis = rc.resolve()
            self.assertEqual((rel, state), (NEW, "INVALIDATED"))
            self.assertIn(f"{NEW} carries rows from {V220}, which is INVALIDATED — {V220} differs from its committed bytes", basis)


if __name__ == "__main__":
    unittest.main()
