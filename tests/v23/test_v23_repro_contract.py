"""BUILD-REPRO-01 / CODE-AUDIT #7: the explicit reproducibility contract, every clause tested (docs/v2.3/W1-DESIGN.md
§6; COMPATIBILITY-MATRIX CT-8, CT-9). The text is docs/v2.3/drafts/BUILD-REPRO-CONTRACT.md. Each clause is tested here
or by staging.yml's `repro` job, and this module pins that job, so the text cannot claim more than CI runs.

The measured root cause (RISK-REGISTER BUILD-REPRO-01): setuptools takes each sdist member's mode from the filesystem,
git records only 100644 / 100755, and repro_dist kept the mode, so a tree whose files carried other permission bits
built another sdist. The wheel too, for package data and dist-info/LICENSE (L1B-R1; RISK-REGISTER's "the wheel is
immune" held only for .py modules). repro_dist now writes git's mode into both.
"""

from __future__ import annotations

import contextlib
import gzip
import io
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import types
import unittest
import zipfile
import zlib
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import release_rc as rc  # noqa: E402
from validation.qualification import repro_dist as R  # noqa: E402

EPOCH = 1_790_000_000
FREEZE = ROOT / "closure-evidence/v2/release/V2.2.0-RC2-FREEZE.json"
CONTRACT = ROOT / "docs/v2.3/drafts/BUILD-REPRO-CONTRACT.md"
STAGING = ROOT / ".github/workflows/staging.yml"
INTERPRETERS = ["3.11", "3.12", "3.13", "3.14"]   # narrowing this is an explicit contract amendment (W1-DESIGN §6)


def _git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


def _tar(members) -> bytes:
    """A gzipped PAX tar (what setuptools writes) of (name, mode, data; None = a directory), in the given order."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as t:
        for name, mode, data in members:
            info = tarfile.TarInfo(name)
            info.mode, info.mtime = mode, 1_800_000_000
            if data is None:
                info.type = tarfile.DIRTYPE
            else:
                info.size = len(data)
            t.addfile(info, None if data is None else io.BytesIO(data))
    return gzip.compress(buf.getvalue(), mtime=0)


def _wheel(members) -> bytes:
    """A wheel as the wheel writer makes one, of (name, mode): a member copied from a file carries S_IFREG and the
    file's mode; RECORD carries the writer's constant 0o664 (measured: setuptools 58.0.4 / 65.5.0, wheel 0.37.0)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, mode in members:
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 21, 0, 0, 0))
            info.external_attr = (mode if name.endswith("/RECORD") else stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, name.encode())
    return buf.getvalue()


def _members(tar: bytes, mode_of) -> list:
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        return [(m.name, mode_of(m), t.extractfile(m).read() if m.isfile() else None) for m in t.getmembers()]


def _perturbed(m: tarfile.TarInfo) -> int:
    """What a working tree with other permission bits gives (the execute bit kept: changing it is another source)."""
    return 0o700 if m.isdir() or m.mode & 0o111 else 0o600


def _job(text: str, name: str) -> str | None:
    """One job of a workflow, its comment lines dropped: an explanation is not a configuration."""
    m = re.search(rf"\n  {re.escape(name)}:\n(.*?)(?=\n  [A-Za-z_][\w-]*:|\Z)", text, re.S)
    return None if m is None else "\n".join(ln for ln in m.group(1).split("\n") if not ln.lstrip().startswith("#"))


def _runs(job: str) -> list[list[str]]:
    """Each `run:` of a job as its command lines: a block scalar's body, or the one-line value."""
    lines, runs = job.split("\n"), []
    for i, ln in enumerate(lines):
        m = re.match(r"( *)(?:- +)?run: *(.*)$", ln)
        if m is None:
            continue
        if m.group(2)[:1] not in ("|", ">"):
            runs.append([m.group(2)])
            continue
        body = []
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= len(m.group(1)):
                break
            body.append(nxt.strip())
        runs.append([b for b in body if b])
    return runs


