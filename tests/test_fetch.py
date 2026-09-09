"""Lấy nguồn skill về — điều kiện để bản cài bằng pip dùng được `setup`.

Lỗi gốc: `setup` đòi `references/` nằm sẵn trong dự án. Người cài bằng
`pip install aisef` không có thư mục đó, nên `setup` chết ở dòng đầu và
cả khung không chạy được lần nào.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.kit import fetch  # noqa: E402
from aisef.kit.catalog import Catalog, Source  # noqa: E402


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def kho_gia(d: Path) -> str:
    """Một kho git thật, tại chỗ — để test đường đi mà không cần mạng."""
    d.mkdir(parents=True, exist_ok=True)
    git("init", "--quiet", "-b", "main", str(d))
    git("config", "user.email", "t@t.t", cwd=d)
    git("config", "user.name", "T", cwd=d)
    (d / "SKILL.md").write_text("# skill", encoding="utf-8")
    git("add", "-A", cwd=d)
    git("commit", "--quiet", "-m", "x", cwd=d)
    return git("rev-parse", "HEAD", cwd=d).stdout.strip()


def nguon(repo: str, commit: str, **kw) -> Source:
    base = dict(id="thu", repo=repo, commit=commit, license="MIT",
                redistribute=True, local_path="references/thu",
                skill_roots=("skills",), selection="all")
    base.update(kw)
    return Source(**base)


class TestNoiCatNguon(unittest.TestCase):
    def test_mac_dinh_nam_trong_cache_khong_nam_trong_du_an(self):
        """Nguồn skill là tài sản của framework, dùng chung mọi dự án."""
        with TemporaryDirectory() as tmp:
            os.environ.pop(fetch.ENV_REFS, None)
            cu = os.environ.get("XDG_CACHE_HOME")
            os.environ["XDG_CACHE_HOME"] = tmp
            try:
                got = fetch.default_root()
            finally:
                os.environ.pop("XDG_CACHE_HOME", None)
                if cu is not None:
                    os.environ["XDG_CACHE_HOME"] = cu
            self.assertEqual(got, Path(tmp).resolve() / "aisef" / "references")

    def test_bien_moi_truong_de_ci_tro_sang_cho_khac(self):
        os.environ[fetch.ENV_REFS] = "/tmp/refs-cua-ci"
        try:
            self.assertEqual(fetch.default_root(), Path("/tmp/refs-cua-ci").resolve())
        finally:
            del os.environ[fetch.ENV_REFS]

    def test_duong_dan_dich_khop_voi_cho_catalog_di_tim_skill(self):
        """`_dir_of` và `Source.roots` phải đồng ý, nếu không lấy về xong
        vẫn báo "không có nguồn"."""
        s = nguon("http://x", "abc")
        root = Path("/c/aisef/references")
        self.assertEqual(fetch._dir_of(s, root), Path("/c/aisef/references/thu"))
        self.assertTrue(str(s.roots(root)[0]).startswith(str(fetch._dir_of(s, root))))


class TestLayVe(unittest.TestCase):
    def test_lay_dung_commit_da_ghim(self):
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            sha = kho_gia(t / "goc")
            cat = Catalog(sources=[nguon(str(t / "goc"), sha)])
            bao = fetch.ensure(t / "references", catalog=cat)
            self.assertEqual(bao.fetched, ["thu"], bao.summary())
            self.assertTrue((t / "references" / "thu" / "SKILL.md").is_file())
            self.assertEqual(
                git("rev-parse", "HEAD", cwd=t / "references" / "thu").stdout.strip(),
                sha,
            )

    def test_goi_lai_khong_lam_gi_them(self):
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            sha = kho_gia(t / "goc")
            cat = Catalog(sources=[nguon(str(t / "goc"), sha)])
            fetch.ensure(t / "references", catalog=cat)
            lai = fetch.ensure(t / "references", catalog=cat)
            self.assertEqual(lai.already, ["thu"])
            self.assertEqual(lai.fetched, [])

    def test_dung_commit_khac_thi_lay_lai(self):
        """Catalog ghim commit; thư mục đứng ở commit khác là không dùng được."""
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            sha1 = kho_gia(t / "goc")
            cat1 = Catalog(sources=[nguon(str(t / "goc"), sha1)])
            fetch.ensure(t / "references", catalog=cat1)

            (t / "goc" / "SKILL.md").write_text("# đổi rồi", encoding="utf-8")
            git("add", "-A", cwd=t / "goc")
            git("commit", "--quiet", "-m", "y", cwd=t / "goc")
            sha2 = git("rev-parse", "HEAD", cwd=t / "goc").stdout.strip()

            bao = fetch.ensure(t / "references", catalog=Catalog(
                sources=[nguon(str(t / "goc"), sha2)]))
            self.assertEqual(bao.fetched, ["thu"], bao.summary())
            self.assertIn("đổi rồi",
                          (t / "references" / "thu" / "SKILL.md").read_text(encoding="utf-8"))

    def test_mot_nguon_hong_khong_giet_cac_nguon_con_lai(self):
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            sha = kho_gia(t / "goc")
            cat = Catalog(sources=[
                nguon("/khong/co/dau", "0" * 40, id="hong",
                      local_path="references/hong"),
                nguon(str(t / "goc"), sha, id="that", local_path="references/that"),
            ])
            bao = fetch.ensure(t / "references", catalog=cat)
            self.assertEqual(bao.fetched, ["that"])
            self.assertEqual([i for i, _ in bao.failed], ["hong"])
            self.assertFalse(bao.ok)
            self.assertTrue((t / "references" / "that" / "SKILL.md").is_file())

    def test_lay_hong_khong_de_lai_thu_muc_do_dang(self):
        """Thư mục dở dang sẽ bị `Source.roots` coi là nguồn có thật."""
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            cat = Catalog(sources=[nguon("/khong/co/dau", "0" * 40)])
            fetch.ensure(t / "references", catalog=cat)
            self.assertFalse((t / "references" / "thu").exists())

    def test_lay_hong_khong_pha_ban_dang_dung(self):
        """Mạng hỏng giữa chừng không được làm mất nguồn đã có trên đĩa."""
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            sha = kho_gia(t / "goc")
            fetch.ensure(t / "references",
                         catalog=Catalog(sources=[nguon(str(t / "goc"), sha)]))
            bao = fetch.ensure(t / "references", catalog=Catalog(
                sources=[nguon("/khong/co/dau", "1" * 40)]))
            self.assertFalse(bao.ok)
            self.assertTrue((t / "references" / "thu" / "SKILL.md").is_file())

    def test_chon_loc_nguon_can_lay(self):
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            sha = kho_gia(t / "goc")
            cat = Catalog(sources=[
                nguon(str(t / "goc"), sha, id="a", local_path="references/a"),
                nguon(str(t / "goc"), sha, id="b", local_path="references/b"),
            ])
            bao = fetch.ensure(t / "references", catalog=cat, only=["a"])
            self.assertEqual(bao.fetched, ["a"])
            self.assertFalse((t / "references" / "b").exists())


class TestCatalogThat(unittest.TestCase):
    def test_moi_nguon_trong_catalog_deu_ghim_commit_that(self):
        """Không ghim commit thì không tái lập được — và `_at_commit` sẽ
        luôn trả False, tức là clone lại mỗi lần chạy."""
        for s in Catalog.load().sources:
            with self.subTest(nguon=s.id):
                self.assertRegex(s.commit, r"^[0-9a-f]{40}$", s.id)
                self.assertTrue(s.repo.startswith("http"), s.id)


if __name__ == "__main__":
    unittest.main()
