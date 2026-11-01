# VERDICT (README, FIXED DRAFT for the public repo - C097, Track 02)
Status: FIXED DRAFT, 2026-10-27 ~06:30 IST. Applies MERGED_DRAFT_REVIEW.md
(2026-10-27) plus PC_EVIDENCE_2026-10-27.md (2026-10-27 ~04:25 IST).
Not published, not pushed, not submitted. The public repo URL is NOT
yet known and is deliberately left as a placeholder below. Do not
invent or publish a URL from this draft.
Supersedes README_DRAFT_PUBLIC_REPO.md for filing purposes; the
original is kept for diff. A re-review round on THIS fixed draft is
still owed before filing. Nothing here authorises filing.
Team: SaxenaWave. Track 02: The Agent That Can Explain Why.

Evidence status of the claims below (four-level labelling, per the
merge): Demonstrated items are actual runs, receipts, or inspected
artifacts. Implemented-but-undemonstrated items are in code without
submission evidence attached. Intended items are design direction.
Unavailable items are flagged TO CONFIRM and must not be published as
fact.

## What it is
VERDICT is a federated evidence investigator. You lock facts, you
draft, you collect reviews. VERDICT federates the three stores through
Zetaris, investigates one question, and answers ALLOW / BLOCK / REVIEW
with the receipt attached: the query, the rows, the source, the quoted
lines. NVIDIA Nemotron (via the Nightshift / Meterless local runtime)
runs the investigate step. The verdict step is deterministic Python.
An LLM never emits a verdict. Scope, stated plainly: VERDICT checks
locked facts and selected evidence-backed conditions, not every claim
in a document.

## Invariants (enforced in code, not in prose)
1. No verdict without quoted evidence.
2. Never ALLOW when any connected source failed to answer.
3. A claimed contradiction needs BOTH sides quoted, or it degrades to
   REVIEW.
4. Same question against unchanged evidence and unchanged relevant
   configuration gives the same verdict (scoped determinism: a changed
   verdict after an evidence edit is expected, not a failure).

## Measured results (from cases_results.json, Oct 23 19:02, read on the PC 2026-10-27, and RESULTS_SECOND_LOOK.md only)
Full 28-case run, shipping configuration, completed 2026-10-24 about
00:32 IST:
- 27/28 exact
- Catches 9/9, as stated in PC evidence, not recomputed from
  cases_results.json, which does not label catches
- False passes 0
- False alarms 0
Single disclosed miss: breadth_allow_03, REVIEW against an expected
ALLOW, held by the Challenger veto (the quote does not identify the
transfer as rent, so it can be true while the rent-due date is false).
Expectations were never relabelled. Do not quote the older
cases_results_run2.json (Oct 23 18:11, 25/28): it is superseded.

