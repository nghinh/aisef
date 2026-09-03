"""Cấu hình và ngưỡng.

Mọi con số điều khiển hành vi nằm ở đây, không rải rác trong code. Lý do:
ngưỡng đúng cho dự án này thường sai cho dự án khác — coverage 85% hợp lý
với dịch vụ nội bộ nhưng thấp với thư viện dùng chung, và `max_parallel`
phụ thuộc hạn mức model lẫn sức máy.

Thứ tự ưu tiên: mặc định trong mã → `.ai/config.json` của dự án → biến
môi trường `AISDLC_*`. Càng gần chỗ chạy càng thắng.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_PATH = ".ai/config.json"
ENV_PREFIX = "AISDLC_"

#: Mặc định. Khoá dùng dấu chấm để nhóm theo chủ đề.
DEFAULTS: dict[str, Any] = {
    # chất lượng
    "coverage.min": 0.85,
    "security.block_severities": ["critical", "high"],
    # kích thước story — chống tràn ngữ cảnh trong một phiên
    "story.max_acceptance_criteria": 8,
    "story.max_write_scope_paths": 10,
    "story.max_context_tokens": 40000,
    # điều phối
    "run.max_parallel": 3,
    "run.max_turns": 40,
    "run.timeout_seconds": 1800,
    "run.max_retries": 2,
    # chi phí
    "cost.warn_multiple": 3.0,
    # lệnh kiểm định — rỗng nghĩa là "chưa cấu hình", KHÔNG phải "đạt"
    "verify.sit": "",
    "verify.api-contract": "",
    "verify.e2e": "",
    "verify.uat": "",
    "verify.perf": "",
    "verify.security": "",
    "verify.mutation": "",
    "verify.unit": "",
    "verify.sbom": "",
    "verify.image-scan": "",
    #: Loại được miễn tường minh, ngăn bởi dấu phẩy. Miễn phải là quyết
    #: định có người ký, không phải hệ quả của việc quên cấu hình.
    "verify.waived": "",
    # ứng dụng của dự án — để mở route thật lúc đối chiếu với mockup
    "app.dev_command": "",
    "app.base_url": "http://localhost:5173",
    "app.ready_timeout_seconds": 60,
    # định tuyến model theo vai — rỗng nghĩa là dùng mặc định của client
    "route.developer_model": "",
    "route.reviewer_model": "",
    "route.designer_model": "",
    # lệnh của dự án — rỗng nghĩa là tự dò từ file có trong dự án
    "tools.test": "",
    "tools.lint": "",
    "tools.sast": "",
    # sandbox
    "sandbox.image": "alpine:latest",
    "sandbox.allow_degraded": True,
}

#: Kiểu mong đợi, để bắt lỗi cấu hình sớm thay vì để nó nổ giữa chừng.
_TYPES: dict[str, type | tuple[type, ...]] = {
    "coverage.min": float,
    "security.block_severities": list,
    "story.max_acceptance_criteria": int,
    "story.max_write_scope_paths": int,
    "story.max_context_tokens": int,
    "run.max_parallel": int,
    "run.max_turns": int,
    "run.timeout_seconds": int,
    "run.max_retries": int,
    "cost.warn_multiple": float,
    "verify.sit": str,
    "verify.api-contract": str,
    "verify.e2e": str,
    "verify.uat": str,
    "verify.perf": str,
    "verify.security": str,
    "verify.mutation": str,
    "verify.unit": str,
    "verify.sbom": str,
    "verify.image-scan": str,
    "verify.waived": str,
    "app.dev_command": str,
    "app.base_url": str,
    "app.ready_timeout_seconds": int,
    "route.developer_model": str,
    "route.reviewer_model": str,
    "route.designer_model": str,
    "tools.test": str,
    "tools.lint": str,
    "tools.sast": str,
    "sandbox.image": str,
    "sandbox.allow_degraded": bool,
}


class ConfigError(ValueError):
    """Cấu hình sai kiểu hoặc ngoài khoảng cho phép."""


def _env_key(key: str) -> str:
    """`run.max_parallel` → `AISDLC_RUN_MAX_PARALLEL`."""
    return ENV_PREFIX + key.replace(".", "_").upper()


def _coerce(key: str, raw: str) -> Any:
    """Ép giá trị chuỗi từ biến môi trường về đúng kiểu."""
    want = _TYPES.get(key, str)
    try:
        if want is bool:
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if want is int:
            return int(raw)
        if want is float:
            return float(raw)
        if want is list:
            return [p.strip() for p in raw.split(",") if p.strip()]
        return raw
    except ValueError as e:
        raise ConfigError(f"{_env_key(key)}={raw!r} không ép được về {want.__name__}") from e


def _validate(values: dict[str, Any]) -> None:
    for key, want in _TYPES.items():
        if key not in values:
            continue
        val = values[key]
        # bool là lớp con của int trong Python — đừng để True lọt vào ô số
        if want is int and isinstance(val, bool):
            raise ConfigError(f"{key} phải là số nguyên, nhận {val!r}")
        if want is float and isinstance(val, int) and not isinstance(val, bool):
            values[key] = float(val)
            continue
        if not isinstance(val, want):
            raise ConfigError(f"{key} phải là {want.__name__}, nhận {type(val).__name__}")

    if not 0.0 <= values["coverage.min"] <= 1.0:
        raise ConfigError("coverage.min phải trong khoảng 0..1")
    for key in ("run.max_parallel", "run.max_turns", "run.timeout_seconds"):
        if values[key] < 1:
            raise ConfigError(f"{key} phải >= 1")
    if values["run.max_retries"] < 0:
        raise ConfigError("run.max_retries phải >= 0")
    if values["cost.warn_multiple"] <= 1.0:
        raise ConfigError("cost.warn_multiple phải > 1 thì cảnh báo mới có nghĩa")


@dataclass
class Config:
    values: dict[str, Any]
    source: str = "defaults"

    @classmethod
    def load(cls, project_root: Path | str = ".", *, env: dict[str, str] | None = None) -> Config:
        values = dict(DEFAULTS)
        sources = ["defaults"]

        path = Path(project_root) / CONFIG_PATH
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise ConfigError(f"{path} không phải JSON hợp lệ: {e}") from e
            unknown = sorted(set(loaded) - set(DEFAULTS))
            if unknown:
                raise ConfigError(f"khoá không nhận ra trong {path}: {', '.join(unknown)}")
            values.update(loaded)
            sources.append(str(path))

        environ = os.environ if env is None else env
        overridden = []
        for key in DEFAULTS:
            raw = environ.get(_env_key(key))
            if raw is not None:
                values[key] = _coerce(key, raw)
                overridden.append(key)
        if overridden:
            sources.append(f"env({len(overridden)})")

        _validate(values)
        return cls(values, source=" → ".join(sources))

    def __getitem__(self, key: str) -> Any:
        try:
            return self.values[key]
        except KeyError:
            raise KeyError(f"khoá cấu hình không tồn tại: {key}") from None

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def __contains__(self, key: object) -> bool:
        """Không có hàm này thì `key in config` rơi về duyệt theo chỉ số
        nguyên và báo lỗi khoá "0" — sai chỗ và khó lần ra."""
        return key in self.values

    def write_template(self, project_root: Path | str = ".") -> Path:
        """Ghi file cấu hình mặc định để người dùng chỉnh."""
        path = Path(project_root) / CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(DEFAULTS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return path
