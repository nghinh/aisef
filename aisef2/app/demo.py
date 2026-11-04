"""`aisef demo`: the trust loop, offline and credential-free.

Runs the packaged one-story calc project (`aisef bundle init --example calc-1-story`)
three times against a fake developer and a loopback provider — nothing reaches a network
or a model, no credentials are read — to show the three outcomes the kernel distinguishes:

  correct  the developer writes `add` correctly      -> delivered, and the run verifies
  caught   the developer writes a wrong `add` (a-b)   -> refused; the repository is untouched
  escape   the developer writes `add` as `return 5`   -> delivered, and still wrong for 1+1

The escape is the honest boundary (ROADMAP-2.2 G5): AISEF proves every *stated* contract
holds; it does not prove the code is correct beyond them. A contract that pins only
`add(2, 3) == 5` is satisfied by code that returns 5 for everything. The demo delivers that
code and then evaluates `add(1, 1)` on it to show the gap the proof never promised to close.

The project, the seal→approve path, and `run.execute` / `verify` are the real product; only
the developer and the provider are doubles, because running with no network and no model is
the whole point. It is the same end-to-end path tests/v2/test_app_run.py exercises, shipped."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from unittest import mock

from aisef2.app import bundle, bundle_cli, settings
from aisef2.app import run as R
from aisef2.app.verify import verify
from aisef2.arch.enums import Owner

EXAMPLE = "calc-1-story"
ROUTE = "fakeprov/model-1"
APPROVER = "human:demo-owner"
APPROVED_AT = 1_700_000_000.0  # a fixed instant so the demo is byte-reproducible

#: the three bodies of `app/calc.py` the fake developer writes, by mode. `sub` is the baseline's
#: and is kept; only `add` (the story's subject) changes.
_SUB = "def sub(a, b):\n    return a - b\n"
BODIES = {
    "correct": _SUB + "\n\ndef add(a, b):\n    return a + b\n",
    "caught": _SUB + "\n\ndef add(a, b):\n    return a - b\n",   # an in-scope regression
    "escape": _SUB + "\n\ndef add(a, b):\n    return 5\n",        # passes add(2, 3) == 5, nothing else
}
#: the story's pinned test (tests/test_add.py) — the contract's own example, nothing more
TEST = ("import unittest\n\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(calc.add(2, 3), 5)\n")

#: the fake developer/reviewer: an `opencode run ... --title T --dir D` stand-in. It writes the
#: story's code from a `mode` file beside it (the same mechanism test_app_run uses), reports one
#: finished step the way the real client does, and reaches no network. The reviewer finds nothing.
FAKE_CLIENT = r'''import json, os, pathlib, sys
argv = sys.argv[1:]
if argv == ["--version"]:
    print("0.0.0-demo"); raise SystemExit(0)
title = argv[argv.index("--title") + 1]
cwd = pathlib.Path(argv[argv.index("--dir") + 1])
mode = pathlib.Path(__file__).with_name("mode").read_text()
if title.startswith("developer"):
    (cwd / "app" / "calc.py").write_text(BODIES[mode])
    (cwd / "tests").mkdir(exist_ok=True)
    (cwd / "tests" / "__init__.py").write_text("")
    (cwd / "tests" / "test_add.py").write_text(TEST)
text = '{"findings": []}' if title.startswith("reviewer") else "done"
print(json.dumps({"type": "text", "part": {"text": text}}))
print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 120, "output": 7, "reasoning": 3,
                                                             "cache": {"read": 10, "write": 0}}}}))
'''

SETTINGS = {
    "format": settings.FORMAT, "client": "opencode", "route": ROUTE,
    "provider": {"name": "fakeprov", "endpoint": "https://provider.invalid/v1", "api_key_env": "AISEF_DEMO_NO_KEY",
                 "served_model": "model-1", "listed_owner": "demo", "model_limit": {"context": 100000, "output": 8000}},
    "client_env": [], "budget": {"provider_requests": 20, "turns": 50, "input_tokens": 100000, "output_tokens": 10000},
    "max_turns_per_session": 10, "limits": {o.value: 1 for o in Owner},
    "timeouts_s": {"developer": 60, "reviewer": 60, "tool": 120, "probe": 60}, "preflight": {"chat_probes": 2}}


def _git(cwd: pathlib.Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "demo",
        "GIT_AUTHOR_EMAIL": "demo@demo", "GIT_COMMITTER_NAME": "demo", "GIT_COMMITTER_EMAIL": "demo@demo"}
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                          env=env).stdout


def loopback():
    """The provider the preflight's chat probes talk to: 200 for the model list and every chat, no network."""
    def transport(path, body=None):
        if body is None:
            return 200, {"data": [{"id": "model-1", "owned_by": "demo"}]}
        return 200, {"model": "model-1", "system_fingerprint": "fp-demo",
                     "usage": {"prompt_tokens": 9, "completion_tokens": 1}}
    return transport


