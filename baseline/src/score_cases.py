"""Score VERDICT harness results per ../TEST_SET.md.

Usage: python3 score_cases.py cases_results.json

Headline numbers, always reported together:
- planted BLOCKs: catches (BLOCK), half catches (REVIEW), FALSE PASSES
  (ALLOW on a planted break, P0, target zero)
- clean ALLOWs: correct, false alarms (BLOCK, target zero), soft alarms
  (REVIEW)
- expected REVIEWs: correct, unsupported ALLOWs, over-BLOCKs
Plus error cases, agent-source health (model vs labelled fallback),
and rejected-quote totals.
"""
import json
import sys
from collections import Counter


def main():
    results = json.load(open(sys.argv[1]))
    catches = half = false_pass = 0
    planted = 0
    clean = clean_ok = false_alarm = soft_alarm = 0
    review_exp = review_ok = review_allow = review_block = 0
    errors = []
    sources = Counter()
    rej = 0
    exact = total = 0
    for c in results:
        if c.get("error"):
            errors.append(c["name"])
        src = c.get("agent_sources", {})
        sources[("investigator", src.get("investigator"))] += 1
        sources[("challenger", src.get("challenger"))] += 1
        rej += len(c.get("rejected_quotes", []))
        for d in c.get("decisions", []):
            total += 1
            v, e = d["verdict"], d["expected"]
            if d["ok"]:
                exact += 1
            if e == "BLOCK":
                planted += 1
                if v == "BLOCK":
                    catches += 1
                elif v == "REVIEW":
                    half += 1
                elif v == "ALLOW":
                    false_pass += 1
            elif e == "ALLOW":
                clean += 1
                if v == "ALLOW":
                    clean_ok += 1
                elif v == "BLOCK":
                    false_alarm += 1
                elif v == "REVIEW":
                    soft_alarm += 1
            elif e == "REVIEW":
                review_exp += 1
                if v == "REVIEW":
                    review_ok += 1
                elif v == "ALLOW":
                    review_allow += 1
                elif v == "BLOCK":
                    review_block += 1
    print(f"cases: {len(results)}  decisions: {total}  exact: {exact}")
    print(f"planted BLOCKs: {planted}  catches: {catches}  half catches (REVIEW): {half}  FALSE PASSES (P0): {false_pass}")
    print(f"clean ALLOWs: {clean}  correct: {clean_ok}  false alarms (BLOCK): {false_alarm}  soft alarms (REVIEW): {soft_alarm}")
    print(f"expected REVIEWs: {review_exp}  correct: {review_ok}  unsupported ALLOW: {review_allow}  over-BLOCK: {review_block}")
    print(f"error cases: {errors if errors else 'none'}")
    print(f"agent sources: {dict(sources)}")
    print(f"rejected quotes total: {rej}")


if __name__ == "__main__":
    main()
