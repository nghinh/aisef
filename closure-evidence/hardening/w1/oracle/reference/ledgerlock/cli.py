"""§9: `python -m ledgerlock {verify|snapshot|apply|repair-tail}` with the exact exit codes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ledger import ConflictError, CorruptionError, Ledger

EXIT_OK, EXIT_USAGE, EXIT_IO, EXIT_CONFLICT, EXIT_CORRUPT = 0, 2, 3, 4, 5  # §9


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ledgerlock")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify").add_argument("ledger")
    s = sub.add_parser("snapshot")
    s.add_argument("ledger")
    s.add_argument("--out")  # §6; without it the document goes to stdout (§14.2's bare form — choice)
    a = sub.add_parser("apply")
    a.add_argument("--batch", required=True)
    a.add_argument("ledger")
    sub.add_parser("repair-tail").add_argument("ledger")
    return p


def _read_batch(path: str) -> list[tuple]:
    """choice: the batch spec (§5 names the file only) is a JSON array of {op, key, value, rid|id, ts} objects."""
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(spec, list):
        raise ValueError("batch spec must be a JSON array")
    ops = []
    for e in spec:
        if not isinstance(e, dict) or "op" not in e or "key" not in e:
            raise ValueError("each batch entry needs op and key")
        ops.append((e["op"], e["key"], e.get("value"), e.get("rid", e.get("id")), e.get("ts", 0)))
    return ops


def main(argv=None) -> int:
    try:
        a = _parser().parse_args(argv)
    except SystemExit as e:  # argparse: usage error → 2, --help → 0
        return EXIT_USAGE if e.code else EXIT_OK
    led = Ledger(a.ledger)
    try:
        if a.cmd == "verify":
            v = led.verify()
            print(json.dumps(v))
            return EXIT_OK if v["ok"] else EXIT_CORRUPT
        if a.cmd == "snapshot":
            doc = led.snapshot()
            if a.out:
                Path(a.out).write_bytes(doc)
            else:
                sys.stdout.buffer.write(doc)
                sys.stdout.flush()
            return EXIT_OK
        if a.cmd == "apply":
            led.apply_batch(_read_batch(a.batch))
            return EXIT_OK
        led.repair_tail()
        return EXIT_OK
    except ConflictError as e:
        print(f"conflict: {e}", file=sys.stderr)
        return EXIT_CONFLICT
    except CorruptionError as e:
        print(f"corruption: {e}", file=sys.stderr)
        return EXIT_CORRUPT
    except (ValueError, TypeError) as e:
        print(f"usage: {e}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as e:
        print(f"io: {e}", file=sys.stderr)
        return EXIT_IO
