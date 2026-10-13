"""V2.1 (B-03 round 3, WP client): the other readers of `aisef2/app/` that split a text at what `str.splitlines()` splits
at, and what each decided with the pieces.

`str.splitlines()` ends a line at U+2028, U+2029, U+0085, U+000B, U+000C and U+001C-U+001E as well as at a line feed.
The operating system and git print U+2028, U+2029 and U+0085 raw inside a path, so a path that holds one was two
"lines". The readers below were checked one by one (docs/v2.1/decisions/B03-R3-CLIENT.md, section 4); these are the
three that decided something from the pieces, and the one that is pinned because its writer, not its reader, is what
keeps it safe:

* `WorktreeListing`   — `lineage.reconcile` reads `git worktree list --porcelain`: a kernel worktree whose path holds a
  separator was not found, and with it the unjournaled candidate it holds (the item a continuation must name); and
  what the item says to the operator.
* `MergeStatement`   — the same function's other item, the merge in flight, and what it says (the listing of `main`'s
  first parents is hex only: not exposed; asserted because `reconcile` was changed and its statements are read).
* `ProbeOutput`       — `confine._sections` / `_mounts` / `_judge`: a mount point, a socket or a name the probe prints
  with a separator was two rows; a writable mount outside the workspace whose path holds one was not judged at all.
* `HostTable`         — `confine._host_mounts`: a host mount point with one made the whole table "not read whole", so
  every pseudo mount of the sandbox was "not established" and the run was refused.
* `Lines`             — `confine._lines`, the one reading of both.
* `PreflightLedger`   — `preflight.accounting` reads what `preflight._append` writes with ASCII escapes: no raw
  separator can be in the ledger; pinned through `preflight.run` so a writer that stops escaping fails here first."""

from __future__ import annotations

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

from aisef2.app import confine, lineage, preflight  # noqa: E402
from aisef2.journal import event as ev  # noqa: E402
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402

SEPARATORS = (("U+2028", " "), ("U+2029", " "), ("U+0085", "\u0085"))
M = confine.MARK


def git(cwd, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", env=env,
                          check=True).stdout.strip()


class WorktreeListing(unittest.TestCase):
    """Requirement: `reconcile` names the candidate a kernel worktree (`wt-<open story>`) holds, whatever characters
    the worktree's path holds — it reads `git worktree list --porcelain` by lines that end at a line feed. Before: a
    path that held U+2028, U+2029 or U+0085 anywhere (the run directory's, the temporary root's) was cut there, the
    worktree's name was the cut piece's, and the unjournaled candidate was not reported."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))

    def run_dir_with_candidate(self, label: str, parent: pathlib.Path) -> tuple[pathlib.Path, str, str]:
        """(run directory, baseline, candidate): `repo` on main holding one commit, and the commit of a branch main does
        not hold checked out as `<parent>/wt-S1`."""
        run_dir = self.tmp / f"run-{label}"
        repo = run_dir / "repo"
        repo.mkdir(parents=True)
        git(repo, "init", "-q", "-b", "main")
        (repo / "base.txt").write_text("base\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        base = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "-b", "cand")
        (repo / "cand.txt").write_text("candidate\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "candidate")
        head = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "main")
        git(repo, "worktree", "add", "-q", "--detach", str(parent / "wt-S1"), head)
        return run_dir, base, head

    def reconciled(self, label: str, parent: pathlib.Path) -> tuple[list[dict], str, str]:
        run_dir, base, head = self.run_dir_with_candidate(label, parent)
        events = [ev.Event(0, "story/begin", {"story_id": "S1", "parent": base}, 0.0)]
        return lineage.reconcile(run_dir, events, base, False)["items"], head, git(run_dir / "repo", "worktree", "list",
                                                                                   "--porcelain")

    def test_a_worktree_under_a_directory_whose_name_holds_a_separator_is_found(self):
        for label, sep in SEPARATORS:
            with self.subTest(separator=label):
                parent = self.tmp / f"root{sep}tail-{label}"
                try:
                    parent.mkdir()
                except OSError as e:
                    self.skipTest(f"this file system holds no {label} in a name: {e}")
                items, head, listing = self.reconciled(label, parent)
                if sep not in listing:
                    self.skipTest(f"this git does not print {label} raw in `worktree list --porcelain`")
                self.assertEqual([(i["commit"], i["operation"], i["story"], i["identified"]) for i in items],
                                 [(head, "candidate", "S1", True)])

    def test_the_same_worktree_under_an_ordinary_path_is_found_too(self):
        parent = self.tmp / "ordinary"
        parent.mkdir()
        items, head, _ = self.reconciled("ordinary", parent)
        self.assertEqual([(i["commit"], i["operation"], i["story"], i["identified"]) for i in items],
                         [(head, "candidate", "S1", True)])

    def test_the_item_says_whose_candidate_where_and_what_the_continuation_does_with_it(self):
        """What the operator reads (`aisef bundle continue` prints the items): the story, the kernel's worktree by name,
        that no proof ran on it, and that the story is developed again."""
        parent = self.tmp / "ordinary"
        parent.mkdir()
        items, _, _ = self.reconciled("ordinary", parent)
        [why] = [i["why"] for i in items]
        self.assertIn("the developer's candidate of S1", why)
        self.assertIn("in the kernel's worktree wt-S1", why)
        self.assertIn("never journaled (no proof ran on it): developed again", why)


class MergeStatement(unittest.TestCase):
    """Requirement: a merge the kernel started and did not journal is stated with its story, its proved candidate and
    what is missing of it — the operator reads this to decide whether to leave the item out of the continuation
    (`reconcile` identifies it through the same listing of `main`'s first parents the worktree scan follows)."""

    def test_the_kernels_merge_in_flight_is_stated(self):
        with tempfile.TemporaryDirectory() as t:
            run_dir = pathlib.Path(os.path.realpath(t)) / "run-dir"
            repo = run_dir / "repo"
            repo.mkdir(parents=True)
            git(repo, "init", "-q", "-b", "main")
            (repo / "base.txt").write_text("base\n", encoding="utf-8")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "base")
            base = git(repo, "rev-parse", "HEAD")
            git(repo, "checkout", "-q", "-b", "s2", base)
            (repo / "s2.txt").write_text("candidate\n", encoding="utf-8")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "candidate")
            cand = git(repo, "rev-parse", "HEAD")
            git(repo, "checkout", "-q", "main")
            git(repo, "merge", "-q", "--no-ff", "-m", f"merge {cand[:12]}", "s2")
            events = [ev.Event(0, "story/begin", {"story_id": "S2", "parent": base}, 0.0),
                      ev.Event(1, "proof/verified", {"story_id": "S2", "criterion_id": "C1", "candidate": cand}, 0.0)]
            [item] = lineage.reconcile(run_dir, events, base, False)["items"]
        self.assertEqual((item["operation"], item["story"], item["candidate"], item["identified"]), ("merge", "S2", cand, True))
        self.assertIn("the kernel's merge of S2", item["why"])
        self.assertIn(f"'s proved candidate {cand[:12]}", item["why"])
        self.assertIn("its post-merge proof and commit were never journaled", item["why"])


