"""Independent acceptance for a LedgerLock implementation tree (WP-2.0.3).

`run(tree)` returns {assertion_id: {"ok": bool, "detail": str}} for every assertion in ASSERTIONS. Every observation
is made in a fresh `python -I` subprocess with only the tree root on sys.path: the CLI as `python -m ledgerlock`
(through runpy) and the library through a short driver that prints JSON. Nothing of this process, of a previous
check or of another tree is visible to the subject, and the suite reads no mutant id, no path and no fixture name:
it observes behaviour. The hash formula, the canonical form and every expected value are this suite's own reading
of REQUIREMENTS.md; the static assertions (A-8-a, A-10-a, A-12-a, A-13-a) read the tree's source.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ASSERTIONS = (
    "A-3.1-a", "A-3.2-a", "A-3.2-b", "A-3.3-a", "A-3.3-b", "A-3.3-c", "A-3.3-d", "A-3.3-e", "A-3.3-f", "A-3.4-a",
    "A-4.1-a", "A-4.2-a", "A-4.3-a", "A-4.4-a", "A-4.5-a", "A-5-a", "A-5-b", "A-5-c", "A-5-d", "A-6-a", "A-6-b",
    "A-7-a", "A-7-b", "A-7-c", "A-8-a", "A-9-a", "A-9-b", "A-9-c", "A-9-d", "A-9-e", "A-9-f", "A-9-g", "A-9-h",
    "A-10-a", "A-12-a", "A-13-a",
)
ALLOWED_IMPORTS = {"hashlib", "json", "os", "sys", "pathlib", "tempfile", "argparse", "unittest", "typing",
                   "unicodedata", "uuid", "__future__"}
TIMEOUT = 120
NFC_E = "\u00e9"
NFD_E = "e\u0301"

BOOT = ("import sys, runpy; sys.path.insert(0, sys.argv[1]); sys.argv = ['ledgerlock'] + sys.argv[2:]; "
        "runpy.run_module('ledgerlock', run_name='__main__', alter_sys=True)")
DRIVER = ("import sys, json, re, os\nsys.path.insert(0, sys.argv[1])\nimport ledgerlock\n"
          "from ledgerlock.ledger import ConflictError, Ledger\nOUT = {}\n@@CODE@@\n"
          "print(json.dumps(OUT, ensure_ascii=False))")


# --------------------------------------------------------------------------------------- observation

def cli(tree, *args, cwd=None):
    """The CLI in a fresh isolated interpreter: (exit code, stdout bytes, stderr text)."""
    p = subprocess.run([sys.executable, "-I", "-c", BOOT, str(tree), *args], cwd=str(cwd or tree),
                       capture_output=True, timeout=TIMEOUT)
    return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")


def lib(tree, code: str) -> dict:
    """A library driver in a fresh isolated interpreter; `code` fills OUT, printed as JSON."""
    p = subprocess.run([sys.executable, "-I", "-c", DRIVER.replace("@@CODE@@", code), str(tree)], cwd=str(tree),
                       capture_output=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    if p.returncode != 0 or not p.stdout.strip():
        return {"__error__": (p.stderr or "no output")[-1500:]}
    return json.loads(p.stdout.strip().splitlines()[-1])


def read_lines(path) -> list:
    raw = pathlib.Path(path).read_bytes()
    parts = raw.split(b"\n")
    return parts[:-1] if raw.endswith(b"\n") else parts


def records(path) -> list:
    return [json.loads(line.decode("utf-8")) for line in read_lines(path)]


def canonical(rec: dict) -> bytes:
    blank = dict(rec, hash="", prev_hash="")
    return json.dumps(blank, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def expected_hash(prev: str, rec: dict) -> str:
    return hashlib.sha256(prev.encode("utf-8") + b"|" + canonical(rec)).hexdigest()


def put(tree, ledger, key, value, rid, ts):
    code, out, _ = cli(tree, "put", str(ledger), key, json.dumps(value), "--rid", rid, "--ts", str(ts))
    return code, out


def delete(tree, ledger, key, rid, ts):
    code, out, _ = cli(tree, "delete", str(ledger), key, "--rid", rid, "--ts", str(ts))
    return code, out


def verdict(tree, ledger):
    code, out, _ = cli(tree, "verify", str(ledger))
    try:
        return code, json.loads(out.decode("utf-8"))
    except ValueError:
        return code, None


def tamper(path, pattern: bytes, replacement: bytes, line: int) -> bool:
    """Rewrite one line of the file with a single regex substitution; False when the pattern is not there once."""
    lines = read_lines(path)
    new, n = re.subn(pattern, replacement, lines[line], count=1)
    if n != 1:
        return False
    lines[line] = new
    pathlib.Path(path).write_bytes(b"\n".join(lines) + b"\n")
    return True


def _json(out: bytes):
    try:
        return json.loads(out.decode("utf-8"))
    except ValueError:
        return None


def _q(path) -> str:
    return json.dumps(str(path))


# --------------------------------------------------------------------------------------- assertions

def a_3_1_a(tree, work):
    ledger = work / "l.jsonl"
    c1, o1 = put(tree, ledger, NFD_E, 1, "r1", 1)
    c2, o2 = put(tree, ledger, NFC_E, 2, "r1", 2)
    c3, _ = put(tree, ledger, NFC_E, 3, "r2", 3)
    n = len(read_lines(ledger))
    snap = _json(cli(tree, "snapshot", str(ledger))[1])
    ok = (c1, c2, c3, n) == (0, 0, 4, 1) and _json(o1) == _json(o2) and snap == {NFC_E: 1} and list(snap) == [NFC_E]
    return ok, f"codes {c1},{c2},{c3}; lines {n}; snapshot keys {list(snap or {})!r}; same result {_json(o1) == _json(o2)}"


def a_3_2_a(tree, work):
    ledger = work / "l.jsonl"
    put(tree, ledger, "a", 1, "r1", 1)
    put(tree, ledger, "b", {"x": [1, "é"]}, "r2", 2)
    recs = records(ledger)
    if len(recs) != 2:
        return False, f"{len(recs)} lines"
    h0 = expected_hash("GENESIS", recs[0])
    h1 = expected_hash(recs[0]["hash"], recs[1])
    ok = recs[0]["prev_hash"] == "GENESIS" and recs[0]["hash"] == h0 and recs[1]["prev_hash"] == recs[0]["hash"] \
        and recs[1]["hash"] == h1
    return ok, f"prev0 {recs[0]['prev_hash']!r}; hash0 ok {recs[0]['hash'] == h0}; prev1 linked {recs[1]['prev_hash'] == recs[0]['hash']}; hash1 ok {recs[1]['hash'] == h1}"


def a_3_2_b(tree, work):
    ledger = work / "l.jsonl"
    put(tree, ledger, "a", 1, "r1", 1)
    first = read_lines(ledger)[0]
    put(tree, ledger, "b", 2, "r2", 2)
    lines = read_lines(ledger)
    return len(lines) == 2 and lines[0] == first, f"lines {len(lines)}; first unchanged {lines[0] == first}"


def _two_lines(tree, work):
    ledger = work / "l.jsonl"
    put(tree, ledger, "a", 1, "r1", 1)
    put(tree, ledger, "b", 2, "r2", 2)
    return ledger


def _detected(tree, ledger, index):
    code, v = verdict(tree, ledger)
    lv = lib(tree, f"v = Ledger({_q(ledger)}).verify()\nOUT = {{'ok': v.ok, 'first_bad_index': v.first_bad_index}}")
    ok = v is not None and v.get("ok") is False and v.get("first_bad_index") == index \
        and lv.get("ok") is False and lv.get("first_bad_index") == index
    return ok, f"cli verdict {v}; library verdict {lv}; expected first_bad_index {index}"


def a_3_3_a(tree, work):
    ledger = _two_lines(tree, work)
    if not tamper(ledger, rb'"value":\s*1', b'"value":9', 0):
        return False, "could not tamper the value of line 0"
    return _detected(tree, ledger, 0)


def a_3_3_b(tree, work):
    ledger = _two_lines(tree, work)
    if not tamper(ledger, rb'"op":\s*"put"', b'"op":"delete"', 0):
        return False, "could not swap the op of line 0"
    return _detected(tree, ledger, 0)


def a_3_3_c(tree, work):
    ledger = _two_lines(tree, work)
    h = records(ledger)[1]["hash"]
    flipped = h[:-1] + ("0" if h[-1] != "0" else "1")
    if not tamper(ledger, re.escape(h.encode("utf-8")), flipped.encode("utf-8"), 1):
        return False, "could not modify the hash of line 1"
    return _detected(tree, ledger, 1)


def a_3_3_d(tree, work):
    ledger = _two_lines(tree, work)
    code, v = verdict(tree, ledger)
    ok = v is not None and v.get("ok") is True and v.get("first_bad_index") is None and v.get("length") == 2
    return ok, f"verdict {v}"


def a_3_3_e(tree, work):
    ledger = work / "l.jsonl"
    for i in range(3):
        put(tree, ledger, f"k{i}", i, f"r{i}", i)
    lines = read_lines(ledger)
    ledger.write_bytes(b"\n".join([lines[0], lines[2]]) + b"\n")
    return _detected(tree, ledger, 1)


def a_3_3_f(tree, work):
    """The link alone: line 1's prev_hash field is changed while its hash (computed over blanked link fields) is
    not; only the prev_hash-equals-previous-hash rule can see it."""
    ledger = _two_lines(tree, work)
    link = records(ledger)[1]["prev_hash"]
    flipped = link[:-1] + ("0" if link[-1] != "0" else "1")
    if not tamper(ledger, re.escape(link.encode("utf-8")), flipped.encode("utf-8"), 1):
        return False, "could not modify the prev_hash of line 1"
    return _detected(tree, ledger, 1)


def a_3_4_a(tree, work):
    ledger = work / "l.jsonl"
    r = lib(tree, f"p = {_q(ledger)}\nL = Ledger(p)\nL.put('a', 1, 'r1', 1)\n"
                  "raw = open(p, 'rb').read()\nraw2, n = re.subn(rb'\"value\":\\s*1', b'\"value\":9', raw, count=1)\n"
                  "open(p, 'wb').write(raw2)\nv = L.verify()\n"
                  "OUT = {'subs': n, 'ok': v.ok, 'first_bad_index': v.first_bad_index}")
    ok = r.get("subs") == 1 and r.get("ok") is False and r.get("first_bad_index") == 0
    return ok, f"{r}"


def a_4_1_a(tree, work):
    ledger = work / "l.jsonl"
    r = lib(tree, f"try:\n    Ledger({_q(ledger)}).put('a', 1, '', 1)\n    OUT['raised'] = None\n"
                  "except ValueError as e:\n    OUT['raised'] = 'ValueError'")
    code, _ = put(tree, ledger, "a", 1, "", 1)
    exists = ledger.exists() and len(read_lines(ledger)) > 0
    ok = r.get("raised") == "ValueError" and code == 2 and not exists
    return ok, f"library {r}; cli exit {code}; a line was written {exists}"


def a_4_2_a(tree, work):
    ledger = work / "l.jsonl"
    c1, o1 = put(tree, ledger, "a", 1, "r1", 1)
    c2, o2 = put(tree, ledger, "a", 1, "r1", 2)
    n = len(read_lines(ledger))
    ok = (c1, c2, n) == (0, 0, 1) and _json(o1) is not None and _json(o1) == _json(o2)
    return ok, f"codes {c1},{c2}; lines {n}; same result {_json(o1) == _json(o2)}"


def a_4_3_a(tree, work):
    ledger = work / "l.jsonl"
    c1, _ = put(tree, ledger, "a", 1, "r1", 1)
    c2, _ = put(tree, ledger, "a", 2, "r2", 2)
    n = len(read_lines(ledger))
    r = lib(tree, f"try:\n    Ledger({_q(ledger)}).put('a', 3, 'r3', 3)\n    OUT['raised'] = None\n"
                  "except ConflictError:\n    OUT['raised'] = 'ConflictError'")
    n2 = len(read_lines(ledger))
    ok = (c1, c2, n, n2) == (0, 4, 1, 1) and r.get("raised") == "ConflictError"
    return ok, f"codes {c1},{c2}; lines {n},{n2}; library {r}"


def a_4_4_a(tree, work):
    ledger = work / "l.jsonl"
    c1, o1 = delete(tree, ledger, "k", "r2", 1)
    op0 = (records(ledger)[0].get("op") if read_lines(ledger) else None)
    c2, _ = put(tree, ledger, "k", 1, "r3", 2)
    n2 = len(read_lines(ledger))
    c3, o3 = put(tree, ledger, "k", 1, "r2", 3)
    n3 = len(read_lines(ledger))
    snap = _json(cli(tree, "snapshot", str(ledger))[1])
    ok = (c1, op0, c2, n2, c3, n3) == (0, "delete", 4, 1, 0, 1) and _json(o1) == _json(o3) and snap == {}
    return ok, f"delete {c1} op {op0!r}; put r3 {c2} lines {n2}; put r2 {c3} lines {n3}; same result {_json(o1) == _json(o3)}; snapshot {snap}"


def a_4_5_a(tree, work):
    ledger = work / "l.jsonl"
    c1, _ = put(tree, ledger, "k", 1, "r1", 1)
    c2, _ = delete(tree, ledger, "k", "r2", 2)
    n2 = len(read_lines(ledger))
    c3, _ = put(tree, ledger, "k", 1, "r1", 3)
    c4, _ = delete(tree, ledger, "k", "r2", 4)
    n4 = len(read_lines(ledger))
    ok = (c1, c2, n2, c3, c4, n4) == (0, 4, 1, 0, 4, 1)
    return ok, f"codes {c1},{c2},{c3},{c4}; lines {n2},{n4}"


def _batch(work, entries):
    path = work / "batch.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def a_5_a(tree, work):
    ledger = work / "l.jsonl"
    batch = _batch(work, [{"op": "put", "key": "a", "value": 1, "rid": "ra", "ts": 1},
                          {"op": "put", "key": "b", "value": 2, "rid": "rb", "ts": 2},
                          {"op": "delete", "key": "c", "rid": "rc", "ts": 3}])
    code, _, _ = cli(tree, "apply", "--batch", str(batch), str(ledger))
    n = len(read_lines(ledger)) if ledger.exists() else 0
    vcode, v = verdict(tree, ledger)
    snap = _json(cli(tree, "snapshot", str(ledger))[1])
    ok = code == 0 and n == 3 and v is not None and v.get("ok") is True and snap == {"a": 1, "b": 2}
    return ok, f"apply {code}; lines {n}; verdict {v}; snapshot {snap}"


def a_5_b(tree, work):
    ledger = work / "l.jsonl"
    put(tree, ledger, "a", 1, "r1", 1)
    before = ledger.read_bytes()
    batch = _batch(work, [{"op": "put", "key": "x", "value": 1, "rid": "rx", "ts": 1},
                          {"op": "put", "key": "a", "value": 2, "rid": "r9", "ts": 2},
                          {"op": "put", "key": "y", "value": 1, "rid": "ry", "ts": 3}])
    code, _, _ = cli(tree, "apply", "--batch", str(batch), str(ledger))
    after = ledger.read_bytes()
    return code == 4 and after == before, f"apply {code}; bytes identical {after == before}; lines {len(read_lines(ledger))}"


def a_5_c(tree, work):
    ledger = work / "l.jsonl"
    r = lib(tree, f"res = Ledger({_q(ledger)}).apply_batch([('put', 'a', 1, 'r1', 1), ('put', 'a', 1, 'r1', 2)])\n"
                  "OUT = {'n': len(res), 'same': res[0] == res[1]}")
    n = len(read_lines(ledger)) if ledger.exists() else 0
    ok = r.get("n") == 2 and r.get("same") is True and n == 1
    return ok, f"library {r}; lines {n}"


def a_5_d(tree, work):
    ledger = work / "l.jsonl"
    put(tree, ledger, "a", 1, "r1", 1)
    before = ledger.read_bytes()
    batch = _batch(work, [{"op": "put", "key": "b", "value": 2, "rid": "rb", "ts": 2},
                          {"op": "put", "key": "c", "value": 3, "rid": "rc", "ts": 3}])
    code, _, _ = cli(tree, "apply", "--batch", str(batch), str(ledger))
    after = ledger.read_bytes()
    siblings = sorted(os.listdir(work))
    ok = code == 0 and after.startswith(before) and len(read_lines(ledger)) == 3 and siblings == ["batch.json", "l.jsonl"]
    return ok, f"apply {code}; prefix kept {after.startswith(before)}; siblings {siblings}"


def a_6_a(tree, work):
    ledger = work / "l.jsonl"
    for i, key in enumerate(["b", "a", NFC_E, "Z"]):
        put(tree, ledger, key, i + 1, f"r{i}", i)
    delete(tree, ledger, "d", "rd", 9)
    s1 = cli(tree, "snapshot", str(ledger))[1]
    s2 = cli(tree, "snapshot", str(ledger))[1]
    snap = _json(s1)
    keys = list(snap) if isinstance(snap, dict) else None
    ok = keys == ["Z", "a", "b", NFC_E] and snap == {"b": 1, "a": 2, NFC_E: 3, "Z": 4} and s1 == s2 and s1.endswith(b"\n")
    return ok, f"keys {keys!r}; values ok {snap == {'b': 1, 'a': 2, NFC_E: 3, 'Z': 4}}; stable {s1 == s2}"


def a_6_b(tree, work):
    ledger = work / "l.jsonl"
    put(tree, ledger, "a", {"n": [1, 2]}, "r1", 1)
    put(tree, ledger, "b", "x", "r2", 2)
    out = work / "snap.json"
    code, stdout, _ = cli(tree, "snapshot", str(ledger))
    code2, _, _ = cli(tree, "snapshot", str(ledger), "--out", str(out))
    r = lib(tree, f"OUT = {{'hex': Ledger({_q(ledger)}).snapshot().hex()}}")
    ok = code == 0 and code2 == 0 and out.exists() and out.read_bytes() == stdout and r.get("hex") == stdout.hex()
    return ok, f"codes {code},{code2}; file == stdout {out.exists() and out.read_bytes() == stdout}; library == stdout {r.get('hex') == stdout.hex()}"


def _three_lines(tree, work):
    ledger = work / "l.jsonl"
    for i in range(3):
        put(tree, ledger, f"k{i}", {"v": i}, f"r{i}", i)
    return ledger, ledger.read_bytes()


def a_7_a(tree, work):
    ledger, original = _three_lines(tree, work)
    ledger.write_bytes(original[:-10])
    code, _, _ = cli(tree, "repair-tail", str(ledger))
    lines = original.split(b"\n")
    expected = b"\n".join(lines[:2]) + b"\n"
    after = ledger.read_bytes()
    vcode, v = verdict(tree, ledger)
    ok = code == 0 and after == expected and v is not None and v.get("ok") is True and v.get("length") == 2
    return ok, f"repair {code}; bytes == first two lines {after == expected}; verdict {v}"


def a_7_b(tree, work):
    ledger, original = _three_lines(tree, work)
    code, _, _ = cli(tree, "repair-tail", str(ledger))
    return code == 0 and ledger.read_bytes() == original, f"repair {code}; identical {ledger.read_bytes() == original}"


def a_7_c(tree, work):
    ledger, _ = _three_lines(tree, work)
    if not tamper(ledger, rb'"v":\s*0', b'"v":7', 0):
        return False, "could not tamper line 0"
    corrupt = ledger.read_bytes()
    code1, _, _ = cli(tree, "repair-tail", str(ledger))
    same1 = ledger.read_bytes() == corrupt
    ledger.write_bytes(corrupt[:-10])
    truncated = ledger.read_bytes()
    code2, _, _ = cli(tree, "repair-tail", str(ledger))
    same2 = ledger.read_bytes() == truncated
    ok = code1 == 5 and same1 and code2 == 5 and same2
    return ok, f"terminated: exit {code1} untouched {same1}; truncated tail too: exit {code2} untouched {same2}"


def _writes(func: ast.FunctionDef) -> bool:
    for n in ast.walk(func):
        if isinstance(n, ast.Call) and (isinstance(n.func, ast.Name) and n.func.id == "open"
                                        or isinstance(n.func, ast.Attribute) and n.func.attr in ("open", "fdopen")):
            for a in n.args[1:2] + [k.value for k in n.keywords if k.arg == "mode"]:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and ("a" in a.value or "w" in a.value):
                    return True
    return False


def _fsyncs(func: ast.FunctionDef) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "fsync"
               for n in ast.walk(func))


def a_8_a(tree, work):
    tree_ = ast.parse((pathlib.Path(tree) / "ledgerlock" / "ledger.py").read_text(encoding="utf-8"))
    writers = [f for f in ast.walk(tree_) if isinstance(f, ast.FunctionDef) and _writes(f)]
    missing = [f.name for f in writers if not _fsyncs(f)]
    ok = bool(writers) and not missing
    return ok, f"writing functions {[f.name for f in writers]}; without fsync {missing}"


def a_9_a(tree, work):
    ledger = _two_lines(tree, work)
    code, _, _ = cli(tree, "verify", str(ledger))
    return code == 0, f"exit {code}"


def a_9_b(tree, work):
    ledger = _two_lines(tree, work)
    tamper(ledger, rb'"value":\s*1', b'"value":9', 0)
    code, _, _ = cli(tree, "verify", str(ledger))
    return code == 5, f"exit {code}"


def a_9_c(tree, work):
    ledger = _two_lines(tree, work)
    c1, _, _ = cli(tree, "frobnicate", str(ledger))
    c2, _, _ = cli(tree, "verify")
    c3, _, _ = cli(tree, "put", str(ledger), "k", "1", "--rid", "r", "--ts", "notanint")
    return (c1, c2, c3) == (2, 2, 2), f"exits {c1},{c2},{c3}"


def a_9_d(tree, work):
    missing = work / "absent" / "l.jsonl"
    c1, _, _ = cli(tree, "verify", str(missing))
    c2, _, _ = cli(tree, "snapshot", str(missing))
    ledger = _two_lines(tree, work)
    c3, _, _ = cli(tree, "apply", "--batch", str(work / "absent.json"), str(ledger))
    return (c1, c2, c3) == (3, 3, 3), f"exits {c1},{c2},{c3}"


def a_9_e(tree, work):
    ledger = work / "l.jsonl"
    put(tree, ledger, "a", 1, "r1", 1)
    code, _ = put(tree, ledger, "a", 2, "r2", 2)
    return code == 4, f"exit {code}"


def a_9_f(tree, work):
    ledger = work / "l.jsonl"
    put(tree, ledger, "a", 1, "r1", 1)
    batch = _batch(work, [{"op": "put", "key": "a", "value": 2, "rid": "r2", "ts": 2}])
    code, _, _ = cli(tree, "apply", "--batch", str(batch), str(ledger))
    return code == 4, f"exit {code}"


def a_9_g(tree, work):
    ledger, _ = _three_lines(tree, work)
    tamper(ledger, rb'"v":\s*0', b'"v":7', 0)
    code, _, _ = cli(tree, "repair-tail", str(ledger))
    return code == 5, f"exit {code}"


def a_9_h(tree, work):
    ledger = _two_lines(tree, work)
    code, out, _ = cli(tree, "snapshot", str(ledger))
    return code == 0 and _json(out) == {"a": 1, "b": 2}, f"exit {code}; snapshot {_json(out)}"


def _imports(tree_: ast.AST) -> set:
    out = set()
    for n in ast.walk(tree_):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out.add((n.module or "").split(".")[0])
    return out


def _modules(tree):
    pkg = pathlib.Path(tree) / "ledgerlock"
    return {p.name: ast.parse(p.read_text(encoding="utf-8")) for p in sorted(pkg.glob("*.py"))}


def a_10_a(tree, work):
    mods = _modules(tree)
    extra = {name: sorted(_imports(t) - ALLOWED_IMPORTS - {"ledgerlock"}) for name, t in mods.items()}
    extra = {k: v for k, v in extra.items() if v}
    future = {name: any(isinstance(n, ast.ImportFrom) and n.module == "__future__" for n in t.body)
              for name, t in mods.items() if name in ("ledger.py", "cli.py")}
    ok = not extra and all(future.values()) and set(future) == {"ledger.py", "cli.py"}
    return ok, f"imports outside the allowed set {extra}; __future__ {future}"


def a_12_a(tree, work):
    mods = _modules(tree)
    bad = []
    for name, t in mods.items():
        if _imports(t) & {"socket", "subprocess"}:
            bad.append(f"{name}: socket/subprocess")
        for n in ast.walk(t):
            if isinstance(n, ast.Attribute) and n.attr == "system" and isinstance(n.value, ast.Name) and n.value.id == "os":
                bad.append(f"{name}:{n.lineno}: os.system")
    return not bad, f"{bad}"


def a_13_a(tree, work):
    pkg = pathlib.Path(tree) / "ledgerlock"
    present = {name: (pkg / name).is_file() for name in ("__init__.py", "ledger.py", "cli.py")}
    names = set()
    if present["ledger.py"]:
        for n in ast.parse((pkg / "ledger.py").read_text(encoding="utf-8")).body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                names.add(n.name)
    required = {"Ledger", "ConflictError", "append", "verify", "snapshot", "apply_batch"}
    r = lib(tree, "OUT = {'file': os.path.realpath(ledgerlock.__file__)}")
    inside = str(r.get("file", "")).startswith(os.path.realpath(str(tree)))
    ok = all(present.values()) and required <= names and inside
    return ok, f"files {present}; missing names {sorted(required - names)}; module inside the tree {inside}"


CHECKS = {
    "A-3.1-a": a_3_1_a, "A-3.2-a": a_3_2_a, "A-3.2-b": a_3_2_b, "A-3.3-a": a_3_3_a, "A-3.3-b": a_3_3_b,
    "A-3.3-c": a_3_3_c, "A-3.3-d": a_3_3_d, "A-3.3-e": a_3_3_e, "A-3.3-f": a_3_3_f, "A-3.4-a": a_3_4_a,
    "A-4.1-a": a_4_1_a,
    "A-4.2-a": a_4_2_a, "A-4.3-a": a_4_3_a, "A-4.4-a": a_4_4_a, "A-4.5-a": a_4_5_a, "A-5-a": a_5_a, "A-5-b": a_5_b,
    "A-5-c": a_5_c, "A-5-d": a_5_d, "A-6-a": a_6_a, "A-6-b": a_6_b, "A-7-a": a_7_a, "A-7-b": a_7_b, "A-7-c": a_7_c,
    "A-8-a": a_8_a, "A-9-a": a_9_a, "A-9-b": a_9_b, "A-9-c": a_9_c, "A-9-d": a_9_d, "A-9-e": a_9_e, "A-9-f": a_9_f,
    "A-9-g": a_9_g, "A-9-h": a_9_h, "A-10-a": a_10_a, "A-12-a": a_12_a, "A-13-a": a_13_a,
}
assert tuple(CHECKS) == ASSERTIONS


def check(tree, assertion: str, work: pathlib.Path) -> dict:
    """One assertion in its own working directory; any harness error is a failure with its reason. The tree is
    handed to every subprocess as an absolute path: inside the child the cwd is the tree itself."""
    work.mkdir(parents=True, exist_ok=True)
    try:
        ok, detail = CHECKS[assertion](pathlib.Path(tree).resolve(), work.resolve())
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as e:
        return {"ok": False, "detail": f"harness: {type(e).__name__}: {e}"}
    return {"ok": bool(ok), "detail": detail}


def run(tree) -> dict:
    results = {}
    with tempfile.TemporaryDirectory(prefix="ledgerlock-acc-") as t:
        for n, assertion in enumerate(ASSERTIONS):
            results[assertion] = check(tree, assertion, pathlib.Path(t) / f"a{n:02d}")
    return results


if __name__ == "__main__":
    res = run(sys.argv[1])
    for a, r in res.items():
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {a:8s} {r['detail']}")
    print(f"{sum(r['ok'] for r in res.values())}/{len(res)} assertions hold")
    sys.exit(0 if all(r["ok"] for r in res.values()) else 1)
