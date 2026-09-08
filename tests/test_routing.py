"""Test harness/routing.py — role assignment and session separation."""

from __future__ import annotations

import unittest
from pathlib import Path

from aisef.harness.routing import (
    DESIGNER,
    DEVELOPER,
    REVIEWER,
    ROLES,
    SECURITY,
    Role,
    Routing,
    RoutingError,
    build_spec,
    role_of,
)
from aisef.harness.prompts import Prompt
from aisef.harness.sandbox import Level


def _prompt(name: str) -> Prompt:
    return Prompt(name=name, version=1, role="", body="body")


class TestRoles(unittest.TestCase):

    def test_four_roles_defined(self):
        self.assertEqual(sorted(ROLES), sorted([DESIGNER, DEVELOPER, REVIEWER, SECURITY]))

    def test_developer_may_resume(self):
        self.assertTrue(ROLES[DEVELOPER].may_resume)

    def test_reviewer_may_not_resume(self):
        self.assertFalse(ROLES[REVIEWER].may_resume)

    def test_security_may_not_resume(self):
        self.assertFalse(ROLES[SECURITY].may_resume)

    def test_designer_may_not_resume(self):
        self.assertFalse(ROLES[DESIGNER].may_resume)

    def test_reviewer_disallows_write(self):
        r = ROLES[REVIEWER]
        for tool in ("Write", "Edit", "NotebookEdit"):
            self.assertIn(tool, r.disallowed_tools, f"{tool} must be disallowed for reviewer")

    def test_security_disallows_write(self):
        r = ROLES[SECURITY]
        for tool in ("Write", "Edit", "NotebookEdit"):
            self.assertIn(tool, r.disallowed_tools, f"{tool} must be disallowed for security")

    def test_developer_allows_write(self):
        self.assertEqual(ROLES[DEVELOPER].disallowed_tools, ())

    def test_reviewer_read_only_level(self):
        self.assertEqual(ROLES[REVIEWER].level, Level.READ_ONLY)

    def test_security_read_only_level(self):
        self.assertEqual(ROLES[SECURITY].level, Level.READ_ONLY)

    def test_developer_workspace_write_level(self):
        self.assertEqual(ROLES[DEVELOPER].level, Level.WORKSPACE_WRITE)

    def test_designer_workspace_write_level(self):
        self.assertEqual(ROLES[DESIGNER].level, Level.WORKSPACE_WRITE)


class TestRoleOf(unittest.TestCase):

    def test_valid_role(self):
        r = role_of(DEVELOPER)
        self.assertIsInstance(r, Role)
        self.assertEqual(r.id, DEVELOPER)

    def test_unknown_role_raises(self):
        with self.assertRaises(RoutingError):
            role_of("nonexistent")


class TestRouting(unittest.TestCase):

    def test_empty_routing_returns_empty_model(self):
        r = Routing()
        self.assertEqual(r.model_for(DEVELOPER), "")

    def test_model_for_returns_configured(self):
        r = Routing(models={REVIEWER: "claude-3-haiku"})
        self.assertEqual(r.model_for(REVIEWER), "claude-3-haiku")
        self.assertEqual(r.model_for(DEVELOPER), "")

    def test_from_config_none(self):
        r = Routing.from_config(None)
        self.assertEqual(r.model_for(DEVELOPER), "")


class TestBuildSpec(unittest.TestCase):

    def test_developer_spec(self):
        prompt = _prompt("story-implement")
        spec = build_spec(DEVELOPER, prompt, {}, workdir=Path("/tmp/test"))
        self.assertEqual(spec.prompt, "body")
        self.assertEqual(spec.workdir, Path("/tmp/test"))
        self.assertEqual(spec.disallowed_tools, [])

    def test_reviewer_spec_has_disallowed_tools(self):
        prompt = _prompt("story-review")
        spec = build_spec(REVIEWER, prompt, {}, workdir=Path("/tmp/test"))
        self.assertIn("Write", spec.disallowed_tools)
        self.assertIn("Edit", spec.disallowed_tools)

    def test_wrong_prompt_for_role_raises(self):
        prompt = _prompt("story-implement")
        with self.assertRaises(RoutingError) as ctx:
            build_spec(REVIEWER, prompt, {}, workdir=Path("/tmp/test"))
        self.assertIn("story-review", str(ctx.exception))

    def test_reviewer_with_session_id_raises(self):
        prompt = _prompt("story-review")
        with self.assertRaises(RoutingError) as ctx:
            build_spec(REVIEWER, prompt, {}, workdir=Path("/tmp/test"), session_id="abc")
        self.assertIn("new session", str(ctx.exception))

    def test_security_with_session_id_raises(self):
        prompt = _prompt("story-security-review")
        with self.assertRaises(RoutingError) as ctx:
            build_spec(SECURITY, prompt, {}, workdir=Path("/tmp/test"), session_id="abc")
        self.assertIn("new session", str(ctx.exception))

    def test_developer_with_session_id_ok(self):
        prompt = _prompt("story-implement")
        spec = build_spec(DEVELOPER, prompt, {}, workdir=Path("/tmp/test"), session_id="abc")
        self.assertEqual(spec.session_id, "abc")

    def test_routing_model_applied(self):
        prompt = _prompt("story-implement")
        routing = Routing(models={DEVELOPER: "sonnet-4"})
        spec = build_spec(DEVELOPER, prompt, {}, workdir=Path("/tmp/test"), routing=routing)
        self.assertEqual(spec.model, "sonnet-4")

    def test_security_spec(self):
        prompt = _prompt("story-security-review")
        spec = build_spec(SECURITY, prompt, {}, workdir=Path("/tmp/test"))
        self.assertIn("Write", spec.disallowed_tools)
        self.assertEqual(spec.session_id, "")

    def test_designer_spec(self):
        prompt = _prompt("mockup-screen")
        spec = build_spec(DESIGNER, prompt, {}, workdir=Path("/tmp/test"))
        self.assertEqual(spec.disallowed_tools, [])

    def test_unknown_role_raises(self):
        prompt = _prompt("anything")
        with self.assertRaises(RoutingError):
            build_spec("ghost", prompt, {}, workdir=Path("/tmp/test"))


class TestRolePromptMapping(unittest.TestCase):
    """Each role maps to exactly one prompt name, and the prompts exist."""

    def test_developer_prompt_name(self):
        self.assertEqual(ROLES[DEVELOPER].prompt, "story-implement")

    def test_reviewer_prompt_name(self):
        self.assertEqual(ROLES[REVIEWER].prompt, "story-review")

    def test_security_prompt_name(self):
        self.assertEqual(ROLES[SECURITY].prompt, "story-security-review")

    def test_designer_prompt_name(self):
        self.assertEqual(ROLES[DESIGNER].prompt, "mockup-screen")


if __name__ == "__main__":
    unittest.main()
