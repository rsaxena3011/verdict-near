# VERDICT x NEAR — verdicts an agent cannot fake

## What it is

An evidence investigator for the agent economy. An agent's claim goes
in, together with the evidence behind it. A deterministic engine (never
a language model) returns one verdict — ALLOW, BLOCK, or REVIEW — with
the verbatim quoted evidence attached as a receipt. The receipt's
SHA-256 hash is anchored outside the agent's control (a local
append-only log in the standalone demo; the NEAR testnet contract when
configured). Any third party can re-check a verdict later: recompute
the hash, confirm the anchor, and re-run the deterministic engine from
the receipt alone.

On top of the receipt sits a milestone gate: escrowed money is
released only when a verified ALLOW receipt is presented. A BLOCK, a
REVIEW, an edited receipt, or an unanchored receipt all refuse.

## The problem

Agents increasingly act and get paid on their own word. When an
agent's report is wrong — a draft that breaks a locked term, a claim
with no source behind it — there is usually no artefact a third party
can check after the fact. VERDICT makes the artefact: a verdict that
carries its own quoted evidence, a hash that commits to the exact
receipt, and an anchor the author cannot rewrite.

## Tracks

- **agents** (Agent Economy) — primary. Agents produce receipts that
  other agents and humans verify before acting or paying.
- **security** (AI Security & Defense) — the verification gates are
  the defence layer, demonstrated live: a source that does not answer
  means REVIEW, never ALLOW; a claimed contradiction with an unquoted
  side degrades to REVIEW instead of being invented into a BLOCK; an
  edited receipt fails the re-check.
- **business** (Autonomous Business) — the milestone gate: release is
  gated on a verified evidence receipt, not on manual approval.

## Run it (standalone demo, no network, no accounts)

Requires Python 3.10+ only. Everything in this section runs offline.

1. Run the baseline engine tests.
   Do: `python3 -m unittest discover -s baseline/tests`
   See: `OK` (7 tests). This is the unmodified baseline suite.
2. Run the window-work tests.
   Do: `python3 -m unittest discover -s tests`
   See: `OK` (16 tests; re-verified 2026-11-12).
3. Run the contract tests.
   Do: `cd near/contract && npm test`
   See: `contract tests: 41 passed, 0 failed` (re-verified 2026-11-12).
4. Start the demo surface.
   Do: `python3 app/server.py`
   See: `VERDICT x NEAR demo on http://127.0.0.1:8791 (anchor backend: local)`.
