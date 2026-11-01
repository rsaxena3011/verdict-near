"""Second-look promotion layers for VERDICT (merged fix plan, 2026-10-23:
MERGED_FIX_PLAN_28.md in the competition folder).

Both layers run ONLY on a REVIEW that came out of the NOT SETTLED branch
of decide.py, and can only upgrade REVIEW to ALLOW. They never run on a
BLOCK or an ALLOW, never override a structured contradiction, and never
fire when either agent fell back to the structured stand-in. Pass 1 (the
agent prompts in agents.py and the rules in decide.py) is untouched.

Layer 1 (pure code, Grok's rule): IDENTITY_ACTING_SUBJECT. A lock that
pins a person's name settles when a validated draft quote uses that name
as the acting subject of a real action verb. This is the LK-002 family
("Meera wiped down the counter") stated as a rule instead of left to
model variance. A mere mention ("Meera was mentioned in the staff chat")
fails the verb test by construction.

Layer 2 (model classification + code gates, Kimi's SLIP with Argon's
modes and spans and Sol's concurrence test): the model classifies the
relation between one draft quote and the lock; plain code then applies
the threshold behind verbatim gates. The model never gets the final say.
"""
import re

from model_client import extract_json

# The STATE_SNAPSHOT promotion mode ships only while its mirror
# diagnostic (mirror_state in mirrors.json: an in-scope OPEN observation
# must BLOCK) passes. If the mirror ever fails, set this to False; the
# change can only add REVIEWs, never ALLOWs.
STATE_SNAPSHOT_ENABLED = True

HONORIFIC_RE = r"(?:Mr|Mrs|Ms|Miss|Dr|Mx|Prof)\.?\s+"
NAME_RE = r"[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)*"

PRESENCE_VERBS = {
    "is", "was", "are", "were", "be", "been", "being", "am",
    "went", "came", "arrived", "appeared", "seemed",
    "said", "mentioned", "named", "called",
    "had", "have", "has",
    "stood", "sat", "walked", "passed", "visited", "approached",
    "looked", "stayed", "remained", "existed", "lived",
}

REJECT_NAME_TOKENS = {
    "due", "locked", "open", "closed", "true", "false", "night", "day",
    "always", "sharp", "daily", "only",
}

RECURRENCE_MARKER_RE = re.compile(r"\b(as always|as usual|every|each|always)\b", re.I)
DATE_TIME_TOKEN_RE = re.compile(
    r"(\d{1,2}:\d{2}|\d+(?:st|nd|rd|th)\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b)",
    re.I,
)


def _looks_like_person_name(name):
    tokens = name.split()
    if not tokens:
        return False
    for tok in tokens:
        base = tok.strip(".,'\"")
        if not base or not base[0].isalpha() or not base[0].isupper():
            return False
        if base.lower() in REJECT_NAME_TOKENS:
            return False
        if re.search(r"\d", base):
            return False
    return True


def identity_core_name(lock_claim):
    """Core person name if the lock is an IDENTITY lock, else None.
    Handles "The owner's name is Meera." and "The librarian is
    Mr. Kapoor." Time, quantity and state locks cannot parse: their
    would-be names are numbers, times or lowercase state words."""
    claim = (lock_claim or "").strip().rstrip(".")
    m = re.search(r"name is\s+(?:" + HONORIFIC_RE + r")?(" + NAME_RE + r")$", claim, re.I)
    if not m:
        m = re.search(r"\bis\s+(?:" + HONORIFIC_RE + r")?(" + NAME_RE + r")$", claim, re.I)
    if not m:
        return None
    name = m.group(1).strip()
    return name if _looks_like_person_name(name) else None


def name_is_acting_subject(core_name, quote):
    """The verb if `core_name` acts in `quote`, else None. The name must
    sit at the start of the quote or right after a clause boundary, and
    the next word must be a verb outside the presence denylist."""
    pat = re.compile(
        r"(?:^|[.\"';:,\n]\s*)(?:"
        + HONORIFIC_RE
        + r")?"
        + re.escape(core_name)
        + r"\s+([A-Za-z']+)"
    )
    for m in pat.finditer(quote or ""):
        verb = m.group(1).lower()
        if verb not in PRESENCE_VERBS:
            return verb
    return None


