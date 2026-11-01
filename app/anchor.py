"""Anchoring: record a receipt hash somewhere the verdict's author
cannot quietly rewrite it.

WINDOW WORK (C133, built 2026-11-01). Two backends share one record
shape, the same shape the NEAR contract stores:

    {"receipt_hash", "verdict", "question", "anchored_at",
     "backend", "record_id", "contract_id"}

- LocalAnchorLog: append-only JSONL file (one JSON object per line).
  This is the offline default: the demo runs end to end with no
  network and no account, and the record format is identical to the
  on-chain one, so the verify path does not change when the backend
  does.
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
        try:
            record = self.rpc.view_call(
                self.contract_id, "get_receipt", {"receipt_hash": h}
            )
        except Exception:
            return None
        if not record:
            return None
        return {
            "receipt_hash": record["receipt_hash"],
            "verdict": record["verdict"],
            "question": record["question"],
            "anchored_at": record["anchored_at"],
            "backend": self.backend,
            "record_id": record.get("tx_hash"),
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
