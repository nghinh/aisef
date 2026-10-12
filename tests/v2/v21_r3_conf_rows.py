"""What the confinement tests share since B03-R3 (docs/v2.1/decisions/B03-R3-conf.md; owner, 2026-10-12): a writable
mount outside the workspace is accepted only when the report SHOWS it belongs to the sandbox — the file system, the
mount source, a super block the host's own mount table does not hold, no propagation with the host — so a
measurement these tests model as correctly confined has to carry what shows it. This module is not a test: it holds
the rows and the seam they use.

* `host_table()` — the host's mount table `confine.measure` reads (its own /proc/self/mountinfo) is the test's: a
  Linux CI host's real table would hold super blocks the transcripts' made-up numbers collide with, and a macOS or
  Windows host has none.
* `mount()` — a row as `confine._mounts` parses it from a mountinfo line, a sandbox-made one by default.
* `DEVICES_SEEN` — what the probe's `devices` section reads of the nodes `--dev` places.
"""

from __future__ import annotations

import zlib
from unittest import mock

from aisef2.app import confine

#: a host that holds one real file system (a block device) and none of the pseudo super blocks the transcripts' sandboxes
#: make; the sandbox's `/dev/null` and the others are bound from /dev, which a table that holds only this lacks
HOST = confine._mounts(["1 0 8:1 / / rw,relatime - ext4 /dev/vda1 rw"])
#: what the probe reads of each device node `--dev /dev` places in a correct sandbox (`stat -c %t:%T`)
DEVICES_SEEN = {f"/dev/{n}": number for n, number in confine.DEVICES.items()}


def host_table(table=None):
    """The patch under which `confine.measure` reads `table` as the host's mount table: a list of rows (HOST by
    default) or a callable answering each reading — the measurement reads it before the session and after it."""
    if callable(table):
        return mock.patch.object(confine, "_host_mounts", table)
    rows = list(HOST if table is None else table)
    return mock.patch.object(confine, "_host_mounts", lambda: list(rows))


def mount(at: str, fs: str = "tmpfs", access: str = "rw", dev: str | None = None, source: str | None = None,
          optional: str = "", root: str = "/") -> dict:
    """The row of a mount the sandbox made for itself — `fs` with its own name as the source, a super block of its own
    (a number that depends on the path only, never the host's 8:1), no propagation — as `confine._mounts` reads it
    from the line the kernel prints; a different `dev`, `source`, `optional` or `root` makes it something else."""
    dev = dev or f"0:{100 + zlib.crc32(at.encode()) % 800}"
    [row] = confine._mounts([f"1 0 {dev} {root} {at} {access},relatime {optional} - {fs} {source or fs} {access}"
                             .replace("  ", " ")])
    return row
