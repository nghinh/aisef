"""Ed25519 evidence-seal primitives — the C-2 surface (A2, lane L2-SIGN; design docs/v2.3/drafts/A2-SIGNING-DESIGN-DRAFT.md).

One ephemeral keypair per run signs ONE payload `{run_id, kernel_digest, journal, anchor}` at finalize (§3.1): the
signature covers the anchor, the anchor covers the manifest, the manifest covers every evidence byte — a post-hoc
consistent rewrite of a finished run directory is REFUTABLE by an operator who kept the run's public key (and the
anchor) off-box. The private half is never persisted anywhere (design §4).

Backend: the `cryptography` package (owner package #1 decision 8 direction: a maintained library, no vendored
original Ed25519), imported lazily and ONLY here. Fail-closed: when the backend is missing, every operation that
needs the curve raises `SigningUnavailable` — there is no unsigned fallback. `verify` stays total over *inputs*:
a malformed public key, message or signature returns False and never raises.

Declared limitations (design §13): authenticity is conditional on the escrow's custody (L1); Python cannot zeroize
the private half, its lifetime ceiling is the process's (L4); the seal binds bytes, not truth — a kernel compromised
during the run signs its own lies (L5); `kernel_digest` is self-reported by the signing process (L7).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
import re
import secrets

from aisef2.product.contract import canonical

FORMAT_ID = "aisef-v2-seal/1"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX128 = re.compile(r"[0-9a-f]{128}")
#: the Ed25519 group order (RFC 8032 §5.1); a signature's s MUST be < L or the encoding is malleable
_L = 2 ** 252 + 27742317777372353535851937790883648493
_JOURNAL_KEYS = {"path": str, "sha256": str, "lines": int, "head": str}


class SigningUnavailable(RuntimeError):
    """The signing backend is not installed — fail closed, never an unsigned fallback (decision 8)."""


def _ed25519():
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as e:
        raise SigningUnavailable(
            "evidence signing needs the 'cryptography' package (pip install 'aisef[signing]'); "
            "there is no unsigned fallback") from e
    return ed25519


@dataclasses.dataclass(frozen=True)
class Keypair:
    """One run's ephemeral Ed25519 keypair. The seed is the private half: it lives only in this process and is
    never written anywhere by this module."""
    seed: bytes

    def __post_init__(self):
        if not isinstance(self.seed, bytes) or len(self.seed) != 32:
            raise ValueError("an Ed25519 seed is exactly 32 bytes")

    @property
    def pubkey_hex(self) -> str:
        e = _ed25519()
        return e.Ed25519PrivateKey.from_private_bytes(self.seed).public_key().public_bytes_raw().hex()


def generate() -> Keypair:
    """A fresh keypair from the OS CSPRNG. One per run, never reused, never derived from anything (design §4.1)."""
    _ed25519()  # fail closed BEFORE a run starts relying on a keypair it cannot sign with
    return Keypair(secrets.token_bytes(32))


def fingerprint(pubkey_hex: str) -> str:
    """sha256 of the 32 RAW key bytes, hex64 — THE `run/begin.signer` value (FORMAT-4 §4.1)."""
    if not isinstance(pubkey_hex, str) or not _HEX64.fullmatch(pubkey_hex):
        raise ValueError(f"not an Ed25519 public key (64 lowercase hex): {pubkey_hex!r}")
    return hashlib.sha256(bytes.fromhex(pubkey_hex)).hexdigest()


def sign(keypair: Keypair, message: bytes) -> str:
    """The RFC 8032 (deterministic) signature, hex128."""
    if not isinstance(message, bytes):
        raise ValueError("a message is bytes")
    e = _ed25519()
    return e.Ed25519PrivateKey.from_private_bytes(keypair.seed).sign(message).hex()


def verify(pubkey_hex: str, message: bytes, sig_hex: str) -> bool:
    """Strict RFC 8032 verification. Malformed input — wrong types, wrong lengths, non-hex, s >= L, a public key
    that does not decode to a canonical point — is False, never an exception. A missing backend is not an input:
    it raises `SigningUnavailable` (fail closed; a False there would read as 'forged')."""
    if not isinstance(pubkey_hex, str) or not isinstance(sig_hex, str) or not isinstance(message, bytes):
        return False
    if not _HEX64.fullmatch(pubkey_hex) or not _HEX128.fullmatch(sig_hex):
        return False
    raw_sig = bytes.fromhex(sig_hex)
    if int.from_bytes(raw_sig[32:], "little") >= _L:  # explicit, backend-independent (N2)
        return False
    e = _ed25519()
    try:
        e.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex)).verify(raw_sig, message)
        return True
    except Exception:
        return False


def seal_payload(run_id: str, kernel_digest: str, journal_info: dict, anchor: str) -> dict:
    """The §3.1 payload, canonical-ready. Every field is validated here so a malformed seal can never be SIGNED —
    verification strictness alone would only catch it after the run is gone."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id is a non-empty string")
    for name, v in (("kernel_digest", kernel_digest), ("anchor", anchor)):
        if not isinstance(v, str) or not _HEX64.fullmatch(v):
            raise ValueError(f"{name} is 64 lowercase hex, got {v!r}")
    if not isinstance(journal_info, dict) or set(journal_info) != set(_JOURNAL_KEYS) \
            or any(not isinstance(journal_info[k], t) or isinstance(journal_info[k], bool)
                   for k, t in _JOURNAL_KEYS.items()):
        raise ValueError(f"journal_info is exactly {{path: str, sha256: str, lines: int, head: str}}, got {journal_info!r}")
    for k in ("sha256", "head"):
        if not _HEX64.fullmatch(journal_info[k]):
            raise ValueError(f"journal_info[{k!r}] is 64 lowercase hex, got {journal_info[k]!r}")
    return {"format": FORMAT_ID, "run_id": run_id, "kernel_digest": kernel_digest,
            "journal": {k: journal_info[k] for k in ("path", "sha256", "lines", "head")}, "anchor": anchor}


