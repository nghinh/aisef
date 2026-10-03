"""The AISEF 2.0 product runtime — what `aisef run` executes (V2.0 release charter §7 B12, §9).

The kernel (`aisef2` outside this package) decides; this package wires it to a project and to the outside world:

* `bundle`   — the project bundle: requirements, approved contracts, the plan and the public facts of its obligations,
               loaded into the kernel's sealed objects (every hash re-checked on load), the specs compiled under this
               release's probe catalog;
* `settings` — the run settings: the fixed model route, the client, the budget, the retry limits — every one explicit,
               no default (a run without one is refused);
* `preflight`— the provider preflight that attests the fixed route before any session (identity stop otherwise);
* `client`   — the one OpenCode session runner (the fixed route, a built environment, the budget, a turn cap);
* `adapters` — the developer, the reviewer and the scanner the kernel's story runner calls;
* `feedback` — the developer's task and its retry feedback, from public facts and the journal only;
* `run`      — the run driver: a run directory that nothing removes — the raw chained journal, the repository with
               every revision, the session streams, the record — written even when the run breaks;
* `verify`   — the journal's hash chain and the record re-checked from the run directory alone;
* `cli`      — `aisef run`.

Nothing here decides a verdict, an owner, a retry or a budget charge: the kernel does, from its journal.
"""
