"""WP-2.1.1 (Cycle 2, C2-P1) — the `file_artifact` probe on real repositories and on the committed fixtures.

FA-1 the object-store rule on a dirty checkout and on two worktrees of one commit; FA-2 ABSENCE_IS_DECIDABLE decides
a prohibition over an absent path through run_probe + classify_failure; FA-3 the three classes calibrated with
contrast and rejected once the fixtures stop contrasting; FA-ADV-1..3 a symlink entry, a tree escape and an
always-REFUTED probe of the same shape; FM2-FILE-1..5 git absent, revision unknown, binary under grep, pattern cap,
case-collision paths; FA-Q0 the Q0 probe rules. The kill set for every mutation target of
aisef2/probe/file_artifact.py, so the pure tables are pinned exhaustively here too.

The module lives at the tests/v2 root (Tier.ROOT): every test directory under tests/v2 must be a Tier of
aisef2/invariants/registry.py, which this package may not edit.
"""

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction, Enforcement, Polarity, SubjectAbsence, SubjectKind,
)
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.calibration import NotQualified, calibrate, calibration_env, fixture_spec  # noqa: E402
from aisef2.probe.catalog import CATALOG, entry_for  # noqa: E402
from aisef2.probe.protocol import (  # noqa: E402
    ExecutionEnv, HarnessProbe, Observation, ObservationKind as K, ProbeRegistry, RevisionRef, run_probe,
)
from aisef2.product.compiler import expectation_for  # noqa: E402
from aisef2.product.contract import names_test_artefact  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason, InvalidSpec, Unrunnable, contract_satisfaction  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

P = fa.FileArtifactProbe()
S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
DECIDABLE, REQUIRES = SubjectAbsence.ABSENCE_IS_DECIDABLE, SubjectAbsence.REQUIRES_SUBJECT
ENV = ExecutionEnv(sys.executable, 30.0, Enforcement.PARTIAL)
FULL_ENV = ExecutionEnv(sys.executable, 30.0, Enforcement.FULL)
BASE = ROOT / "tests" / "v2" / "fixtures" / "calibration" / "file_artifact"
REGISTRY = ProbeRegistry([fa.METADATA])
W = 10
EXISTS = {"condition": "exists"}
NO_SHA = "f" * 40
CONFIG = b'name = "calib"\nversion = 1\n'
MAIN = b'"""The product."""\n\nimport json\n\n\ndef load(path):\n    return json.load(open(path))\n'
V1, V2, DIRTY = b"1.0.0\n", b"2.0.0\n", b"9.9.9\n"
_NO_BACKGROUND_GIT = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false",
                      "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0"}


def git(repo, *args: str, data: bytes | None = None) -> bytes:
    p = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t.t",
                        "-c", "core.autocrlf=false", "-c", "core.symlinks=false", *args],
                       input=data, capture_output=True, env={**os.environ, **_NO_BACKGROUND_GIT})
    if p.returncode != 0:
        raise AssertionError(f"git {args}: {p.stderr.decode('utf-8', 'replace')}")
    return p.stdout


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def spec(locator, observable=None, stimulus=None, *, expectation=S, absence=DECIDABLE, probe=P, window=W,
         kind="file_artifact"):
    """A spec over `locator`; its observable declares the bounded window `window` (None: declares none)."""
    observable = dict(observable or EXISTS)
    if window is not None:
        observable.setdefault("within_s", window)
    return ProductProofSpec.create(
        contract_id="BC-FA", probe_id=probe.id, probe_digest=probe.digest,
        probe_input={"subject": {"kind": kind, "locator": locator}, "stimulus": stimulus or {},
                     "observable": observable, "subject_absence": absence.value},
        candidate_expectation=expectation, compiler_id="c2", compiler_digest="c" * 64)


def content(digest: str, newline: str | None = None) -> dict:
    return {"sha256": digest, **({"newline": newline} if newline else {})}


def grep(pattern: str, matches: int, suffixes=None) -> tuple[dict, dict]:
    return {"matches": matches}, {"grep": pattern, **({"suffixes": suffixes} if suffixes is not None else {})}


def facts(o: Observation) -> dict:
    return json.loads(o.detail[o.detail.index("{"):])


