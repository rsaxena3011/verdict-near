"""VERDICT core loop: two interacting agents over Zetaris-federated stores,
a deterministic decision layer, and an auditable decision memory.

Flow:
1. Investigator fetches locks, drafts, reviews through Zetaris and
   proposes a verdict per lock (Nemotron via Nightshift).
2. Challenger independently re-queries all three stores and attacks the
   proposal (second Nemotron call).
3. Any CHALLENGE forces ONE Investigator re-investigation round on that
   lock with the Challenger's evidence included.
4. The deterministic layer decides on the combined record. No verdict is
   emitted without at least one validated quoted source line.
5. Every decision is appended to the decision memory (~/verdict/memory/
   decision_memory.jsonl), the persistent auditable memory the product
   reads back on the next run (H-MEM pattern: memory influences the next
   investigation, it is not just a log).

Run: python3 run_verdict.py
Writes a receipt JSON to ~/verdict/receipts/ and prints it.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from zetaris_client import ZetarisClient
from model_client import ModelClient
import agents
import explain
import second_look
from decide import decide

SECOND_LOOK_ON = os.environ.get("VERDICT_SECOND_LOOK", "1") != "0"

HOME = os.path.expanduser("~/verdict")
MEMORY_PATH = os.path.join(HOME, "memory", "decision_memory.jsonl")
RECEIPTS_DIR = os.path.join(HOME, "receipts")


def load_prior_decisions():
    prior = {}
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    e = json.loads(line)
                    prior[e["lock_id"]] = e
    return prior


def main():
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    prior = load_prior_decisions()

    zc = ZetarisClient()
    model = ModelClient()
    model_receipts = []

    # 1. Investigator pass
    locks = zc.fetch_store("verdict_locks")
    drafts = zc.fetch_store("verdict_drafts")
    reviews = zc.fetch_store("verdict_reviews")
    investigator_queries = list(zc.query_log)
    proposal, rcpt, rejected_a = agents.run_investigator(model, locks, drafts, reviews)
    model_receipts.append({"step": "investigator", "source": proposal.get("source"), **(rcpt or {})})

    # 2. Challenger pass, with its own independent fetches
    zc2 = ZetarisClient()
    locks_b = zc2.fetch_store("verdict_locks")
    drafts_b = zc2.fetch_store("verdict_drafts")
    reviews_b = zc2.fetch_store("verdict_reviews")
    challenger_queries = list(zc2.query_log)
    challenges, rcpt, rejected_b = agents.run_challenger(
        model, proposal, locks_b, drafts_b, reviews_b
    )
    model_receipts.append({"step": "challenger", "source": challenges.get("source"), **(rcpt or {})})

    proposals = proposal.get("proposals", [])
    challenge_list = challenges.get("challenges", [])

    # 3. One re-investigation round per challenged lock
    reinv = []
    for ch in challenge_list:
        if ch.get("stance") == "CHALLENGE":
            ctx = json.dumps(ch, indent=1)
            prop2, rcpt, rejected_c = agents.run_investigator(
                model, locks, drafts, reviews, extra_context=ctx
            )
            model_receipts.append({"step": f"reinvestigate_{ch.get('lock_id')}", "source": prop2.get("source"), **(rcpt or {})})
            for p2 in prop2.get("proposals", []):
                if p2.get("lock_id") == ch.get("lock_id"):
                    proposals = [
                        p2 if p.get("lock_id") == ch.get("lock_id") else p for p in proposals
                    ]
                    reinv.append(
                        {"lock_id": ch.get("lock_id"), "new_proposal": p2.get("proposed_verdict")}
                    )
            rejected_a += rejected_c

    # 4. Deterministic decision on the combined record
    all_rows = locks + drafts + reviews
    decisions = [decide(lock, proposals, challenge_list, all_rows) for lock in locks]

    # 4a. Second look (merged fix plan, 2026-10-23): REVIEW-only
    # promotion layers. Can upgrade a NOT SETTLED REVIEW to ALLOW behind
    # deterministic gates; never touches a BLOCK or an ALLOW.
    if SECOND_LOOK_ON:
        sources = {
            "investigator": proposal.get("source"),
            "challenger": challenges.get("source"),
        }
        promoted = []
        for lock, d in zip(locks, decisions):
            d2, tel = second_look.maybe_promote(
                model, lock, d, drafts, reviews, sources, receipts_out=model_receipts
            )
            if tel.get("invoked"):
                d2["second_look_telemetry"] = tel
            promoted.append(d2)
        decisions = promoted

    # 4b. Plain-language explanations (presentation step, never an agent:
    # it cannot change a verdict, and its text must quote the evidence)
    for d in decisions:
        text, source, rcpt = explain.explain(model, d)
        d["explanation"] = text
        d["explanation_source"] = source
        if rcpt:
            model_receipts.append({"step": f"explain_{d['lock_id']}", **rcpt})

    # 5. Memory write + receipt
    ts = datetime.now(timezone.utc).isoformat()
    for d in decisions:
        entry = {
            "ts": ts,
            "lock_id": d["lock_id"],
            "lock_quote": d["lock_quote"],
            "verdict": d["verdict"],
            "basis": d["basis"],
            "quotes": d["quotes"],
            "prior_verdict": (prior.get(d["lock_id"]) or {}).get("verdict"),
        }
        with open(MEMORY_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
        d["prior_verdict_in_memory"] = entry["prior_verdict"]

    receipt = {
        "product": "VERDICT",
        "run_at": ts,
        "stores": ["verdict_locks", "verdict_drafts", "verdict_reviews"],
        "investigator_queries": investigator_queries,
        "challenger_queries": challenger_queries,
        "model_receipts": model_receipts,
        "rejected_quotes": rejected_a + rejected_b,
        "reinvestigations": reinv,
        "decisions": decisions,
    }
    out = os.path.join(RECEIPTS_DIR, "receipt_" + ts.replace(":", "").replace("-", "") + ".json")
    with open(out, "w") as f:
        json.dump(receipt, f, indent=1)
    print(json.dumps(receipt, indent=1))
    print("\nRECEIPT FILE:", out)


if __name__ == "__main__":
    main()
