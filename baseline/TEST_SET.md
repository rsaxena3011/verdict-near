# C097 VERDICT test set (designed 2026-10-23, runs Oct 25)

Purpose: prove the two-agent loop + deterministic layer behave on more than the golden pair, and put a number on the headline claim. Scoring mirrors the Canon Lock family discipline: catches and false alarms are always reported together, and a wrong ALLOW on a planted break is a P0 failure.

## How it runs
- Breadth cases run IN-PROCESS via test_harness.py: fixture rows are injected in place of the Zetaris fetch, but the agents still make real Nemotron calls through Nightshift and the deterministic layer decides. This keeps 30 cases affordable (a full store swap + driver restart per case would take ~30s of restart alone).
- Cases 1 and 2 ALSO run full-stack through the live Zetaris stores before the freeze, so the submitted evidence includes end-to-end runs, not only harness runs.
- Ground truth is written here, before any run. It is never edited after a run; surprises are logged as defects, not relabelled.

## Cases
Golden (live-stack + harness):
1. Seed stores as-is. Expect: LK-001 BLOCK (DR-002 tag + quote; RV-001 supporting), LK-002 ALLOW (DR-001 quote).
2. Live-edit flip: LK-001 corrected to a 23:30 close, DR-002 re-tagged by ingestion. Expect: LK-001 ALLOW, with memory showing the prior BLOCK.

Attack cases (harness):
3. Deleted source line: a lock whose draft and review rows are absent entirely. Expect REVIEW, basis "no quoted evidence". Never ALLOW.
4. Paraphrase contradiction, no structured tag: lock "The cafe closes at 22:00", draft quote "The shutters came down at half past eleven." with contradicts empty. Expect: never ALLOW, never BLOCK from the deterministic layer; REVIEW (agent-only break claim) or BLOCK only if an agent produces the quote AND the layer's rule is met (it cannot be, no tag) — so the expected verdict is REVIEW with the disagreement visible.
5. Missed-evidence trap: the contradicting line sits in REVIEWS only, tagged; the draft looks clean. Investigator expected to miss or catch; Challenger must surface it (its job). Expect final BLOCK; if the Challenger misses it too, that is a logged defect, and the case counts as a miss, not a relabel.
6. Unsupported ALLOW trap: lock with a draft quote that mentions the subject but does not confirm it ("Meera was mentioned in the staff chat."). Expect: not ALLOW unless a genuinely supporting quote exists; REVIEW acceptable, ALLOW is a false pass and counts against the headline.

Generated breadth cases (7-30): 24 synthetic cafe/story locks built by construction, 8 per expected class:
- 8 BLOCK: draft or review row carries the contradicts tag + a quote that states the breaking fact.
- 8 ALLOW: a draft quote directly supports the lock, no tags anywhere.
- 8 REVIEW: no evidence rows, or evidence that mentions without resolving.
Names, times, props and wording vary; no case repeats a golden quote.

## Scoring
- Catch = planted BLOCK returned BLOCK. REVIEW on a planted BLOCK = half catch, reported separately.
- False pass = planted BLOCK returned ALLOW: P0, target ZERO.
- False alarm = clean/ALLOW case returned BLOCK: target zero; REVIEW on a clean case = soft alarm, reported.
- Headline reported as three numbers together: catches / half catches / false passes, plus false alarms.
- Agent health: per-case record of investigator/challenger sources (model vs fallback) and any rejected (hallucinated) quotes. A case decided while either agent was on the structured fallback is reported as such, never hidden.
