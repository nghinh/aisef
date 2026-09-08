"""Phát hiện brownfield — dự án đã có mã nguồn, không chỉ requirements.md.

Greenfield: chưa có gì ngoài tài liệu yêu cầu.
Brownfield: đã có source, test, config, CI, schema, docs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_SRC_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
             ".rb", ".php", ".cs", ".swift", ".kt", ".c", ".cpp", ".h"}
_TEST_PAT = {"test_", "_test.", ".test.", ".spec.", "tests/", "__tests__/"}
_CONFIG_FILES = {
    "package.json", "pyproject.toml", "setup.py", "setup.cfg",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "Gemfile", "composer.json", "Makefile", "CMakeLists.txt",
}
_CI_DIRS = {".github", ".gitlab-ci.yml", ".circleci", "Jenkinsfile", ".travis.yml"}
_SCHEMA_EXTS = {".sql", ".prisma"}
_SCHEMA_DIRS = {"migrations", "alembic"}
_DOC_FILES = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "ADR"}
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "dist",
    "build", ".next", ".nuxt", "target", "vendor", "_bmad-output",
    "graphify-out", ".aisef",
}


@dataclass
class BrownfieldSignal:
    """Tín hiệu từ hệ thống hiện tại."""
    source_files: int = 0
    test_files: int = 0
    config_files: list[str] = field(default_factory=list)
    ci_present: bool = False
    schema_files: int = 0
    doc_files: list[str] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    package_managers: list[str] = field(default_factory=list)
    total_loc: int = 0

    @property
    def is_brownfield(self) -> bool:
        return self.source_files >= 3

    @property
    def summary(self) -> str:
        parts = [f"{self.source_files} source"]
        if self.test_files:
            parts.append(f"{self.test_files} test")
        if self.config_files:
            parts.append(f"config: {', '.join(self.config_files[:5])}")
        if self.ci_present:
            parts.append("CI")
        if self.schema_files:
            parts.append(f"{self.schema_files} schema")
        langs = sorted(self.languages.items(), key=lambda kv: -kv[1])[:5]
        if langs:
            parts.append("langs: " + ", ".join(f"{k}({v})" for k, v in langs))
        return " · ".join(parts)


def detect(project: Path, *, limit: int = 10_000) -> BrownfieldSignal:
    """Quét nhanh dự án — dừng sau ``limit`` file."""
    sig = BrownfieldSignal()
    seen = 0

    for name in os.listdir(project):
        if name in _CONFIG_FILES:
            sig.config_files.append(name)
            if name == "package.json":
                sig.package_managers.append("npm")
            elif name == "pyproject.toml":
                sig.package_managers.append("pip")
            elif name == "go.mod":
                sig.package_managers.append("go")
            elif name == "Cargo.toml":
                sig.package_managers.append("cargo")
        if name in _CI_DIRS or (project / name).is_file() and name in _CI_DIRS:
            sig.ci_present = True
        if name in _DOC_FILES:
            sig.doc_files.append(name)

    if (project / ".github" / "workflows").is_dir():
        sig.ci_present = True

    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for f in files:
            seen += 1
            if seen > limit:
                return sig
            p = Path(f)
            ext = p.suffix.lower()
            if ext in _SRC_EXTS:
                sig.source_files += 1
                lang = ext.lstrip(".")
                sig.languages[lang] = sig.languages.get(lang, 0) + 1
                rel = os.path.join(root, f)
                if any(pat in rel.lower() for pat in _TEST_PAT):
                    sig.test_files += 1
            elif ext in _SCHEMA_EXTS:
                sig.schema_files += 1
            dirname = os.path.basename(root)
            if dirname in _SCHEMA_DIRS and ext == ".py":
                sig.schema_files += 1
    return sig
