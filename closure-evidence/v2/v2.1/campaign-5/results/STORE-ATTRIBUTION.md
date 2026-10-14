# The OpenCode store before and after campaign 5 (store-before.json, store-after.json)

Campaign 5 ran 2026-10-13T05:33:28Z to 2026-10-14T05:54:02Z on five workers under `env -i`, a PATH without the real
`opencode` and scratch HOME/XDG directories (see `owned/` and `launch.log`).

Between the two snapshots the user's store changed in three ways: `opencode.db` grew by 69,632 bytes and its mtime moved
to 2026-10-13T11:01:54.877Z, `opencode.db-wal` and `opencode.db-shm` are gone, and `log/` has a newer entry
(2026-10-13T11:01:54.758Z). Everything else (config, auth, snapshot, storage, tool-output) is byte-for-byte the same
inode/mtime/size/entry count.

What the evidence says about the cause:

* `~/.local/share/opencode/log/opencode.log`, last line, run `a7141900`:
  `timestamp=2026-10-13T11:01:54.744Z ... message="global event disconnected"`. The same run id writes the hourly
  `cleanup prune=7.days` and `booting location services` lines for the whole of the campaign (09:02, 10:02, 11:00 UTC),
  i.e. it is a long-lived OpenCode Desktop process that was already running when the campaign started.
* The db mtime (11:01:54.877Z) is 133 ms after that line, and the -wal/-shm pair disappears: the closing of the last
  connection checkpoints the WAL and removes the pair. That is what a normal exit of the process that held the db open
  does.
* No worker started an `opencode` process: no file in `owned/` (the ledger of every process a worker started and
  proved) names one, and the workers' PATH has no `opencode` on it (`py.sh`: directories holding an `opencode` are
  filtered out).

Attribution: the changes are the OpenCode Desktop process `a7141900` exiting at 2026-10-13T11:01:54Z. They are not an
effect of the campaign. What this does NOT show is who or what closed that process (the user quitting the app, a
crash, a restart); the log carries no reason and nothing else was looked for.
