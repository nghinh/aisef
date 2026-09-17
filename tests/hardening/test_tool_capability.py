"""SS-65 — INV-N.DEFAULT-CAPABILITY: a tool AISEF selects by default for a stack is executable in the managed
environment selected for that stack, and both come from ONE registry (aisef/harness/capabilities.py).

Deterministic, no Docker: probes run against a scripted sandbox that answers per image. The real-image half of the
invariant is `validation/tool_capability_qualification.py` (closure-evidence/hardening/tool-capability-matrix.json),
which W0 requires at the candidate's product tree.
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from aisef.config import DEFAULTS, Config, ConfigError, _validate  # noqa: E402
from aisef.control.identity import verifier_config_digest  # noqa: E402
from aisef.harness import capabilities as C  # noqa: E402
from aisef.harness import sandbox, tools, verify_image  # noqa: E402
from aisef.harness.observe import TOOL_RUN, EvidenceStore  # noqa: E402
from aisef.phases.qa import command_for_kind  # noqa: E402
from aisef.phases.run import _missing_tools  # noqa: E402

FAKE = "aisef.harness.sandbox:FakeProvider"
PY = C.profile_by_stack("python")
GO = C.profile_by_stack("go")


def _project(tmp: str, marker: str, body: str = "", **cfg) -> tuple[Path, Config]:
    root = Path(tmp)
    (root / marker).write_text(body, encoding="utf-8")
    return root, Config({**DEFAULTS, "sandbox.provider": FAKE, **cfg})


def _image_says(contents: dict[str, dict[str, str]]):
    """A sandbox whose images hold exactly `contents[image][tool] = output`; anything else is `not found` (127)."""
    def run(spec):
        have = contents.get(spec.image, {})
        argv = list(spec.cmd)
        key = argv[-1] if argv[:2] == ["go", "version"] and len(argv) == 4 else argv[0]
        if argv[:2] == ["cargo", "clippy"] or argv[:2] == ["cargo", "audit"]:
            key = " ".join(argv[:2])
        if key in have:
            return sandbox.SandboxResult(0, stdout=have[key])
        return sandbox.SandboxResult(127, stderr=f"sh: {argv[0]}: not found")
    return run


PY_IMAGE_OK = {PY.image: {"pytest": "pytest 9.1.1", "python": "pytest-cov 7.1.0", "ruff": "ruff 0.16.7", "bandit": "bandit 1.9.4"}}


class TestRegistryIsTheOnlySource(unittest.TestCase):
    def test_every_selectable_capability_is_provisioned_and_probed_by_its_own_profile(self):
        for p in C.PROFILES:
            for cap in p.capabilities:
                with self.subTest(stack=p.stack, tool=cap.tool_id):
                    if cap.provision is C.Provision.NONE:
                        self.assertEqual(cap.command, "")
                        self.assertTrue(cap.note, "a role the profile leaves empty says why")
                        continue
                    self.assertTrue(cap.command)
                    if cap.provision in (C.Provision.MANAGED, C.Provision.TOOLCHAIN):
                        self.assertTrue(cap.probes, "no probe → nothing proves it runs")
                        self.assertTrue(all(pr.expect for pr in cap.probes if pr.argv[0] != "test"),
                                        "every version-bearing probe pins what it must observe")
                        self.assertTrue(p.base and "@sha256:" in p.base, "the environment is pinned by digest")
                    if cap.provision is C.Provision.MANAGED:
                        self.assertTrue(cap.install and cap.version)
                        self.assertTrue(p.managed and p.image.startswith(C.MANAGED_PREFIX))
                        self.assertIn(p.digest[:12], p.image)
                        rendered = p.dockerfile()
                        for spec in cap.install:
                            arg = spec.partition(":")[2]
                            self.assertIn(arg.split("=")[0].split("@")[0], rendered, spec)
                    if cap.provision is C.Provision.PROJECT:
                        self.assertTrue(p.runtime, "a project tool relies on a runtime the image must provide")

    def test_managed_recipes_are_exactly_the_managed_profiles(self):
        self.assertEqual(set(verify_image.RECIPES), {p.stack for p in C.PROFILES if p.managed})
        for recipe in verify_image.RECIPES.values():
            self.assertIs(verify_image.recipe_for(recipe.image), recipe)

    def test_auto_selection_is_the_registry_for_every_marker(self):
        for p in C.PROFILES:
            for marker in p.markers:
                with self.subTest(marker=marker), tempfile.TemporaryDirectory() as tmp:
                    body = json.dumps({"scripts": {"test": "t", "lint": "l"}}) if marker == "package.json" else ""
                    (Path(tmp) / marker).write_text(body, encoding="utf-8")
                    got = tools.detect_commands(tmp)
                    self.assertEqual(got, {r.value: p.capability(r).command for r in C.Role})
                    self.assertEqual(tools.image_for(tmp), p.image)

    #: Advisory text for the agents' rule files (CLAUDE.md / AGENTS.md): it never selects, provisions or runs an
    #: evidence tool — asserted below — so repeating a command there is guidance, not a second source of truth.
    ADVISORY = ("aisef/kit/constitution.py",)

    def test_no_second_table_of_default_commands_exists_in_the_product(self):
        """The defect was two tables. No module but the registry may carry a default command as a literal."""
        defaults = {c.command for p in C.PROFILES for c in p.capabilities if c.command}
        offenders = []
        for rel in self.ADVISORY:
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertFalse(any(w in src for w in ("run_tool", "sandbox", "subprocess", "command_for")),
                             f"{rel} is exempt only while it runs nothing")
        for f in sorted((ROOT / "aisef").rglob("*.py")):
            if f.name == "capabilities.py" or f.relative_to(ROOT).as_posix() in self.ADVISORY:
                continue
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in defaults:
                    offenders.append(f"{f.relative_to(ROOT).as_posix()}:{node.lineno} {node.value!r}")
        self.assertEqual(offenders, [])

    def test_the_fallback_image_is_the_sandbox_default(self):
        self.assertEqual(C.FALLBACK_IMAGE, sandbox.DEFAULT_IMAGE)

    def test_every_preset_image_is_a_profile_image_and_go_lint_is_the_profiles(self):
        from aisef.cli.harness import STACK_PRESETS
        images = {p.image for p in C.PROFILES}
        for name, preset in STACK_PRESETS.items():
            with self.subTest(preset=name):
                self.assertIn(preset["sandbox.image"], images)
        self.assertEqual(STACK_PRESETS["go"]["tools.lint"], GO.capability(C.Role.LINT).command)
        self.assertEqual(STACK_PRESETS["go"]["sandbox.image"], GO.image)


class TestPythonAndGoKeepTheirSecurityDefault(unittest.TestCase):
    def test_python_selects_bandit_and_its_image_installs_the_pinned_version(self):
        cap = PY.capability(C.Role.SAST)
        self.assertEqual((cap.tool_id, cap.provision, cap.version), ("bandit", C.Provision.MANAGED, "1.9.4"))
        self.assertIn("bandit==1.9.4", PY.dockerfile())

    def test_go_selects_gosec_and_its_image_installs_the_pinned_version(self):
        cap = GO.capability(C.Role.SAST)
        self.assertEqual((cap.tool_id, cap.command, cap.version), ("gosec", "gosec ./...", "2.29.0"))
        self.assertIn("go install github.com/securego/gosec/v2/cmd/gosec@v2.29.0", GO.dockerfile())

    def test_node_has_no_automatic_sast_and_says_why(self):
        cap = C.profile_by_stack("node").capability(C.Role.SAST)
        self.assertIs(cap.provision, C.Provision.NONE)
        self.assertIn("network", cap.note)


class TestNegativeControls(unittest.TestCase):
    def test_declared_tool_missing_from_the_image_fails_the_check_and_blocks_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg = _project(tmp, "pyproject.toml")
            without_bandit = {PY.image: {k: v for k, v in PY_IMAGE_OK[PY.image].items() if k != "bandit"}}
            with mock.patch.object(sandbox, "run", side_effect=_image_says(without_bandit)):
                checks = {c.key: c for c in verify_image.check_tools(root, cfg, build=False)}
                missing = _missing_tools(root, Config({**cfg.values, "sandbox.image": PY.image}))
            self.assertEqual(checks["tools.sast"].state, "MISSING")
            self.assertIs(checks["tools.sast"].ok, False)
            self.assertTrue(checks["tools.test"].ok and checks["tools.lint"].ok)
            self.assertTrue(any("bandit" in m for m in missing), missing)

    def test_the_complete_managed_image_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg = _project(tmp, "pyproject.toml")
            with mock.patch.object(sandbox, "run", side_effect=_image_says(PY_IMAGE_OK)):
                checks = verify_image.check_tools(root, cfg, build=False)
            self.assertEqual([(c.key, c.state, c.tool_id) for c in checks],
                             [("tools.test", "present", "pytest"), ("tools.lint", "present", "ruff"), ("tools.sast", "present", "bandit")])

    def test_a_tool_the_image_carries_but_the_profile_does_not_select_never_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg = _project(tmp, "package.json", json.dumps({"scripts": {"test": "node t.js"}}))
            node = C.profile_by_stack("node").image
            fake = sandbox.FakeProvider([sandbox.SandboxResult(0, stdout="bandit 1.9.4")])
            with mock.patch.object(sandbox, "resolve_provider", return_value=fake):
                res = tools.run_tool("sast", root, story_id="S-1", artifact_root=root / "_a", config=cfg)
            self.assertTrue(res.skipped and not res.ok)
            self.assertEqual(fake.calls, [], f"nothing ran in {node}")
            self.assertEqual(command_for_kind("security", root, cfg), "")
            e = EvidenceStore(root / "_a").read("S-1").last(TOOL_RUN, "sast")
            self.assertFalse(e.ok)
            self.assertIn("no default Node SAST", e.detail["skipped"])

    def test_empty_tool_config_means_auto_and_only_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg = _project(tmp, "pyproject.toml", **{"tools.sast": ""})
            row = tools.resolved_tool("sast", root, cfg)
            self.assertEqual((row.mode, row.command), (C.Mode.AUTO, "bandit -q -r ."))

    def test_disabling_an_optional_tool_is_typed_and_never_falls_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg = _project(tmp, "pyproject.toml", **{"tools.disabled": ["sast"]})
            row = tools.resolved_tool("sast", root, cfg)
            self.assertEqual((row.mode, row.command), (C.Mode.DISABLED, ""))
            fake = sandbox.FakeProvider()
            with mock.patch.object(sandbox, "resolve_provider", return_value=fake), \
                 mock.patch("shutil.which", return_value="/usr/bin/bandit"):
                res = tools.run_tool("sast", root, story_id="S-1", artifact_root=root / "_a", config=cfg)
                self.assertEqual(command_for_kind("security", root, cfg), "", "a disabled sast has no qa fallback")
            self.assertEqual(fake.calls, [])
            self.assertEqual(res.skipped, "disabled by `tools.disabled`")
            self.assertEqual(res.detail.get("mode"), "disabled")
            self.assertNotIn("tools.sast", [k for k, _ in verify_image.declared_tools(cfg, root)])

    def test_a_required_tool_cannot_be_disabled(self):
        for role in ("test", "lint"):
            with self.subTest(role=role), self.assertRaises(ConfigError):
                _validate({**DEFAULTS, "tools.disabled": [role]})

    def test_disabled_and_explicit_at_once_is_refused(self):
        with self.assertRaises(ConfigError):
            _validate({**DEFAULTS, "tools.disabled": ["sast"], "tools.sast": "semgrep"})

    def test_a_version_mismatch_in_the_managed_image_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg = _project(tmp, "pyproject.toml")
            drifted = {PY.image: {**PY_IMAGE_OK[PY.image], "bandit": "bandit 1.8.0"}}
            with mock.patch.object(sandbox, "run", side_effect=_image_says(drifted)):
                sast = {c.key: c for c in verify_image.check_tools(root, cfg, build=False)}["tools.sast"]
            self.assertEqual((sast.state, sast.ok), ("VERSION_MISMATCH", False))
            self.assertIn("bandit 1.9.4", sast.detail)
            self.assertIn("bandit 1.8.0", sast.detail)

    def test_a_version_difference_in_a_project_declared_image_is_reported_not_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg = _project(tmp, "pyproject.toml", **{"sandbox.image": "corp/ci:1"})
            theirs = {"corp/ci:1": {**PY_IMAGE_OK[PY.image], "bandit": "bandit 1.8.0"}}
            with mock.patch.object(sandbox, "run", side_effect=_image_says(theirs)):
                sast = {c.key: c for c in verify_image.check_tools(root, cfg, build=False)}["tools.sast"]
            self.assertEqual((sast.state, sast.ok), ("present (version differs)", True))
            self.assertIn("bandit 1.8.0", sast.detail)

    def test_another_stacks_image_cannot_satisfy_a_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg = _project(tmp, "go.mod", "module x\n", **{"sandbox.image": PY.image})
            with mock.patch.object(sandbox, "run", side_effect=_image_says(PY_IMAGE_OK)):
                checks = {c.key: c for c in verify_image.check_tools(root, cfg, build=False)}
            self.assertEqual({k: c.state for k, c in checks.items()},
                             {"tools.test": "MISSING", "tools.lint": "MISSING", "tools.sast": "MISSING"})

    def test_a_missing_managed_tool_is_an_environment_failure_not_behavioural_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg = _project(tmp, "pyproject.toml")
            fake = sandbox.FakeProvider([sandbox.SandboxResult(127, stderr="sh: bandit: not found")])
            with mock.patch.object(sandbox, "resolve_provider", return_value=fake):
                res = tools.run_tool("sast", root, story_id="S-1", artifact_root=root / "_a", config=cfg)
            self.assertTrue(res.unrunnable, "typed as unrunnable, never a security finding")
            self.assertEqual(tools.outcome_kind(res), "TOOL_UNRUNNABLE")


class TestEnvironmentFailuresAreNeverBehaviouralRed(unittest.TestCase):
    """INV-N.1, measured on real images during the SS-65 sweep: the 1.7.x classifier scored these as real results."""

    def _kind(self, name, code, out):
        res = tools.ToolResult(name=name, ok=False, exit_code=code, stdout=out)
        res.unrunnable = tools.unrunnable_reason(name, code, out)
        return tools.outcome_kind(res)

    def test_a_missing_cargo_subcommand_is_a_missing_tool(self):
        out = "error: no such command: `clippy`\n\nhelp: run `rustup component add clippy` to install it"
        self.assertEqual(self._kind("lint", 101, out), tools.TOOL_UNRUNNABLE)
        self.assertEqual(self._kind("sast", 101, out.replace("clippy", "audit")), tools.TOOL_UNRUNNABLE)

    def test_a_tool_denied_network_by_the_sandbox_is_an_environment_failure(self):
        out = "npm warn audit request to https://registry.npmjs.org/-/npm/v1/security/audits/quick failed, reason: getaddrinfo EAI_AGAIN registry.npmjs.org"
        self.assertEqual(self._kind("sast", 1, out), tools.ENVIRONMENT_FAILURE)

    def test_an_unwritable_toolchain_cache_is_an_environment_failure_even_for_test(self):
        out = "failed to initialize build cache at /.cache/go-build: mkdir /.cache: permission denied"
        self.assertEqual(self._kind("test", 1, out), tools.ENVIRONMENT_FAILURE)
        self.assertEqual(self._kind("lint", 1, out), tools.ENVIRONMENT_FAILURE)

    def test_a_missing_python_dependency_is_not_mistaken_for_a_network_refusal(self):
        why = tools.unrunnable_reason("test", 1, "ModuleNotFoundError: No module named 'requests'")
        self.assertTrue(why.startswith(tools.NO_SETUP), why)          # `enotfound` inside ModuleNotFoundError is not a word

    def test_a_named_failing_test_stays_a_real_result(self):
        out = "test_calc.py::TestAdd::test_add FAILED\nE   OSError: getaddrinfo EAI_AGAIN api.example.com\n1 failed in 0.01s"
        self.assertEqual(self._kind("test", 1, out), tools.TEST_FAILED)

    def test_a_clean_security_finding_stays_a_real_result(self):
        out = ">> Issue: [B602:subprocess_popen_with_shell_equals_true] subprocess call with shell=True identified"
        self.assertEqual(self._kind("sast", 1, out), tools.TOOL_FAILED)


class TestTheContractDocumentIsRendered(unittest.TestCase):
    def test_tool_capabilities_md_matches_the_registry(self):
        sys.path.insert(0, str(ROOT / "validation"))
        import render_hardening_docs as R
        self.assertEqual((ROOT / "docs/TOOL-CAPABILITIES.md").read_text(encoding="utf-8"), R.render_capabilities(),
                         "run `python3 validation/render_hardening_docs.py capabilities`")


class TestTheNewKeyDoesNotMoveSignedDigests(unittest.TestCase):
    def test_tools_disabled_at_its_default_leaves_the_verifier_digest_unchanged(self):
        before = dict(DEFAULTS); before.pop("tools.disabled")
        self.assertEqual(verifier_config_digest(Config(before)), verifier_config_digest(Config(dict(DEFAULTS))))

    def test_disabling_a_role_changes_what_a_verdict_means(self):
        self.assertNotEqual(verifier_config_digest(Config(dict(DEFAULTS))),
                            verifier_config_digest(Config({**DEFAULTS, "tools.disabled": ["sast"]})))


if __name__ == "__main__":
    unittest.main()
