"""``closure`` command — score the project closure gate, read-only.

Evaluates `docs/closure-gate.json` against the repository and writes the
machine report. It never runs an agent, never runs a paid workload, never
touches a corpus, and never signs anything on the owner's behalf: `--approve`
is a separate, explicit act (contract §0).
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..control import closure as C

#: Closure's own exit codes, stated by the contract §4.3: ``0`` closable,
#: ``1`` blocked, ``2`` usage error. This is the **reverse** of the rest of
#: this CLI (``1`` usage, ``2`` not-ready), so the subparser's `error` is
#: redirected too (`parser._closure_error`) — otherwise a mistyped flag would
#: exit 1 and read as "blocked".
EXIT_CLOSABLE = 0
EXIT_BLOCKED = 1
EXIT_USAGE = 2


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def cmd_closure(args) -> int:
    root = Path(args.project)
    if args.report and (args.pin or args.waive or args.approve):
        print("✗ --report renders the last evaluation; run it on its own", file=sys.stderr)
        return EXIT_USAGE
    if args.reason and not args.waive:
        print("✗ --reason is the reason for a waiver — pass --waive <criterion> too",
              file=sys.stderr)
        return EXIT_USAGE

    if args.report:
        try:
            data = C.read_report(root)
        except (OSError, ValueError) as e:
            print(f"✗ no evaluation to render ({e}) — run `aisef closure` first", file=sys.stderr)
            return EXIT_USAGE
        path = C.write_markdown(root, data)
        print(f"✅ {_rel(root, path)} — {'CLOSABLE' if data.get('closable') else 'BLOCKED'}"
              f", evaluated {data.get('at')}")
        return EXIT_CLOSABLE if data.get("closable") else EXIT_BLOCKED

    try:
        spec = C.load_spec(root)
    except (OSError, ValueError) as e:
        print(f"✗ cannot read {C.CRITERIA_PATH}: {e}\n"
              "  `aisef closure` scores the AISEF framework repository — run it from that checkout.",
              file=sys.stderr)
        return EXIT_USAGE

    if args.pin:
        try:
            pinned = C.pin(root, force=args.force)
        except ValueError as e:
            print(f"✗ {e}", file=sys.stderr)
            return EXIT_USAGE
        for what, digest in pinned.items():
            print(f"✅ pinned {what} at {digest[:12]}")
        print(f"   commit {C.CRITERIA_PATH} — the pin is the record")
        spec = C.load_spec(root)

    if args.waive:
        try:
            rec = C.sign_waiver(root, args.waive, args.reason)
        except ValueError as e:
            print(f"✗ {e}", file=sys.stderr)
            return EXIT_USAGE
        print(f"◇ {args.waive} waived by {rec['by']} at {rec['at']}: {rec['reason']}")

    if args.approve:
        try:
            rec = C.sign_approval(root, note=args.note)
        except ValueError as e:
            print(f"✗ cannot approve — {e}", file=sys.stderr)
            return EXIT_BLOCKED
        print(f"✅ closure approved by {rec['by']} at {rec['at']} — "
              f"{len(rec['digests'])} evidence digests signed"
              + (f", waived: {', '.join(rec['waived'])}" if rec["waived"] else ""))

    report = C.evaluate(root, corpus=args.corpus, spec=spec)
    path = C.write_report(root, report)
    print(C.table(report))
    print(f"\nreport: {_rel(root, path)} · human form: `aisef closure --report`")
    return EXIT_CLOSABLE if report.closable else EXIT_BLOCKED
