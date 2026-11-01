"""Slice-1 tests for the C133 window work. Stdlib unittest, offline.

Run from build/verdict-near/:  python3 -m unittest discover -s tests -v

Covers: the demo cases produce the engine-correct verdicts on the
unmodified baseline engine; the receipt hash commits to the exact
receipt; the third-party re-check reproduces verdicts and catches both
forgery (wrong claimed verdict) and tampering (edited quote); the local
anchor log round-trips and is idempotent; the milestone gate releases
only on a verified ALLOW; the NEAR client key handling and transaction
serialiser are self-consistent.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT / "app", ROOT / "near", ROOT / "vendor"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from anchor import LocalAnchorLog  # noqa: E402
from engine_runner import list_cases, run_case  # noqa: E402
from milestone import MilestoneGate  # noqa: E402
from receipts import receipt_hash, recheck  # noqa: E402


class TestCases(unittest.TestCase):
    def test_all_cases_match_expected_verdict(self):
        cases = list_cases()
        self.assertEqual(len(cases), 5)
        for meta in cases:
            out = run_case(meta["id"])
            self.assertEqual(out["verdict"], meta["expected"], meta["id"])

    def test_block_case_reason_quotes_both_sides(self):
        out = run_case("block_contradiction")
        self.assertIn("22:00", out["reason"])
        self.assertIn("23:15", out["reason"])


class TestReceiptHashAndRecheck(unittest.TestCase):
    def test_hash_is_deterministic_and_content_bound(self):
        out = run_case("block_contradiction")
        h1 = receipt_hash(out["receipt"], out["verdict"])
        h2 = receipt_hash(out["receipt"], out["verdict"])
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)
        tampered = json_copy(out["receipt"])
        tampered["findings"][0]["evidence"][0]["quote"] = tampered["findings"][0]["evidence"][0]["quote"].replace(
            "22:00", "22:0X"
        )
        self.assertNotEqual(receipt_hash(tampered, out["verdict"]), h1)

    def test_recheck_reproduces_every_case_verdict(self):
        for meta in list_cases():
            out = run_case(meta["id"])
            check = recheck(out["receipt"], out["verdict"])
            self.assertTrue(check["verdict_match"], meta["id"])
            self.assertEqual(check["recomputed_verdict"], meta["expected"])

    def test_recheck_catches_a_forged_verdict_claim(self):
        out = run_case("allow_consistent")
        check = recheck(out["receipt"], "BLOCK")  # claim BLOCK on an ALLOW receipt
        self.assertFalse(check["verdict_match"])
        self.assertEqual(check["recomputed_verdict"], "ALLOW")


def json_copy(obj):
    import copy

    return copy.deepcopy(obj)


class TestAnchorAndGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.anchor = LocalAnchorLog(Path(self.tmp.name) / "anchors.jsonl")
        self.gate = MilestoneGate(Path(self.tmp.name) / "milestones.json", self.anchor)

    def tearDown(self):
        self.tmp.cleanup()

    def test_anchor_roundtrip_and_idempotent(self):
        out = run_case("allow_consistent")
        r1 = self.anchor.anchor(out["receipt"], out["verdict"])
        r2 = self.anchor.anchor(out["receipt"], out["verdict"])
        self.assertEqual(r1["receipt_hash"], r2["receipt_hash"])
        self.assertEqual(r1["record_id"], r2["record_id"])
        self.assertEqual(self.anchor.get(r1["receipt_hash"])["verdict"], "ALLOW")
        self.assertIsNone(self.anchor.get("0" * 64))

    def test_gate_releases_only_on_verified_allow(self):
        self.gate.create("ms-1", "10", "cafe-operator.testnet")
        block = run_case("block_contradiction")
        self.anchor.anchor(block["receipt"], block["verdict"])
        refused = self.gate.attempt_release("ms-1", block["receipt"], block["verdict"])
        self.assertFalse(refused["released"])
        self.assertIn("BLOCK", refused["reason"])
        self.assertEqual(self.gate.get("ms-1")["state"], "HELD")
        self.assertEqual(len(self.gate.get("ms-1")["refusals"]), 1)

        allow = run_case("allow_consistent")
        self.anchor.anchor(allow["receipt"], allow["verdict"])
        released = self.gate.attempt_release("ms-1", allow["receipt"], allow["verdict"])
        self.assertTrue(released["released"])
        self.assertEqual(self.gate.get("ms-1")["state"], "RELEASED")

        again = self.gate.attempt_release("ms-1", allow["receipt"], allow["verdict"])
        self.assertFalse(again["released"])  # no double release

    def test_gate_refuses_unanchored_and_tampered(self):
        self.gate.create("ms-2", "5", "cafe-operator.testnet")
        allow = run_case("allow_consistent")
        unanchored = self.gate.attempt_release("ms-2", allow["receipt"], allow["verdict"])
        self.assertFalse(unanchored["released"])
        self.assertIn("not anchored", unanchored["reason"])

        self.anchor.anchor(allow["receipt"], allow["verdict"])
        tampered = json_copy(allow["receipt"])
        tampered["findings"][0]["claim"] = "edited after anchoring"
        refused = self.gate.attempt_release("ms-2", tampered, "ALLOW")
        self.assertFalse(refused["released"])  # hash no longer resolves to the anchor


def _near_deps_available() -> bool:
    try:
        import base58  # noqa: F401
        import nacl.signing  # noqa: F401

        return True
    except ImportError:
        return False


@unittest.skipUnless(
    _near_deps_available(),
    "NEAR extras not installed (pip install -r requirements-near.txt, or the vendored vendor/ dir)",
)
class TestNearClient(unittest.TestCase):
    def test_keypair_roundtrip_and_signing(self):
        import nacl.signing

        from client import generate_keypair, parse_private_key, serialize_function_call_tx, sign_tx

        private, public = generate_keypair()
        signing_key, public_str, pub_bytes = parse_private_key(private)
        self.assertEqual(public_str, public)
        tx = serialize_function_call_tx(
            signer_id="someone.testnet",
            public_key_bytes=pub_bytes,
            nonce=7,
            receiver_id="verdict.testnet",
            block_hash_bytes=b"\x01" * 32,
            method_name="record_receipt",
            args=b'{"receipt_hash":"abc"}',
            gas=30_000_000_000_000,
            deposit=0,
        )
        signed = sign_tx(tx, signing_key, pub_bytes)
        self.assertEqual(len(signed), len(tx) + 65)  # key type byte + 64-byte signature
        import hashlib

        signature = signed[-64:]
        nacl.signing.VerifyKey(pub_bytes).verify(hashlib.sha256(tx).digest(), signature)

    def test_serialiser_rejects_bad_lengths(self):
        from client import NearError, serialize_function_call_tx

        with self.assertRaises(NearError):
            serialize_function_call_tx("a.testnet", b"\x00" * 31, 1, "b.testnet", b"\x01" * 32, "m", b"{}", 1, 0)


if __name__ == "__main__":
    unittest.main()
