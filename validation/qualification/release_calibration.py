"""V2.0 release: the probe capability calibrations the release ships — `aisef2/app/calibrations.py`, the rows static
admission (RFC §12, check 9) reads in every `aisef run` — and their record.

    python -P validation/qualification/release_calibration.py --print   # calibrate, print, write nothing
    python -P validation/qualification/release_calibration.py --write   # -> aisef2/app/calibrations.py and
                                                                        #    closure-evidence/v2/release/PROBE-CALIBRATIONS.json
    python -P validation/qualification/release_calibration.py --check   # the shipped rows are this tree's probes, every
                                                                        # class re-demonstrated (calibrate() runs again),
                                                                        # and the record resolve() cites is current
    python -P validation/qualification/release_calibration.py --state   # resolve() only (no calibration): JSON, exit 1
                                                                        # unless MEASURED / VERIFIED_REUSE

A row exists only for a contrast demonstrated now (aisef2.probe.calibration.calibrate, §9.1.1): every active probe of
the catalog, every observation class it declares, its committed positive fixture observed SATISFIED and its negative
REFUTED, and the same fixtures rejected once they stop contrasting (negative, negative). A class without fixtures, or
that does not contrast, is a problem and nothing is written. The probes are the ones B1 changed, so the cycle-2
calibration records (bound to the earlier digests) stay as committed, as history.

v2.3 (EVID-COUPLING-01, W1-DESIGN §3): the record the release cites is resolved by INPUT IDENTITY, never by the
pyproject version string alone. `resolve()` takes the newest record of the nearest version <= this one and gives it one
of the F5 states (validation/v23/impact.py's four): MEASURED (a record written by this file in v2.3, committed at HEAD),
VERIFIED_REUSE (a legacy record, byte-identical to its blob at the v2.2.0 release commit, basis
`identical-inputs:V<ver>`), INVALIDATED or UNRESOLVED. Either current state needs all three inputs equal now: the
record's rows (KEYS) are the shipped `calibrations.py` rows and the rows derived from the catalog (probe ids, executing
digests, classes, fixture paths), and every row's positive and negative fixture tree has the record's sha256. A
version bump with no other change therefore keeps citing the same record, and `--write` then writes nothing.
Declared limits: the demonstration procedure (aisef2/probe/calibration.py, this generator) is not an impact input —
the record proves contrast for the probe bytes and fixtures it names; and a legacy record is anchored to git history
(it proves the bytes v2.2.0 committed, not who calibrated).
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SHIPPED_REL = "aisef2/app/calibrations.py"


def record_rel(version: str, n: int = 1) -> str:
    """The n-th record of `version`'s calibrations: 2.0.0's keeps its name; a later version writes its own beside it,
    and a recalibration of the same version (other bytes) the next number — a record is never rewritten."""
    if version == "2.0.0":
        return "closure-evidence/v2/release/PROBE-CALIBRATIONS.json"
    return f"closure-evidence/v2/release/V{version}-PROBE-CALIBRATIONS{'' if n == 1 else f'-{n}'}.json"


def newest_rel(version: str) -> tuple[str, int]:
    """The version's newest calibration record (its path and number); number 1's path when there is none yet."""
    n = 1
    while version != "2.0.0" and (ROOT / record_rel(version, n + 1)).exists():
        n += 1
    return record_rel(version, n), n


def _version(pyproject: pathlib.Path | None = None) -> str:
    import tomllib
    return tomllib.loads((pyproject or ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


FIXTURES_REL = "tests/v2/fixtures/calibration"
KEYS = ("probe_id", "probe_digest", "observation_class", "positive_fixture", "negative_fixture")
STATES = ("MEASURED", "VERIFIED_REUSE", "INVALIDATED", "UNRESOLVED")     # validation/v23/impact.py's, the only four
CURRENT = ("MEASURED", "VERIFIED_REUSE")
BASE = "da3ea33f3b695aaca73e87a704145a0193aced23"   # v2.2.0, whose release gate accepted every legacy record (impact.BASE)
ROUND = "v2.3"
_RECORD_NAME = re.compile(r"(?:V(.+?)-)?PROBE-CALIBRATIONS(?:-[0-9]+)?\.json")
_VERSION = re.compile(r"([0-9]+(?:\.[0-9]+)*)(?:\.dev([0-9]+))?")


def _vkey(version: str) -> tuple | None:
    m = _VERSION.fullmatch(version)
    return (tuple(int(x) for x in m[1].split(".")), m[2] is None, int(m[2] or 0)) if m else None


def _git(*args: str) -> bytes | None:
    """git's stdout in ROOT, or None when git fails (never an empty answer); replace refs ignored, as impact.py does."""
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                           env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"})
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def _rows(rows) -> list[tuple]:
    return sorted(tuple(r[k] for k in KEYS) for r in rows)


