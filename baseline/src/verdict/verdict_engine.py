"""The deterministic verdict layer. Pure rules, no LLM, no network.

Decision order (first match wins):
1. Any connected source missing/unreachable            -> REVIEW (missing source)
2. A lock finding and a draft finding provably
   contradict, with BOTH sides quoted                  -> BLOCK (receipt: both quotes)
3. Two review findings contradict, both sides quoted    -> REVIEW (conflict shown)
4. A claimed contradiction with a side missing/unquoted -> REVIEW (refuse to invent)
5. No finding answers the question                      -> REVIEW (cannot verify)
6. Otherwise                                            -> ALLOW

Same inputs => same output (invariant 4). No state anywhere.
"""

from __future__ import annotations

from .investigator import Investigation
from .models import Finding, Receipt, SourceKind, Verdict, VerdictResult


def _has_quotes(f: Finding) -> bool:
    return bool(f.evidence) and all(bool(e.quote.strip()) for e in f.evidence)


def _lock_side(f: Finding) -> bool:
    return any(e.ref.source == SourceKind.LOCKS for e in f.evidence)


def _draft_side(f: Finding) -> bool:
    return any(e.ref.source == SourceKind.DRAFTS for e in f.evidence)


def _review_side(f: Finding) -> bool:
    return any(e.ref.source == SourceKind.REVIEWS for e in f.evidence)


def decide(inv: Investigation) -> VerdictResult:
    receipt = Receipt(
        question=inv.question.text,
        findings=inv.findings,
        missing_sources=inv.missing_sources,
        notes=inv.notes,
    )

    # 1. Missing source: never ALLOW on a partial federation.
    if inv.missing_sources:
        names = ", ".join(s.value for s in inv.missing_sources)
        return VerdictResult(
            Verdict.REVIEW,
            f"Source unreachable: {names}. Cannot rule without the full federation.",
            receipt,
        )

    by_id = {f.id: f for f in inv.findings}

    # 2/3/4. Contradictions the investigator flagged.
    for f in inv.findings:
        for other_id in f.contradicts:
            other = by_id.get(other_id)
            if other is None:
                continue
            if not (_has_quotes(f) and _has_quotes(other)):
                # 4. Claimed contradiction, quotes missing: refuse to invent.
                return VerdictResult(
                    Verdict.REVIEW,
                    f"Contradiction claimed between {f.id} and {other.id} but a "
                    "side is unquoted. Needs a human read.",
                    receipt,
                )
            if _lock_side(f) and _draft_side(other) or _lock_side(other) and _draft_side(f):
                lock_f = f if _lock_side(f) else other
                draft_f = other if lock_f is f else f
                lock_q = lock_f.evidence[0]
                draft_q = draft_f.evidence[0]
                return VerdictResult(
                    Verdict.BLOCK,
                    f'Draft breaks lock {lock_q.ref.document_id}: lock says '
                    f'"{lock_q.quote}" ({lock_q.ref.locator}), draft says '
                    f'"{draft_q.quote}" ({draft_q.ref.locator}).',
                    receipt,
                )
            if _review_side(f) and _review_side(other):
                return VerdictResult(
                    Verdict.REVIEW,
                    f"Reviews conflict ({f.id} vs {other.id}); both quoted, needs "
                    "a human read.",
                    receipt,
                )

    # 5. Nothing answers the question.
    if not inv.findings or all(f.unanswerable for f in inv.findings):
        return VerdictResult(
            Verdict.REVIEW,
            "No connected source answers this question. Cannot verify — no invented evidence.",
            receipt,
        )

    # 6. Everything checks out.
    return VerdictResult(
        Verdict.ALLOW,
        "All connected sources answer consistently with the locked facts.",
        receipt,
    )
