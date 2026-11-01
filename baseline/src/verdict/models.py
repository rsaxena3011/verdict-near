"""Data models. Plain dataclasses — no LLM, no network, nothing to mock."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Verdict(Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"


class SourceKind(Enum):
    LOCKS = "locks"      # locked facts (boss's canon)
    DRAFTS = "drafts"    # current drafts under investigation
    REVIEWS = "reviews"  # critic / reviewer notes


@dataclass(frozen=True)
class SourceRef:
    """Where one quoted line came from. All four fields are required for a
    quote to count as evidence (invariant 1)."""

    source: SourceKind
    document_id: str   # e.g. lock id "LK-0042" or draft version "draft-v9"
    locator: str       # line / page / scene reference, e.g. "Act 2, sc 14"


@dataclass(frozen=True)
class EvidenceLine:
    """One quoted line. `text` is the verbatim quote, never a paraphrase."""

    quote: str
    ref: SourceRef


@dataclass
class Finding:
    """One claim the investigator pulled out of the sources. The investigator
    (Nemotron) is allowed to suggest contradictions; the engine only honors
    ones with both sides quoted (invariant 3)."""

    id: str
    claim: str
    evidence: list[EvidenceLine] = field(default_factory=list)
    contradicts: list[str] = field(default_factory=list)  # other finding ids
    unanswerable: bool = False


@dataclass(frozen=True)
class Question:
    text: str


@dataclass
class Receipt:
    """The thing attached to every verdict: the query, the rows, the source,
    the quoted lines. Serializable; the UI renders this verbatim."""

    question: str
    findings: list[Finding]
    missing_sources: list[SourceKind]
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "missing_sources": [s.value for s in self.missing_sources],
            "notes": self.notes,
            "findings": [
                {
                    "id": f.id,
                    "claim": f.claim,
                    "contradicts": f.contradicts,
                    "unanswerable": f.unanswerable,
                    "evidence": [
                        {
                            "quote": e.quote,
                            "source": e.ref.source.value,
                            "document_id": e.ref.document_id,
                            "locator": e.ref.locator,
                        }
                        for e in f.evidence
                    ],
                }
                for f in self.findings
            ],
        }


@dataclass
class VerdictResult:
    verdict: Verdict
    reason: str  # one plain-English line for the "why" panel
    receipt: Receipt