class Repo:
    """A throwaway repository. `commit` writes files and commits them; `index` puts an entry into the index by
    content and mode without touching the working tree (a symlink entry, a case-colliding path, a gitlink)."""

    def __init__(self, path) -> None:
        self.path = pathlib.Path(path)
        self.path.mkdir()
        git(self.path, "init", "-q", "-b", "main")

    def commit(self, files: dict, message: str = "c") -> str:
        for rel, data in files.items():
            p = self.path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        git(self.path, "add", "-A")
        return self.commit_index(message)

    def index(self, rel: str, data: bytes | None, mode: str = "100644", oid: str | None = None) -> None:
        oid = oid or git(self.path, "hash-object", "-w", "--stdin", data=data).decode().strip()
        git(self.path, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{rel}")

    def commit_index(self, message: str = "c") -> str:
        git(self.path, "commit", "-q", "--allow-empty", "-m", message)
        return git(self.path, "rev-parse", "HEAD").decode().strip()

    def worktree(self, name: str, rev: str) -> pathlib.Path:
        wt = self.path.parent / name
        git(self.path, "worktree", "add", "-q", "--detach", str(wt), rev)
        return wt


def at(repo, rev: str) -> RevisionRef:
    return RevisionRef(rev, str(repo))


class ObjectStoreRule(unittest.TestCase):
    """FA-1, FM2-FILE-2/3/5, FA-ADV-1: what the probe reads is the object store at the revision SHA."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="aisef2-fa-")
        cls.repo = Repo(pathlib.Path(cls.tmp.name) / "repo")
        cls.sha1 = cls.repo.commit({"app/config.toml": CONFIG, "app/VERSION": V1, "app/main.py": MAIN,
                                    "app/sub/deep.py": b"import telemetry\nimport telemetry\n",
                                    "app/data.bin": b"\x00\x01 telemetry", "app/NOTES.md": b"telemetry\n"})
        cls.repo.index("app/run.py", b"#!/usr/bin/env python3\nimport telemetry\n", "100755")
        cls.repo.index("app/latin1.txt", b"caf\xe9 telemetry\n")
        cls.sha1b = cls.repo.commit_index("modes")
        cls.sha2 = cls.repo.commit({"app/VERSION": V2})
        # the working tree is now dirty: a committed file rewritten, an untracked file added
        (cls.repo.path / "app" / "VERSION").write_bytes(DIRTY)
        (cls.repo.path / "app" / "untracked.py").write_bytes(b"import telemetry\n")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def observe(self, rev, *args, **kw) -> Observation:
        return P.observe(spec(*args, **kw), at(self.repo.path, rev), ENV)

    def test_FA_1_a_dirty_checkout_answers_with_the_committed_tree_at_the_sha(self):
        o1 = self.observe(self.sha1, "path:app/VERSION", content(sha(V1)))
        o2 = self.observe(self.sha2, "path:app/VERSION", content(sha(V2)))
        dirty = self.observe(self.sha2, "path:app/VERSION", content(sha(DIRTY)))
        self.assertEqual([(o.kind, o.verdict) for o in (o1, o2, dirty)], [(K.OBSERVED, S), (K.OBSERVED, S), (K.OBSERVED, R)])
        self.assertEqual((facts(o1)["read"], facts(o1)["revision"], facts(o2)["revision"]), ("object_store", self.sha1, self.sha2))
        self.assertEqual((facts(o1)["path"], facts(o1)["mode"], facts(o1)["kind"]), ("app/VERSION", "100644", "blob"))
        self.assertEqual((facts(o1)["sha256"], facts(o2)["sha256"]), (sha(V1), sha(V2)))
        self.assertEqual(facts(dirty)["sha256"], sha(V2))   # never the working file's 9.9.9
        self.assertEqual(self.observe(self.sha2, "path:app/VERSION", content(sha(V1))).verdict, R)
        # the untracked working file is not in the tree at either revision
        for rev in (self.sha1, self.sha2):
            o = self.observe(rev, "path:app/untracked.py")
            self.assertEqual((o.kind, o.verdict, facts(o)["present"], facts(o)["path"]),
                             (K.SUBJECT_ABSENT, R, False, "app/untracked.py"))
        o = self.observe(self.sha2, "path:app", *grep(r"9\.9\.9|untracked", 0))
        self.assertEqual((o.kind, o.verdict, facts(o)["matches"]), (K.OBSERVED, S, 0))
        self.assertEqual((facts(o)["path"], facts(o)["mode"], facts(o)["revision"]), ("app", "040000", self.sha2))
        rec = run_probe(P, spec("path:app/VERSION", content(sha(V1))), at(self.repo.path, self.sha1), FULL_ENV)
        self.assertEqual((rec.result, rec.enforcement, rec.revision), (Executed(S), Enforcement.FULL, self.sha1))

    def test_FA_1_implementer_and_verifier_worktrees_of_one_commit_agree_one_dirty(self):
        impl, ver = self.repo.worktree("wt-impl", self.sha1), self.repo.worktree("wt-verifier", self.sha1)
        (impl / "app" / "VERSION").write_bytes(DIRTY)
        (impl / "app" / "extra.py").write_bytes(b"import telemetry\n")
        for s in (spec("path:app/VERSION", content(sha(V1))), spec("path:app/extra.py"),
                  spec("path:app", *grep("telemetry", 2, [".py"])), spec("path:app/NOTES.md", content(sha(b"telemetry\n")))):
            with self.subTest(spec=dict(s.probe_input["observable"])):
                a, b = (P.observe(s, at(root, self.sha1), ENV) for root in (impl, ver))
                self.assertEqual((a.kind, a.verdict, facts(a)["read"]), (b.kind, b.verdict, "object_store"))
                self.assertEqual({k: v for k, v in facts(a).items() if k != "revision"},
                                 {k: v for k, v in facts(b).items() if k != "revision"})
        ra, rb = (run_probe(P, spec("path:app/VERSION", content(sha(V1))), at(root, self.sha1), ENV) for root in (impl, ver))
        self.assertEqual((ra.result, rb.result, ra.comparability), (Executed(S), Executed(S), rb.comparability))
        git(self.repo.path, "worktree", "remove", "--force", str(impl))
        git(self.repo.path, "worktree", "remove", "--force", str(ver))

    def test_FA_1_exists_and_modes_come_from_the_tree(self):
        o = self.observe(self.sha1b, "path:app/run.py")
        self.assertEqual((o.kind, o.verdict, facts(o)["mode"], facts(o)["path"]), (K.OBSERVED, S, "100755", "app/run.py"))
        o = self.observe(self.sha1b, "path:app/run.py/x")   # through an executable blob: not in the tree
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R))
        o = self.observe(self.sha1b, "path:app/run.py", content(sha(b"#!/usr/bin/env python3\nimport telemetry\n")))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        o = self.observe(self.sha1, "path:app")
        self.assertEqual((o.kind, o.verdict, facts(o)["mode"]), (K.OBSERVED, S, "040000"))
        o = self.observe(self.sha1, "path:app", content(sha(b"")))
        self.assertEqual((o.kind, o.verdict, facts(o)["kind"], facts(o)["path"]), (K.OBSERVED, R, "tree", "app"))
        o = self.observe(self.sha1, "path:app/sub")
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        for missing in ("path:app/nothing.py", "path:nothing/x.py", "path:app/VERSION/x"):
            with self.subTest(locator=missing):
                o = self.observe(self.sha1, missing)
                self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R))

    def test_FA_1_grep_counts_lines_over_the_tree_by_suffix(self):
        o = self.observe(self.sha1b, "path:app", *grep("telemetry", 3, [".py"]))   # deep.py x2 + run.py; never untracked.py
        self.assertEqual((o.kind, o.verdict, facts(o)["files"]), (K.OBSERVED, S, 3))
        self.assertEqual((facts(o)["path"], facts(o)["mode"]), ("app", "040000"))
        self.assertEqual(facts(o)["locations"], [["app/run.py", 2], ["app/sub/deep.py", 1], ["app/sub/deep.py", 2]])
        o = self.observe(self.sha1, "path:app", *grep("telemetry", 2, [".py", ".md"]))
        self.assertEqual((o.verdict, facts(o)["matches"], facts(o)["files"]), (R, 3, 3))
        o = self.observe(self.sha1, "path:app/sub/deep.py", *grep("tele", 2))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        o = self.observe(self.sha1, "path:app/sub/deep.py", *grep("tele", 2, [".md"]))
        self.assertEqual((o.verdict, facts(o)["files"], facts(o)["matches"]), (R, 0, 0))
        o = self.observe(self.sha1, "path:app/sub/deep.py", *grep("e", 2))   # one per matching line, never per match
        self.assertEqual((o.verdict, facts(o)["matches"], facts(o)["path"], facts(o)["mode"]), (S, 2, "app/sub/deep.py", "100644"))

    def test_FM2_FILE_2_a_revision_the_repository_does_not_hold_is_a_harness_failure_never_absence(self):
        tree = git(self.repo.path, "rev-parse", "HEAD^{tree}").decode().strip()   # an object of the repository, not a commit
        blob = git(self.repo.path, "rev-parse", "HEAD:app/VERSION").decode().strip()
        for rev in (NO_SHA, tree, blob):
            for s in (spec("path:app/VERSION", content(sha(V1))), spec("path:app/untracked.py"), spec("path:nothing")):
                with self.subTest(rev=rev[:8], locator=s.probe_input["subject"]["locator"]):
                    o = P.observe(s, at(self.repo.path, rev), ENV)
                    self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                    self.assertEqual(o.detail, f"revision {rev[:12]} not in the repository at the checkout root")
                    self.assertIsInstance(run_probe(P, s, at(self.repo.path, rev), ENV).result, Unrunnable)

    def test_FM2_FILE_3_a_binary_file_under_a_text_grep_is_skipped_and_recorded(self):
        o = self.observe(self.sha1, "path:app", *grep("telemetry", 3))   # deep.py x2 + NOTES.md; data.bin skipped
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        self.assertEqual((facts(o)["skipped_binary"], facts(o)["files"], facts(o)["matches"]), (["app/data.bin"], 6, 3))
        o = self.observe(self.sha1, "path:app/data.bin", *grep("telemetry", 0))
        self.assertEqual((o.verdict, facts(o)["skipped_binary"]), (S, ["app/data.bin"]))

    def test_FM2_FILE_3_a_file_that_is_not_utf8_leaves_the_count_unestablished(self):
        o = self.observe(self.sha1b, "path:app", *grep("telemetry", 4, [".py", ".txt"]))
        self.assertEqual((o.kind, o.verdict, facts(o)["undecodable"]), (K.OBSERVED, R, "app/latin1.txt"))
        self.assertNotIn("matches", facts(o))
        o = self.observe(self.sha1b, "path:app", *grep("telemetry", 3, [".py"]))   # not selected: counted normally
        self.assertEqual((o.verdict, facts(o)["matches"]), (S, 3))

    def test_FM2_FILE_5_case_collision_paths_are_read_exactly_from_the_tree(self):
        repo = Repo(pathlib.Path(self.tmp.name) / "collide")
        repo.index("README.md", b"upper\n")
        repo.index("Readme.md", b"mixed\n")
        rev = repo.commit_index("two names differing by case")
        self.assertEqual(sorted(git(repo.path, "ls-tree", "--name-only", rev).decode().split()), ["README.md", "Readme.md"])
        for name, data in (("README.md", b"upper\n"), ("Readme.md", b"mixed\n")):
            with self.subTest(name=name):
                o = P.observe(spec(f"path:{name}", content(sha(data))), at(repo.path, rev), ENV)
                self.assertEqual((o.kind, o.verdict, facts(o)["sha256"]), (K.OBSERVED, S, sha(data)))
        o = P.observe(spec("path:readme.md"), at(repo.path, rev), ENV)
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R))   # exact: the tree holds no readme.md

    def test_FA_ADV_1_a_symlink_entry_is_refused_for_content_and_grep_and_never_followed(self):
        repo = Repo(pathlib.Path(self.tmp.name) / "links")
        repo.commit({"d/x.py": b"import telemetry\n", "d/y.md": b"y\n"})
        repo.index("link", b"d/x.py", "120000")     # a symlink entry, put into the tree without a link on disk
        repo.index("dl", b"d", "120000")
        rev = repo.commit_index("links")
        for s in (spec("path:link", content(sha(b"import telemetry\n"))), spec("path:link", *grep("telemetry", 1)),
                  spec("path:dl/x.py"), spec("path:dl/x.py", content(sha(b"import telemetry\n")))):
            with self.subTest(locator=s.probe_input["subject"]["locator"], observable=dict(s.probe_input["observable"])):
                o = P.observe(s, at(repo.path, rev), ENV)
                self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                self.assertIn("link", o.detail)
                self.assertIn("120000", o.detail)
                self.assertIsInstance(run_probe(P, s, at(repo.path, rev), ENV).result, Unrunnable)
        o = P.observe(spec("path:link"), at(repo.path, rev), ENV)
        self.assertEqual((o.kind, o.verdict, facts(o)["mode"]), (K.OBSERVED, S, "120000"))   # exists: an entry
        o = P.observe(spec("path:d", *grep("telemetry", 1)), at(repo.path, rev), ENV)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        walk = P.observe(spec("path:.", *grep("telemetry", 1)), at(repo.path, rev), ENV)
        self.assertEqual(walk.kind, K.HARNESS_FAILED)   # '.' names no entry
        repo.index("nest/l", b"../d/x.py", "120000")
        rev = repo.commit_index("a link inside a directory")
        o = P.observe(spec("path:nest", *grep("telemetry", 0)), at(repo.path, rev), ENV)
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertIn("nest/l (120000)", o.detail)
        o = P.observe(spec("path:nest", *grep("telemetry", 0, [".py"])), at(repo.path, rev), ENV)
        self.assertEqual((o.kind, o.verdict, facts(o)["files"]), (K.OBSERVED, S, 0))   # not selected: not read

    def test_a_gitlink_is_not_a_file_of_this_repository(self):
        repo = Repo(pathlib.Path(self.tmp.name) / "gitlink")
        repo.index("vendor", None, "160000", oid="a" * 40)
        rev = repo.commit_index("a submodule entry")
        for s in (spec("path:vendor"), spec("path:vendor", content(sha(b""))), spec("path:vendor", *grep("x", 0))):
            with self.subTest(observable=dict(s.probe_input["observable"])):
                o = P.observe(s, at(repo.path, rev), ENV)
                self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                self.assertIn("160000", o.detail)

    def test_content_newline_declares_the_line_convention(self):
        repo = Repo(pathlib.Path(self.tmp.name) / "newlines")
        crlf, lf = b"a\r\nb\r\n", b"a\nb\n"
        rev = repo.commit({"crlf.txt": crlf, "lf.txt": lf})
        cases = [("crlf.txt", content(sha(crlf)), S), ("crlf.txt", content(sha(lf)), R),
                 ("crlf.txt", content(sha(lf), "\n"), S), ("crlf.txt", content(sha(crlf), "\r\n"), S),
                 ("lf.txt", content(sha(crlf), "\r\n"), S), ("lf.txt", content(sha(crlf)), R),
                 ("crlf.txt", {"equals_text": "a\nb\n", "newline": "\r\n"}, S),
                 ("crlf.txt", {"equals_text": "a\nb\n", "newline": "\n"}, S),
                 ("lf.txt", {"equals_text": "a\nb\n", "newline": "\r\n"}, S),
                 ("lf.txt", {"equals_text": "a\nb", "newline": "\n"}, R)]
        for rel, observable, want in cases:
            with self.subTest(rel=rel, observable=observable):
                o = P.observe(spec(f"path:{rel}", observable), at(repo.path, rev), ENV)
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, want))

    def test_the_per_file_cap_is_a_harness_refusal_never_a_verdict(self):
        with mock.patch.object(fa, "FILE_CAP", 5):
            o = self.observe(self.sha1, "path:app/VERSION", content(sha(V1)))
            self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
            self.assertIn("cap", o.detail)
            o = self.observe(self.sha1, "path:app", *grep("telemetry", 0, [".md"]))
            self.assertEqual(o.kind, K.HARNESS_FAILED)
        o = self.observe(self.sha1, "path:app/VERSION", content(sha(V1)))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))

    def test_git_that_does_not_answer_within_the_watchdog_is_a_harness_failure(self):
        with mock.patch.object(fa.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 1)):
            o = self.observe(self.sha1, "path:app/VERSION")
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertIn("watchdog", o.detail)
        with mock.patch.object(fa.subprocess, "run", side_effect=OSError("no")):
            o = self.observe(self.sha1, "path:app/VERSION")
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertIn("cannot launch", o.detail)
        with mock.patch.object(fa.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"broken")):
            o = self.observe(self.sha1, "path:app/VERSION")
        self.assertEqual(o.kind, K.HARNESS_FAILED)
        self.assertIn("exited 1", o.detail)

    def test_every_class_means_REFUTED_by_an_expired_window(self):
        for s in (spec("path:app/VERSION"), spec("path:app/VERSION", content(sha(V1))),
                  spec("path:app", *grep("telemetry", 3))):
            with self.subTest(observable=dict(s.probe_input["observable"])):
                with mock.patch.object(fa, "time", mock.Mock(monotonic=mock.Mock(side_effect=[0.0, W + 1.0]))):
                    o = P.observe(s, at(self.repo.path, self.sha1), ENV)
                self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R))
                cls = fa.spec_class(s)
                self.assertTrue(o.detail.startswith(f"the {W}s observation window expired ({cls}); {{\"read\": \"object_store\""), o.detail)
                with mock.patch.object(fa, "time", mock.Mock(monotonic=mock.Mock(side_effect=[0.0, W + 1.0]))):
                    self.assertEqual(run_probe(P, s, at(self.repo.path, self.sha1), ENV).result, Executed(R))
                with mock.patch.object(fa, "time", mock.Mock(monotonic=mock.Mock(side_effect=[0.0, W - 1.0]))):
                    self.assertEqual(P.observe(s, at(self.repo.path, self.sha1), ENV).kind, K.OBSERVED)

    def test_the_scrubbed_git_environment_and_the_evaluation_home(self):
        seen = []
        real = fa.subprocess.run

        def spy(argv, **kw):
            seen.append((argv, kw))
            return real(argv, **kw)
        with mock.patch.object(fa.subprocess, "run", side_effect=spy):
            o = self.observe(self.sha1, "path:app/VERSION", content(sha(V1)))
        self.assertEqual(o.verdict, S)
        self.assertEqual([a[0][3] for a in seen], ["rev-parse", "cat-file", "ls-tree", "cat-file"])
        self.assertEqual(seen[0][0][3:], ["rev-parse", "--show-toplevel"])
        self.assertEqual(seen[1][0][3:], ["cat-file", "-e", f"{self.sha1}^{{commit}}"])
        self.assertEqual(seen[2][0][3:], ["ls-tree", "-z", "-l", "-t", self.sha1, "--", "app/VERSION"])
        self.assertEqual(seen[3][0][3:5], ["cat-file", "blob"])
        for argv, kw in seen:
            self.assertEqual((argv[0], argv[1], kw["shell"], kw["capture_output"], kw["timeout"]),
                             (P._git, "-C", False, True, ENV.timeout_s))
            self.assertTrue(os.path.isabs(argv[0]))
            self.assertNotIn("text", kw)
            env = kw["env"]
            self.assertEqual((env["GIT_CONFIG_NOSYSTEM"], env["GIT_TERMINAL_PROMPT"], env["LC_ALL"]), ("1", "0", "C"))
            self.assertFalse(os.path.exists(env["GIT_CONFIG_GLOBAL"]))
            self.assertTrue(os.path.basename(env["HOME"]).startswith("aisef2-file-artifact-"), env["HOME"])
            self.assertFalse(os.path.isdir(env["HOME"]))   # the evaluation directory is gone with the evaluation
        self.assertEqual(seen[0][1]["env"]["GIT_CEILING_DIRECTORIES"], os.path.dirname(os.path.realpath(self.repo.path)))
        self.assertNotIn("GIT_CEILING_DIRECTORIES", seen[1][1]["env"])


class Absence(unittest.TestCase):
    """FA-2: ABSENCE_IS_DECIDABLE decides a prohibition over an absent path through run_probe + classify_failure."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="aisef2-fa-")
        cls.repo = Repo(pathlib.Path(cls.tmp.name) / "repo")
        cls.rev = cls.repo.commit({"app/main.py": MAIN})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def result(self, s):
        return run_probe(P, s, at(self.repo.path, self.rev), ENV).result

    def test_FA_2_a_MUST_NOT_HOLD_prohibition_over_an_absent_path_is_decided(self):
        must_not = expectation_for(Polarity.MUST_NOT_HOLD)
        s = spec("path:app/telemetry.py", expectation=must_not, absence=DECIDABLE)
        self.assertEqual(self.result(s), Executed(R))
        self.assertIs(contract_satisfaction(self.result(s), s), ContractSatisfaction.SATISFIED)
        s = spec("path:app/telemetry.py", content(sha(b"x")), expectation=must_not, absence=DECIDABLE)
        self.assertEqual(self.result(s), Executed(R))
        self.assertIs(contract_satisfaction(self.result(s), s), ContractSatisfaction.SATISFIED)

    def test_FA_2_grep_over_an_absent_package_takes_the_verdict_of_zero_matches(self):
        s = spec("path:vendor", *grep("telemetry", 0), expectation=S, absence=DECIDABLE)
        self.assertEqual(self.result(s), Executed(S))
        self.assertIs(contract_satisfaction(self.result(s), s), ContractSatisfaction.SATISFIED)
        s = spec("path:vendor", *grep("telemetry", 2), expectation=S, absence=DECIDABLE)
        self.assertEqual(self.result(s), Executed(R))
        o = P.observe(s, at(self.repo.path, self.rev), ENV)
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R))

    def test_FA_2_REQUIRES_SUBJECT_drops_the_offered_verdict(self):
        for s in (spec("path:app/telemetry.py", absence=REQUIRES),
                  spec("path:vendor", *grep("telemetry", 0), absence=REQUIRES),
                  spec("path:app/telemetry.py", content(sha(b"x")), absence=REQUIRES)):
            with self.subTest(observable=dict(s.probe_input["observable"])):
                self.assertEqual(self.result(s), Executed(BehaviorVerdict.INDETERMINATE,
                                                          IndeterminateReason.PRECONDITION_ABSENT))

    def test_run_probe_binds_FULL_enforcement_and_refuses_a_foreign_spec(self):
        rec = run_probe(P, spec("path:app/main.py"), at(self.repo.path, self.rev), FULL_ENV)
        self.assertEqual((rec.result, rec.enforcement, rec.probe_id, rec.probe_digest),
                         (Executed(S), Enforcement.FULL, fa.PROBE_ID, fa.DIGEST))
        other = spec("app.main:load", kind="python_callable")
        self.assertIsInstance(run_probe(P, other, at(self.repo.path, self.rev), ENV).result, InvalidSpec)
        o = P.observe(other, at(self.repo.path, self.rev), ENV)
        self.assertEqual((o.kind, o.verdict), (K.UNSUPPORTED, None))
        self.assertEqual(o.detail, "subject kind 'python_callable' is not file_artifact")


