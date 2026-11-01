"""One-screen judge UI. SCAFFOLD for the Oct 25 build — not wired yet.

Planned surface (single page):
  [ question box ]  [ Investigate ]
  -> verdict badge (ALLOW / BLOCK / REVIEW)
  -> why panel (one plain-English line)
  -> receipt: the query, the rows, the source, the quoted lines
  -> "cached fallback" badge when live_nemotron is False

FastAPI + a single HTML page. Deps (pin Oct 22): fastapi, uvicorn.
The /investigate route calls Investigator.investigate then decide(), and
returns receipt.to_dict() verbatim. Nothing in the UI ever re-words a quote.
"""

# from fastapi import FastAPI
# from verdict.investigator import Investigator
# from verdict.models import Question
# from verdict.sources import FileSource
# from verdict.verdict_engine import decide
#
# app = FastAPI()
#
# @app.post("/investigate")
# def investigate(q: str):
#     ...build connectors (live Zetaris by then)...
#     result = decide(investigator.investigate(Question(q)))
#     return {
#         "verdict": result.verdict.value,
#         "why": result.reason,
#         "receipt": result.receipt.to_dict(),
#     }
