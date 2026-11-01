"""Anchoring: record a receipt hash somewhere the verdict's author
cannot quietly rewrite it.

WINDOW WORK (C133, built 2026-11-01). The two backends share the
receipt fields below; they are not claimed identical (review round
1, M10): the on-chain record additionally carries the recorder, and
the local record's record_id is a log position while the NEAR one is
a transaction hash on the write path and unknown on the read path.

    {"receipt_hash", "verdict", "question", "anchored_at",
     "backend", "record_id", "contract_id"}

- LocalAnchorLog: append-only JSONL file (one JSON object per line).
  This is the offline default: the demo runs end to end with no
  network and no account, and the shared fields mean the verify path
  does not change shape when the backend does.
- NearAnchor: record_receipt / get_receipt on the verdict_receipts
  contract (near/contract/) over NEAR testnet RPC. Active only when
  NEAR_ACCOUNT_ID, NEAR_PRIVATE_KEY and NEAR_CONTRACT_ID are set.
  Writes are signed function calls; reads are unsigned view calls.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_NEAR_DIR = Path(__file__).resolve().parent.parent / "near"
if str(_NEAR_DIR) not in sys.path:
    sys.path.insert(0, str(_NEAR_DIR))

from receipts import receipt_hash  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LocalAnchorLog:
    backend = "local"

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _records(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def anchor(self, receipt: dict, verdict: str) -> dict:
        h = receipt_hash(receipt, verdict)
        existing = self.get(h)
        if existing:
            return existing  # anchoring is idempotent per hash
        record = {
            "receipt_hash": h,
            "verdict": verdict,
            "question": receipt.get("question", ""),
            "anchored_at": _now(),
            "backend": self.backend,
            "record_id": f"local-{len(self._records()) + 1}",
            "contract_id": None,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def get(self, h: str) -> dict | None:
        for record in self._records():
            if record["receipt_hash"] == h:
                return record
        return None


class NearAnchor:
    backend = "near-testnet"

    def __init__(self, account_id: str, private_key: str, contract_id: str, rpc_url: str | None = None):
        from client import NearRpc

        self.account_id = account_id
        self.private_key = private_key
        self.contract_id = contract_id
        self.rpc = NearRpc(rpc_url) if rpc_url else NearRpc()

    def anchor(self, receipt: dict, verdict: str) -> dict:
        h = receipt_hash(receipt, verdict)
        existing = self.get(h)
        if existing:
            return existing
        result = self.rpc.function_call(
            signer_id=self.account_id,
            private_key=self.private_key,
            contract_id=self.contract_id,
            method_name="record_receipt",
            args={
                "receipt_hash": h,
                "verdict": verdict,
                "question": receipt.get("question", ""),
            },
        )
        # Read the stored record back (review round 1, M10): report
        # what the chain actually holds, not the locally computed
        # values. If another writer won the first-writer race, the
        # stored verdict differs from the one just computed, and the
        # caller must see that. Fall back to the local record only if
        # the read comes back empty (indexing lag).
        stored = self.get(h)
        if stored is not None:
            stored["record_id"] = result["transaction"]["hash"]
            return stored
        return {
            "receipt_hash": h,
            "verdict": verdict,
            "question": receipt.get("question", ""),
            "anchored_at": _now(),
            "backend": self.backend,
            "record_id": result["transaction"]["hash"],
            "contract_id": self.contract_id,
        }

    def get(self, h: str) -> dict | None:
        # Only a genuine on-chain miss returns None. An RPC failure
        # must NOT masquerade as "not anchored" (review round 1, M-1:
        # the verify path and the milestone gate both read anchored as
        # a boolean, so a swallowed outage would print a confident,
        # wrong "not anchored" during exactly the incident a judge
        # would probe). RPC exceptions therefore propagate: the server
        # surfaces them as an error, which is the honest state.
        record = self.rpc.view_call(
            self.contract_id, "get_receipt", {"receipt_hash": h}
        )
        if not record:
            return None
        return {
            "receipt_hash": record["receipt_hash"],
            "verdict": record["verdict"],
            "question": record["question"],
            "anchored_at": record["anchored_at"],
            "backend": self.backend,
            # record_id is the anchoring transaction hash. It is known
            # on the write path (anchor() takes it from the broadcast
            # result); a view call cannot recover it, and the contract
            # stores tx_hash as null by design, so on this read path
            # record_id is None: present-but-unknown, never invented
            # (review round 1, minor).
            "record_id": record.get("tx_hash"),
            # Who anchored this receipt on chain. The local backend
            # has no such field; dropping it here would hide exactly
            # the provenance the verify surface exists to show
            # (review round 1, M10).
            "recorder": record.get("recorder"),
            "contract_id": self.contract_id,
        }


def anchor_from_env(local_path: Path):
    """Pick the NEAR backend when fully configured, else the local log."""
    account = os.environ.get("NEAR_ACCOUNT_ID")
    key = os.environ.get("NEAR_PRIVATE_KEY")
    contract = os.environ.get("NEAR_CONTRACT_ID")
    if account and key and contract:
        return NearAnchor(account, key, contract, os.environ.get("NEAR_RPC_URL"))
    return LocalAnchorLog(local_path)
