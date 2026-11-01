"""In-process test harness for VERDICT (see ../TEST_SET.md).

Runs one case = a set of fixture rows (locks, drafts, reviews) through the
real agents (live Nemotron calls via Nightshift) and the real deterministic
layer, with the Zetaris fetch replaced by the injected rows. Full-stack
cases through the live stores are run separately by run_verdict.py.

Usage: python3 test_harness.py cases.json
cases.json: [{"name": ..., "locks": [...], "drafts": [...], "reviews": [...],
              "expect": {"LK-001": "BLOCK", ...}}]
Rows use the findings schema: finding_id, claim, quote, document_id,
locator, contradicts, unanswerable.
Prints one line per lock plus a summary; writes results next to the input.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model_client import ModelClient
import agents
import second_look
from decide import decide

SECOND_LOOK_ON = os.environ.get("VERDICT_SECOND_LOOK", "1") != "0"


def run_case(model, case):
    locks, drafts, reviews = case["locks"], case["drafts"], case["reviews"]
    proposal, _, rej_a = agents.run_investigator(model, locks, drafts, reviews)
    challenges, _, rej_b = agents.run_challenger(model, proposal, locks, drafts, reviews)
    proposals = proposal.get("proposals", [])
    challenge_list = challenges.get("challenges", [])
    for ch in challenge_list:
        if ch.get("stance") == "CHALLENGE":
            import json as _json

            prop2, _, _ = agents.run_investigator(
                model, locks, drafts, reviews, extra_context=_json.dumps(ch)
            )
            for p2 in prop2.get("proposals", []):
                if p2.get("lock_id") == ch.get("lock_id"):
                    proposals = [
                        p2 if p.get("lock_id") == ch.get("lock_id") else p for p in proposals
                    ]
    all_rows = locks + drafts + reviews
    decisions = [decide(lock, proposals, challenge_list, all_rows) for lock in locks]
    if SECOND_LOOK_ON:
        sources = {
            "investigator": proposal.get("source"),
            "challenger": challenges.get("source"),
        }
        promoted = []
        for lock, d in zip(locks, decisions):
            d2, tel = second_look.maybe_promote(model, lock, d, drafts, reviews, sources)
            if tel.get("invoked"):
                d2["second_look_telemetry"] = tel
            promoted.append(d2)
        decisions = promoted
    return {
        "name": case["name"],
        "agent_sources": {
            "investigator": proposal.get("source"),
            "challenger": challenges.get("source"),
        },
        "rejected_quotes": rej_a + rej_b,
        "decisions": [
            {
                "lock_id": d["lock_id"],
                "verdict": d["verdict"],
                "expected": case["expect"].get(d["lock_id"]),
                "ok": d["verdict"] == case["expect"].get(d["lock_id"]),
                "basis": d["basis"],
                "investigator_proposal": d.get("investigator_proposal"),
                "challenger_stance": d.get("challenger_stance"),
                "second_look": d.get("second_look"),
                "second_look_telemetry": d.get("second_look_telemetry"),
            }
            for d in decisions
        ],
    }


def main():
    path = sys.argv[1]
    with open(path) as f:
        cases = json.load(f)
    model = ModelClient()
    results = []
    false_pass = 0
    out = path.replace(".json", "_results.json")
    for case in cases:
        try:
            r = run_case(model, case)
        except Exception as e:
            # One bad case (a hung model call, a bridge failure) must not
            # lose the whole run: record it as ERROR and keep going. ERROR
            # cases are re-run separately before scoring.
            r = {
                "name": case["name"],
                "error": f"{type(e).__name__}: {e}",
                "agent_sources": {},
                "rejected_quotes": [],
                "decisions": [
                    {
                        "lock_id": lid,
                        "verdict": "ERROR",
                        "expected": exp,
                        "ok": False,
                        "basis": "harness error, case not executed",
                    }
                    for lid, exp in case["expect"].items()
                ],
            }
            print(f"[ERROR] {case['name']}: {type(e).__name__}: {e}", flush=True)
        results.append(r)
        with open(out, "w") as f:
            json.dump(results, f, indent=1)
        for d in r["decisions"]:
            mark = "OK " if d["ok"] else "MISS"
            if d["expected"] == "BLOCK" and d["verdict"] == "ALLOW":
                false_pass += 1
                mark = "FALSE-PASS(P0)"
            print(f"[{mark}] {case['name']} {d['lock_id']}: got {d['verdict']}, want {d['expected']} ({d['basis']})", flush=True)
    total = sum(len(r["decisions"]) for r in results)
    ok = sum(1 for r in results for d in r["decisions"] if d["ok"])
    print(f"\n{ok}/{total} exact, false passes (P0): {false_pass}. Full results: {out}")


if __name__ == "__main__":
    main()
