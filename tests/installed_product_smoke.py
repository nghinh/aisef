"""Clean-install PRODUCT smoke: the installed `aisef run`, end to end and offline (docs/v2/V2-STABLE-RELEASE-CHARTER.md
§9 "clean-install fixture"; owner ruling 'CONTINUE RELEASE EXECUTION / OWNER RULING FOR RISK-G7-1' §7 and §10: the
public path is installed artifact -> `aisef run`, and normal use never depends on the qualification harness).

Run by the interpreter of a fresh venv into which exactly the built wheel was installed, isolated (`-I`):

    <venv-python> -I tests/installed_product_smoke.py

The one-story calc project of tests/v2/test_app_run.py (its fixture functions, loaded by file path only after aisef2
was imported from the installed artifact; every loaded aisef/aisef2 module is checked to come from it), the fake
client on PATH, an isolated client configuration and a loopback fake provider: the venv's `aisef run --check` is
ready, `aisef run` delivers the story (exit 0) and `aisef run --verify` re-derives the run from its journal (exit 0).
Then the venv's `aisef demo` runs, and its three printed rows are asserted (its exit status alone proves nothing:
`demo.main` returns 0 whatever the verdicts). Nothing reaches a network or a model. Not collected by unittest (no
`test` prefix).

CODE-AUDIT #6 (non-A2 part), W1-DESIGN §7 — the historical-2.2 read:

    <venv-python> -I tests/installed_product_smoke.py --writer <the `aisef` of a venv holding the 2.2.0 wheel>

the writer's `aisef run` --check and run write the run, the candidate's `aisef run --verify` re-derives it (exit 0), and
its RUN.json carries the 2.2.0 kernel digest. The demo is not re-run in this mode.
"""

from __future__ import annotations

import argparse
import ast
import http.server
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading

HERE = pathlib.Path(__file__).resolve().parent
#: the kernel the published 2.2.0 wheel runs (closure-evidence/v2/release/V2.2.0-RC2-FREEZE.json "kernel")
KERNEL_2_2_0 = "c2d356b1cb1ed66652a6c1c88a4e7bd0fe962223430f131575de9432d9e334a0"
#: `aisef demo`'s three rows (tests/v2/test_v22_demo.py): delivery, the story's last outcome, verify
DEMO = {"correct": ("PASS", "COMMIT", "VERIFIED"), "caught": ("FAIL", "ROLLBACK", "VERIFIED"),
        "escape": ("PASS", "COMMIT", "VERIFIED")}
ROW = re.compile(r"^\[(\w+)\] .*\n    delivery (\S+)   stories (\{.*\})   verify (\S+)\n", re.M)
GAP = "    but: add(1, 1) returns 5"


class _Provider(http.server.BaseHTTPRequestHandler):
    """The fixture's provider: lists model-1 (owner fake), answers every chat as model-1 under one fingerprint."""

    def _send(self, doc: dict) -> None:
        body = json.dumps(doc).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):   # noqa: N802
        self._send({"data": [{"id": "model-1", "owned_by": "fake"}]})

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send({"model": "model-1", "system_fingerprint": "fp-1", "usage": {"prompt_tokens": 9, "completion_tokens": 1}})

    def log_message(self, *a):
        pass


def _outside_the_artifact() -> list[str]:
    prefix = pathlib.Path(sys.prefix).resolve()
    return sorted(name for name, mod in list(sys.modules.items()) if name.split(".")[0] in ("aisef", "aisef2")
                  and getattr(mod, "__file__", None) and not pathlib.Path(mod.__file__).resolve().is_relative_to(prefix))


def demo_problems(stdout: str) -> list[str]:
    """`aisef demo`'s printed rows against DEMO, and the escape's gap printed under the escape row."""
    rows = {m.group(1): m for m in ROW.finditer(stdout)}
    out = [] if sorted(rows) == sorted(DEMO) else [f"`aisef demo` printed rows {sorted(rows)}, not {sorted(DEMO)}"]
    for mode, want in DEMO.items():
        if mode not in rows:
            continue
        m = rows[mode]
        try:
            last = ast.literal_eval(m.group(3))["S1"][-1]
        except (ValueError, SyntaxError, KeyError, IndexError, TypeError):
            last = None
        if (m.group(2), last, m.group(4)) != want:
            out.append(f"`aisef demo` [{mode}]: delivery {m.group(2)}, last outcome {last}, verify {m.group(4)}; want {want}")
    if "escape" in rows and not stdout[rows["escape"].end():].startswith(GAP):
        out.append("`aisef demo` did not show the escape's gap under the escape row")
    return out