def layer1_check(lock, draft_quotes):
    """Returns a telemetry dict if Layer 1 promotes, else None."""
    core = identity_core_name(lock.get("claim"))
    if not core:
        return None
    for q in draft_quotes:
        verb = name_is_acting_subject(core, q)
        if verb:
            return {
                "layer": 1,
                "rule": "IDENTITY_ACTING_SUBJECT",
                "name": core,
                "verb": verb,
                "quote": q,
            }
    return None


def _norm(s):
    s = (s or "").lower()
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(".,;:\"'")
    if s.startswith("the "):
        s = s[4:]
    return s


CLASSIFY_SYSTEM = (
    "You are the second-look classifier in VERDICT, an evidence-checking "
    "system. You classify the relation between ONE draft quote and ONE "
    "locked fact. You do not decide the verdict; a deterministic layer "
    "applies the threshold to your classification. Reply with a single "
    "JSON object and nothing else."
)

CLASSIFY_TEMPLATE = """LOCK (the locked fact, claim and its source line):
claim: {claim}
source line: {lock_quote}

DRAFT QUOTE under examination:
{quote}

ALL EVIDENCE LINES for this lock (for the ANY_BREAK check):
{evidence}

Reply with JSON of exactly this shape:
{{"element": "...", "element_in_quote": "...", "relation": "RESTATES|INSTANTIATES|MENTIONS|CONTRADICTS", "mode": "ROLE_DUTY|SCHEDULE_RECURRENCE|STATE_SNAPSHOT|NONE", "anchor_span": "...", "predicate_span": "...", "scope": "HABITUAL-WITH-RECURRENCE|HABITUAL-NO-RECURRENCE|SINGLE", "any_break": "YES|NO", "proposal": "ALLOW|REVIEW"}}

Field rules:
- element: the single decisive value the lock pins down (a name, date, time, quantity, or state), copied verbatim from the lock claim.
- element_in_quote: the shortest span of the DRAFT QUOTE expressing that same value, verbatim, or the word ABSENT.
- relation: RESTATES = the quote states the locked fact itself. INSTANTIATES = the quote shows the locked fact in action, with the element itself present in a concrete action, event, or state realizing the lock's claim; merely naming the lock's subject, people, place, or topic is never INSTANTIATES. MENTIONS = the quote touches the subject or topic without stating or instantiating the fact. CONTRADICTS = the quote breaks the lock.
- mode (only when relation is INSTANTIATES, else NONE): ROLE_DUTY = the lock assigns a role and the named person performs a duty that role consists of. SCHEDULE_RECURRENCE = the lock states a recurring date or time obligation and the quote shows the event happening on the lock's exact date or time as an established routine. STATE_SNAPSHOT = the lock states an object stays in a state during a window and the quote observes that exact state at a moment inside the window.
- anchor_span: an exact contiguous substring of the quote identifying the subject. predicate_span: a DIFFERENT exact contiguous substring of the quote that states or enacts the predicate.
- scope: HABITUAL-WITH-RECURRENCE = the lock makes a habitual claim and the quote carries a recurrence marker (such as "as always", "every", "each"). HABITUAL-NO-RECURRENCE = habitual claim, no recurrence marker in the quote. SINGLE = everything else.
- any_break: YES if any line in ALL EVIDENCE contradicts the lock, else NO.
- proposal: ALLOW only if any_break is NO and (relation is RESTATES, or relation is INSTANTIATES with mode ROLE_DUTY and scope SINGLE, or relation is INSTANTIATES with mode SCHEDULE_RECURRENCE and scope HABITUAL-WITH-RECURRENCE, or relation is INSTANTIATES with mode STATE_SNAPSHOT). Otherwise REVIEW."""

VETO_SYSTEM = (
    "You are the Evidence Challenger in VERDICT, reviewing a proposed "
    "second-look promotion. Your job is to veto promotions the evidence "
    "does not earn. Reply with a single JSON object and nothing else."
)

