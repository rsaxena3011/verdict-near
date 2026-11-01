"""Minimal NEAR JSON-RPC client. WINDOW WORK (C133, built 2026-11-01).

Stdlib + requests for transport. View calls need no key and no signing.
Signed function calls use PyNaCl + base58 (vendored under vendor/ at
the repo root, because this VM has no system packages for them); the transaction
serialiser below implements exactly one action shape, FunctionCall,
following the NEAR Borsh transaction layout.

Verified live from this VM on 2026-11-01: status() against
https://rpc.testnet.near.org returns chain_id "testnet". RPC through
this egress is slow (allow 20s+ timeouts).

Nothing in this module creates accounts or holds funds. A signed call
runs only when the caller supplies an account id, a private key, and a
contract id (env vars in the demo server; never committed).
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import sys
import threading
from pathlib import Path

import requests

_VENDOR = Path(__file__).resolve().parent.parent / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

DEFAULT_RPC = "https://rpc.testnet.near.org"
TIMEOUT = 30


class NearError(Exception):
    pass


# ---------------------------------------------------------------- keys


def parse_private_key(text: str):
    """Parse a NEAR private key string ("ed25519:<base58>").

    Returns (signing_key, public_key_str, public_key_bytes). The NEAR
    secret is seed(32) || public_key(32), base58-encoded.
    """
    import base58
    import nacl.signing

    if not text.startswith("ed25519:"):
        raise NearError("private key must start with 'ed25519:'")
    raw = base58.b58decode(text[len("ed25519:"):])
    if len(raw) != 64:
        raise NearError(f"private key decodes to {len(raw)} bytes, expected 64")
    seed, pub = raw[:32], raw[32:]
    signing_key = nacl.signing.SigningKey(seed)
    if bytes(signing_key.verify_key) != pub:
        raise NearError("private key seed does not match its public key half")
    return signing_key, "ed25519:" + base58.b58encode(pub).decode(), pub


def generate_keypair() -> tuple[str, str]:
    """Generate a fresh ed25519 keypair. Returns (private_key_str,
    public_key_str) in NEAR string formats. Local only; an implicit
    account id would be the hex of the public key bytes."""
    import base58
    import nacl.signing

    signing_key = nacl.signing.SigningKey.generate()
    seed = bytes(signing_key)
    pub = bytes(signing_key.verify_key)
    private = "ed25519:" + base58.b58encode(seed + pub).decode()
    public = "ed25519:" + base58.b58encode(pub).decode()
    return private, public


# ---------------------------------------------------------------- borsh


def _u32(n: int) -> bytes:
    return struct.pack("<I", n)


def _u64(n: int) -> bytes:
    return struct.pack("<Q", n)


def _u128(n: int) -> bytes:
    return n.to_bytes(16, "little")


def _string(s: str) -> bytes:
    b = s.encode("utf-8")
    return _u32(len(b)) + b


def _bytes(b: bytes) -> bytes:
    return _u32(len(b)) + b


def serialize_function_call_tx(
    signer_id: str,
    public_key_bytes: bytes,
    nonce: int,
    receiver_id: str,
    block_hash_bytes: bytes,
    method_name: str,
    args: bytes,
    gas: int,
    deposit: int,
) -> bytes:
    """Serialise an unsigned Transaction with one FunctionCall action."""
    if len(public_key_bytes) != 32 or len(block_hash_bytes) != 32:
        raise NearError("public key and block hash must be 32 bytes each")
    action = (
        b"\x02"  # Action enum variant 2 = FunctionCall
        + _string(method_name)
        + _bytes(args)
        + _u64(gas)
        + _u128(deposit)
    )
    return (
        _string(signer_id)
        + b"\x00"  # key type 0 = ed25519
        + public_key_bytes
        + _u64(nonce)
        + _string(receiver_id)
        + block_hash_bytes
        + _u32(1)
        + action
    )


def sign_tx(tx_bytes: bytes, signing_key, public_key_bytes: bytes) -> bytes:
    """Sign a serialised Transaction and return the SignedTransaction
    bytes ready for broadcast_tx_commit."""
    digest = hashlib.sha256(tx_bytes).digest()
    signature = signing_key.sign(digest).signature  # 64 bytes
    return tx_bytes + b"\x00" + signature  # key type 0 + signature


# ---------------------------------------------------------------- rpc


class NearRpc:
    def __init__(self, rpc_url: str = DEFAULT_RPC):
        self.rpc_url = rpc_url
        # Serialises signed calls from this client instance: the
        # nonce is read from the chain and then used, so two threads
        # doing that concurrently for the same signer would read the
        # same nonce and one transaction would be rejected as a
        # duplicate. The demo server is threaded and shares one
        # NearRpc (inside NearAnchor), so the read-nonce-then-
        # broadcast section of function_call runs under this lock
        # (review round 1, minor: nonce race).
        self._call_lock = threading.Lock()

    def _rpc(self, method: str, params) -> dict:
        resp = requests.post(
            self.rpc_url,
            json={"jsonrpc": "2.0", "id": "verdict-near", "method": method, "params": params},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise NearError(f"RPC {method} error: {json.dumps(data['error'])[:300]}")
        return data["result"]

    def status(self) -> dict:
        result = self._rpc("status", [])
        return {
            "chain_id": result["chain_id"],
            "latest_block_height": result["sync_info"]["latest_block_height"],
            "latest_block_hash": result["sync_info"]["latest_block_hash"],
            "protocol_version": result["protocol_version"],
        }

    def view_call(self, contract_id: str, method_name: str, args: dict | None = None) -> dict:
        """Unsigned view call. Returns the decoded JSON result."""
        args_b64 = base64.b64encode(
            json.dumps(args or {}).encode("utf-8")
        ).decode()
        result = self._rpc(
            "query",
            {
                "request_type": "call_function",
                "finality": "final",
                "account_id": contract_id,
                "method_name": method_name,
                "args_base64": args_b64,
            },
        )
        raw = bytes(result["result"])
        return json.loads(raw.decode("utf-8")) if raw else {}

    def access_key_nonce(self, account_id: str, public_key_str: str) -> int:
        result = self._rpc(
            "query",
            {
                "request_type": "view_access_key",
                "finality": "final",
                "account_id": account_id,
                "public_key": public_key_str,
            },
        )
        return int(result["nonce"])

    def function_call(
        self,
        signer_id: str,
        private_key: str,
        contract_id: str,
        method_name: str,
        args: dict,
        gas: int = 30_000_000_000_000,
        deposit: int = 0,
    ) -> dict:
        """Signed function call, broadcast with commit finality.

        Only runs when a caller supplies real credentials. Returns the
        RPC result dict (contains transaction hash under
        result["transaction"]["hash"] on success).
        """
        import base58

        signing_key, public_key_str, pub_bytes = parse_private_key(private_key)
        with self._call_lock:
            nonce = self.access_key_nonce(signer_id, public_key_str) + 1
            status = self.status()
            block_hash = base58.b58decode(status["latest_block_hash"])
            tx = serialize_function_call_tx(
                signer_id=signer_id,
                public_key_bytes=pub_bytes,
                nonce=nonce,
                receiver_id=contract_id,
                block_hash_bytes=block_hash,
                method_name=method_name,
                args=json.dumps(args).encode("utf-8"),
                gas=gas,
                deposit=deposit,
            )
            signed = sign_tx(tx, signing_key, pub_bytes)
            result = self._rpc(
                "broadcast_tx_commit", [base64.b64encode(signed).decode()]
            )
        status_value = result.get("status", {})
        if "Failure" in status_value:
            raise NearError(f"tx failed: {json.dumps(status_value)[:300]}")
        return result
