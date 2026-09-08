from __future__ import annotations
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients.base import (
    Capability, ClientAdapter, Support, RunSpec, ENV_KEEP, ENV_KEEP_PREFIXES,
    GIT_NO_CREDENTIALS, child_env,
)
from aisef.clients.stream import RunResult


class TestSupport(unittest.TestCase):

    def test_native_blocks(self):
        self.assertTrue(Support.NATIVE.blocks_at_source)

    def test_emulated_blocks(self):
        self.assertTrue(Support.EMULATED.blocks_at_source)

    def test_post_hoc_does_not_block(self):
        self.assertFalse(Support.POST_HOC.blocks_at_source)

    def test_unsupported_does_not_block(self):
        self.assertFalse(Support.UNSUPPORTED.blocks_at_source)


class TestChildEnv(unittest.TestCase):

    CLEAN_ENV = {
        "PATH": "/usr/bin",
        "HOME": "/home/test",
        "ANTHROPIC_API_KEY": "sk-test",
        "SECRET_STUFF": "nope",
        "LC_ALL": "en_US.UTF-8",
    }

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_keeps_path(self):
        env = child_env({})
        self.assertEqual(env["PATH"], "/usr/bin")

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_keeps_anthropic_prefix(self):
        env = child_env({})
        self.assertEqual(env["ANTHROPIC_API_KEY"], "sk-test")

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_drops_unknown(self):
        env = child_env({})
        self.assertNotIn("SECRET_STUFF", env)

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_adds_git_no_credentials(self):
        env = child_env({})
        for k, v in GIT_NO_CREDENTIALS.items():
            self.assertEqual(env[k], v)

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_spec_env_overlays(self):
        env = child_env({"PATH": "/custom", "NEW": "val"})
        self.assertEqual(env["PATH"], "/custom")
        self.assertEqual(env["NEW"], "val")

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_empty_prefix_filtered(self):
        env = child_env({}, allow_prefixes=("", "MY_"))
        self.assertNotIn("SECRET_STUFF", env)

    @patch.dict("os.environ", {**CLEAN_ENV, "MY_VAR": "yes"}, clear=True)
    def test_allow_prefixes(self):
        env = child_env({}, allow_prefixes=("MY_",))
        self.assertEqual(env["MY_VAR"], "yes")

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_keeps_lc_prefix(self):
        env = child_env({})
        self.assertEqual(env["LC_ALL"], "en_US.UTF-8")


class TestRunSpec(unittest.TestCase):

    def test_defaults(self):
        spec = RunSpec(prompt="hi", workdir=Path("/tmp"))
        self.assertEqual(spec.system_prompt, "")
        self.assertEqual(spec.model, "")
        self.assertEqual(spec.max_turns, 0)
        self.assertEqual(spec.timeout_seconds, 1800)
        self.assertEqual(spec.allowed_tools, [])
        self.assertEqual(spec.disallowed_tools, [])
        self.assertEqual(spec.extra_dirs, [])
        self.assertIsNone(spec.settings_file)
        self.assertEqual(spec.session_id, "")
        self.assertEqual(spec.env, {})
        self.assertEqual(spec.env_allow, [])


class _Stub(ClientAdapter):
    id = "stub"

    def __init__(self, caps: dict[Capability, Support] | None = None):
        self._caps = caps or {}

    def available(self) -> bool:
        return True

    def capabilities(self) -> dict[Capability, Support]:
        return self._caps

    def run(self, spec: RunSpec) -> RunResult:
        raise NotImplementedError


class TestClientAdapter(unittest.TestCase):

    def test_supports_known(self):
        s = _Stub({Capability.HEADLESS: Support.NATIVE})
        self.assertIs(s.supports(Capability.HEADLESS), Support.NATIVE)

    def test_supports_unknown_returns_unsupported(self):
        s = _Stub({})
        self.assertIs(s.supports(Capability.HEADLESS), Support.UNSUPPORTED)

    def test_guards_block_native(self):
        s = _Stub({Capability.PRE_TOOL_GUARD: Support.NATIVE})
        self.assertTrue(s.guards_block_at_source())

    def test_guards_block_post_hoc(self):
        s = _Stub({Capability.PRE_TOOL_GUARD: Support.POST_HOC})
        self.assertFalse(s.guards_block_at_source())

    def test_degradations_empty_when_all_native(self):
        caps = {Capability.HEADLESS: Support.NATIVE, Capability.SUBAGENT: Support.NATIVE}
        self.assertEqual(_Stub(caps).degradations(), [])

    def test_degradations_lists_non_native(self):
        caps = {
            Capability.HEADLESS: Support.NATIVE,
            Capability.TOOL_ALLOWLIST: Support.POST_HOC,
            Capability.SUBAGENT: Support.EMULATED,
        }
        d = _Stub(caps).degradations()
        self.assertEqual(len(d), 2)
        self.assertIn("subagent: emulated", d)
        self.assertIn("tool_allowlist: post_hoc", d)


if __name__ == "__main__":
    unittest.main()