def _contract() -> str:
    """The contract paragraph: the draft's first block quote, its lines joined."""
    lines = CONTRACT.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(">"))
    block = []
    for ln in lines[start:]:
        if not ln.startswith(">"):
            break
        block.append(ln[1:].strip())
    return " ".join(block)


def _matrix(job: str) -> list[str] | None:
    m = re.search(r"matrix:\s*\n\s+python-version:\s*(\[[^\]]*\]|(?:\n\s+-\s*\S+)+)", job)
    return None if m is None else re.findall(r"3\.\d+", m.group(1))


class ModeNormalisation(unittest.TestCase):
    """W1-DESIGN §6: two sdists differing only in member modes re-pack to identical bytes, 0600 -> 0644, a 0700
    directory -> 0755, an executable -> 0755, and the execute bit itself is kept."""

    # name: (data, None = a directory; git's mode; two modes another builder's filesystem gives)
    MEMBERS = {"pkg-1.0": (None, 0o755, (0o700, 0o775)),
               "pkg-1.0/PKG-INFO": (b"Name: pkg\n", 0o644, (0o600, 0o664)),
               "pkg-1.0/bin": (None, 0o755, (0o700, 0o750)),
               "pkg-1.0/bin/run": (b"#!/bin/sh\n", 0o755, (0o700, 0o610)),   # any execute bit
               "pkg-1.0/pkg": (None, 0o755, (0o700, 0o711)),
               "pkg-1.0/pkg/__init__.py": (b"", 0o644, (0o600, 0o640))}

    def test_sdists_differing_only_in_modes_re_pack_to_one_digest_with_git_s_modes(self):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for k in range(3):
                p = pathlib.Path(d, f"{k}.tar.gz")
                p.write_bytes(_tar([(n, git if k == 0 else other[k - 1], data)
                                    for n, (data, git, other) in self.MEMBERS.items()]))
                paths.append(p)
            self.assertEqual(len({p.read_bytes() for p in paths}), 3)
            self.assertEqual(len({R.normalize(p, EPOCH) for p in paths}), 1)
            self.assertEqual(len({p.read_bytes() for p in paths}), 1)
            with tarfile.open(paths[2]) as t:
                self.assertEqual({m.name: m.mode for m in t.getmembers()},
                                 {n: git for n, (_, git, _) in self.MEMBERS.items()})

    def test_a_changed_execute_bit_is_a_different_source(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = pathlib.Path(d, "a.tar.gz"), pathlib.Path(d, "b.tar.gz")
            a.write_bytes(_tar([("pkg-1.0/run", 0o644, b"x")]))
            b.write_bytes(_tar([("pkg-1.0/run", 0o744, b"x")]))
            self.assertNotEqual(R.normalize(a, EPOCH), R.normalize(b, EPOCH))


class WheelModeNormalisation(unittest.TestCase):
    """L1B-R1: the wheel keeps package data's and dist-info/LICENSE's file mode (setuptools build_py copies package
    data with preserve_mode), so a perturbed tree built another wheel (measured, 13 of 221 members, mode only).
    `repro_dist.py dist/*.whl` rewrites each member's mode to git's in the central directory and nothing else: wheels
    differing only in member modes give one digest, and a wheel already on git's modes keeps every byte."""

    # name: (git's mode; two modes another builder's filesystem gives). RECORD's is the wheel writer's constant.
    MEMBERS = {"pkg/__init__.py": (0o644, (0o600, 0o640)),
               "pkg/kit/catalog.json": (0o644, (0o600, 0o604)),
               "pkg-1.0.data/scripts/run": (0o755, (0o700, 0o711)),   # any execute bit
               "pkg-1.0.dist-info/LICENSE": (0o644, (0o600, 0o660)),
               "pkg-1.0.dist-info/RECORD": (0o664, (0o664, 0o664))}

    def test_wheels_differing_only_in_modes_give_one_digest_and_a_git_mode_wheel_keeps_every_byte(self):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for k in range(3):
                p = pathlib.Path(d, f"pkg-1.0-{k}-py3-none-any.whl")
                p.write_bytes(_wheel([(n, git if k == 0 else other[k - 1]) for n, (git, other) in self.MEMBERS.items()]))
                paths.append(p)
            raw = [p.read_bytes() for p in paths]
            self.assertEqual(len(set(raw)), 3)
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": str(EPOCH)}), contextlib.redirect_stdout(out):
                self.assertEqual(R.main([str(p) for p in paths]), 0)        # the CLI the CI runs
            self.assertEqual(len({p.read_bytes() for p in paths}), 1)
            self.assertEqual(paths[0].read_bytes(), raw[0])                 # a fresh checkout's wheel: every byte kept
            with zipfile.ZipFile(paths[2]) as z:
                self.assertEqual({i.filename: i.external_attr >> 16 for i in z.infolist()},
                                 {n: git if n.endswith("/RECORD") else stat.S_IFREG | git
                                  for n, (git, _) in self.MEMBERS.items()})
                self.assertEqual({i.filename: z.read(i) for i in z.infolist()}, {n: n.encode() for n in self.MEMBERS})

    def test_a_changed_execute_bit_is_a_different_source(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = pathlib.Path(d, "a.whl"), pathlib.Path(d, "b.whl")
            a.write_bytes(_wheel([("pkg/run", 0o644)]))
            b.write_bytes(_wheel([("pkg/run", 0o744)]))
            self.assertNotEqual(R.normalize_wheel(a), R.normalize_wheel(b))


class FreshCheckoutBytesUnchanged(unittest.TestCase):
    """CT-8, unit half (CR-17). Tag v2.2.0 is the frozen RC2's shipped trees. On the modes a fresh checkout gives, the
    v2.3 repro_dist writes the bytes the v2.2.0 one wrote, so the published sdist (102cda44...) stays the rebuild of
    the tag. On a perturbed tree it writes them too, which the v2.2.0 one did not (BUILD-REPRO-01, reproduced). The
    real setuptools rebuilds are staging.yml's `repro` job."""

    def test_the_v2_2_0_trees_re_pack_as_v2_2_0_did_and_perturbed_modes_no_longer_matter(self):
        frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
        self.assertEqual(frozen["artifacts"]["sha256"], {
            "aisef-2.2.0-py3-none-any.whl": "8c94dd6bd6acb6b7052a8724a6a19ca99fae370ef57a978004ee05fbcce1c389",
            "aisef-2.2.0.tar.gz": "102cda44738a44d84422e4f307163f93ae9d233e082714364e164d796dbd1291"})
        commit = _git("rev-parse", "--verify", "v2.2.0^{commit}").decode().strip()
        self.assertEqual(commit, "da3ea33f3b695aaca73e87a704145a0193aced23")
        shipped = sorted(frozen["rc"]["shipped_trees"])                   # the 2.2.0 set, whatever SHIPPED is now
        self.assertEqual({p: _git("rev-parse", f"{commit}:{p}").decode().strip() for p in shipped},
                         frozen["rc"]["shipped_trees"])
        old = types.ModuleType("repro_dist_at_v2_2_0")
        exec(compile(_git("show", f"{commit}:validation/qualification/repro_dist.py"), "repro_dist@v2.2.0", "exec"),
             old.__dict__)
        # git archive at umask 022 = the modes of a fresh checkout: 0644 / 0755 by git mode, directories 0755
        tar = _git("-c", "tar.umask=0022", "archive", "--format=tar", "--prefix=aisef-2.2.0/", commit, "--",
                   *shipped)
        fresh = _tar(_members(tar, lambda m: m.mode))
        perturbed = _tar(_members(tar, _perturbed))
        epoch = frozen["rc"]["source_date_epoch"]
        with tempfile.TemporaryDirectory() as d:
            def repack(module, sdist: bytes) -> str:
                p = pathlib.Path(d, "aisef-2.2.0.tar.gz")
                p.write_bytes(sdist)
                return module.normalize(p, epoch)

            v22 = repack(old, fresh)
            self.assertEqual(repack(R, fresh), v22)
            self.assertEqual(repack(R, perturbed), v22)
            self.assertNotEqual(repack(old, perturbed), v22)


class KernelDigestOfTheReleasedKernel(unittest.TestCase):
    """CT-9 (CR-17): both kernel_digest implementations give the frozen 2.2.0 digest on its kernel tree, the
    installed-package one (aisef2.app.run, over a tree extracted from git) and the git-object one (release_rc). The
    #41 fix (W2 L2-RECORD) must keep this green."""

    def test_both_implementations_give_the_frozen_digest(self):
        frozen = json.loads(FREEZE.read_text(encoding="utf-8"))["kernel"]
        self.assertEqual(frozen, {"digest": "c2d356b1cb1ed66652a6c1c88a4e7bd0fe962223430f131575de9432d9e334a0",
                                  "tree": "e865d65c80e2e134e2154c15ed5d58fe0b9ff713"})
        commit = _git("rev-parse", "--verify", "v2.2.0^{commit}").decode().strip()
        self.assertEqual(_git("rev-parse", f"{commit}:aisef2").decode().strip(), frozen["tree"])
        self.assertEqual(rc.kernel_digest_at(commit), frozen["digest"])
        from aisef2.app import run
        with tempfile.TemporaryDirectory() as d:
            with tarfile.open(fileobj=io.BytesIO(_git("archive", "--format=tar", commit, "aisef2"))) as t:
                t.extractall(d, filter="data")
            with mock.patch.object(run, "__file__", str(pathlib.Path(d, "aisef2", "app", "run.py"))):
                self.assertEqual(run.kernel_digest(), frozen["digest"])


class ToolchainRecord(unittest.TestCase):
    """Each build records its interpreter and runtime zlib version (the contract): `repro_dist.py --toolchain`."""

    def test_the_record_names_the_interpreter_both_zlib_versions_the_frontend_and_the_image(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(R.main(["--toolchain"]), 0)
        rec = json.loads(out.getvalue())
        self.assertEqual(set(rec), {"python", "zlib_runtime", "zlib_compiled", "build", "image", "platform"})
        self.assertEqual((rec["python"], rec["zlib_runtime"], rec["zlib_compiled"]),
                         (sys.version, zlib.ZLIB_RUNTIME_VERSION, zlib.ZLIB_VERSION))
        with mock.patch.dict(os.environ, {"ImageOS": "ubuntu24", "ImageVersion": "20261116.1"}):
            self.assertEqual(R.toolchain()["image"], "ubuntu24 20261116.1")


@unittest.skipUnless(os.name == "posix", "permission bits are POSIX's; the repro job runs on ubuntu-latest")
class PerturbedCopy(unittest.TestCase):
    """The contract's perturbed tree, `repro_dist.py --perturb SRC DST`: a copy at another path whose files carry
    non-git permission bits (the execute bit kept) and which holds __pycache__/, a stale aisef.egg-info/, dist/ and
    build/; never .git."""

    def test_the_copy_carries_non_git_modes_and_the_debris_the_contract_names(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = pathlib.Path(d, "src"), pathlib.Path(d, "elsewhere", "copy")
            (src / ".git").mkdir(parents=True)
            (src / ".git" / "HEAD").write_text("ref: refs/heads/x\n", encoding="utf-8")
            (src / "pkg").mkdir()
            (src / "pkg" / "__init__.py").write_text("X = 1\n", encoding="utf-8")
            (src / "run").write_text("#!/bin/sh\n", encoding="utf-8")
            (src / "pkg" / "__init__.py").chmod(0o644)
            (src / "run").chmod(0o755)
            (src / "dist").mkdir()
            (src / "dist" / "aisef-9.9.9.tar.gz").write_bytes(b"the fresh build's output")
            (src / "aisef.egg-info").mkdir()
            (src / "aisef.egg-info" / "PKG-INFO").write_text("Version: 9.9.9\n", encoding="utf-8")
            self.assertEqual(R.main(["--perturb", str(src), str(dst)]), 0)
            self.assertFalse((dst / ".git").exists())
            self.assertFalse((dst / "dist" / "aisef-9.9.9.tar.gz").exists())   # never src's outputs: a no-op build fails
            self.assertIn("Version: 0.0.0", (dst / "aisef.egg-info" / "PKG-INFO").read_text(encoding="utf-8"))
            self.assertEqual((dst / "pkg" / "__init__.py").read_text(encoding="utf-8"), "X = 1\n")
            for debris in ("pkg/__pycache__", "aisef.egg-info/PKG-INFO", "aisef.egg-info/SOURCES.txt", "dist", "build"):
                self.assertTrue((dst / debris).exists(), debris)
            self.assertTrue(list((dst / "pkg" / "__pycache__").glob("*.pyc")))
            self.assertTrue(zipfile.is_zipfile(dst / "dist" / "aisef-0.0.0-py3-none-any.whl"))   # dist/*.whl reads it
            modes = {p.relative_to(dst).as_posix(): p.stat().st_mode & 0o777 for p in [dst, *dst.rglob("*")]}
            self.assertEqual({k: v for k, v in modes.items() if v in (0o644, 0o755)}, {})
            self.assertEqual((modes["run"] & 0o111 != 0, modes["pkg/__init__.py"] & 0o111 != 0), (True, False))


class ContractPinnedToCi(unittest.TestCase):
    """W1-DESIGN §6 pinning test: the draft's clauses are what staging.yml runs: the backend pin, the four
    interpreters = the `repro` matrix on ubuntu-latest after `build`, the toolchain record in both jobs, the fresh and
    perturbed checks against the 3.12 build's digests, and the tag v2.2.0 rebuild. Removing coverage fails here, and
    so does keeping it while it can no longer fail (`if:`, `continue-on-error`, `||`, a pipe, `set +e`, `exit 0`, a
    rebuild outside the tree it names). PinsBite holds the negative fixtures."""

    def test_the_build_backend_is_pinned_as_the_contract_states(self):
        build_system = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["build-system"]
        self.assertEqual(build_system["requires"], ["setuptools==84.0.0"])
        self.assertIn("`setuptools==84.0.0`", _contract())

    def test_the_contract_claims_the_four_interpreters_and_the_3_12_staging_build_freezes(self):
        c = _contract()
        listed = re.search(r"CPython ((?:3\.\d+, )*3\.\d+ and 3\.\d+)", c)
        self.assertIsNotNone(listed, c)
        self.assertEqual(re.findall(r"3\.\d+", listed.group(1)), INTERPRETERS)
        self.assertRegex(c, r"`ubuntu-latest`")
        self.assertRegex(c, r"the CPython 3\.12 staging build")
        self.assertRegex(c, r"\*\*Not claimed:\*\*")
        build = _job(STAGING.read_text(encoding="utf-8"), "build")
        self.assertIn("runs-on: ubuntu-latest", build)
        self.assertRegex(build, r'python-version:\s*"3\.12"')

    def test_the_repro_job_runs_the_contract_s_interpreters_after_build(self):
        repro = _job(STAGING.read_text(encoding="utf-8"), "repro")
        self.assertIsNotNone(repro, "staging.yml has no `repro` job (W1-DESIGN §6; the job is lane L1-CIGOV's)")
        self.assertRegex(repro, r"needs:\s*(build\b|\[[^\]]*\bbuild\b)")
        self.assertIn("runs-on: ubuntu-latest", repro)
        self.assertEqual(_matrix(repro), INTERPRETERS)
        self.assertIn("python-version: ${{ matrix.python-version }}", repro)

    def test_the_repro_job_runs_every_clause(self):
        text = STAGING.read_text(encoding="utf-8")
        build, repro = _job(text, "build"), _job(text, "repro")
        self.assertIsNotNone(repro, "staging.yml has no `repro` job (W1-DESIGN §6; the job is lane L1-CIGOV's)")
        for job in (build, repro):
            self.assertIn("repro_dist.py --toolchain", job)          # interpreter + runtime zlib, on every build
        self.assertRegex(build, r"repro_dist\.py dist/\*\.tar\.gz dist/\*\.whl")   # both published files (L1B-R1)
        self.assertIn("release_rc.py --epoch", repro)                 # the contract's SOURCE_DATE_EPOCH
        self.assertIn("repro_dist.py --perturb", repro)               # the copy at another path, non-git bits, debris
        self.assertIn("name: dist-sha256", repro)                     # the 3.12 build's digests
        for clause in ("v2.2.0", "V2.2.0-RC2-FREEZE.json", "source_date_epoch"):   # the published 2.2.0 rebuild
            self.assertIn(clause, repro)

    def test_each_rebuild_leg_builds_where_it_claims_and_checks_both_files(self):
        """Three rebuilds, each in one `run`: the fresh checkout and the perturbed copy against the 3.12 build's
        SHA256SUMS, tag v2.2.0 against its frozen digests. Each starts `set -eu`, builds in its own tree (the last
        `cd` before `python -m build`), normalises the sdist and the wheel, then checks."""
        repro = _job(STAGING.read_text(encoding="utf-8"), "repro")
        self.assertIsNotNone(repro, "staging.yml has no `repro` job (W1-DESIGN §6; the job is lane L1-CIGOV's)")
        runs = [r for r in _runs(repro) if any("python -m build" in ln for ln in r)]
        legs = {"tag": [r for r in runs if any("V2.2.0-RC2-FREEZE.json" in ln for ln in r)],
                "perturbed": [r for r in runs if any("repro_dist.py --perturb" in ln for ln in r)]}
        legs["fresh"] = [r for r in runs if all(r not in v for v in legs.values())]
        tree = {"fresh": None, "perturbed": r"repro_dist\.py --perturb \S+ (\S+)$",
                "tag": r"^git worktree add (?:-\S+ )*(\S+) v2\.2\.0$"}
        for leg, blocks in legs.items():
            self.assertEqual(len(blocks), 1, f"{leg}: one rebuild leg, in one run")
            run = blocks[0]

            def at(pattern: str, run: list[str] = run, leg: str = leg) -> int:
                i = next((i for i, ln in enumerate(run) if re.search(pattern, ln)), None)
                self.assertIsNotNone(i, f"{leg}: no line matching {pattern!r}")
                return i

            self.assertRegex(run[0], r"^set -eu", leg)
            build, norm = at(r"^python -m build$"), at(r"^python -P \S*repro\S* dist/\*\.tar\.gz dist/\*\.whl$")
            check = at(r"sha256sum -c")
            self.assertLess(at(r"^export SOURCE_DATE_EPOCH="), build, leg)
            self.assertLess(build, norm, leg)
            self.assertLess(norm, check, leg)
            if leg != "tag":
                self.assertIn("SHA256SUMS", run[check], leg)
            cds = [ln for ln in run[:build] if ln.startswith("cd ")]
            if tree[leg] is None:
                self.assertEqual(cds, [], f"{leg}: builds in the checkout")
            else:
                self.assertEqual(cds[-1:], [f"cd {re.search(tree[leg], run[at(tree[leg])]).group(1)}"], leg)

    def test_no_leg_can_be_skipped_or_its_failure_swallowed(self):
        text = STAGING.read_text(encoding="utf-8")
        for name in ("build", "repro"):
            job = _job(text, name)
            self.assertIsNotNone(job, f"staging.yml has no `{name}` job (W1-DESIGN §6; `repro` is lane L1-CIGOV's)")
            self.assertNotRegex(job, r"(?m)^ *(?:- +)?if:", f"{name}: a condition can skip it")
            self.assertNotIn("continue-on-error", job, name)
        repro = _job(text, "repro")
        self.assertNotRegex(repro, r"(?m)^ *exclude:", "a matrix exclude drops a leg")
        for run in _runs(repro):
            for ln in run:
                self.assertNotRegex(ln, r"\||(?<![&>])&(?!&)|\bset \+|\bexit 0\b", f"can swallow a failure: {ln}")


class PinsBite(unittest.TestCase):
    """The pins pass on a staging.yml that runs every clause (REFERENCE: L1-CIGOV's job may differ, the pins decide)
    and fail on each way found to remove a leg, or to keep it while it can no longer fail (L1B-R2)."""

    VARIANTS = {   # name: (text in REFERENCE, its replacement)
        "job if false": ("  repro:\n    needs: build\n", "  repro:\n    if: ${{ false }}\n    needs: build\n"),
        "job continue-on-error": ("    needs: build\n", "    needs: build\n    continue-on-error: true\n"),
        "step continue-on-error": ("      - name: perturbed\n", "      - name: perturbed\n        continue-on-error: true\n"),
        "step if false": ("      - name: fresh\n", "      - name: fresh\n        if: false\n"),
        "|| true": ('/v220.sums")\n', '/v220.sums") || true\n'),
        "set +e": ("          set -eu\n          freeze=", "          set -eu\n          set +e\n          freeze="),
        "exit 0": ('/v220.sums")\n', '/v220.sums"); exit 0\n'),
        "pipe": ('/v220.sums")\n', '/v220.sums") | tee check.log\n'),
        "background": ('/v220.sums")\n', '/v220.sums") &\n'),
        "no set -eu": ("          set -eu\n          freeze=", "          freeze="),
        "perturbed build in the checkout": ('          cd "$RUNNER_TEMP/perturbed"\n', '          cd "$GITHUB_WORKSPACE"\n'),
        "perturbed cd dropped": ('          cd "$RUNNER_TEMP/perturbed"\n', ""),
        "tag not checked out": ('git worktree add --detach "$RUNNER_TEMP/v2.2.0" v2.2.0',
                                'cp -R "$GITHUB_WORKSPACE" "$RUNNER_TEMP/v2.2.0"'),
        "wheel not normalised in build": ("dist/*.tar.gz dist/*.whl\n  repro:", "dist/*.tar.gz\n  repro:"),
        "wheel not normalised in a leg": ('"$repro" dist/*.tar.gz dist/*.whl', '"$repro" dist/*.tar.gz'),
        "check before normalise": ('          python -P "$repro" dist/*.tar.gz dist/*.whl\n          (cd dist && sha256sum -c',
                                   '          (cd dist && sha256sum -c'),
        "matrix exclude": ('["3.11", "3.12", "3.13", "3.14"]\n',
                           '["3.11", "3.12", "3.13", "3.14"]\n        exclude:\n          - python-version: "3.11"\n'),
        "3.11 dropped": ('["3.11", "3.12", "3.13", "3.14"]', '["3.12", "3.13", "3.14"]'),
        "needs install": ("    needs: build\n", "    needs: install\n"),
        "macos": ("    needs: build\n    runs-on: ubuntu-latest", "    needs: build\n    runs-on: macos-latest"),
        "no toolchain in build": ("          python -P validation/qualification/repro_dist.py --toolchain > toolchain.json\n",
                                  ""),
        "RC1 freeze": ("V2.2.0-RC2-FREEZE.json", "V2.2.0-RC1-FREEZE.json"),
        "fresh leg dropped": ('      - name: fresh\n        run: |\n          set -eu\n          export SOURCE_DATE_EPOCH="$(python -P'
                              ' validation/qualification/release_rc.py --epoch)"\n          python -m build\n          python -P'
                              ' validation/qualification/repro_dist.py dist/*.tar.gz dist/*.whl\n          (cd dist &&'
                              ' sha256sum -c "$RUNNER_TEMP/sums/SHA256SUMS")\n', ""),
    }

    def _failing(self, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            staging = pathlib.Path(d, "staging.yml")
            staging.write_text(text, encoding="utf-8")
            result = unittest.TestResult()
            with mock.patch.object(sys.modules[__name__], "STAGING", staging):
                unittest.defaultTestLoader.loadTestsFromTestCase(ContractPinnedToCi).run(result)
        return sorted(t.id().rsplit(".", 1)[1] for t, _ in result.failures + result.errors)

    def test_the_reference_passes_every_pin(self):
        self.assertEqual(self._failing(REFERENCE), [])

    def test_every_neutralisation_fails_a_pin(self):
        for name, (old, new) in self.VARIANTS.items():
            with self.subTest(name):
                self.assertEqual(REFERENCE.count(old), 1, "the fixture must change REFERENCE exactly once")
                self.assertNotEqual(self._failing(REFERENCE.replace(old, new)), [])


REFERENCE = """\
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install build twine
      - run: |
          set -eu
          python -P validation/qualification/repro_dist.py --toolchain > toolchain.json
          cat toolchain.json
      - run: |
          set -eu
          export SOURCE_DATE_EPOCH="$(python -P validation/qualification/release_rc.py --epoch)"
          python -m build
          python -P validation/qualification/repro_dist.py dist/*.tar.gz dist/*.whl
  repro:
    needs: build
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13", "3.14"]
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install build
      - run: |
          set -eu
          python -P validation/qualification/repro_dist.py --toolchain > "$RUNNER_TEMP/toolchain.json"
          cat "$RUNNER_TEMP/toolchain.json"
      - uses: actions/download-artifact@v4
        with:
          name: dist-sha256
          path: ${{ runner.temp }}/sums
      - name: fresh
        run: |
          set -eu
          export SOURCE_DATE_EPOCH="$(python -P validation/qualification/release_rc.py --epoch)"
          python -m build
          python -P validation/qualification/repro_dist.py dist/*.tar.gz dist/*.whl
          (cd dist && sha256sum -c "$RUNNER_TEMP/sums/SHA256SUMS")
      - name: perturbed
        run: |
          set -eu
          export SOURCE_DATE_EPOCH="$(python -P validation/qualification/release_rc.py --epoch)"
          python -P validation/qualification/repro_dist.py --perturb "$GITHUB_WORKSPACE" "$RUNNER_TEMP/perturbed"
          cd "$RUNNER_TEMP/perturbed"
          python -m build
          python -P validation/qualification/repro_dist.py dist/*.tar.gz dist/*.whl
          (cd dist && sha256sum -c "$RUNNER_TEMP/sums/SHA256SUMS")
      - name: tag v2.2.0, the current repro_dist.py
        run: |
          set -eu
          freeze="$GITHUB_WORKSPACE/closure-evidence/v2/release/V2.2.0-RC2-FREEZE.json"
          export SOURCE_DATE_EPOCH="$(python -c "import json,sys;print(json.load(open(sys.argv[1]))['rc']['source_date_epoch'])" "$freeze")"
          python -c "import json,sys;[print(v+'  '+k) for k,v in json.load(open(sys.argv[1]))['artifacts']['sha256'].items()]" "$freeze" > "$RUNNER_TEMP/v220.sums"
          repro="$GITHUB_WORKSPACE/validation/qualification/repro_dist.py"
          git worktree add --detach "$RUNNER_TEMP/v2.2.0" v2.2.0
          cd "$RUNNER_TEMP/v2.2.0"
          python -m build
          python -P "$repro" dist/*.tar.gz dist/*.whl
          (cd dist && sha256sum -c "$RUNNER_TEMP/v220.sums")
"""


if __name__ == "__main__":
    unittest.main()
