"""ROUND-AUTH review findings, fixed fail-closed. Always runs; seconds; throwaway trees and repositories only.

* RA-GP-1 — with the reviewed wiring (SEQ13-WIRING-R6.patch; R5's mechanism, re-pinned for the CI-portability
  corrections) applied, the 11 V22_REPLAYED tests and
  the V22_REPLAYED_Q0 class are skipped only while every V23_PINNED file is exactly as pinned. Deleting or editing one
  (the counterparts, the Q0 counterpart, `round_gate`, the replay, q0_round.py, the digest tool, tests/v23/__init__.py)
  un-skips all 12: they run under AISEF_SEALING=1 as before seq 13.
* RA-INT-2 — round v2.3 opens only for exactly one committed seq 13 that is the reviewed draft's ruling, by
  canonical digest, with the owner's own words quoting that digest. The placeholder, R1-R5, a minimal or doctored
  entry, a rewritten draft and a second seq 13 are each refused.
* Q0R-INT-1 — a draft rewritten through a merge (resolved by hand, or `-X theirs`), and any shallow clone, are
  refused; a merge that leaves the draft alone is not.
* Q0R-INT-2 — once approved, the round stays open only while every file the ruling binds (BOUND_SHA256: the Q0-1
  amendments and the evidence) is exactly those LF bytes.
"""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v2 import sealing_gate  # noqa: E402
from tests.v23 import test_v23_rounds as R  # noqa: E402  (module import: its TestCases are not collected twice)
from validation.v23 import ledger_digest as LD  # noqa: E402
from validation.v23 import replay_v22 as RP  # noqa: E402

PINNED = ("tests/v23/__init__.py", "tests/v23/test_v23_q0_round.py", "tests/v23/test_v23_rounds.py",
          "validation/v23/ledger_digest.py", "validation/v23/q0_round.py", "validation/v23/replay_v22.py")
NOT_REPLAYED = "tests/v2/test_cycle2_wp201.py::Baseline.test_the_committed_freeze_manifest_holds"
_n = itertools.count()