## Layout and the layout warning
READ THIS FIRST. Two layouts exist, and one command does not fit both.
The PC running copy is FLAT: *.py directly under /root/verdict/. The
workspace copy is src/-LAYOUT: verdict/src/*.py. `python3
run_verdict.py` works in the flat layout and fails in the src/ layout.
The setup commands below target the FLAT layout, the layout proven by
the Oct 22-27 runs on the PC. Before publishing, the published repo
must be reconciled to ONE layout, and these commands re-verified on a
clean checkout of that exact layout. Do not publish one command for
both layouts.

Flat layout (PC running copy, proven):
- `run_verdict.py` - core loop: Investigator, Challenger,
  deterministic layer, decision memory, receipt writer.
- `agents.py` - Investigator and Challenger, verbatim-quote
  validation. Both agents run on NVIDIA Nemotron through Meterless
  Nightshift.
- `decide.py` - deterministic verdict layer, labelled non-agent.
- `second_look.py` - REVIEW-only second look, wired into
  test_harness.py and run_verdict.py behind the VERDICT_SECOND_LOOK
  flag (default on; "0" disables it completely and restores the
  earlier behaviour). Promotion semantics (what a promotion changes:
  verdict, classification, or review category only) require code
  confirmation before filing; they are not asserted as settled here.
- `zetaris_client.py` - Zetaris REST client. Reads credentials from
  `~/verdict/.env` and never prints them. On the PC build that
  resolves to /root/verdict/.env (mode 600, dated Oct 22; contents
  never read).
- `model_client.py` - Nemotron access via the Nightshift runtime.
  Requested model in code: nvidia/nemotron-3.5-lightning-30b-a3b.
  Requested is not routed: receipts show Nightshift auto routing
  (requested_mode meterless/auto, routed_mode auto) with several
  models in the mix (ultra, super-vl, lightning as judge_model). Base
  origin in code: http://127.0.0.1:8088; API path:
  http://127.0.0.1:8088/v1. The origin is not the endpoint. Every call
  returns a receipt with the model asked for, the model that actually
  answered, token usage, and the Meterless receipt block when present.
- `ui.py` - one-screen receipt view generator. The --serve flag is
  verified in both the PC copy and the workspace copy: it serves
  http://127.0.0.1:8765 and writes ui/index.html, which exists on the
  PC.
- `test_harness.py`, `score_cases.py`, `cases.json`, `mirrors.json`,
  `probe.json` - test harness, scoring, and case inputs.
- `fixtures/*.sample.json` - STRUCTURAL SAMPLES ONLY, fictional
  content. See the sample inputs section below. They are not the real
  locked facts, drafts, or reviews.
- `tests/test_verdict_engine.py` - deterministic golden-path tests
  (no network, no LLM, per the workspace README).
- `server.py` - SCAFFOLD ONLY. It exists in the workspace copy only,
  with its FastAPI code commented out ("not wired yet"), and does NOT
  exist in the PC running copy at all. Do not describe it as a working
  server until it is wired and verified. Do not list fastapi/uvicorn
  as installed dependencies.
## Development tool note (Oct 27 2026, in-window)
Cursor 3.27.14 was used on Oct 27 2026, inside the build window, to edit this submission package. The original VERDICT build (Oct 22-23) was done in other tools, not Cursor. Cursor installation on Oct 26 alone is not claimed as use, and no Cursor use is claimed for the original build.


## Published layout (Oct 27 2026)
The published repo uses the src/ layout: code in src/, tests in tests/, fixtures in fixtures/. The PC running copy is flat (modules at the top of /root/verdict/). On Oct 27 2026 the core modules (agents, decide, edit_lock, explain, gen_cases, model_client, run_verdict, second_look, test_harness, ui, zetaris_client) and cases.json, mirrors.json, probe.json were verified byte-identical between the PC flat copy and this src/ copy. The only layout difference is the directory prefix; the entry point in the published layout is src/run_verdict.py, not run_verdict.py at the repo root.

## Setup
Prerequisites, as documented in the recon and build files (verify each
on the machine you run on):
- Python version TO CONFIRM. Do not claim 3.12: WSL python3 reports
  3.14.4, no python3.12 binary exists in WSL, yet the PC pycache is
  cpython-312, so the interpreter that ran the code is not the current
  WSL python3 (likely a Windows-side Python 3.12, unverified).
- A running Zetaris local stack (per the recon: docker login to the
  hackathon registry, preflight, docker compose up; UI
  http://localhost:3000, REST http://localhost:8888/api/v1.0, JDBC
  10000, avoid port 8889). The three stores (locks, drafts, reviews)
  must be registered through the Zetaris platform surface, not by raw
  DDL alone. At the Oct 27 04:25 IST PC check the live stack was 4
  containers, all Up and healthy: zetaris-api-1, zetaris-driver-1,
  zetaris-postgres-1, zetaris-ui-1. The Oct 22 "verify.sh 9/9" is
  nine verification checks, a different 9 from the container count
  and from the 9/9 catches; never conflate the three.
- A running Nightshift (Meterless) runtime, base origin
  http://127.0.0.1:8088, API path http://127.0.0.1:8088/v1, with a
  Nemotron provider configured (in the PC build: a free NVIDIA Build
  key in Nightshift Setup, Providers, for the cloud lane; local models
  are optional per the recon). Without a configured provider,
  Nightshift returns no_provider_configured and no model call will
  succeed.
- A `.env` file at `~/verdict/.env` (on the PC build:
  /root/verdict/.env), holding ZETARIS_REST_URL, ZETARIS_API_KEY, and
  ZETARIS_ORG_ID. NEVER commit this file. NEVER paste its values into
  an issue, a screenshot, or this README. See `.env.example` below for
  the shape only.

Steps (published src/ layout; verified Oct 27 2026 on a clean staging copy):
1. Clone the public repo: https://github.com/rsaxena3011/verdict (public, created Oct 27 2026).
2. Copy `.env.example` to `~/verdict/.env` and fill in your own
   values. Do not commit the filled file.
3. Start Zetaris and Nightshift as above and confirm both respond
   (Zetaris REST reachable; Nightshift GET /v1/models returns 401
   without a key, which means the runtime is up and key-protected, or
   200 with a valid runtime key).
4. Run the deterministic tests from the repo root: `python3 -m unittest discover -s tests -v` (verified Oct 27 2026: 7 tests, OK).
5. Run the golden path from the repo root: `python3 src/run_verdict.py`. Entry-point import verified Oct 27 2026 on the published layout. A live run needs Zetaris and Nightshift up, as above; it is not verified from a clean checkout without those runtimes.

## Usage
- Golden run (published layout): `python3 src/run_verdict.py` - runs the
  Investigator and Challenger over the Zetaris-federated stores,
  applies the deterministic layer and the second look, writes a
  receipt, and renders the one-screen UI from the latest receipt
  (regenerate the UI from the golden run receipt before recording, per
  DEMO_SCRIPT_DRAFT.md).
- Second look control: `VERDICT_SECOND_LOOK=1` is the default (on).
  `VERDICT_SECOND_LOOK=0` disables it completely.
- Live-edit flip (demonstrated in the build, two runs, different
  outcomes): edit a lock in the Zetaris store (in the golden demo,
  LK-001 from a 22:00 close to a 23:30 close) and rerun. The Oct 23
  flip went BLOCK to ALLOW, with the prior BLOCK read back from the
  product decision memory. The Oct 27 live flip, same edit, returned
  REVIEW, not ALLOW: second-look gates failed because no quote states
  the decisive 23:30 close; the store was then restored to 22:00 and
  the next run returned BLOCK again. Do not present the Oct 27 flip
  as ALLOW. The draft's 23:15 line sits between the original 22:00
  lock and the edited 23:30 lock, which is why the flip is the right
  test.
- UI: `python3 ui.py --serve` serves http://127.0.0.1:8765 and writes
  ui/index.html (verified on both copies).
- Two-agent interaction evidence gap, stated plainly: the code
  implements the Investigator/Challenger interaction, but no captured
  interaction proof (visible handoff, contest, deterministic
  resolution on one case) is attached yet. That capture is the
  highest-value remaining evidence item.

## Dependencies
Consolidated position, see the pins section below for the full
status: shipping Python modules have no third-party pip imports;
workspace requirements.txt has no package lines, only a comment about
the deterministic core; the PC running copy has no requirements.txt;
sponsor-stack package pins were never written to a file; Python point
version and Zetaris/Nightshift runtime versions remain TO CONFIRM;
fastapi and uvicorn are not listed as installed shipping dependencies
based on the unconnected server.py scaffold. What is known from
the code:
- Deterministic core: Python standard library only (per
  requirements.txt comment).
- Model bridge: Windows curl.exe subprocess interop in the PC build
  (model_client.py), because WSL cannot reach host 8088 directly in
  that setup. Environment-specific; on macOS or native Linux that
  bridge does not apply.
- Zetaris client: HTTP via Python standard library (urllib in the PC
  health script pattern; verify against zetaris_client.py imports
  before publishing a list).
- The scaffold server.py names fastapi and uvicorn as intended deps,
  but its code is commented out and it is absent from the PC running
  copy. Do not list them as installed dependencies until the server is
  wired.
## Dependency pins (honest status, 2026-10-27)
What is actually pinned, from files in hand, not from memory:
- Deterministic core and clients: Python standard library only.
  verdict/requirements.txt contains no package lines at all, only
  the comment "v0 (deterministic core only, stdlib, no network).
  Sponsor-stack deps pin on Oct 22 recon." Workspace imports confirm
  this for the shipping modules: collections, csv, datetime, glob,
  html, io, json, os, re, subprocess, sys, time, urllib.request,
  uuid, plus local modules. No third-party pip package is imported
  by the shipping code. The model bridge is Windows curl.exe
  subprocess interop, a platform tool, not a pip package.
- Zetaris and Nightshift are runtimes, not pip packages (Zetaris:
  4 Docker containers, Oct 27 PC check, all Up and healthy;
  Nightshift: local Windows runtime). No version pins for either
  runtime were found in the workspace files or on the PC copy, so
  none are claimed.
- Still TO CONFIRM, not invented: Python point version (WSL python3
  reports 3.14.4, no python3.12 binary in WSL, PC pycache is
  cpython-312; Windows python 3.12.10 corroborates the cpython-312
  pycache but does not prove that interpreter ran VERDICT, so neither
  "Python 3.12" nor "Python 3.12.10" is published as the runner);
  any pinned sponsor dependency beyond stdlib (no requirements.txt
  exists on the PC running copy at all, and the Oct 22 recon pin was
  never written into a file); fastapi and uvicorn (named in server.py
  as intended deps, but that file's FastAPI code is commented out
  and it is absent from the PC running copy, so they are not listed
  as installed dependencies).
- Bottom line: the repo can honestly say "stdlib only, no
  third-party pip imports in the shipping code" and must still carry
  Python version and runtime versions as TO CONFIRM. A full
  package==version list cannot be written from the files in hand.

## Sample inputs / outputs
Sample inputs are the structural samples in `fixtures/` (fictional
content, clearly labelled as such in the files):
- `fixtures/locks.sample.json`: LK-001, "The cafe's closing time is
  22:00, not 23:00", quote "The cafe closes at 22:00 sharp, every
  day." LK-002, "The owner's name is Meera", quote "Owner: Meera
  Sharma."
- `fixtures/drafts.sample.json`: DR-001, draft states the owner's
  name correctly, quote "Meera wiped down the counter." DR-002, draft
  says the cafe is open till late, contradicts LK-001, quote "The last
  customer left at 23:15, and Meera locked up." (23:15 sits between the
  22:00 lock and the edited 23:30 lock.)
- `fixtures/reviews.sample.json`: RV-001, reviewer flagged the
  closing-time scene as feeling late, quote "Scene 7 reads like
  midnight, not a 22:00 close." RV-001 is review context only, not an
  authoritative lock.
- `fixtures/schema.md`: quote must be verbatim (a paraphrase is not
  evidence); empty or blank quotes are treated as unquoted; a
  contradiction degrades to REVIEW unless both sides carry quotes.
Sample outputs (golden pair, from RESULTS_SECOND_LOOK.md, live stores):
- LK-001: BLOCK (structured contradiction, DR-002). Second look not
  invoked.
- LK-002: ALLOW via Layer 1 (name=Meera, verb=wiped). On that run Pass
  1 proposed REVIEW, so the deterministic rule replaced the model
  variance.
Full 28-case outputs: the detailed results file is
`cases_results.json`, copied from the PC into this workspace on
2026-10-27 and re-counted from the file itself: 28 decisions, 27 ok,
single miss breadth_allow_03 (C03-LOCK, REVIEW vs expected ALLOW).
Do not fabricate a results table beyond that file. Note on
provenance: the 9/9 catches figure is as stated in the deck and PC
evidence, not recomputed from cases_results.json, which does not
label catches.

## Logs / traces
- Every model call returns a receipt: requested model, routed model,
  token usage, Meterless receipt block when present. Requested is not
  routed: receipts show Nightshift auto routing with several models in
  the mix; never write "served by lightning" for every call.
- Every verdict receipt carries: the query, the rows, the source, the
  quoted lines, and any machine line that fired (including second-look
  rule lines).
- Decision memory: the product's own decision memory records prior
  verdicts, so the Oct 23 flip (BLOCK to ALLOW after a lock edit)
  and the Oct 27 flip (REVIEW after the same edit, then restore to
  BLOCK) are on the record, not just on the screen. (Described; no
  attached artifact yet.)
- Meterless Engine: H-MEM pattern, persistent auditable memory, as
  named in run_verdict.py code: every decision is appended to
  decision_memory.jsonl, read back on the next run, so memory
  influences the next decision, with a FLIPPED badge in the UI when
  the verdict differs from the prior verdict in memory. Claimed only
  as a pattern implementation in VERDICT code, not a Meterless SDK
  engine.
- Test harness inputs and expectations: `cases.json`,
  `mirrors.json`, `probe.json`, with ground truth written before any
  run and never edited after a run (per TEST_SET.md). Ground-truth
  provenance is asserted from the build record; attach file history
  or timestamps before treating it as proven.
[TO ATTACH BEFORE PUBLISH: a real receipt JSON and a real harness log,
copied from the PC build, with any credential redacted. Do not paste a
receipt that contains a key, a token, or a secret.]

## .env.example (shape only, no real values)
```
# Copy to ~/verdict/.env. NEVER commit the filled file. NEVER share its values.
ZETARIS_REST_URL=http://localhost:8888/api/v1.0
ZETARIS_API_KEY=YOUR_OWN_API_KEY_HERE
ZETARIS_ORG_ID=1
```
Note: ZETARIS_ORG_ID=1 is the default in zetaris_client.py when the
key is absent; it is a default, not a credential. The API key
placeholder above is not a real key. The Nightshift runtime key is NOT
in this file: in the PC build it lives in the Nightshift runtime state
file and is never printed or copied into the repo.

## SAMPLE_MODE fallback
DRAFT WARNING: no SAMPLE_MODE flag exists in any PC or workspace .py
file (confirmed by the Oct 27 PC evidence run: no SAMPLE_MODE string
anywhere). The recon guide recommends a SAMPLE_MODE=true fallback, and
the old workspace README says the investigator transport is injectable
so a demo can replay recorded responses (fixture-backed). Those two
facts do NOT prove a working SAMPLE_MODE flag exists in the shipping
code. This README describes the fallback as INTENDED, not shipped.
Intended behaviour, to verify or implement before claiming it:
- With the fallback on, the demo replays recorded model responses
  against the fixture stores instead of making live Nemotron calls,
  and every replayed screen is labelled as a replay, not a live call.
- With the fallback off, all calls go live through Nightshift, and any
  failed source degrades the verdict to REVIEW (invariant 2).
Until that verification lands, do not claim SAMPLE_MODE=true works.

## Pre-existing components (summary; full text in the submission form fixed draft)
VERDICT extends the builder's own earlier continuity-checker work
(Canon Lock: deterministic ALLOW / BLOCK / REVIEW checker, TypeScript
matcher ported for a prior hackathon entry, Canon Lock Cloud, October
2026). The deterministic verdict idea and the lock data model predate
this event. Everything that touches the sponsor stack is new: the
Zetaris federation layer, the agent implementation, the
Meterless/Nightshift and Nemotron integration, the memory engine
implementation, the UI, and all code in the repo was written during
the build window, except the disclosed scaffold item: the verdict
scaffold directory was created before the window opened, is declared
as a pre-existing component, and its contents are TO CONFIRM (no git
history exists on the PC copy or the workspace copy; do not silently
present pre-window scaffold code as in-window work). Open-source
libraries are used under their licences. Fixture texts are short
fictional story fragments written by the builder for his own
productions, used as demo data only.