5. Investigate the planted contradiction.
   Do: open http://127.0.0.1:8791 and click "Planted contradiction:
   draft breaks the closing lock", or
   `curl -s -X POST localhost:8791/api/investigate -d '{"case":"block_contradiction"}'`
   See: verdict `BLOCK`, the reason quoting both sides ("closes at
   22:00 sharp" vs "Last customer left at 23:15"), and a receipt hash.
6. Anchor and re-check.
   Do: click "Anchor this receipt", then "Verify receipt".
   See: an anchor record (`local-1`, backend `local`) and a re-check
   with hash matched, anchored YES, engine re-run reproduces BLOCK,
   overall VERIFIED. Click "Verify a TAMPERED copy": overall FAILED.
7. Work the milestone gate.
   Do: "Create milestone (HELD)", then "Attempt release with the
   current case's verdict" while the BLOCK case is selected.
   See: REFUSED, state stays HELD. Investigate "Consistent closing
   report" (ALLOW), anchor it via the release flow, attempt release
   again: RELEASED. A milestone releases once.
8. (Optional) Talk to NEAR testnet.
   Do: `pip install -r requirements-near.txt`, restart the server,
   open the page header or `curl -s localhost:8791/api/near/status`.
   See: `chain_id: testnet` with a current block height, fetched live
   from https://rpc.testnet.near.org.

A recorded transcript of steps 5–8 is in RUN_EVIDENCE_2026-11-01.txt.

## How it works

- `baseline/src/verdict/` — the deterministic engine (baseline, see
  below). The investigator gathers findings from sources; `decide()`
  applies fixed rules: missing source → REVIEW; lock-vs-draft
  contradiction with both sides quoted → BLOCK; reviewer conflict →
  REVIEW; claimed contradiction with an unquoted side → REVIEW;
  nothing answers → REVIEW; otherwise ALLOW. Same input, same output.
- `app/engine_runner.py` — wires bundled demo cases (app/cases/) to
  the baseline engine through its file-source connector, offline.
- `app/receipts.py` — the canonical receipt form and its SHA-256 hash,
  plus the re-check: rebuild the engine input from a receipt alone and
  re-run `decide()`.
- `app/anchor.py` — anchor backends with one record shape: the local
  append-only log, and the NEAR testnet backend (record_receipt /
  get_receipt) used when NEAR_ACCOUNT_ID, NEAR_PRIVATE_KEY and
  NEAR_CONTRACT_ID are set.
- `app/milestone.py` — the milestone gate described above.
- `near/client.py` — a small NEAR JSON-RPC client: status and view
  calls unsigned; signed function calls via a hand-rolled Borsh
  serialiser for the single FunctionCall shape (PyNaCl + base58).
- `near/contract/verdict_receipts.js` — the near-sdk-js contract:
  receipt records (first writer wins per hash) and milestone escrow
  whose release reads the stored receipt's verdict from the contract
  itself — the caller cannot pass a verdict in.

## Baseline vs window work (reuse disclosure)

This entry reuses the VERDICT code base, disclosed here as the
hackathon rules require.

- **Baseline (pre-existing, not judged):** everything under
  `baseline/`, a verbatim copy of https://github.com/rsaxena3011/verdict
  at commit `eb1094717ebe0524d3e735c2bc0a526c2218f1a7` (see
  BASELINE.md). That code was the C097 Open Agent Hackathon entry
  (Track 02, filed Oct 27 2026) for a different organiser; it has
  never been submitted to NEAR Hackathon. The local git history of
  this repository starts with the baseline import commit, so the diff
  between the baseline commit and the window-work commits is the
  window work.
- **Window work (built for this hackathon, from Nov 1 2026):**
  everything outside `baseline/` — the demo surface, the demo cases,
  the receipt hash + anchor + re-check layer, the milestone gate, the
  NEAR RPC client, and the NEAR contract source.
- **Libraries and prior work used:** Python standard library (demo,
  engine, tests); `requests`, `pynacl`, `base58` for the optional
  NEAR client only (requirements-near.txt); near-sdk-js for the
  contract (near/contract/). No other pre-existing code.
- **Second project disclosure:** the entrant has one other NEAR
  Hackathon project if and only if a second submission is filed; this
  section will name it before filing. (Placeholder to resolve at
  filing time; a single-project entry deletes this bullet.)

## Status and honest limits (updated 2026-11-12, testnet deploy live)

- Contract deployed to NEAR testnet: `verdict.ratnesh3011.testnet`,
  deploy tx `FKKGXYHysBo7myB1Cs8tdNSmt3TcFTZwfc4zf7iHM1ro`
  (https://testnet.nearblocks.io/txns/FKKGXYHysBo7myB1Cs8tdNSmt3TcFTZwfc4zf7iHM1ro),
  account https://testnet.nearblocks.io/address/verdict.ratnesh3011.testnet.
- First on-chain anchor: BLOCK receipt
  `b87ce8cbc17b481f8f4bfc7399f1c1d22d5c78eac647929ddc63bb6a4d2e2ad5`,
  anchor tx `5fT2WYVspbyjLNc3UwpwpmYD1gTWvVzQzSKL1Hgy1w33`
  (https://testnet.nearblocks.io/txns/5fT2WYVspbyjLNc3UwpwpmYD1gTWvVzQzSKL1Hgy1w33),
  recorder `ratnesh3011.testnet`, anchored 2026-11-12T17:18:45Z.
  Independent read-back via `near view ... get_receipt` returns the same
  record; the third-party re-check through the demo surface returns
  ok / anchored / verdict_match all true; a tampered receipt fails the
  check. Run evidence: RUN_EVIDENCE_2026-11-12.txt.
- Honest claim, narrowed per the deploy gate: this is an
  anchored-verdict release check, not an on-chain escrow demo. The
  on-chain milestone gate is permissionless and unbound (known risks
  B1/B2: anyone can record a hash first; one ALLOW can release any
  milestone) — the strict re-check lives in the demo layer. No claim in
  this README presents the contract as escrow.
- Testnet only. No mainnet spend anywhere in this project. The prize
  payout address on the submission form is a separate mainnet implicit
  account created by the team lead.

## Layout

```
baseline/            pre-existing VERDICT code at commit eb10947 (unmodified)
app/                 demo surface, cases, receipt/anchor/milestone layers
near/client.py       NEAR JSON-RPC client (view + signed function call)
near/contract/       verdict_receipts contract (near-sdk-js)
tests/               window-work tests (stdlib unittest)
RUN_EVIDENCE_2026-11-01.txt   recorded end-to-end run of the demo flow
BASELINE.md          baseline provenance
LICENSE              MIT
```