def seal_message(payload: dict) -> bytes:
    """Domain prefix + canonical JSON — the exact bytes the run's key signs."""
    return FORMAT_ID.encode("ascii") + b"\n" + canonical(payload).encode("utf-8")


def write_seal(path: pathlib.Path, payload: dict, keypair: Keypair) -> dict:
    """Signs the payload and writes SEAL.json with the anchor file's exact discipline (lineage.write_anchor's:
    created exclusively, never through a symbolic link, read-only, fsync'd). Returns the written document.
    SEAL.json is deliberately OUTSIDE the evidence manifest globs (design M3): the signature covers the manifest
    through the anchor, so it must not be inside what the manifest covers."""
    doc = {"format": FORMAT_ID, "payload": payload, "pubkey": keypair.pubkey_hex,
           "sig": sign(keypair, seal_message(payload))}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o444)
    with os.fdopen(fd, "wb") as f:
        f.write((canonical(doc) + "\n").encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    return doc


def read_seal(path: pathlib.Path) -> dict:
    """The document `write_seal` wrote — strictly. Exactly the keys {format, payload, pubkey, sig}, the known
    format id, hex-shaped key and signature, a dict payload; anything else — unknown keys, truncation, another
    format — is refused with ValueError. Semantic checks (the V-checks) are the verifier's, not the codec's."""
    try:
        doc = json.loads(pathlib.Path(path).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{path} is not a readable seal: {e}") from e
    if not isinstance(doc, dict) or set(doc) != {"format", "payload", "pubkey", "sig"}:
        raise ValueError(f"{path} is not a seal: exactly the keys format/payload/pubkey/sig are required")
    if doc["format"] != FORMAT_ID:
        raise ValueError(f"{path} claims format {doc['format']!r}, not {FORMAT_ID!r}")
    if not isinstance(doc["pubkey"], str) or not _HEX64.fullmatch(doc["pubkey"]) \
            or not isinstance(doc["sig"], str) or not _HEX128.fullmatch(doc["sig"]) \
            or not isinstance(doc["payload"], dict):
        raise ValueError(f"{path} is not a seal: pubkey is hex64, sig is hex128, payload is an object")
    return doc
