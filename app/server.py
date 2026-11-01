"""VERDICT x NEAR — one-screen demo surface. WINDOW WORK (C133).

Stdlib-only HTTP server (no pip installs, runs anywhere Python 3 runs,
including this VM). It wires the unmodified baseline VERDICT engine to:

  POST /api/investigate  {case}            -> verdict + receipt + hash
  POST /api/anchor       {case}            -> anchor the receipt hash
  POST /api/verify       {receipt,verdict} -> full third-party re-check
  POST /api/milestone/create   {milestone_id, amount, beneficiary}
  POST /api/milestone/release  {milestone_id, case}
  GET  /api/cases                          -> demo case list
  GET  /api/near/status                    -> NEAR testnet RPC status
  GET  /                                   -> the one-screen page

The server never trusts a client-supplied verdict or hash: anchoring
re-runs the case server-side, and verification recomputes the hash and
re-runs the deterministic engine from the receipt alone.

Anchor backend: local append-only log by default (var/anchors.jsonl);
NEAR testnet when NEAR_ACCOUNT_ID, NEAR_PRIVATE_KEY and
NEAR_CONTRACT_ID are set in the environment.

Run:  python3 app/server.py            (http://127.0.0.1:8791)
      DEMO_HOST=0.0.0.0 DEMO_PORT=8791 python3 app/server.py
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (_HERE, _ROOT / "near"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from anchor import anchor_from_env  # noqa: E402
from engine_runner import list_cases, run_case  # noqa: E402
from milestone import MilestoneGate  # noqa: E402
from receipts import receipt_hash, recheck  # noqa: E402

VAR = _ROOT / "var"
ANCHOR = anchor_from_env(VAR / "anchors.jsonl")
GATE = MilestoneGate(VAR / "milestones.json", ANCHOR)

COLORS = {"BLOCK": "#c0392b", "ALLOW": "#1e8449", "REVIEW": "#b7950b"}

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>VERDICT x NEAR</title><style>
body{font-family:Segoe UI,Arial,sans-serif;background:#101418;color:#e8edf2;margin:0;padding:28px;max-width:980px;margin:0 auto}
h1{margin:0 0 4px;font-size:30px;letter-spacing:1px}
.sub{color:#9fb0c3;margin-bottom:20px;font-size:14px;line-height:1.5}
.card{background:#171d24;border:1px solid #2a3441;border-radius:10px;padding:18px 20px;margin-bottom:16px}
button{background:#3d5a80;color:#fff;border:0;border-radius:8px;padding:9px 16px;font-size:14px;cursor:pointer;margin:4px 6px 4px 0}
button:hover{background:#4a6fa0}
button.case{background:#22303f;border:1px solid #3d5a80}
.chip{display:inline-block;color:#fff;font-weight:700;padding:4px 14px;border-radius:20px;font-size:15px}
.quote{background:#0d1117;border-left:3px solid #3d5a80;padding:8px 12px;margin:6px 0;font-size:14px}
.meta{color:#9fb0c3;font-size:13px;margin-top:8px;word-break:break-all}
.hash{font-family:Consolas,monospace;font-size:12px;word-break:break-all;background:#0d1117;padding:8px 12px;border-radius:6px}
.ok{color:#2ecc71;font-weight:700}.bad{color:#e74c3c;font-weight:700}
input,select{background:#0d1117;color:#e8edf2;border:1px solid #2a3441;border-radius:6px;padding:8px;font-size:14px}
label{font-size:13px;color:#9fb0c3;display:block;margin:8px 0 2px}
</style></head>
<body>
<h1>VERDICT &times; NEAR</h1>
<div class="sub">An evidence investigator for the agent economy. An agent's claim goes in; a deterministic
verdict (ALLOW / BLOCK / REVIEW) comes out with the quoted evidence attached; the receipt hash is anchored
outside the agent's control; anyone can re-check it. Verdicts are decided by rules, never by the model.
Anchor backend: <b id="backend">...</b> &nbsp;|&nbsp; NEAR testnet: <span id="nearstatus">checking...</span></div>

<div class="card"><b>1. Pick a case and investigate</b><div id="cases" style="margin-top:10px"></div>
<div id="result"></div></div>

<div class="card"><b>2. Anchor and re-check</b>
<div class="meta">Anchoring records the receipt hash. Verify re-computes the hash, looks the anchor up,
and re-runs the deterministic engine from the receipt alone. The tamper button edits one character of a
quote in the copy sent for verification: a real re-check must fail.</div>
<div style="margin-top:10px">
<button onclick="doAnchor()">Anchor this receipt</button>
<button onclick="doVerify(false)">Verify receipt</button>
<button onclick="doVerify(true)">Verify a TAMPERED copy</button>
</div><div id="anchorout"></div></div>

<div class="card"><b>3. Milestone gate (business): money moves only on a verified ALLOW</b>
<label>Milestone id</label><input id="msid" value="ms-cafe-closing">
<label>Amount (test NEAR, demo state)</label><input id="msamt" value="10">
<label>Beneficiary</label><input id="msben" value="cafe-operator.testnet">
<div style="margin-top:10px">
<button onclick="doMsCreate()">Create milestone (HELD)</button>
<button onclick="doMsRelease()">Attempt release with the current case's verdict</button>
</div><div id="msout"></div></div>

<script>
let current = null; // {caseId, verdict, reason, receipt, receipt_hash}
async function post(path, body){ const r = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); return r.json(); }
async function getj(path){ const r = await fetch(path); return r.json(); }
function chip(v){ return '<span class="chip" style="background:'+({BLOCK:'#c0392b',ALLOW:'#1e8449',REVIEW:'#b7950b'})[v]+'">'+v+'</span>'; }
async function loadCases(){
  const cases = await getj('/api/cases');
  document.getElementById('cases').innerHTML = cases.map(c =>
    '<button class="case" onclick="investigate(\\''+c.id+'\\')">'+c.title+' (expect '+c.expected+')</button>').join('');
  const st = await getj('/api/near/status');
  document.getElementById('backend').textContent = st.anchor_backend;
  document.getElementById('nearstatus').textContent = st.rpc_error ? ('unreachable: '+st.rpc_error) : (st.chain_id+' @ block '+st.latest_block_height);
}
async function investigate(caseId){
  const out = await post('/api/investigate',{case:caseId});
  current = {caseId, ...out};
  const quotes = out.receipt.findings.flatMap(f => f.evidence.map(e =>
    '<div class="quote">&quot;'+e.quote+'&quot;<div class="meta">'+e.source+' / '+e.document_id+', '+e.locator+' (finding '+f.id+')</div></div>')).join('');
  document.getElementById('result').innerHTML =
    '<div style="margin-top:12px">'+chip(out.verdict)+'</div>'+
    '<div style="margin:10px 0;font-size:16px">'+out.reason+'</div>'+ quotes +
    '<div class="meta">Receipt hash (SHA-256 of the canonical receipt + verdict):</div><div class="hash">'+out.receipt_hash+'</div>';
  document.getElementById('anchorout').innerHTML = '';
}
async function doAnchor(){
  if(!current){ alert('Investigate a case first'); return; }
  const out = await post('/api/anchor',{case:current.caseId});
  document.getElementById('anchorout').innerHTML =
    '<div class="meta" style="margin-top:10px">Anchored via <b>'+out.anchor.backend+'</b>, record '+out.anchor.record_id+' at '+out.anchor.anchored_at+'</div><div class="hash">'+out.anchor.receipt_hash+'</div>';
}
async function doVerify(tamper){
  if(!current){ alert('Investigate a case first'); return; }
  const receipt = JSON.parse(JSON.stringify(current.receipt));
  if(tamper){ receipt.findings[0].evidence[0].quote = receipt.findings[0].evidence[0].quote.replace('22:00','22:0X'); }
  const out = await post('/api/verify',{receipt, verdict: current.verdict});
  const row = (k,v) => '<div>'+k+': '+(v?'<span class="ok">YES</span>':'<span class="bad">NO</span>')+'</div>';
  document.getElementById('anchorout').innerHTML =
    '<div style="margin-top:10px"><b>'+(tamper?'Tampered copy':'Receipt')+' re-check</b>'+
    row('Hash matches an anchored record for this exact receipt', out.anchored && out.hash_consistent)+
    row('Anchored record exists', out.anchored)+
    row('Engine re-run reproduces the verdict ('+out.recomputed_verdict+')', out.verdict_match)+
    '<div style="margin-top:6px">Overall: '+(out.ok?'<span class="ok">VERIFIED</span>':'<span class="bad">FAILED</span>')+'</div></div>';
}
async function doMsCreate(){
  const out = await post('/api/milestone/create',{milestone_id:document.getElementById('msid').value,
    amount:document.getElementById('msamt').value, beneficiary:document.getElementById('msben').value});
  document.getElementById('msout').innerHTML = '<div class="meta" style="margin-top:8px">'+JSON.stringify(out)+'</div>';
}
async function doMsRelease(){
  if(!current){ alert('Investigate a case first'); return; }
  const out = await post('/api/milestone/release',{milestone_id:document.getElementById('msid').value, case:current.caseId});
  document.getElementById('msout').innerHTML = '<div style="margin-top:8px">'+
    (out.released?'<span class="ok">RELEASED</span>':'<span class="bad">REFUSED</span>')+': '+out.reason+
    '<div class="meta">Milestone state: '+out.milestone.state+'</div></div>';
}
loadCases();
</script>
</body></html>"""


