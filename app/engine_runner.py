"""Run the baseline VERDICT engine on a bundled demo case.

WINDOW WORK (C133, built 2026-11-01). The engine, investigator, and
source connectors are the unmodified baseline (baseline/src/verdict/,
commit eb10947). This module only wires the demo cases (app/cases/) to
them through the baseline FileSource connector, offline: no model
call, no PC runtime, no credentials. The verdict is produced by the
baseline deterministic decide(), never by this module.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BASELINE_SRC = _HERE.parent / "baseline" / "src"
if str(_BASELINE_SRC) not in sys.path:
    sys.path.insert(0, str(_BASELINE_SRC))

from verdict.investigator import Investigator  # noqa: E402
from verdict.models import Question, SourceKind  # noqa: E402
from verdict.sources import FileSource  # noqa: E402
from verdict.verdict_engine import decide  # noqa: E402

CASES_DIR = _HERE / "cases"

_SOURCE_FILES = [
    (SourceKind.LOCKS, "locks.json"),
    (SourceKind.DRAFTS, "drafts.json"),
    (SourceKind.REVIEWS, "reviews.json"),
]


def list_cases() -> list[dict]:
    metas = []
    for case_dir in sorted(CASES_DIR.iterdir()):
        meta_file = case_dir / "meta.json"
        if meta_file.exists():
            metas.append(json.loads(meta_file.read_text(encoding="utf-8")))
    return metas


def case_meta(case_id: str) -> dict:
    meta_file = CASES_DIR / case_id / "meta.json"
    if not meta_file.exists():
        raise ValueError(f"unknown case {case_id}")
    return json.loads(meta_file.read_text(encoding="utf-8"))


def run_case(case_id: str) -> dict:
    """Investigate one demo case. Returns {verdict, reason, receipt}."""
    case_dir = CASES_DIR / case_id
    if not case_dir.is_dir():
        raise ValueError(f"unknown case {case_id}")
    meta = case_meta(case_id)
    connectors = [
        FileSource(kind, case_dir / filename) for kind, filename in _SOURCE_FILES
    ]
    investigator = Investigator(connectors, chat=None)  # offline replay
    result = decide(investigator.investigate(Question(meta["question"])))
    return {
        "verdict": result.verdict.value,
        "reason": result.reason,
        "receipt": result.receipt.to_dict(),
    }
