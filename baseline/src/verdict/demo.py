"""Golden-path walkthrough on the sample fixtures. No network, no LLM.

Run:  python3 -m verdict.demo   (from the verdict/ directory)
"""

from pathlib import Path

from verdict.investigator import Investigator
from verdict.models import Question, SourceKind
from verdict.sources import FileSource
from verdict.verdict_engine import decide

FIX = Path(__file__).resolve().parent.parent.parent / "fixtures"


def build():
    connectors = [
        FileSource(SourceKind.LOCKS, FIX / "locks.sample.json"),
        FileSource(SourceKind.DRAFTS, FIX / "drafts.sample.json"),
        FileSource(SourceKind.REVIEWS, FIX / "reviews.sample.json"),
    ]
    return Investigator(connectors, chat=None)  # offline replay


def main():
    inv = build().investigate(Question("Does draft-v9 respect the 22:00 closing lock?"))
    result = decide(inv)
    print(f"verdict : {result.verdict.value}")
    print(f"why     : {result.reason}")
    print(f"sources : {[c.kind.value for c in build().connectors]}")
    print(f"missing : {[s.value for s in result.receipt.missing_sources]}")
    print(f"notes   : {result.receipt.notes}")
    print("\nreceipt (judge-visible):")
    import json

    print(json.dumps(result.receipt.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
