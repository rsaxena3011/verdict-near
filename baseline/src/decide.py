"""The deterministic decision layer. This is NOT an agent and is labelled
as such in every receipt: it applies fixed rules to the final evidence
record the two agents produced, so the same record always yields the same
verdict.

Rules, per lock:
- BROKEN -> BLOCK: a draft or review finding whose structured
  `contradicts` field names this lock is part of the final record AND at
  least one of its quotes survived validation.
- NO EVIDENCE -> REVIEW: the final record holds no validated quote for
  this lock at all. Reason recorded as "no quoted evidence". A verdict is
  never ALLOW without a quoted source line (the hard invariant).
- AGENT-ONLY BREAK CLAIM -> REVIEW: an agent claims a break that the
  structured record cannot confirm (for example a paraphrase). The
  disagreement stays visible in the receipt instead of being hidden.
- NOT SETTLED -> REVIEW: the Investigator's final proposal for the lock
  is not ALLOW. A validated quote that merely mentions the lock's
  people, place, or topic is not support; if the Investigator judges
  the evidence does not settle the lock, the verdict is REVIEW.
- HOLDS -> ALLOW: validated quotes exist, none of them contradict the
  lock, and the Investigator's final proposal is ALLOW.
"""


def decide(lock, proposals, challenges, all_rows):
    lock_id = lock["finding_id"]
    by_id = {r["finding_id"]: r for r in all_rows}
    prop = next((p for p in proposals if p.get("lock_id") == lock_id), {})
    chal = next((c for c in challenges if c.get("lock_id") == lock_id), {})

    evidence_ids = []
    for src in (prop, chal):
        for fid in src.get("evidence_finding_ids", []):
            if fid in by_id and fid not in evidence_ids:
                evidence_ids.append(fid)
    quotes = []
    for fid in evidence_ids:
        q = by_id[fid]["quote"]
        if q not in quotes:
            quotes.append(q)
    for src in (prop, chal):
        for q in src.get("quotes", []):
            if q not in quotes:
                quotes.append(q)

    contradicting = [
        fid for fid in evidence_ids if (by_id[fid].get("contradicts") or "") == lock_id
    ]
    agent_says_block = prop.get("proposed_verdict") == "BLOCK" or (
        chal.get("stance") == "CHALLENGE" and "contradict" in (chal.get("reasoning") or "").lower()
    )

    if contradicting and quotes:
        verdict, basis = "BLOCK", f"structured contradiction in the record: {', '.join(contradicting)}"
    elif not quotes:
        verdict, basis = "REVIEW", "no quoted evidence"
    elif agent_says_block:
        verdict, basis = "REVIEW", "agent claims a break the structured record cannot confirm"
    elif prop.get("proposed_verdict") != "ALLOW":
        verdict, basis = "REVIEW", "investigator judges the quoted evidence does not settle the lock"
    else:
        verdict, basis = "ALLOW", "quoted evidence supports the lock; no contradiction in the record"

    return {
        "lock_id": lock_id,
        "lock_claim": lock.get("claim"),
        "lock_quote": lock.get("quote"),
        "verdict": verdict,
        "basis": basis,
        "evidence_finding_ids": evidence_ids,
        "quotes": quotes,
        "investigator_proposal": prop.get("proposed_verdict"),
        "challenger_stance": chal.get("stance"),
    }
