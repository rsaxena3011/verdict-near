"""Milestone gate: money moves only on a verified ALLOW receipt.

WINDOW WORK (C133, built 2026-11-01); this is the business-track
mechanism. A milestone holds an amount for a beneficiary. Release is
attempted with a verdict receipt and succeeds only when ALL of these
hold, checked by the same re-check a third party can run:

  1. the receipt hash recomputes exactly (nothing was edited);
  2. the receipt is anchored (its hash exists in the anchor backend);
  3. re-running the deterministic engine on the receipt reproduces
     the claimed verdict;
  4. that verdict is ALLOW.

BLOCK, REVIEW, a tampered receipt, or an unanchored receipt all refuse,
and the refusal reason is recorded on the milestone. A released
milestone cannot release twice.

State lives in a JSON file here for the standalone demo. The NEAR
contract (near/contract/verdict_receipts.js) carries the on-chain
SUBSET of these rules: release_milestone checks that the receipt is
anchored in the contract and that the stored verdict is ALLOW before
transferring. It cannot recompute the receipt hash or re-run the
engine (checks 1 and 3 above), and its receipts are neither
recorder-bound nor milestone-bound, so the strict gate is this file;
the contract's release check is the weaker on-chain counterpart, a
distinction the review rounds recorded (round 1, B3) and the deploy
gate in DEPLOY_RUNBOOK.md governs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from receipts import receipt_hash, recheck


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MilestoneGate:
    def __init__(self, path: Path, anchor_backend):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.anchor = anchor_backend

    # ------------------------------------------------------------ store

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------ api

    def create(self, milestone_id: str, amount: str, beneficiary: str) -> dict:
        data = self._load()
        if milestone_id in data:
            raise ValueError(f"milestone {milestone_id} already exists")
        record = {
            "milestone_id": milestone_id,
            "amount": amount,
            "beneficiary": beneficiary,
            "state": "HELD",
            "created_at": _now(),
            "released_at": None,
            "receipt_hash": None,
            "refusals": [],
        }
        data[milestone_id] = record
        self._save(data)
        return record

    def get(self, milestone_id: str) -> dict | None:
        return self._load().get(milestone_id)

    def attempt_release(self, milestone_id: str, receipt: dict, verdict: str) -> dict:
        data = self._load()
        record = data.get(milestone_id)
        if record is None:
            raise ValueError(f"unknown milestone {milestone_id}")
        if record["state"] == "RELEASED":
            return {"released": False, "reason": "already released; a milestone releases once", "milestone": record}

        h = receipt_hash(receipt, verdict)
        anchored = self.anchor.get(h)
        check = recheck(receipt, verdict)

        if anchored is None:
            reason = "receipt is not anchored; an unanchored verdict is the author's word only"
        elif not check["verdict_match"]:
            reason = (
                f"re-check failed: the engine recomputes {check['recomputed_verdict']} "
                f"from this receipt, not {verdict}"
            )
        elif verdict != "ALLOW":
            reason = f"verdict is {verdict}; only a verified ALLOW releases a milestone"
        else:
            record["state"] = "RELEASED"
            record["released_at"] = _now()
            record["receipt_hash"] = h
            self._save(data)
            return {"released": True, "reason": "verified ALLOW receipt; milestone released", "milestone": record}

        record["refusals"].append({"at": _now(), "receipt_hash": h, "reason": reason})
        self._save(data)
        return {"released": False, "reason": reason, "milestone": record}
