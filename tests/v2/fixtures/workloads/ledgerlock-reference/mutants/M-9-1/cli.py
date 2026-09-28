"""The LedgerLock CLI (§5, §6, §7, §9): argparse, exact exit codes.

    ledgerlock verify <ledger>                         0 intact, 5 corrupt
    ledgerlock snapshot <ledger> [--out <file>]        0; the snapshot bytes on stdout or in the file
    ledgerlock apply --batch <file> <ledger>           0; the batch file is a JSON list of {op, key, value, rid, ts}
    ledgerlock repair-tail <ledger>                    0 (no-op or repaired), 5 when corruption is not at the tail
    ledgerlock put <ledger> <key> <json-value> --rid <rid> --ts <int>
    ledgerlock delete <ledger> <key> --rid <rid> --ts <int>

Exit codes: 0 success, 2 usage error, 3 I/O error, 4 conflict, 5 corruption. A timestamp is always given by the
caller (§10 allows no clock module).
"""

from __future__ import annotations

import argparse
import json
import sys

from ledgerlock.ledger import ConflictError, CorruptionError, Ledger

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_IO = 3
EXIT_CONFLICT = 4
EXIT_CORRUPT = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledgerlock", description="append-only, tamper-evident key/value ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify").add_argument("ledger")
    snap = sub.add_parser("snapshot")
    snap.add_argument("ledger")
    snap.add_argument("--out")
    apply = sub.add_parser("apply")
    apply.add_argument("--batch", required=True)
    apply.add_argument("ledger")
    sub.add_parser("repair-tail").add_argument("ledger")
    put = sub.add_parser("put")
    put.add_argument("ledger")
    put.add_argument("key")
    put.add_argument("value", help="a JSON value")
    put.add_argument("--rid", required=True)
    put.add_argument("--ts", required=True, type=int)
    delete = sub.add_parser("delete")
    delete.add_argument("ledger")
    delete.add_argument("key")
    delete.add_argument("--rid", required=True)
    delete.add_argument("--ts", required=True, type=int)
    return parser


def _batch_ops(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    if not isinstance(spec, list):
        raise ValueError("a batch is a JSON list")
    ops = []
    for entry in spec:
        if not isinstance(entry, dict):
            raise ValueError("a batch entry is a JSON object")
        ops.append((entry.get("op"), entry.get("key"), entry.get("value"), entry.get("rid"), entry.get("ts")))
    return ops


def _result_json(result) -> str:
    return json.dumps(result._asdict(), ensure_ascii=False, sort_keys=True) + "\n"


def dispatch(args: argparse.Namespace) -> int:
    ledger = Ledger(args.ledger)
    if args.command == "verify":
        verdict = ledger.verify()
        sys.stdout.write(json.dumps(verdict._asdict(), sort_keys=True) + "\n")
        return EXIT_OK if verdict.ok else EXIT_CORRUPT
    if args.command == "snapshot":
        data = ledger.snapshot()
        if args.out:
            with open(args.out, "wb") as f:
                f.write(data)
        else:
            sys.stdout.buffer.write(data)
        return EXIT_OK
    if args.command == "apply":
        results = ledger.apply_batch(_batch_ops(args.batch))
        sys.stdout.write(json.dumps({"applied": len(results)}) + "\n")
        return EXIT_OK
    if args.command == "repair-tail":
        repaired = ledger.repair_tail()
        sys.stdout.write(json.dumps({"repaired": repaired}) + "\n")
        return EXIT_OK
    if args.command == "put":
        sys.stdout.write(_result_json(ledger.put(args.key, json.loads(args.value), args.rid, args.ts)))
        return EXIT_OK
    sys.stdout.write(_result_json(ledger.delete(args.key, args.rid, args.ts)))
    return EXIT_OK


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    try:
        return dispatch(args)
    except ConflictError as e:
        sys.stderr.write(f"conflict: {e}\n")
        return EXIT_CORRUPT
    except CorruptionError as e:
        sys.stderr.write(f"corruption: {e}\n")
        return EXIT_CORRUPT
    except OSError as e:
        sys.stderr.write(f"i/o error: {e}\n")
        return EXIT_IO
    except ValueError as e:
        sys.stderr.write(f"usage error: {e}\n")
        return EXIT_USAGE
