"""Cấu hình và ngưỡng.

Mọi con số điều khiển hành vi nằm ở đây, không rải rác trong code. Lý do:
ngưỡng đúng cho dự án này thường sai cho dự án khác — coverage 85% hợp lý
với dịch vụ nội bộ nhưng thấp với thư viện dùng chung, và `max_parallel`
phụ thuộc hạn mức model lẫn sức máy.

Thứ tự ưu tiên: mặc định trong mã → `.ai/config.json` của dự án → biến
môi trường `AISEF_*`. Càng gần chỗ chạy càng thắng.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_PATH = ".ai/config.json"
ENV_PREFIX = "AISEF_"

#: Mặc định. Khoá dùng dấu chấm để nhóm theo chủ đề.
DEFAULTS: dict[str, Any] = {
    # chất lượng
    "coverage.min": 0.85,
    "security.block_severities": ["critical", "high"],
    # Rà soát bảo mật theo ngữ nghĩa, chạy cùng pha kiểm định.
    "security.semantic_review": True,
    # kích thước story — chống tràn ngữ cảnh trong một phiên
    "story.max_acceptance_criteria": 8,
    "story.max_write_scope_paths": 10,
    # trạng thái màn hình một story phải dựng (P2-12): đo 2026-09-05 trên e9,
    # story 11 và 18 trạng thái đều chạm max_turns ở lượt đầu và cần 4–8 lượt
    "story.max_screen_states": 8,
    # điểm cỡ story tổng hợp (ADR-004 R5) — trạng thái màn hình + tiêu chí +
    # phạm vi ghi + fan-in + hành vi VERIFIED bị chạm. Hiệu chuẩn B4 hồi cứu
    # 23 story thật (Spearman 0,88 trên 10 story có số lượt): 16 tách đúng hai
    # story đắt nhất (e9 01-04 23,5 và 01-05 18,0) khỏi phần còn lại (≤ 15,5).
    # Xem `control/complexity.py` và ADR-004 §6 R5.
    "story.max_complexity": 16.0,
    # Trần ký tự cho lát cắt chỉ mục bằng chứng nạp vào prompt (ADR-004 R6).
    # Chỉ mục thay cho việc đổ lịch sử: agent cần chi tiết thì gọi
    # `aisef evidence <id>`, không nạp sẵn cả sổ.
    "context.max_index_chars": 2000,
    # Trần ký tự cho hai slot R4 (`preservation`, `validation`) — hành vi
    # VERIFIED của story khác mà story này chạm tệp, và thứ phải xanh ở ứng
    # viên. Chỉ id + nguồn kiểm, không có lịch sử: đo trên sổ e9, STORY-01-07
    # chạm 31 hành vi của 3 story — đổ hết vào prompt là quá 15 % ngân sách B5.
    # Cổng "bảo toàn" vẫn kiểm **đủ** danh sách, cắt chỉ là cắt phần in ra.
    # 1 200, không phải 1 500: B5 hồi cứu e9 (ADR-004 §6 R4) đo developer
    # +17,5 % prompt với trần 1 500 — vượt trần 15 %; bớt ≈ 300 ký tự về ≈ 15 %.
    "context.max_preservation_chars": 1200,
    # Bản đồ mã quanh phạm vi ghi (ADR-005 V7, `harness/context.py`): skeleton
    # tệp trong phạm vi + lân cận 1 bước + test nhắc tên, nạp cho cả ba vai.
    # **0 = tắt** cho tới khi A/B T8 đạt (trung vị lượt −20 % **và** cổng cùng
    # kết cục): Aider không công bố số đo nào cho repo map, còn trần B5 là
    # +15 % prompt — 2 000 ký tự trên baseline 11 537 đã là +17 %, nên khi bật
    # thử 1 500 (≈ +13 %). Tắt thì developer vẫn tra được bằng `aisef ctx`.
    "context.max_repo_map_chars": 0,
    # Lệnh ngoài vẽ bản đồ (tree-sitter, serena… cắm sau, không thêm gói):
    # stdin JSON {project, seeds, budget} → stdout văn bản. Rỗng = dựng sẵn
    # stdlib; lệnh hỏng thì lùi về dựng sẵn và slot nói rõ là thô.
    "context.map_provider": "",
    # Nhà cung cấp đồ thị mã nguồn cho brownfield: "auto" (Graphify nếu có,
    # Basic nếu không), "graphify", "basic". Không bật MCP mặc định.
    "context.graph_provider": "auto",
    # vòng cải tiến epic theo bằng chứng (ADR-004 R3). HoH chạy T = 70 vòng
    # không có điều kiện dừng; ở đây mọi điều kiện dừng là code và ba số này
    # là trần. Đếm theo epic từ `loops[]` của sổ hành vi — chạy lại
    # `aisef improve` tiếp từ vòng cuối, không đếm lại từ 0.
    "improve.max_loops": 3,
    # dừng khi cải thiện biên (Δverified − Δreopened giữa hai mốc `loops[]`
    # liên tiếp) ≤ 0 chừng này vòng liền: vòng sau nhận cùng gap, cùng ngữ
    # cảnh, sẽ cho cùng kết quả.
    "improve.flat_loops": 2,
    # trần tổng chi phí (USD) các vòng của một epic; 0 = không giới hạn.
    # Chi phí đọc từ bằng chứng của story sửa, không từ lời client.
    "improve.cost_cap_usd": 0.0,
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
    "verify.accessibility": "",
    "verify.migration": "",
    "verify.sbom": "",
    "verify.image-scan": "",
    #: Loại được miễn tường minh, ngăn bởi dấu phẩy. Miễn phải là quyết
    #: định có người ký, không phải hệ quả của việc quên cấu hình.
    "verify.waived": "",
    #: Lý do miễn (phạm vi, ngày, người ký). `pre-deploy` đòi có lý do khi
    #: `verify.waived` khác rỗng và ghi nó vào `pre-deploy-report.json`;
    #: loại miễn hiện ◇, không bao giờ thành ✅.
    "verify.waiver_reason": "",
    # Baseline trước khi sửa (ADR-004 R9): harness chạy bộ test ở candidate
    # cha **trước** phiên developer đầu tiên, để cổng "không làm đỏ test có
    # sẵn" so được tên test xanh trước/sau. Tắt khi bộ test quá chậm — tắt
    # thì mục cổng là "không áp dụng: tắt bởi cấu hình", không phải đạt.
    "verify.baseline": True,
    # Kiểm định cấp dự án (`aisef qa`, `pre-deploy`, `improve`) chạy ở worktree
    # sạch dựng từ SHA đang chấm (ADR-005 V6, theo Harbor: dừng env agent rồi
    # chạy verifier ở chỗ tách): shim `node_modules/.bin/*`, `conftest.py`,
    # `pytest.ini` chưa commit không tới được cây kiểm; `node_modules`/venv mượn
    # của dự án. Giá phải trả: tệp **không theo dõi** mà test cần (`.env.test`,
    # fixture sinh tay) cũng không có ở đó — commit chúng, hoặc tắt khoá này
    # khi thật cần; tắt thì bằng chứng ghi `tree = "cây agent"`, không im lặng.
    # Mức story (`run`) giữ cây worktree: đã đóng băng và guard write-scope
    # đã chặn ngoài phạm vi — không đọc khoá này.
    "verify.clean_tree": True,
    # Nop control (ADR-005 V3): sau khi đóng băng ứng viên, chép tệp test story
    # thêm/sửa vào một worktree tạm ở SHA cha rồi chạy `tools.test` — test mang
    # mã tiêu chí phải **đỏ hoặc không tồn tại** khi không có mã của story.
    # Tắt khi bộ test quá chậm (+1 lần chạy test mỗi lượt) — tắt thì mục cổng
    # "test có kiểm được story" là "không áp dụng: tắt bởi cấu hình", không đạt.
    "verify.nop": True,
    # ứng dụng của dự án — để mở route thật lúc đối chiếu với mockup
    "app.dev_command": "",
    "app.base_url": "http://localhost:5173",
    "app.ready_timeout_seconds": 60,
    # định tuyến model theo vai — rỗng nghĩa là dùng mặc định của client
    "route.developer_model": "",
    "route.reviewer_model": "",
    "route.designer_model": "",
    "route.security_model": "",
    # Nhà cung cấp phân tích ảnh hưởng cho người rà soát (P0.3).
    "review.impact_provider": "",
    # Đưa mục "Kỹ năng có sẵn" (router chọn, tên + dùng khi) vào prompt
    # story. Tắt mặc định cho tới khi A/B trên `par` có số (ADR-003 §6).
    "skills.offer": False,
    # ADR-003 cơ chế B (thí nghiệm): dán thẳng nội dung skill được chọn cao nhất
    # vào prompt thay vì chỉ mời mở bằng tool `Skill` — đo trước khi quyết.
    "skills.inline": False,
    # lệnh của dự án — rỗng nghĩa là tự dò từ file có trong dự án
    "tools.test": "",
    "tools.lint": "",
    "tools.sast": "",
    # sandbox — ảnh rỗng nghĩa là tự chọn theo stack của dự án
    "sandbox.image": "",
    "sandbox.tools_network": False,
    "sandbox.use_docker": True,
    "sandbox.allow_degraded": True,
    # Provider chạy lệnh (ADR-005 V5): `docker` · `local` (chạy thẳng, mọi
    # bảo đảm UNSUPPORTED — bằng chứng ghi `missing`) · `"mô-đun:Lớp"` cho
    # backend ngoài cùng hợp đồng `harness/sandbox.py::ExecutionProvider`.
    # `use_docker=false` tương đương `local`; giữ để cấu hình cũ còn chạy.
    "sandbox.allow_hosts": [],
    "sandbox.provider": "docker",
    # Cổng trước triển khai **không** chấp nhận suy biến (kiểm định chạy
    # ngoài Docker) trừ khi có lý do khai tường minh ở đây; lý do được ghi
    # vào `pre-deploy.json`. `run` thường vẫn theo `sandbox.allow_degraded`.
    "sandbox.pre_deploy_degraded_waiver": "",
    # Tiền tố biến môi trường của máy được cho qua vào tiến trình client, ngoài
    # allowlist cố định (`clients.base.ENV_KEEP`: PATH HOME LANG LC_* TERM TMPDIR
    # SHELL USER LOGNAME SSL_CERT_FILE + `ANTHROPIC_*` + `AISEF_*`). Mặc định
    # rỗng (ADR-005 V2): agent không cầm thứ nó không cần, và cái nó cần thì dự
    # án khai tường minh — provider của OpenCode đọc khoá từ biến riêng thì khai
    # tiền tố ấy; CI xác thực Claude bằng `CLAUDE_CODE_OAUTH_TOKEN` thì khai tên
    # ấy (tên đầy đủ cũng là một tiền tố). Đo 2026-09-06 với `9router/mycombo`
    # (khoá nằm ở `~/.local/share/opencode/auth.json`, config chỉ đọc `{env:HOME}`):
    # OpenCode chạy đủ hợp quy với danh sách rỗng.
    "clients.env_allow": [],
}

#: Kiểu mong đợi, để bắt lỗi cấu hình sớm thay vì để nó nổ giữa chừng.
_TYPES: dict[str, type | tuple[type, ...]] = {
    "coverage.min": float,
    "security.block_severities": list,
    "security.semantic_review": bool,
    "story.max_acceptance_criteria": int,
    "story.max_write_scope_paths": int,
    "story.max_screen_states": int,
    "story.max_complexity": float,
    "context.max_index_chars": int,
    "context.max_preservation_chars": int,
    "context.max_repo_map_chars": int,
    "context.map_provider": str,
    "context.graph_provider": str,
    "improve.max_loops": int,
    "improve.flat_loops": int,
    "improve.cost_cap_usd": float,
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
    "verify.accessibility": str,
    "verify.migration": str,
    "verify.sbom": str,
    "verify.image-scan": str,
    "verify.waived": str,
    "verify.waiver_reason": str,
    "verify.baseline": bool,
    "verify.clean_tree": bool,
    "verify.nop": bool,
    "app.dev_command": str,
    "app.base_url": str,
    "app.ready_timeout_seconds": int,
    "route.developer_model": str,
    "route.reviewer_model": str,
    "route.designer_model": str,
    "route.security_model": str,
    "review.impact_provider": str,
    "skills.offer": bool,
    "skills.inline": bool,
    "tools.test": str,
    "tools.lint": str,
    "tools.sast": str,
    "sandbox.image": str,
    "sandbox.tools_network": bool,
    "sandbox.allow_hosts": list,
    "sandbox.use_docker": bool,
    "sandbox.allow_degraded": bool,
    "sandbox.provider": str,
    "sandbox.pre_deploy_degraded_waiver": str,
    "clients.env_allow": list,
}


#: Khoá đã gỡ, kèm lý do. Gặp trong `.ai/config.json` thì **cảnh báo rồi bỏ
#: qua**, không lỗi: dự án cũ phải nạp được. Một knob không có mã đọc là một
#: lời hứa suông — đúng lớp "chưa cấu hình ≠ đạt" áp cho cấu hình.
RETIRED: dict[str, str] = {
    "story.max_context_tokens": (
        "2026-09-05 — chưa từng có mã đọc; thay bằng `prompt_chars` ghi vào "
        "evidence của mỗi lượt gọi model, `aisef status` cảnh báo story vượt "
        "3× trung vị"
    ),
}


class ConfigError(ValueError):
    """Cấu hình sai kiểu hoặc ngoài khoảng cho phép."""


def _env_key(key: str) -> str:
    """`run.max_parallel` → `AISEF_RUN_MAX_PARALLEL`."""
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
    for key in ("improve.max_loops", "improve.flat_loops"):
        if values[key] < 1:
            raise ConfigError(f"{key} phải >= 1")
    if values["context.max_repo_map_chars"] < 0:
        raise ConfigError("context.max_repo_map_chars phải >= 0 (0 = tắt)")
    if values["improve.cost_cap_usd"] < 0:
        raise ConfigError("improve.cost_cap_usd phải >= 0 (0 = không giới hạn)")
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
            retired = sorted(k for k in loaded if k in RETIRED)
            for k in retired:
                print(f"cấu hình: `{k}` không còn tác dụng ({RETIRED[k]}) — xoá khỏi {path}",
                      file=sys.stderr)
                loaded.pop(k)
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

    def overlay(self, overrides: dict[str, object]) -> "Config":
        """Trả Config mới với giá trị đã ghi đè — dùng cho stack preset."""
        merged = dict(self.values)
        merged.update(overrides)
        return Config(merged, source=self.source)

    def write_template(self, project_root: Path | str = ".") -> Path:
        """Ghi file cấu hình để người dùng chỉnh."""
        path = Path(project_root) / CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.values, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return path
