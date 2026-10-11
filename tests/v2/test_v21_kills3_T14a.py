"""V2.1 mutation-survivor batch T14a (aisef2/app/run.py: the evidence manifest, the anchor and the repository check).

What an operator of `aisef run` relies on, and what each class pins:

* the anchor is a value the operator keeps OUTSIDE the run directory and checks later, under a later release
  (`aisef run --verify --expect-anchor`; verify.py already verifies runs of older releases). So the serialisation the
  anchor is the digest of is part of its definition, and the record's digest must not depend on how the record happens
  to be formatted (docs/v2.1/ANCHOR-THREAT-MODEL.md: "JSON chuan hoa"): `RecordDigest`, `AnchorValue`;
* `anchor_in` reads the manifest a killed or disk-full run may have left empty or torn: no manifest is `None`, never a
  traceback (`aisef run --parent`, `aisef bundle continue`): `AnchorOfAnUnreadableManifest`;
* the manifest binds the record, RUN.started.json, the journal, every session stream and the preflight's files, and
  nothing else (CONTINUED-BY.json is written into the directory later, by another run): `ManifestMembers`,
  `ManifestShape`, and — through `verify` on a real run — `OneFileChangedAlone`;
* a refusal of `--check`/`--repo` names its cause, so the operator knows what to fix: `RepositoryRefusalCauses`.

Offline: no client, no provider, no network. The one real run is made by the fake client of test_app_run (POSIX)."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, lineage, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from tests.v2 import test_app_run as base  # noqa: E402


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def put(root: pathlib.Path, rel: str, data: bytes) -> pathlib.Path:
    p = root / pathlib.PurePosixPath(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


class _Dir(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.out = pathlib.Path(t.name).resolve()


#: One record, three ways of writing it down: indented with sorted keys (what `execute` writes), compact with the keys
#: the other way round, and indented with CRLF line ends (an editor's save). Written as bytes: no newline translation.
RECORD = {"b": "x", "a": [1, 2]}
THREE_WAYS = (
    (json.dumps(RECORD, indent=1, sort_keys=True) + "\n").encode("utf-8"),
    json.dumps(RECORD, separators=(",", ":")).encode("utf-8"),
    json.dumps(RECORD, indent=4).replace("\n", "\r\n").encode("utf-8"),
)
#: the record's canonical JSON, spelled out: sorted keys, no whitespace
CANONICAL = b'{"a":[1,2],"b":"x"}'


class RecordDigest(_Dir):
    """The manifest's entry for RUN.json is the digest of its canonical JSON: a re-serialised identical record is the
    same record, a changed value is not — and the other files are bound byte for byte.

    Pins aisef2/app/run.py::_content_sha [0, 2, 3, 5, 6, 7, 8, 9]: which file is canonicalised, that its keys are
    sorted, and the separators (compact; an emptied item separator makes [1, 2] and [12] one record; the digest is
    spelled out because an operator's anchor is taken over it)."""

    def entry(self, rel: str, data: bytes) -> str:
        put(self.out, rel, data)
        return R.evidence_manifest(self.out)["files"][rel]

    def test_one_record_written_three_ways_has_one_digest_and_it_is_the_canonical_form_s(self):
        for i, data in enumerate(THREE_WAYS):
            with self.subTest(way=i):
                self.assertEqual(self.entry("RUN.json", data), sha(CANONICAL))

    def test_a_changed_value_is_another_record(self):
        original = self.entry("RUN.json", THREE_WAYS[1])
        changed = self.entry("RUN.json", json.dumps({"a": [12], "b": "x"}).encode("utf-8"))
        # [1, 2] and [12] are two records: one digest for both (an item separator left out of the canonical text)
        # would let a changed value pass as the same record
        self.assertNotEqual(changed, original)
        self.assertEqual(changed, sha(b'{"a":[12],"b":"x"}'))

    def test_every_other_file_is_bound_by_its_bytes(self):
        for rel in ("RUN.started.json", "preflight/PREFLIGHT.json"):
            with self.subTest(rel):
                digests = [self.entry(rel, data) for data in THREE_WAYS]
                self.assertEqual(digests, [sha(data) for data in THREE_WAYS])
                self.assertEqual(len(set(digests)), 3)


class AnchorValue(unittest.TestCase):
    """The evidence anchor is the sha256 of the manifest's canonical JSON — sorted keys, compact separators, UTF-8 —
    which the operator keeps and later passes as `--expect-anchor`; an anchor kept from one release must be the value
    a later release derives. The expected digest is computed here from the spelled-out text, not by json.dumps.

    Pins aisef2/app/run.py::anchor_of [5, 6]."""

    MANIFEST = {"format": "aisef-v2-evidence/1", "files": {"RUN.started.json": "b" * 64, "RUN.json": "a" * 64}}
    TEXT = ('{"files":{"RUN.json":"' + "a" * 64 + '","RUN.started.json":"' + "b" * 64 + '"},'
            '"format":"aisef-v2-evidence/1"}').encode("utf-8")

    def test_the_anchor_of_a_manifest_is_the_digest_of_its_canonical_text(self):
        self.assertEqual(R.anchor_of(self.MANIFEST), sha(self.TEXT))


class AnchorOfAnUnreadableManifest(_Dir):
    """A run killed (SIGKILL, ENOSPC) at its last write leaves EVIDENCE.json created and empty or torn; the next
    `aisef run --parent` / `aisef bundle continue` must find "no manifest" (None), not a traceback. A whole manifest's
    anchor is `anchor_of` of it.

    Pins aisef2/app/run.py::anchor_in [2] (the not-JSON and not-UTF-8 arm; the absent file is held elsewhere)."""

    def test_a_manifest_that_is_empty_torn_or_not_text_is_no_manifest(self):
        for name, data in (("empty", b""), ("torn", b'{"files": {"RUN.js'), ("not utf-8", b"\xff\xfe")):
            with self.subTest(name):
                put(self.out, R.MANIFEST, data)
                self.assertIsNone(R.anchor_in(self.out))

    def test_a_whole_manifest_has_its_anchor(self):
        put(self.out, R.MANIFEST, (json.dumps(AnchorValue.MANIFEST, indent=1, sort_keys=True) + "\n").encode("utf-8"))
        self.assertEqual(R.anchor_in(self.out), sha(AnchorValue.TEXT))


class ManifestMembers(_Dir):
    """The manifest holds the sha256 of every file a verification re-derives from — the record, RUN.started.json, the
    journal, each session stream, the preflight's ledger and observation — by its path relative to the run directory,
    and of nothing else: the repository, and CONTINUED-BY.json (written into this directory later, by a run that
    continues it) are not members.

    Pins aisef2/app/run.py::evidence_manifest [1, 2, 3, 5, 10, 17, 20]."""

    MEMBERS = {
        "RUN.json": b'{"format":"aisef-v2-run-record/1"}',     # already canonical: its digest is that of these bytes
        "RUN.started.json": b'{"started": 1.0}\n',
        "run/journals/aisef-run.jsonl": b'{"seq": 0, "type": "run/begin"}\n',     # one JSON line: still bound as bytes
        "sessions/developer.S1.jsonl": b'{"type": "step_finish"}\n{"type": "text"}\n',
        "preflight/LEDGER.jsonl": b'{"request": 1}\n',
        "preflight/PREFLIGHT.json": b'{"verdict": "ATTESTED"}\n',
    }
    NOT_MEMBERS = {
        "EVIDENCE.json": b"{}\n",
        "CONTINUED-BY.json": b'{"run": "elsewhere"}\n',
        "repo/app/calc.py": b"def sub(a, b):\n    return a - b\n",
    }

    def test_each_member_is_bound_and_a_non_member_is_not(self):
        for rel, data in {**self.MEMBERS, **self.NOT_MEMBERS}.items():
            put(self.out, rel, data)
        files = R.evidence_manifest(self.out)["files"]
        self.assertEqual(files, {rel: sha(data) for rel, data in self.MEMBERS.items()})


class ManifestShape(_Dir):
    """EVIDENCE.json is a document of two keys: `format` (what this file is, `MANIFEST_FORMAT`) and `files`. The
    anchor is taken over the whole document, so a manifest without its format tag is another anchor.

    Pins aisef2/app/run.py::evidence_manifest [6, 8]."""

    def test_the_manifest_is_its_format_tag_and_its_files(self):
        put(self.out, "RUN.json", b"{}")
        m = R.evidence_manifest(self.out)
        self.assertEqual(sorted(m), ["files", "format"])
        self.assertEqual(m["format"], R.MANIFEST_FORMAT)
        self.assertEqual(m["files"], {"RUN.json": sha(b"{}")})


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class OneFileChangedAlone(unittest.TestCase):
    """A finished run's record and evidence files are bound by EVIDENCE.json (verify.py: "the record and every evidence
    file are bound by EVIDENCE.json"). Changing ONE of them — in a field `verify` does not re-derive — is refuted, and
    the problem names that file; and when the manifest is re-made to agree, the anchor the run printed refutes it.
    RUN.started.json is what `lineage.predecessor_of` follows (a redirected `continues.path` changes whose spend a
    continuation counts); PREFLIGHT.json is data nothing else re-derives: the manifest is the only thing that sees
    either change.

    Pins aisef2/app/run.py::evidence_manifest [1, 2, 3, 5, 6, 8, 10, 17, 20] at the reader, `verify`."""

    FILES = ("RUN.json", "RUN.started.json", R.MANIFEST, "preflight/PREFLIGHT.json")

    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        cls.tmp = pathlib.Path(t.name).resolve()
        cls.project = bundle.load(base.project_bundle(base.make_repo(cls.tmp / "source")))
        client = cls.tmp / "client" / "opencode"
        client.parent.mkdir()
        client.write_text(f"#!{sys.executable}\nADD = {base.ADD!r}\nTEST = {base.TEST!r}\n" + base.FAKE_CLIENT)
        client.chmod(0o755)
        (client.parent / "mode").write_text("write")
        for patch in (mock.patch.object(ad, "scanner", lambda: ad.NoScanner()),
                      mock.patch.dict(os.environ, base.client_config(cls.tmp))):
            patch.start()
            cls.addClassCleanup(patch.stop)
        cls.out = cls.tmp / "out"
        R.execute(cls.project, settings.load(base.SETTINGS), cls.tmp / "source", cls.out, client_exe=str(client),
                  transport=base.provider(), cals=base.calibrations())
        cls.anchor = R.anchor_in(cls.out)
        cls.original = {rel: (cls.out / pathlib.PurePosixPath(rel)).read_bytes() for rel in cls.FILES}

    def setUp(self) -> None:     # one run for the class: each test puts the directory back as the run left it
        self.addCleanup(self.restore)

    def restore(self) -> None:
        for rel, data in self.original.items():
            (self.out / pathlib.PurePosixPath(rel)).write_bytes(data)
        (self.out / "run" / "journals" / "stray.jsonl").unlink(missing_ok=True)

    def rewrite(self, rel: str, **fields) -> None:
        p = self.out / pathlib.PurePosixPath(rel)
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc.update(fields)
        p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    def refuted_naming(self, rel: str) -> None:
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertTrue(any(rel in p for p in v["problems"]), (rel, v["problems"]))
        (self.out / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(self.out), indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")
        v = verify(self.project, self.out, expect_anchor=self.anchor)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertTrue(any("anchor" in p for p in v["problems"]), (rel, v["problems"]))

    def test_the_untouched_run_verifies_against_its_anchor_and_the_manifest_is_the_two_keys(self):
        self.assertEqual(len(self.anchor or ""), 64)     # a missing anchor would make the next line skip the check
        self.assertEqual(verify(self.project, self.out, expect_anchor=self.anchor)["verdict"], "VERIFIED")
        written = json.loads((self.out / R.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(sorted(written), ["files", "format"])
        self.assertEqual(written["format"], R.MANIFEST_FORMAT)
        self.assertIn("run/journals/aisef-run.jsonl", written["files"])

    def test_a_manifest_in_the_documented_shape_is_this_run_s_manifest(self):
        # spelled by hand, not made by evidence_manifest: the `format` tag and the `files`, as another process of
        # this release writes them. verify compares the whole document and the anchor is taken over all of it, so a
        # manifest that is not written with the tag (or under another key) refutes every run an earlier one wrote.
        stored = json.loads((self.out / R.MANIFEST).read_text(encoding="utf-8"))
        (self.out / R.MANIFEST).write_text(
            json.dumps({"format": R.MANIFEST_FORMAT, "files": stored["files"]}, indent=1, sort_keys=True) + "\n",
            encoding="utf-8")
        self.assertEqual(verify(self.project, self.out, expect_anchor=self.anchor)["verdict"], "VERIFIED")

    def test_the_record_changed_alone_is_refuted(self):
        self.rewrite("RUN.json", kernel_digest="0" * 64)
        self.refuted_naming("RUN.json")

    def test_the_started_file_changed_alone_is_refuted(self):
        elsewhere = str(self.tmp / "another-run")
        self.rewrite("RUN.started.json", continues={"path": elsewhere, "evidence_anchor": None})
        self.assertEqual(lineage.predecessor_of(self.out), pathlib.Path(elsewhere))     # the reader follows it
        self.refuted_naming("RUN.started.json")

    def test_the_preflight_observation_changed_alone_is_refuted(self):
        self.rewrite("preflight/PREFLIGHT.json", verdict="OPAQUE")
        self.refuted_naming("preflight/PREFLIGHT.json")

    def test_a_journal_that_appeared_beside_the_run_s_is_refuted(self):
        put(self.out, "run/journals/stray.jsonl", b'{"seq": 0}\n')
        self.refuted_naming("run/journals/stray.jsonl")


class RepositoryRefusalCauses(_Dir):
    """`aisef run` / `--check` refuses a `--repo` it cannot use with the cause the operator must act on: the path is
    not a directory (point at one), the project repository could not be cloned (git's own words say why), or the
    clone lacks the baseline (a different message). One refusal is never read as another.

    Pins aisef2/app/run.py::check_repository [31, 37]."""

    def setUp(self) -> None:
        super().setUp()
        self.project = bundle.load(base.project_bundle("a" * 40))

    def refusal(self, repo: pathlib.Path) -> str:
        with self.assertRaises(R.RunRefused) as c:
            R.check_repository(self.project, repo)
        return str(c.exception)

    def test_a_path_that_is_not_a_directory_is_refused_as_that(self):
        a_file = put(self.out, "a-file", b"x")
        for repo in (self.out / "absent", a_file):
            with self.subTest(repo.name):
                msg = self.refusal(repo)
                self.assertIn(str(repo), msg)
                self.assertIn("not a directory", msg)
                self.assertNotIn("does not hold", msg)

    def clone_refused_with(self, stderr: str) -> str:
        def clone_fails(cwd, *args):
            self.assertEqual(args[0], "clone")
            return subprocess.CompletedProcess(["git", *args], 128, "", stderr)
        with mock.patch.object(R, "git", clone_fails):
            return self.refusal(self.out)

    def test_a_clone_git_refuses_is_refused_as_a_failed_clone_with_git_s_words(self):
        msg = self.clone_refused_with("fatal: no such repository here\n")
        self.assertIn("clone", msg)
        self.assertIn("fatal: no such repository here", msg)
        self.assertNotIn("does not hold", msg)

    def test_a_clone_that_failed_without_a_word_still_names_the_failed_step(self):
        self.assertIn("clone", self.clone_refused_with(""))     # git killed by a signal says nothing: never a bare refusal

    def test_a_directory_that_is_not_a_repository_carries_git_s_own_refusal(self):
        with mock.patch.dict(os.environ, {"LC_ALL": "C"}):     # git's own words are translated ("fatal:" is, in de)
            msg = self.refusal(self.out)
        self.assertIn("clone", msg)
        self.assertIn("fatal", msg)     # git's own word for why: `fatal: repository '...' does not exist`
        self.assertNotIn("does not hold the plan's baseline", msg)


if __name__ == "__main__":
    unittest.main()
