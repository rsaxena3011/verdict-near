"""Deterministic golden-path tests. Stdlib unittest: no network, no LLM, no deps."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from verdict.investigator import Investigation  # noqa: E402
from verdict.models import (  # noqa: E402
    EvidenceLine,
    Finding,
    Question,
    SourceKind,
    SourceRef,
    Verdict,
)
from verdict.verdict_engine import decide  # noqa: E402


def line(quote, source, doc="d1", loc="l1"):
    return EvidenceLine(
        quote=quote, ref=SourceRef(source=source, document_id=doc, locator=loc)
    )


def inv_with(*findings, missing=()):
    return Investigation(
        question=Question("q"),
        findings=list(findings),
        missing_sources=list(missing),
        live_nemotron=False,
        notes=["offline replay"],
    )


class TestVerdictEngine(unittest.TestCase):
    def test_planted_contradiction_blocks_with_both_quotes(self):
        lock = Finding(
            id="LK-1",
            claim="closes 22:00",
            evidence=[line("closes at 22:00 sharp", SourceKind.LOCKS, "locks-v3", "s2")],
            contradicts=["DR-1"],
        )
        draft = Finding(
            id="DR-1",
            claim="open till 23:15",
            evidence=[line("last customer left at 23:15", SourceKind.DRAFTS, "draft-v9", "sc7")],
        )
        r = decide(inv_with(lock, draft))
        self.assertEqual(r.verdict, Verdict.BLOCK)
        self.assertIn("22:00", r.reason)
        self.assertIn("23:15", r.reason)
        # receipt carries both sides
        quotes = [e.quote for f in r.receipt.findings for e in f.evidence]
        self.assertIn("closes at 22:00 sharp", quotes)
        self.assertIn("last customer left at 23:15", quotes)

    def test_missing_source_never_allows(self):
        lock = Finding(
            id="LK-1", claim="ok",
            evidence=[line("fine", SourceKind.LOCKS)],
        )
        r = decide(inv_with(lock, missing=[SourceKind.DRAFTS]))
        self.assertEqual(r.verdict, Verdict.REVIEW)
        self.assertIn("drafts", r.reason)

    def test_unquoted_contradiction_claim_degrades_to_review(self):
        lock = Finding(
            id="LK-1", claim="closes 22:00",
            evidence=[line("closes at 22:00 sharp", SourceKind.LOCKS)],
            contradicts=["DR-1"],
        )
        draft = Finding(id="DR-1", claim="open late", evidence=[])  # no quote
        r = decide(inv_with(lock, draft))
        self.assertEqual(r.verdict, Verdict.REVIEW)
        self.assertIn("unquoted", r.reason)

    def test_nothing_answers_means_review_not_invention(self):
        f = Finding(id="RV-1", claim="nothing here", unanswerable=True)
        r = decide(inv_with(f))
        self.assertEqual(r.verdict, Verdict.REVIEW)
        self.assertIn("Cannot verify", r.reason)

    def test_same_question_twice_identical_verdict(self):
        lock = Finding(
            id="LK-1", claim="closes 22:00",
            evidence=[line("closes at 22:00 sharp", SourceKind.LOCKS)],
        )
        r1 = decide(inv_with(lock))
        r2 = decide(inv_with(lock))
        self.assertEqual(r1.verdict, r2.verdict)
        self.assertEqual(r1.reason, r2.reason)

    def test_consistent_facts_allow(self):
        lock = Finding(
            id="LK-1", claim="owner Meera",
            evidence=[line("Owner: Meera.", SourceKind.LOCKS)],
        )
        draft = Finding(
            id="DR-1", claim="Meera in draft",
            evidence=[line("Meera wiped the counter.", SourceKind.DRAFTS)],
        )
        r = decide(inv_with(lock, draft))
        self.assertEqual(r.verdict, Verdict.ALLOW)

    def test_review_conflict_is_review_with_both_quoted(self):
        a = Finding(
            id="RV-1", claim="too late",
            evidence=[line("reads like midnight", SourceKind.REVIEWS)],
            contradicts=["RV-2"],
        )
        b = Finding(
            id="RV-2", claim="just right",
            evidence=[line("pacing feels right", SourceKind.REVIEWS)],
        )
        r = decide(inv_with(a, b))
        self.assertEqual(r.verdict, Verdict.REVIEW)
        self.assertIn("Reviews conflict", r.reason)


if __name__ == "__main__":
    unittest.main()