def build(work: pathlib.Path):
    """Init the packaged example, make its repo a git repository, seal the authoring and approve every
    contract — the real `aisef bundle` path — and return (loaded project, source repo path)."""
    proj = work / "project"
    bundle_cli.init(EXAMPLE, proj)
    repo = proj / "repo"
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "baseline")
    authoring = json.loads((proj / "authoring.json").read_text(encoding="utf-8"))
    sealed, report = bundle_cli.seal(authoring, repo=repo)
    for row in report["to_approve"]:
        sealed = bundle_cli.approve(sealed, row["contract"], APPROVER, APPROVED_AT)
    return bundle.load(sealed), repo


def _run(project, source: pathlib.Path, client: pathlib.Path, out: pathlib.Path, mode: str) -> dict:
    (client.parent / "mode").write_text(mode)
    return R.execute(project, settings.load(SETTINGS), source, out, client_exe=str(client), transport=loopback())


def _escape_gap(out: pathlib.Path) -> str | None:
    """The delivered escape code evaluated on an input the contract never named. The delivered merge lives
    on `main` of <out>/repo; we exec exactly that, so the gap is shown, not asserted (our own fake code)."""
    try:
        src = _git(out / "repo", "show", "main:app/calc.py")
    except subprocess.CalledProcessError:
        return None
    ns: dict = {}
    exec(src, ns)        # noqa: S102 — the demo's own delivered code
    return f"add(1, 1) returns {ns['add'](1, 1)!r} on the delivered code (the sum is 2)"


SCENARIOS = [
    ("correct", "the developer writes add correctly"),
    ("caught", "the developer writes a wrong add (a - b)"),
    ("escape", "the developer writes add as `return 5`"),
]


def run_demo(work: pathlib.Path) -> list[dict]:
    """Build the project and run every scenario; one row per scenario with its real verdicts. No printing —
    main() prints these, a test asserts on them."""
    # the operator's own client configuration is never read: an isolated XDG whose only provider is the
    # loopback one, so the run's endpoint check matches the attested endpoint
    (work / "xdg" / "opencode").mkdir(parents=True)
    (work / "xdg" / "opencode" / "opencode.json").write_text(json.dumps(
        {"provider": {"fakeprov": {"options": {"baseURL": SETTINGS["provider"]["endpoint"],
                                               "apiKey": "{env:AISEF_DEMO_NO_KEY}"}}}}), encoding="utf-8")
    client = work / "client" / "opencode"
    client.parent.mkdir()
    client.write_text(f"#!{sys.executable}\nBODIES = {BODIES!r}\nTEST = {TEST!r}\n" + FAKE_CLIENT)
    client.chmod(0o755)
    rows = []
    with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(work / "xdg")}):
        project, source = build(work)
        rows.append({"project": project.name})
        for mode, told in SCENARIOS:
            rec = _run(project, source, client, work / mode, mode)
            row = {"mode": mode, "told": told, "delivery": rec["delivery_verdict"],
                   "stories": rec.get("story_outcomes"), "verify": verify(project, work / mode)["verdict"]}
            if mode == "escape" and row["delivery"] == "PASS":
                row["gap"] = _escape_gap(work / mode)
            rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="aisef demo",
                            description="Run the trust loop offline on the packaged example (no network, no "
                                        "credentials).").parse_args([] if argv is None else argv)
    with tempfile.TemporaryDirectory(prefix="aisef-demo-") as t:
        rows = run_demo(pathlib.Path(t))
    print(f"project: {rows[0]['project']} — one story (S1), one contract (BC-ADD: add(2, 3) == 5)\n")
    for row in rows[1:]:
        print(f"[{row['mode']}] {row['told']}")
        print(f"    delivery {row['delivery']}   stories {row['stories']}   verify {row['verify']}")
        if row.get("gap"):
            print(f"    but: {row['gap']}")
        print()
    print("The kernel delivered `correct`, refused `caught`, and delivered `escape` — because `escape`\n"
          "satisfies every stated contract. AISEF proves the contracts you write hold; it does not\n"
          "prove the code is right where no contract looks. Write the contract that would have caught it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
