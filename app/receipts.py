"""Receipt canonicalisation, hashing, and third-party re-check.

WINDOW WORK (C133, built 2026-11-01). The baseline VERDICT engine
(baseline/src/verdict/) emits a verdict plus a receipt dict. This module
defines the exact bytes that identify a verdict:

    payload = {"receipt": <receipt dict>, "verdict": <verdict string>}
    bytes   = JSON, keys sorted, separators (",", ":"), UTF-8
    hash    = SHA-256 hex of those bytes

That hash is what gets anchored (local anchor log today, NEAR testnet
contract when configured). The re-check is the point of the entry: a
third party who holds only the receipt can

  1. recompute the hash and compare it with the anchored record;
  2. rebuild the engine's Investigation from the receipt alone and
     re-run the deterministic decide() to confirm the verdict follows
     from the quoted evidence (no trust in whoever produced it).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_BASELINE_SRC = Path(__file__).resolve().parent.parent / "baseline" / "src"
if str(_BASELINE_SRC) not in sys.path:
    sys.path.insert(0, str(_BASELINE_SRC))

from verdict.investigator import Investigation  # noqa: E402
from verdict.models import (  # noqa: E402
    EvidenceLine,
    Finding,
    Question,
    SourceKind,
    SourceRef,
)
from verdict.verdict_engine import decide  # noqa: E402


def canonical_payload(receipt: dict, verdict: str) -> bytes:
    """The exact byte string a receipt hash commits to."""
    payload = {"receipt": receipt, "verdict": verdict}
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def receipt_hash(receipt: dict, verdict: str) -> str:
    """SHA-256 hex of the canonical payload."""
    return hashlib.sha256(canonical_payload(receipt, verdict)).hexdigest()


def investigation_from_receipt(receipt: dict) -> Investigation:
    """Rebuild the engine input from a receipt dict alone.

    Every field decide() reads is carried in the receipt: findings with
    verbatim quotes and source refs, contradiction links, unanswerable
    flags, and the missing-source list.
    """
    findings: list[Finding] = []
    for raw in receipt.get("findings", []):
        evidence = [
            EvidenceLine(
                quote=e["quote"],
                ref=SourceRef(
                    source=SourceKind(e["source"]),
                    document_id=e["document_id"],
                    locator=e["locator"],
                ),
            )
            for e in raw.get("evidence", [])
        ]
        findings.append(
            Finding(
                id=raw["id"],
                claim=raw["claim"],
                evidence=evidence,
                contradicts=list(raw.get("contradicts", [])),
                unanswerable=bool(raw.get("unanswerable", False)),
            )
        )
    return Investigation(
        question=Question(receipt.get("question", "")),
        findings=findings,
        missing_sources=[SourceKind(s) for s in receipt.get("missing_sources", [])],
        live_nemotron=False,
        notes=list(receipt.get("notes", [])),
    )


def recheck(receipt: dict, claimed_verdict: str) -> dict:
    """Re-run the deterministic engine on a receipt and compare verdicts.

    Returns {"recomputed_verdict": ..., "verdict_match": bool,
    "recomputed_reason": ...}. This never trusts the claimed verdict:
    the engine derives it again from the quoted evidence.
    """
    result = decide(investigation_from_receipt(receipt))
    return {
        "recomputed_verdict": result.verdict.value,
        "verdict_match": result.verdict.value == claimed_verdict,
        "recomputed_reason": result.reason,
    }
