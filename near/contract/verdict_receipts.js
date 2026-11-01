// VERDICT Receipts — NEAR testnet contract (near-sdk-js).
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
    assert(receipt_hash && receipt_hash.length === 64, 'receipt_hash must be a sha256 hex string');
    assert(['ALLOW', 'BLOCK', 'REVIEW'].includes(verdict), 'verdict must be ALLOW, BLOCK or REVIEW');
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
      tx_hash: near.transactionHash ? near.transactionHash() : null,
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
    assert(!this.milestones.get(milestone_id), 'milestone already exists');
    const deposit = near.attachedDeposit();
    assert(deposit > 0n, 'attach the milestone amount as the deposit');
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
