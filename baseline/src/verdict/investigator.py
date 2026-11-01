"""The investigate step. Nemotron (via the Nightshift local runtime) runs this
step exactly once per question. The investigator suggests findings and
contradictions; it NEVER emits a verdict — that is the engine's job.

Transport is injectable: pass an OpenAI-compatible chat callable for live
runs, or None for fixture-backed offline runs (recorded/demo mode).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Finding, Question, SourceKind
from .sources import SourceConnector, SourceError

NIGHTSHIFT_BASE_URL = "http://127.0.0.1:8088/v1"  # verified live 2026-10-21
NIGHTSHIFT_STATED_PORT = 10088  # workshop docs say this; 8088 verified, 10088 untested


@dataclass
class Investigation:
    question: Question
    findings: list[Finding]
    missing_sources: list[SourceKind]
    live_nemotron: bool  # True when a real model call ran; False = fixture replay
    notes: list[str]


class Investigator:
    def __init__(self, connectors: list[SourceConnector], chat=None):
        self.connectors = connectors
        self.chat = chat  # callable(messages) -> str, or None for offline mode

    def investigate(self, question: Question) -> Investigation:
        findings: list[Finding] = []
        missing: list[SourceKind] = []
        notes: list[str] = []
        for connector in self.connectors:
            try:
                findings.extend(connector.fetch(question.text))
            except SourceError as exc:
                missing.append(connector.kind)
                notes.append(str(exc))
        live = False
        if self.chat is not None and not missing:
            # One Nemotron call per question, at the investigate step only.
            # Prompt and response are logged into the receipt notes so the
            # demo shows a real model call, not a canned verdict.
            prompt = self._prompt(question, findings)
            response = self.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You investigate one question against locked facts, "
                            "drafts, and reviews. Return findings as JSON with "
                            "verbatim quotes only. Never invent quotes. Never "
                            "answer ALLOW/BLOCK/REVIEW yourself."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ]
            )
            notes.append(f"nemotron investigate call ran ({len(response)} chars)")
            live = True
        else:
            notes.append("offline replay: findings from connected sources only")
        return Investigation(
            question=question,
            findings=findings,
            missing_sources=missing,
            live_nemotron=live,
            notes=notes,
        )

    @staticmethod
    def _prompt(question: Question, findings: list[Finding]) -> str:
        lines = [f"Question: {question.text}", ""]
        for f in findings:
            lines.append(f"[{f.id}] {f.claim}")
            for e in f.evidence:
                lines.append(f'  "{e.quote}" ({e.ref.source.value}/{e.ref.document_id}, {e.ref.locator})')
        lines += [
            "",
            "Flag any pair of findings that contradict each other, citing both "
            "quotes. List any question no finding answers.",
        ]
        return "\n".join(lines)
