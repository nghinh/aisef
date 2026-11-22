"""L1-CIGOV (docs/v2.3/W1-DESIGN.md §5, §7; CODE-AUDIT #1, #6a, #29, #30, #52 (a); COMPATIBILITY-MATRIX CT-5, CT-6; the
CI-INCR job). The workflows are read as text (no YAML dependency in CI), comment lines dropped: an explanation is not a
configuration. Each pin has negative fixtures, so keeping a step while it can no longer fail fails here too.

* REL-GOV-01 / #1: release_governance.problems() FAILs unless `pypi` has a required reviewer and only tag policies; the
  `governance` job runs it, no publish path in any workflow reaches a publish without it, and every publish job deploys
  to exactly `pypi`, the environment the guard reads (CIGOV-R2).
* #6 (non-A2): the installed product smoke asserts `aisef demo`'s three rows and, with `--writer`, verifies a run the
  published 2.2.0 wheel wrote (kernel digest c2d356b1...); staging.yml runs both.
* #29: no scheduled workflow references a secret other than GITHUB_TOKEN; conformance.yml is dispatch-only.
* #30: diagnostic.yml stays a non-gating legacy reproducer, recorded as such in the CI baseline.
* #52 (a): the unit job fails when the suite left closure-evidence/ different from HEAD; (b) is
  test_v23_released_evidence_guard.py, its CI step is pinned here.
* CI-INCR: mutation-incr.yml runs the F5 engine only, never a mutation campaign, with the mutation-worker guard.
* CT-5: the release-decision ledger is append-only; CT-6: every closure-evidence/v2 blob of the branch base is kept.
  The two conflict on the ledger itself (it lives under closure-evidence/v2/): CIGOV-R1, OPEN, owner/integrator
  decision in docs/v2.3/amendments/CIGOV-R1.md. Until decided, a seq 13 append turns HistoryKept and the CI guard red.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
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

from validation.qualification import release_governance as G  # noqa: E402
from validation.v23 import released_evidence_guard as RE  # noqa: E402

WF = ROOT / ".github" / "workflows"
GUARD = "python -P validation/qualification/release_governance.py"
SWALLOW = re.compile(r"\||(?<![&>])&(?!&)|\bset \+|\bexit 0\b")   # || true, a pipe, background, set +e, exit 0


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True, encoding="utf-8").stdout


def code(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def jobs(text: str) -> dict[str, str]:
    """Job name -> its block (a job is a key indented two spaces under `jobs:`), comment lines dropped."""
    body = code(text).split("\njobs:", 1)[-1]
    marks = [(m.group(1), m.start()) for m in re.finditer(r"(?m)^  ([A-Za-z_][\w-]*):[ \t]*$", body)]
    return {n: body[at:(marks[i + 1][1] if i + 1 < len(marks) else len(body))] for i, (n, at) in enumerate(marks)}


def needs(block: str) -> list[str]:
    m = re.search(r"(?m)^    needs:[ \t]*(.*)$", block)
    if m is None:
        return []
    v = m.group(1).strip()
    if v:
        return [x.strip().strip("'\"") for x in v.strip("[]").split(",") if x.strip()]
    listed = []
    for ln in block[m.end():].split("\n")[1:]:
        item = re.match(r"      - +['\"]?([\w-]+)", ln)
        if item is None:
            break
        listed.append(item.group(1))
    return listed


def runs(block: str) -> list[str]:
    """Every command line of every `run:` of a job (a block scalar's body, or the one-line value)."""
    lines, out = block.split("\n"), []
    for i, ln in enumerate(lines):
        m = re.match(r"( *)(?:- +)?run: *(.*)$", ln)
        if m is None:
            continue
        if m.group(2)[:1] not in ("|", ">"):
            out.append(m.group(2))
            continue
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= len(m.group(1)):
                break
            if nxt.strip():
                out.append(nxt.strip())
    return out


def steps(block: str) -> list[str]:
    """Each step of a job as its text: what follows one `- ` at the steps' indentation, up to the next."""
    m = re.search(r"(?m)^    steps:\n", block)
    return [] if m is None else ["- " + s for s in re.split(r"(?m)^      - ", block[m.end():])[1:]]


def workflows() -> dict[str, str]:
    return {f.name: f.read_text(encoding="utf-8") for f in sorted(WF.glob("*.yml"))}


# --------------------------------------------------------------------------------------- REL-GOV-01 / #1

#: a job that holds a publish capability: an OIDC token, a PyPI upload, or a deployment environment (gated secrets)
PUBLISH = re.compile(r"id-token|pypi-publish|twine +upload|^\s*environment\s*:", re.M)


def environments(block: str) -> list[str]:
    """Every deployment environment a job declares: `environment: X`, or `environment:` over one `name: X` line."""
    out = []
    for m in re.finditer(r"(?m)^    environment:[ \t]*(.*)$", block):
        value = m.group(1).strip()
        if not value:
            names = re.findall(r"(?m)^      name:[ \t]*(.*)$", re.match(r"(?:\n      .*)*", block[m.end():]).group(0))
            value = names[0].strip() if len(names) == 1 else ""
        out.append(value.strip("'\""))
    return out


def bypasses(wfs: dict[str, str]) -> list[str]:
    """[] iff no workflow can publish except release.yml's publish jobs, each deploying to exactly the environment the
    guard reads (G.ENV) and needing `governance` through jobs that no condition can run past, and `governance` runs the
    guard and cannot be skipped or swallowed."""
    out = []
    for name, text in sorted(wfs.items()):
        if PUBLISH.search(code(text).split("\njobs:", 1)[0]):
            out.append(f"{name}: a publish capability at workflow level (every job holds it)")
        if name != "release.yml":
            out += [f"{name}:{j} can publish outside release.yml" for j, b in jobs(text).items() if PUBLISH.search(b)]
    if "release.yml" not in wfs:
        return out + ["release.yml is missing"]
    js = jobs(wfs["release.yml"])
    gov = js.get("governance")
    if gov is None:
        return out + ["release.yml has no `governance` job"]
    if GUARD not in runs(gov):
        out.append(f"governance does not run `{GUARD}`")
    if re.search(r"(?m)^ *(?:- +)?if:", gov) or "continue-on-error" in gov:
        out.append("governance: a condition can skip it or its failure is swallowed")
    out += [f"governance: can swallow a failure: {ln}" for ln in runs(gov) if SWALLOW.search(ln)]
    if PUBLISH.search(gov):
        out.append("governance holds a publish capability")

    def ancestors(j: str, seen: set[str] | None = None) -> set[str]:
        seen = set() if seen is None else seen
        for n in needs(js.get(j, "")):
            if n not in seen:
                seen.add(n)
                ancestors(n, seen)
        return seen

    for j, block in js.items():
        m = re.search(r"(?m)^    uses:\s*(\S+)", block)
        if m and not m.group(1).startswith("./.github/workflows/"):
            out.append(f"release.yml:{j} calls a workflow outside this repository: {m.group(1)}")
        if j == "governance" or not PUBLISH.search(block):
            continue
        if environments(block) != [G.ENV]:     # CIGOV-R2: else the reviewer `governance` checks never applies
            out.append(f"release.yml:{j} does not deploy to exactly `{G.ENV}`, the environment `governance` reads: "
                       f"{environments(block)}")
        up = ancestors(j)
        if "governance" not in up:
            out.append(f"release.yml:{j} can publish without `governance`")
        for k in [j, *sorted(x for x in up if "governance" in ancestors(x))]:
            if re.search(r"(?m)^    if:", js.get(k, "")) or "continue-on-error" in js.get(k, ""):
                out.append(f"release.yml:{k} has a condition that can run {j} past a failed `governance`")
    return out


class Predicate(unittest.TestCase):
    """W1-DESIGN §5 negative tests: protection_rules [], a branch policy, no policies -> FAIL; reviewer + tag -> PASS."""

    REVIEWER = {"type": "required_reviewers", "prevent_self_review": False,
                "reviewers": [{"type": "User", "reviewer": {"login": "the-owner", "id": 1}}]}
    ENV = {"name": "pypi", "can_admins_bypass": False, "protection_rules": [REVIEWER],
           "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}
    TAG = {"total_count": 1, "branch_policies": [{"name": "v[0-9]*.[0-9]*.[0-9]*", "type": "tag"}]}

    def test_a_reviewer_and_one_tag_policy_pass(self):
        self.assertEqual(G.problems(self.ENV, self.TAG), [])

    def test_the_w0_recorded_state_fails(self):
        """docs/v2.3/RELEASE-GOVERNANCE-FINDING.md: protection_rules [] and no deployment policy (re-read 2026-11-21)."""
        found = G.problems({"name": "pypi", "protection_rules": [], "deployment_branch_policy": None}, None)
        self.assertTrue(any("required_reviewers" in p for p in found), found)
        self.assertTrue(any("custom (tag) policies" in p for p in found), found)

    def test_each_missing_part_fails(self):
        cases = {
            "protection_rules []": ({**self.ENV, "protection_rules": []}, self.TAG),
            "a reviewers rule with no reviewer": ({**self.ENV, "protection_rules": [{**self.REVIEWER, "reviewers": []}]},
                                                  self.TAG),
            "only a wait timer": ({**self.ENV, "protection_rules": [{"type": "wait_timer", "wait_timer": 5}]}, self.TAG),
            "a branch policy": (self.ENV, {"total_count": 1, "branch_policies": [{"name": "*", "type": "branch"}]}),
            "a tag and a branch policy": (self.ENV, {"total_count": 2, "branch_policies": [
                *self.TAG["branch_policies"], {"name": "main", "type": "branch"}]}),
            "a policy with no type": (self.ENV, {"total_count": 1, "branch_policies": [{"name": "v*"}]}),
            "no policies": (self.ENV, {"total_count": 0, "branch_policies": []}),
            "policies unreadable": (self.ENV, None),
            "policies listing truncated": (self.ENV, {**self.TAG, "total_count": 31}),
            "protected branches instead of custom policies": (
                {**self.ENV, "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False}},
                self.TAG),
            "no deployment policy at all": ({**self.ENV, "deployment_branch_policy": None}, self.TAG),
            "environment unreadable": (None, self.TAG),
        }
        for name, (env, pol) in cases.items():
            with self.subTest(name):
                self.assertNotEqual(G.problems(env, pol), [])

    def test_admin_bypass_and_self_review_are_reported_not_judged(self):
        env = {**self.ENV, "can_admins_bypass": True, "protection_rules": [{**self.REVIEWER, "prevent_self_review": True}]}
        doc = G.report(env, self.TAG)
        self.assertEqual((doc["verdict"], doc["can_admins_bypass"], doc["prevent_self_review"], doc["reviewers"]),
                         ("PASS", True, [True], 1))
        self.assertNotIn("the-owner", json.dumps(doc))   # a count only: no identity in a public log


class Cli(unittest.TestCase):
    """The job's command: GET only, both endpoints, exit 0 only on PASS, fail closed on anything unreadable."""

    def _main(self, answers: dict, environ: dict | None = None) -> tuple[int, list, str]:
        seen = []

        def urlopen(req, timeout):
            seen.append((req.get_method(), req.full_url, dict(req.header_items())))
            for suffix, doc in answers.items():
                if req.full_url.endswith(suffix):
                    if doc is None:
                        raise G.urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
                    return contextlib.nullcontext(io.BytesIO(json.dumps(doc).encode()))
            raise AssertionError(req.full_url)

        out = io.StringIO()
        env = {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "t0k3n"} if environ is None else environ
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(G.urllib.request, "urlopen", urlopen), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code_ = G.main([])
        return code_, seen, out.getvalue()

    def test_protected_passes_unprotected_or_unreadable_fails(self):
        protected = {"/environments/pypi": Predicate.ENV, "/deployment-branch-policies?per_page=100": Predicate.TAG}
        rc, seen, text = self._main(protected)
        self.assertEqual(rc, 0, text)
        self.assertEqual([(m, u) for m, u, _ in seen],
                         [("GET", "https://api.github.com/repos/owner/repo/environments/pypi"),
                          ("GET", "https://api.github.com/repos/owner/repo/environments/pypi/deployment-branch-policies"
                                  "?per_page=100")])
        self.assertTrue(all(h.get("Authorization") == "Bearer t0k3n" for _, _, h in seen))
        self.assertNotIn("t0k3n", text)
        for name, answers in {"unprotected": {**protected, "/environments/pypi": {"protection_rules": []}},
                              "environment 403": {**protected, "/environments/pypi": None},
                              "policies 403": {**protected, "/deployment-branch-policies?per_page=100": None}}.items():
            with self.subTest(name):
                rc, _, text = self._main(answers)
                self.assertEqual(rc, 1, text)
                self.assertIn('"verdict": "FAIL"', text)

    def test_no_repository_refuses(self):
        self.assertEqual(self._main({}, environ={})[0], 2)


class PublishNeedsGovernance(unittest.TestCase):
    """release.yml: `publish` needs `v2-gate`, which needs `governance` (tests/test_release_gate.py pins publish's own
    `needs` list); no other workflow holds a publish capability, and no condition runs a publish past the guard."""

    def test_the_workflows_have_no_bypass(self):
        self.assertEqual(bypasses(workflows()), [])

    def test_the_governance_job_reads_with_a_read_only_token(self):
        gov = jobs(workflows()["release.yml"])["governance"]
        self.assertIn("runs-on: ubuntu-latest", gov)
        perms = re.search(r"(?m)^    permissions:\n((?:      .*\n)+)", gov)
        self.assertIsNotNone(perms, "governance must declare its own token scope")
        self.assertEqual(sorted(perms.group(1).split()), ["actions:", "contents:", "read", "read"])
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", gov)
        self.assertIn("governance", needs(jobs(workflows()["release.yml"])["v2-gate"]))

    def test_the_release_that_published_2_2_0_had_no_checkpoint(self):
        """Red-before: release.yml at tag v2.2.0 auto-published with no human pause (RELEASE-GOVERNANCE-FINDING)."""
        old = {**workflows(), "release.yml": _git("show", "v2.2.0:.github/workflows/release.yml")}
        self.assertIn("release.yml has no `governance` job", bypasses(old))

    VARIANTS = {   # name: (text in release.yml, its replacement)
        "v2-gate drops governance": ("needs: [stable-tag, governance]", "needs: stable-tag"),
        "publish if always": ("  publish:\n", "  publish:\n    if: always()\n"),
        "v2-gate if always": ("  v2-gate:\n", "  v2-gate:\n    if: ${{ always() }}\n"),
        "v2-gate continue-on-error": ("  v2-gate:\n", "  v2-gate:\n    continue-on-error: true\n"),
        "governance job if": ("  governance:\n", "  governance:\n    if: false\n"),
        "governance continue-on-error": ("  governance:\n", "  governance:\n    continue-on-error: true\n"),
        "guard || true": (f"run: {GUARD}\n", f"run: {GUARD} || true\n"),
        "guard step if": (f"        run: {GUARD}\n", f"        if: false\n        run: {GUARD}\n"),
        "guard not run": (f"run: {GUARD}\n", "run: echo governance\n"),
        "governance renamed": ("  governance:\n", "  governance-check:\n"),
        "workflow-level id-token": ("permissions:\n  contents: read\n", "permissions:\n  contents: read\n  id-token: write\n"),
        "a second publish job": ("\n  publish:\n", "\n  publish-fast:\n    needs: stable-tag\n    runs-on: ubuntu-latest\n"
                                 "    environment: pypi\n    steps:\n      - run: echo\n\n  publish:\n"),
        "a remote reusable workflow": ("\n  publish:\n", "\n  other:\n    uses: someone/else/.github/workflows/x.yml@v1\n\n"
                                       "  publish:\n"),
        # CIGOV-R2: publish must deploy to the environment `governance` reads, or the reviewer it checks never applies
        "publish loses environment: pypi": ("    environment: pypi\n", ""),
        "publish targets another environment": ("    environment: pypi\n", "    environment: pypi-fast\n"),
        "publish environment from an expression": ("    environment: pypi\n", "    environment: ${{ github.ref_name }}\n"),
        "publish environment mapping names another": ("    environment: pypi\n", "    environment:\n      name: staging\n"),
    }

    def test_every_neutralisation_is_found(self):
        real = workflows()
        for name, (old, new) in self.VARIANTS.items():
            with self.subTest(name):
                self.assertEqual(real["release.yml"].count(old), 1, "the fixture must change release.yml exactly once")
                self.assertNotEqual(bypasses({**real, "release.yml": real["release.yml"].replace(old, new)}), [])

    def test_publish_deploys_to_the_guarded_environment_in_either_form(self):
        """CIGOV-R2: the pin is on the environment's name, not its spelling: a quoted scalar or a `name:` mapping of
        `pypi` passes; a mapping with two names fails closed."""
        real = workflows()
        self.assertEqual(environments(jobs(real["release.yml"])["publish"]), [G.ENV])
        for new, ok in (('    environment: "pypi"\n', True),
                        ("    environment:\n      name: pypi\n      url: https://pypi.org/p/aisef\n", True),
                        ("    environment:\n      name: pypi\n      name: staging\n", False)):
            with self.subTest(new):
                found = bypasses({**real, "release.yml": real["release.yml"].replace("    environment: pypi\n", new, 1)})
                self.assertEqual(found == [], ok, found)

    def test_the_probe_workflow_never_lands_on_the_branch(self):
        """W1-DESIGN §5: relgov-probe.yml lives only in the owner's probe commit P; on the branch it is a bypass."""
        probe = (ROOT / "docs/v2.3/drafts/relgov/relgov-probe.yml").read_text(encoding="utf-8")
        self.assertFalse((WF / "relgov-probe.yml").exists())
        self.assertIn("relgov-probe.yml:checkpoint can publish outside release.yml",
                      bypasses({**workflows(), "relgov-probe.yml": probe}))
        self.assertNotEqual(bypasses({**workflows(), "staging.yml": workflows()["staging.yml"].replace(
            "  install:\n", "  install:\n    environment: pypi\n", 1)}), [])


# --------------------------------------------------------------------------------------- #6 (non-A2 part)

_spec = importlib.util.spec_from_file_location("installed_product_smoke_v23", ROOT / "tests" / "installed_product_smoke.py")
SMOKE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SMOKE)

#: `aisef demo` as measured (2026-11-22, darwin, CPython 3.14, this kernel)
DEMO_OUT = """project: calc — one story (S1), one contract (BC-ADD: add(2, 3) == 5)

[correct] the developer writes add correctly
    delivery PASS   stories {'S1': ['COMMIT']}   verify VERIFIED

[caught] the developer writes a wrong add (a - b)
    delivery FAIL   stories {'S1': ['RETRY', 'ROLLBACK']}   verify VERIFIED

[escape] the developer writes add as `return 5`
    delivery PASS   stories {'S1': ['COMMIT']}   verify VERIFIED
    but: add(1, 1) returns 5 on the delivered code (the sum is 2)

The kernel delivered `correct`, refused `caught`, and delivered `escape` — because `escape`
satisfies every stated contract. AISEF proves the contracts you write hold; it does not
prove the code is right where no contract looks. Write the contract that would have caught it.
"""


class DemoRows(unittest.TestCase):
    """`aisef demo` exits 0 whatever its verdicts (demo.main returns 0): the smoke asserts the printed rows."""

    def test_the_measured_output_passes(self):
        self.assertEqual(SMOKE.demo_problems(DEMO_OUT), [])

    def test_every_wrong_row_fails(self):
        variants = {
            "no rows": "",
            "a row missing": DEMO_OUT.replace("[caught]", "[cought]"),
            "caught delivered": DEMO_OUT.replace("delivery FAIL   stories {'S1': ['RETRY', 'ROLLBACK']}",
                                                 "delivery PASS   stories {'S1': ['RETRY', 'COMMIT']}"),
            "correct refuted": DEMO_OUT.replace("{'S1': ['COMMIT']}   verify VERIFIED\n\n[caught]",
                                                "{'S1': ['COMMIT']}   verify REFUTED\n\n[caught]"),
            "escape refused": DEMO_OUT.replace("delivery PASS   stories {'S1': ['COMMIT']}   verify VERIFIED\n    but",
                                               "delivery FAIL   stories {'S1': ['ROLLBACK']}   verify VERIFIED\n    but"),
            "no gap": DEMO_OUT.replace("    but: add(1, 1) returns 5", "    and: add(1, 1) returns 2"),
            "stories unparsable": DEMO_OUT.replace("{'S1': ['COMMIT']}   verify VERIFIED\n\n[caught]",
                                                   "{S1: COMMIT}   verify VERIFIED\n\n[caught]"),
        }
        for name, text in variants.items():
            with self.subTest(name):
                self.assertNotEqual(SMOKE.demo_problems(text), [])


@unittest.skipUnless(os.name == "posix", "the smoke's product steps run on POSIX runners only")
class SmokeWiring(unittest.TestCase):
    """problems(): the candidate runs check/run/verify and then `aisef demo`; problems(writer) has the writer write the
    run, the candidate verify it, and the 2.2.0 kernel digest required in RUN.json. `aisef` is faked, git is real."""

    def _problems(self, writer, demo_out=DEMO_OUT, kernel=SMOKE.KERNEL_2_2_0):
        real, calls = subprocess.run, []

        def run(argv, **kw):
            if pathlib.Path(argv[0]).name not in ("aisef", "aisef.exe", "writer-aisef"):
                return real(argv, **kw)
            calls.append([pathlib.Path(argv[0]).name, *argv[1:3]])
            if argv[1] == "demo":
                return subprocess.CompletedProcess(argv, 0, demo_out, "")
            if "--out" in argv and "--verify" not in argv:
                out = pathlib.Path(argv[argv.index("--out") + 1])
                out.mkdir()
                (out / "RUN.json").write_text(json.dumps({"delivery_verdict": "PASS", "story_outcomes": {"S1": ["COMMIT"]},
                                                          "kernel_digest": kernel}), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "{}", "")

        with mock.patch.object(SMOKE, "_outside_the_artifact", lambda: []), mock.patch.object(subprocess, "run", run):
            return SMOKE.problems(writer), calls

    def test_the_candidate_runs_and_then_the_demo(self):
        found, calls = self._problems(None)
        self.assertEqual(found, [])
        self.assertEqual([c[:2] for c in calls], [["aisef", "run"]] * 3 + [["aisef", "demo"]])
        self.assertNotEqual(self._problems(None, demo_out=DEMO_OUT.replace("[escape]", "[x]"))[0], [])

    def test_the_writer_writes_and_the_candidate_verifies(self):
        writer = pathlib.Path(tempfile.gettempdir(), "writer-aisef")
        found, calls = self._problems(writer)
        self.assertEqual(found, [])
        self.assertEqual(calls, [["writer-aisef", "run", "--project"]] * 2 + [["aisef", "run", "--project"]])
        found, _ = self._problems(writer, kernel="0" * 64)
        self.assertTrue(any("not 2.2.0's" in p for p in found), found)


class StagingRunsBoth(unittest.TestCase):
    """staging.yml's install job runs the product smoke (demo included) and the historical-2.2 read, the latter with the
    published 2.2.0 wheel pinned to its frozen sha256 (pip --require-hashes)."""

    def test_both_steps_are_in_the_install_job_and_cannot_be_swallowed(self):
        install = jobs(workflows()["staging.yml"])["install"]
        self.assertNotIn("continue-on-error", install)
        self.assertEqual(set(re.findall(r"(?m)^ +if: *(.*)$", install)), {"runner.os != 'Windows'"})
        smoke = [s for s in steps(install) if "installed_product_smoke.py" in s]
        self.assertEqual(len(smoke), 2, smoke)
        plain, writer = sorted(smoke, key=lambda s: "--writer" in s)
        self.assertNotIn("--writer", plain)
        self.assertRegex(plain, r'(?m)"\$SMOKE_PY" -I "\$GITHUB_WORKSPACE/tests/installed_product_smoke\.py"$')
        for clause in ("V2.2.0-RC2-FREEZE.json", "aisef-2.2.0-py3-none-any.whl", "aisef==2.2.0 --hash=sha256:",
                       "--require-hashes", "--no-deps",
                       '"$SMOKE_PY" -I "$GITHUB_WORKSPACE/tests/installed_product_smoke.py" --writer '):
            self.assertIn(clause, writer)
        for s in smoke:
            body = runs(s)
            self.assertEqual(body[0], "set -eu", s)
            self.assertEqual([ln for ln in body if SWALLOW.search(ln)], [], s)

    def test_the_writer_is_the_published_2_2_0_kernel(self):
        frozen = json.loads((ROOT / "closure-evidence/v2/release/V2.2.0-RC2-FREEZE.json").read_text(encoding="utf-8"))
        self.assertEqual(frozen["kernel"]["digest"], SMOKE.KERNEL_2_2_0)
        self.assertEqual(frozen["artifacts"]["sha256"]["aisef-2.2.0-py3-none-any.whl"],
                         "8c94dd6bd6acb6b7052a8724a6a19ca99fae370ef57a978004ee05fbcce1c389")


# --------------------------------------------------------------------------------------- #29, #30

def scheduled_secrets(wfs: dict[str, str]) -> list[str]:
    """A scheduled workflow fires whatever the release state: it may reference no secret but GITHUB_TOKEN (a paid key
    there is unmetered spend, charter §4). `secrets: inherit`, `secrets[...]` and toJSON(secrets) count as references."""
    out = []
    for name, text in sorted(wfs.items()):
        c = code(text)
        if not re.search(r"(?m)^\s*schedule\s*:|^\s*-?\s*cron\s*:", c):
            continue
        out += [f"{name}: scheduled and references secrets{m.group(1) or ''}"
                for m in re.finditer(r"\bsecrets\b(\.[A-Za-z_][\w-]*|\[[^\]]*\])?", c) if m.group(1) != ".GITHUB_TOKEN"]
    return out


class NoScheduledPaidSecret(unittest.TestCase):
    def test_no_scheduled_workflow_references_a_paid_secret(self):
        self.assertEqual(scheduled_secrets(workflows()), [])

    def test_conformance_is_dispatch_only(self):
        on = code(workflows()["conformance.yml"]).split("\non:", 1)[1].split("\njobs:", 1)[0]
        self.assertEqual(re.findall(r"(?m)^  (\w+):", on), ["workflow_dispatch"])

    def test_the_weekly_paid_cron_is_found(self):
        """Red-before: conformance.yml at v2.2.0 ran weekly with ANTHROPIC_API_KEY (the cron master still runs)."""
        old = {"conformance.yml": _git("show", "v2.2.0:.github/workflows/conformance.yml")}
        self.assertEqual(scheduled_secrets(old), ["conformance.yml: scheduled and references secrets.ANTHROPIC_API_KEY"])
        sched = 'on:\n  schedule:\n    - cron: "0 3 * * 1"\njobs:\n  j:\n    runs-on: ubuntu-latest\n'
        for ref in ("    secrets: inherit\n", "    env:\n      K: ${{ secrets['OPENAI_API_KEY'] }}\n",
                    "    env:\n      K: ${{ toJSON(secrets) }}\n", "    env:\n      K: ${{ secrets.OTHER }}\n"):
            with self.subTest(ref):
                self.assertNotEqual(scheduled_secrets({"x.yml": sched + ref}), [])
        self.assertEqual(scheduled_secrets({"x.yml": sched + "    env:\n      K: ${{ secrets.GITHUB_TOKEN }}\n"}), [])


class DiagnosticIsNotAGate(unittest.TestCase):
    """#30 ACCEPTED_LIMITATION: diagnostic.yml is the legacy P7-FINDING-001 reproducer, recorded so in the CI baseline;
    no release-path workflow depends on it."""

    def test_recorded_and_not_wired_into_the_release_path(self):
        baseline = (ROOT / "docs/v2.3/BASELINE.md").read_text(encoding="utf-8")
        self.assertRegex(baseline, r"CODE-AUDIT #30, ACCEPTED_LIMITATION\):\*\* `diagnostic\.yml` is the legacy "
                                   r"P7-FINDING-001")
        for name in ("release.yml", "staging.yml", "tests.yml"):
            self.assertNotIn("diagnostic", code(workflows()[name]), name)
        on = code(workflows()["diagnostic.yml"]).split("\non:", 1)[1].split("\njobs:", 1)[0]
        self.assertNotIn("release/", on)


# --------------------------------------------------------------------------------------- #52 (a) + (b) wiring

CLEAN = "git status --porcelain=v1 --untracked-files=all -- closure-evidence/"


class EvidenceUntouchedBySuite(unittest.TestCase):
    """#52: after the suite, on every leg of the unit job, the released-V2 guard runs and a step fails when
    closure-evidence/ differs from HEAD (a test that rewrote or added evidence, by any route)."""

    def _unit(self) -> list[str]:
        return steps(jobs(workflows()["tests.yml"])["unit"])

    def test_the_steps_follow_the_suite_and_cannot_be_skipped(self):
        st = self._unit()
        at = {k: next((i for i, s in enumerate(st) if k in s), None)
              for k in ("unittest discover -s tests", "v1_evidence_guard.py --check",
                        "python -P validation/v23/released_evidence_guard.py --check", CLEAN)}
        self.assertNotIn(None, at.values(), at)
        self.assertEqual(sorted(at, key=at.get), list(at))
        for k in ("python -P validation/v23/released_evidence_guard.py --check", CLEAN):
            self.assertNotRegex(st[at[k]], r"(?m)^ *(?:- +)?if:|continue-on-error", k)
        self.assertIn("shell: bash", st[at[CLEAN]])
        self.assertEqual([ln for ln in runs(st[at[CLEAN]]) if SWALLOW.search(ln)], [])
        self.assertNotRegex(jobs(workflows()["tests.yml"])["unit"], r"(?m)^    if:|continue-on-error")

    @unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "the step's bash, run here on POSIX")
    def test_the_clean_step_fails_on_a_changed_or_added_evidence_file_only(self):
        """Red-before: a test writing closure-evidence/v2/x.json left the unit job green (the V1 guard skips v2/,
        tests/v2/test_v1_evidence_guard.py::test_changes_under_v2_are_ignored); this step turns it red."""
        script = "\n".join(runs(next(s for s in self._unit() if CLEAN in s)))
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

            def git(*a):
                subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                               cwd=d, env=env, check=True, capture_output=True)

            def step() -> int:
                return subprocess.run(["bash", "-c", script], cwd=d, env=env, capture_output=True).returncode

            git("init", "-q")
            pathlib.Path(d, "closure-evidence/v2").mkdir(parents=True)
            pathlib.Path(d, "closure-evidence/v2/r.json").write_text("{}\n", encoding="utf-8")
            pathlib.Path(d, ".gitignore").write_text("closure-evidence/*.rows.jsonl\n", encoding="utf-8")
            git("add", "-A")
            git("commit", "-q", "-m", "c")
            self.assertEqual(step(), 0)
            pathlib.Path(d, "closure-evidence/local.rows.jsonl").write_text("ignored\n", encoding="utf-8")
            self.assertEqual(step(), 0)                                   # git-ignored local artefact: not evidence
            pathlib.Path(d, "closure-evidence/v2/x.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual(step(), 1)                                   # added
            pathlib.Path(d, "closure-evidence/v2/x.json").unlink()
            pathlib.Path(d, "closure-evidence/v2/r.json").write_text("{ }\n", encoding="utf-8")
            self.assertEqual(step(), 1)                                   # rewritten
            pathlib.Path(d, "closure-evidence/v2/r.json").unlink()
            self.assertEqual(step(), 1)                                   # deleted


# --------------------------------------------------------------------------------------- CI-INCR

class IncrementalQualificationJob(unittest.TestCase):
    """CI-INCR-JOB under the owner-approved TWO-TIER policy (ruling 2026-11-22 §4; docs/v2.3/amendments/CI-TWO-TIER.md,
    which supersedes W1-DESIGN §11 exit gate 2's always-fail for DEVELOPMENT pushes — the rc tier keeps it). `gate`
    (release/** pushes, PRs) runs ci_gate --tier develop: the truthful F5 state table plus the pinned negative
    controls, exit 0 while evidence is incomplete (final line `EVIDENCE: INCOMPLETE (NOT QUALIFIED)`), non-zero only on
    checker malfunction, false-current reuse or negative-control regression. `rc` (release tags, or dispatch with
    tier=rc) runs ci_gate --tier rc: additionally fails while any target lacks valid MEASURED or VERIFIED_REUSE
    evidence. `plan` (dispatch) lists the affected targets with reasons. No mutant runs; no exception list exists in
    the gate or the workflow (tested below as the literal string)."""

    TEXT = (WF / "mutation-incr.yml").read_text(encoding="utf-8") if (WF / "mutation-incr.yml").exists() else ""
    GATE_PY = ROOT / "validation" / "v23" / "ci_gate.py"

    def test_triggers_permissions_and_no_secret(self):
        c = code(self.TEXT)
        self.assertTrue(c, "no .github/workflows/mutation-incr.yml")
        on = c.split("\non:", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(re.findall(r"(?m)^  (\w+):", on), ["push", "pull_request", "workflow_dispatch"])
        self.assertIn('branches: ["release/**"]', on)
        self.assertIn('tags: ["v[0-9]*.[0-9]*.[0-9]*"]', on)   # the rc tier fires on exactly the release-tag shape
        self.assertRegex(c, r"(?m)^permissions:\n  contents: read\n\s*jobs:")
        self.assertNotIn("secrets", c)
        self.assertNotIn("permissions", "".join(jobs(c).values()))     # no job widens the read-only token

    def test_two_tiers_the_engine_only_never_a_campaign(self):
        c = code(self.TEXT)
        for forbidden in ("mutation.py", "b1_bindings_check", "run-affected", "pip install"):
            self.assertNotIn(forbidden, c)
        js = jobs(c)
        self.assertEqual(sorted(js), ["gate", "plan", "rc"])
        self.assertEqual(runs(js["gate"])[-1], "python -P validation/v23/ci_gate.py --tier develop")
        self.assertEqual(runs(js["rc"])[-1], "python -P validation/v23/ci_gate.py --tier rc")
        self.assertEqual(runs(js["plan"])[-1], "python -P validation/v23/impact.py --classify --affected")
        self.assertRegex(js["gate"],
                         r"(?m)^    if: github\.event_name != 'workflow_dispatch' && github\.ref_type != 'tag'$")
        self.assertRegex(js["rc"], r"(?m)^    if: github\.ref_type == 'tag' \|\| \(github\.event_name == "
                                   r"'workflow_dispatch' && inputs\.tier == 'rc'\)$")
        self.assertRegex(js["plan"], r"(?m)^    if: github\.event_name == 'workflow_dispatch' && inputs\.tier != 'rc'$")

    def test_no_exception_list_in_the_gate_or_the_workflow(self):
        """Ruling §4: 'without allowlists masking qualification failures' — the string is absent from both files
        (comments included), so no variant of the v2.1.0 release-tag exception mechanism can quietly return."""
        self.assertNotIn("allowlist", self.TEXT.lower())
        self.assertTrue(self.GATE_PY.exists(), "validation/v23/ci_gate.py is missing")
        self.assertNotIn("allowlist", self.GATE_PY.read_text(encoding="utf-8").lower())

    def test_the_mutation_worker_guard_and_full_history(self):
        self.assertEqual(sorted(jobs(code(self.TEXT))), ["gate", "plan", "rc"])
        for name, block in jobs(code(self.TEXT)).items():
            with self.subTest(name):
                self.assertIn("runs-on: ubuntu-latest", block)
                self.assertRegex(block, r"(?m)^    timeout-minutes: \d+$")
                self.assertRegex(block, r"fetch-depth: 0\b")             # a shallow clone has no basis (N10)
                self.assertIn('if command -v opencode; then echo "OPENCODE PRESENT — refusing"; exit 1; fi', runs(block))
                for var in ("DATA", "STATE", "CACHE"):
                    self.assertIn(f"XDG_{var}_HOME: ${{{{ runner.temp }}}}/xdg/{var.lower()}", block)
                # GitHub rejects the whole file when a job-level key uses the runner context (run 44974302513)
                self.assertNotIn("runner.", block.split("steps:", 1)[0])
                self.assertEqual(re.findall(r"(?m)^ +(?:- +)?if:.*$", block.split("steps:", 1)[1]), [])
                self.assertNotIn("continue-on-error", block)
                self.assertEqual([ln for ln in runs(block) if SWALLOW.search(ln)], [])


# --------------------------------------------------------------------------------------- CT-5, CT-6

class LedgerAppendOnly(unittest.TestCase):
    """CT-5 (CR-14): RELEASE-DECISIONS entries 1-12 are value-identical to tag v2.2.0's; seq strictly increasing."""

    REL = "closure-evidence/v2/cycle2/RELEASE-DECISIONS.json"

    def test_entries_1_to_12_unchanged_and_seq_increasing(self):
        tag = json.loads(_git("show", f"v2.2.0:{self.REL}"))["entries"]
        head = json.loads((ROOT / self.REL).read_text(encoding="utf-8"))["entries"]
        self.assertEqual([e["seq"] for e in tag], list(range(1, 13)))
        self.assertEqual(head[:12], tag)
        seqs = [e["seq"] for e in head]
        self.assertTrue(all(isinstance(s, int) for s in seqs), seqs)
        self.assertEqual(seqs, sorted(set(seqs)), "seq must be strictly increasing")


class HistoryKept(unittest.TestCase):
    """CT-6 (CR-13): every closure-evidence/v2 blob of the branch base 399b775f, and of tag v2.2.0, is unchanged at HEAD
    (additions allowed), by git blob. The CI step runs the same check with the working tree. CIGOV-R1 OPEN: this
    includes the ledger CT-5 lets grow, so the two cannot both hold after a seq 13 append (amendments/CIGOV-R1.md)."""

    def test_committed_v2_history_is_unchanged(self):
        for rev in (RE.BRANCH_BASE, RE.RELEASED):
            with self.subTest(rev):
                self.assertGreater(len(RE.entries(rev)), 6000)
                self.assertEqual(RE.committed_changes(rev), [])


if __name__ == "__main__":
    unittest.main()