def _json(handler, obj, status=200):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the demo log readable
        pass

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/cases":
            _json(self, list_cases())
        elif self.path == "/api/near/status":
            out = {"anchor_backend": ANCHOR.backend, "rpc_error": None}
            try:
                from client import NearRpc

                out.update(NearRpc(os.environ.get("NEAR_RPC_URL", "https://rpc.testnet.near.org")).status())
            except Exception as exc:  # RPC is a status display, never fatal
                out["rpc_error"] = str(exc)[:160]
            _json(self, out)
        else:
            _json(self, {"error": "not found"}, 404)

    def do_POST(self):
        try:
            data = self._body()
            if self.path == "/api/investigate":
                out = run_case(data["case"])
                out["receipt_hash"] = receipt_hash(out["receipt"], out["verdict"])
                _json(self, out)
            elif self.path == "/api/anchor":
                # Re-run server-side: never anchor a client-supplied receipt.
                out = run_case(data["case"])
                record = ANCHOR.anchor(out["receipt"], out["verdict"])
                _json(self, {"anchor": record, "verdict": out["verdict"]})
            elif self.path == "/api/verify":
                receipt, verdict = data["receipt"], data["verdict"]
                h = receipt_hash(receipt, verdict)
                record = ANCHOR.get(h)
                check = recheck(receipt, verdict)
                _json(
                    self,
                    {
                        "receipt_hash": h,
                        "anchored": record is not None,
                        "anchor": record,
                        # The hash is recomputed from the supplied receipt;
                        # it is "consistent" iff it resolves to an anchor
                        # record carrying the same verdict.
                        "hash_consistent": bool(record and record["verdict"] == verdict),
                        "recomputed_verdict": check["recomputed_verdict"],
                        "verdict_match": check["verdict_match"],
                        "ok": bool(record and record["verdict"] == verdict and check["verdict_match"]),
                    },
                )
            elif self.path == "/api/milestone/create":
                record = GATE.create(data["milestone_id"], str(data["amount"]), data["beneficiary"])
                _json(self, record)
            elif self.path == "/api/milestone/release":
                out = run_case(data["case"])
                ANCHOR.anchor(out["receipt"], out["verdict"])  # anchor, then gate on it
                _json(self, GATE.attempt_release(data["milestone_id"], out["receipt"], out["verdict"]))
            else:
                _json(self, {"error": "not found"}, 404)
        except (ValueError, KeyError) as exc:
            _json(self, {"error": str(exc)}, 400)
        except Exception as exc:  # surface, never swallow
            _json(self, {"error": f"{type(exc).__name__}: {exc}"}, 500)


def main():
    host = os.environ.get("DEMO_HOST", "127.0.0.1")
    port = int(os.environ.get("DEMO_PORT", "8791"))
    print(f"VERDICT x NEAR demo on http://{host}:{port}  (anchor backend: {ANCHOR.backend})")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
