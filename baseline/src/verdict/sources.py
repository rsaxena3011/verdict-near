"""Source connectors. v0: file-backed (fixtures/). Live Zetaris connectors land
after the Oct 22 recon confirms source types and MCP availability."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from .models import EvidenceLine, Finding, SourceKind, SourceRef


class SourceError(Exception):
    """The source could not be reached or read. Never swallowed silently."""


class SourceConnector(ABC):
    """One connected source behind the federation."""

    kind: SourceKind

    @abstractmethod
    def fetch(self, question: str) -> list[Finding]:
        """Return findings relevant to the question. Raise SourceError if the
        source is unreachable so the engine can downgrade to REVIEW instead
        of guessing (invariant 2)."""
        ...


class FileSource(SourceConnector):
    """v0 connector: reads findings from a JSON fixture file.

    Format: {"findings": [{"id": ..., "claim": ..., "evidence": [{"quote": ...,
    "document_id": ..., "locator": ...}], "contradicts": [...],
    "unanswerable": bool}], "unreachable": bool}
    """

    def __init__(self, kind: SourceKind, path: Path):
        self.kind = kind
        self.path = path

    def fetch(self, question: str) -> list[Finding]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SourceError(f"{self.kind.value}: {exc}") from exc
        if data.get("unreachable"):
            raise SourceError(f"{self.kind.value}: marked unreachable")
        findings: list[Finding] = []
        for raw in data.get("findings", []):
            evidence = [
                EvidenceLine(
                    quote=e["quote"],
                    ref=SourceRef(
                        source=self.kind,
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
        return findings
