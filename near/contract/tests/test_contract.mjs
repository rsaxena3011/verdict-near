// State-machine tests for the compiled verdict_receipts contract.
//
// Runs the REAL build/verdict_receipts.wasm under the local NEAR host
// (tests/near_host.mjs): no sandbox, no network, no testnet account.
// Every expectation below is one of the contract's stated rules:
//   - record_receipt is idempotent per hash, first writer wins, the
//     stored record never changes afterwards;
//   - the hash must be a sha256 hex string and the verdict must be
//     ALLOW, BLOCK or REVIEW, or the call panics;
//   - create_milestone is payable: it holds exactly the attached
//     deposit, once per milestone id;
//   - release_milestone pays the BENEFICIARY (never the caller) only
//     when the stored receipt for the given hash has verdict ALLOW;
//     the caller cannot pass a verdict in; a released milestone
//     cannot release twice.
//
// Run: npm test   (from near/contract/)

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { NearHost } from './near_host.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const wasm = readFileSync(join(here, '..', 'build', 'verdict_receipts.wasm'));
const host = new NearHost(wasm);

const H_ALLOW = 'a'.repeat(64);
const H_BLOCK = 'b'.repeat(64);
const H_REVIEW = 'c'.repeat(64);
const H_UNKNOWN = 'd'.repeat(64);
const TEN = 10000000000000000000000000n; // 10 NEAR in yocto, as a deposit

let passed = 0;
let failed = 0;
function check(name, cond, detail = '') {
  if (cond) {
    passed++;
    console.log(`ok   - ${name}`);
  } else {
    failed++;
    console.log(`FAIL - ${name} ${detail}`);
  }
}
function expectPanic(name, result, needle) {
  check(name, !result.ok && result.error.includes(needle), `(got ok=${result.ok}, error=${result.error || ''})`);
}
function transfers(result) {
  return result.promises.flatMap((p) => p.actions.filter((a) => a.type === 'transfer').map((a) => ({ to: p.accountId, amount: a.amount })));
}

// ------------------------------------------------------------ receipts

let r = host.call('record_receipt', { receipt_hash: H_ALLOW, verdict: 'ALLOW', question: 'Is the cafe deal consistent?' });
check('record_receipt returns the stored record', r.ok && r.value.receipt_hash === H_ALLOW && r.value.verdict === 'ALLOW', JSON.stringify(r));
check('record carries the recorder and no self-tx-hash claim', r.ok && r.value.recorder === 'recorder.testnet' && r.value.tx_hash === null);

r = host.call('get_receipt', { receipt_hash: H_ALLOW });
check('get_receipt reads the record back', r.ok && r.value && r.value.verdict === 'ALLOW' && r.value.question === 'Is the cafe deal consistent?');

// First writer wins: a second record attempt on the same hash, even
// claiming a different verdict, must not change the stored record.
r = host.call('record_receipt', { receipt_hash: H_ALLOW, verdict: 'BLOCK', question: 'forged' }, { predecessorAccountId: 'attacker.testnet' });
check('re-record returns the original record', r.ok && r.value.verdict === 'ALLOW' && r.value.recorder === 'recorder.testnet');
r = host.call('get_receipt', { receipt_hash: H_ALLOW });
check('stored record is unchanged after a re-record attempt', r.ok && r.value.verdict === 'ALLOW' && r.value.question === 'Is the cafe deal consistent?');

r = host.call('record_receipt', { receipt_hash: 'abc', verdict: 'ALLOW' });
expectPanic('non-sha256 hash is rejected', r, 'sha256');

r = host.call('record_receipt', { receipt_hash: 'g'.repeat(64), verdict: 'ALLOW' });
expectPanic('a 64-char non-hex hash is rejected', r, 'sha256');

r = host.call('record_receipt', { receipt_hash: 'e'.repeat(64), verdict: 'ALLOW', question: 'x'.repeat(1025) });
expectPanic('an oversized question is rejected', r, '1024');

r = host.call('record_receipt', { receipt_hash: 'e'.repeat(64), verdict: 'ALLOW' }, { attachedDeposit: 1000n });
expectPanic('a deposit on record_receipt is rejected, not stranded', r, 'not payable');

r = host.call('record_receipt', { receipt_hash: H_BLOCK, verdict: 'MAYBE' });
expectPanic('verdict outside ALLOW/BLOCK/REVIEW is rejected', r, 'verdict must be ALLOW, BLOCK or REVIEW');

r = host.call('record_receipt', { receipt_hash: H_BLOCK, verdict: 'BLOCK' });
check('question defaults to empty string', r.ok && r.value.question === '');

r = host.call('get_receipt', { receipt_hash: H_UNKNOWN });
check('get_receipt on an unknown hash returns null', r.ok && r.value === null);

r = host.call('record_receipt', { receipt_hash: 'A'.repeat(64), verdict: 'ALLOW' });
expectPanic('an uppercase hash is rejected (lowercase hex only)', r, 'lowercase sha256');