class ProbeOutput(unittest.TestCase):
    """Requirement: the probe's output is read by lines that end at a line feed. A mount point, a socket path or a
    name that holds U+2028, U+2029 or U+0085 is one row, one list entry, whole — and the judgement sees the mount: a
    writable host file system mounted at such a path is refused as one at any other path is."""

    def test_a_mount_point_a_name_and_a_socket_that_hold_a_separator_are_one_entry_each(self):
        for label, sep in SEPARATORS:
            with self.subTest(separator=label):
                mount = f"/srv/a{sep}b"
                out = "\n".join([
                    f"{M}uid 1000", f"{M}section mountinfo", f"41 1 8:2 /srv {mount} rw,relatime - ext4 /dev/vdb rw",
                    f"{M}section home", f".cache{sep}x", f"{M}section sockets", f"/w/ws/run{sep}ctl.sock",
                    f"{M}sockets listed", f"{M}end", ""])
                values, sections, _ = confine._sections(out)
                self.assertEqual(sections["mountinfo"], [f"41 1 8:2 /srv {mount} rw,relatime - ext4 /dev/vdb rw"])
                self.assertEqual(sections["home"], [f".cache{sep}x"])
                self.assertEqual(sections["sockets"], [f"/w/ws/run{sep}ctl.sock"])
                self.assertEqual(values, {"uid": "1000", "sockets": "listed", "end": ""})
                [row] = confine._mounts(sections["mountinfo"])
                self.assertEqual((row["at"], row["access"], row["fs"]), (mount, "rw", "ext4"))

    def judged(self, lines: list[str], targets: list[str]) -> list[str]:
        ws = pathlib.PurePosixPath("/w/ws")
        rep = {"network": "host", "created_outside_workspace": {}, "setsid_survivors": [], "host_mounts": rows.HOST,
               "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0"),
                          "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                          "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                          "mounts": confine._mounts(lines), "mount_targets": targets}}
        tries = {"read_canary": (1, ""), "workspace": (0, "ok"), "read_git_directory": (0, "ref: x"),
                 "user_namespace": (1, "unshare failed: No space left on device")}
        return confine._judge(rep, "tok", "", tries, "/nonexistent", ws)

    def test_a_writable_host_mount_whose_path_holds_a_separator_is_refused_like_any_other(self):
        for label, sep in SEPARATORS:
            for name in (f"data{sep}disk", "data-disk"):
                with self.subTest(separator=label, name=name):
                    out = "\n".join([f"{M}section mountinfo", "1 0 0:30 / / rw,nosuid - tmpfs tmpfs rw",
                                     "26 1 8:1 /ws /w/ws rw,relatime - ext4 /dev/vda1 rw",
                                     f"41 1 8:2 /d /w/ws/{name} rw,relatime - ext4 /dev/vdb rw", f"{M}end", ""])
                    _, sections, _ = confine._sections(out)
                    said = self.judged(sections["mountinfo"], ["/w/ws"])
                    self.assertEqual(len(said), 1, said)
                    self.assertTrue(said[0].startswith("writable outside the workspace"), said)
                    self.assertIn(repr(f"/w/ws/{name}"), said[0])     # the refusal names the mount, as a list of paths


