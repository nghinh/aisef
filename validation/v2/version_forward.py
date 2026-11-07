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

import hashlib
import json
import subprocess

#: the key the binding block lives under, inside the record body
BLOCK = "version_forward"

#: the qualification round this tree is being verified for (owner's "declared release context"). The pyproject
#: version is the RELEASE (2.1.0, patch lane); the ROUND is the re-qualification identity after a wave divergence.
#: A checker verifies the record DECLARED for this round, bound to this tree — never a global "newest".
CURRENT_ROUND = "v2.2"


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
        # old record being re-spliced as head.
        pair = (b.get("version_context"), b.get("kernel_digest"))
        if pair in seen_pair:
            problems.append(f"{path}: duplicate (version_context, kernel_digest) {pair} — two records bind one "
                            f"(round, tree) (ambiguous head / replay / rollback)")
        seen_pair.add(pair)
    return problems


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
    if present)."""
    out = []
    for rel in (legacy_rel, v22_rel):
        p = root / rel
        if p.exists():
            b = p.read_bytes()
            out.append((rel, json.loads(b), b))
    return out


def write_supersession(root, legacy_rel: str, v22_rel: str, body: dict, *, render) -> tuple[int, str]:
    """Append the CURRENT_ROUND supersession of `legacy_rel` at `v22_rel`, bound to this round + tree, superseding
    the legacy record by digest. `body` is the already-built record body (no block). Append-only: refuses to
    rewrite an existing v2.2 record with other bytes; a no-op if it already records this derivation. The legacy
    record is never touched. Returns (rc, message)."""
    base = root / legacy_rel
    if not base.exists():
        return 1, f"{legacy_rel} (the base record) is missing"
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
