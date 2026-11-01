"""Plain-language explanations for VERDICT decisions.

This is a presentation step, not a third agent: it never changes a
verdict. It takes the deterministic layer's decision record and renders
one or two sentences a non-technical reader can follow. Grounding rule:
the explanation must quote at least one of the decision's evidence lines
verbatim; if the model's text fails that check, a templated explanation
built from the same record is used instead, and the receipt says which
path produced the text.
"""

EXPLAINER_SYSTEM = (
    "You write short, plain explanations of fact-check verdicts for "
    "non-technical readers. Use ONLY the facts in the decision record "
    "given to you. You must include at least one of the record's quoted "
    "evidence lines word for word, inside quotation marks. Do not add "
    "facts, names or times that are not in the record. Two sentences at "
    "most. Plain words."
)

EXPLAINER_TEMPLATE = """DECISION RECORD:
Lock: {lock_claim} (source line: "{lock_quote}")
Verdict: {verdict}
Basis: {basis}
Evidence lines: {quotes}
Investigator proposed: {inv}; Challenger: {chal}

Write the explanation now, nothing else."""


def template_explanation(d):
    q = d["quotes"][0] if d["quotes"] else ""
    if d["verdict"] == "BLOCK":
        return (
            f"This draft cannot pass. The lock says: \"{d['lock_quote']}\" "
            f"but the evidence line reads: \"{q}\" Basis: {d['basis']}."
        )
    if d["verdict"] == "ALLOW":
        return (
            f"This lock holds. The lock says: \"{d['lock_quote']}\" and the "
            f"evidence line supports it: \"{q}\""
        )
    return (
        f"A human needs to look at this one. Basis: {d['basis']}. "
        f"Lock: \"{d['lock_quote']}\"."
    )


def explain(model, decision):
    prompt = EXPLAINER_TEMPLATE.format(
        lock_claim=decision["lock_claim"],
        lock_quote=decision["lock_quote"],
        verdict=decision["verdict"],
        basis=decision["basis"],
        quotes=" | ".join(f'"{q}"' for q in decision["quotes"]) or "(none)",
        inv=decision.get("investigator_proposal"),
        chal=decision.get("challenger_stance"),
    )
    try:
        text, receipt = model.chat(
            [
                {"role": "system", "content": EXPLAINER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=900,
        )
        # Reasoning models leak their monologue into the visible reply,
        # closed by a </think> marker; only the tail is the answer.
        if "</think>" in text:
            text = text.rsplit("</think>", 1)[1]
        text = " ".join(text.split()).strip()
        if (
            any(q in text for q in decision["quotes"])
            and 20 < len(text) <= 600
            and "<think>" not in text
        ):
            return text, "model", receipt
    except Exception:
        pass
    return template_explanation(decision), "template", None
