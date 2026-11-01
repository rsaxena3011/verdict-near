"""VERDICT one-screen UI.

Renders the latest run receipt (~/verdict/receipts/) into a single
self-contained HTML page: verdict cards with the quoted evidence, the
plain-language explanation, both agents' positions, the prior verdict
held in decision memory (with a FLIPPED badge when it changed), and the
model receipt strip (requested vs routed Nemotron lane per step, with
any structured-fallback step labelled). No external assets.

Usage: python3 ui.py [--serve]   (writes ~/verdict/ui/index.html;
--serve also serves it on http://127.0.0.1:8765 for the demo recording)
"""
import glob
import html
import json
import os
import sys

HOME = os.path.expanduser("~/verdict")
OUT = os.path.join(HOME, "ui", "index.html")

COLORS = {"BLOCK": "#c0392b", "ALLOW": "#1e8449", "REVIEW": "#b7950b"}

CSS = """
body{font-family:Segoe UI,Arial,sans-serif;background:#101418;color:#e8edf2;margin:0;padding:28px}
h1{margin:0 0 4px;font-size:30px;letter-spacing:1px}
.sub{color:#9fb0c3;margin-bottom:20px;font-size:14px}
.card{background:#171d24;border:1px solid #2a3441;border-radius:10px;padding:18px 20px;margin-bottom:16px}
.chip{display:inline-block;color:#fff;font-weight:700;padding:4px 14px;border-radius:20px;font-size:15px}
.flip{display:inline-block;background:#7d3c98;color:#fff;font-weight:700;padding:4px 10px;border-radius:20px;font-size:12px;margin-left:8px}
.claim{font-size:19px;margin:10px 0 4px}
.lockq{color:#9fb0c3;font-style:italic;margin-bottom:10px}
.expl{font-size:16px;line-height:1.45;margin:10px 0}
.quote{background:#0d1117;border-left:3px solid #3d5a80;padding:8px 12px;margin:6px 0;font-size:14px}
.meta{color:#9fb0c3;font-size:13px;margin-top:10px}
.strip{background:#171d24;border:1px solid #2a3441;border-radius:10px;padding:14px 20px;margin-bottom:16px;font-size:13px;color:#c7d3e0}
.strip b{color:#fff}
.fb{color:#f39c12;font-weight:700}
"""


def esc(s):
    return html.escape(str(s if s is not None else ""))


def render(receipt):
    cards = []
    for d in receipt["decisions"]:
        color = COLORS.get(d["verdict"], "#555")
        flipped = d.get("prior_verdict_in_memory") and d["prior_verdict_in_memory"] != d["verdict"]
        quotes = "".join(f'<div class="quote">"{esc(q)}"</div>' for q in d["quotes"]) or '<div class="quote">(no quoted evidence)</div>'
        cards.append(
            f"""<div class="card">
<span class="chip" style="background:{color}">{esc(d['verdict'])}</span>{'<span class="flip">FLIPPED from ' + esc(d['prior_verdict_in_memory']) + '</span>' if flipped else ''}
<div class="claim">{esc(d['lock_claim'])}</div>
<div class="lockq">Lock source line: "{esc(d['lock_quote'])}"</div>
<div class="expl">{esc(d.get('explanation',''))}</div>
{quotes}
<div class="meta">Investigator proposed: {esc(d.get('investigator_proposal'))} &nbsp;|&nbsp; Challenger: {esc(d.get('challenger_stance'))} &nbsp;|&nbsp; Prior verdict in memory: {esc(d.get('prior_verdict_in_memory') or 'none (first run)')} &nbsp;|&nbsp; Basis: {esc(d['basis'])}</div>
</div>"""
        )
    steps = []
    for m in receipt["model_receipts"]:
        src = m.get("source")
        label = f' <span class="fb">STRUCTURED FALLBACK</span>' if src == "fallback_structured" else ""
        steps.append(
            f"<div><b>{esc(m['step'])}</b>: asked for {esc(m.get('requested_model') or '(no model call)')}"
            + (f", answered by {esc(m['routed_model'])}" if m.get("routed_model") else "")
            + label
            + "</div>"
        )
    queries = []
    for who in ("investigator_queries", "challenger_queries"):
        for q in receipt.get(who, []):
            queries.append(f"<div>{esc(who.split('_')[0])}: {esc(q['sql'])} &rarr; {esc(q['rows'])} rows</div>")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>VERDICT</title><style>{CSS}</style></head>
<body>
<h1>VERDICT</h1>
<div class="sub">Federated evidence investigator &nbsp;|&nbsp; Run at {esc(receipt['run_at'])} &nbsp;|&nbsp; Stores behind Zetaris: {esc(', '.join(receipt['stores']))} &nbsp;|&nbsp; Agents: Investigator + Evidence Challenger (NVIDIA Nemotron via Meterless Nightshift) &nbsp;|&nbsp; Decisions by the deterministic layer</div>
{''.join(cards)}
<div class="strip"><b>Model receipts</b>{''.join(steps)}</div>
<div class="strip"><b>Zetaris queries</b>{''.join(queries)}</div>
</body></html>"""


def main():
    files = sorted(glob.glob(os.path.join(HOME, "receipts", "*.json")))
    if not files:
        print("no receipts yet")
        sys.exit(1)
    with open(files[-1]) as f:
        receipt = json.load(f)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(render(receipt))
    print("wrote", OUT, "from", files[-1])
    if "--serve" in sys.argv:
        import http.server
        import socketserver

        os.chdir(os.path.dirname(OUT))
        with socketserver.TCPServer(("127.0.0.1", 8765), http.server.SimpleHTTPRequestHandler) as srv:
            print("serving on http://127.0.0.1:8765")
            srv.serve_forever()


if __name__ == "__main__":
    main()
