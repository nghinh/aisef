"""WP-2.5.1 (C2-P5, corrected per the owner ruling "CYCLE-2 OWNER REVIEW / C2-P5 NOT ACCEPTED / P5 CORRECTION AUTHORIZED",
2026-09-30) — the contract authoring aid: the LedgerLock PLAN-V2.2 PROPOSAL rebuilt from the FROZEN REQUIREMENTS.

    python -P validation/qualification/p10_contracts.py --write    # writes the record and the proposal document
    python -P validation/qualification/p10_contracts.py --check    # both committed files are what this module derives

**Normative priority** (owner): 1 frozen requirements, 2 approved Behavior Contract semantics, 3 ProductProofSpec, 4 plan /
story decomposition, 5 developer tests. PLAN-V2.1 is not normative: a PLAN-V2.1 detail the requirements do not require
never becomes a mandatory ProductProof property. The reference fixture (WP-2.0.3), authored from the requirements, is
never changed to fit a plan.

**Three tables, one direction of authority.**

* `CLAUSES` — every clause of tests/v2/fixtures/workloads/ledgerlock-reference/REQUIREMENTS.md (sections by
  REQUIREMENTS-MAP.json id), classified NORMATIVE_PRODUCT_REQUIREMENT, ENGINEERING_TEST_REQUIREMENT,
  UNSUPPORTED_FOR_FULL_ENFORCEMENT or DESCRIPTIVE, with the specs that cover it or the exact reason none can.
* `SPECS` — the retained ProductProofSpecs: each observes ONE clause (atomic), traces to its clause(s), names its probe
  stimulus and observable, its quantifier semantics (DECISION-1) and its own falsifiability witness in the P5 mutant
  corpus (tests/v2/fixtures/workloads/ledgerlock-p5-mutants/MUTANTS.json).
* `CRITERIA` — each of PLAN-V2.1's 77 criteria classified NORMATIVE_PRODUCT_REQUIREMENT, ENGINEERING_TEST_REQUIREMENT,
  PLAN_ONLY_DETAIL or UNSUPPORTED_FOR_FULL_ENFORCEMENT, with the specs its normative content maps to and every plan-only
  or unsupported facet named.

**Implementation-neutral observation.** A spec observes only what every implementation conforming to the requirements
must show, whatever it chose where the requirements are open (canonical bytes, the GENESIS form, return
representations, the snapshot layout, the CLI batch-file shape, argument types): CLI exit codes (§9) of the invocations
§5/§6/§7/§14 name; the on-disk JSONL fields (§3.2); the ConflictError type (§4.3, §13); the equality of two results of one
scenario; the line count and final byte of the ledger; the package tree's source. Chains are written by the product
itself, never by the harness (a harness-written hash presumes a canonical encoding) — except lines whose hashes are
wrong under ANY encoding (`BOGUS`). **One interface binding** is not fixed by the requirements and is declared, not
hidden (`INTERFACE_BINDINGS` IB-LEDGER): a Ledger is constructed with its ledger path and offers apply_batch(ops),
snapshot() and verify() as methods; ops are delivered as JSON arrays.

**Approvals.** `compile_spec` and the StaticPlanAdmissionEngine accept only a contract that a `human:` approval binds
(aisef2/product/approval.py). The admission is measured with approvals of `SYNTHETIC_APPROVER`, NON-AUTHORITATIVE TEST
FIXTURE DATA created in memory and never persisted as a ContractApproval or as owner approval evidence: it shows only
that the proposal WOULD admit once valid approvals exist. The record carries `approvals.given = []`, and the admission
without any approval (not admitted) beside it.

**C2-P5-FINDING-001** stays in the history: the aid refuses a MUST_NOT_HOLD contract whose observable is not declared to
state the forbidden behaviour (the adversarial test replays the inverted form).
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

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import p10 as P10  # noqa: E402

OUT_REL = "closure-evidence/v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json"
DOC_REL = "docs/implementation/v2/cycle2/LEDGERLOCK-PLAN-V2.2-PROPOSAL.md"
DECISIONS_REL = "closure-evidence/v2/cycle2/OWNER-DECISIONS.json"
FIX_REL = "tests/v2/fixtures/workloads/ledgerlock-reference"
MUTANTS_REL = "tests/v2/fixtures/workloads/ledgerlock-p5-mutants/MUTANTS.json"
PLAN_ID = "LEDGERLOCK-PLAN-V2.2-PROPOSAL"
PACKAGE = "WP-2.5.1"
#: the schema requires the human: namespace (approval.HUMAN_PREFIX); this identity is NON-AUTHORITATIVE TEST FIXTURE DATA
SYNTHETIC_APPROVER = "human:SYNTHETIC-TEST-FIXTURE-NOT-AN-APPROVAL"
QUANTIFIERS = ("exhaustive_finite_domain", "bounded_witness_measurement", "unsupported_for_full_enforcement")
EX, BW, UF = QUANTIFIERS
CLASSES = ("NORMATIVE_PRODUCT_REQUIREMENT", "ENGINEERING_TEST_REQUIREMENT", "PLAN_ONLY_DETAIL",
           "UNSUPPORTED_FOR_FULL_ENFORCEMENT")
N, E, P, U = CLASSES
D = "DESCRIPTIVE"
WINDOW = 30
CALIBRATION_RECORDS = ("closure-evidence/v2/cycle2/P1-FILE-ARTIFACT-CALIBRATION.json",
                       "closure-evidence/v2/cycle2/P2-CLI-CALIBRATION.json",
                       "closure-evidence/v2/cycle2/P3-EFFECT-CALIBRATION.json",
                       "closure-evidence/v2/cycle2/P4-PYTHON-CALLABLE-V2-CALIBRATION.json")

INTERFACE_BINDINGS = {
    "IB-CLI": {"binding": "python -m ledgerlock verify <ledger> | snapshot <ledger> [--out <file>] | apply --batch <file> "
                          "<ledger> | repair-tail <ledger>, exit codes 0/2/3/4/5",
               "source": "§14 items 1-4, §6, §5, §7, §9", "fixed_by_requirements": True},
    "IB-JSONL": {"binding": "the ledger is one JSON object per line with the fields op, key, value (put), ts, id, hash, "
                            "prev_hash; key NFC; ts an integer; lines newline-terminated",
                 "source": "§3.2, §3.1, §7 (a truncated line is one whose last byte is not a newline)",
                 "fixed_by_requirements": True},
    "IB-NAMES": {"binding": "ledgerlock/ledger.py defines Ledger, ConflictError, append, verify, snapshot, apply_batch; a "
                            "conflicting mutation raises ConflictError",
                 "source": "§13, §4.3", "fixed_by_requirements": True},
    "IB-LEDGER": {"binding": "a Ledger is constructed with its ledger file path, Ledger(<path>), and offers apply_batch(ops), "
                             "snapshot() and verify() as methods; ops are (op, key, value, rid, ts) delivered as 5-element "
                             "JSON arrays (a contract stimulus is JSON data)",
                  "source": "§5 names apply_batch(ops) and its tuple shape, §6 snapshot(), §3.4 verify from the library, "
                            "§12 'the configured ledger path', §13 the class Ledger",
                  "fixed_by_requirements": False,
                  "gap": "the requirements do not say how a Ledger is bound to its path, nor that an implementation must "
                         "accept arrays where they say tuples; every process_effect spec depends on this binding (the "
                         "reference and PLAN-V2.1 read it the same way) — open normative gap OG-IB-LEDGER"},
    "IB-ELEMENTS": {"binding": "a delete element carries null in its value slot; ts is an integer the caller supplies",
                    "source": "§5 gives every element the shape (op, key, value, rid, ts); §3.2 gives a delete line no value",
                    "fixed_by_requirements": False, "gap": "the requirements do not say what a delete's value slot holds"},
    "IB-EMPTY": {"binding": "a zero-byte file is a fresh, empty ledger (a valid chain of no lines)",
                 "source": "§14 item 1 'a fresh ledger'; §3.3 (ok when every line verifies)",
                 "fixed_by_requirements": False,
                 "gap": "a 'fresh ledger' could also be a path that does not exist yet, which §9 makes an I/O error (RISK-4); "
                        "the specs on an empty ledger (S-5-a, S-6-d, S-7-d, S-9-a, S-9-c, S-9-e) read it as a zero-byte file"},
}

# --------------------------------------------------------------------------------------- stimuli (implementation-neutral)

L = "<ws>/l.jsonl"
LEDGER = "ledgerlock.ledger:Ledger"
MAIN = "ledgerlock:__main__"
NFC_E, NFD_E = "é", "é"
TRUNC = b'{"op":"put","key":"d"'     # an unterminated final line that does not parse, under any encoding


def _json_line(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


#: lines whose stored hash is wrong under every canonical encoding and either GENESIS form (the harness never writes a
#: line it presents as valid)
BOGUS = [_json_line({"op": "put", "key": "a", "value": 1, "ts": 1, "id": "r1", "prev_hash": "GENESIS", "hash": "0" * 64}),
         _json_line({"op": "put", "key": "b", "value": 2, "ts": 2, "id": "r2", "prev_hash": "0" * 64, "hash": "0" * 64})]


def put(key, value, rid, ts) -> list:
    return ["put", key, value, rid, ts]


def dele(key, rid, ts) -> list:
    return ["delete", key, None, rid, ts]


NEW = {"step": "construct", "args": [L], "kwargs": {}}


def batch(*ops, as_=None) -> dict:
    return {"step": "call", "method": "apply_batch", "args": [list(ops)], "kwargs": {}, **({"as": as_} if as_ else {})}


def refuse(*ops) -> dict:
    return {"step": "expect_raises", "method": "apply_batch", "args": [list(ops)], "kwargs": {}, "exception": "ConflictError"}


def call(method, as_=None) -> dict:
    return {"step": "call", "method": method, "args": [], "kwargs": {}, **({"as": as_} if as_ else {})}


def edit(line, field, value) -> dict:
    return {"step": "edit_jsonl", "path": L, "line": line, "field": field, "value": value}


def cli_step(*argv, code) -> dict:
    return {"step": "subprocess", "argv": ["-m", "ledgerlock", *argv], "expect_exit": code}


def ws(data: bytes) -> dict:
    return {"step": "workspace", "files": {"l.jsonl": {"bytes_hex": data.hex()}}}


def count(n) -> dict:
    return {"files": {L: {"line_count": n}}}


def field(line, name, value) -> dict:
    return {"files": {L: {"jsonl": {"line": line, "field": name, "equals": value}}}}


SAME = {"returns_name": "after", "equals_name": "before"}
THREE = (put("a", 1, "r1", 1), put("b", 2, "r2", 2), put("c", 3, "r3", 3))


def eff(steps, observable, **meta):
    return {"kind": "process_effect", "locator": LEDGER, "stimulus": {"scenario": steps},
            "observable": {**observable, "within_s": WINDOW}, "absence": "REQUIRES_SUBJECT", **meta}


def cli(argv, observable, *, ledger=None, **meta):
    stim = {"argv": list(argv), **({"workspace": {"l.jsonl": {"bytes_hex": ledger.hex()}}} if ledger is not None else {})}
    return {"kind": "cli_invocation", "locator": MAIN, "stimulus": stim, "observable": {**observable, "within_s": WINDOW},
            "absence": "REQUIRES_SUBJECT", **meta}


def tree(locator, pattern, matches, **meta):
    return {"kind": "file_artifact", "locator": locator, "stimulus": {"grep": pattern, "suffixes": [".py"]},
            "observable": {"matches": matches, "within_s": WINDOW}, "absence": "REQUIRES_SUBJECT", **meta}


def present(path, **meta):
    return {"kind": "file_artifact", "locator": f"path:{path}", "stimulus": {},
            "observable": {"condition": "exists", "within_s": WINDOW}, "absence": "ABSENCE_IS_DECIDABLE", **meta}


def defined(name, **meta):
    return {"kind": "python_callable", "locator": f"ledgerlock.ledger:{name}", "stimulus": {},
            "observable": {"condition": "exists", "within_s": WINDOW}, "absence": "ABSENCE_IS_DECIDABLE", **meta}


def S(req, clause, story, q, measured, witness, **extra) -> dict:
    return {"requirement": req, "clause": clause, "story": story, "quantifier": q, "measured": measured,
            "witness": witness, "unmeasured": extra.pop("unmeasured", []), "note": extra.pop("note", ""), **extra}


ALLOWED = ("hashlib", "json", "os", "sys", "pathlib", "tempfile", "argparse", "unittest", "typing", "unicodedata", "uuid",
           "__future__", "ledgerlock")
#: an import statement whose first named module is outside §10's allowed set (a relative import is the package's own)
IMPORT_OUTSIDE = r"^\s*(?:import|from)\s+(?!(?:" + "|".join(ALLOWED) + r")\b|\.)[A-Za-z_]"
TREE_ALL = "every .py file of the package tree at the revision is scanned: the domain is finite and read entirely"
IMPORT_LIMIT = ("an import statement is inspected on its first named module: a second module of a comma list, and a "
                "dynamic __import__ / importlib call, escape the pattern")

# --------------------------------------------------------------------------------------- the retained ProductProofSpecs

SPECS: dict[str, dict] = {
    # §3.1
    "S-3.1-a": {**eff([NEW, batch(put(NFD_E, 1, "r1", 1))], field(0, "key", NFC_E)),
                **S("R-3.1", "R-3.1/1", "STORY-03-01", BW, "the key of the stored line is the NFC form of an NFD key",
                    "one NFD key (e + U+0301)")},
    "S-3.1-b": {**eff([NEW, batch(put(NFC_E, 1, "r1", 1)), refuse(put(NFD_E, 2, "r2", 2))], {"raises": True}),
                **S("R-3.1", "R-3.1/2", "STORY-03-01", BW, "an NFD spelling of an NFC-committed key is the same key: "
                    "another rid on it raises ConflictError", "the pair U+00E9 / e + U+0301")},
    "S-3.1-c": {**eff([NEW, batch(put(NFC_E, "v1", "r1", 1)), batch(put(NFD_E, "v2", "r1", 2))], count(1)),
                **S("R-3.1", "R-3.1/2", "STORY-03-01", BW, "the NFD spelling with the committed rid is a replay of the "
                    "NFC-committed key: no line is appended", "the pair U+00E9 / e + U+0301 under one rid")},
    # §3.2
    "S-3.2-a": {**eff([NEW, batch(put("a", 1, "r1", 1)), batch(put("b", 2, "r2", 2)), cli_step("verify", L, code=0)], count(2)),
                **S("R-3.2", "R-3.2/3", "STORY-04-01", BW, "a chain the product wrote in two batches links (the second "
                    "batch's line to the stored tail) as its own verify checks: `verify` exits 0",
                    "a two-line chain from two calls", note="the link is observed through the product's full verify "
                    "(§3.3): no observable compares two fields, and the hash value depends on the open canonical bytes")},
    "S-3.2-b": {**eff([NEW, batch(put("a", 1, "r1", 1)), batch(put("b", 2, "r2", 2))], count(2)),
                **S("R-3.2", "R-3.2/5", "STORY-03-01", BW, "a second batch appends: the committed line stays, two lines",
                    "two single-put batches")},
    "S-3.2-c": {**eff([NEW, batch(put("a", 1, "r1", 1)), batch(put("b", 2, "r2", 2))], field(0, "id", "r1")),
                **S("R-3.2", "R-3.2/5", "STORY-03-01", BW, "the committed record is not rewritten out of place: line 0 "
                    "is still the first mutation", "two single-put batches")},
    "S-3.2-d": {**eff([NEW, batch(put("k", {"v": 1}, "r1", 100))], field(0, "op", "put")),
                **S("R-3.2", "R-3.2/1", "STORY-03-01", BW, "the stored line's op is \"put\"", "one put")},
    "S-3.2-e": {**eff([NEW, batch(put("k", {"v": 1}, "r1", 100))], field(0, "value", {"v": 1})),
                **S("R-3.2", "R-3.2/1", "STORY-03-01", BW, "the stored line's value is the JSON value put", "one put")},
    "S-3.2-f": {**eff([NEW, batch(put("k", {"v": 1}, "r1", 100))], field(0, "ts", 100)),
                **S("R-3.2", "R-3.2/1", "STORY-03-01", BW, "the stored line's ts is the integer given", "one put")},
    "S-3.2-g": {**eff([NEW, batch(put("k", {"v": 1}, "r1", 100))], field(0, "id", "r1")),
                **S("R-3.2", "R-3.2/1", "STORY-03-01", BW, "the stored line's id is the rid given", "one put")},
    "S-3.2-h": {**eff([NEW, batch(put("a", 1, "r1", 1), put("b", 2, "r2", 2))], {"files": {L: {"final_byte": "\n"}}}),
                **S("R-3.2", "R-3.2/1", "STORY-03-01", BW, "every stored line is newline-terminated: the ledger's last "
                    "byte is a newline", "a two-put batch")},
    # §3.3 (the verdict through the CLI's exit code, §9: 0 intact, 5 corrupt)
    "S-3.3-a": {**eff([NEW, batch(*THREE), edit(1, "value", 20), cli_step("verify", L, code=5)], count(3)),
                **S("R-3.3", "R-3.3/1", "STORY-04-02", BW, "a mutated value on a committed line is detected: `verify` "
                    "exits 5", "a three-line chain, line 1's value changed on disk",
                    unmeasured=["first_bad_index (R-3.3/3: the verdict's representation is open)"])},
    "S-3.3-b": {**eff([NEW, batch(*THREE), edit(1, "op", "delete"), cli_step("verify", L, code=5)], count(3)),
                **S("R-3.3", "R-3.3/1", "STORY-04-02", BW, "a swapped op on a committed line is detected: `verify` exits 5",
                    "a three-line chain, line 1's op changed on disk")},
    "S-3.3-c": {**eff([NEW, batch(*THREE), edit(2, "hash", "0" * 64), cli_step("verify", L, code=5)], count(3)),
                **S("R-3.3", "R-3.3/1", "STORY-04-02", BW, "a modified hash is detected by recomputation: `verify` "
                    "exits 5", "a three-line chain, the LAST line's hash changed (no later link could reveal it)")},
    "S-3.3-d": {**eff([NEW, batch(*THREE), edit(1, "prev_hash", "f" * 64), cli_step("verify", L, code=5)], count(3)),
                **S("R-3.3", "R-3.3/2", "STORY-04-02", BW, "a prev_hash that is not the previous line's stored hash is "
                    "detected: `verify` exits 5", "a three-line chain, line 1's prev_hash changed (its own hash still "
                    "matches its content)")},
    # §3.4
    "S-3.4-a": {**eff([NEW, batch(*THREE), call("verify", as_="before"), edit(1, "value", 20), call("verify", as_="after")],
                      SAME), "polarity": "MUST_NOT_HOLD", "states": "forbidden",
                **S("R-3.4", "R-3.4/1", "STORY-03-01", BW, "the verdict of the SAME instance after an on-disk change is "
                    "not the verdict it gave before: verify reads the disk, not what the instance remembers",
                    "an instance that wrote the chain, one value changed on disk between its two verify calls",
                    note="MUST_NOT_HOLD over the equality of the two verdicts (the forbidden behaviour: equal verdicts); "
                         "representation-agnostic among JSON-shaped verdicts. Caveat: a scenario that fails before its "
                         "comparison also satisfies a MUST_NOT_HOLD contract; the pristine reference and the witness "
                         "complete every step")},
    # §4
    "S-4.2-a": {**eff([NEW, batch(put("k", "v1", "r1", 100)), batch(put("k", "anything", "r1", 999))], count(1)),
                **S("R-4.2", "R-4.2/1", "STORY-03-01", BW, "a replayed rid (another value and ts) appends no line",
                    "one replay", unmeasured=["the replay returns the same result (R-4.2/2)"])},
    "S-4.2-b": {**eff([NEW, batch(put("k", "v1", "r1", 100)), batch(put("k", "v2", "r1", 200), put("k2", 2, "r2", 201))],
                      count(2)),
                **S("R-4.2", "R-4.2/1", "STORY-03-01", BW, "a replayed element inside a batch appends nothing; the "
                    "batch's new element appends one line", "a two-element batch whose first element replays")},
    "S-4.3-a": {**eff([NEW, batch(put("k", "v1", "r1", 100)), refuse(put("k", "v2", "r2", 200))], {"raises": True}),
                **S("R-4.3", "R-4.3/1", "STORY-03-01", BW, "another rid on a committed key raises ConflictError",
                    "one conflicting put", unmeasured=["the error's attributes (not in the requirements)"])},
    "S-4.3-b": {**eff([NEW, batch(put("k", "v1", "r1", 100)), refuse(put("k", "v2", "r2", 200))], count(1)),
                **S("R-4.3", "R-4.3/2", "STORY-03-01", BW, "the conflicting mutation appends no line",
                    "one conflicting put")},
    "S-4.4-a": {**eff([NEW, batch(dele("k", "r1", 100)), refuse(put("k", "v", "r2", 200))], {"raises": True}),
                **S("R-4.4", "R-4.4/1", "STORY-03-01", BW, "a put with another rid after a tombstone raises ConflictError",
                    "a tombstone on a never-mutated key, then a put")},
    "S-4.4-b": {**eff([NEW, batch(dele("k", "r1", 100)), batch(put("k", "v", "r1", 200))], count(1)),
                **S("R-4.4", "R-4.4/2", "STORY-03-01", BW, "a put with the tombstone's rid is a no-op: no line",
                    "a tombstone, then a put under its rid",
                    unmeasured=["the result equals the delete's result (R-4.2/2: representation open)"])},
    "S-4.5-a": {**eff([NEW, batch(put("k", "v", "r1", 100)), refuse(dele("k", "r2", 200))], {"raises": True}),
                **S("R-4.5", "R-4.5/1", "STORY-03-01", BW, "a delete with another rid after a put raises ConflictError",
                    "a put, then a delete")},
    "S-4.5-b": {**eff([NEW, batch(put("k", "v", "r1", 100)), refuse(dele("k", "r2", 200)), batch(put("k", "v", "r1", 300))],
                      count(1)),
                **S("R-4.5", "R-4.5/2", "STORY-03-01", BW, "after the refused delete, a replay of the put does not "
                    "conflict and appends nothing", "a put, a refused delete, the put replayed")},
    # §5
    "S-5-a": {**eff([NEW, batch(put("k", "v1", "r1", 100)), refuse(put("k2", 2, "r2", 101), put("k", "v2", "r3", 102))], count(1)),
              **S("R-5", "R-5/3", "STORY-03-01", BW, "a batch refused at its second element commits nothing, not even "
                  "its acceptable first element: one line", "a committed key, then a batch whose second element conflicts "
                  "with it (a conflict against a COMMITTED mutation: RISK-10 leaves conflicts between two elements of one "
                  "batch open)", unmeasured=["the refusal's error attributes (not in the requirements)"])},
    "S-5-b": {**eff([NEW, batch(*THREE)], count(3)),
              **S("R-5", "R-5/3", "STORY-03-01", BW, "an accepted batch commits every element: three lines",
                  "a three-put batch on a fresh ledger")},
    # §6
    "S-6-a": {**eff([NEW, batch(put("b", 2, "r2", 2), put("a", 1, "r1", 1)), call("snapshot", as_="before"),
                     call("snapshot", as_="after")], SAME),
              **S("R-6", "R-6/1", "STORY-03-01", BW, "two snapshots of one chain are equal (byte-stable)",
                  "two calls on one instance",
                  note="the two results are compared as the probe reports them (bytes as hex, a str or a JSON value): "
                       "representation-agnostic among the forms a JSON document can take")},
    "S-6-b": {**eff([NEW, batch(put("k", "v", "r1", 1)), call("snapshot", as_="before"), refuse(dele("k", "r2", 2)),
                     call("snapshot", as_="after")], SAME),
              **S("R-6", "R-6/2", "STORY-03-01", BW, "a refused delete does not change the materialised state",
                  "a put, a snapshot, a refused delete, a snapshot")},
    "S-6-c": {**eff([NEW, batch(put("a", 1, "r1", 1)), call("snapshot", as_="before"), batch(dele("k2", "r3", 3)),
                     call("snapshot", as_="after")], SAME),
              **S("R-6", "R-6/2", "STORY-03-01", BW, "a tombstone on a never-mutated key leaves the materialised state "
                  "unchanged (the key does not appear)", "a put, a snapshot, a tombstone on another key, a snapshot")},
    "S-6-d": {"kind": "cli_invocation", "locator": MAIN, "stimulus": {}, "absence": "REQUIRES_SUBJECT",
              "observable": {"equality": {"stimulus_a": {"argv": ["snapshot", L], "workspace": {"l.jsonl": {"bytes_hex": ""}}},
                                          "stimulus_b": {"argv": ["snapshot", L], "workspace": {"l.jsonl": {"bytes_hex": ""}}},
                                          "normalization": {}, "comparator": "bytes_equal"},
                             "streams": ["stdout"], "within_s": WINDOW},
              **S("R-6", "R-6/1", "STORY-04-01", BW, "`snapshot <ledger>` produces the same bytes in two independent "
                  "invocations (§14 item 2)", "two invocations over an empty ledger, each in a fresh evaluation "
                  "directory (DECISION-4)")},
    # §7 (the CLI repair-tail, §7 and §14 item 4)
    "S-7-a": {**eff([NEW, batch(put("a", 1, "r1", 1), put("b", 2, "r2", 2)),
                     {"step": "write", "path": L, "bytes_hex": TRUNC.hex(), "append": True}, cli_step("repair-tail", L, code=0)],
                    count(2)),
              **S("R-7", "R-7/1", "STORY-04-01", BW, "repair-tail removes the truncated final line: two lines remain",
                  "a two-line chain the product wrote, then an unterminated line that does not parse",
                  unmeasured=["the preserved lines' bytes (R-7/2: the harness does not know the bytes the product wrote)"])},
    "S-7-b": {**eff([NEW, batch(put("a", 1, "r1", 1), put("b", 2, "r2", 2)),
                     {"step": "write", "path": L, "bytes_hex": TRUNC.hex(), "append": True}, cli_step("repair-tail", L, code=0),
                     cli_step("verify", L, code=0)], count(2)),
              **S("R-7", "R-7/1", "STORY-04-01", BW, "after repair-tail the chain verifies: `verify` exits 0",
                  "as S-7-a, then verify")},
    "S-7-c": {**eff([NEW, batch(put("a", 1, "r1", 1), put("b", 2, "r2", 2)),
                     {"step": "write", "path": L, "bytes_hex": TRUNC.hex(), "append": True}, cli_step("repair-tail", L, code=0)],
                    {"files": {L: {"final_byte": "\n"}}}),
              **S("R-7", "R-7/1", "STORY-04-01", BW, "after repair-tail the ledger ends with a newline (only complete "
                  "lines remain)", "as S-7-a")},
    "S-7-d": {**cli(["repair-tail", L], {"exit_code": 0, "files": {L: {"equals_before": True}}}, ledger=b""),
              **S("R-7", "R-7/3", "STORY-04-01", BW, "repair-tail on a clean chain is a no-op: exit 0, the ledger "
                  "byte-identical", "the empty (clean) chain",
                  unmeasured=["a non-empty clean chain byte-identical (only the product knows its bytes)"])},
    "S-7-e": {**cli(["repair-tail", L], {"exit_code": 5}, ledger=BOGUS[0] + BOGUS[1] + TRUNC),
              **S("R-7", "R-7/4", "STORY-04-02", BW, "repair-tail refuses mid-chain corruption: exit 5 (§9)",
                  "line 0 corrupt (its hash is wrong under any encoding), a later line, a truncated tail")},
    "S-7-f": {**cli(["repair-tail", L], {"exit_code": 5, "files": {L: {"equals_before": True}}}, ledger=BOGUS[0] + BOGUS[1] + TRUNC),
              **S("R-7", "R-7/4", "STORY-04-02", BW, "the refusal modifies nothing: the ledger is byte-identical",
                  "as S-7-e")},
    # §9
    "S-9-a": {**cli(["verify", L], {"exit_code": 0}, ledger=b""),
              **S("R-9", "R-9/0", "STORY-04-01", BW, "`verify` of a fresh (empty) ledger exits 0 (§14 item 1)",
                  "a zero-byte ledger")},
    "S-9-b": {**cli(["verify"], {"exit_code": 2}),
              **S("R-9", "R-9/2", "STORY-01-01", BW, "a missing required argument is a usage error: exit 2",
                  "`verify` without its ledger argument")},
    "S-9-c": {**cli(["verify", L, "extra"], {"exit_code": 2}, ledger=b""),
              **S("R-9", "R-9/2", "STORY-01-01", BW, "an extra positional argument is a usage error: exit 2",
                  "`verify <ledger> extra`")},
    "S-9-d": {**cli(["verify", "<ws>/missing.jsonl"], {"exit_code": 3}),
              **S("R-9", "R-9/3", "STORY-04-02", BW, "a ledger file that does not exist is an I/O error: exit 3",
                  "`verify` of a missing file")},
    "S-9-e": {**cli(["apply", "--batch", "<ws>/missing.json", L], {"exit_code": 3}, ledger=b""),
              **S("R-9", "R-9/3", "STORY-04-02", BW, "a batch file that does not exist is an I/O error: exit 3",
                  "`apply --batch` of a missing file (no batch-file shape is needed)")},
    "S-9-f": {**cli(["verify", L], {"exit_code": 5}, ledger=BOGUS[0]),
              **S("R-9", "R-9/5", "STORY-04-02", BW, "`verify` of a corrupt chain exits 5",
                  "one line whose hash is wrong under any encoding")},
    # §10
    "S-10-a": {**tree("path:ledgerlock", IMPORT_OUTSIDE, 0),
               **S("R-10", "R-10/1", "STORY-01-01", EX, "no import statement of the package names a module outside the "
                   "allowed set (§10)", TREE_ALL, unmeasured=[IMPORT_LIMIT])},
    "S-10-b": {**tree("path:ledgerlock/ledger.py", r"^from __future__ import annotations\b", 1),
               **S("R-10", "R-10/2", "STORY-01-01", EX, "ledger.py uses `from __future__ import annotations`",
                   "the file ledgerlock/ledger.py", note="the reference acceptance (A-10-a) requires it of ledger.py and cli.py")},
    "S-10-c": {**tree("path:ledgerlock/cli.py", r"^from __future__ import annotations\b", 1),
               **S("R-10", "R-10/2", "STORY-01-01", EX, "cli.py uses `from __future__ import annotations`",
                   "the file ledgerlock/cli.py")},
    # §12
    "S-12-a": {**tree("path:ledgerlock", r"^\s*(?:import\s+socket\b|from\s+socket\b)|\bsocket\.\w", 0),
               **S("R-12", "R-12/1", "STORY-01-01", EX, "no socket in the package source", TREE_ALL)},
    "S-12-b": {**tree("path:ledgerlock", r"^\s*(?:import\s+subprocess\b|from\s+subprocess\b)|\bsubprocess\.\w", 0),
               **S("R-12", "R-12/1", "STORY-01-01", EX, "no subprocess in the package source", TREE_ALL)},
    "S-12-c": {**tree("path:ledgerlock", r"\bos\.system\s*\(", 0),
               **S("R-12", "R-12/1", "STORY-01-01", EX, "no os.system in the package source", TREE_ALL)},
    # §13
    "S-13-a": {**present("ledgerlock/__init__.py"), **S("R-13", "R-13/1", "STORY-01-01", EX, "ledgerlock/__init__.py exists", "the path")},
    "S-13-b": {**present("ledgerlock/ledger.py"), **S("R-13", "R-13/1", "STORY-01-01", EX, "ledgerlock/ledger.py exists", "the path")},
    "S-13-c": {**present("ledgerlock/cli.py"), **S("R-13", "R-13/1", "STORY-01-01", EX, "ledgerlock/cli.py exists", "the path")},
    "S-13-d": {**defined("Ledger"), **S("R-13", "R-13/2", "STORY-01-01", EX, "ledger.py defines Ledger", "the name")},
    "S-13-e": {**defined("ConflictError"), **S("R-13", "R-13/2", "STORY-01-01", EX, "ledger.py defines ConflictError", "the name")},
    "S-13-f": {**defined("append"), **S("R-13", "R-13/2", "STORY-01-05", EX, "ledger.py defines append", "the name")},
    "S-13-g": {**defined("verify"), **S("R-13", "R-13/2", "STORY-02-01", EX, "ledger.py defines verify", "the name")},
    "S-13-h": {**defined("snapshot"), **S("R-13", "R-13/2", "STORY-02-02", EX, "ledger.py defines snapshot", "the name")},
    "S-13-i": {**defined("apply_batch"), **S("R-13", "R-13/2", "STORY-03-01", EX, "ledger.py defines apply_batch", "the name")},
    # DECISION-3 behavioural mappings (proposals; PRESERVE in STORY-05-01)
    "S-D3-05-01-1": {**eff([NEW, batch(put("a", 1, "s1", 1)), batch(put("b", 2, "s2", 2)), batch(put("a", 1, "s1", 3)),
                            batch(dele("d", "s5", 4)), batch(put("c", [1, 2], "s3", 5)), batch(put(NFD_E, "x", "s4", 6)),
                            batch(put(NFC_E, "y", "s4", 7)), batch(dele("b", "s2", 8)), cli_step("verify", L, code=0)], count(5)),
                     **S("R-3.3", "R-3.3/2", "STORY-05-01", BW, "after a fixed conflict-free sequence of mutations (puts, "
                         "a tombstone, replays, an NFD/NFC replay) the chain the product wrote verifies (`verify` exits 0) "
                         "and holds exactly the five committed lines", "one fixed eight-call sequence (nothing random at "
                         "evaluation) stands for the property test's seeded sequences", role="PRESERVE",
                         clauses_also=["R-4.2/1", "R-4.4/2"],
                         unmeasured=["two snapshot() calls equal after each sequence (S-6-a measures snapshot stability)"])},
    "S-D3-05-01-2": {**eff([NEW, batch(put("a", 1, "s1", 1), put("b", 2, "s2", 2)), refuse(dele("a", "s9", 10))], count(2)),
                     **S("R-5", "R-4.3/2", "STORY-05-01", BW, "a sequence whose element conflicts leaves the ledger as the "
                         "prefix committed it: two lines", "a two-element prefix, then a delete of 'a' under another rid",
                         role="PRESERVE")},
}

# --------------------------------------------------------------------------------------- the frozen requirement clauses

CLAUSES: list[dict] = [
    {"id": "R-1/1", "requirement": "R-1", "clause": "purpose", "class": D, "specs": [], "reason": "descriptive; the behaviours are R-3..R-9"},
    {"id": "R-2/1", "requirement": "R-2", "clause": "non-goals (no network listener, database, client/server, third-party deps)", "class": D,
     "specs": [], "reason": "descriptive; the side-channel half is measured under R-12, the dependency half under R-10"},
    {"id": "R-3.1/1", "requirement": "R-3.1", "clause": "all keys are normalized to Unicode NFC before storage, lookup, hashing, serialization",
     "class": N, "specs": ["S-3.1-a"]},
    {"id": "R-3.1/2", "requirement": "R-3.1", "clause": "strings differing only in NFC/NFD are the same key", "class": N,
     "specs": ["S-3.1-b", "S-3.1-c"]},
    {"id": "R-3.2/1", "requirement": "R-3.2", "clause": "a single JSONL file; each line {op, key <nfc>, value, ts <int>, id <rid>}", "class": N,
     "specs": ["S-3.2-d", "S-3.2-e", "S-3.2-f", "S-3.2-g", "S-3.2-h"]},
    {"id": "R-3.2/2", "requirement": "R-3.2", "clause": "hash = SHA-256(prev_hash || '|' || canonical_bytes), hash fields emptied", "class": U,
     "specs": [], "reason": "the canonical bytes encoding is not fixed: no harness can recompute a hash value independently; the "
                            "product's own consistency is observed through its verify (S-3.2-a, S-3.3-*)"},
    {"id": "R-3.2/3", "requirement": "R-3.2", "clause": "prev_hash of the next line = this hash", "class": N, "specs": ["S-3.2-a"],
     "note": "observed through the product's full verify; no observable compares two fields of a file"},
    {"id": "R-3.2/4", "requirement": "R-3.2", "clause": "first prev_hash is 'GENESIS' or 64 zeros, an implementation choice, documented and constant",
     "class": U, "specs": [], "reason": "a disjunctive expected value: every file shape compares one value; fixing one form "
                                        "would enforce a stronger property than the requirement (OD-STRONGER)"},
    {"id": "R-3.2/5", "requirement": "R-3.2", "clause": "append-only: existing records MUST NOT be rewritten in place", "class": N,
     "specs": ["S-3.2-b", "S-3.2-c"]},
    {"id": "R-3.3/1", "requirement": "R-3.3", "clause": "a mutated value, swapped op or modified hash on a committed line is detected by a full verify",
     "class": N, "specs": ["S-3.3-a", "S-3.3-b", "S-3.3-c"]},
    {"id": "R-3.3/2", "requirement": "R-3.3", "clause": "ok iff every recomputed hash matches AND every prev_hash matches the previous stored hash",
     "class": N, "specs": ["S-3.2-a", "S-3.3-d", "S-D3-05-01-1"]},
    {"id": "R-3.3/3", "requirement": "R-3.3", "clause": "ok=False and first_bad_index=<i> on the first violation", "class": U, "specs": [],
     "reason": "the verdict's representation is open (the CLI exposes the exit code only); no class reads one field of an "
               "arbitrary returned object; a fixed-shape comparison would prescribe a representation (OD-02-01-4)"},
    {"id": "R-3.4/1", "requirement": "R-3.4", "clause": "verify reads no in-memory state set by append; recomputes from disk, CLI or library",
     "class": N, "specs": ["S-3.4-a"]},
    {"id": "R-4.1/1", "requirement": "R-4.1", "clause": "a rid is a non-empty UTF-8 string supplied by the caller", "class": D, "specs": [],
     "reason": "a definition of the caller's input; the requirements prescribe no behaviour for a violation (the reference's "
               "refusal of an empty rid is its interpretation)"},
    {"id": "R-4.2/1", "requirement": "R-4.2", "clause": "a replayed rid MUST NOT append a new line", "class": N,
     "specs": ["S-4.2-a", "S-4.2-b", "S-3.1-c", "S-4.4-b", "S-4.5-b"]},
    {"id": "R-4.2/2", "requirement": "R-4.2", "clause": "the second call MUST return the same result", "class": U, "specs": [],
     "reason": "the result's representation is open; the only comparator of two results needs a JSON form, which would "
               "prescribe one (OD-RETURN)"},
    {"id": "R-4.3/1", "requirement": "R-4.3", "clause": "another rid on a key last mutated by another rid MUST raise ConflictError", "class": N,
     "specs": ["S-4.3-a", "S-3.1-b"]},
    {"id": "R-4.3/2", "requirement": "R-4.3", "clause": "... and MUST NOT append a new line", "class": N, "specs": ["S-4.3-b", "S-D3-05-01-2"]},
    {"id": "R-4.3/3", "requirement": "R-4.3", "clause": "or return an error result depending on CLI surface (exit 4, §9)", "class": U, "specs": [],
     "reason": "the only mutating CLI invocation is `apply --batch <file>`, whose file shape the requirements do not fix (OD-BATCH)"},
    {"id": "R-4.4/1", "requirement": "R-4.4", "clause": "a put with another rid after a tombstone MUST conflict", "class": N, "specs": ["S-4.4-a"]},
    {"id": "R-4.4/2", "requirement": "R-4.4", "clause": "a put with the tombstone's rid is a no-op replay", "class": N, "specs": ["S-4.4-b"]},
    {"id": "R-4.4/3", "requirement": "R-4.4", "clause": "... returning the same result as the delete", "class": U, "specs": [],
     "reason": "as R-4.2/2 (OD-RETURN)"},
    {"id": "R-4.5/1", "requirement": "R-4.5", "clause": "put k r1 then delete k r2: the second MUST conflict", "class": N, "specs": ["S-4.5-a", "S-6-b"]},
    {"id": "R-4.5/2", "requirement": "R-4.5", "clause": "replays of either MUST NOT conflict", "class": N, "specs": ["S-4.5-b"]},
    {"id": "R-5/0", "requirement": "R-5", "clause": "apply_batch runs 'under the lock'", "class": U, "specs": [],
     "reason": "the requirements define no lock and nothing observable depends on one"},
    {"id": "R-5/1", "requirement": "R-5", "clause": "apply_batch writes all lines to a sibling temp file, fsyncs it, renames it over the path",
     "class": U, "specs": [], "reason": "the mechanism is not observable by any class (no step traces the subject's own files)"},
    {"id": "R-5/2", "requirement": "R-5", "clause": "a crash at any point leaves the full batch or the pre-batch bytes, never a partial batch",
     "class": U, "specs": [], "reason": "a fault step makes the faulted call either return (call) or raise (expect_raises); the "
                                       "requirements fix neither, only the post-crash state, and a fault the implementation "
                                       "does not use (os.replace vs os.rename) never fires (OD-03-01-5)"},
    {"id": "R-5/3", "requirement": "R-5", "clause": "all or nothing without a crash: a refused batch commits nothing; an accepted one every element",
     "class": N, "specs": ["S-5-a", "S-5-b"]},
    {"id": "R-5/4", "requirement": "R-5", "clause": "the CLI `apply --batch <file>` performs the same atomic operation", "class": U, "specs": [],
     "reason": "the batch-file shape is not fixed (OD-BATCH); the file-absent I/O error is measured (S-9-e)"},
    {"id": "R-6/1", "requirement": "R-6", "clause": "the snapshot is deterministic, byte-stable for a given chain", "class": N,
     "specs": ["S-6-a", "S-6-d"]},
    {"id": "R-6/2", "requirement": "R-6", "clause": "the materialised state: each key's most recent committed put unless tombstoned", "class": N,
     "specs": ["S-6-b", "S-6-c"], "note": "measured relationally (a refused delete and a tombstone leave the state unchanged)"},
    {"id": "R-6/3", "requirement": "R-6", "clause": "sorted by NFC key in UTF-8 byte order; a JSON document", "class": U, "specs": [],
     "reason": "the document's layout and representation are open: its content and key order are observable only through "
               "bytes or a representation no requirement fixes"},
    {"id": "R-6/4", "requirement": "R-6", "clause": "the CLI `snapshot --out <file>` writes this same document", "class": U, "specs": [],
     "reason": "no class compares a written file with a library value, and the file's bytes are layout-open"},
    {"id": "R-7/1", "requirement": "R-7", "clause": "a truncated final line is removed and the chain verifies cleanly afterwards", "class": N,
     "specs": ["S-7-a", "S-7-b", "S-7-c"]},
    {"id": "R-7/2", "requirement": "R-7", "clause": "no other content may be modified", "class": U, "specs": [],
     "reason": "the preserved lines were written by the product: their bytes are unknown to the harness (S-7-a measures that "
               "they remain)"},
    {"id": "R-7/3", "requirement": "R-7", "clause": "on a clean chain repair-tail is a no-op", "class": N, "specs": ["S-7-d"]},
    {"id": "R-7/4", "requirement": "R-7", "clause": "on mid-chain corruption repair-tail MUST refuse", "class": N, "specs": ["S-7-e", "S-7-f"]},
    {"id": "R-8/1", "requirement": "R-8", "clause": "after a successful append the bytes are durably on disk (fsync) before return", "class": U,
     "specs": [], "reason": "durability is not observable from outside the process (the reference fixture treats R-8 as static)"},
    {"id": "R-9/0", "requirement": "R-9", "clause": "exit 0 on success", "class": N, "specs": ["S-9-a", "S-3.2-a", "S-7-a", "S-7-d"]},
    {"id": "R-9/2", "requirement": "R-9", "clause": "exit 2 on a usage error", "class": N, "specs": ["S-9-b", "S-9-c"]},
    {"id": "R-9/3", "requirement": "R-9", "clause": "exit 3 on an I/O error", "class": N, "specs": ["S-9-d", "S-9-e"]},
    {"id": "R-9/4", "requirement": "R-9", "clause": "exit 4 on a conflict", "class": U, "specs": [], "reason": "as R-4.3/3 (OD-BATCH)"},
    {"id": "R-9/5", "requirement": "R-9", "clause": "exit 5 on corruption (verify not ok, repair-tail non-tail corruption)", "class": N,
     "specs": ["S-9-f", "S-3.3-a", "S-3.3-b", "S-3.3-c", "S-3.3-d", "S-7-e"]},
    {"id": "R-10/1", "requirement": "R-10", "clause": "stdlib only; the allowed modules", "class": N, "specs": ["S-10-a"]},
    {"id": "R-10/2", "requirement": "R-10", "clause": "use `from __future__ import annotations`", "class": N, "specs": ["S-10-b", "S-10-c"]},
    {"id": "R-10/3", "requirement": "R-10", "clause": "no pip install of a runtime dependency", "class": E, "specs": [],
     "reason": "an installation practice; its product consequence is R-10/1"},
    {"id": "R-10/4", "requirement": "R-10", "clause": "Python 3.11+ required", "class": E, "specs": [],
     "reason": "a property of the runtime environment the harness chooses, not of the product's behaviour"},
    {"id": "R-11/1", "requirement": "R-11", "clause": "unit tests, >=85% coverage, unittest/pytest agreement", "class": E, "specs": [],
     "reason": "DEVELOPER_TEST_REQUIREMENT: a requirement on the product's own tests, outside ProductProof by invariant IX; "
               "not satisfied by this classification"},
    {"id": "R-12/1", "requirement": "R-12", "clause": "no socket, no subprocess, no os.system", "class": N, "specs": ["S-12-a", "S-12-b", "S-12-c"]},
    {"id": "R-12/2", "requirement": "R-12", "clause": "no opening of files outside the ledger, batch and snapshot paths", "class": U, "specs": [],
     "reason": "no class observes which files a subject opens"},
    {"id": "R-13/1", "requirement": "R-13", "clause": "ledgerlock/__init__.py, ledger.py, cli.py", "class": N, "specs": ["S-13-a", "S-13-b", "S-13-c"]},
    {"id": "R-13/2", "requirement": "R-13", "clause": "ledger.py: Ledger, ConflictError, append, verify, snapshot, apply_batch", "class": N,
     "specs": ["S-13-d", "S-13-e", "S-13-f", "S-13-g", "S-13-h", "S-13-i"]},
    {"id": "R-13/3", "requirement": "R-13", "clause": "tests/test_*.py, docs/requirements.md, README.md, pyproject.toml", "class": E, "specs": [],
     "reason": "repository deliverables: the developer's tests (R-11) and packaging/documentation files, not product behaviour; "
               "the reference fixture carries the package tree only"},
    {"id": "R-14/1", "requirement": "R-14", "clause": "acceptance items 1-6", "class": D, "specs": ["S-9-a", "S-6-d", "S-7-a", "S-10-a"],
     "reason": "a summary of R-3..R-12: item 1 S-9-a, 2 S-6-d, 3 R-5/4 (unsupported, OD-BATCH), 4 S-7-a, 5 R-11 (engineering), 6 S-10-a"},
]

# --------------------------------------------------------------------------------------- PLAN-V2.1's 77 criteria

def C(cls, specs=(), plan_only=(), unsupported=(), reason=""):
    return {"class": cls, "specs": list(specs), "plan_only": list(plan_only), "unsupported": list(unsupported), "reason": reason}


FMT = "the module ledgerlock.format and its functions are PLAN-V2.1 topology (§13 names ledger.py and cli.py only)"
STORE = "the module ledgerlock.store is PLAN-V2.1 topology (OD-STORE)"
TUPLE_API = "append((op, key, value, rid, ts)) as one tuple is PLAN-V2.1's signature"
RET = "the returned value's shape (OD-RETURN)"
SILENT = "silent stdout / stderr status lines are not in the requirements"
CRITERIA: dict[str, dict] = {
    "AC-STORY-01-01-1": C(N, ["S-3.1-a"], [FMT], [], "NFC normalization (R-3.1/1), observed on the stored line; 'any string' "
                                                     "is a bounded witness (DECISION-1)"),
    "AC-STORY-01-01-2": C(N, ["S-3.1-a", "S-3.1-b"], [FMT], [], "NFC/NFD are one key (R-3.1/2)"),
    "AC-STORY-01-01-3": C(N, ["S-13-a"], ["the pyproject.toml / empty tests/ givens (engineering scaffolding)"], [],
                          "the package's __init__.py (R-13/1)"),
    "AC-STORY-01-01-4": C(N, ["S-10-a", "S-12-a", "S-12-b"], ["the grep command form"], [],
                          "network and process modules are outside §10's allowed set; socket/subprocess (§12)"),
    "AC-STORY-01-01-5": C(N, ["S-12-a", "S-12-b", "S-12-c"], ["the grep command form"], [], "§12, split per prohibited name (OD-FACETS)"),
    "AC-STORY-01-01-6": C(N, ["S-13-d", "S-13-e"], ["the package-level re-export `from ledgerlock import`"], [],
                          "two independent names, two atomic contracts (OD-01-01-6)"),
    "AC-STORY-01-01-7": C(N, ["S-9-c"], [SILENT], [], "a usage error exits 2 (R-9/2)"),
    "AC-STORY-01-02-1": C(P, [], [FMT, "the exact canonical encoding json.dumps(sort_keys, compact, ensure_ascii=False)"], [],
                          "§3.2 leaves the canonical bytes open"),
    "AC-STORY-01-02-2": C(P, [], [FMT], [], "a property of a plan function; the chain's consistency is observed through verify (S-3.2-a)"),
    "AC-STORY-01-02-3": C(P, [], [FMT, "the UTF-8-literal encoding choice"], [], "encoding choice"),
    "AC-STORY-01-02-4": C(P, [], [FMT], [], "a property of a plan function (DECISION-4 criterion; OD-D4)"),
    "AC-STORY-01-02-5": C(P, [], [FMT, "the literal 'GENESIS' (the requirements allow it or 64 zeros)"], [], "OD-STRONGER"),
    "AC-STORY-01-02-6": C(P, [], [FMT], [], "a property of a plan function (DECISION-4 criterion; OD-D4)"),
    "AC-STORY-01-03-1": C(P, [], [FMT, "the digest's exact value / 64-lowercase-hex form"], [], "OD-STRONGER: the canonical bytes are open"),
    "AC-STORY-01-03-2": C(P, [], [FMT], [], "a property of a plan function (DECISION-4; OD-D4); linkage detection is S-3.3-d"),
    "AC-STORY-01-03-3": C(P, [], [FMT], [], "a property of a plan function"),
    "AC-STORY-01-03-4": C(P, [], [FMT], [], "a property of a plan function (DECISION-4; OD-D4)"),
    "AC-STORY-01-03-5": C(P, [], [FMT], [], "a property of a plan function"),
    "AC-STORY-01-04-1": C(P, [], [STORE], [], "OD-STORE"),
    "AC-STORY-01-04-2": C(N, ["S-9-d"], [STORE], [], "a missing ledger file is an I/O error (R-9/3)"),
    "AC-STORY-01-04-3": C(N, ["S-9-a"], [STORE], [], "an empty file is an empty (valid) chain (R-3.3, R-9/0)"),
    "AC-STORY-01-04-4": C(P, [], [STORE], [], "OD-STORE"),
    "AC-STORY-01-04-5": C(U, [], [STORE], ["R-5/2 crash atomicity (DECISION-2 fault; OD-03-01-5)"], "the post-crash state cannot be "
                          "observed without fixing how the crash surfaces"),
    "AC-STORY-01-04-6": C(U, [], [STORE], ["R-5/1 the sibling temp file"], "the mechanism is not observable"),
    "AC-STORY-01-05-1": C(N, ["S-3.2-d", "S-3.2-e", "S-3.2-f", "S-3.2-g", "S-3.2-h", "S-3.1-a"], [TUPLE_API],
                          ["R-3.2/4 the GENESIS form", "R-3.2/2 the hash value"], "the stored line's fields (R-3.2/1)"),
    "AC-STORY-01-05-2": C(N, ["S-3.2-a"], [TUPLE_API], ["R-3.2/2 the hash value"], "linkage (R-3.2/3) through verify"),
    "AC-STORY-01-05-3": C(P, [], ["an empty key raising ValueError: the requirements say nothing about empty keys"], [], ""),
    "AC-STORY-01-05-4": C(N, ["S-3.2-a"], [TUPLE_API], ["a second, fresh instance (one construct per scenario; a harness-written "
                                                      "chain presumes the canonical encoding)"], "the tail link (R-3.2/3, R-3.4)"),
    "AC-STORY-01-05-5": C(N, ["S-3.2-h", "S-3.2-a"], [TUPLE_API], ["R-8/1 durability"], "the line is visible to a separate process "
                          "(the CLI verify) and newline-terminated"),
    "AC-STORY-01-06-1": C(N, ["S-4.2-a"], [TUPLE_API, RET], ["R-4.2/2 the same result"], "replay appends nothing (R-4.2/1)"),
    "AC-STORY-01-06-2": C(N, ["S-4.3-a", "S-4.3-b"], [TUPLE_API, "the ConflictError attributes key / incoming_rid / committed_rid / batch_index"],
                          [], "conflict raises and appends nothing (R-4.3/1, R-4.3/2)"),
    "AC-STORY-01-06-3": C(N, ["S-4.4-a"], [TUPLE_API], [], "R-4.4/1"),
    "AC-STORY-01-06-4": C(N, ["S-4.4-b"], [TUPLE_API, RET], ["R-4.4/3 the same result as the delete"], "R-4.4/2"),
    "AC-STORY-01-06-5": C(N, ["S-3.1-c"], [TUPLE_API, RET], [], "an NFD replay of an NFC rid appends nothing (R-3.1/2, R-4.2/1)"),
    "AC-STORY-02-01-1": C(N, ["S-3.2-a"], ["verify() returning the dict {ok, first_bad_index}"], [], "a product-written chain verifies"),
    "AC-STORY-02-01-2": C(N, ["S-9-a"], ["the dict return"], [], "an empty chain verifies"),
    "AC-STORY-02-01-3": C(N, ["S-9-d"], ["FileNotFoundError from the library"], [], "a missing ledger is an I/O error"),
    "AC-STORY-02-01-4": C(N, ["S-3.3-c"], ["the dict return"], ["R-3.3/3 first_bad_index (OD-02-01-4)"], "a modified hash is detected"),
    "AC-STORY-02-01-5": C(N, ["S-3.3-a"], ["the dict return"], ["R-3.3/3 first_bad_index"], "a mutated value is detected"),
    "AC-STORY-02-02-1": C(N, ["S-6-a"], [], ["R-6/3 key order"], "snapshot stability (DECISION-4 criterion rewritten at the "
                          "requirement level with an existing observable, OD-D4)"),
    "AC-STORY-02-02-2": C(N, ["S-4.5-a", "S-6-b"], [], ["R-6/3 the snapshot's content {k: v}"], "the refused delete conflicts and "
                          "changes nothing"),
    "AC-STORY-02-02-3": C(N, ["S-6-c"], [], ["R-6/3 content"], "a tombstone on a never-mutated key leaves the state unchanged"),
    "AC-STORY-02-02-4": C(N, ["S-3.1-a", "S-3.1-c"], [], ["R-6/3 the snapshot's content"], "NFC storage and the NFD/NFC replay"),
    "AC-STORY-02-02-5": C(N, ["S-6-a", "S-6-d"], [], ["two instances in one scenario (one construct)"], "determinism across calls "
                          "and across processes (DECISION-4; OD-D4)"),
    "AC-STORY-03-01-1": C(N, ["S-5-b", "S-3.2-a"], [], ["R-3.2/4 the GENESIS form"], "a batch commits every element and verifies"),
    "AC-STORY-03-01-2": C(N, ["S-4.2-b"], [], [], "a replay inside a batch"),
    "AC-STORY-03-01-3": C(N, ["S-5-a"], ["the ConflictError attributes", "a conflict between two elements of one batch (RISK-10: "
                          "R-4.3 judges against the last COMMITTED mutation)"], [], "a refused batch commits nothing"),
    "AC-STORY-03-01-4": C(N, ["S-4.3-a", "S-4.3-b"], ["batch_index 0"], [], "element 0 conflicts: raise, no line"),
    "AC-STORY-03-01-5": C(U, [], ["os.replace as the mechanism"], ["R-5/2 crash atomicity (DECISION-2; OD-03-01-5)"], ""),
    "AC-STORY-03-02-1": C(N, ["S-7-a", "S-7-b", "S-7-c"], ["the library method repair_tail() (§7 names the CLI)"],
                          ["R-7/2 byte identity of the preserved lines"], "three atomic clauses (OD-FACETS)"),
    "AC-STORY-03-02-2": C(N, ["S-7-d"], ["the library method"], [], "a clean chain is a no-op"),
    "AC-STORY-03-02-3": C(N, ["S-7-e", "S-7-f"], ["the library method"], ["R-3.3/3 the verdict names the corruption"],
                          "refusal: exit 5 and nothing modified (OD-REFUSE: the CLI's exit code is the requirement's refusal)"),
    "AC-STORY-03-02-4": C(U, [], ["the library method"], ["a terminated tail line whose hash is broken: the requirements define "
                          "truncation and mid-chain refusal only; every probe running repair-tail asserts an exit code the "
                          "requirements leave open for this case"], ""),
    "AC-STORY-04-01-1": C(P, [], ["`snapshot` without --out exiting 2 CONTRADICTS §14 item 2 (`snapshot <ledger>` is a documented invocation)"], [], ""),
    "AC-STORY-04-01-2": C(N, ["S-9-b", "S-9-c"], [SILENT], [], "a wrong positional count exits 2 (bounded witnesses)"),
    "AC-STORY-04-01-3": C(P, [], ["the --help output"], [], "not in the requirements"),
    "AC-STORY-04-01-4": C(N, ["S-9-a", "S-3.2-a"], [SILENT], [], "verify exits 0 on a fresh / product-written ledger"),
    "AC-STORY-04-01-5": C(U, [], ["the json.dumps byte form of the --out file"], ["R-6/4 the file equals the library document"], ""),
    "AC-STORY-04-01-6": C(U, [], [SILENT], ["R-5/4 the batch-file shape (OD-BATCH)"], ""),
    "AC-STORY-04-01-7": C(N, ["S-7-d"], [SILENT], [], "repair-tail on a clean chain: exit 0, byte-identical"),
    "AC-STORY-04-02-1": C(N, ["S-9-e"], [SILENT], [], "a missing batch file: exit 3"),
    "AC-STORY-04-02-2": C(U, [], [SILENT], ["R-9/4 exit 4 needs a batch file (OD-BATCH)"], ""),
    "AC-STORY-04-02-3": C(N, ["S-3.3-a", "S-9-f"], [SILENT, "'line 17'"], [], "verify of a corrupt chain exits 5"),
    "AC-STORY-04-02-4": C(N, ["S-7-e"], [SILENT, "'line 17'"], [], "repair-tail refuses mid-chain corruption: exit 5"),
    "AC-STORY-04-03-1": C(P, [], [SILENT], [], "DECISION-1 criterion; the stderr shape is not a requirement"),
    "AC-STORY-04-03-2": C(P, [], [SILENT], [], "DECISION-1 criterion"),
    "AC-STORY-04-03-3": C(P, [], [SILENT], [], "DECISION-1 criterion"),
    "AC-STORY-04-03-4": C(P, [], [SILENT], [], "DECISION-1 criterion"),
    "AC-STORY-04-03-5": C(P, [], [SILENT], [], "DECISION-1 criterion"),
    "AC-STORY-05-01-1": C(N, ["S-D3-05-01-1"], ["the property test as the subject (DECISION-3: engineering)"], [], "DECISION-3 mapping"),
    "AC-STORY-05-01-2": C(N, ["S-D3-05-01-2"], ["the property test as the subject"], [], "DECISION-3 mapping"),
    "AC-STORY-05-01-3": C(E, [], [], [], "unittest/pytest agreement of a test module (DECISION-3; R-11)"),
    "AC-STORY-05-02-1": C(E, [], [], [], "line coverage >= 85% (DECISION-3; R-11)"),
    "AC-STORY-05-02-2": C(E, [], [], [], "suite-level runner agreement (DECISION-3; R-11)"),
    "AC-STORY-05-02-3": C(E, [], [], [], "coverage configuration (DECISION-3; R-11)"),
    "AC-STORY-05-03-1": C(N, ["S-10-a", "S-12-a", "S-12-b"], ["'and the test passes' (engineering)"], [], "PRESERVE of 01-01-4"),
    "AC-STORY-05-03-2": C(N, ["S-12-a", "S-12-b", "S-12-c"], ["'and the test passes' (engineering)"], [], "PRESERVE of 01-01-5"),
}
#: PLAN-V2.1 criteria that contradict the frozen requirements (agreed with the LANE-P5C audit)
CONTRADICTS = {
    "AC-STORY-04-01-1": "R-14 item 2 documents `snapshot <ledger>` without --out as a successful invocation; the plan requires exit 2",
    "AC-STORY-04-03-3": "no stdout on every snapshot success path, while §14 item 2's form without --out produces the bytes (on stdout)",
    "AC-STORY-04-03-5": "as AC-STORY-04-03-3, for every success path",
    "AC-STORY-01-06-1": "a replay flagged replayed=True / committed=False is not 'the same result' as the first call (R-4.2)",
    "AC-STORY-01-06-4": "as AC-STORY-01-06-1, against 'returning the same result as the delete' (R-4.4)",
    "AC-STORY-01-06-5": "as AC-STORY-01-06-1",
    "AC-STORY-03-02-1": "truncation defined with OR (last byte not newline OR does not parse); §7 requires both, so an unterminated "
                        "but valid last record would be removed",
    "AC-STORY-03-02-4": "when the tampered last line is unterminated, §7 makes it a truncated line to remove; the plan requires no "
                        "modification",
    "AC-STORY-02-02-1": "if its single rid r is literal, only the first put commits under rid-keyed replay, so a, b, c cannot all appear",
}
#: risks in the frozen requirements themselves (LANE-P5C audit RISK-1..16, reviewed; the specs avoid each ambiguous case)
REQUIREMENT_RISKS = {
    "RISK-1": "a key with a committed put can never be deleted or changed (a same-rid delete replays, another rid conflicts): "
              "R-6's 'unless tombstoned by a later delete' is unreachable for a put key; tombstones exist only as a first mutation",
    "RISK-2": "R-4.5 'replays of either MUST NOT conflict' holds only for the committed put (S-4.5-b); the refused delete replayed "
              "is again another rid (R-4.3)",
    "RISK-3": "replay scope rid alone or rid+key: no spec reuses a rid across keys",
    "RISK-4": "'verify: any other exit code is a bug' vs 2 and 3; 'fresh ledger' consistent only as an existing empty file (IB-EMPTY)",
    "RISK-5": "'any modification detected' vs hashing canonical bytes: only semantic edits are testable (S-3.3-* edit value, op, hash, "
              "prev_hash)",
    "RISK-6": "the GENESIS form is both 'the literal' and an implementation choice (R-3.2/4 UNSUPPORTED)",
    "RISK-7": "§12 file confinement vs §5's sibling temp file (R-12/2 UNSUPPORTED)",
    "RISK-8": "'under the lock' is undefined (R-5/0 UNSUPPORTED)",
    "RISK-9": "a newline-terminated corrupt last line is neither truncated nor 'in the middle' (AC-STORY-03-02-4 UNSUPPORTED)",
    "RISK-10": "conflicts and replays between elements of one batch: R-4.3 judges against committed mutations (S-5-a conflicts "
               "against a committed line)",
    "RISK-11": "§10's allowed set omits __future__ (which §10 requires) and the package's own modules: S-10-a admits both",
    "RISK-12": "§3.2's line shapes omit hash and prev_hash, which every line carries",
    "RISK-13": "module functions vs methods; append/put/delete signatures and ts provenance open (IB-LEDGER, IB-ELEMENTS)",
    "RISK-14": "durability, crash atomicity, file confinement and the interpreter version are outside every probe",
    "RISK-15": "'0 — success (append …)' names a CLI append no clause specifies",
    "RISK-16": "'no third-party imports succeed at runtime' reads as an environment property (R-14 item 6 mapped to S-10-a)",
}
#: PLAN-level (level 4) changes: STORY-03-01 also depends on STORY-02-02, so the snapshot specs it owns can be met there
STORY_EDGES = {"STORY-03-01": ["STORY-02-02"]}

#: DECISION-3 (APPROVED_FOR_PROPOSAL_ONLY)
D3 = ("AC-STORY-05-01-1", "AC-STORY-05-01-2", "AC-STORY-05-01-3", "AC-STORY-05-02-1", "AC-STORY-05-02-2", "AC-STORY-05-02-3")

OWNER_RULINGS = {
    "OD-D4": "applied: 02-02-1 / 02-02-5 rewritten at the requirement level (S-6-a two calls, S-6-d two invocations); the "
             "format-module criteria are PLAN_ONLY_DETAIL; no probe added",
    "OD-GREP": "measured: MUST_NOT_HOLD of grep_count {matches: 0} is satisfied exactly when the observation is REFUTED — "
               "a count other than 0, OR a non-UTF-8 file (count unestablished) OR an expired window (and a file holding a NUL byte is skipped) — so it expresses "
               "'at least one match' only up to those two causes; not needed: §10/§12 state the prohibitions as absence, "
               "so the contracts are MUST_HOLD {matches: 0}, exact",
    "OD-RETURN": "applied: no return shape is prescribed; 'returns the same result' is UNSUPPORTED (R-4.2/2, R-4.4/3)",
    "OD-REFUSE": "applied: refusal is the CLI's exit 5 (§9) and the unchanged file (S-7-e, S-7-f); return-vs-raise is not tested",
    "OD-BATCH": "applied: no batch-file shape is frozen; only the missing-file I/O error is tested (S-9-e); exit 4 and the CLI "
                "batch success are UNSUPPORTED",
    "OD-01-01-6": "applied: Ledger and ConflictError are two atomic contracts (S-13-d, S-13-e)",
    "OD-02-01-4": "applied: first_bad_index is UNSUPPORTED (R-3.3/3); no convention promoted",
    "OD-03-01-5": "applied: the crash clause R-5/2 is UNSUPPORTED; no surfacing mechanism is required",
    "OD-STORE": "applied: ledgerlock.store is PLAN_ONLY; its normative content is re-expressed (S-9-d, S-9-a) or UNSUPPORTED",
    "OD-FACETS": "applied: every retained spec observes one clause; multi-clause criteria map to several atomic specs",
    "OD-STRONGER": "applied: no digest value or GENESIS form is asserted (R-3.2/2, R-3.2/4 UNSUPPORTED)",
}

FINDINGS = [{
    "id": "C2-P5-FINDING-001", "class": "DEVELOPER (the authoring aid of WP-2.5.1, candidate ec473d1)",
    "found_by": "a diagnostic trial run of the WP-2.5.2 falsifiability runner over the reference fixture",
    "defect": "ec473d1 compiled the four source-tree prohibitions as grep_count {matches: 0} under polarity MUST_NOT_HOLD: the "
              "contracts demanded at least one matching line",
    "measured": "reproduced in P5-FALSIFIABILITY.json (5c608bf's reproduction; kept)",
    "correction": "5c608bf: the aid refuses a MUST_NOT_HOLD contract whose observable is not declared to state the forbidden "
                  "behaviour; this correction states the prohibitions from the requirements (MUST_HOLD {matches: 0}) and keeps "
                  "the adversarial case (INVERTED_FORM)",
    "criteria": ["AC-STORY-01-01-4", "AC-STORY-01-01-5", "AC-STORY-05-03-1", "AC-STORY-05-03-2"]}]
#: C2-P5-FINDING-001's inverted form, kept only for the adversarial polarity test
INVERTED_FORM = tree("path:ledgerlock", r"os\.system|subprocess\.|socket\.", 0)
SUPERSEDES = [{"commit": "ec473d1742bb41206d34a72542d7ef0d8a19aa4a", "sha256": "6caf0deb8a556f10f3bb4a62c1d2591d73e15d48c86c4d0788eab08bbc60a851",
               "reason": "C2-P5-FINDING-001"},
              {"commit": "0f779956f98f38abf4d4c33c6db4cadd819d8640", "sha256": "13283389e04c220342aba95add2cc8935af407ee406ef6a251f6278117a7d23d",
               "reason": "owner ruling 2026-09-30: C2-P5 NOT ACCEPTED — the proposal was rebuilt from the frozen requirements"}]


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


def section(rid: str) -> str:
    """The frozen requirement section as REQUIREMENTS-MAP.json binds it, checked by its digest."""
    rmap = json.loads((ROOT / FIX_REL / "REQUIREMENTS-MAP.json").read_text(encoding="utf-8"))
    row = next(r for r in rmap["requirements"] if r["id"] == rid)
    lines = (ROOT / FIX_REL / "REQUIREMENTS.md").read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    body = "\n".join(lines[row["lines"][0] - 1:row["lines"][1]]).rstrip("\n") + "\n"
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != row["sha256"]:
        raise SystemExit(f"{rid}: the section text does not match REQUIREMENTS-MAP.json")
    return body


def requirements() -> dict:
    """The frozen requirement sections the retained specs cite, as kernel Requirements (text = the section)."""
    from aisef2.product.approval import Requirement
    return {rid: Requirement.create(id=rid, text=section(rid), source=f"{FIX_REL}/REQUIREMENTS.md#{rid}")
            for rid in sorted({s["requirement"] for s in SPECS.values()})}


def universal(spec_id: str) -> bool:
    """A spec derived from a DECISION-1 criterion, or measuring a universally quantified clause by a witness."""
    return any(spec_id in CRITERIA[ac]["specs"] for ac in decision_criteria(1)) or SPECS[spec_id]["quantifier"] != EX


def author(spec_id: str, entry: dict, reqs: dict, polarity_rule: bool = True) -> dict:
    """One spec's contract and ProductProofSpec, or a typed Refusal: the aid's rules (DECISION-1; the polarity rule of
    C2-P5-FINDING-001) and the kernel's (the contract rule, the compiler, the registry's observation class).
    `polarity_rule=False` only reproduces FINDING-001."""
    from aisef2.arch.enums import Enforcement, Polarity, SubjectAbsence, SubjectKind
    from aisef2.probe import catalog
    from aisef2.product.approval import ContractApproval
    from aisef2.product.compiler import CompileError, ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, ContractError, Subject
    q = entry.get("quantifier")
    polarity = entry.get("polarity", "MUST_HOLD")
    if q not in QUANTIFIERS:
        raise Refusal("REFUSED_QUANTIFIER_UNDECLARED", f"{spec_id} declares no quantifier semantics of {QUANTIFIERS}")
    if q == EX and any(spec_id in CRITERIA[ac]["specs"] for ac in decision_criteria(1)):
        raise Refusal("REFUSED_UNIVERSAL_DECLARED_EXHAUSTIVE", f"{spec_id} derives from a DECISION-1 criterion and names no "
                                                               "finite domain")
    if polarity_rule and polarity == "MUST_NOT_HOLD" and entry.get("states") != "forbidden":
        raise Refusal("REFUSED_POLARITY_INVERTED", f"{spec_id} has polarity MUST_NOT_HOLD and its observable is not declared "
                                                   "to state the forbidden behaviour (C2-P5-FINDING-001)")
    req = entry["requirement"]
    try:
        contract = BehaviorContract.create(id=f"BC-V22-{spec_id}", requirement_ids=(req,),
                                           subject=Subject(SubjectKind(entry["kind"]), entry["locator"]),
                                           stimulus=entry["stimulus"], observable=entry["observable"],
                                           polarity=Polarity[polarity], subject_absence=SubjectAbsence[entry["absence"]],
                                           rationale=entry["measured"])
    except ContractError as e:
        raise Refusal("REFUSED_BY_CONTRACT_RULE", f"ContractError: {e}") from None
    approval = ContractApproval(req, reqs[req].requirement_hash, contract.id, contract.contract_hash, SYNTHETIC_APPROVER, 0.0, ())
    active = catalog.active()
    refs = {kind: ProbeRef(e.probe_id, e.probe_digest) for kind, e in active.items()}
    try:
        spec = compile_spec(contract, requirements=reqs, approvals=[approval], probes=refs)
    except (CompileError, ContractError) as e:
        raise Refusal("REFUSED_BY_COMPILER", f"{type(e).__name__}: {e}") from None
    e = active[contract.subject.kind]
    cls = catalog.registry().observation_class(e.probe_id, e.probe_digest, spec)
    if cls is None:
        raise Refusal("UNSUPPORTED_OBSERVATION", f"{e.probe_id} gives the spec no observation class")
    enforcement = e.factory().enforcement()
    if q != EX and enforcement is Enforcement.FULL:
        raise Refusal("REFUSED_WITNESS_UNDER_FULL", f"{q} on {e.probe_id}, whose enforcement is FULL (DECISION-1)")
    table = getattr(importlib.import_module(e.factory.__module__), "CLASS_TABLE", {})
    return {"contract": contract, "spec": spec, "approval": approval, "probe_id": e.probe_id, "probe_digest": e.probe_digest,
            "observation_class": cls, "enforcement": enforcement.value, "class_quantifier": table.get(cls, {}).get("quantifier")}


def calibrations() -> tuple:
    """Every Cycle-2 ProbeCapabilityCalibration the lanes recorded."""
    from aisef2.probe.calibration import ProbeCapabilityCalibration
    keys = ("probe_id", "probe_digest", "observation_class", "positive_fixture", "negative_fixture", "demonstrated_at")
    out = []
    for rel in CALIBRATION_RECORDS:
        c = json.loads((ROOT / rel).read_text(encoding="utf-8"))["calibrations"]
        rows = [r for v in c.values() for r in v] if isinstance(c, dict) else c
        out += [ProbeCapabilityCalibration(*(r[k] for k in keys)) for r in rows if set(keys) <= set(r) and r.get("qualified", True)]
    return tuple(out)


def _mutants() -> dict:
    return {m["spec"]: m for m in json.loads((ROOT / MUTANTS_REL).read_text(encoding="utf-8"))["mutants"]}


def story_graph() -> dict[str, set[str]]:
    deps: dict[str, set[str]] = {}
    for r in P10.v1_rows():
        deps.setdefault(r["story"], set()).update(r["depends_on"])
    for s, extra in STORY_EDGES.items():
        deps[s].update(extra)
    closure = {}
    for s in deps:
        seen, todo = set(), list(deps[s])
        while todo:
            x = todo.pop()
            if x not in seen:
                seen.add(x)
                todo += list(deps.get(x, ()))
        closure[s] = seen
    return closure


def build() -> dict:
    """The corrected proposal: every retained spec authored and compiled; the plan of their obligations put to the
    admission engine with the synthetic approvals and with none."""
    from aisef2.arch.enums import ObligationRole
    from aisef2.plan import static_admission as sa
    from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation
    from aisef2.probe import catalog
    rows = {r["ac_id"]: r for r in P10.v1_rows()}
    assert len(rows) == 77 and set(CRITERIA) == set(rows), "CRITERIA classifies exactly the 77 frozen criteria"
    reqs = requirements()
    mutants = _mutants()
    specs_out, contracts, specs, approvals = [], {}, {}, []
    for sid, t in SPECS.items():
        entry = {"spec_id": sid, "requirement": t["requirement"], "clause": t["clause"], "clauses_also": t.get("clauses_also", []),
                 "story": t["story"], "role": t.get("role", "INTRODUCE"), "quantifier": t["quantifier"],
                 "measured": t["measured"], "witness": t["witness"], "unmeasured": t["unmeasured"], "note": t["note"],
                 "polarity": t.get("polarity", "MUST_HOLD"), "subject_kind": t["kind"], "locator": t["locator"],
                 "stimulus": t["stimulus"], "observable": t["observable"], "subject_absence": t["absence"],
                 "criteria": sorted(ac for ac, c in CRITERIA.items() if sid in c["specs"]),
                 "falsifiability_mutant": mutants.get(sid, {}).get("id")}
        try:
            a = author(sid, t, reqs)
        except Refusal as x:
            entry.update(status=x.code, typed_refusal=x.reason)
            specs_out.append(entry)
            continue
        contracts[a["contract"].id], specs[a["spec"].id] = a["contract"], a["spec"]
        approvals.append(a["approval"])
        entry.update(status="COMPILED", contract_id=a["contract"].id, contract_hash=a["contract"].contract_hash,
                     spec_hash_id=a["spec"].id, semantic_hash=a["spec"].semantic_hash, probe_id=a["probe_id"],
                     probe_digest=a["probe_digest"], observation_class=a["observation_class"], enforcement=a["enforcement"],
                     class_quantifier=a["class_quantifier"])
        specs_out.append(entry)
    compiled = [e for e in specs_out if e["status"] == "COMPILED"]
    by_story: dict[str, list[str]] = {}
    for e in compiled:
        if e["role"] == "INTRODUCE":
            by_story.setdefault(e["story"], []).append(e["spec_id"])
    graph = story_graph()
    spec_of = {e["spec_id"]: e["spec_hash_id"] for e in compiled}
    obligations = []
    for e in compiled:
        deps = tuple(c for s in sorted(graph[e["story"]]) for c in by_story.get(s, ()))
        obligations.append(PlanObligation(e["spec_id"], e["spec_hash_id"], e["story"], ObligationRole[e["role"]],
                                          EXPECTED_AT_PARENT[ObligationRole[e["role"]]], deps,
                                          f"{e['story']} {e['role']}s {e['spec_id']} ({e['clause']})"))
    introduced = {e["spec_id"]: e["story"] for e in compiled if e["role"] == "INTRODUCE"}
    for ac, c in CRITERIA.items():
        r = rows[ac]
        if c["class"] != N or ac in D3:
            continue
        for sid in c["specs"]:
            story = introduced.get(sid)
            if story and story != r["story"] and story in graph[r["story"]]:
                deps = tuple(x for s in sorted(graph[r["story"]]) for x in by_story.get(s, ()))
                obligations.append(PlanObligation(f"{ac}:{sid}", spec_of[sid], r["story"], ObligationRole.PRESERVE,
                                                  EXPECTED_AT_PARENT[ObligationRole.PRESERVE], deps,
                                                  f"{r['story']} PRESERVEs {sid} for {ac}"))
    plan = Plan.create(id=PLAN_ID, baseline=P10.LEDGERLOCK_PLAN_COMMIT, obligations=tuple(obligations),
                       plan_quality_policy=NOT_PREREGISTERED)
    cals = calibrations()
    catalogue, registry = catalog.catalogue(), catalog.registry()
    engine = sa.StaticPlanAdmissionEngine()
    checked = engine.admit(plan, sa.AdmissionInputs(reqs, contracts, tuple(approvals), specs, catalogue, cals, registry))
    bare = engine.admit(plan, sa.AdmissionInputs(reqs, contracts, (), specs, catalogue, cals, registry))
    return {"specs": specs_out, "compiled": {e["spec_id"]: specs[e["spec_hash_id"]] for e in compiled}, "plan": plan,
            "requirements": reqs, "checked": checked, "bare": bare}


def _admission(result) -> dict:
    return {"engine_digest": result.engine_digest, "admitted": result.admitted, "result_digest": result.result_digest,
            "checks": [{"number": c.number, "name": c.name, "passed": c.passed, "problems_count": len(c.problems),
                        "problems": list(c.problems[:5])} for c in result.checks]}


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file(rel: str) -> dict:
    return {"path": rel, "sha256": _sha((ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))}


def counts(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def record() -> dict:
    """The P5-PLAN-V2.2-PROPOSAL record: deterministic for a given tree."""
    from aisef2.probe import catalog
    from aisef2.product.compiler import COMPILER_DIGEST, COMPILER_ID
    b = build()
    rows = {r["ac_id"]: r for r in P10.v1_rows()}
    crit = [{"ac_id": ac, "story": rows[ac]["story"], "v1_requirement": rows[ac]["requirement"], "v1_mode": rows[ac]["proof_mode"],
             "criterion": rows[ac]["criterion"], **CRITERIA[ac], "contradicts_requirements": CONTRADICTS.get(ac)}
            for ac in sorted(CRITERIA)]
    p10_status = {e["ac_id"]: e for e in json.loads((ROOT / "closure-evidence/v2/P10/WORKLOAD.json").read_text(encoding="utf-8"))["criteria"]}
    mappings = []
    for ac in D3:
        c = CRITERIA[ac]
        before = P10.V2[ac]
        mappings.append({"ac_id": ac, "criterion": rows[ac]["criterion"], "classification": c["class"],
                         "before": {"subject_kind": before["kind"], "locator": before["locator"], "p10_status": p10_status[ac]["v2_status"]},
                         "after": ([{"spec_id": s, "measured": SPECS[s]["measured"], "requirement": SPECS[s]["requirement"],
                                     "clause": SPECS[s]["clause"]} for s in c["specs"]] or c["reason"]),
                         "approved": False})
    entries = {e.probe_id: {"digest": e.probe_digest, "kind": e.subject_kind.value, "active": e.active, "cycle": e.cycle}
               for e in catalog.CATALOG}
    body = {
        "record": "AISEF V2 — C2-P5 WP-2.5.1 LEDGERLOCK PLAN-V2.2 PROPOSAL, requirements-grounded (P5 correction)",
        "work_package": PACKAGE,
        "authority": "owner ruling 'AISEF V2 — CYCLE-2 OWNER REVIEW / P1-P4 ACCEPTED / C2-P5 NOT ACCEPTED / P5 CORRECTION "
                     "AUTHORIZED / QP-2.6 REMAINS BLOCKED' (2026-09-30)",
        "status": "PROPOSAL — NOT APPROVED, NOT APPLIED; no owner approval recorded; LedgerLock not run; QP-2.6 not started",
        "normative_priority": ["frozen requirements", "approved Behavior Contract semantics", "ProductProofSpec",
                               "plan / story decomposition", "developer tests"],
        "identities": {"aisef2_tree": _git("rev-parse", "HEAD:aisef2"), "compiler": {"id": COMPILER_ID, "digest": COMPILER_DIGEST},
                       "admission_engine_digest": b["checked"].engine_digest, "catalog": entries,
                       "requirements": _file(f"{FIX_REL}/REQUIREMENTS.md"), "requirements_map": _file(f"{FIX_REL}/REQUIREMENTS-MAP.json"),
                       "owner_decisions": _file(DECISIONS_REL), "v1_audit": _file(P10.V1_AUDIT_REL),
                       "p10_workload": _file("closure-evidence/v2/P10/WORKLOAD.json"), "p5_mutants": _file(MUTANTS_REL),
                       "authoring_aid": _file("validation/qualification/p10_contracts.py"),
                       "calibration_records": [_file(r) for r in CALIBRATION_RECORDS]},
        "requirements": {rid: {"hash": r.requirement_hash} for rid, r in b["requirements"].items()},
        "interface_bindings": INTERFACE_BINDINGS,
        "approvals": {"given": [], "synthetic_identity": SYNTHETIC_APPROVER,
                      "authority": "NON-AUTHORITATIVE TEST FIXTURE DATA: the schema mechanically requires the human: namespace "
                                   "(aisef2/product/approval.py HUMAN_PREFIX); these approvals exist in memory only, are never "
                                   "persisted as a ContractApproval or as owner approval evidence, and the 9/9 admission they "
                                   "give means only that the proposal WOULD admit once valid required approvals exist"},
        "plan": {"id": b["plan"].id, "plan_hash": b["plan"].plan_hash, "baseline": b["plan"].baseline,
                 "obligations": len(b["plan"].obligations), "stories": len({o.story_id for o in b["plan"].obligations}),
                 "obligations_by_role": counts(o.role.value for o in b["plan"].obligations), "story_edges_added": STORY_EDGES,
                 "plan_quality_policy": "NOT_PREREGISTERED (DECISION-5)"},
        "counts": {"specs_retained": len([s for s in b["specs"] if s["status"] == "COMPILED"]),
                   "specs_by_status": counts(s["status"] for s in b["specs"]),
                   "specs_by_kind": counts(s["subject_kind"] for s in b["specs"]),
                   "specs_by_quantifier": counts(s["quantifier"] for s in b["specs"]),
                   "criteria_by_class": counts(c["class"] for c in CRITERIA.values()),
                   "clauses_by_class": counts(c["class"] for c in CLAUSES)},
        "old_vs_new": {"old_specs": 64, "old_record": SUPERSEDES[-1], "new_specs": len(SPECS)},
        "decision_3_mappings": mappings,
        "owner_rulings_applied": OWNER_RULINGS,
        "requirement_risks": REQUIREMENT_RISKS,
        "audit": {"record": "closure-evidence/v2/cycle2/P5-CORRECTION-AUDIT.json",
                  "rule": "LANE-P5C's read-only audit is a reviewer's report, not evidence; its points adopted and its "
                          "disagreements are recorded there"},
        "findings": FINDINGS,
        "supersedes": SUPERSEDES,
        "static_admission": {"with_synthetic_approvals": _admission(b["checked"]), "without_approvals": _admission(b["bare"])},
        "clauses": CLAUSES,
        "criteria": crit,
        "specs": b["specs"],
    }
    body["proposal_digest"] = _sha(json.dumps({"plan_hash": b["plan"].plan_hash, "specs": b["specs"], "criteria": crit,
                                               "clauses": CLAUSES}, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    body["problems"] = problems(body)
    body["verdict"] = "PROPOSAL ADMITTED STATICALLY (synthetic, non-authoritative approvals); OWNER REVIEW PENDING" \
        if not body["problems"] else "PROBLEMS"
    return json.loads(json.dumps(body))


def problems(body: dict) -> list[str]:
    out = []
    specs = {s["spec_id"]: s for s in body["specs"]}
    if len(body["criteria"]) != 77:
        out.append("the proposal does not classify the 77 criteria")
    out += [f"{s}: not compiled ({v['status']})" for s, v in specs.items() if v["status"] != "COMPILED"]
    out += [f"{s}: no falsifiability witness in the P5 corpus" for s, v in specs.items() if not v["falsifiability_mutant"]]
    out += [f"{c['ac_id']}: normative without a spec" for c in body["criteria"] if c["class"] == N and not c["specs"]]
    out += [f"{c['ac_id']}: {c['class']} carries specs" for c in body["criteria"] if c["class"] != N and c["specs"]]
    out += [f"{c['ac_id']}: names unknown spec {s}" for c in body["criteria"] for s in c["specs"] if s not in specs]
    out += [f"{c['id']}: normative clause without a spec" for c in body["clauses"] if c["class"] == N and not c["specs"]]
    out += [f"{c['id']}: {c['class']} clause without a reason" for c in body["clauses"] if c["class"] in (U, E) and not c.get("reason")]
    covered = {s for c in body["clauses"] for s in c["specs"]}
    out += [f"{s}: traces to no clause of the coverage matrix" for s in specs if s not in covered]
    out += [f"{s}: its clause {v['clause']} is not a normative clause" for s, v in specs.items()
            if next((c for c in body["clauses"] if c["id"] == v["clause"]), {}).get("class") != N]
    if not body["static_admission"]["with_synthetic_approvals"]["admitted"]:
        out.append("not admitted even with the synthetic approvals")
    if body["static_admission"]["without_approvals"]["admitted"]:
        out.append("admitted without any approval: the approval gate did not hold")
    if body["approvals"]["given"]:
        out.append("an approval is recorded")
    if any(m["approved"] for m in body["decision_3_mappings"]):
        out.append("a DECISION-3 mapping is approved")
    if next(c for c in body["clauses"] if c["id"] == "R-11/1")["class"] != E:
        out.append("R-11 is not engineering-test only")
    return out


# --------------------------------------------------------------------------------------- the document

def document(rec: dict) -> str:
    c = rec["counts"]
    lines = [
        "# LedgerLock PLAN-V2.2 — PROPOSAL, requirements-grounded (not approved, not applied)", "",
        f"**Status.** {rec['status']}. Generated by `validation/qualification/p10_contracts.py` from the frozen requirements "
        f"(`{FIX_REL}/REQUIREMENTS.md`); the record is [`P5-PLAN-V2.2-PROPOSAL.json`](../../../../{OUT_REL}).", "",
        f"- proposal digest `{rec['proposal_digest']}`; plan `{rec['plan']['id']}` hash `{rec['plan']['plan_hash']}`",
        f"- retained ProductProofSpecs: {c['specs_retained']} (the previous proposal had {rec['old_vs_new']['old_specs']}); "
        f"by kind {', '.join(f'{k} {v}' for k, v in c['specs_by_kind'].items())}",
        f"- PLAN-V2.1 criteria: {', '.join(f'{k} {v}' for k, v in c['criteria_by_class'].items())}",
        f"- requirement clauses: {', '.join(f'{k} {v}' for k, v in c['clauses_by_class'].items())}",
        f"- static admission with the synthetic approvals: **{'ADMITTED' if rec['static_admission']['with_synthetic_approvals']['admitted'] else 'NOT ADMITTED'}**; "
        f"without approvals: **{'ADMITTED' if rec['static_admission']['without_approvals']['admitted'] else 'NOT ADMITTED'}**", "",
        f"`{rec['approvals']['synthetic_identity']}` is NON-AUTHORITATIVE TEST FIXTURE DATA: {rec['approvals']['authority']}.", "",
        "## Interface bindings", ""]
    lines += [f"- **{k}** ({'fixed by the requirements' if v['fixed_by_requirements'] else 'NOT fixed by the requirements'}): "
              f"{v['binding']} — {v['source']}" + (f". Gap: {v['gap']}" if v.get("gap") else "") for k, v in rec["interface_bindings"].items()]
    lines += ["", "## Requirement coverage matrix", "", "| clause | class | specs | reason |", "|---|---|---|---|"]
    lines += [f"| {x['id']} {x['clause']} | {x['class']} | {', '.join(x['specs']) or '—'} | {x.get('reason', x.get('note', ''))} |"
              for x in rec["clauses"]]
    lines += ["", "## Retained ProductProofSpecs", "", "| spec | clause | story | probe / class | quantifier | measured | witness mutant |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {s['spec_id']} | {s['clause']} | {s['story']} | {s.get('probe_id', '—')} / {s.get('observation_class', '—')} | "
              f"{s['quantifier']} | {s['measured']} | {s['falsifiability_mutant']} |" for s in rec["specs"]]
    lines += ["", "## PLAN-V2.1 criteria", "", "| criterion | class | specs | plan-only facets | unsupported facets |", "|---|---|---|---|---|"]
    lines += [f"| {x['ac_id']} | {x['class']} | {', '.join(x['specs']) or '—'} | {'; '.join(x['plan_only']) or '—'} | "
              f"{'; '.join(x['unsupported']) or '—'} |" for x in rec["criteria"]]
    lines += ["", "## DECISION-3 mappings (none approved)", ""]
    for m in rec["decision_3_mappings"]:
        after = m["after"] if isinstance(m["after"], str) else "; ".join(f"{a['spec_id']}: {a['measured']}" for a in m["after"])
        lines.append(f"- **{m['ac_id']}** {m['classification']} — before `{m['before']['locator']}` ({m['before']['p10_status']}); after: {after}")
    lines += ["", "## Owner rulings applied", ""] + [f"- **{k}** — {v}" for k, v in rec["owner_rulings_applied"].items()]
    lines += ["", "## Findings", ""] + [f"- **{f['id']}** — {f['defect']}. {f['correction']}." for f in rec["findings"]]
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
    if json.loads((ROOT / OUT_REL).read_text(encoding="utf-8")) != rec:
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
        print(f"{OUT_REL}: {rec['verdict']}; {rec['counts']}; plan {rec['plan']['plan_hash'][:12]}; proposal {rec['proposal_digest'][:12]}")
        return 0
    found = check()
    print("\n".join(found) if found else "PASS")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
