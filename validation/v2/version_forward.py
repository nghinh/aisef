"""Version-forward record supersession (owner v2.2 directive, Option C).

The problem it solves: a record-currency checker asserts a COMMITTED evidence record re-derives on this tree. When
the tree legitimately advances (a new release candidate), the committed record — pinned to the earlier sealed tree
— goes stale, and the only in-tree generators are write-once, so there is no way to make the check current without
rewriting the historical record. release_calibration already shows the escape: a later version appends a NEW record
beside the old one, never over it. This module generalises that into a SERIES with explicit version binding.

A SERIES for one logical record id is an ordered chain of files: the legacy v2.1/cycle2 record is the base, and
each later qualification appends ONE new record under its own version namespace. Every non-base record carries a
`version_forward` block binding it to the exact (version_context, source_commit, kernel_digest) it was derived on,
its own content digest, and the digest of the predecessor it SUPERSEDES — so the chain is a cryptographic line, not
a pile.

A checker selects the record bound to the tree it is verifying — NEVER a global "newest". Selection is by the
declared release context (source_commit + kernel_digest), the selected record's digest is re-checked (tamper), and
the whole chain is validated (duplicate / fork / broken link / rollback). Anything missing, tampered,
wrong-version, ambiguous or chain-broken is an explicit failure with no silent fallback.

This module is PURE: every function takes its inputs explicitly (records as dicts, the tree context as a
(commit, tree) pair), so the selector and chain validator are unit-tested on synthetic series without a real tree.
The one helper that reads git (`current_context`) is the only impure edge and declares encoding explicitly.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import subprocess

#: the key the binding block lives under, inside the record body
BLOCK = "version_forward"

#: the qualification round this tree is being verified for (owner's "declared release context"). The pyproject
#: version is the RELEASE (2.1.0, patch lane); the ROUND is the re-qualification identity after a wave divergence.
#: A checker verifies the record DECLARED for this round, bound to this tree — never a global "newest".
CURRENT_ROUND = "v2.2"

#: the v2.3 branch round (W1-DESIGN §2.6, authorized by ledger seq 13). In this round a record is the VERIFIED HEAD
#: of its own chain — selection by (round, kernel tree) stays the v2.2 rule, under ROUND's default.
BRANCH_ROUND = "v2.3"

#: the round the CALLER is verifying for. The default keeps every existing v2.2 path byte-identical; a round-v2.3
#: checker wraps its work in `in_round(BRANCH_ROUND)`.
ROUND: contextvars.ContextVar[str] = contextvars.ContextVar("round", default=CURRENT_ROUND)

#: the directory a round-v2.3 record series continues in: <stem of the v2.2 rel>-<k>.json, k = 1…
V23_DIR = "closure-evidence/v2/v2.3"


@contextlib.contextmanager
def in_round(r: str):
    """Run the body with ROUND set to `r` (restored on exit, exceptions included)."""
    token = ROUND.set(r)
    try:
        yield
    finally:
        ROUND.reset(token)


def _v23_series(root, v22_rel: str) -> list[str]:
    """The committed round-v2.3 rels continuing `v22_rel`'s series, in k order. The ks must be exactly 1..n — a gap,
    a leading zero or a non-numeric suffix is a broken series and raises (fail closed), never a silent skip."""
    stem = v22_rel.rsplit("/", 1)[-1][: -len(".json")]
    d = root / V23_DIR
    found: dict[int, str] = {}
    for p in sorted(d.glob(f"{stem}-*.json")) if d.is_dir() else []:
        suffix = p.name[len(stem) + 1: -len(".json")]
        if not (suffix.isdigit() and suffix == str(int(suffix))):
            raise ValueError(f"{V23_DIR}/{p.name}: not a -<k>.json member of the {stem} series (fail closed)")
        found[int(suffix)] = f"{V23_DIR}/{p.name}"
    if sorted(found) != list(range(1, len(found) + 1)):
        raise ValueError(f"the {stem} series under {V23_DIR} has ks {sorted(found)}, not 1..{len(found)} (fail closed)")
    return [found[k] for k in sorted(found)]


def _lf(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def digest_bytes(b: bytes) -> str:
    """The content digest of a record's bytes, line-ending normalised (the repo stores LF; a CRLF checkout must
    hash the same)."""
    return hashlib.sha256(_lf(b)).hexdigest()


def _canon(doc: dict) -> bytes:
    return json.dumps(doc, sort_keys=True, ensure_ascii=False).encode("utf-8")


def body_digest(doc: dict) -> str:
    """The self-digest of a record: the sha256 of its canonical body with its own stored `record_digest` removed
    (a value cannot commit to itself). The binding's `kernel_digest`/`source_commit`/`supersedes` ARE included, so
    tampering with any of them is caught."""
    d = json.loads(json.dumps(doc))              # deep copy
    blk = d.get(BLOCK)
    if isinstance(blk, dict):
        blk.pop("record_digest", None)
    return hashlib.sha256(_canon(d)).hexdigest()


def bind(doc: dict, *, version_context: str, source_commit: str, kernel_digest: str,
         predecessor_path: str, predecessor_bytes: bytes) -> dict:
    """Return `doc` with a `version_forward` block: its release binding, the digest of the predecessor it
    supersedes, and its own self-digest (computed last). `doc` must not already carry a block."""
    if BLOCK in doc:
        raise ValueError(f"{BLOCK} already present")
    out = dict(doc)
    out[BLOCK] = {
        "version_context": version_context,
        "source_commit": source_commit,
        "kernel_digest": kernel_digest,
        "supersedes": {"path": predecessor_path, "record_digest": digest_bytes(predecessor_bytes)},
    }
    out[BLOCK]["record_digest"] = body_digest(out)
    return out


def _binding(doc: dict) -> dict | None:
    b = doc.get(BLOCK)
    return b if isinstance(b, dict) else None


def validate_chain(series: list[tuple[str, dict, bytes]]) -> list[str]:
    """`series` is [(path, parsed_doc, raw_bytes)] ordered base-first. The base (index 0) is the legacy record and
    carries no block. Every later record must bind, self-verify, and supersede exactly its immediate predecessor's
    bytes. Returns a list of problems (empty = a sound chain). Detects: a base that claims to supersede, a non-base
    without a block, a self-digest that does not recompute (tamper), a supersede link whose digest is not the
    predecessor's (broken link / fork onto the wrong parent), a duplicate (version_context, source_commit) pair
    (replay), and a kernel_digest reappearing after it was already superseded (rollback)."""
    problems: list[str] = []
    if not series:
        return ["empty series"]
    base_path, base_doc, _ = series[0]
    if _binding(base_doc) is not None:
        problems.append(f"{base_path}: the base record must not carry a {BLOCK} block")
    seen_pair: set[tuple[str, str]] = set()
    for i in range(1, len(series)):
        path, doc, _ = series[i]
        b = _binding(doc)
        if b is None:
            problems.append(f"{path}: a superseding record carries no {BLOCK} block")
            continue
        if b.get("record_digest") != body_digest(doc):
            problems.append(f"{path}: record_digest does not recompute (tampered)")
        prev_path, _, prev_bytes = series[i - 1]
        sup = b.get("supersedes") or {}
        if sup.get("record_digest") != digest_bytes(prev_bytes):
            problems.append(f"{path}: supersedes a digest that is not its predecessor {prev_path} (broken chain)")
        # one record per (declared round, tree): a repeated pair is a duplicate head — the ambiguity, replay and
        # rollback-onto-a-sealed-(round,tree) cases all reduce to this, and the linear supersede link above stops an
        # old record being re-spliced as head. A v2.3 record binds the COMMIT it was derived on, not a sealed kernel
        # tree (the branch round re-measures on a moving tree), so its key is (round, source_commit).
        if b.get("version_context") == BRANCH_ROUND:
            pair = (b.get("version_context"), b.get("source_commit"))
            if pair in seen_pair:
                problems.append(f"{path}: duplicate (version_context, source_commit) {pair} — two v2.3 records "
                                f"bind one (round, commit) (ambiguous derivation / replay)")
        else:
            pair = (b.get("version_context"), b.get("kernel_digest"))
            if pair in seen_pair:
                problems.append(f"{path}: duplicate (version_context, kernel_digest) {pair} — two records bind one "
                                f"(round, tree) (ambiguous head / replay / rollback)")
        seen_pair.add(pair)
    return problems


def toposort(graph: dict[str, list[str]]) -> list[str]:
    """Kahn topological order of a dependency DAG `{node: [the nodes it depends on]}`, dependencies before dependents.
    Raises ValueError naming an unknown node referenced as a dependency, or the nodes left in a cycle (owner v2.2 #1:
    the dependency DAG is checked in topological order and a cyclic dependency is refused)."""
    deps = {n: set(ds) for n, ds in graph.items()}
    for n, ds in deps.items():
        unknown = ds - set(deps)
        if unknown:
            raise ValueError(f"{n} depends on unknown node(s) {sorted(unknown)}")
    order: list[str] = []
    done: set[str] = set()
    while len(order) < len(deps):
        ready = sorted(n for n, ds in deps.items() if n not in done and ds <= done)
        if not ready:
            raise ValueError(f"dependency cycle among {sorted(set(deps) - done)}")
        order.extend(ready)
        done.update(ready)
    return order


def select_for_tree(series: list[tuple[str, dict, bytes]], *, version_context: str, kernel_digest: str,
                    legacy_binding: tuple[str, str] | None = None) -> tuple[str, dict]:
    """Return the ONE record DECLARED for `version_context` and bound to `kernel_digest` (the tree being verified),
    or raise LookupError. Selection is by the declared round + tree, never a global "newest". `legacy_binding` is
    the (version_context, kernel_digest) the base record stands for, supplied by the caller (the base predates the
    block); omit it when the base is not a candidate for this round. Never falls back to another record: a context
    with no record, or more than one, is an error naming the case. Validates the chain first; a broken chain is
    never selected from."""
    chain_problems = validate_chain(series)
    if chain_problems:
        raise LookupError("chain invalid: " + "; ".join(chain_problems))
    if ROUND.get() == BRANCH_ROUND:
        # round v2.3 (W1-DESIGN §2.6): the record is the VERIFIED HEAD of its own chain — the arguments are ignored.
        # A head is never chosen across series; a base-only series has no round record and refuses.
        path, doc, _ = series[-1]
        b = _binding(doc)
        if b is None:
            raise LookupError(f"no record in the series of {path} for round {BRANCH_ROUND!r}; "
                              f"missing supersession — refusing to fall back")
        if b.get("record_digest") != body_digest(doc):
            raise LookupError(f"{path}: record_digest does not recompute (tampered)")
        return path, doc
    want = (version_context, kernel_digest)
    matches: list[tuple[str, dict]] = []
    for path, doc, _ in series:
        b = _binding(doc)
        if b is None:
            if legacy_binding is not None and legacy_binding == want:
                matches.append((path, doc))
        elif (b.get("version_context"), b.get("kernel_digest")) == want:
            if b.get("record_digest") != body_digest(doc):
                raise LookupError(f"{path}: record_digest does not recompute (tampered)")
            matches.append((path, doc))
    if not matches:
        raise LookupError(f"no record declared for round {version_context!r} binds this tree "
                          f"(kernel_digest {kernel_digest[:12]}); missing supersession — refusing to fall back")
    if len(matches) > 1:
        raise LookupError("ambiguous head: " + ", ".join(p for p, _ in matches) + " all bind this (round, tree)")
    return matches[0]


def current_context(root) -> tuple[str, str]:
    """(HEAD commit, HEAD:aisef2 tree) for the working tree at `root` — the impure edge, encoding declared."""
    def git(*a: str) -> str:
        return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True,
                              encoding="utf-8", check=True).stdout.strip()
    return git("rev-parse", "HEAD"), git("rev-parse", "HEAD:aisef2")


# --- the shared generator/checker API every currency group wires in (one audited copy of the selection and
#     provenance logic, so "no global newest / explicit binding / provenance integrity" is not re-implemented
#     per group). A group supplies only its own build/problems/render and its two record paths. ---

def load_series(root, legacy_rel: str, v22_rel: str) -> list[tuple[str, dict, bytes]]:
    """The record series for one logical id, base-first: the legacy record then its v2.2 supersession (each only
    if present). In round v2.3 the series continues with the committed round records
    closure-evidence/v2/v2.3/<stem>-<k>.json in k order (fail closed on a broken k sequence)."""
    rels = [legacy_rel, v22_rel]
    if ROUND.get() == BRANCH_ROUND:
        rels += _v23_series(root, v22_rel)
    out = []
    for rel in rels:
        p = root / rel
        if p.exists():
            b = p.read_bytes()
            out.append((rel, json.loads(b), b))
    return out


def write_supersession(root, legacy_rel: str, v22_rel: str, body: dict, *, render) -> tuple[int, str]:
    """Append the CURRENT_ROUND supersession of `legacy_rel` at `v22_rel`, bound to this round + tree, superseding
    the legacy record by digest. `body` is the already-built record body (no block). Append-only: refuses to
    rewrite an existing v2.2 record with other bytes; a no-op if it already records this derivation. The legacy
    record is never touched. Returns (rc, message). In round v2.3 the predecessor is the chain HEAD and the output
    is the next closure-evidence/v2/v2.3/<stem>-<k>.json, opened "x" (append-only); the binding's kernel_digest is
    provenance only — v2.3 selection is by chain head, never by tree."""
    base = root / legacy_rel
    if not base.exists():
        return 1, f"{legacy_rel} (the base record) is missing"
    if ROUND.get() == BRANCH_ROUND:
        series = load_series(root, legacy_rel, v22_rel)
        head_rel, head_doc, head_bytes = series[-1]
        if {k: v for k, v in head_doc.items() if k != BLOCK} == body:
            return 0, f"{head_rel} already records this derivation: nothing written"
        stem = v22_rel.rsplit("/", 1)[-1][: -len(".json")]
        k = sum(1 for rel, _, _ in series if rel.startswith(V23_DIR + "/")) + 1
        out_rel = f"{V23_DIR}/{stem}-{k}.json"
        commit, tree = current_context(root)
        rec = bind(body, version_context=BRANCH_ROUND, source_commit=commit, kernel_digest=tree,
                   predecessor_path=head_rel, predecessor_bytes=head_bytes)
        out = root / out_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "x", encoding="utf-8", newline="\n") as f:
            f.write(render(rec))
        return 0, f"wrote {out_rel}: round {BRANCH_ROUND}, kernel {tree[:12]}"
    base_bytes = base.read_bytes()
    out = root / v22_rel
    if out.exists():
        existing = {k: v for k, v in json.loads(out.read_text(encoding="utf-8")).items() if k != BLOCK}
        if existing == body:
            return 0, f"{v22_rel} already records this derivation: nothing written"
        return 1, f"refused: {v22_rel} exists with other bytes — a record is never rewritten"
    commit, tree = current_context(root)
    rec = bind(body, version_context=CURRENT_ROUND, source_commit=commit, kernel_digest=tree,
               predecessor_path=legacy_rel, predecessor_bytes=base_bytes)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rec), encoding="utf-8")
    return 0, f"wrote {v22_rel}: round {CURRENT_ROUND}, kernel {tree[:12]}"


def resolve_upstream(root, legacy_rel: str, v22_rel: str, *, version_context: str = CURRENT_ROUND,
                     kernel_digest: str | None = None) -> tuple[str, dict]:
    """Cross-record resolution (owner v2.2 #1): return (path, body) of the UPSTREAM dependency record DECLARED for
    `version_context` and bound to `kernel_digest` (the tree being verified), body with its `version_forward` block
    stripped so a dependent checker reads the dependency exactly as its own legacy check would. Selection is
    context-bound and provenance-verified (the chain is validated and the selected record's self-digest re-checked by
    `select_for_tree`); it never falls back. The legacy v2.1 base carries no block and is passed no `legacy_binding`,
    so it is NOT a candidate in the v2.2 round — a v2.2 dependent never resolves a v2.1 upstream (v2.1 and v2.2 are
    not mixed). A dependency with no supersession for this round, or an ambiguous / tampered / cross-version one,
    raises LookupError naming the case."""
    if kernel_digest is None:
        _, kernel_digest = current_context(root)
    path, rec = select_for_tree(load_series(root, legacy_rel, v22_rel),
                                version_context=version_context, kernel_digest=kernel_digest)
    return path, {k: v for k, v in rec.items() if k != BLOCK}


def check_supersession(root, legacy_rel: str, v22_rel: str, *, derive_body, problems, render) -> list[str]:
    """Context-bound currency check for CURRENT_ROUND: select the record declared for this round and bound to this
    tree (never a global newest, never a silent fallback), then apply the group's OWN verdict logic — `problems`
    on the freshly-derived body and an exact `render` equality against the selected record. Same strictness as the
    legacy check; only selection differs. The legacy check stays the v2.1 path, unchanged."""
    _, tree = current_context(root)
    try:
        path, rec = select_for_tree(load_series(root, legacy_rel, v22_rel), version_context=CURRENT_ROUND,
                                    kernel_digest=tree)
    except LookupError as e:
        return [str(e)]
    recorded = {k: v for k, v in rec.items() if k != BLOCK}
    fresh = derive_body()
    out = list(problems(fresh))
    if render(recorded) != render(fresh):
        out.append(f"{path} does not re-derive from the tree")
    return out


if __name__ == "__main__":   # pragma: no cover — a runnable self-check of the mechanism on synthetic records
    base = {"record": "BASE", "n": 1}
    base_b = _canon(base)
    one = bind({"record": "V2.2", "sources": {"a": "x"}}, version_context="2.2.0", source_commit="c1" * 20,
               kernel_digest="k1" * 20, predecessor_path="base.json", predecessor_bytes=base_b)
    ser = [("base.json", base, base_b), ("v22.json", one, _canon(one))]
    assert validate_chain(ser) == [], validate_chain(ser)
    assert select_for_tree(ser, version_context="2.2.0", kernel_digest="k1" * 20)[1]["record"] == "V2.2"
    try:
        select_for_tree(ser, version_context="9.9.9", kernel_digest="k1" * 20)
        raise SystemExit("wrong-version should have refused")
    except LookupError:
        pass
    tampered = json.loads(json.dumps(one)); tampered["sources"]["a"] = "TAMPERED"
    assert any("tampered" in p for p in validate_chain([("base.json", base, base_b),
                                                        ("v22.json", tampered, _canon(tampered))]))
    print("version_forward self-check: OK")