class HostTable(unittest.TestCase):
    """Requirement: the host's mount table is read by lines that end at a line feed: a host mount point that holds
    U+2028, U+2029 or U+0085 is one row of it. Before: it was two lines, neither a row, and the table was "not read
    whole" (None): no pseudo mount of any session could be shown to be the sandbox's own, so the run was refused."""

    def read(self, text: str):
        with mock.patch.object(confine.pathlib.Path, "read_text", lambda path, encoding=None, errors=None, **k: text):
            return confine._host_mounts()

    def test_a_host_mount_point_that_holds_a_separator_is_one_row(self):
        for label, sep in SEPARATORS:
            with self.subTest(separator=label):
                table = "\n".join(["1 0 8:1 / / rw,relatime - ext4 /dev/vda1 rw",
                                   f"300 1 0:46 / /mnt/usb{sep}stick rw,nosuid shared:7 - tmpfs tmpfs rw", ""])
                self.assertEqual(self.read(table), [
                    {"at": "/", "fs": "ext4", "dev": "8:1", "optional": []},
                    {"at": f"/mnt/usb{sep}stick", "fs": "tmpfs", "dev": "0:46", "optional": ["shared:7"]}])

    def test_a_table_with_a_line_that_is_no_row_is_still_not_read_whole(self):
        for table in ("1 0 8:1 / / rw - ext4 /dev/vda1 rw\n\n2 0 8:2 / /b rw - ext4 /dev/vda2 rw\n",
                      "1 0 8:1 / / rw - ext4 /dev/vda1 rw\nnot a row\n", "\n", ""):
            with self.subTest(table=table):
                self.assertIsNone(self.read(table))


class Lines(unittest.TestCase):
    """Requirement: `confine._lines` ends a line at a line feed and nowhere else; a text that ends with one has no
    empty line after it (what `splitlines()` did for it), and a blank line inside a text is a line."""

    def test_lines(self):
        for text, expected in (("a\nb\n", ["a", "b"]), ("a\nb", ["a", "b"]), ("", []), ("\n", [""]), ("a\n\nb\n", ["a", "", "b"]),
                               ("a\n\n", ["a", ""]),
                               ("a b c\u0085d\x0be\x0cf\x1cg\x1dh\x1ei\n", ["a b c\u0085d\x0be\x0cf\x1cg\x1dh\x1ei"])):
            with self.subTest(text=text):
                self.assertEqual(confine._lines(text), expected)


class PreflightLedger(unittest.TestCase):
    """Requirement: the preflight's ledger holds no raw U+2028, U+2029 or U+0085 whatever an answer's failure text
    holds, and `accounting` reads it back whole: its reader cuts by `splitlines()` and raises on a line that does not
    parse, so what keeps a cut from ever happening is that `_append` writes ASCII (`json.dumps`'s default)."""

    def test_a_failure_text_with_separators_is_written_escaped_and_read_back(self):
        answers = {"/models": (200, {"data": [{"id": "m", "owned_by": "o"}]}),
                   "/chat/completions": (502, {"transport_error": "Bad Gateway", "content_type": "text/ html\u0085"})}
        with tempfile.TemporaryDirectory() as t:
            rec = preflight.run("p/m", 1, lambda path, body=None: answers[path], pathlib.Path(t) / "pf")
            data = (pathlib.Path(t) / "pf" / "LEDGER.jsonl").read_bytes()
        for raw in (" ", " ", "\u0085"):
            self.assertNotIn(raw.encode("utf-8"), data)
        self.assertEqual(data.count(b"\n"), 4)                       # sent, done, sent, done
        self.assertEqual(rec["accounting"], {"provider_requests": 2, "turns": 0, "input_tokens": 0, "output_tokens": 0,
                                             "unaccounted": []})


if __name__ == "__main__":
    unittest.main()
