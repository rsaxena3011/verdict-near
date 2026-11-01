"""Slice-2 integration tests: demo server end to end with the NEAR
chain layer mocked. Stdlib unittest, offline, no real RPC.

Run from build/verdict-near/:  python3 -m unittest tests.test_slice2_integration -v
(or discover: python3 -m unittest discover -s tests -v)

What is mocked and what is real:
- REAL: app/server.py HTTP surface, the baseline VERDICT engine, the
  receipt hash + re-check, the milestone gate, and app/anchor.py's
  NearAnchor backend (env-selected, backend name "near-testnet").
- MOCKED: near/client.py's NearRpc class only. FakeNearRpc below is an
  in-memory implementation of the verdict_receipts contract's
  semantics exactly as written in near/contract/verdict_receipts.js:
  record_receipt is first-writer-wins per hash and validates the hash
  shape and the verdict enum; get_receipt returns the stored record or
  null; every function call returns a fake tx hash. This is the seam
  the demo server itself defines: swap NearRpc and the whole stack
  above it runs unchanged, which is what the testnet deploy relies on.
"""

import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT / "app", ROOT / "near", ROOT / "vendor"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


class FakeNearRpc:
    """In-memory stand-in for client.NearRpc, contract-faithful."""

    instances = []

    def __init__(self, rpc_url=None):
        self.rpc_url = rpc_url or "mock://testnet"
        self.receipts = {}  # receipt_hash -> record (contract storage)
        self.calls = []  # (method_name, args) audit trail
        self._nonce = 0
        FakeNearRpc.instances.append(self)

    # -- chain surface used by anchor.NearAnchor ---------------------

    def view_call(self, contract_id, method_name, args=None):
        args = args or {}
        if method_name == "get_receipt":
            record = self.receipts.get(args.get("receipt_hash"))
            # Mirror the real client exactly: the contract returns
            # JSON null for a miss and near/client.py decodes that to
            # None (review round 1, M-1: an earlier {} here drifted
            # from the real client's return contract).
            return dict(record) if record else None
        raise AssertionError(f"unexpected view method {method_name}")

    def function_call(self, signer_id, private_key, contract_id, method_name, args, gas=0, deposit=0):
        self.calls.append((method_name, dict(args)))
        if method_name == "record_receipt":
            h = args["receipt_hash"]
            # Mirror the contract's validation exactly (round 2, N-1):
            # lowercase sha256 hex, verdict enum, question cap.
            import re

            if not (isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h)):
                raise AssertionError("contract would reject: receipt_hash must be a lowercase sha256 hex string")
            if args["verdict"] not in ("ALLOW", "BLOCK", "REVIEW"):
                raise AssertionError("contract would reject: bad verdict")
            if len(args.get("question") or "") > 1024:
                raise AssertionError("contract would reject: question over the 1024 cap")
            if h not in self.receipts:  # first writer wins
                self._nonce += 1
                self.receipts[h] = {
                    "receipt_hash": h,
                    "verdict": args["verdict"],
                    "question": args.get("question", ""),
                    "recorder": signer_id,
                    "anchored_at": "2026-11-02T00:00:00.000Z",
                    # The real contract stores tx_hash null in the
                    # record (it cannot know its own tx hash); the
                    # fabricated hash below lives ONLY in this call's
                    # return value, like a real broadcast result.
                    "tx_hash": None,
                }
            fake_tx = hashlib.sha256(f"fake-tx-for-{h}".encode()).hexdigest()
            return {"transaction": {"hash": fake_tx}, "status": {"SuccessValue": ""}}
        raise AssertionError(f"unexpected call method {method_name}")

    def status(self):
        return {
            "chain_id": "testnet",
            "latest_block_height": 424242,
            "latest_block_hash": "fakelatestblockhash",
            "protocol_version": 0,
        }


def _post(base, path, payload):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_status(base, path, payload):
    """POST and return (http_status, body) without raising on 4xx/5xx."""
    import urllib.error

    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))