def _demo(aisef: pathlib.Path) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="aisef-installed-demo-") as t:
        r = subprocess.run([str(aisef), "demo"], capture_output=True, text=True, encoding="utf-8", cwd=t, timeout=900,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode != 0:
        return [f"`aisef demo` exited {r.returncode}: {(r.stderr or r.stdout)[-600:]}"]
    return demo_problems(r.stdout)


def problems(writer: pathlib.Path | None = None) -> list[str]:
    """writer: another installed `aisef` that writes the run (--check, run); the candidate verifies it."""
    import aisef2  # noqa: F401 — the installed artifact's, before the fixture puts the checkout on sys.path
    spec = importlib.util.spec_from_file_location("installed_product_fixture", HERE / "v2" / "test_app_run.py")
    fx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fx)
    out = [f"{m} was imported from outside the installed artifact" for m in _outside_the_artifact()]
    aisef = pathlib.Path(sys.executable).parent / ("aisef.exe" if os.name == "nt" else "aisef")
    writes = {"check": writer or aisef, "run": writer or aisef, "verify": aisef}
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        with tempfile.TemporaryDirectory(prefix="aisef-installed-product-") as t:
            t = pathlib.Path(t).resolve()
            baseline = fx.make_repo(t / "source")
            (t / "project.json").write_text(json.dumps(fx.project_bundle(baseline)), encoding="utf-8")
            settings = {**fx.SETTINGS, "provider": {**fx.SETTINGS["provider"], "endpoint": endpoint}}
            (t / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
            client = t / "client" / "opencode"
            client.parent.mkdir()
            client.write_text(f"#!{sys.executable}\nADD = {fx.ADD!r}\nTEST = {fx.TEST!r}\n" + fx.FAKE_CLIENT, encoding="utf-8")
            client.chmod(0o755)
            (client.parent / "mode").write_text("write", encoding="utf-8")
            env = {**os.environ, **fx.client_config(t, endpoint=endpoint), "AISEF_TEST_NO_KEY": "installed-smoke-not-a-key",
                   "PATH": f"{client.parent}{os.pathsep}{os.environ.get('PATH', '')}"}
            common = ["--project", str(t / "project.json")]
            steps = {"check": [*common, "--check", "--settings", str(t / "settings.json"), "--repo", str(t / "source")],
                     "run": [*common, "--settings", str(t / "settings.json"), "--repo", str(t / "source"), "--out", str(t / "out")],
                     "verify": [*common, "--verify", "--out", str(t / "out")]}
            for name, argv in steps.items():
                r = subprocess.run([str(writes[name]), "run", *argv], capture_output=True, text=True, encoding="utf-8", env=env,
                                   cwd=t, timeout=900)
                if r.returncode != 0:
                    out.append(f"`aisef run` ({name}) exited {r.returncode}: {(r.stderr or r.stdout)[-600:]}")
                    break
            else:
                rec = json.loads((t / "out" / "RUN.json").read_text(encoding="utf-8"))
                if (rec["delivery_verdict"], rec["story_outcomes"]) != ("PASS", {"S1": ["COMMIT"]}):
                    out.append(f"the installed run did not deliver: {rec['delivery_verdict']} {rec['story_outcomes']}")
                if writer is not None and rec.get("kernel_digest") != KERNEL_2_2_0:
                    out.append(f"the run {writer} wrote has kernel_digest {rec.get('kernel_digest')}, not 2.2.0's {KERNEL_2_2_0}")
    finally:
        server.shutdown()
        server.server_close()
    return out + (_demo(aisef) if writer is None else [])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--writer", type=pathlib.Path, help="the `aisef` that writes the run (the historical-2.2 read)")
    a = ap.parse_args()
    found = problems(a.writer)
    for p in found:
        print(f"FAIL  {p}")
    done = (f"a run written by {a.writer} (kernel 2.2.0) verifies with the installed artifact" if a.writer else
            "`aisef run` --check, run, --verify and `aisef demo`'s three rows from the installed artifact")
    print("installed product smoke: " + ("FAIL" if found else f"PASS ({done})"))
    sys.exit(1 if found else 0)
