"""WP-2.5.1 (C2-P5) — the contract authoring aid: LedgerLock PLAN-V2.1's 77 criteria re-expressed as Cycle-2 contracts,
compiled and statically admitted as the LedgerLock PLAN-V2.2 PROPOSAL.

    python -P validation/qualification/p10_contracts.py --write    # writes the record and the proposal document
    python -P validation/qualification/p10_contracts.py --check    # both committed files are what this module derives

**A proposal, never a plan in force.** Owner DECISION-3 (APPROVED_FOR_PROPOSAL_ONLY): nothing here approves a contract,
and nothing runs LedgerLock. The P10 record (PLAN-V2.1, NOT_REACHED) is read, never edited or re-interpreted
(`p10.V2` is its table; `p10.v1_rows()` the 77 criteria as V1 froze them).

**The approvals used to compile are not approvals.** `compile_spec` and the StaticPlanAdmissionEngine accept only a
contract a human approval binds (RFC §6). To measure whether the proposal *would* compile and admit, every contract is
bound here, in memory, by an approval of the declared check identity `CHECK_APPROVER` — the precedent is WP-2.3.2's
fixture approver (`human:c2-p3-calibration-fixture`). No such approval is written to any record: the record's
`approvals.given` is empty, and the admission is reported twice — with the check approvals (would the proposal admit
once the owner approves exactly these contract hashes?) and with none (what the kernel says of the proposal today:
not admitted, checks 2 and 7).

**DECISION-1.** Every criterion carries a declared quantifier semantics, one of `QUANTIFIERS`. The aid refuses
(typed) a criterion with none; refuses a criterion of DECISION-1's list declared `exhaustive_finite_domain`; and
refuses `bounded_witness_measurement` or `unsupported_for_full_enforcement` on a probe whose enforcement is FULL (a
witness is never recorded as a proof of the universal property). `exhaustive_finite_domain` is declared only where the
criterion names every input it quantifies over; a "Given a JSONL …", "any", "every" or "N" is a bounded witness.

**DECISION-2.** A fault is a step of process_effect's closed vocabulary naming an id of its `FAULTS` table.

**DECISION-3.** The six test-named criteria are carried as before/after pairs: *before* is P10's contract (refused by the
kernel's contract rule, as in P10), *after* is a product contract or a typed removal from ProductProof.

**DECISION-4.** The only equality class in the integrated catalog that runs two independent observations in two fresh
evaluation directories is `cli_invocation`'s `equality`. The seven DECISION-4 criteria have library subjects
(`canonical_bytes`, `line_hash`, `snapshot`), for which no such class exists (python_callable_v2 has none;
process_effect's `returns_name`/`equals_name` compares two calls inside one process, sharing module state, which
DECISION-4 forbids). Each is restated as one observation against one constant derived from the requirements, or
refused where no stimulus can carry the witness — every such case is an open decision for the owner.

**One observable per contract.** Each probe class observes one thing; a criterion with several clauses is measured on
the clause named in `measured`, and every clause left out is listed in `unmeasured` — never silently dropped.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import importlib
import json
import pathlib
import subprocess
import sys
import unicodedata

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import p10 as P10  # noqa: E402

OUT_REL = "closure-evidence/v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json"
DOC_REL = "docs/implementation/v2/cycle2/LEDGERLOCK-PLAN-V2.2-PROPOSAL.md"
DECISIONS_REL = "closure-evidence/v2/cycle2/OWNER-DECISIONS.json"
PLAN_ID = "LEDGERLOCK-PLAN-V2.2-PROPOSAL"
PACKAGE = "WP-2.5.1"
CHECK_APPROVER = "human:c2-p5-proposal-check"
QUANTIFIERS = ("exhaustive_finite_domain", "bounded_witness_measurement", "unsupported_for_full_enforcement")
WINDOW = 30
CALIBRATION_RECORDS = ("closure-evidence/v2/cycle2/P1-FILE-ARTIFACT-CALIBRATION.json",
                       "closure-evidence/v2/cycle2/P2-CLI-CALIBRATION.json",
                       "closure-evidence/v2/cycle2/P3-EFFECT-CALIBRATION.json",
                       "closure-evidence/v2/cycle2/P4-PYTHON-CALLABLE-V2-CALIBRATION.json")

# --------------------------------------------------------------------------------------- expected values (§3.2)

L = "<ws>/l.jsonl"
LEDGER = "ledgerlock.ledger:Ledger"
MAIN = "ledgerlock:__main__"
NFC_E, NFD_E = "é", "é"
#: DECISION-1 witness for "any string s": NFD sequences of three scripts, a combining ring, ASCII and a space in one string
ANY_S = "éÅ가 x"


def canon(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def put(key, value, rid, ts) -> dict:
    return {"op": "put", "key": key, "value": value, "ts": ts, "id": rid}


def dele(key, rid, ts) -> dict:
    return {"op": "delete", "key": key, "ts": ts, "id": rid}


def chain(*records: dict) -> list[dict]:
    """The committed lines of `records` in order: each with its prev_hash and its hash (requirements §3.2)."""
    prev, out = "GENESIS", []
    for r in records:
        line = {**r, "prev_hash": prev, "hash": P10.line_hash_expected(prev, r)}
        out.append(line)
        prev = line["hash"]
    return out


def jsonl(lines: list[dict]) -> bytes:
    """One committed line per row, canonical and newline-terminated: bytes any implementation of §3.2 must accept."""
    return b"".join(canon(line) + b"\n" for line in lines)


def tup(record: dict) -> list:
    """A mutation as PLAN-V2.1 writes it: (op, key, value, rid, ts), or (op, key, rid, ts) for a delete (a JSON list)."""
    if record["op"] == "delete":
        return ["delete", record["key"], record["id"], record["ts"]]
    return ["put", record["key"], record["value"], record["id"], record["ts"]]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_bytes(state: dict) -> bytes:
    """PLAN-V2.1 AC-STORY-04-01-5: json.dumps(snapshot, sort_keys, compact, ensure_ascii=False) + newline."""
    return canon(state) + b"\n"


LINE = P10.LINE
H_A, H_B, H_G = P10.H_A, P10.H_B, P10.H_G
LINE_SET = P10.LINE_SET
C1 = chain(put("k", "v1", "r1", 100))                                                   # one committed put
C_DEL = chain(dele("k", "r1", 100))                                                     # one committed delete
C_NFC = chain(put(NFC_E, "v1", "r1", 100))
C3 = chain(put("a", 1, "r1", 1), put("b", 2, "r2", 2), put("c", 3, "r3", 3))
C_KV = chain(put("k", {"v": 1}, "r1", 100))
TRUNC = b'{"op":"put","key":"d"'                                                        # an unterminated line that does not parse
C20 = chain(*(put(f"k{i:02d}", i, f"r{i:02d}", 100 + i) for i in range(20)))
C20_TAMPERED = [dict(line, value=999) if i == 17 else line for i, line in enumerate(C20)]
BATCH3 = [put("a", 1, "r1", 1), put("b", 2, "r2", 2), put("c", 3, "r3", 3)]
#: DECISION-3 witness sequence for AC-STORY-05-01-1: conflict-free puts, deletes and replays over four keys, fixed at
#: authoring time (nothing is random at evaluation)
SEQ = [put("a", 1, "s1", 1), put("b", 2, "s2", 2), put("a", 1, "s1", 3), dele("b", "s2", 4), put("c", [1, 2], "s3", 5),
       put(NFD_E, "x", "s4", 6), put(NFC_E, "y", "s4", 7), dele("d", "s5", 8), put("b", 2, "s2", 9)]


def ws(**files: bytes) -> dict:
    return {"step": "workspace", "files": {name: {"bytes_hex": data.hex()} for name, data in files.items()}}


NEW = {"step": "construct", "args": [L], "kwargs": {}}


def call(method: str, *args, as_: str | None = None) -> dict:
    return {"step": "call", "method": method, "args": list(args), "kwargs": {}, **({"as": as_} if as_ else {})}


def raises(method: str, exception: str, *args, attrs: dict | None = None) -> dict:
    return {"step": "expect_raises", "method": method, "args": list(args), "kwargs": {}, "exception": exception,
            **({"attrs": attrs} if attrs is not None else {})}


def edit(line: int, field: str, value) -> dict:
    return {"step": "edit_jsonl", "path": L, "line": line, "field": field, "value": value}


def fault(name: str) -> dict:
    return {"step": "fault", "fault": name}


# --------------------------------------------------------------------------------------- entry builders

def _meta(q, measured, unmeasured=(), decisions=(), witness=None, note=""):
    return {"quantifier": q, "measured": measured, "unmeasured": list(unmeasured), "decisions": list(decisions),
            "witness": witness, "note": note}


def pc2(locator, observable, *, args=None, workspace=None, no_stimulus=False, **meta):
    stim = {} if no_stimulus else {"args": list(args or []), **({"workspace": workspace} if workspace else {})}
    return {"kind": "python_callable", "locator": locator, "stimulus": stim,
            "observable": {**observable, "within_s": WINDOW}, "absence": "REQUIRES_SUBJECT", **_meta(**meta)}


def eff(steps, observable, *, locator=LEDGER, **meta):
    return {"kind": "process_effect", "locator": locator, "stimulus": {"scenario": steps},
            "observable": {**observable, "within_s": WINDOW}, "absence": "REQUIRES_SUBJECT", **_meta(**meta)}


def cli(argv, observable, *, workspace=None, pre=None, **meta):
    stim = {"argv": list(argv), **({"workspace": workspace} if workspace else {}),
            **({"pre": [{"argv": list(p)} for p in pre]} if pre else {})}
    return {"kind": "cli_invocation", "locator": MAIN, "stimulus": stim,
            "observable": {**observable, "within_s": WINDOW}, "absence": "REQUIRES_SUBJECT", **_meta(**meta)}


def tree(pattern, **meta):
    return {"kind": "file_artifact", "locator": "path:ledgerlock", "stimulus": {"grep": pattern},
            "observable": {"matches": 0, "within_s": WINDOW}, "absence": "ABSENCE_IS_DECIDABLE", **_meta(**meta)}


def refused(code, reason, **meta):
    return {"refusal": code, "reason": reason, **_meta(**meta)}


def files_ws(**files: bytes) -> dict:
    """cli_invocation workspace: flat names, byte-exact."""
    return {name: {"bytes_hex": data.hex()} for name, data in files.items()}


EX, BW, UF = QUANTIFIERS
NET = r"^(import|from) (socket|subprocess|requests|http|urllib|asyncio|ssl|multiprocessing|ctypes|http\.server|http\.client|socketserver)"
SIDE = r"os\.system|subprocess\.|socket\."
ONE_LINE = r"(?=[ \t\n]|\Z)[^\n]*\n?\Z"          # the rest of exactly one line, after the first word
ALL = "the one declared stimulus is the whole domain the criterion names"
TREE = "every file of the package tree at the revision is scanned: the domain is finite and read entirely"
BYTES_ARGS = ("the call takes bytes arguments (a list of lines as bytes); a contract's stimulus is JSON-shaped data and "
              "no probe stimulus converts a value to bytes (workspace files are the only byte-exact input)")
D4_NOTE = ("DECISION-4: no class of the integrated catalog runs two independent observations of a library subject in "
           "two fresh evaluation directories; restated as one observation against a constant derived from the "
           "requirements — equivalent under the conjunction with {sib} in the same story, stronger than this criterion "
           "alone (open decision OD-D4)")
RETURN_SHAPE = "the returned value's shape ('the line dict … with replayed/committed') is not fixed by the plan (OD-RETURN)"

# --------------------------------------------------------------------------------------- the 77 criteria

V22: dict[str, dict] = {
    # ---- STORY-01-01
    "AC-STORY-01-01-1": pc2("ledgerlock.format:normalize_key", {"returns": unicodedata.normalize("NFC", ANY_S)},
                            args=[ANY_S], q=BW, measured="normalize_key(w) == NFC(w) for the witness w",
                            decisions=["DECISION-1"],
                            witness="one string holding NFD Latin (e + U+0301, A + U+030A), a decomposed Hangul syllable "
                                    "(U+1100 U+1161), a space and ASCII; never a proof for every string"),
    "AC-STORY-01-01-2": pc2("ledgerlock.format:normalize_key", {"returns": NFC_E}, args=[NFD_E], q=EX,
                            measured="normalize_key(NFD 'e\\u0301') == '\\u00e9'",
                            unmeasured=["normalize_key('\\u00e9') == '\\u00e9' (the identity half; AC-STORY-01-01-1's class)"],
                            witness="the NFD spelling, the half that discriminates"),
    "AC-STORY-01-01-3": pc2("ledgerlock:__file__", {"condition": "exists"}, no_stimulus=True, q=EX,
                            measured="the package imports from the revision and has __file__",
                            unmeasured=["the printed path ends in ledgerlock/__init__.py"]),
    "AC-STORY-01-01-4": tree(NET, q=EX, measured="zero lines of the package tree match the pattern", witness=TREE),
    "AC-STORY-01-01-5": tree(SIDE, q=EX, measured="zero lines of the package tree match the pattern", witness=TREE),
    "AC-STORY-01-01-6": pc2("ledgerlock:Ledger", {"condition": "exists"}, no_stimulus=True, q=EX,
                            measured="ledgerlock.Ledger resolves",
                            unmeasured=["ledgerlock.ConflictError resolves", "Ledger is a callable class"],
                            note="one contract names one subject (OD-01-01-6: split into two contracts?)"),
    "AC-STORY-01-01-7": cli(["verify", L, "extra"], {"exit_code": 2, "stdout": ""}, q=EX,
                            measured="exit 2 and empty stdout"),
    # ---- STORY-01-02 (canonical_bytes; a dict whose hash fields are unset: the plan's json.dumps form exactly)
    "AC-STORY-01-02-1": pc2("ledgerlock.format:canonical_bytes", {"returns_bytes_hex": canon(put("k", 1, "r", 1)).hex()},
                            args=[put("k", 1, "r", 1)], q=BW, measured="the bytes equal the plan's json.dumps form",
                            witness="one dict {op, key, value, ts, id}"),
    "AC-STORY-01-02-2": pc2("ledgerlock.format:canonical_bytes", {"returns_bytes_hex": canon(put("k", 1, "r", 1)).hex()},
                            args=[dict(reversed(list(put("k", 1, "r", 1).items())))], q=BW, decisions=["DECISION-4"],
                            measured="an element-equal dict gives AC-STORY-01-02-1's bytes",
                            witness="the element-equal copy (the contract layer sorts mapping keys, so the copy reaches the "
                                    "subject in the same key order)", note=D4_NOTE.format(sib="AC-STORY-01-02-1")),
    "AC-STORY-01-02-3": pc2("ledgerlock.format:canonical_bytes", {"returns_bytes_hex": canon({"k": NFC_E}).hex()},
                            args=[{"k": NFC_E}], q=BW, measured="U+00E9 is encoded as the UTF-8 bytes c3 a9",
                            unmeasured=["byte-stable across two invocations (DECISION-4's class; each evaluation is "
                                        "compared with the same constant)"], witness="{'k': '\\u00e9'}"),
    "AC-STORY-01-02-4": refused("UNSUPPORTED_STIMULUS",
                                "the witness is two dicts differing only in key insertion order; the contract layer "
                                "canonicalises every mapping of a stimulus (aisef2.product.contract.freeze sorts keys), so "
                                "no contract can deliver a dict in a non-sorted insertion order to the subject",
                                q=BW, measured="nothing", decisions=["DECISION-4"],
                                note="open decision OD-D4: a stimulus-level insertion order is a kernel question (compiler "
                                     "contract, F4): STOP-class if ever required"),
    "AC-STORY-01-02-5": pc2("ledgerlock.format:GENESIS", {"equals": "GENESIS"}, no_stimulus=True, q=EX,
                            measured="GENESIS == 'GENESIS'"),
    "AC-STORY-01-02-6": pc2("ledgerlock.format:canonical_bytes", {"returns_bytes_hex": canon({"op": "put", "v": [1, "x"]}).hex()},
                            args=[{"op": "put", "v": [1, "x"]}], q=BW, decisions=["DECISION-4"],
                            measured="a JSON round-tripped dict gives the canonical bytes",
                            witness="every stimulus is JSON data, so the dict the subject receives is round-tripped",
                            note=D4_NOTE.format(sib="AC-STORY-01-02-1")),
    # ---- STORY-01-03 (line_hash)
    "AC-STORY-01-03-1": pc2("ledgerlock.format:line_hash", {"returns": H_A}, args=["a" * 64, LINE], q=BW,
                            measured="line_hash('a'*64, line) is §3.2's digest (64 lowercase hex)",
                            note="stronger than the criterion (the value, not only its form, fixed by §3.2); P10's restatement kept"),
    "AC-STORY-01-03-2": pc2("ledgerlock.format:line_hash", {"returns": H_B}, args=["b" * 64, LINE], q=BW,
                            decisions=["DECISION-4"], measured="a second prev_hash gives §3.2's second digest (!= H_A)",
                            note=D4_NOTE.format(sib="AC-STORY-01-03-1")),
    "AC-STORY-01-03-3": pc2("ledgerlock.format:line_hash", {"returns": H_A}, args=["a" * 64, LINE_SET], q=BW,
                            measured="hash fields already set are ignored (the digest of the emptied line)"),
    "AC-STORY-01-03-4": pc2("ledgerlock.format:line_hash", {"returns": H_A}, args=["a" * 64, LINE], q=BW,
                            decisions=["DECISION-4"], measured="the same pair gives the same digest (the constant)",
                            note=D4_NOTE.format(sib="AC-STORY-01-03-1")),
    "AC-STORY-01-03-5": pc2("ledgerlock.format:line_hash", {"returns": H_G}, args=["GENESIS", LINE], q=BW,
                            measured="prev_hash 'GENESIS' is accepted: the call returns §3.2's digest",
                            note="stronger than the criterion (the value fixed by §3.2)"),
    # ---- STORY-01-04 (ledgerlock.store)
    "AC-STORY-01-04-1": refused("UNSUPPORTED_OBSERVABLE",
                                "read_lines returns a list of bytes: python_callable_v2 compares one bytes value "
                                "(returns_bytes) and process_effect one bytes value (returns_bytes_hex); a list of bytes "
                                "is unserializable to both, so no class can compare it", q=BW, measured="nothing",
                                witness="N = 2 would be the witness"),
    "AC-STORY-01-04-2": pc2("ledgerlock.store:read_lines", {"raises": "FileNotFoundError"}, args=["<ws>/missing.jsonl"],
                            q=EX, measured="FileNotFoundError"),
    "AC-STORY-01-04-3": pc2("ledgerlock.store:read_lines", {"returns": []}, args=["<ws>/empty.jsonl"],
                            workspace={"empty.jsonl": {"bytes_hex": ""}}, q=EX, measured="[] for a zero-byte file"),
    "AC-STORY-01-04-4": refused("UNSUPPORTED_STIMULUS", BYTES_ARGS, q=EX, measured="nothing"),
    "AC-STORY-01-04-5": refused("UNSUPPORTED_STIMULUS", BYTES_ARGS, q=BW, measured="nothing", decisions=["DECISION-2"],
                                note="the fault step exists (process_effect FAULTS 'os.replace'); the stimulus it would "
                                     "apply to does not"),
    "AC-STORY-01-04-6": refused("UNSUPPORTED_OBSERVABLE",
                                "where the subject creates a temporary file under a name it chooses is observed by no "
                                "class (file shapes name files; no step traces the subject's own file creation)",
                                q=UF, measured="nothing", note="and the stimulus needs bytes arguments, as 01-04-4"),
    # ---- STORY-01-05 (Ledger.append)
    "AC-STORY-01-05-1": eff([NEW, call("append", tup(C_KV[0]))],
                            {"files": {L: {"jsonl": {"line": 0, "field": "hash", "equals": C_KV[0]["hash"]}}}}, q=EX,
                            measured="line 0's hash is line_hash('GENESIS', the put) — op, key, value, ts, id pinned by it",
                            unmeasured=["exactly one line", "the terminating newline", "the stored prev_hash field"]),
    "AC-STORY-01-05-2": eff([NEW, call("append", tup(C3[0])), call("append", tup(C3[1]))],
                            {"files": {L: {"jsonl": {"line": 1, "field": "hash", "equals": C3[1]["hash"]}}}}, q=EX,
                            measured="line 1's hash is line_hash(line 0's hash, line 1)",
                            unmeasured=["the stored prev_hash field of line 1"]),
    "AC-STORY-01-05-3": eff([NEW, raises("append", "ValueError", ["put", "", "v", "r", 1])], {"files": {L: {"absent": True}}},
                            q=EX, measured="ValueError is raised (a step) and no file exists afterwards"),
    "AC-STORY-01-05-4": eff([ws(**{"l.jsonl": jsonl(C3[:1])}), NEW, call("append", tup(C3[1]))],
                            {"files": {L: {"jsonl": {"line": 1, "field": "hash", "equals": C3[1]["hash"]}}}}, q=BW,
                            measured="a fresh instance over an existing file chains its first append from the file's tail",
                            witness="an existing one-line chain written byte-exactly by the harness (what any §3.2 writer "
                                    "produces for that line)"),
    "AC-STORY-01-05-5": eff([NEW, call("append", tup(C_KV[0]))], {"files": {L: {"final_byte": "\n"}}}, q=EX,
                            measured="after append returned, the file read through a new descriptor ends in a newline",
                            unmeasured=["the reader is a separate process (the harness reads it; the subprocess step runs "
                                        "the revision's own modules, and at STORY-01-05 no CLI exists yet)"]),
    # ---- STORY-01-06 (idempotency, conflicts, tombstones)
    "AC-STORY-01-06-1": eff([ws(**{"l.jsonl": jsonl(C1)}), NEW, call("append", ["put", "k", "anything", "r1", 999])],
                            {"files": {L: {"line_count": 1}}}, q=EX,
                            measured="the replay returns (does not raise) and the chain length is unchanged",
                            unmeasured=[RETURN_SHAPE]),
    "AC-STORY-01-06-2": eff([ws(**{"l.jsonl": jsonl(C1)}), NEW,
                             raises("append", "ConflictError", ["put", "k", "v2", "r2", 200],
                                    attrs={"key": "k", "incoming_rid": "r2", "committed_rid": "r1", "batch_index": None})],
                            {"files": {L: {"equals_before": True}}}, q=EX,
                            measured="ConflictError with its four attributes (a step) and the file byte-identical"),
    "AC-STORY-01-06-3": eff([ws(**{"l.jsonl": jsonl(C_DEL)}), NEW, raises("append", "ConflictError", ["put", "k", "v", "r2", 200])],
                            {"raises": True}, q=EX, measured="ConflictError"),
    "AC-STORY-01-06-4": eff([ws(**{"l.jsonl": jsonl(C_DEL)}), NEW, call("append", ["put", "k", "v", "r1", 200])],
                            {"files": {L: {"line_count": 1}}}, q=EX,
                            measured="the replay returns (does not raise) and appends nothing", unmeasured=[RETURN_SHAPE]),
    "AC-STORY-01-06-5": eff([ws(**{"l.jsonl": jsonl(C_NFC)}), NEW, call("append", ["put", NFD_E, "v2", "r1", 200])],
                            {"files": {L: {"line_count": 1}}}, q=EX,
                            measured="the NFD replay returns and the chain length is unchanged",
                            unmeasured=["the returned key is '\\u00e9' byte-exact (" + RETURN_SHAPE + ")"]),
    # ---- STORY-02-01 (verify)
    "AC-STORY-02-01-1": eff([NEW, *(call("append", tup(r)) for r in C3), call("verify")],
                            {"returns": {"ok": True, "first_bad_index": None}}, q=BW,
                            measured="verify() returns {ok: true, first_bad_index: null}", witness="N = 3 lines"),
    "AC-STORY-02-01-2": eff([ws(**{"l.jsonl": b""}), NEW, call("verify")], {"returns": {"ok": True, "first_bad_index": None}},
                            q=EX, measured="verify() of a zero-byte file returns ok"),
    "AC-STORY-02-01-3": eff([NEW, raises("verify", "FileNotFoundError")], {"raises": True}, q=EX,
                            measured="FileNotFoundError"),
    "AC-STORY-02-01-4": eff([ws(**{"l.jsonl": jsonl(C3)}), edit(1, "hash", "0" * 64), NEW, call("verify")],
                            {"returns": {"ok": False, "first_bad_index": 1}}, q=BW,
                            measured="the first bad index is the overwritten line (i = 1)",
                            witness="a three-line chain, line 1's hash overwritten after it was written",
                            note="OD-02-01-4: the criterion allows i or an earlier index; §3.3 says the first violation, "
                                 "which is i itself (every line before i still verifies)"),
    "AC-STORY-02-01-5": eff([ws(**{"l.jsonl": jsonl(C3)}), edit(1, "value", 20), NEW, call("verify")],
                            {"returns": {"ok": False, "first_bad_index": 1}}, q=BW,
                            measured="the first bad index is the mutated line (i = 1)",
                            witness="a three-line chain, line 1's value mutated after it was written"),
    # ---- STORY-02-02 (snapshot)
    "AC-STORY-02-02-1": eff([NEW, call("append", tup(put("a", 1, "r1", 1))), call("append", tup(put("c", 3, "r3", 3))),
                             call("append", tup(put("b", 2, "r2", 2))), call("snapshot", as_="first"),
                             call("snapshot", as_="second")],
                            {"returns": {"a": 1, "b": 2, "c": 3}}, q=BW, decisions=["DECISION-4"],
                            measured="the second of two snapshot calls returns the fixed materialised state",
                            unmeasured=["the first call's value equals the second's (only its not raising is measured)",
                                        "the key order (json.dumps(sort_keys=True) orders any dict; JSON equality ignores order)"],
                            note=D4_NOTE.format(sib="AC-STORY-02-02-2..4")),
    "AC-STORY-02-02-2": eff([NEW, call("append", tup(put("k", "v", "r1", 1))), raises("append", "ConflictError", ["delete", "k", "r2", 2]),
                             call("snapshot")], {"returns": {"k": "v"}}, q=EX,
                            measured="the refused delete raises ConflictError (a step) and the snapshot is still {k: v}"),
    "AC-STORY-02-02-3": eff([NEW, call("append", ["delete", "k2", "r3", 3]), call("snapshot")], {"returns": {}}, q=EX,
                            measured="a tombstone on a never-mutated key leaves no key (the snapshot is empty)"),
    "AC-STORY-02-02-4": eff([NEW, call("append", tup(put(NFD_E, "v", "r1", 1))), call("append", tup(put(NFC_E, "v2", "r1", 2))),
                             call("snapshot")], {"returns": {NFC_E: "v"}}, q=EX,
                            measured="the snapshot holds the NFC key with the first value"),
    "AC-STORY-02-02-5": eff([ws(**{"l.jsonl": jsonl(C3)}), NEW, call("snapshot")], {"returns": {"a": 1, "b": 2, "c": 3}},
                            q=BW, decisions=["DECISION-4"],
                            measured="a fresh instance over an existing chain returns the fixed state",
                            witness="each evaluation constructs its own fresh instance; two evaluations are the two instances",
                            note=D4_NOTE.format(sib="AC-STORY-02-02-1")),
    # ---- STORY-03-01 (apply_batch)
    "AC-STORY-03-01-1": eff([NEW, call("apply_batch", [tup(r) for r in BATCH3])],
                            {"files": {L: {"jsonl": {"line": 2, "field": "hash", "equals": C3[2]["hash"]}}}}, q=EX,
                            measured="line 2's hash is the third link of a chain from GENESIS over the batch",
                            unmeasured=["exactly three lines", "a verify() call"]),
    "AC-STORY-03-01-2": eff([ws(**{"l.jsonl": jsonl(C1)}), NEW, call("apply_batch", [["put", "k", "v2", "r1", 200], ["put", "k2", 2, "r2", 201]])],
                            {"files": {L: {"line_count": 2}}}, q=EX, measured="the file gains exactly one line"),
    "AC-STORY-03-01-3": eff([ws(**{"l.jsonl": b""}), NEW,
                             raises("apply_batch", "ConflictError", [["put", "k", "v1", "r1", 100], ["put", "k", "v2", "r2", 200]],
                                    attrs={"key": "k", "incoming_rid": "r2", "committed_rid": "r1", "batch_index": 1})],
                            {"files": {L: {"equals_before": True}}}, q=EX,
                            measured="ConflictError with its four attributes (a step) and the file byte-identical",
                            note="'an empty ledger' is a zero-byte file here"),
    "AC-STORY-03-01-4": eff([ws(**{"l.jsonl": jsonl(C1)}), NEW,
                             raises("apply_batch", "ConflictError", [["put", "k", "v2", "r2", 200]], attrs={"batch_index": 0})],
                            {"files": {L: {"equals_before": True}}}, q=EX,
                            measured="ConflictError with batch_index 0 (a step) and the file unchanged"),
    "AC-STORY-03-01-5": eff([ws(**{"l.jsonl": jsonl(C1)}), NEW, fault("os.replace"),
                             raises("apply_batch", "OSError", [["put", "k2", 2, "r2", 200]])],
                            {"files": {L: {"equals_before": True}}}, q=BW, decisions=["DECISION-1", "DECISION-2"],
                            measured="with os.replace failing once, the file is byte-identical to its pre-batch state",
                            unmeasured=["verify() afterwards (the file is the pre-batch chain, which verifies)"],
                            witness="one fault (os.replace raises OSError once) at one call: a bounded witness of 'a crash "
                                    "at any point'",
                            note="OD-03-01-5: the simulated crash is read as the fault's OSError propagating out of apply_batch"),
    # ---- STORY-03-02 (repair_tail)
    "AC-STORY-03-02-1": eff([ws(**{"l.jsonl": jsonl(C3[:2]) + TRUNC}), NEW, call("repair_tail")],
                            {"files": {L: {"sha256": sha(jsonl(C3[:2]))}}}, q=BW,
                            measured="the file is exactly the valid prefix: tail removed, preserved lines unchanged, final "
                                     "byte newline (the prefix verifies)",
                            witness="a two-line chain followed by an unterminated line that does not parse"),
    "AC-STORY-03-02-2": eff([ws(**{"l.jsonl": jsonl(C3)}), NEW, call("repair_tail")], {"files": {L: {"equals_before": True}}},
                            q=BW, measured="repair_tail returns and the file is byte-identical", witness="a three-line clean chain"),
    "AC-STORY-03-02-3": eff([ws(**{"l.jsonl": jsonl([C3[0], dict(C3[1], value=20), C3[2]]) + TRUNC}), NEW, call("repair_tail")],
                            {"files": {L: {"equals_before": True}}}, q=BW,
                            measured="repair_tail returns and does not modify the file",
                            unmeasured=["the verify verdict reports the earlier corruption"],
                            witness="line 1's value mutated and an unparsable unterminated tail",
                            note="OD-REFUSE: 'refuse' is read as returning without modifying (the plan does not say whether "
                                 "repair_tail raises)"),
    "AC-STORY-03-02-4": eff([ws(**{"l.jsonl": jsonl([C3[0], C3[1], dict(C3[2], hash="0" * 64)])}), NEW, call("repair_tail")],
                            {"files": {L: {"equals_before": True}}}, q=BW,
                            measured="repair_tail returns and does not modify the file",
                            unmeasured=["the corruption is reported via the verdict"],
                            witness="the last line parses and is terminated, its hash overwritten", note="OD-REFUSE as 03-02-3"),
    # ---- STORY-04-01 (the CLI)
    "AC-STORY-04-01-1": cli(["snapshot", L], {"exit_code": 2}, workspace=files_ws(**{"l.jsonl": jsonl(C1)}), q=EX,
                            measured="exit 2"),
    "AC-STORY-04-01-2": cli(["verify"], {"exit_code": 2, "stdout": ""}, q=BW, measured="exit 2 and empty stdout",
                            witness="verify with no positional argument (one subcommand, one wrong count)"),
    "AC-STORY-04-01-3": cli(["--help"], {"exit_code": 0, "stdout": {"regex": r"(?m)^usage:(?=[^\n]*verify)(?=[^\n]*snapshot)(?=[^\n]*apply)(?=[^\n]*repair-tail)"}},
                            q=EX, measured="exit 0 and one stdout line starting 'usage:' names the four subcommands"),
    "AC-STORY-04-01-4": cli(["verify", L], {"exit_code": 0, "stdout": "", "stderr": {"regex": r"\A(?=[^\n]*ok)verify" + ONE_LINE}},
                            workspace=files_ws(**{"l.jsonl": jsonl(C1)}), q=BW,
                            measured="exit 0, empty stdout, stderr exactly one line whose first word is verify and holding 'ok'",
                            witness="a one-line chain (what Ledger.append writes for that put, written by the harness)"),
    "AC-STORY-04-01-5": cli(["snapshot", L, "--out", "<ws>/snap.json"],
                            {"exit_code": 0, "files": {"<ws>/snap.json": {"sha256": sha(snapshot_bytes({"k": {"v": 1}}))}}},
                            workspace=files_ws(**{"l.jsonl": jsonl(C_KV)}), q=EX,
                            measured="exit 0 and <snap> holds the canonical snapshot bytes", unmeasured=["empty stdout"]),
    "AC-STORY-04-01-6": cli(["snapshot", L, "--out", "<ws>/snap.json"],
                            {"exit_code": 0, "files": {"<ws>/snap.json": {"sha256": sha(snapshot_bytes({"a": 1, "b": 2, "c": 3}))}}},
                            workspace=files_ws(**{"batch.json": canon([tup(r) for r in BATCH3])}),
                            pre=[["apply", "--batch", "<ws>/batch.json", L]], q=EX,
                            measured="apply exits 0 (a pre-step) and the ledger then materialises exactly the batch",
                            unmeasured=["apply's empty stdout", "line-level exactness beyond the materialised state"],
                            note="OD-BATCH: the batch file's JSON shape is not fixed by the plan; proposed: a list of "
                                 "[op, key, value, rid, ts] arrays (the plan's tuple notation)"),
    "AC-STORY-04-01-7": cli(["repair-tail", L], {"exit_code": 0, "files": {L: {"equals_before": True}}},
                            workspace=files_ws(**{"l.jsonl": jsonl(C3)}), q=BW,
                            measured="exit 0 and the file byte-identical", unmeasured=["empty stdout"],
                            witness="a three-line clean chain"),
    "AC-STORY-04-02-1": cli(["apply", "--batch", "<ws>/missing.json", L], {"exit_code": 3, "stdout": ""},
                            workspace=files_ws(**{"l.jsonl": jsonl(C1)}), q=EX, measured="exit 3 and empty stdout"),
    "AC-STORY-04-02-2": cli(["apply", "--batch", "<ws>/b.json", L], {"exit_code": 4, "files": {L: {"equals_before": True}}},
                            workspace=files_ws(**{"l.jsonl": jsonl(C1), "b.json": canon([["put", "k", "v2", "r2", 200]])}), q=EX,
                            measured="exit 4 and the file byte-identical", unmeasured=["empty stdout"], note="OD-BATCH"),
    "AC-STORY-04-02-3": cli(["verify", L], {"exit_code": 5, "stdout": ""}, workspace=files_ws(**{"l.jsonl": jsonl(C20_TAMPERED)}),
                            q=BW, measured="exit 5 and empty stdout",
                            witness="a 20-line chain whose line at index 17 has its value changed (mid-chain under either "
                                    "counting of 'line 17')"),
    "AC-STORY-04-02-4": cli(["repair-tail", L], {"exit_code": 5, "stdout": ""}, workspace=files_ws(**{"l.jsonl": jsonl(C20_TAMPERED)}),
                            q=BW, measured="exit 5 and empty stdout", witness="as AC-STORY-04-02-3"),
    # ---- STORY-04-03 (stderr status lines; DECISION-1: 'every success path')
    "AC-STORY-04-03-1": cli(["verify", L], {"exit_code": 0, "stdout": "", "stderr": {"regex": r"\Averify" + ONE_LINE}},
                            workspace=files_ws(**{"l.jsonl": jsonl(C3)}), q=BW, decisions=["DECISION-1"],
                            measured="empty stdout and exactly one stderr line beginning with verify",
                            witness="one success path: verify of an intact three-line chain"),
    "AC-STORY-04-03-2": cli(["apply", "--batch", "<ws>/batch.json", L],
                            {"exit_code": 0, "stdout": "", "stderr": {"regex": r"\Aapply(?=[ \t\n]|\Z)[^\n]*\b3\b[^\n]*\n?\Z"}},
                            workspace=files_ws(**{"batch.json": canon([tup(r) for r in BATCH3])}), q=BW,
                            decisions=["DECISION-1"], measured="empty stdout and one stderr line beginning with apply "
                                                               "holding the count 3 as a word",
                            witness="one success path: a three-element batch on a fresh ledger", note="OD-BATCH"),
    "AC-STORY-04-03-3": cli(["snapshot", L, "--out", "<ws>/snap.json"],
                            {"exit_code": 0, "stdout": "", "stderr": {"regex": r"\Asnapshot(?=[ \t\n]|\Z)[^\n]*snap\.json[^\n]*\n?\Z"}},
                            workspace=files_ws(**{"l.jsonl": jsonl(C3)}), q=BW, decisions=["DECISION-1"],
                            measured="empty stdout and one stderr line beginning with snapshot naming the destination file",
                            witness="one success path: snapshot of a three-line chain to <ws>/snap.json",
                            note="'mentions the destination path' is measured as naming the file: the probe substitutes "
                                 "<ws> only into argv, never back into a stream"),
    "AC-STORY-04-03-4": cli(["repair-tail", L], {"exit_code": 0, "stdout": "", "stderr": {"regex": r"\Arepair-tail" + ONE_LINE}},
                            workspace=files_ws(**{"l.jsonl": jsonl(C3[:2]) + TRUNC}), q=BW, decisions=["DECISION-1"],
                            measured="empty stdout and exactly one stderr line beginning with repair-tail",
                            witness="one success path: a successful repair of a truncated tail (the clean path is "
                                    "AC-STORY-04-01-7's stimulus)"),
    "AC-STORY-04-03-5": cli(["snapshot", L, "--out", "<ws>/snap.json"], {"exit_code": 0, "stdout": ""},
                            workspace=files_ws(**{"l.jsonl": jsonl(C3)}), q=BW, decisions=["DECISION-1"],
                            measured="empty stdout", witness="one success path: snapshot --out"),
    # ---- STORY-05-01 / 05-02 (DECISION-3: the six test-named criteria, AFTER)
    "AC-STORY-05-01-1": eff([NEW, *(call("append", tup(r)) for r in SEQ), call("verify")],
                            {"returns": {"ok": True, "first_bad_index": None}}, q=BW, decisions=["DECISION-3", "DECISION-1"],
                            measured="after a fixed conflict-free sequence (puts, deletes, replays, an NFD/NFC replay) "
                                     "verify() returns ok",
                            unmeasured=["two snapshot() calls return equal dicts (no DECISION-4 class for a library subject)"],
                            witness="one fixed nine-operation sequence stands for the property test's 50 seeded sequences"),
    "AC-STORY-05-01-2": eff([ws(**{"l.jsonl": jsonl(chain(*SEQ[:2]))}), NEW,
                             raises("append", "ConflictError", ["delete", "a", "s9", 10])],
                            {"files": {L: {"equals_before": True}}}, q=BW, decisions=["DECISION-3", "DECISION-1"],
                            measured="when an element raises ConflictError, the file is byte-identical to its state after "
                                     "the prefix",
                            witness="a committed two-element prefix, then a delete of 'a' under another rid"),
    "AC-STORY-05-01-3": refused("REMOVED_FROM_PRODUCTPROOF",
                                "unittest / pytest agreement of a test module is a property of the developer's tests, not "
                                "of the product: a DEVELOPER_TEST_REQUIREMENT (as R-11 in the reference fixture), outside "
                                "ProductProof by invariant IX", q=EX, measured="nothing", decisions=["DECISION-3"]),
    "AC-STORY-05-02-1": refused("REMOVED_FROM_PRODUCTPROOF",
                                "line coverage >= 85% is a project quality gate over the developer's tests (RFC §15), not "
                                "a product behaviour: a DEVELOPER_TEST_REQUIREMENT", q=EX, measured="nothing",
                                decisions=["DECISION-3"]),
    "AC-STORY-05-02-2": refused("REMOVED_FROM_PRODUCTPROOF", "as AC-STORY-05-01-3, for the whole suite", q=EX,
                                measured="nothing", decisions=["DECISION-3"]),
    "AC-STORY-05-02-3": refused("REMOVED_FROM_PRODUCTPROOF",
                                "what the coverage measurement includes is configuration of a developer-test gate: a "
                                "DEVELOPER_TEST_REQUIREMENT", q=EX, measured="nothing", decisions=["DECISION-3"]),
    # ---- STORY-05-03
    "AC-STORY-05-03-1": tree(NET, q=EX, measured="zero lines of the package tree match the pattern", witness=TREE,
                             unmeasured=["'and the test passes' (a developer-test clause)"]),
    "AC-STORY-05-03-2": tree(SIDE, q=EX, measured="zero lines of the package tree match the pattern", witness=TREE,
                             unmeasured=["'and the test passes' (a developer-test clause)"]),
}

#: DECISION-3 (APPROVED_FOR_PROPOSAL_ONLY): the six criteria whose PLAN-V2.1 subject is a developer test
D3 = ("AC-STORY-05-01-1", "AC-STORY-05-01-2", "AC-STORY-05-01-3", "AC-STORY-05-02-1", "AC-STORY-05-02-2", "AC-STORY-05-02-3")

OPEN_DECISIONS = {
    "OD-D4": "DECISION-4 criteria with library subjects (01-02-2, 01-02-4, 01-02-6, 01-03-2, 01-03-4, 02-02-1, 02-02-5): "
             "accept the restatement against one constant derived from the requirements, or commission a DECISION-4 "
             "equality class for python_callable_v2 / process_effect (a new probe identity: a probe package, not an "
             "edit); 01-02-4 cannot be witnessed at all while the contract layer sorts mapping keys",
    "OD-RETURN": "the value append returns on a replay ('the original line dict … with replayed is True, committed is "
                 "False'): a dict of the stored line plus two keys, or an object with attributes? Until fixed, the "
                 "replay criteria measure only 'returns without raising' and the chain length",
    "OD-REFUSE": "how repair_tail refuses (return a verdict, or raise): the proposal reads 'refuse' as returning without "
                 "modifying the file",
    "OD-BATCH": "the JSON shape of a CLI batch file (not fixed by PLAN-V2.1): proposed a list of [op, key, value, rid, ts]",
    "OD-01-01-6": "one criterion names two symbols (Ledger, ConflictError): split into two contracts, or keep the class",
    "OD-02-01-4": "first_bad_index 'i (or the earlier index)': proposed i, the first violation of §3.3",
    "OD-03-01-5": "the simulated crash in apply_batch: proposed that the fault's OSError propagates to the caller",
    "OD-STORE": "the store criteria 01-04-1, 01-04-4, 01-04-5, 01-04-6 are refused (bytes arguments, a list of bytes, "
                "an unobservable temp-file location): restate them at the Ledger level (process_effect over files), or "
                "accept them as unmeasured",
    "OD-FACETS": "criteria with more than one clause are measured on one clause (`measured`); every other clause is "
                 "listed as `unmeasured` — accept, or split such criteria into one contract per clause",
    "OD-STRONGER": "01-03-1 and 01-03-5 fix the digest's value (requirements §3.2), not only its form; accept",
}


# --------------------------------------------------------------------------------------- authoring

class Refusal(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(f"{code}: {reason}")
        self.code, self.reason = code, reason


@functools.lru_cache(maxsize=1)
def owner_decisions() -> dict:
    return json.loads((ROOT / DECISIONS_REL).read_text(encoding="utf-8"))


def decision_criteria(n: int) -> tuple[str, ...]:
    d = next(x for x in owner_decisions()["decisions"] if x["id"] == f"DECISION-{n}")
    return tuple(f"AC-STORY-{c}" for c in d["criteria"])


def requirements() -> dict:
    """The fourteen FR requirements exactly as P10 built them (so their hashes are P10's)."""
    from aisef2.product.approval import Requirement
    return {fr: Requirement.create(id=fr, text=title, source=f"docs/requirements.md@{P10.REQUIREMENTS_SHA256[:12]} (PRD {fr})")
            for fr, title in P10.FR_TITLES.items()}


def author(ac_id: str, entry: dict, requirement_id: str, polarity: str, rationale: str, reqs: dict) -> dict:
    """One criterion's contract and spec, or a typed Refusal. The checks are the aid's (DECISION-1) and the kernel's
    (the contract rule, the compiler, the harness registry's observation class)."""
    from aisef2.arch.enums import Enforcement, Polarity, SubjectAbsence, SubjectKind
    from aisef2.probe import catalog
    from aisef2.product.approval import ContractApproval
    from aisef2.product.compiler import CompileError, ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, ContractError, Subject
    q = entry.get("quantifier")
    if q not in QUANTIFIERS:
        raise Refusal("REFUSED_QUANTIFIER_UNDECLARED", f"{ac_id} declares no quantifier semantics of {QUANTIFIERS} "
                                                        "(DECISION-1: every criterion declares one)")
    if ac_id in decision_criteria(1) and q == "exhaustive_finite_domain":
        raise Refusal("REFUSED_UNIVERSAL_DECLARED_EXHAUSTIVE", f"{ac_id} is universally quantified (DECISION-1) and "
                                                                "names no finite domain")
    if "refusal" in entry:
        raise Refusal(entry["refusal"], entry["reason"])
    try:
        contract = BehaviorContract.create(id=f"BC-V22-{ac_id}", requirement_ids=(requirement_id,),
                                           subject=Subject(SubjectKind(entry["kind"]), entry["locator"]),
                                           stimulus=entry["stimulus"], observable=entry["observable"],
                                           polarity=Polarity[polarity], subject_absence=SubjectAbsence[entry["absence"]],
                                           rationale=rationale)
    except ContractError as e:
        raise Refusal("REFUSED_BY_CONTRACT_RULE", f"ContractError: {e}") from None
    approval = ContractApproval(requirement_id, reqs[requirement_id].requirement_hash, contract.id,
                                contract.contract_hash, CHECK_APPROVER, 0.0, ())
    active = catalog.active()
    refs = {kind: ProbeRef(e.probe_id, e.probe_digest) for kind, e in active.items()}
    try:
        spec = compile_spec(contract, requirements=reqs, approvals=[approval], probes=refs)
    except (CompileError, ContractError) as e:
        raise Refusal("REFUSED_BY_COMPILER", f"{type(e).__name__}: {e}") from None
    e = active[contract.subject.kind]
    cls = catalog.registry().observation_class(e.probe_id, e.probe_digest, spec)
    if cls is None:
        raise Refusal("UNSUPPORTED_OBSERVATION", f"{e.probe_id} gives the spec no observation class (UNSUPPORTED -> "
                                                 "INVALID_SPEC at admission)")
    enforcement = e.factory().enforcement()
    if q != "exhaustive_finite_domain" and enforcement is Enforcement.FULL:
        raise Refusal("REFUSED_WITNESS_UNDER_FULL", f"{q} on {e.probe_id}, whose enforcement is FULL: a witness "
                                                    "measurement is never a FULL proof (DECISION-1)")
    table = getattr(importlib.import_module(e.factory.__module__), "CLASS_TABLE", {})
    return {"contract": contract, "spec": spec, "approval": approval, "probe_id": e.probe_id,
            "probe_digest": e.probe_digest, "observation_class": cls, "enforcement": enforcement.value,
            "class_quantifier": table.get(cls, {}).get("quantifier")}


def calibrations() -> tuple:
    """Every Cycle-2 ProbeCapabilityCalibration the lanes recorded (the harness's, read from their records)."""
    from aisef2.probe.calibration import ProbeCapabilityCalibration
    keys = ("probe_id", "probe_digest", "observation_class", "positive_fixture", "negative_fixture", "demonstrated_at")
    out = []
    for rel in CALIBRATION_RECORDS:
        c = json.loads((ROOT / rel).read_text(encoding="utf-8"))["calibrations"]
        rows = [r for v in c.values() for r in v] if isinstance(c, dict) else c
        out += [ProbeCapabilityCalibration(*(r[k] for k in keys)) for r in rows
                if set(keys) <= set(r) and r.get("qualified", True)]
    return tuple(out)


def build() -> dict:
    """The proposal: 77 criteria authored, compiled, the compiled ones planned and put to the admission engine twice."""
    from aisef2.arch.enums import ObligationRole, SubjectAbsence
    from aisef2.orchestrate import seam
    from aisef2.plan import static_admission as sa
    from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation
    from aisef2.probe import catalog
    rows = P10.v1_rows()
    assert len(rows) == 77 and set(V22) == {r["ac_id"] for r in rows} == set(P10.V2), "V22 covers the 77 frozen criteria"
    table = json.loads((ROOT / P10.MIGRATION_TABLE_REL).read_text(encoding="utf-8"))
    reqs = requirements()
    criteria, contracts, specs, approvals = [], {}, {}, []
    for r in rows:
        ac, t = r["ac_id"], V22[r["ac_id"]]
        absence = SubjectAbsence[t.get("absence", "REQUIRES_SUBJECT")]
        legacy = seam.resolve(ac, r["proof_mode"], table, absence)
        role, polarity = legacy.role.value, legacy.polarity.value
        e = {"ac_id": ac, "story": r["story"], "requirement": r["requirement"], "v1_mode": r["proof_mode"], "role": role,
             "polarity": polarity, "criterion": r["criterion"], "quantifier": t.get("quantifier"),
             "witness": t.get("witness"), "measured": t["measured"], "unmeasured": t["unmeasured"],
             "decisions": t["decisions"], "note": t["note"], "depends_on_stories": list(r["depends_on"])}
        if "refusal" not in t:
            e.update(subject_kind=t["kind"], locator=t["locator"], stimulus=t["stimulus"], observable=t["observable"],
                     subject_absence=t["absence"])
        try:
            a = author(ac, t, r["requirement"], polarity, r["criterion"], reqs)
        except Refusal as x:
            e.update(v22_status=x.code, typed_refusal=x.reason)
            criteria.append(e)
            continue
        contracts[a["contract"].id], specs[a["spec"].id] = a["contract"], a["spec"]
        approvals.append(a["approval"])
        e.update(v22_status="COMPILED", contract_id=a["contract"].id, contract_hash=a["contract"].contract_hash,
                 spec_id=a["spec"].id, semantic_hash=a["spec"].semantic_hash, probe_id=a["probe_id"],
                 probe_digest=a["probe_digest"], observation_class=a["observation_class"],
                 enforcement=a["enforcement"], class_quantifier=a["class_quantifier"])
        criteria.append(e)
    compiled = [e for e in criteria if e["v22_status"] == "COMPILED"]
    by_story: dict[str, list[str]] = {}
    for e in compiled:
        by_story.setdefault(e["story"], []).append(e["ac_id"])
    obligations = tuple(PlanObligation(e["ac_id"], e["spec_id"], e["story"], ObligationRole[e["role"]],
                                       EXPECTED_AT_PARENT[ObligationRole[e["role"]]],
                                       tuple(c for s in e["depends_on_stories"] for c in by_story.get(s, ())),
                                       f"{e['story']} owns {e['ac_id']} ({e['requirement']}) as PLAN-V2.2 proposes it")
                        for e in compiled)
    plan = Plan.create(id=PLAN_ID, baseline=P10.LEDGERLOCK_PLAN_COMMIT, obligations=obligations,
                       plan_quality_policy=NOT_PREREGISTERED)
    cals = calibrations()
    catalogue, registry = catalog.catalogue(), catalog.registry()
    engine = sa.StaticPlanAdmissionEngine()
    checked = engine.admit(plan, sa.AdmissionInputs(reqs, contracts, tuple(approvals), specs, catalogue, cals, registry))
    bare = engine.admit(plan, sa.AdmissionInputs(reqs, contracts, (), specs, catalogue, cals, registry))
    return {"criteria": criteria, "plan": plan, "requirements": reqs, "specs": specs, "checked": checked, "bare": bare,
            "calibrations": cals}


def _admission(result) -> dict:
    return {"engine_digest": result.engine_digest, "admitted": result.admitted, "result_digest": result.result_digest,
            "checks": [{"number": c.number, "name": c.name, "passed": c.passed, "problems_count": len(c.problems),
                        "problems": list(c.problems[:5])} for c in result.checks]}


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout.strip()


def _file(rel: str) -> dict:
    return {"path": rel, "sha256": sha((ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))}


def record() -> dict:
    """The P5-PLAN-V2.2-PROPOSAL record: deterministic for a given tree (no clock, no host identity)."""
    from aisef2.probe import catalog
    from aisef2.product.compiler import COMPILER_DIGEST, COMPILER_ID
    b = build()
    crit, plan = b["criteria"], b["plan"]
    counts: dict[str, int] = {}
    for e in crit:
        counts[e["v22_status"]] = counts.get(e["v22_status"], 0) + 1
    before = {ac: P10.V2[ac] for ac in D3}
    p10_status = {e["ac_id"]: e for e in json.loads((ROOT / "closure-evidence/v2/P10/WORKLOAD.json").read_text(encoding="utf-8"))["criteria"]}
    mappings = []
    for ac in D3:
        e = next(x for x in crit if x["ac_id"] == ac)
        after = ({"subject_kind": e["subject_kind"], "locator": e["locator"], "stimulus": e["stimulus"],
                  "observable": e["observable"], "v22_status": e["v22_status"], "spec_id": e.get("spec_id"),
                  "semantic_hash": e.get("semantic_hash"), "measured": e["measured"], "unmeasured": e["unmeasured"]}
                 if "locator" in e else {"v22_status": e["v22_status"], "reason": e["typed_refusal"]})
        mappings.append({"ac_id": ac, "criterion": e["criterion"], "requirement": e["requirement"], "role": e["role"],
                         "before": {"subject_kind": before[ac]["kind"], "locator": before[ac]["locator"],
                                    "stimulus": before[ac]["stimulus"], "observable": before[ac]["observable"],
                                    "p10_status": p10_status[ac]["v2_status"], "p10_refusal": p10_status[ac]["typed_refusal"]},
                         "after": after, "approved": False})
    entries = {e.probe_id: {"digest": e.probe_digest, "kind": e.subject_kind.value, "active": e.active, "cycle": e.cycle}
               for e in catalog.CATALOG}
    body = {
        "record": "AISEF V2 — C2-P5 WP-2.5.1 LEDGERLOCK PLAN-V2.2 PROPOSAL (contract authoring aid)",
        "work_package": PACKAGE,
        "authority": "owner ruling 'AISEF V2 — CYCLE-2 OWNER RULING / C2-P0 ACCEPTED / AUTHORIZE MAXIMUM SAFE PARALLEL "
                     "EXECUTION' (2026-09-29): C2-P5 WP-2.5.1 after the integration of C2-P1..P4",
        "status": "PROPOSAL — NOT APPROVED, NOT APPLIED; no LedgerLock run under it (DECISION-3); P10 untouched",
        "identities": {"aisef2_tree": _git("rev-parse", "HEAD:aisef2"), "compiler": {"id": COMPILER_ID, "digest": COMPILER_DIGEST},
                       "admission_engine_digest": b["checked"].engine_digest, "catalog": entries,
                       "owner_decisions": _file(DECISIONS_REL), "v1_audit": _file(P10.V1_AUDIT_REL),
                       "migration_table": _file(P10.MIGRATION_TABLE_REL), "p10_workload": _file("closure-evidence/v2/P10/WORKLOAD.json"),
                       "requirements_sha256": P10.REQUIREMENTS_SHA256, "plan_v2_1_commit": P10.LEDGERLOCK_PLAN_COMMIT,
                       "authoring_aid": _file("validation/qualification/p10_contracts.py"),
                       "calibration_records": [_file(r) for r in CALIBRATION_RECORDS]},
        "requirements": {fr: {"hash": r.requirement_hash, "title": P10.FR_TITLES[fr]} for fr, r in b["requirements"].items()},
        "approvals": {"given": [], "check_approver": CHECK_APPROVER,
                      "rule": "every compiled contract was bound, in memory only, by an approval of the check identity so "
                              "the frozen compiler and admission engine could be asked whether the proposal WOULD compile "
                              "and admit; no approval is recorded, none is the owner's, and the plan is not in force "
                              "(precedent: WP-2.3.2's fixture approver human:c2-p3-calibration-fixture)"},
        "plan": {"id": plan.id, "plan_hash": plan.plan_hash, "baseline": plan.baseline,
                 "obligations": len(plan.obligations), "stories": len({o.story_id for o in plan.obligations}),
                 "obligations_by_role": {r: sum(1 for o in plan.obligations if o.role.value == r) for r in ("INTRODUCE", "PRESERVE", "VERIFY")},
                 "plan_quality_policy": "NOT_PREREGISTERED (DECISION-5)"},
        "counts_by_v22_status": dict(sorted(counts.items())),
        "counts_by_subject_kind": {k: sum(1 for e in crit if e.get("subject_kind") == k) for k in sorted({e.get("subject_kind") for e in crit if e.get("subject_kind")})},
        "counts_by_quantifier": {q: sum(1 for e in crit if e["quantifier"] == q) for q in QUANTIFIERS},
        "decision_1": {"criteria": list(decision_criteria(1)),
                       "declared": {ac: next(e["quantifier"] for e in crit if e["ac_id"] == ac) for ac in decision_criteria(1)},
                       "rule": "every criterion declares one of the three; a DECISION-1 criterion is never exhaustive; a "
                               "witness measurement is refused on a FULL probe; no verdict of a witness is a proof"},
        "decision_2": {ac: {"v22_status": next(e["v22_status"] for e in crit if e["ac_id"] == ac),
                            "faults": [s["fault"] for s in (next(e for e in crit if e["ac_id"] == ac).get("stimulus") or {}).get("scenario", []) if s["step"] == "fault"]}
                       for ac in decision_criteria(2)},
        "decision_3_mappings": mappings,
        "decision_4": {ac: {"v22_status": next(e["v22_status"] for e in crit if e["ac_id"] == ac),
                            "class_available": False, "note": next(e["note"] for e in crit if e["ac_id"] == ac)}
                       for ac in decision_criteria(4)},
        "open_decisions": OPEN_DECISIONS,
        "static_admission": {"with_check_approvals": _admission(b["checked"]), "without_approvals": _admission(b["bare"])},
        "criteria": crit,
    }
    body["proposal_digest"] = sha(canon({"plan_hash": plan.plan_hash, "criteria": crit, "mappings": mappings}))
    body["problems"] = problems(body)
    body["verdict"] = ("PROPOSAL ADMITTED STATICALLY (with the check approvals); OWNER REVIEW PENDING"
                       if not body["problems"] else "PROBLEMS")
    return json.loads(json.dumps(body))


def problems(body: dict) -> list[str]:
    out = []
    crit = body["criteria"]
    if len(crit) != 77 or len({e["ac_id"] for e in crit}) != 77:
        out.append("the proposal does not account for the 77 criteria exactly once")
    if not body["static_admission"]["with_check_approvals"]["admitted"]:
        out.append("the compiled proposal is not admitted even with the check approvals")
    if body["static_admission"]["without_approvals"]["admitted"]:
        out.append("the proposal is admitted without any approval: the kernel's approval gate did not hold")
    if body["approvals"]["given"]:
        out.append("an approval is recorded")
    if any(m["approved"] for m in body["decision_3_mappings"]) or len(body["decision_3_mappings"]) != 6:
        out.append("DECISION-3: six unapproved mappings are required")
    out += [f"{e['ac_id']}: no quantifier semantics" for e in crit if e["quantifier"] not in QUANTIFIERS]
    return out


# --------------------------------------------------------------------------------------- the document

def document(rec: dict) -> str:
    crit = rec["criteria"]
    lines = [
        "# LedgerLock PLAN-V2.2 — PROPOSAL (not approved, not applied)",
        "",
        f"**Status.** {rec['status']}. Generated by `validation/qualification/p10_contracts.py` (WP-2.5.1) from PLAN-V2.1's 77 "
        f"criteria as V1 froze them; the record is [`P5-PLAN-V2.2-PROPOSAL.json`](../../../../{OUT_REL}).",
        "",
        f"- proposal digest `{rec['proposal_digest']}`; plan `{rec['plan']['id']}` hash `{rec['plan']['plan_hash']}`, baseline "
        f"`{rec['plan']['baseline']}`",
        f"- {rec['plan']['obligations']} obligations in {rec['plan']['stories']} stories "
        f"({', '.join(f'{k} {v}' for k, v in rec['plan']['obligations_by_role'].items())}); plan quality NOT_PREREGISTERED",
        f"- criteria by status: {', '.join(f'{k} {v}' for k, v in rec['counts_by_v22_status'].items())}",
        f"- by quantifier: {', '.join(f'{k} {v}' for k, v in rec['counts_by_quantifier'].items())}",
        f"- static admission with the check approvals: **{'ADMITTED' if rec['static_admission']['with_check_approvals']['admitted'] else 'NOT ADMITTED'}**; "
        f"without approvals: **{'ADMITTED' if rec['static_admission']['without_approvals']['admitted'] else 'NOT ADMITTED'}** "
        f"(checks {', '.join(str(c['number']) for c in rec['static_admission']['without_approvals']['checks'] if not c['passed'])} fail)",
        "",
        "No approval is recorded. The check identity `" + rec["approvals"]["check_approver"] + "` exists only in memory so "
        "that the frozen compiler and admission engine can say whether the proposal would compile and admit.",
        "",
        "## The six DECISION-3 mappings (for owner review)",
        "",
    ]
    for m in rec["decision_3_mappings"]:
        a = m["after"]
        after = (f"`{a['subject_kind']}` `{a['locator']}`, observable `{json.dumps({k: v for k, v in a['observable'].items() if k != 'within_s'}, ensure_ascii=False)}`; "
                 f"measures: {a['measured']}" + (f"; not measured: {'; '.join(a['unmeasured'])}" if a["unmeasured"] else "")
                 if "locator" in a else f"**{a['v22_status']}** — {a['reason']}")
        lines += [f"### {m['ac_id']} ({m['requirement']}, {m['role']})", "",
                  f"- before: `{m['before']['subject_kind']}` `{m['before']['locator']}` — P10: {m['before']['p10_status']}",
                  f"- after: {after}", "- approved: no", ""]
    lines += ["## Open decisions", ""] + [f"- **{k}** — {v}" for k, v in rec["open_decisions"].items()] + ["", "## Criteria", "",
              "| criterion | kind | class | quantifier | status | measured |", "|---|---|---|---|---|---|"]
    for e in crit:
        lines.append(f"| {e['ac_id']} | {e.get('subject_kind', '—')} | {e.get('observation_class', '—')} | {e['quantifier']} | "
                     f"{e['v22_status']} | {e['measured'].replace('|', '/')} |")
    lines += ["", "## Refusals", ""] + [f"- **{e['ac_id']}** `{e['v22_status']}` — {e['typed_refusal']}" for e in crit
                                         if e["v22_status"] != "COMPILED"]
    return "\n".join(lines) + "\n"


def write() -> dict:
    rec = record()
    if rec["problems"]:
        raise SystemExit("refused: " + "; ".join(rec["problems"]))
    (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (ROOT / DOC_REL).write_text(document(rec), encoding="utf-8", newline="\n")
    return rec


def check() -> list[str]:
    rec = record()
    out = list(rec["problems"])
    committed = json.loads((ROOT / OUT_REL).read_text(encoding="utf-8"))
    if committed != rec:
        out.append(f"{OUT_REL} is not what the authoring aid derives from this tree")
    if (ROOT / DOC_REL).read_text(encoding="utf-8").replace("\r\n", "\n") != document(rec):
        out.append(f"{DOC_REL} is not what the authoring aid derives from this tree")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        rec = write()
        print(f"{OUT_REL}: {rec['verdict']}; {rec['counts_by_v22_status']}; plan {rec['plan']['plan_hash'][:12]}; "
              f"proposal {rec['proposal_digest'][:12]}")
        return 0
    problems_ = check()
    print("\n".join(problems_) if problems_ else "PASS")
    return 1 if problems_ else 0


if __name__ == "__main__":
    raise SystemExit(main())
