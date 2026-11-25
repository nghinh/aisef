"""A2 primitives (aisef2/journal/sign.py): RFC 8032 vectors, strictness negatives (design N1/N2/N6), the seal codec
discipline, and the fail-closed no-backend contract. The design is docs/v2.3/drafts/A2-SIGNING-DESIGN-DRAFT.md."""
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

from aisef2.journal import sign as sg
from aisef2.product.contract import canonical

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: F401
    HAVE_BACKEND = True
except ImportError:
    HAVE_BACKEND = False

#: RFC 8032 §7.1 TEST 1–3: (seed, public key, message, signature), all hex
VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0"
     "595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eae"
     "b4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9"
     "716ed28dc027beceea1ec40a"),
]
#: every module of the backend's import chain, so a sys.modules=None patch defeats the from-import's cache
_CHAIN = {name: None for name in (
    "cryptography", "cryptography.hazmat", "cryptography.hazmat.primitives",
    "cryptography.hazmat.primitives.asymmetric", "cryptography.hazmat.primitives.asymmetric.ed25519")}


def _payload():
    return sg.seal_payload("run-1", "aa" * 32,
                           {"path": "run/journals/j.jsonl", "sha256": "bb" * 32, "lines": 7, "head": "cc" * 32},
                           "dd" * 32)


class BackendPolicy(unittest.TestCase):
    """Fail-closed, and never a silent skip where the gate lives."""

    def test_ci_never_skips_the_vectors(self):
        if os.environ.get("CI") and not HAVE_BACKEND:
            self.fail("CI must install the signing backend (tests.yml unit step installs cryptography); "
                      "the RFC 8032 vectors were about to be silently skipped")

    def test_missing_backend_fails_closed_never_unsigned(self):
        with mock.patch.dict(sys.modules, _CHAIN):
            with self.assertRaises(sg.SigningUnavailable):
                sg.generate()
            with self.assertRaises(sg.SigningUnavailable):
                sg.sign(sg.Keypair(b"\x00" * 32), b"m")
            with self.assertRaises(sg.SigningUnavailable):
                sg.Keypair(b"\x00" * 32).pubkey_hex  # noqa: B018 — the property IS the operation
            with self.assertRaises(sg.SigningUnavailable):
                sg.verify("00" * 32, b"", "00" * 64)  # well-formed inputs reach the curve: raise, don't say "forged"

    def test_malformed_input_is_false_even_without_a_backend(self):
        s_ge_l = ("00" * 32) + (sg._L).to_bytes(32, "little").hex()
        with mock.patch.dict(sys.modules, _CHAIN):
            for pub, msg, sig in [
                ("zz" * 32, b"", "00" * 64),            # non-hex key
                ("00" * 31, b"", "00" * 64),            # short key
                ("00" * 32, b"", "00" * 63),            # short signature
                ("00" * 32, b"", "00" * 65),            # long signature
                ("00" * 32, "not-bytes", "00" * 64),    # message is not bytes
                (None, b"", "00" * 64),                 # key is not a string
                ("00" * 32, b"", s_ge_l),               # s >= L: rejected before any arithmetic
            ]:
                self.assertFalse(sg.verify(pub, msg, sig), (pub, msg, sig))


@unittest.skipUnless(HAVE_BACKEND, "cryptography not installed (BackendPolicy keeps this loud on CI)")
class Rfc8032(unittest.TestCase):
    def test_the_vectors_sign_and_verify_exactly(self):
        for seed, pub, msg, sig in VECTORS:
            kp = sg.Keypair(bytes.fromhex(seed))
            self.assertEqual(kp.pubkey_hex, pub)
            self.assertEqual(sg.sign(kp, bytes.fromhex(msg)), sig)
            self.assertTrue(sg.verify(pub, bytes.fromhex(msg), sig))

    def test_any_flip_refutes(self):
        seed, pub, msg, sig = VECTORS[2]
        message = bytes.fromhex(msg)
        flip = lambda h, i: h[:i] + format(int(h[i], 16) ^ 1, "x") + h[i + 1:]  # noqa: E731
        self.assertFalse(sg.verify(pub, message, flip(sig, 0)))
        self.assertFalse(sg.verify(pub, message, flip(sig, 127)))
        self.assertFalse(sg.verify(flip(pub, 30), message, sig))
        self.assertFalse(sg.verify(pub, bytes.fromhex("af83"), sig))
        self.assertFalse(sg.verify(pub, message, VECTORS[0][3]))            # another run's signature
        self.assertFalse(sg.verify(VECTORS[0][1], message, sig))            # another run's key

    def test_s_plus_L_malleation_is_rejected(self):
        seed, pub, msg, sig = VECTORS[0]
        raw = bytes.fromhex(sig)
        malleated = raw[:32] + (int.from_bytes(raw[32:], "little") + sg._L).to_bytes(32, "little")
        self.assertFalse(sg.verify(pub, bytes.fromhex(msg), malleated.hex()))

    def test_a_non_canonical_or_invalid_public_key_is_false(self):
        _, pub, msg, sig = VECTORS[0]
        self.assertFalse(sg.verify("ff" * 32, bytes.fromhex(msg), sig))

    def test_deterministic_signatures_fresh_keys(self):
        kp = sg.generate()
        self.assertEqual(len(kp.seed), 32)
        self.assertEqual(sg.sign(kp, b"m"), sg.sign(kp, b"m"))
        self.assertNotEqual(kp.pubkey_hex, sg.generate().pubkey_hex)
        self.assertEqual(sg.Keypair(kp.seed).pubkey_hex, kp.pubkey_hex)

    def test_a_seed_is_exactly_32_bytes(self):
        for bad in (b"short", b"\x00" * 33, "9d" * 32, None):
            with self.assertRaises(ValueError):
                sg.Keypair(bad)


