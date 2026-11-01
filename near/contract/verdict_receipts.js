// VERDICT Receipts: NEAR testnet contract (near-sdk-js).
// WINDOW WORK (C133, built 2026-11-01).
//
// What it stores:
//   receipts:   receipt_hash -> { receipt_hash, verdict, question,
//                                 recorder, anchored_at, tx_hash }
//   milestones: milestone_id -> { milestone_id, amount, beneficiary,
//                                 state, receipt_hash }
//
// How the on-chain rules relate to app/milestone.py (stated exactly,
// review round 1, B3): the contract enforces the SUBSET of the
// milestone gate that a contract can enforce: the receipt is
// anchored (it exists in this contract's storage) and the stored
// verdict is ALLOW. The Python gate enforces two further checks the
// contract cannot perform: the receipt hash recomputes from the
// receipt, and re-running the deterministic engine reproduces the
// verdict. The rules are therefore NOT identical, and the on-chain
// escrow in this contract is exercised by the contract test suite in
// isolation; the demo's milestone flow runs the Python gate.
//   - record_receipt is idempotent per hash: first writer wins, the
//     stored record never changes afterwards.
//   - release_milestone pays the beneficiary only when the stored
//     receipt for the given hash has verdict "ALLOW". The caller
//     cannot pass a verdict in; the contract reads its own record.
//   Known limits, gated to the deploy step (review round 1, B1/B2):
//   record_receipt is permissionless and a receipt is not bound to a
//   milestone, so a self-recorded or replayed ALLOW can satisfy this
//   on-chain check. Do not pitch this contract as a verified escrow
//   gate until those are fixed or the claim is narrowed; see the
//   DEPLOY GATE in DEPLOY_RUNBOOK.md.
//
// Build (from this directory):
//   npm install --ignore-scripts && npm run setup
//   npm run build        # produces build/verdict_receipts.wasm
//   npm test             # state-machine suite on the compiled WASM
// Deploy (testnet, needs a funded testnet account):
//   see DEPLOY_RUNBOOK.md in the competition folder.
//
// Status at slice 2 (2026-11-02): compiled and tested locally
// (35-check state-machine suite at the time of writing, since
// extended); NOT deployed, no transaction broadcast. The demo runs
// against the local anchor log by default, whose records share the
// receipt fields above and add backend, record_id and contract_id.

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
    // Storage floor (review round 1, M4): a dust escrow whose storage
    // cost exceeds its value is a drain on the contract account, not
    // a milestone. 0.1 NEAR minimum.
    assert(
      deposit >= 100000000000000000000000n,
      'milestone amount is below the 0.1 NEAR minimum (storage floor)'
    );
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
