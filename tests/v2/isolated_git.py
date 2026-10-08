"""git for tests that must never reach the caller's repository or run a program the repository holds: no GIT_* variable
of the caller (a hook's GIT_DIR / GIT_INDEX_FILE would take it to the caller's repository), no system or global
configuration, and the runner's own isolation, aisef2.orchestrate.workspace._ISOLATED_GIT (hook path the null device,
fsmonitor off, no signing, no maintenance). It lives here, not in tests/v2/test_app_run.git: that helper is in the import
closure of the kill tests of 406 of campaign 2's 466 mutation targets, and a change to it after the campaign's snapshot
would make every one of them be measured again (closure-evidence/v2/v2.1/campaign-2/delta/)."""

from __future__ import annotations

import os
import subprocess

from aisef2.orchestrate import workspace


def git(cwd, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | workspace._ISOLATED_GIT | {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", env=env,
                          check=True).stdout.strip()