class FingerprintAndPayload(unittest.TestCase):
    """Pure-stdlib surface: runs everywhere, backend or not."""

    def test_fingerprint_is_sha256_of_the_raw_bytes_not_the_hex(self):
        pub = VECTORS[0][1]
        self.assertEqual(sg.fingerprint(pub), hashlib.sha256(bytes.fromhex(pub)).hexdigest())
        self.assertNotEqual(sg.fingerprint(pub), hashlib.sha256(pub.encode()).hexdigest())

    def test_fingerprint_refuses_malformation(self):
        for bad in ("AA" * 32, "aa" * 31, "aa" * 33, "zz" * 32, b"aa" * 32, None):
            with self.assertRaises(ValueError):
                sg.fingerprint(bad)

    def test_seal_payload_shape(self):
        p = _payload()
        self.assertEqual(list(p), ["format", "run_id", "kernel_digest", "journal", "anchor"])
        self.assertEqual(p["format"], "aisef-v2-seal/1")
        self.assertEqual(list(p["journal"]), ["path", "sha256", "lines", "head"])

    def test_seal_payload_refuses_malformation(self):
        ok = {"path": "p", "sha256": "bb" * 32, "lines": 7, "head": "cc" * 32}
        for args in [
            ("", "aa" * 32, ok, "dd" * 32),                                     # empty run id
            ("r", "AA" * 32, ok, "dd" * 32),                                    # uppercase digest
            ("r", "aa" * 32, ok, "dd" * 31),                                    # short anchor
            ("r", "aa" * 32, {**ok, "extra": 1}, "dd" * 32),                    # unknown journal key
            ("r", "aa" * 32, {k: ok[k] for k in list(ok)[:3]}, "dd" * 32),      # missing journal key
            ("r", "aa" * 32, {**ok, "lines": True}, "dd" * 32),                 # bool is not a count
            ("r", "aa" * 32, {**ok, "sha256": "zz" * 32}, "dd" * 32),           # non-hex journal digest
            ("r", "aa" * 32, "not-a-dict", "dd" * 32),
        ]:
            with self.assertRaises(ValueError):
                sg.seal_payload(*args)

    def test_seal_message_is_domain_prefix_plus_canonical(self):
        p = _payload()
        m = sg.seal_message(p)
        self.assertTrue(m.startswith(b"aisef-v2-seal/1\n"))
        self.assertEqual(m[len(b"aisef-v2-seal/1\n"):], canonical(p).encode("utf-8"))


class SealFile(unittest.TestCase):
    def test_read_seal_is_strict(self):
        good = {"format": "aisef-v2-seal/1", "payload": {"k": 1}, "pubkey": "aa" * 32, "sig": "bb" * 64}
        cases = [
            {**good, "extra": 1},                                   # unknown key
            {k: good[k] for k in ("format", "payload", "pubkey")},  # missing key
            {**good, "format": "aisef-v2-seal/2"},                  # another format id
            {**good, "pubkey": "AA" * 32},                          # uppercase key
            {**good, "sig": "bb" * 63},                             # short signature
            {**good, "payload": [1]},                               # payload is not an object
            [good],                                                 # the document is not an object
        ]
        with tempfile.TemporaryDirectory() as d:
            for i, doc in enumerate(cases):
                p = pathlib.Path(d, f"seal-{i}.json")
                p.write_text(json.dumps(doc), encoding="utf-8")
                with self.assertRaises(ValueError, msg=doc):
                    sg.read_seal(p)
            trunc = pathlib.Path(d, "trunc.json")
            trunc.write_bytes(json.dumps(good).encode()[:20])
            with self.assertRaises(ValueError):
                sg.read_seal(trunc)
            with self.assertRaises(ValueError):
                sg.read_seal(pathlib.Path(d, "absent.json"))

    @unittest.skipUnless(HAVE_BACKEND, "cryptography not installed (BackendPolicy keeps this loud on CI)")
    def test_write_seal_roundtrip_and_the_anchor_discipline(self):
        kp = sg.generate()
        payload = _payload()
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d, "SEAL.json")
            doc = sg.write_seal(p, payload, kp)
            self.assertEqual(sg.read_seal(p), doc)
            self.assertTrue(sg.verify(doc["pubkey"], sg.seal_message(payload), doc["sig"]))
            self.assertEqual(sg.fingerprint(doc["pubkey"]), sg.fingerprint(kp.pubkey_hex))
            raw = p.read_bytes()
            self.assertTrue(raw.endswith(b"\n"))
            self.assertEqual((canonical(doc) + "\n").encode("utf-8"), raw)      # byte-deterministic
            with self.assertRaises(FileExistsError):                            # O_EXCL: never overwrite a seal
                sg.write_seal(p, payload, kp)
            if os.name != "nt":                                                 # 0444 until V21-41(b)'s Windows pass
                self.assertEqual(os.stat(p).st_mode & 0o222, 0)


if __name__ == "__main__":
    unittest.main()