def _lf(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class WiringR6(unittest.TestCase):
    """RA-GP-1 + Q0-1, on a throwaway tree holding the patched sealing_gate.py and copies of the pinned files."""

    @classmethod
    def setUpClass(cls):
        cls.patch = (ROOT / R.SEQ13_PATCH_REL).read_bytes()
        cls.wired = R.wired_sealing_gate(cls.patch)
        cls._tmp = tempfile.TemporaryDirectory(prefix="aisef-seq13-gate-")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def tree(self, change=None) -> pathlib.Path:
        t = pathlib.Path(self._tmp.name, f"t{next(_n)}").resolve()
        (t / "tests/v2").mkdir(parents=True)
        (t / "tests/v2/sealing_gate.py").write_bytes(self.wired)
        for rel in PINNED:
            (t / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, t / rel)
        if change:
            change(t)
        return t

    def gate(self, tree: pathlib.Path, sealing_on: bool = True):
        spec = importlib.util.spec_from_file_location(f"aisef_seq13_gate_{next(_n)}", tree / "tests/v2/sealing_gate.py")
        mod = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ):
            os.environ.pop("AISEF_SEALING", None)
            if sealing_on:
                os.environ["AISEF_SEALING"] = "1"
            spec.loader.exec_module(mod)
        return mod

    @staticmethod
    def decorated(mod, tree: pathlib.Path, tid: str):
        """`mod.sealing` applied to a fresh function defined, as far as `inspect` can tell, at tid in tree."""
        path, qual = tid.split("::")
        ns: dict = {}
        exec(compile("def f(self):\n    pass\n", str(tree / path), "exec"), ns)
        ns["f"].__qualname__ = qual
        fn = mod.sealing(ns["f"])
        return getattr(fn, "__unittest_skip__", False), getattr(fn, "__unittest_skip_why__", "")

    def test_the_patch_is_current_and_keeps_GATED(self):
        self.assertEqual(re.findall(rb"^diff --git a/(\S+) ", self.patch, re.M), [b"tests/v2/sealing_gate.py"])
        (draft,) = LD.entries((ROOT / R.SEQ13_DRAFT_REL).read_text(encoding="utf-8"))
        self.assertIn(_sha(_lf(self.patch)), draft["decision"]["GATED_TEST_WIRING"])     # the ruling names this patch
        mod = self.gate(self.tree())
        self.assertEqual(mod.GATED, sealing_gate.GATED)
        gated_src = re.compile(rb"\nGATED = \(\n.*?\n\)\n", re.S)
        self.assertEqual(gated_src.findall(self.wired), gated_src.findall(_lf((ROOT / "tests/v2/sealing_gate.py").read_bytes())))
        self.assertEqual(mod.V22_REPLAYED, RP.V22_REPLAYED)
        self.assertEqual(mod.V22_REPLAYED_Q0, (RP.Q0_REPLAYED,))
        self.assertEqual(tuple(mod.V23_PINNED), PINNED)
        for rel in PINNED:   # the drafted pins are this tree's files: an edit of one without a new patch is red here
            self.assertEqual(mod.V23_PINNED[rel], _sha(_lf((ROOT / rel).read_bytes())), rel)
        self.assertEqual((ROOT / "tests/v23/__init__.py").read_bytes(), b"")
        self.assertTrue(mod.V23_PINS_HOLD)

    def test_with_every_pin_holding_the_11_and_q0_are_skipped_naming_the_replay(self):
        t = self.tree()
        mod = self.gate(t)
        for tid in RP.REPLAYED:
            skipped, why = self.decorated(mod, t, tid)
            self.assertTrue(skipped, tid)
            self.assertIn("replayed at v2.2.0", why)
        self.assertEqual(self.decorated(mod, t, NOT_REPLAYED), (False, ""))      # the other 7 run, as before

    def test_a_dropped_or_edited_pinned_file_un_skips_all_12(self):
        def delete(rel):
            return lambda t: (t / rel).unlink()

        def append(rel):
            return lambda t: (t / rel).write_bytes((t / rel).read_bytes() + b"# x\n")

        def neuter_round_gate(t):   # the reviewer's variant D: one line in the counterparts file
            p = t / "tests/v23/test_v23_rounds.py"
            src = p.read_bytes()
            self.assertIn(b"    sealing_gate.SEALING, \"round-v2.3", src)
            p.write_bytes(src.replace(b"    sealing_gate.SEALING, \"round-v2.3", b"    False and sealing_gate.SEALING, \"round-v2.3", 1))

        cases = [(f"delete {r}", delete(r)) for r in PINNED] + [(f"edit {r}", append(r)) for r in PINNED]
        cases += [("neuter round_gate", neuter_round_gate)]
        for name, change in cases:
            with self.subTest(name):
                t = self.tree(change)
                mod = self.gate(t)
                self.assertFalse(mod.V23_PINS_HOLD)
                for tid in RP.REPLAYED:
                    self.assertEqual(self.decorated(mod, t, tid), (False, ""), f"{name}: {tid} is not run")

    def test_without_the_sealing_tier_a_broken_pin_is_the_ordinary_visible_skip(self):
        t = self.tree(lambda t: (t / "tests/v23/test_v23_rounds.py").unlink())
        mod = self.gate(t, sealing_on=False)
        for tid in RP.REPLAYED:
            skipped, why = self.decorated(mod, t, tid)
            self.assertTrue(skipped)
            self.assertIn("record-currency/sealing check", why)
            self.assertNotIn("replayed", why)

    def test_a_CRLF_checkout_keeps_the_pins(self):
        def crlf(t):
            for rel in PINNED:
                (t / rel).write_bytes(_lf((t / rel).read_bytes()).replace(b"\n", b"\r\n"))
        t = self.tree(crlf)
        mod = self.gate(t)
        self.assertTrue(mod.V23_PINS_HOLD)
        self.assertTrue(self.decorated(mod, t, RP.V22_REPLAYED[0])[0])

    def test_R2s_patch_would_have_skipped_with_the_counterparts_deleted(self):
        """The finding itself, on R2's wiring: the contrast the fix removes."""
        old = R.wired_sealing_gate((ROOT / "docs/v2.3/drafts/SEQ13-WIRING.patch").read_bytes())
        t = self.tree(lambda t: (t / "tests/v23/test_v23_rounds.py").unlink())
        (t / "tests/v2/sealing_gate.py").write_bytes(old)
        mod = self.gate(t)
        self.assertTrue(all(self.decorated(mod, t, tid)[0] for tid in RP.V22_REPLAYED))

    def test_R5s_patch_on_this_tree_skips_nothing(self):
        """R5 is superseded: the CI-portability corrections changed replay_v22.py and the Q0 counterpart, and R6
        re-points the counterparts file, so R5's pins fail and it skips none."""
        old = R.wired_sealing_gate((ROOT / "docs/v2.3/drafts/SEQ13-WIRING-R5.patch").read_bytes())
        t = self.tree()
        (t / "tests/v2/sealing_gate.py").write_bytes(old)
        mod = self.gate(t)
        self.assertEqual(mod.V22_REPLAYED_Q0, (RP.Q0_REPLAYED,))
        self.assertFalse(mod.V23_PINS_HOLD)
        self.assertEqual([tid for tid in RP.REPLAYED if self.decorated(mod, t, tid)[0]], [])

    def test_R4s_patch_on_this_tree_skips_nothing(self):
        """R4 is superseded: R5 changed q0_round.py and both counterpart files, so R4's pins fail and it skips none."""
        old = R.wired_sealing_gate((ROOT / "docs/v2.3/drafts/SEQ13-WIRING-R4.patch").read_bytes())
        t = self.tree()
        (t / "tests/v2/sealing_gate.py").write_bytes(old)
        mod = self.gate(t)
        self.assertEqual(mod.V22_REPLAYED_Q0, (RP.Q0_REPLAYED,))
        self.assertFalse(mod.V23_PINS_HOLD)
        self.assertEqual([tid for tid in RP.REPLAYED if self.decorated(mod, t, tid)[0]], [])

    def test_R3s_patch_never_skips_q0_and_on_this_tree_skips_nothing(self):
        """R3 is superseded, not unsafe: it never names Q0, and its pins no longer hold, so applied now it skips none."""
        old = R.wired_sealing_gate((ROOT / "docs/v2.3/drafts/SEQ13-WIRING-R3.patch").read_bytes())
        t = self.tree()
        (t / "tests/v2/sealing_gate.py").write_bytes(old)
        mod = self.gate(t)
        self.assertFalse(hasattr(mod, "V22_REPLAYED_Q0"))
        self.assertFalse(mod.V23_PINS_HOLD)
        self.assertEqual([tid for tid in RP.REPLAYED if self.decorated(mod, t, tid)[0]], [])


