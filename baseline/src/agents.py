"""VERDICT's two agents.

Agent A, the Investigator: reads the locks, the draft findings and the
review findings (all fetched through Zetaris) and proposes a verdict per
lock with quoted evidence lines.

Agent B, the Evidence Challenger: independently re-queries the same three
stores and attacks the proposal: missed evidence, quotes that do not say
what the proposal claims, ALLOWs with no real evidence behind them.

Both agents run on NVIDIA Nemotron through Meterless Nightshift. Their
outputs are validated in code: any quote an agent returns that is not a
verbatim quote from the stores is rejected and logged, never trusted.
"""
import json

from model_client import extract_json

INVESTIGATOR_SYSTEM = (
    "You are the Investigator in VERDICT, an evidence-checking system. "
    "You are given LOCK findings (facts that must hold), DRAFT findings "
    "(lines from a new draft) and REVIEW findings (notes from reviewers). "
    "For each lock, decide whether the draft evidence supports it, breaks "
    "it, or leaves it uncertain. You must quote evidence lines EXACTLY as "
    "given; never invent or reword a quote. Reply with a single JSON "
    "object and nothing else."
)

INVESTIGATOR_TEMPLATE = """LOCKS:
{locks}

DRAFT FINDINGS:
{drafts}

REVIEW FINDINGS:
{reviews}

Reply with JSON of exactly this shape:
{{"proposals": [{{"lock_id": "LK-001", "proposed_verdict": "ALLOW|BLOCK|REVIEW", "evidence_finding_ids": ["DR-001"], "quotes": ["exact quote from a finding above"], "reasoning": "one short sentence"}}]}}
One proposal per lock. proposed_verdict BLOCK means the draft breaks the lock; ALLOW means a quoted line states the locked fact itself, in so many words; REVIEW means the evidence is missing, ambiguous, or does not settle the lock. A quote that only mentions the people, place, or topic of the lock without stating the locked fact does NOT support the lock: propose REVIEW for that lock and do not present that quote as supporting evidence."""

CHALLENGER_SYSTEM = (
    "You are the Evidence Challenger in VERDICT. Your job is to attack "
    "the Investigator's proposal. You are given the same store findings, "
    "fetched independently for you. Look for: evidence lines the "
    "Investigator missed, quotes that do not support the claim made for "
    "them (a quote that merely mentions the people, place, or topic of "
    "a lock without stating the locked fact is not support), and ALLOW "
    "verdicts with no real evidence. Reply with a single "
    "JSON object and nothing else."
)

CHALLENGER_TEMPLATE = """INVESTIGATOR PROPOSAL:
{proposal}

LOCKS:
{locks}

DRAFT FINDINGS (independently fetched):
{drafts}

REVIEW FINDINGS (independently fetched):
{reviews}

Reply with JSON of exactly this shape:
{{"challenges": [{{"lock_id": "LK-001", "stance": "AGREE|CHALLENGE", "evidence_finding_ids": ["DR-002"], "quotes": ["exact quote from a finding above"], "reasoning": "one short sentence"}}]}}
One entry per lock. Use CHALLENGE only when you found a concrete problem or missed evidence; attach the finding ids and exact quotes that prove it."""


def _fmt(rows):
    # Compact JSON: shorter prompts leave the model less material to echo
    # back inside its reasoning, which measurably cuts parse failures.
    return json.dumps(rows, separators=(",", ":"))


def validate_quotes(obj, all_rows, key):
    """Drop any quote that is not verbatim from the stores; log the drops."""
    valid = {r["quote"] for r in all_rows}
    rejected = []
    for item in obj.get(key, []):
        kept = []
        for q in item.get("quotes", []):
            if q in valid:
                kept.append(q)
            else:
                rejected.append({"lock_id": item.get("lock_id"), "quote": q})
        item["quotes"] = kept
    return rejected


RETRY_SUFFIX = (
    "\n\nIMPORTANT: your previous reply could not be parsed. Reply with "
    "ONLY the JSON object. No reasoning, no explanation, no markdown."
)


def _ask(model, system, prompt, key):
    """Two attempts: normal, then a stern JSON-only retry. Raises the last
    error if both fail, so the caller can fall back honestly."""
    last_err = None
    receipt = None
    for suffix in ("", RETRY_SUFFIX):
        text, receipt = model.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt + suffix},
            ],
            max_tokens=4000,
        )
        try:
            return extract_json(text, key=key), receipt
        except ValueError as e:
            last_err = e
    raise last_err


def fallback_proposal(locks, drafts, reviews):
    """Structured-only stand-in used when the model cannot be parsed after
    a retry. It never ALLOWs: a lock is proposed BLOCK only when a finding
    carries a structured contradiction tag for it, otherwise REVIEW. The
    receipt labels this path, and the deterministic layer still decides."""
    props = []
    tagged = {}
    for r in drafts + reviews:
        if r.get("contradicts"):
            tagged.setdefault(r["contradicts"], []).append(r)
    for lock in locks:
        hits = tagged.get(lock["finding_id"], [])
        if hits:
            props.append(
                {
                    "lock_id": lock["finding_id"],
                    "proposed_verdict": "BLOCK",
                    "evidence_finding_ids": [h["finding_id"] for h in hits],
                    "quotes": [h["quote"] for h in hits],
                    "reasoning": "fallback: structured contradiction tag (agent output unparseable)",
                }
            )
        else:
            props.append(
                {
                    "lock_id": lock["finding_id"],
                    "proposed_verdict": "REVIEW",
                    "evidence_finding_ids": [],
                    "quotes": [],
                    "reasoning": "fallback: agent output unparseable; no structured contradiction tag",
                }
            )
    return {"proposals": props, "source": "fallback_structured"}


def fallback_challenges(locks):
    return {
        "challenges": [
            {
                "lock_id": lock["finding_id"],
                "stance": "AGREE",
                "evidence_finding_ids": [],
                "quotes": [],
                "reasoning": "fallback: challenger output unparseable after retry",
            }
            for lock in locks
        ],
        "source": "fallback_structured",
    }


def run_investigator(model, locks, drafts, reviews, extra_context=""):
    prompt = INVESTIGATOR_TEMPLATE.format(
        locks=_fmt(locks), drafts=_fmt(drafts), reviews=_fmt(reviews)
    )
    if extra_context:
        prompt += "\n\nADDITIONAL EVIDENCE FROM THE CHALLENGER (re-investigation round):\n" + extra_context
    try:
        proposal, receipt = _ask(model, INVESTIGATOR_SYSTEM, prompt, "proposals")
        proposal["source"] = "model"
    except ValueError:
        proposal, receipt = fallback_proposal(locks, drafts, reviews), None
    rejected = validate_quotes(proposal, locks + drafts + reviews, "proposals")
    return proposal, receipt, rejected


def run_challenger(model, proposal, locks, drafts, reviews):
    prompt = CHALLENGER_TEMPLATE.format(
        proposal=_fmt(proposal), locks=_fmt(locks), drafts=_fmt(drafts), reviews=_fmt(reviews)
    )
    try:
        challenges, receipt = _ask(model, CHALLENGER_SYSTEM, prompt, "challenges")
        challenges["source"] = "model"
    except ValueError:
        challenges, receipt = fallback_challenges(locks), None
    rejected = validate_quotes(challenges, locks + drafts + reviews, "challenges")
    return challenges, receipt, rejected