r = host.call('record_receipt', { receipt_hash: 'f'.repeat(64), verdict: 'REVIEW', question: 'q'.repeat(1024) });
check('a question of exactly 1024 characters is accepted (boundary)', r.ok && r.value.question.length === 1024);

// ------------------------------------------------------------ milestones

r = host.call('create_milestone', { milestone_id: 'ms-1', beneficiary: 'cafe-operator.testnet' }, { attachedDeposit: 0n });
expectPanic('create_milestone with no deposit is rejected', r, 'deposit');

r = host.call('create_milestone', { milestone_id: 'ms-1' }, { attachedDeposit: TEN });
expectPanic('create_milestone without a beneficiary is rejected', r, 'beneficiary');

// Assert ORDER: when deposit, beneficiary and existence would all
// fail, the deposit message must win (deposit is checked first).
host.call('create_milestone', { milestone_id: 'ms-dup', beneficiary: 'cafe-operator.testnet' }, { attachedDeposit: TEN });
r = host.call('create_milestone', { milestone_id: 'ms-dup' }, { attachedDeposit: 0n });
expectPanic('create assert order: deposit is checked before beneficiary and existence', r, 'deposit');

r = host.call('create_milestone', { milestone_id: 'ms-1', beneficiary: 'cafe-operator.testnet' }, { attachedDeposit: TEN });
check('create_milestone holds the exact attached deposit', r.ok && r.value.state === 'HELD' && r.value.amount === TEN.toString() && r.value.beneficiary === 'cafe-operator.testnet' && r.value.receipt_hash === null, JSON.stringify(r.value));

r = host.call('create_milestone', { milestone_id: 'ms-1', beneficiary: 'other.testnet' }, { attachedDeposit: TEN });
expectPanic('duplicate milestone id is rejected', r, 'already exists');

r = host.call('get_milestone', { milestone_id: 'ms-1' });
check('get_milestone reads the record back', r.ok && r.value.state === 'HELD');

// Release paths: unanchored, BLOCK, REVIEW, unknown milestone.
r = host.call('release_milestone', { milestone_id: 'ms-1', receipt_hash: H_UNKNOWN });
expectPanic('release on an unanchored receipt is rejected', r, 'not anchored');
check('no transfer happened on the unanchored attempt', transfers(r).length === 0);

r = host.call('release_milestone', { milestone_id: 'ms-1', receipt_hash: H_BLOCK });
expectPanic('release on a BLOCK receipt is rejected', r, 'only a verified ALLOW releases');
check('no transfer happened on the BLOCK attempt', transfers(r).length === 0);

host.call('record_receipt', { receipt_hash: H_REVIEW, verdict: 'REVIEW' });
r = host.call('release_milestone', { milestone_id: 'ms-1', receipt_hash: H_REVIEW });
expectPanic('release on a REVIEW receipt is rejected', r, 'only a verified ALLOW releases');

r = host.call('get_milestone', { milestone_id: 'ms-1' });
check('milestone is still HELD after refused releases', r.ok && r.value.state === 'HELD');

r = host.call('release_milestone', { milestone_id: 'ms-nope', receipt_hash: H_ALLOW });
expectPanic('release on an unknown milestone is rejected', r, 'unknown milestone');

r = host.call('release_milestone', { milestone_id: 'ms-1', receipt_hash: H_ALLOW }, { attachedDeposit: 1000n });
expectPanic('a deposit on release_milestone is rejected, not stranded', r, 'not payable');

r = host.call('release_milestone', { milestone_id: 'ms-1', receipt_hash: 'not-a-hash' });
expectPanic('release validates the hash format before lookup', r, 'sha256');

// Assert ORDER in release: an unknown milestone paired with a
// malformed hash must produce the format panic, not "unknown
// milestone" (format is checked before the lookup happens).
r = host.call('release_milestone', { milestone_id: 'ms-never-existed', receipt_hash: 'zz' });
expectPanic('release assert order: hash format is checked before the milestone lookup', r, 'sha256');

// Happy path, triggered by a third party: the money still goes to
// the beneficiary, exactly the held amount, exactly once.
r = host.call('release_milestone', { milestone_id: 'ms-1', receipt_hash: H_ALLOW }, { predecessorAccountId: 'third-party.testnet' });
const t = transfers(r);
check('release on an ALLOW receipt succeeds', r.ok && r.value.state === 'RELEASED' && r.value.receipt_hash === H_ALLOW, JSON.stringify(r.value));
check('exactly one transfer, of the held amount, to the beneficiary', t.length === 1 && t[0].to === 'cafe-operator.testnet' && t[0].amount === TEN, JSON.stringify(t, (k, v) => (typeof v === 'bigint' ? v.toString() : v)));

r = host.call('release_milestone', { milestone_id: 'ms-1', receipt_hash: H_ALLOW });
expectPanic('a released milestone cannot release twice', r, 'not HELD');
check('no second transfer happened', transfers(r).length === 0);

r = host.call('get_milestone', { milestone_id: 'ms-nope' });
check('get_milestone on an unknown id returns null', r.ok && r.value === null);

console.log(`\ncontract tests: ${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