class Refusals(unittest.TestCase):
    """FA-ADV-2, FM2-FILE-1, FM2-FILE-4: escapes, a probe without git, the pattern cap, unsupported specs."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="aisef2-fa-")
        cls.repo = Repo(pathlib.Path(cls.tmp.name) / "repo")
        cls.rev = cls.repo.commit({"app/main.py": MAIN})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_FA_ADV_2_a_tree_escape_is_refused(self):
        for locator, why in (("path:../x", "'..'"), ("path:/etc/passwd", "absolute"), ("path:a\\b", "backslash"),
                             ("path:C:/x", "drive letter"), ("path:app/../x", "'..'"), ("path:app//main.py", "empty"),
                             ("path:./app", "'.'"), ("path:app/", "empty"), ("path:", "absolute"), ("path:.", "'.'")):
            with self.subTest(locator=locator):
                s = spec(locator)
                o = P.observe(s, at(self.repo.path, self.rev), ENV)
                self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                self.assertEqual(o.detail, f"locator {locator!r} refused ({fa.refusal(locator[5:])}): the tree is never escaped")
                self.assertIn(why, o.detail)
                self.assertIsInstance(run_probe(P, s, at(self.repo.path, self.rev), ENV).result, Unrunnable)
        for locator in ("path:app/main.py", "path:a", "path:..a/b..", "path:a.b/c"):
            with self.subTest(locator=locator):
                self.assertIsNone(fa.refusal(locator[5:]))

    def test_a_locator_without_the_path_prefix_or_of_another_kind_is_unsupported(self):
        for s in (spec("app/main.py"), spec("module:attr"), spec(5), spec("path:app/main.py", kind="cli_invocation")):
            locator, kind = s.probe_input["subject"]["locator"], s.probe_input["subject"]["kind"]
            with self.subTest(locator=locator, kind=kind):
                o = P.observe(s, at(self.repo.path, self.rev), ENV)
                self.assertEqual((o.kind, o.verdict), (K.UNSUPPORTED, None))
                self.assertEqual(o.detail, f"subject kind {kind!r} is not file_artifact" if kind != "file_artifact"
                                 else f"locator {locator!r} is not path:<relative posix path>")
                self.assertIsInstance(run_probe(P, s, at(self.repo.path, self.rev), ENV).result, InvalidSpec)

    def test_an_unsupported_observable_is_refused_not_degraded(self):
        for s in (spec("path:app/main.py", window=None), spec("path:app/main.py", {"condition": "absent"}),
                  spec("path:app/main.py", {"sha256": "nope"}), spec("path:app", *grep("(", 0)),
                  spec("path:app", {"matches": 0}), spec("path:app/main.py", EXISTS, {"grep": "x"})):
            with self.subTest(observable=dict(s.probe_input["observable"]), stimulus=dict(s.probe_input["stimulus"])):
                o = P.observe(s, at(self.repo.path, self.rev), ENV)
                self.assertEqual((o.kind, o.verdict), (K.UNSUPPORTED, None))
                self.assertEqual(o.detail, "observable/stimulus is not a supported class ('exists', 'content', 'grep_count') "
                                           "with a bounded window (within_s); refused, not degraded")

    def test_FM2_FILE_1_a_probe_constructed_without_git_refuses_every_observation(self):
        with mock.patch.object(fa.shutil, "which", return_value=None):
            probe = fa.FileArtifactProbe()
        self.assertIsNone(probe._git)
        s = spec("path:app/main.py", probe=probe)
        o = probe.observe(s, at(self.repo.path, self.rev), ENV)
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertIn("git absent", o.detail)
        self.assertIsInstance(run_probe(probe, s, at(self.repo.path, self.rev), ENV).result, Unrunnable)
        self.assertTrue(os.path.isabs(P._git))
        self.assertEqual((P._on_range, P._scratch), (None, None))
        hook = object()
        self.assertEqual((fa.FileArtifactProbe(on_range=hook, scratch="s")._on_range,
                          fa.FileArtifactProbe(on_range=hook, scratch="s")._scratch), (hook, "s"))

    def test_FM2_FILE_4_a_pattern_over_the_cap_is_a_harness_failure(self):
        o = P.observe(spec("path:app", *grep("a" * (fa.PATTERN_CAP + 1), 0)), at(self.repo.path, self.rev), ENV)
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertEqual(o.detail, f"grep pattern of {fa.PATTERN_CAP + 1} characters exceeds the cap of {fa.PATTERN_CAP}; refused")
        o = P.observe(spec("path:app", *grep("a" * fa.PATTERN_CAP, 0)), at(self.repo.path, self.rev), ENV)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))

    def test_a_missing_checkout_is_a_harness_failure(self):
        o = P.observe(spec("path:app/main.py"), RevisionRef(self.rev, str(pathlib.Path(self.tmp.name) / "none")), ENV)
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertIn("checkout is missing", o.detail)


class Fixtures(unittest.TestCase):
    """FA-3: the committed fixtures qualify every class with contrast and reject it once they stop contrasting;
    FA-ADV-3: an always-REFUTED probe of the same shape is not calibrated."""

    def test_every_supported_class_has_both_fixtures_asking_for_it(self):
        self.assertEqual(sorted(p.name for p in BASE.iterdir()), sorted(fa.CLASSES))
        for cls in fa.CLASSES:
            for side in ("positive", "negative"):
                d = BASE / cls / side
                with self.subTest(cls=cls, side=side):
                    self.assertTrue((d / "checkout").is_dir())
                    self.assertEqual(fa.spec_class(fixture_spec(P, d)), cls)
                    request = json.loads((d / "request.json").read_text(encoding="utf-8"))
                    self.assertEqual(names_test_artefact(request), [])
                    self.assertIsNotNone(fa.window_of(request["observable"]))
                    self.assertFalse([p for p in (d / "checkout").rglob("*") if p.name.startswith("test")])

    def test_FA_3_file_artifact_is_qualified_for_every_class_over_the_directory_read_path(self):
        env = calibration_env(sys.executable)
        for cls in fa.CLASSES:
            with self.subTest(cls=cls):
                rec = calibrate(P, cls, BASE / cls / "positive", BASE / cls / "negative", env, time.time, registry=REGISTRY)
                self.assertEqual((rec.probe_id, rec.probe_digest, rec.observation_class), (P.id, P.digest, cls))
                for side, want in (("positive", S), ("negative", R)):
                    d = BASE / cls / side
                    o = P.observe(fixture_spec(P, d), RevisionRef("0" * 40, str((d / "checkout").resolve())), env)
                    self.assertEqual((o.verdict, facts(o)["read"]), (want, "directory"))

    def test_FA_3_the_same_fixtures_reject_it_once_they_stop_contrasting(self):
        env = calibration_env(sys.executable)
        for cls in fa.CLASSES:
            with self.subTest(cls=cls):
                with self.assertRaises(NotQualified):
                    calibrate(P, cls, BASE / cls / "negative", BASE / cls / "negative", env, time.time, registry=REGISTRY)
                with self.assertRaises(NotQualified):
                    calibrate(P, cls, BASE / cls / "positive", BASE / cls / "positive", env, time.time, registry=REGISTRY)

    def test_FA_ADV_3_an_always_REFUTED_probe_of_the_same_shape_is_not_calibrated(self):
        class AlwaysRefuted(HarnessProbe):
            id, digest = fa.PROBE_ID, fa.DIGEST

            def enforcement(self):
                return Enforcement.FULL

            def harness_preconditions(self):
                return ()

            def observe(self, spec, at, env):
                return Observation(K.OBSERVED, R, detail="always")
        env = calibration_env(sys.executable)
        for cls in fa.CLASSES:
            with self.subTest(cls=cls):
                with self.assertRaisesRegex(NotQualified, "positive fixture observed"):
                    calibrate(AlwaysRefuted(), cls, BASE / cls / "positive", BASE / cls / "negative", env, time.time,
                              registry=REGISTRY)

    def test_the_directory_read_path_matches_names_exactly_and_never_follows_a_link(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-fa-") as t:
            root = pathlib.Path(t) / "checkout"
            (root / "app" / "sub").mkdir(parents=True)
            (root / "app" / "VERSION").write_bytes(V1)
            (root / "app" / "sub" / "deep.py").write_bytes(b"import telemetry\n")
            (root / "app" / "data.bin").write_bytes(b"\x00x")
            rev = RevisionRef("0" * 40, str(root))
            o = P.observe(spec("path:app/VERSION", content(sha(V1))), rev, ENV)
            self.assertEqual((o.kind, o.verdict, facts(o)["read"]), (K.OBSERVED, S, "directory"))
            o = P.observe(spec("path:app", *grep("telemetry", 1)), rev, ENV)
            self.assertEqual((o.kind, o.verdict, facts(o)["files"], facts(o)["skipped_binary"]),
                             (K.OBSERVED, S, 3, ["app/data.bin"]))
            for missing in ("path:app/version", "path:APP/VERSION", "path:app/sub/DEEP.py", "path:app/nothing"):
                with self.subTest(locator=missing):
                    o = P.observe(spec(missing), rev, ENV)
                    self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R))
            try:
                os.symlink("app", str(root / "link"))
                os.symlink("VERSION", str(root / "app" / "vlink"))
                os.symlink("sub", str(root / "app" / "sub2"))   # a link to a directory inside the walked tree
            except (OSError, NotImplementedError, AttributeError) as e:
                self.skipTest(f"symlink creation not permitted here: {e}")
            for s in (spec("path:link/VERSION"), spec("path:app/vlink", content(sha(V1))),
                      spec("path:app", *grep("1", 0)), spec("path:link", content(sha(V1))), spec("path:app/sub2/deep.py")):
                with self.subTest(locator=s.probe_input["subject"]["locator"]):
                    o = P.observe(s, rev, ENV)
                    self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                    self.assertIn("120000", o.detail)
            o = P.observe(spec("path:app", *grep("1", 0)), rev, ENV)
            self.assertIn("['app/sub2 (120000)', 'app/vlink (120000)']", o.detail)   # named, never read
            o = P.observe(spec("path:link"), rev, ENV)
            self.assertEqual((o.kind, o.verdict, facts(o)["mode"]), (K.OBSERVED, S, "120000"))
            o = P.observe(spec("path:app", *grep("telemetry", 1, [".py"])), rev, ENV)   # sub2 is a link: never walked
            self.assertEqual((o.kind, o.verdict, facts(o)["files"], facts(o)["locations"]),
                             (K.OBSERVED, S, 1, [["app/sub/deep.py", 1]]))
            self.assertEqual([r[:2] for r in fa.PlainTree(str(root)).walk("app")],
                             [("app/VERSION", "100644"), ("app/data.bin", "100644"), ("app/sub/deep.py", "100644"),
                              ("app/sub2", "120000"), ("app/vlink", "120000")])


class Tables(unittest.TestCase):
    """The pure functions and the declared tables, pinned exhaustively (kill set of the table targets)."""

    def test_observation_class_table(self):
        h = "a" * 64
        ok = [({"condition": "exists"}, {}, "exists"), ({"sha256": h}, {}, "content"),
              ({"sha256": h, "newline": "\n"}, {}, "content"), ({"sha256": h, "newline": "\r\n"}, {}, "content"),
              ({"equals_text": "x"}, {"newline": "\n"}, None), ({"equals_text": "x", "newline": "\n"}, {}, "content"),
              ({"equals_text": "", "newline": "\r\n"}, {}, "content"),
              ({"matches": 0}, {"grep": "a"}, "grep_count"), ({"matches": 3}, {"grep": "^x\\b", "suffixes": [".py"]}, "grep_count"),
              ({"matches": 3}, {"grep": "a", "suffixes": (".py", ".md")}, "grep_count"),
              ({"matches": 0}, {"grep": "a", "suffixes": []}, "grep_count")]
        bad = [({"condition": "exists"}, {"x": 1}), ({"condition": "exists", "x": 1}, {}), ({"condition": "absent"}, {}),
               ({"sha256": h}, {"x": 1}), ({"sha256": "zz"}, {}), ({"sha256": h.upper()}, {}), ({"sha256": 5}, {}),
               ({"sha256": h, "newline": "\r"}, {}), ({"newline": "\n"}, {}), ({"sha256": h, "x": 1}, {}),
               ({"equals_text": "x"}, {}), ({"equals_text": 5, "newline": "\n"}, {}),
               ({"equals_text": "x", "newline": "\n", "sha256": h}, {}), ({"equals_text": "x", "newline": "\n"}, {"x": 1}),
               ({"matches": -1}, {"grep": "a"}), ({"matches": True}, {"grep": "a"}), ({"matches": "0"}, {"grep": "a"}),
               ({"matches": 1.0}, {"grep": "a"}), ({"matches": 0}, {}), ({"matches": 0}, {"grep": ""}),
               ({"matches": 0}, {"grep": "("}), ({"matches": 0}, {"grep": 5}), ({"matches": 0}, {"grep": "a", "x": 1}),
               ({"matches": 0, "x": 1}, {"grep": "a"}), ({"matches": 0}, {"grep": "a", "suffixes": ["py"]}),
               ({"matches": 0}, {"grep": "a", "suffixes": ["."]}), ({"matches": 0}, {"grep": "a", "suffixes": [1]}),
               ({"matches": 0}, {"grep": "a", "suffixes": ".py"}), ({"matches": 0}, {"suffixes": [".py"]}), ({}, {})]
        for obs, stim, want in ok:
            with self.subTest(obs=obs, stim=stim):
                self.assertEqual(fa.observation_class({**obs, "within_s": 5}, stim), want)
                self.assertIsNone(fa.observation_class(obs, stim))   # no window: no meaning for an expired one
        for obs, stim in bad:
            with self.subTest(obs=obs, stim=stim):
                self.assertIsNone(fa.observation_class({**obs, "within_s": 5}, stim))
        for w in (0, -1, True, "5", float("inf"), float("nan"), None):
            with self.subTest(within_s=w):
                self.assertIsNone(fa.window_of({"condition": "exists", "within_s": w}))
        self.assertEqual((fa.window_of({"within_s": 5}), fa.window_of({"within_s": 0.5}), fa.window_of({})), (5.0, 0.5, None))
        self.assertIs(fa._compiles("a"), True)
        for bad in ("", "(", 5, None, "[a-"):
            with self.subTest(pattern=bad):
                self.assertIs(fa._compiles(bad), False)   # False, not merely falsy

    def test_spec_class_reads_the_subject_kind_and_the_path_prefix(self):
        self.assertEqual(fa.spec_class(spec("path:app")), "exists")
        self.assertEqual(fa.spec_class(spec("path:app", *grep("a", 0))), "grep_count")
        for s in (spec("app"), spec("path:app", kind="python_callable"), spec(3), spec("path:app", window=None)):
            with self.subTest(subject=dict(s.probe_input["subject"])):
                self.assertIsNone(fa.spec_class(s))
        self.assertEqual(REGISTRY.observation_class(fa.PROBE_ID, fa.DIGEST, spec("path:a", content("b" * 64))), "content")
        self.assertIsNone(REGISTRY.observation_class(fa.PROBE_ID, "0" * 64, spec("path:a")))

    def test_verdict_of_and_the_expected_digest(self):
        self.assertEqual(fa.verdict_of("exists", EXISTS, {"present": True}), S)
        self.assertEqual(fa.verdict_of("exists", EXISTS, {"present": False}), R)
        self.assertEqual(fa.verdict_of("exists", EXISTS, {}), R)
        h = sha(b"x\r\ny\r\n")
        self.assertEqual(fa.verdict_of("content", {"sha256": h}, {"present": True, "sha256": h}), S)
        self.assertEqual(fa.verdict_of("content", {"sha256": h}, {"present": True, "sha256": sha(b"")}), R)
        self.assertEqual(fa.verdict_of("content", {"sha256": h}, {"present": True, "kind": "tree"}), R)
        self.assertEqual(fa.verdict_of("content", {"equals_text": "x\ny\n", "newline": "\r\n"}, {"sha256": h}), S)
        self.assertEqual(fa.verdict_of("content", {"equals_text": "x\ny\n", "newline": "\n"}, {"sha256": h}), R)
        self.assertEqual(fa.expected_sha256({"sha256": h, "newline": "\n"}), h)
        self.assertEqual(fa.expected_sha256({"equals_text": "x\ny\n", "newline": "\n"}), sha(b"x\ny\n"))
        self.assertEqual(fa.verdict_of("grep_count", {"matches": 2}, {"matches": 2}), S)
        self.assertEqual(fa.verdict_of("grep_count", {"matches": 2}, {"matches": 3}), R)
        self.assertEqual(fa.verdict_of("grep_count", {"matches": 0}, {"undecodable": "f"}), R)
        self.assertEqual(fa.verdict_of("grep_count", {"matches": 0}, {"matches": 0}), S)

    def test_normalisation_and_the_content_facts(self):
        self.assertEqual(fa.normalised(b"a\r\nb\n", None), b"a\r\nb\n")
        self.assertEqual(fa.normalised(b"a\r\nb\n", "\n"), b"a\nb\n")
        self.assertEqual(fa.normalised(b"a\r\nb\n", "\r\n"), b"a\r\nb\r\n")
        self.assertEqual(fa.content_facts(b"a\r\n", {"sha256": "x"}),
                         {"present": True, "kind": "blob", "size": 3, "sha256": sha(b"a\r\n")})
        self.assertEqual(fa.content_facts(b"a\r\n", {"sha256": "x", "newline": "\n"})["sha256"], sha(b"a\n"))

    def test_grep_facts_counts_lines_skips_binary_and_names_undecodable(self):
        import re
        p = re.compile("a")
        self.assertEqual(fa.grep_facts(p, [("f", b"aa\nb\na\r\n"), ("g", b"\x00a"), ("h", b"")]),
                         {"present": True, "files": 3, "matches": 2, "skipped_binary": ["g"], "locations": [["f", 1], ["f", 3]]})
        self.assertEqual(fa.grep_facts(p, [("g", b"\x00a"), ("f", b"\xff")]), {"present": True, "undecodable": "f", "skipped_binary": ["g"]})
        many = fa.grep_facts(p, [("f", b"a\n" * 70)])
        self.assertEqual((many["matches"], len(many["locations"]), many["locations"][-1]), (70, fa._LOCATIONS, ["f", 50]))
        self.assertEqual(fa.grep_facts(p, []), {"present": True, "files": 0, "matches": 0, "skipped_binary": [], "locations": []})
        self.assertTrue(fa.selected("a/b.py", None) and fa.selected("a/b.py", []) and fa.selected("a/b.py", [".md", ".py"]))
        self.assertFalse(fa.selected("a/b.py", [".md"]) or fa.selected("a/py", [".py"]))

    def test_refusal_table(self):
        for rel, why in (("", "absolute"), ("/x", "absolute"), ("C:/x", "drive"), ("a\\b", "backslash"), ("../x", "'..'"),
                         ("a/../b", "'..'"), ("a/./b", "'.'"), ("a//b", "empty"), ("a/", "empty"), (".", "'.'"), ("..", "'..'")):
            with self.subTest(rel=rel):
                self.assertIn(why, fa.refusal(rel))
        for rel in ("a", "a/b", "..a", "a..", ".hidden/x", "a.b/c.d"):
            with self.subTest(rel=rel):
                self.assertIsNone(fa.refusal(rel))

    def test_declared_tables_identity_and_preconditions(self):
        self.assertEqual(fa.PROBE_ID, "probe.file_artifact")
        self.assertEqual(fa.PROBE_SOURCES, ("probe/protocol.py", "probe/file_artifact.py"))
        self.assertEqual(fa.CLASSES, ("exists", "content", "grep_count"))
        self.assertEqual(fa.ON_DEADLINE, {"exists": R, "content": R, "grep_count": R})
        self.assertEqual(fa.NEWLINES, ("\n", "\r\n"))
        self.assertEqual(fa.MODES, ("100644", "100755", "120000", "040000"))
        self.assertIn("object store", fa.WEAKEST_PATH)
        self.assertIn("no subject code runs", fa.WEAKEST_PATH)
        h = hashlib.sha256()
        for rel in fa.PROBE_SOURCES:
            h.update(rel.encode() + b"\0" + (ROOT / "aisef2" / rel).read_bytes().replace(b"\r\n", b"\n") + b"\0")
        self.assertEqual((fa.DIGEST, fa._probe_digest(), fa.METADATA.probe_digest, P.digest), (h.hexdigest(),) * 4)
        self.assertEqual((fa.METADATA.probe_id, fa.METADATA.observation_class, P.id), (fa.PROBE_ID, fa.spec_class, fa.PROBE_ID))
        self.assertIs(P.enforcement(), Enforcement.FULL)
        pre = P.harness_preconditions()
        self.assertEqual(len(pre), 3)
        for word in ("git", "checkout", "object store", "timeout_s", "RevisionRef.sha"):
            self.assertTrue(any(word in p for p in pre), word)

    def test_git_env_is_an_allowlist_plus_pins(self):
        with mock.patch.dict(os.environ, {"PATH": "/p", "TMPDIR": "/t", "SYSTEMROOT": "C:/W", "SystemRoot": "C:/W",
                                          "WINDIR": "C:/W", "TEMP": "/te", "TMP": "/tm", "GIT_DIR": "/evil",
                                          "HOME": "/home/x", "GIT_CONFIG_GLOBAL": "/evil/config"}, clear=True):
            env = fa.git_env("/eval")
        self.assertEqual(env, {"PATH": "/p", "TMPDIR": "/t", "SYSTEMROOT": "C:/W", "SystemRoot": "C:/W", "WINDIR": "C:/W",
                               "TEMP": "/te", "TMP": "/tm", "HOME": "/eval",
                               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.path.join("/eval", "no-global-gitconfig"),
                               "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0",
                               "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false",
                               "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0"})
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertNotIn("PATH", fa.git_env("/eval"))

    def test_the_object_store_parser_and_the_entry_walk(self):
        rows = fa.ObjectStore._parse(b"100644 blob " + b"a" * 40 + b"      12\tapp/x.py\x00" + b"040000 tree " + b"b" * 40
                                     + b"       -\tapp\x00")
        self.assertEqual(rows, [("app/x.py", "100644", "a" * 40, 12), ("app", "040000", "b" * 40, 0)])
        self.assertEqual(fa.ObjectStore._parse(b""), [])
        odd = fa.ObjectStore._parse(b"100644 blob " + b"c" * 40 + b"       3\tcaf\xe9.txt\x00")   # a name that is not UTF-8
        self.assertEqual(odd, [("caf\udce9.txt", "100644", "c" * 40, 3)])   # kept byte for byte, never replaced

        class Reader:
            """Lists like git does: the tree components it can descend and the leaf; nothing past a non-tree."""

            def __init__(self, table):
                self.table, self.asked = table, []

            def lookup(self, rel):
                self.asked.append(("lookup", rel))
                parts, out = rel.split("/"), []
                for i in range(1, len(parts) + 1):
                    p = "/".join(parts[:i])
                    if p not in self.table or (self.table[p][0] != "040000" and p != rel):
                        break
                    out.append((p, *self.table[p]))
                return out

            def entries(self, path):
                self.asked.append(("entries", path))
                return [(path, *self.table[path])] if path in self.table else []
        r = Reader({"a": ("040000", "t", 0), "a/b": ("040000", "t", 0), "a/b/c": ("100644", "o", 3), "l": ("120000", "o", 1),
                    "g": ("160000", "c", 0), "x": ("100755", "o", 2)})
        self.assertEqual(fa.entry(r, "a/b/c"), ("100644", "o", 3))
        self.assertEqual(r.asked, [("lookup", "a/b/c")])   # one listing when the leaf is there
        self.assertIsNone(fa.entry(r, "x/y"))   # through an executable blob: not in the tree either
        self.assertEqual(fa.entry(r, "a/b"), ("040000", "t", 0))
        self.assertIsNone(fa.entry(r, "a/b/d"))
        self.assertIsNone(fa.entry(r, "x/y"))
        self.assertIsNone(fa.entry(r, "a/nothing/deeper"))
        self.assertEqual(r.asked[-1], ("entries", "a/nothing"))
        with self.assertRaisesRegex(fa.Refused, "component 'l'.*120000, a symlink: a link is never followed"):
            fa.entry(r, "l/c")
        self.assertIsNone(fa.entry(r, "a/b/c/d"))   # through a blob: not in the tree, not an escape
        with self.assertRaisesRegex(fa.Refused, "component 'g'.*mode 160000"):
            fa.entry(r, "g/x/y")
        with self.assertRaisesRegex(fa.Refused, "over the per-file cap"):
            fa.read(r, "big", "o", fa.FILE_CAP + 1)


class Catalog(unittest.TestCase):
    """FA-Q0: the catalog entry and the Q0 probe rules over the module source."""

    def test_FA_Q0_the_probe_passes_the_probe_source_rules_and_is_registered_closed(self):
        import importlib.util
        s = importlib.util.spec_from_file_location("aisef_v2_probe_static_checks_c2", ROOT / "validation" / "v2" / "probe_static_checks.py")
        ps = importlib.util.module_from_spec(s)
        s.loader.exec_module(ps)
        src = (ROOT / "aisef2" / "probe" / "file_artifact.py").read_text(encoding="utf-8")
        self.assertEqual(ps.violations("aisef2/probe/file_artifact.py", src, ps.SOURCE_RULES,
                                       {"subject_process": "in_harness_process", "stimulus_shape": "none"}), [])
        self.assertEqual(ps.child_scripts(__import__("ast").parse(src)), [])   # no child script: nothing runs the subject
        self.assertEqual(ps.check(ROOT), [])
        e = entry_for("aisef2/probe/file_artifact.py")
        self.assertIsNotNone(e)
        self.assertEqual((e.probe_id, e.probe_digest, e.subject_kind, e.classes, e.metadata, e.factory, e.fixture_root,
                          e.subject_process, e.protocol_channel, e.stimulus_shape, e.cycle, e.active),
                         (fa.PROBE_ID, fa.DIGEST, SubjectKind.FILE_ARTIFACT, fa.CLASSES, fa.METADATA, fa.FileArtifactProbe,
                          "file_artifact", "in_harness_process", "captured_stdout", "none", 2, True))
        self.assertEqual([x.probe_id for x in CATALOG if x.subject_kind is SubjectKind.FILE_ARTIFACT], [fa.PROBE_ID])
        self.assertEqual(names_test_artefact([str(v) for v in vars(fa).values() if isinstance(v, (str, tuple, dict))]), [])


if __name__ == "__main__":
    unittest.main()