class OutageRpc:
    """An RPC layer that is simply down: every call raises."""

    def view_call(self, *a, **k):
        raise RuntimeError("simulated RPC outage")

    def function_call(self, *a, **k):
        raise RuntimeError("simulated RPC outage")

    def status(self):
        raise RuntimeError("simulated RPC outage")


class TestServerWithMockedChain(unittest.TestCase):
    """Boot the real server with NEAR_* env set, so anchor_from_env
    selects NearAnchor, whose NearRpc is the fake."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["NEAR_ACCOUNT_ID"] = "recorder.testnet"
        os.environ["NEAR_PRIVATE_KEY"] = "ed25519:fake-not-used-by-the-mock"
        os.environ["NEAR_CONTRACT_ID"] = "verdict.testnet"
        import client

        cls._real_rpc = client.NearRpc
        client.NearRpc = FakeNearRpc  # the mocked chain layer

        import server as server_module

        # server.py anchors into ROOT/var at import; redirect its state
        # files into the temp dir so the test never touches real state.
        from anchor import NearAnchor
        from milestone import MilestoneGate

        cls.fake_rpc = FakeNearRpc()
        anchor = NearAnchor("recorder.testnet", "ed25519:fake", "verdict.testnet")
        anchor.rpc = cls.fake_rpc
        server_module.ANCHOR = anchor
        server_module.GATE = MilestoneGate(Path(cls.tmp.name) / "milestones.json", anchor)
        # /api/near/status constructs its own NearRpc: it is the fake
        # class too (patched above), so status stays offline.

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        import client

        client.NearRpc = cls._real_rpc
        for var in ("NEAR_ACCOUNT_ID", "NEAR_PRIVATE_KEY", "NEAR_CONTRACT_ID"):
            os.environ.pop(var, None)
        cls.tmp.cleanup()

    # -- the flow --------------------------------------------------------

    def test_near_status_reports_mocked_chain(self):
        out = _get(self.base, "/api/near/status")
        self.assertEqual(out["anchor_backend"], "near-testnet")
        self.assertEqual(out["chain_id"], "testnet")
        self.assertIsNone(out["rpc_error"])

    def test_anchor_writes_through_the_chain_layer(self):
        out = _post(self.base, "/api/investigate", {"case": "block_contradiction"})
        h = out["receipt_hash"]
        self.assertNotIn(h, self.fake_rpc.receipts)
        anchored = _post(self.base, "/api/anchor", {"case": "block_contradiction"})
        record = anchored["anchor"]
        self.assertEqual(record["backend"], "near-testnet")
        self.assertEqual(record["contract_id"], "verdict.testnet")
        self.assertEqual(record["receipt_hash"], h)
        # the chain layer saw exactly one record_receipt call, carrying
        # the server-computed hash and the engine verdict, no forgery
        # surface: the server re-ran the case instead of trusting us.
        record_calls = [a for (m, a) in self.fake_rpc.calls if m == "record_receipt"]
        self.assertTrue(any(a["receipt_hash"] == h and a["verdict"] == "BLOCK" for a in record_calls))
        # and the record the contract stored is readable back
        self.assertEqual(self.fake_rpc.receipts[h]["verdict"], "BLOCK")

    def test_verify_ok_and_tamper_fails_over_mocked_chain(self):
        inv = _post(self.base, "/api/investigate", {"case": "allow_consistent"})
        _post(self.base, "/api/anchor", {"case": "allow_consistent"})
        ok = _post(self.base, "/api/verify", {"receipt": inv["receipt"], "verdict": inv["verdict"]})
        self.assertTrue(ok["ok"])
        self.assertTrue(ok["anchored"])
        # Readback honesty (round 2, N-1): on the view path the anchor
        # record's record_id is None, because the contract stores
        # tx_hash null by design; the write path knew the tx hash,
        # the read path cannot invent it.
        self.assertIsNone(ok["anchor"]["record_id"])
        self.assertEqual(ok["anchor"]["backend"], "near-testnet")
        tampered = json.loads(json.dumps(inv["receipt"]))
        tampered["findings"][0]["evidence"][0]["quote"] = tampered["findings"][0]["evidence"][0][
            "quote"
        ].replace("22:00", "22:0X")
        bad = _post(self.base, "/api/verify", {"receipt": tampered, "verdict": inv["verdict"]})
        self.assertFalse(bad["ok"])
        self.assertFalse(bad["anchored"])  # edited receipt hashes to nothing on chain

    def test_milestone_gate_runs_on_chain_anchored_receipts(self):
        created = _post(
            self.base,
            "/api/milestone/create",
            {"milestone_id": "ms-slice2", "amount": "10", "beneficiary": "cafe-operator.testnet"},
        )
        self.assertEqual(created["state"], "HELD")
        # release endpoint anchors the case receipt on the (mocked)
        # chain first, then the gate checks the anchor: BLOCK refuses.
        refused = _post(
            self.base, "/api/milestone/release", {"milestone_id": "ms-slice2", "case": "block_contradiction"}
        )
        self.assertFalse(refused["released"])
        self.assertEqual(refused["milestone"]["state"], "HELD")
        block_hash = [a["receipt_hash"] for (m, a) in self.fake_rpc.calls if m == "record_receipt"][-1]
        self.assertIn(block_hash, self.fake_rpc.receipts)
        # ALLOW releases through the same chain-anchored path.
        released = _post(
            self.base, "/api/milestone/release", {"milestone_id": "ms-slice2", "case": "allow_consistent"}
        )
        self.assertTrue(released["released"])
        self.assertEqual(released["milestone"]["state"], "RELEASED")

    def test_rpc_outage_surfaces_as_error_never_as_not_anchored(self):
        # Review round 1, M-1: a down chain must be loud. Before the
        # fix, NearAnchor.get swallowed every exception and returned
        # None, so /api/verify would have answered a confident
        # "anchored": false during an outage. Now the outage is a
        # server error on both the write and the read path.
        import server as server_module

        anchor = server_module.ANCHOR
        good_rpc = anchor.rpc
        anchor.rpc = OutageRpc()
        try:
            status, body = _post_status(self.base, "/api/anchor", {"case": "allow_consistent"})
            self.assertEqual(status, 500)
            self.assertIn("outage", body["error"])
            inv = _post(self.base, "/api/investigate", {"case": "allow_consistent"})
            status, body = _post_status(
                self.base, "/api/verify", {"receipt": inv["receipt"], "verdict": inv["verdict"]}
            )
            self.assertEqual(status, 500)
            self.assertIn("outage", body["error"])
        finally:
            anchor.rpc = good_rpc
        # And with the chain back, the same receipt verifies normally
        # (the outage left no corrupt state behind).
        _post(self.base, "/api/anchor", {"case": "allow_consistent"})
        ok = _post(self.base, "/api/verify", {"receipt": inv["receipt"], "verdict": inv["verdict"]})
        self.assertTrue(ok["ok"])


class TestClientNonceLock(unittest.TestCase):
    """The per-instance lock in near/client.py function_call (round 1
    minor, round 2 N-3 coverage): while one signed call holds the
    lock, a second signed call from another thread must wait instead
    of racing the nonce read. Fully offline: the RPC methods are
    stubbed on the instance."""

    def test_second_signed_call_waits_for_the_lock(self):
        import base58

        import client

        rpc = client.NearRpc("mock://testnet")
        private, _public = client.generate_keypair()
        rpc.access_key_nonce = lambda account_id, public_key_str: 41
        rpc.status = lambda: {"latest_block_hash": base58.b58encode(b"\x02" * 32).decode()}
        rpc._rpc = lambda method, params: {"status": {"SuccessValue": ""}, "transaction": {"hash": "fake"}}

        result = {}

        def call():
            result["out"] = rpc.function_call("a.testnet", private, "verdict.testnet", "record_receipt", {})

        rpc._call_lock.acquire()
        thread = threading.Thread(target=call, daemon=True)
        thread.start()
        thread.join(timeout=1.0)
        try:
            self.assertTrue(thread.is_alive(), "second signed call did not wait for the lock (nonce race open)")
            self.assertNotIn("out", result)
        finally:
            rpc._call_lock.release()
        thread.join(timeout=10)
        self.assertIn("out", result)


if __name__ == "__main__":
    unittest.main()