def _git(root, *a) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "commit.gpgsign=false", *a], capture_output=True, check=True, encoding="utf-8").stdout


class LedgerSeq13(unittest.TestCase):
    """RA-INT-2, Q0R-INT-1, Q0R-INT-2: ledger_seq13_problems on throwaway repositories (ledger 1-12 + one appended
    entry, the reviewed draft — R6 since the CI-portability re-pin — and the files it binds; `self.r3` names the
    reviewed ruling)."""

    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads((ROOT / R.LEDGER_REL).read_text(encoding="utf-8"))
        assert [e["seq"] for e in cls.ledger["entries"]][:12] == list(range(1, 13))
        cls.ledger = dict(cls.ledger, entries=cls.ledger["entries"][:12])   # the committed seq 13 may follow (ROUND-AUTH)
        cls.draft = _lf((ROOT / R.SEQ13_DRAFT_REL).read_bytes())      # its LF bytes, on a CRLF checkout too
        (cls.r3,) = LD.entries(cls.draft.decode("utf-8"))
        cls.d3 = LD.digest(cls.r3)
        cls.bound = cls.r3["decision"]["BOUND_SHA256"]
        cls.rewritten = cls.draft.decode("utf-8").replace("re-derive round-v2.3", "re-derive or rewrite round-v2.3", 1)
        (cls.doctored,) = LD.entries(cls.rewritten)
        cls._tmp = tempfile.TemporaryDirectory(prefix="aisef-seq13-ledger-")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def place(self, root: pathlib.Path, draft: bytes | None, *e13) -> None:
        """The bound files, the ledger (1-12 + e13) and, unless None, `draft` written into root."""
        for rel in self.bound:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, root / rel)
        (root / R.LEDGER_REL).parent.mkdir(parents=True, exist_ok=True)
        doc = dict(self.ledger, entries=self.ledger["entries"] + list(e13))
        (root / R.LEDGER_REL).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        if draft is not None:
            (root / R.SEQ13_DRAFT_REL).parent.mkdir(parents=True, exist_ok=True)
            (root / R.SEQ13_DRAFT_REL).write_bytes(draft)

    @staticmethod
    def commit(root: pathlib.Path, msg: str) -> str:
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", msg)
        return _git(root, "rev-parse", "HEAD").strip()

    def problems(self, *e13, draft_rewrite: bytes | None = None, dirty: bool = False, after=None) -> list[str]:
        root = pathlib.Path(self._tmp.name, f"r{next(_n)}")
        self.place(root, self.draft)
        _git(root, "init", "-q")
        self.commit(root, "draft")
        self.place(root, draft_rewrite, *e13)
        self.commit(root, "seq 13")
        if dirty:
            doc = dict(self.ledger, entries=self.ledger["entries"] + list(e13))
            (root / R.LEDGER_REL).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        if after:
            after(root)
        return R.ledger_seq13_problems(root)

    def approved(self, entry=None, digest=None):
        e = json.loads(json.dumps(self.r3 if entry is None else entry))
        e["authority"] = f"owner, 2026-11-22, chat: I approve seq 13 as drafted, ruling digest {digest or LD.digest(e)}."
        return e

    def test_the_reviewed_ruling_in_the_owners_words_quoting_its_digest_opens(self):
        self.assertEqual(self.problems(self.approved()), [])

    def test_the_reviewers_six_entries_are_refused(self):
        r1 = LD.entries((ROOT / "docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT.md").read_text(encoding="utf-8"))[0]
        r2 = LD.entries((ROOT / "docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R2.md").read_text(encoding="utf-8"))[0]
        r3 = LD.entries((ROOT / "docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R3.md").read_text(encoding="utf-8"))[0]
        r4 = LD.entries((ROOT / "docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R4.md").read_text(encoding="utf-8"))[0]
        r5 = LD.entries((ROOT / "docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R5.md").read_text(encoding="utf-8"))[0]
        doctored = json.loads(json.dumps(self.r3))
        doctored.update(authority="agent wrote this", subject_to="nothing")
        doctored["decision"].update(NOT_AUTHORIZED="", GATED_TEST_WIRING="any wiring")
        minimal = {"seq": 13, "id": R.ROUND_ID, "approver": "human:owner", "decision": {"QUALIFICATION_ROUND": "v2.3"}}
        cases = {
            "R3 with the placeholder": (self.r3, "placeholder"),
            "R1 verbatim": (r1, "is not the reviewed draft's"),
            "R3 with authority ''": (dict(self.r3, authority=""), "placeholder"),
            "R3 without authority": ({k: v for k, v in self.r3.items() if k != "authority"}, "placeholder"),
            "minimal entry": (minimal, "is not a ruling entry"),
            "doctored": (doctored, "is not the reviewed draft's"),
            "R2 approved in words quoting R2's digest": (self.approved(r2), "is not the reviewed draft's"),
            "R3 (superseded by R4) approved in words quoting R3's digest": (self.approved(r3), "is not the reviewed draft's"),
            "R4 (superseded by R5) approved in words quoting R4's digest": (self.approved(r4), "is not the reviewed draft's"),
            "R5 (superseded by R6) approved in words quoting R5's digest": (self.approved(r5), "is not the reviewed draft's"),
            "doctored, approved in words quoting its own digest": (self.approved(dict(doctored)), "is not the reviewed draft's"),
            "R3 approved in words that do not quote the digest": (dict(self.r3, authority="owner, 2026-11-22: approved"),
                                                                 "does not quote its ruling digest"),
            "R3 approved in words quoting another digest": (self.approved(digest="0" * 64), "does not quote"),
        }
        for name, (e, why) in cases.items():
            with self.subTest(name):
                got = self.problems(e)
                self.assertTrue(got, name)
                self.assertTrue(any(why in p for p in got), got)
        for name, e in {"approver agent": dict(self.approved(), approver="agent"),
                        "round v2.4": dict(self.approved(), decision=dict(self.r3["decision"], QUALIFICATION_ROUND="v2.4")),
                        "id X": dict(self.approved(), id="X"),
                        "decision not an object": dict(self.approved(), decision="v2.3")}.items():
            with self.subTest(name):
                self.assertEqual([p for p in self.problems(e) if "no single committed owner entry seq 13" in p][:1],
                                 [f"the ledger holds no single committed owner entry seq 13 {R.ROUND_ID} (ROUND-AUTH: draft only)"])

    def test_a_second_seq_13_is_refused(self):
        self.assertTrue(self.problems(self.approved(), self.approved()))

    def test_a_rewritten_draft_is_refused_even_when_the_entry_matches_it(self):
        got = self.problems(self.approved(self.doctored), draft_rewrite=self.rewritten.encode("utf-8"))
        self.assertEqual(got, ["the ledger or the reviewed draft is unreadable: ValueError"])

    def merged(self, how: str) -> pathlib.Path:
        """Q0R-INT-1's repositories: the reviewed draft added on the main line, a rewritten one added on a side branch
        cut before it, merged so that HEAD holds the rewrite ("by hand": the add/add conflict resolved to it;
        "theirs": `-X theirs`), then seq 13 approving the rewrite committed. "benign": the side branch touches only a
        README, and seq 13 approves the reviewed draft."""
        root = pathlib.Path(self._tmp.name, f"m{next(_n)}")
        self.place(root, None)
        _git(root, "init", "-q")
        base = self.commit(root, "base")
        main = _git(root, "symbolic-ref", "--short", "HEAD").strip()
        self.place(root, self.draft)
        self.commit(root, "the reviewed draft")
        _git(root, "checkout", "-q", "-b", "side", base)
        if how == "benign":
            (root / "README").write_text("side\n", encoding="utf-8")
        else:
            self.place(root, self.rewritten.encode("utf-8"))
        self.commit(root, "side")
        _git(root, "checkout", "-q", main)
        if how == "by hand":
            subprocess.run(["git", "-C", str(root), "merge", "-q", "side"], capture_output=True)   # add/add conflict
            self.place(root, self.rewritten.encode("utf-8"))
            self.commit(root, "merge side, resolved to the rewrite")
        else:
            _git(root, "merge", "-q", "--no-edit", *(["-X", "theirs"] if how == "theirs" else []), "side")
        self.place(root, None, self.approved(self.r3 if how == "benign" else self.doctored))
        self.commit(root, "seq 13")
        return root

    def test_a_draft_rewritten_through_a_merge_is_refused(self):
        for how in ("by hand", "theirs"):
            with self.subTest(how):
                root = self.merged(how)
                self.assertEqual((root / R.SEQ13_DRAFT_REL).read_text(encoding="utf-8"), self.rewritten)
                self.assertEqual(R.ledger_seq13_problems(root), ["the ledger or the reviewed draft is unreadable: ValueError"])
        self.assertEqual(R.ledger_seq13_problems(self.merged("benign")), [])         # a merge alone is not refused

    def test_a_shallow_clone_is_refused(self):
        root = self.merged("benign")
        full, shallow = pathlib.Path(self._tmp.name, f"c{next(_n)}"), pathlib.Path(self._tmp.name, f"c{next(_n)}")
        _git(self._tmp.name, "clone", "-q", str(root), str(full))
        _git(self._tmp.name, "clone", "-q", "--depth", "1", root.resolve().as_uri(), str(shallow))
        self.assertEqual(_git(shallow, "rev-parse", "--is-shallow-repository").strip(), "true")
        self.assertEqual(R.ledger_seq13_problems(full), [])
        self.assertEqual(R.ledger_seq13_problems(shallow), ["the ledger or the reviewed draft is unreadable: ValueError"])

    def test_every_bound_file_must_stay_as_reviewed(self):
        amendment = "docs/v2.3/amendments/Q0-1-V23-ROUND.md"
        evidence = "docs/v2.3/evidence/q0-round/Q0-DELTA-2026-11-21.json"
        self.assertLessEqual({amendment, evidence, "docs/v2.3/amendments/Q0-1-R5.md"}, set(self.bound))

        def edit(root):
            (root / amendment).write_bytes((root / amendment).read_bytes() + b"post-approval edit\n")

        def crlf(root):
            for rel in self.bound:
                (root / rel).write_bytes(_lf((root / rel).read_bytes()).replace(b"\n", b"\r\n"))
        self.assertEqual(self.problems(self.approved(), after=edit),
                         [f"{amendment} is not the file the reviewed ruling binds (BOUND_SHA256 {self.bound[amendment]})"])
        self.assertEqual(self.problems(self.approved(), after=lambda root: (root / evidence).unlink()),
                         [f"{evidence} is not the file the reviewed ruling binds (BOUND_SHA256 {self.bound[evidence]})"])
        self.assertEqual(self.problems(self.approved(), after=crlf), [])

    def test_an_uncommitted_ledger_change_is_refused(self):
        got = self.problems(self.approved(), dirty=True)
        self.assertEqual(got, [f"{R.LEDGER_REL} differs from its committed bytes"])


if __name__ == "__main__":
    unittest.main()
