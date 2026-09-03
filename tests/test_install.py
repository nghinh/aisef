"""Kiểm chứng bộ cài skill vào dự án đích."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.kit import install  # noqa: E402
from aisdlc.kit.detect_stack import detect  # noqa: E402
from aisdlc.kit.install import MARKER, SKILLS_DIR, InstallPlan, PlannedSkill  # noqa: E402

REFERENCES = ROOT / "references"
needs_refs = unittest.skipUnless(REFERENCES.is_dir(), "chưa clone references/")


class InstallTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @property
    def skills_dir(self) -> Path:
        return self.project / SKILLS_DIR

    def fake_skill(self, name: str, body: str = "# skill\n") -> Path:
        """Tạo một thư mục skill giả trong khu tạm để làm nguồn."""
        src = self.project / "_src" / name
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(f"---\nname: {name}\n---\n{body}", encoding="utf-8")
        return src


class TestApply(InstallTestCase):
    def test_installs_and_marks(self):
        p = InstallPlan(skills=[PlannedSkill("a", "src", self.fake_skill("a"), "test")])
        r = install.apply(p, self.project)
        self.assertEqual(r.installed, ["a"])
        self.assertTrue((self.skills_dir / "a" / "SKILL.md").is_file())
        self.assertTrue((self.skills_dir / "a" / MARKER).is_file())

    def test_idempotent(self):
        p = InstallPlan(skills=[PlannedSkill("a", "src", self.fake_skill("a"), "test")])
        install.apply(p, self.project)
        r2 = install.apply(p, self.project)
        self.assertEqual(r2.installed, [])
        self.assertEqual(r2.unchanged, ["a"])

    def test_content_change_triggers_reinstall(self):
        src = self.fake_skill("a", "bản 1\n")
        p = InstallPlan(skills=[PlannedSkill("a", "src", src, "test")])
        install.apply(p, self.project)
        (src / "SKILL.md").write_text("---\nname: a\n---\nbản 2\n", encoding="utf-8")
        r = install.apply(p, self.project)
        self.assertEqual(r.installed, ["a"])
        self.assertIn("bản 2", (self.skills_dir / "a" / "SKILL.md").read_text())

    def test_removes_skill_no_longer_selected(self):
        """Đổi stack rồi cài lại không được để lại rác của lần trước."""
        p1 = InstallPlan(skills=[
            PlannedSkill("a", "src", self.fake_skill("a"), "test"),
            PlannedSkill("b", "src", self.fake_skill("b"), "test"),
        ])
        install.apply(p1, self.project)
        p2 = InstallPlan(skills=[PlannedSkill("a", "src", self.fake_skill("a"), "test")])
        r = install.apply(p2, self.project)
        self.assertEqual(r.removed, ["b"])
        self.assertFalse((self.skills_dir / "b").exists())

    def test_does_not_touch_user_skills(self):
        """Skill người dùng tự thêm (không có dấu) phải được giữ nguyên."""
        self.skills_dir.mkdir(parents=True)
        mine = self.skills_dir / "cua-toi"
        mine.mkdir()
        (mine / "SKILL.md").write_text("của tôi\n", encoding="utf-8")

        install.apply(InstallPlan(skills=[]), self.project)
        self.assertTrue((mine / "SKILL.md").is_file())


@needs_refs
class TestPlanOnRealSources(InstallTestCase):
    def plan_for(self, text: str) -> InstallPlan:
        return install.plan(
            self.project, detect(text),
            references_root=REFERENCES, requirements_text=text,
        )

    def test_full_stack_project(self):
        p = self.plan_for("Backend Python FastAPI, frontend React, PostgreSQL, Docker. Có đăng nhập.")
        counts = p.by_source()
        self.assertGreater(counts.get("bmad", 0), 20)
        self.assertGreater(counts.get("security", 0), 50)
        self.assertEqual(counts.get("superpowers"), 10)
        self.assertGreater(counts.get("ui-ux", 0), 0)

    def test_unlicensed_source_never_installed(self):
        """Bất biến pháp lý — karpathy không bao giờ vào dự án đích."""
        p = self.plan_for("Backend Python, React, Docker.")
        self.assertNotIn("karpathy", p.by_source())
        self.assertTrue(any(src == "karpathy" for src, _ in p.skipped_sources))

    def test_ui_skills_skipped_without_ui(self):
        p = self.plan_for("Công cụ dòng lệnh xử lý tệp, viết bằng Python.")
        self.assertNotIn("ui-ux", p.by_source())

    def test_cloud_project_gets_more_security_skills(self):
        cloud = self.plan_for("Go trên Kubernetes ở AWS, MySQL.")
        local = self.plan_for("Backend Python, PostgreSQL, Docker.")
        self.assertGreater(cloud.by_source()["security"], local.by_source()["security"])

    def test_no_duplicate_skill_names(self):
        p = self.plan_for("Backend Python, React, Docker. Có đăng nhập.")
        names = [s.name for s in p.skills]
        self.assertEqual(len(names), len(set(names)))

    def test_every_planned_skill_path_exists(self):
        for s in self.plan_for("Python, React, Docker.").skills:
            self.assertTrue((s.path / "SKILL.md").is_file(), s.name)

    def test_summary_mentions_skipped_reason(self):
        self.assertIn("license", self.plan_for("Python, Docker.").summary())


@needs_refs
class TestEndToEnd(InstallTestCase):
    def test_install_then_reinstall_is_stable(self):
        text = "Backend Python, frontend React, Docker."
        p = install.plan(self.project, detect(text),
                         references_root=REFERENCES, requirements_text=text)
        r1 = install.apply(p, self.project)
        r2 = install.apply(p, self.project)
        self.assertGreater(r1.total, 100)
        self.assertEqual(r1.total, r2.total)
        self.assertEqual(r2.installed, [])

    def test_installed_skills_are_readable(self):
        text = "Backend Python, Docker."
        p = install.plan(self.project, detect(text),
                         references_root=REFERENCES, requirements_text=text)
        install.apply(p, self.project)
        from aisdlc.kit.skills import scan

        found = scan(self.skills_dir)
        self.assertGreater(len(found), 50)
        self.assertTrue(all(s.name for s in found))


if __name__ == "__main__":
    unittest.main(verbosity=2)