def shipped_rows() -> list[tuple]:
    """The KEYS tuples of `calibrations.py` as its bytes say (parsed, not imported: an edit is seen at once)."""
    tree = ast.parse((ROOT / SHIPPED_REL).read_text(encoding="utf-8"))
    value = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                 and [getattr(t, "id", None) for t in n.targets] == ["CALIBRATIONS"])
    return _rows(ast.literal_eval(value))


def derived_rows() -> list[tuple]:
    """The KEYS tuples this tree's catalog requires: every active probe at the digest of the bytes that run, every class
    it declares, its committed fixtures (#104: compared with `shipped_rows()` in both directions)."""
    from aisef2.probe import catalog
    from aisef2.probe.calibration import executing
    return sorted((e.probe_id, executing(e.factory), cls, f"{FIXTURES_REL}/{e.fixture_root}/{cls}/positive",
                   f"{FIXTURES_REL}/{e.fixture_root}/{cls}/negative") for e in catalog.CATALOG if e.active for cls in e.classes)


def _name(row: tuple) -> str:
    return f"{row[0]} {row[2]}"


def resolve(version: str | None = None) -> tuple[str, str, str]:
    """(record path, state, basis) of the calibration record this tree cites (module doc, W1-DESIGN §3). Never raises:
    an identity it cannot compute is UNRESOLVED; INVALIDATED names every differing row."""
    version = version or _version()
    try:
        return _resolve(version)
    except Exception as x:          # noqa: BLE001 — fail closed: unparsable record, missing file, broken import
        return newest_rel(version)[0], "UNRESOLVED", f"{type(x).__name__}: {x}"


def _resolve(version: str) -> tuple[str, str, str]:
    now = _vkey(version)
    if now is None:
        return record_rel(version), "UNRESOLVED", f"version {version!r} is not N.N.N[.devN]"
    found = {m[1] or "2.0.0" for p in (ROOT / record_rel("2.0.0")).parent.glob("*.json")
             if (m := _RECORD_NAME.fullmatch(p.name))}
    found = {v for v in found if _vkey(v) is not None and _vkey(v) <= now}
    if not found:
        return record_rel(version), "UNRESOLVED", f"no calibration record of a version <= {version}"
    ver = max(found, key=_vkey)
    rel = newest_rel(ver)[0]
    raw = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
    doc = json.loads(raw)
    identity = doc.get("identity")
    v23 = isinstance(identity, dict) and identity.get("round") == ROUND
    at, label = ("HEAD", "HEAD") if v23 else (BASE, "v2.2.0")
    if _git("cat-file", "-e", f"{at}^{{commit}}") is None:
        return rel, "UNRESOLVED", f"basis {label} is not in this repository (shallow clone or no git)"
    blob = _git("cat-file", "blob", f"{at}:{rel}")
    if blob is None and v23:
        return rel, "UNRESOLVED", f"{rel} is not committed (a v2.3 record counts once committed)"
    if blob is None:
        return rel, "INVALIDATED", f"{rel} is neither a record v2.2.0 committed nor a v2.3 record"
    if blob.replace(b"\r\n", b"\n") != raw:
        return rel, "INVALIDATED", f"{rel} differs from its committed bytes at {label}"
    if v23 and len((_git("log", "--format=%H", "HEAD", "--", rel) or b"").split()) != 1:
        return rel, "INVALIDATED", f"{rel} was rewritten after it was committed (a record is written once)"
    if v23 and identity.get("dirty") is not False:
        return rel, "UNRESOLVED", f"{rel} was written from a dirty tree"
    if doc.get("verdict") != "CALIBRATED" or doc.get("problems"):
        return rel, "INVALIDATED", f"{rel} does not record a calibration without problems"
    rows, shipped, derived = _rows(doc["rows"]), shipped_rows(), derived_rows()
    why = [f"{_name(r)}: in the record, not in {SHIPPED_REL}" for r in rows if r not in shipped]
    why += [f"{_name(r)}: in {SHIPPED_REL}, not in the record" for r in shipped if r not in rows]
    why += [f"{_name(r)}: not this tree's (probe digest {r[1][:12]}… or fixture paths)" for r in rows if r not in derived]
    why += [f"{_name(r)}: this tree's, not in the record" for r in derived if r not in rows]
    if len(set(rows)) != len(rows) or len(set(shipped)) != len(shipped):
        why.append("a row is duplicated")
    fixtures = doc.get("fixtures") or {}
    for r in rows:
        group = r[3].rsplit("/", 1)[0]
        for side, path in (("positive", r[3]), ("negative", r[4])):
            want = (fixtures.get(group) or {}).get(side)
            have = _sha_tree(ROOT / path) if (ROOT / path).is_dir() else None
            if want is None or have != want:
                why.append(f"{_name(r)}: the {side} fixture tree is not the record's "
                           f"(record {str(want)[:12]}…, now {str(have)[:12]}…)")
    if set(fixtures) != {r[3].rsplit("/", 1)[0] for r in rows}:
        why.append("the record's fixture trees are not its rows'")
    if why:
        return rel, "INVALIDATED", "; ".join(why)
    return (rel, "MEASURED", f"v2.3-measured@{identity.get('measured_on')}") if v23 else \
        (rel, "VERIFIED_REUSE", f"identical-inputs:V{ver}")


