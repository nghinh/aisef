"""`python -m ledgerlock` (§9): the CLI's exit code is the process's."""

from __future__ import annotations

import sys

from ledgerlock.cli import main

sys.exit(main())