VETO_TEMPLATE = """LOCK claim: {claim}
DRAFT QUOTE: {quote}
PROPOSED CLASSIFICATION: {classification}

Reply with JSON of exactly this shape:
{{"concurs": true, "reason": "one short sentence"}}

Set concurs to false if ANY of these hold:
- the predicate_span merely places someone in a location, mentions a topic, or describes a generic action rather than a role-defining duty, a routine schedule on the locked date, or the verified state at a matching time;
- any decisive number, date, name, or state from the lock is missing from, or contradicted in, the quote;
- the anchor_span and predicate_span do not independently support the subject and the claim;
- all the quoted text could be true while the lock is false, without supposing the source is lying or mistaken.
Otherwise set concurs to true."""


def _ask_json(model, system, prompt, key=None):
    text, receipt = model.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4000,
    )
    try:
        return extract_json(text, key=key), receipt
    except ValueError:
        text, receipt = model.chat(
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": prompt
                    + "\n\nIMPORTANT: your previous reply could not be parsed. Reply with ONLY the JSON object. No reasoning, no explanation, no markdown.",
                },
            ],
            max_tokens=4000,
        )
        return extract_json(text, key=key), receipt


def classify_quote(model, lock, quote, evidence_rows):
    evidence = "\n".join(
        f"- {r.get('finding_id')}: {r.get('quote')}" for r in evidence_rows
    )
    prompt = CLASSIFY_TEMPLATE.format(
        claim=lock.get("claim"),
        lock_quote=lock.get("quote"),
        quote=quote,
        evidence=evidence,
    )
    return _ask_json(model, CLASSIFY_SYSTEM, prompt, key="relation")


def veto_check(model, lock, quote, classification):
    import json as _json

    prompt = VETO_TEMPLATE.format(
        claim=lock.get("claim"),
        quote=quote,
        classification=_json.dumps(classification, separators=(",", ":")),
    )
    return _ask_json(model, VETO_SYSTEM, prompt, key="concurs")


def layer2_gates(lock, quote, cls, concurs):
    """Pure-code threshold on a classification. Returns (ok, reasons).
    Every check here can only refuse a promotion, never grant one the
    classification did not propose."""
    reasons = []
    if not isinstance(cls, dict):
        return False, ["classification not an object"]
    element = cls.get("element") or ""
    eiq = cls.get("element_in_quote") or ""
    relation = (cls.get("relation") or "").upper()
    mode = (cls.get("mode") or "NONE").upper()
    scope = (cls.get("scope") or "").upper()
    anchor = cls.get("anchor_span") or ""
    predicate = cls.get("predicate_span") or ""

    claim = lock.get("claim") or ""
    if not element or element not in claim:
        reasons.append("element is not a verbatim span of the lock claim")
    if not eiq or eiq == "ABSENT" or eiq not in quote:
        reasons.append("element_in_quote is absent or not verbatim in the quote")
    if element and eiq and _norm(element) != _norm(eiq):
        reasons.append("element and element_in_quote differ after normalization")
    if not anchor or anchor not in quote:
        reasons.append("anchor_span is not a verbatim substring of the quote")
    if not predicate or predicate not in quote:
        reasons.append("predicate_span is not a verbatim substring of the quote")
    if anchor and predicate and anchor == predicate:
        reasons.append("anchor_span and predicate_span are identical")
    if (cls.get("any_break") or "").upper() != "NO":
        reasons.append("any_break is not NO")

    combo_ok = False
    if relation == "RESTATES":
        combo_ok = True
    elif relation == "INSTANTIATES" and mode == "ROLE_DUTY" and scope == "SINGLE":
        combo_ok = True
    elif (
        relation == "INSTANTIATES"
        and mode == "SCHEDULE_RECURRENCE"
        and scope == "HABITUAL-WITH-RECURRENCE"
    ):
        if not DATE_TIME_TOKEN_RE.search(element):
            reasons.append("schedule mode but the element is not a date/time token")
        elif not RECURRENCE_MARKER_RE.search(quote):
            reasons.append("schedule mode but no recurrence marker in the quote")
        else:
            combo_ok = True
    elif relation == "INSTANTIATES" and mode == "STATE_SNAPSHOT":
        if STATE_SNAPSHOT_ENABLED:
            combo_ok = True
        else:
            reasons.append("state snapshot mode is disabled")
    if not combo_ok and not reasons:
        reasons.append(f"combination not allowed: relation={relation} mode={mode} scope={scope}")

    proposal_allow = (cls.get("proposal") or "").upper() == "ALLOW"
    if combo_ok and not proposal_allow:
        reasons.append("self-consistency: gates pass but the classifier proposed REVIEW")
        combo_ok = False
    if not concurs:
        reasons.append("challenger did not concur")
        combo_ok = False
    if reasons:
        # Any recorded gate failure (verbatim, normalization, spans,
        # any_break, schedule token/marker, state-mode switch) refuses
        # the promotion even if the combination itself is allowed.
        combo_ok = False
    return combo_ok, reasons


