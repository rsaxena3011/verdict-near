// VERDICT Receipts: NEAR testnet contract (near-sdk-js).
// WINDOW WORK (C133, built 2026-11-01).
//
// What it stores:
//   receipts:   receipt_hash -> { receipt_hash, verdict, question,
//                                 recorder, anchored_at, tx_hash }
//   milestones: milestone_id -> { milestone_id, amount, beneficiary,
//                                 state, receipt_hash }
//
// The rules mirror app/milestone.py exactly:
//   - record_receipt is idempotent per hash: first writer wins, the
//     stored record never changes afterwards.
//   - release_milestone pays the beneficiary only when the stored
//     receipt for the given hash has verdict "ALLOW". The caller
//     cannot pass a verdict in; the contract reads its own record.
//     That is the business gate on chain: money moves on a verified
//     receipt, not on a claim.
//
// Build (from this directory):
//   npm install
//   npm run build        # produces build/verdict_receipts.wasm
// Deploy (testnet, needs a funded testnet account):
//   near deploy <contract-account.testnet> build/verdict_receipts.wasm
//
// Status at slice 1 (2026-11-01): source complete; deploy is a later
// step (funded testnet account + first record_receipt are recorded as
// remaining work in the build log). The demo runs today against the
// local anchor log, which stores the identical record shape.

import { NearBindgen, near, call, view, UnorderedMap, assert } from 'near-sdk-js';

@NearBindgen({})
class VerdictReceipts {
  receipts = new UnorderedMap('r');
  milestones = new UnorderedMap('m');

  @call({})
  record_receipt({ receipt_hash, verdict, question }) {
    // Non-payable: the compiled SDK wrapper already panics with
    // "Function is not payable" when a deposit reaches a non-payable
    // method (verified against the built WASM by the test suite,
    // review round 1, M-3). This assert is defence in depth behind
    // the wrapper, in case wrapper conventions ever change.
    assert(near.attachedDeposit() === 0n, 'record_receipt does not accept a deposit');
    assert(
      typeof receipt_hash === 'string' && /^[0-9a-f]{64}$/.test(receipt_hash),
      'receipt_hash must be a lowercase sha256 hex string'
    );
    assert(['ALLOW', 'BLOCK', 'REVIEW'].includes(verdict), 'verdict must be ALLOW, BLOCK or REVIEW');
    // The question is display text, not evidence; cap it so storage
    // costs stay bounded and predictable (review round 1, minor).
    assert(!question || question.length <= 1024, 'question is capped at 1024 characters');
    const existing = this.receipts.get(receipt_hash);
    if (existing) {
      return JSON.parse(existing);
    }
    const record = {
      receipt_hash,
      verdict,
      question: question || '',
      recorder: near.predecessorAccountId(),
      anchored_at: new Date(Number(near.blockTimestamp() / 1000000n)).toISOString(),
      // A contract cannot know its own transaction hash (the hash is
      // of the signed transaction and exists before execution). The
      // caller learns it from the broadcast result and stores it as
      // the anchor record_id (see app/anchor.py, NearAnchor.anchor).
      // near-sdk-js 2.0.0 exports no transactionHash accessor anyway;
      // referencing it only produced a bundler warning.
      tx_hash: null,
    };
    this.receipts.set(receipt_hash, JSON.stringify(record));
    near.log(`receipt anchored: ${receipt_hash} -> ${verdict}`);
    return record;
  }

  @view({})
  get_receipt({ receipt_hash }) {
    const raw = this.receipts.get(receipt_hash);
    return raw ? JSON.parse(raw) : null;
  }

  @call({ payableFunction: true })
  create_milestone({ milestone_id, beneficiary }) {
    const deposit = near.attachedDeposit();
    assert(deposit > 0n, 'attach the milestone amount as the deposit');
    assert(beneficiary && beneficiary.length >= 2, 'a beneficiary account id is required');
    assert(!this.milestones.get(milestone_id), 'milestone already exists');
    const record = {
      milestone_id,
      amount: deposit.toString(),
      beneficiary,
      funder: near.predecessorAccountId(),
      state: 'HELD',
      receipt_hash: null,
    };
    this.milestones.set(milestone_id, JSON.stringify(record));
    return record;
  }

  @view({})
  get_milestone({ milestone_id }) {
    const raw = this.milestones.get(milestone_id);
    return raw ? JSON.parse(raw) : null;
  }

  @call({})
  release_milestone({ milestone_id, receipt_hash }) {
    assert(near.attachedDeposit() === 0n, 'release_milestone does not accept a deposit');
    assert(
      typeof receipt_hash === 'string' && /^[0-9a-f]{64}$/.test(receipt_hash),
      'receipt_hash must be a lowercase sha256 hex string'
    );
    const raw = this.milestones.get(milestone_id);
    assert(raw, 'unknown milestone');
    const milestone = JSON.parse(raw);
    assert(milestone.state === 'HELD', 'milestone is not HELD (already released?)');
    const receiptRaw = this.receipts.get(receipt_hash);
    assert(receiptRaw, 'receipt is not anchored on this contract');
    const receipt = JSON.parse(receiptRaw);
    assert(
      receipt.verdict === 'ALLOW',
      `verdict is ${receipt.verdict}; only a verified ALLOW releases a milestone`
    );
    milestone.state = 'RELEASED';
    milestone.receipt_hash = receipt_hash;
    this.milestones.set(milestone_id, JSON.stringify(milestone));
    const promise = near.promiseBatchCreate(milestone.beneficiary);
    near.promiseBatchActionTransfer(promise, BigInt(milestone.amount));
    near.log(`milestone released: ${milestone_id} on receipt ${receipt_hash}`);
    return milestone;
  }
}
