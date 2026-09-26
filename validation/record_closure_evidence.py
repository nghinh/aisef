#!/usr/bin/env python3
"""Ghi bằng chứng tất định cho cổng đóng dự án — `aisef closure` chỉ **đọc**.

Vì sao tách ra thay vì để bộ chấm tự chạy: hợp đồng (§4.3, và quyết định của
chủ dự án) buộc bộ chấm chỉ-đọc — không gọi agent, không chạy việc tốn tiền,
không tự dựng gói, không tự cài. Nhưng bốn tiêu chí của G1 và hai của G2 nói về
những việc **phải chạy** mới biết: CI, `build`, `twine`, cài từ PyPI, bộ test,
lint. Cách duy nhất giữ cả hai là: chạy ở đây, ghi lại, để bộ chấm đọc bản ghi.

Bản ghi **không** được tin ở lời: `probe_ci_green` tự phân giải tag bằng git rồi
so commit, nên một lượt CI xanh ở commit khác không lọt được. Cũng vì thế bằng
chứng buộc vào commit: đổi một dòng mã là bản ghi hết hiệu lực, và đó là ý đồ —
"bộ test đã xanh ở đâu đó" không nói gì về cây hiện tại.

    python3 validation/record_closure_evidence.py            # tất cả
    python3 validation/record_closure_evidence.py suite lint # chỉ phần rẻ

Không tiêu một lượt gọi model nào. Lượt tốn nhất là bộ test (~5 phút) và lần
cài từ PyPI (~30 giây, cần mạng).
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "closure-evidence"
sys.path.insert(0, str(ROOT))

from aisef.control import planes  # noqa: E402

#: Members of a distribution that the build tool generates rather than copies —
#: they have no blob in the source tree and are not compared.
GENERATED = ("PKG-INFO", "setup.cfg")


def _run(*argv: str, cwd: Path | None = None, timeout: int = 1800) -> tuple[int, str]:
    p = subprocess.run(argv, cwd=cwd or ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _head() -> str:
    return _run("git", "rev-parse", "HEAD")[1].strip()


def _write(name: str, payload: dict) -> None:
    (OUT / name).parent.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  wrote closure-evidence/{name}")


# ---------------------------------------------------------------- G2.1 / G2.2


def record_suite() -> None:
    """G2.1. Ghi cả `skipped` và `tree`: một worktree bỏ qua ~61 phép nhiều hơn
    cây chính (`.gitignore` loại `references/*`, `.bench*/`, …), và trong dòng
    tóm tắt của pytest thì *bỏ qua* trông y như *đạt*."""
    main = _run("git", "rev-parse", "--show-toplevel")[1].strip()
    tree = "main" if Path(main).resolve() == ROOT else "worktree"
    code, out = _run(sys.executable, "-m", "pytest", "-q")
    m = re.search(r"(\d+) passed(?:, (\d+) skipped)?", out)
    fail = re.search(r"(\d+) failed", out)
    err = re.search(r"(\d+) error", out)
    _write("suite.json", {
        "commit": _head(), "tree": tree, "exit": code,
        "passed": int(m.group(1)) if m else 0,
        "skipped": int(m.group(2)) if m and m.group(2) else 0,
        "failed": int(fail.group(1)) if fail else 0,
        "errors": int(err.group(1)) if err else 0,
        "tool": "python -m pytest -q",
    })


def record_lint() -> None:
    """G2.2."""
    code, out = _run("ruff", "check", ".")
    _write("lint.json", {"commit": _head(), "exit": code, "tool": "ruff check .",
                         "summary": out.strip().splitlines()[-1] if out.strip() else ""})


# ---------------------------------------------------------------------- G5.4


def record_bench_selfcheck() -> None:
    """G5.4 nửa sau. Selfcheck chạy với binary giả — không tốn lượt model."""
    code, out = _run(sys.executable, "-m", "tests.bench", "selfcheck", timeout=600)
    # Dòng tổng kết, không phải cặp `n/n` **đầu tiên** gặp trong đầu ra: bản đầu
    # của hàm này bắt `(\d+)/(\d+)` ở bất cứ đâu và ghi **1/1** trong khi
    # selfcheck báo 19/19 — G5.4 chỉ so `passed == total`, nên một bản ghi 1/1
    # **đạt** một tiêu chí mà hợp đồng nói là 19 phép. Đúng lớp lỗi "đo được cái
    # khác rồi gọi là đo được cái này".
    m = re.search(r"(?m)^\s*(\d+)\s*/\s*(\d+)\s+đạt", out) or \
        re.search(r"(?m)^\s*(\d+)\s*/\s*(\d+)\b", out)
    _write("bench-selfcheck.json", {
        "commit": _head(), "exit": code,
        "passed": int(m.group(1)) if m else 0, "total": int(m.group(2)) if m else 0,
        "tool": "python -m tests.bench selfcheck",
    })


# ------------------------------------------------------------------------ G1


def _packager() -> str | None:
    """Interpreter có sẵn `build` **và** `twine`.

    `sys.executable` ở máy này là python3.14 hệ thống, không có hai gói ấy —
    và ghi "thiếu công cụ" thành `build_exit=1` là biến *không đo được* thành
    *đo ra đỏ*, đúng lớp lỗi hợp đồng gọi là false FAIL. Thà không ghi mục
    `package` để G1.2 ra `UNRUNNABLE` (chặn, và nói thiếu gì) còn hơn ghi một
    con số sai.
    """
    for cand in (ROOT / ".venv" / "bin" / "python", Path(sys.executable)):
        if not cand.exists():
            continue
        if _run(str(cand), "-c", "import build, twine")[0] == 0:
            return str(cand)
    return None


def _version() -> str:
    return re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)


def record_release() -> None:
    """G1.1–G1.4, một bản ghi bốn mục. Buộc vào **tag**, không vào HEAD: cái
    được phát hành là tag, còn HEAD đi tiếp sau đó."""
    ver = _version()
    tag = f"v{ver}"
    at_tag = _run("git", "rev-list", "-n", "1", tag)[1].strip()
    rec: dict = {"version": ver, "tag": tag}

    # G1.1 — CI trên đúng commit của tag, đọc từ GitHub.
    code, out = _run("gh", "run", "list", "--workflow=tests.yml", "--limit", "60",
                     "--json", "headSha,conclusion,workflowName", timeout=180)
    ci = {"tag": tag, "commit": at_tag, "workflow": "tests.yml", "conclusion": ""}
    if code == 0:
        for row in json.loads(out or "[]"):
            if str(row.get("headSha", "")).startswith(at_tag[:12]):
                ci["conclusion"] = row.get("conclusion") or ""
                ci["workflow"] = row.get("workflowName") or "tests.yml"
                break
    rec["ci"] = ci

    # G1.2 — build + twine, và chỉ khi có công cụ thật.
    py = _packager()
    if py is None:
        print("  ! skipping `package`: no interpreter here has both `build` and `twine`;"
              " G1.2 will read UNRUNNABLE, which is the honest answer")
    else:
        with tempfile.TemporaryDirectory() as td:
            b, _ = _run(py, "-m", "build", "--outdir", td, timeout=900)
            arts = sorted(str(p) for p in Path(td).glob("*"))
            t, _ = _run(py, "-m", "twine", "check", *arts, timeout=300) if arts else (1, "no artifacts")
            rec["package"] = {"commit": _head(), "build_exit": b, "twine_exit": t,
                              "artifacts": [Path(a).name for a in arts], "interpreter": py}

    # G1.3 + G1.4 — cài từ PyPI vào venv sạch, rồi hỏi chính bản đã cài.
    with tempfile.TemporaryDirectory() as td:
        venv = Path(td) / "v"
        _run(sys.executable, "-m", "venv", str(venv), timeout=300)
        pip, exe = venv / "bin" / "pip", venv / "bin" / "aisef"
        i, _ = _run(str(pip), "install", "-q", f"aisef=={ver}", timeout=900)
        reported = _run(str(exe), "--version")[1].strip().split()[-1] if exe.exists() else ""
        rec["pypi_install"] = {"version": ver, "install_exit": i, "version_reported": reported}
        probe = (
            "from importlib.resources import files;import json;r=files('aisef');"
            "print(json.dumps({n: sum(1 for _ in r.joinpath(*n.split('/')).iterdir())"
            " if r.joinpath(*n.split('/')).is_dir() else 0"
            " for n in ('kit/prompts','kit/rules','kit/skills','harness/assets')}))"
        )
        c, o = _run(str(venv / "bin" / "python"), "-c", probe, timeout=120)
        counts = json.loads(o.strip().splitlines()[-1]) if c == 0 and o.strip() else {}
        counts["kit/catalog.json"] = 1 if c == 0 else 0
        rec["packaged_data"] = counts
    _write("release.json", rec)


# ---------------------------------------------------------- G1.0 / G6.1 manifest


def _blob(rev: str, path: str) -> bytes | None:
    p = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{path}"], capture_output=True)
    return p.stdout if p.returncode == 0 else None


def _members(kind: str, data: bytes, ver: str) -> list[tuple[str, bytes]]:
    """`(source path, bytes)` for every file a distribution carries that maps
    onto the source tree. dist-info / egg-info / PKG-INFO are generated."""
    out = []
    if kind == "wheel":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if info.is_dir() or ".dist-info/" in info.filename:
                    continue
                out.append((info.filename, z.read(info)))
    else:
        prefix = f"aisef-{ver}/"
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for m in tf.getmembers():
                if not m.isfile() or not m.name.startswith(prefix):
                    continue
                rel = m.name[len(prefix):]
                if rel in GENERATED or ".egg-info/" in rel:
                    continue
                f = tf.extractfile(m)
                out.append((rel, f.read() if f else b""))
    return out


def _observe(kind: str, url: str, want_sha: str, ver: str, at_tag: str) -> dict:
    """Download the public artifact, re-hash it, and compare every member with
    the blob at the tag. `mismatched` and `unmapped` non-empty mean the artifact
    was not built from the release source — G1.0 blocks on either."""
    data = urllib.request.urlopen(url, timeout=120).read()
    got = hashlib.sha256(data).hexdigest()
    checked, mismatched, unmapped = 0, [], []
    for path, body in _members(kind, data, ver):
        blob = _blob(at_tag, path)
        if blob is None:
            unmapped.append(path)
        elif hashlib.sha256(blob).hexdigest() != hashlib.sha256(body).hexdigest():
            mismatched.append(path)
        else:
            checked += 1
    return {"url": url, "size": len(data), "sha256": got, "matches_published": got == want_sha,
            "members_checked": checked, "mismatched": mismatched, "unmapped": unmapped}


def record_manifest() -> None:
    """Release manifest — the release node G1.0 and G6.1 bind to (D-022).

    Taken from the **tag's** tree and the **public** PyPI artifacts, never from
    HEAD or a local build: `release_source_sha` is what the tag resolves to, the
    product digests are `planes.identity` at that commit under the rules in
    `docs/closure-gate.json`, the artifact digests are what PyPI publishes, and
    `observed` is the same files downloaded, re-hashed, and every member
    compared byte-for-byte with the tag's blobs. Runs anywhere with git and the
    network; the evaluator only ever reads the result.
    """
    ver = _version()
    tag = f"v{ver}"
    at_tag = _run("git", "rev-list", "-n", "1", tag)[1].strip()
    if not at_tag:
        raise SystemExit(f"tag {tag} does not resolve — tag the release before recording its manifest")
    spec = json.loads((ROOT / "docs/closure-gate.json").read_text(encoding="utf-8"))
    rules = planes.rules_from(spec)
    ident = planes.identity(ROOT, at_tag, rules)
    if ident.unresolved:
        print(f"  ! {len(ident.unresolved)} tracked path(s) at {tag} have no plane rule — "
              f"G1.0 will block until docs/closure-gate.json#planes classifies them: "
              f"{', '.join(ident.unresolved[:6])}")
    meta = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/aisef/{ver}/json", timeout=60))
    artifacts, observed = {}, {}
    for u in meta.get("urls") or []:
        kind = "wheel" if u.get("packagetype") == "bdist_wheel" else "sdist"
        artifacts[kind] = {"filename": u.get("filename"), "sha256": (u.get("digests") or {}).get("sha256"),
                           "size": u.get("size"), "upload_time": u.get("upload_time_iso_8601"),
                           "url": u.get("url")}
        observed[kind] = _observe(kind, u["url"], artifacts[kind]["sha256"], ver, at_tag)
        print(f"  {kind}: {observed[kind]['members_checked']} members bound to {tag}, "
              f"{len(observed[kind]['mismatched'])} mismatched, {len(observed[kind]['unmapped'])} unmapped")
    shipped = set()
    if "sdist" in observed:
        data = urllib.request.urlopen(artifacts["sdist"]["url"], timeout=120).read()
        shipped = {path for path, _ in _members("sdist", data, ver)}
    not_shipped = sorted(p for p in ident.paths if p not in shipped) if shipped else []
    if not_shipped:
        print(f"  ! {len(not_shipped)} PRODUCT_AFFECTING path(s) are not in the sdist: "
              f"{', '.join(not_shipped[:6])} — classification or build config is wrong")
    run: dict = {}
    code, out = _run("gh", "run", "list", "--workflow=release.yml", "--limit", "20",
                     "--json", "headSha,conclusion,databaseId,createdAt", timeout=120)
    if code == 0:
        for row in json.loads(out or "[]"):
            if str(row.get("headSha", "")).startswith(at_tag[:12]):
                run = {"id": str(row.get("databaseId")), "conclusion": row.get("conclusion"),
                       "created_at": row.get("createdAt")}
                break
    readme = _run("git", "rev-parse", f"{at_tag}:README.md")[1].strip()
    _write(f"releases/{ver}.json", {
        "schema_version": 1,
        "version": ver, "tag": tag, "release_source_sha": at_tag,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "recorded_at_commit": _head(),
        "product": ident.as_dict(),
        "product_not_shipped": not_shipped,
        "readme_blob_at_release": readme,
        "artifacts": artifacts,
        "observed": observed,
        "release_run": run,
        "tooling": {"recorder_python": platform.python_version(), "platform": platform.platform(),
                    "built_by": "github release workflow (trusted publishing)" if run else ""},
    })


STEPS = {"suite": record_suite, "lint": record_lint,
         "bench": record_bench_selfcheck, "release": record_release,
         "manifest": record_manifest}

if __name__ == "__main__":
    want = sys.argv[1:] or list(STEPS)
    bad = [w for w in want if w not in STEPS]
    if bad:
        raise SystemExit(f"unknown step(s) {bad} — pick from {list(STEPS)}")
    for name in want:
        print(f"recording {name} …")
        STEPS[name]()
    print("done — `aisef closure` reads these; it never writes them.")