def state_problems() -> list[str]:
    """[] while the record this tree cites is current; otherwise why it may not be cited (consumers add this)."""
    return [] if STATE in CURRENT else [f"{RECORD_REL}: {STATE} — {BASIS}"]


HEADER = '''"""The probe capability calibrations this release ships: one row per (active probe digest, observation class), each a
contrast demonstrated by aisef2.probe.calibration.calibrate over the committed fixtures named. Static admission (check 9)
admits a spec only with its row. Generated by validation/qualification/release_calibration.py --write; never edited."""

CALIBRATIONS = (
'''


def _sha_tree(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in path.rglob("*") if x.is_file() and "__pycache__" not in x.parts):
        h.update(p.relative_to(path).as_posix().encode() + b"\0" + p.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def calibrate_all() -> tuple[list[dict], list[str], dict]:
    from aisef2.probe import catalog
    from aisef2.probe.calibration import NotQualified, calibrate, calibration_env
    registry, env = catalog.registry(), calibration_env(sys.executable)
    rows, problems, fixtures = [], [], {}
    for e in catalog.CATALOG:
        if not e.active:
            continue
        probe = e.factory()
        if probe.digest != e.probe_digest:
            problems.append(f"{e.probe_id}: the catalog's digest is not the probe's")
        for cls in e.classes:
            rel = f"{FIXTURES_REL}/{e.fixture_root}/{cls}"
            pos, neg = ROOT / rel / "positive", ROOT / rel / "negative"
            if not (pos.is_dir() and neg.is_dir()):
                problems.append(f"{e.probe_id} {cls}: no committed fixtures at {rel}")
                continue
            fixtures[rel] = {"positive": _sha_tree(pos), "negative": _sha_tree(neg)}
            try:
                rec = calibrate(probe, cls, pos, neg, env, time.time, registry=registry,
                                names=(f"{rel}/positive", f"{rel}/negative"))
            except NotQualified as x:
                problems.append(f"{e.probe_id} {cls}: {x}")
                continue
            rows.append(dataclasses.asdict(rec))
            try:
                calibrate(probe, cls, neg, neg, env, time.time, registry=registry)
                problems.append(f"{e.probe_id} {cls}: a non-contrasting pair (negative, negative) was not rejected")
            except NotQualified:
                pass
    return rows, problems, fixtures


def shipped_source(rows: list[dict]) -> str:
    body = "".join("    " + json.dumps({k: r[k] for k in (*KEYS, "demonstrated_at")}, sort_keys=True) + ",\n" for r in rows)
    return HEADER + body + ")\n"


def record(rows: list[dict], problems: list[str], fixtures: dict) -> dict:
    from validation.qualification import common as C
    return {"record": f"AISEF {_version()} — THE PROBE CAPABILITY CALIBRATIONS THE RELEASE SHIPS",
            "keyed_by": "each active probe's EXECUTION_DIGEST (V2.1, V2-007): the bytes the contrast was demonstrated on",
            "generator": {"path": "validation/qualification/release_calibration.py", "sha256": C.lf_sha(HERE / "release_calibration.py")},
            "aisef2_tree": C.git("rev-parse", "HEAD:aisef2"), "shipped": SHIPPED_REL,
            "rows": [{k: r[k] for k in KEYS} for r in rows], "fixtures": fixtures, "problems": problems,
            "verdict": "CALIBRATED" if not problems else "PROBLEMS"}


def check() -> list[str]:
    """The shipped rows are exactly what calibrating this tree gives (without the time), they contrast now, and the
    record resolve() cites is current."""
    from aisef2.app import calibrations as shipped
    rows, problems, _ = calibrate_all()
    want = sorted(tuple(r[k] for k in KEYS) for r in rows)
    have = sorted(tuple(r[k] for k in KEYS) for r in shipped.CALIBRATIONS)
    if want != have:
        problems.append(f"{SHIPPED_REL} is not this tree's calibration: {len(have)} rows shipped, {len(want)} derived "
                        f"(missing {sorted(set(want) - set(have))[:3]}, extra {sorted(set(have) - set(want))[:3]})")
    rel, state, basis = resolve()
    return problems + ([] if state in CURRENT else [f"{rel}: {state} — {basis}"])


#: V2.1: the record followed pyproject's version; v2.3: it is resolved by input identity (resolve()), so a version bump
#: with nothing else changed keeps citing the record it was calibrated in (VERIFIED_REUSE), never a missing file
RECORD_REL, STATE, BASIS = resolve()


def write() -> int:
    """--write: nothing while resolve() is current (calibrations.py byte-unchanged, nothing appended). Otherwise every
    class is re-demonstrated and a NEW v2.3 record is written once (`open "x"`, the next number of this version);
    calibrations.py is rewritten only when its rows change (then it is a kernel change, qualified by F5)."""
    rel, state, basis = resolve()
    if state in CURRENT:
        print(f"{rel}: {state} ({basis}) — nothing written; {SHIPPED_REL} unchanged")
        return 0
    dirty = _git("status", "--porcelain", "--", "aisef2", FIXTURES_REL)    # the inputs as measured, before any run
    rows, problems, fixtures = calibrate_all()
    rec = record(rows, problems, fixtures)
    if problems:
        print(json.dumps(rec, indent=1, sort_keys=True))
        return 1
    version = _version()
    new, n = newest_rel(version)
    if (ROOT / new).exists():
        new = record_rel(version, n + 1)      # the earlier record stays as history (2.0.0's name never numbers)
    rec["identity"] = {"round": ROUND, "measured_on": (_git("rev-parse", "HEAD") or b"").decode().strip() or None,
                       "dirty": dirty is None or bool(dirty.strip()), "supersedes": {"path": rel, "state": state, "basis": basis}}
    (ROOT / new).parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(ROOT / new, "x", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    except FileExistsError:
        print(f"{new} exists: a record is never rewritten", file=sys.stderr)
        return 1
    changed = _rows(rows) != shipped_rows()
    if changed:
        (ROOT / SHIPPED_REL).write_text(shipped_source(rows), encoding="utf-8")
    print(f"wrote {new}" + (f" and {SHIPPED_REL} ({len(rows)} rows)" if changed else f"; {SHIPPED_REL} unchanged (same rows)"))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--state", action="store_true")
    a = ap.parse_args(argv)
    if a.state:
        rel, state, basis = resolve()
        print(json.dumps({"version": _version(), "record": rel, "state": state, "basis": basis}, indent=1))
        return 0 if state in CURRENT else 1
    if a.check:
        problems = check()
        print("release calibration: " + ("PASS" if not problems else "FAIL\n" + "\n".join(problems)))
        return 1 if problems else 0
    if a.write:
        return write()
    rows, problems, fixtures = calibrate_all()
    print(json.dumps(record(rows, problems, fixtures), indent=1, sort_keys=True))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