def maybe_promote(model, lock, decision, drafts, reviews, agent_sources, receipts_out=None):
    """Upgrade a NOT SETTLED REVIEW to ALLOW if a layer earns it.
    Returns (decision, telemetry). The decision is returned unchanged
    unless a promotion fires."""
    tel = {"invoked": False}
    if decision.get("verdict") != "REVIEW":
        return decision, tel
    if not (decision.get("basis") or "").startswith("investigator judges"):
        return decision, tel
    if agent_sources.get("investigator") != "model" or agent_sources.get("challenger") != "model":
        tel["skipped"] = "an agent fell back; second look never fires on fallback"
        return decision, tel
    lock_id = lock["finding_id"]
    if any((r.get("contradicts") or "") == lock_id for r in drafts + reviews):
        tel["skipped"] = "a structured contradiction tag exists for this lock"
        return decision, tel
    draft_quotes = [r["quote"] for r in drafts if r.get("quote")]
    if not draft_quotes:
        return decision, tel

    tel["invoked"] = True

    hit = layer1_check(lock, draft_quotes)
    if hit:
        decision = dict(decision)
        decision["verdict"] = "ALLOW"
        decision["basis"] = (
            "second look layer 1 (identity acting subject): "
            f"name={hit['name']}; verb={hit['verb']}; quote=\"{hit['quote']}\""
        )
        decision["second_look"] = hit
        tel["promoted"] = hit
        return decision, tel

    tel["layer2"] = []
    for q in draft_quotes:
        entry = {"quote": q}
        try:
            cls, rcpt = classify_quote(model, lock, q, drafts + reviews)
            if receipts_out is not None:
                receipts_out.append({"step": f"second_look_classify_{lock_id}", **(rcpt or {})})
        except Exception as e:
            entry["error"] = f"classify failed: {type(e).__name__}: {e}"
            tel["layer2"].append(entry)
            continue
        entry["classification"] = cls
        concurs = False
        try:
            veto, rcpt = veto_check(model, lock, q, cls)
            if receipts_out is not None:
                receipts_out.append({"step": f"second_look_veto_{lock_id}", **(rcpt or {})})
            concurs = bool(veto.get("concurs")) if isinstance(veto, dict) else False
            entry["veto"] = veto
        except Exception as e:
            entry["error"] = f"veto failed: {type(e).__name__}: {e}"
            tel["layer2"].append(entry)
            continue
        ok, reasons = layer2_gates(lock, q, cls, concurs)
        entry["gates_ok"] = ok
        entry["gate_reasons"] = reasons
        tel["layer2"].append(entry)
        if ok:
            decision = dict(decision)
            decision["verdict"] = "ALLOW"
            decision["basis"] = (
                "second look layer 2 (instantiation pass): "
                f"relation={cls.get('relation')}; mode={cls.get('mode')}; "
                f"element=\"{cls.get('element')}\"; quote=\"{q}\""
            )
            decision["second_look"] = {"layer": 2, **cls, "quote": q}
            tel["promoted"] = decision["second_look"]
            return decision, tel
    return decision, tel
