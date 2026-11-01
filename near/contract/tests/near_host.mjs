// Minimal NEAR runtime host for testing the compiled contract WASM
// locally, in Node, with no sandbox download and no network.
//
// It implements the standard NEAR env API surface the contract
// imports (registers, input, storage, context reads, value_return,
// logs, and the promise-batch calls this contract uses): a fresh
// instance per call, storage persists across calls, and a panicking
// call rolls its storage writes back, as the real runtime does.
//
// Fidelity limits, stated plainly (review round 1, M6): balances are
// not modelled (account_balance is a constant, deposits are not drawn
// from anywhere, and recorded transfers are never executed or checked
// against a balance), and promises are recorded as data, never
// resolved, so promise ordering and transfer failure are outside what
// this harness can prove. What it does prove is the contract's state
// machine logic under the runtime's call and rollback semantics.
// Host functions this contract never calls (keccak, ecrecover,
// alt_bn128, complex promise combinators) throw if reached, so a
// test can never pass on a stub that pretends to work.

import { createHash } from 'node:crypto';

const REGISTER_ABSENT = 2n ** 64n - 1n;

export class NearHost {
  constructor(wasmBytes) {
    this.module = new WebAssembly.Module(wasmBytes);
    this.storage = new Map(); // hex(key bytes) -> value bytes (Uint8Array)
    this.registers = new Map(); // id (BigInt) -> Uint8Array
    this.instance = null;
    this.resetCallState();
  }

  resetCallState() {
    this.registers = new Map();
    this.inputBytes = new Uint8Array(0);
    this.returnValue = undefined; // decoded JS value after value_return
    this.returnRaw = null;
    this.logs = [];
    this.promises = []; // {id, accountId, actions: [{type, amount?}]}
    this.nextPromiseId = 0n;
    this.ctx = {
      currentAccountId: 'verdict.testnet',
      signerAccountId: 'recorder.testnet',
      predecessorAccountId: 'recorder.testnet',
      attachedDeposit: 0n,
      blockTimestampNs: 1762041600000000000n, // 2025-11-02T00:00:00Z
      blockIndex: 1000n,
    };
  }

  mem() {
    return new DataView(this.instance.exports.memory.buffer);
  }

  memBytes(ptr, len) {
    return new Uint8Array(this.instance.exports.memory.buffer, Number(ptr), Number(len));
  }

  writeMem(ptr, bytes) {
    this.memBytes(ptr, bytes.length).set(bytes);
  }

  readStr(ptr, len) {
    return new TextDecoder().decode(this.memBytes(ptr, len));
  }

  writeU128(ptr, value) {
    const bytes = new Uint8Array(16);
    let v = BigInt(value);
    for (let i = 0; i < 16; i++) {
      bytes[i] = Number(v & 0xffn);
      v >>= 8n;
    }
    this.writeMem(ptr, bytes);
  }

  readU128(ptr) {
    const bytes = this.memBytes(ptr, 16);
    let v = 0n;
    for (let i = 15; i >= 0; i--) v = (v << 8n) | BigInt(bytes[i]);
    return v;
  }

  setRegister(id, bytes) {
    this.registers.set(BigInt(id), bytes);
  }

  getRegister(id) {
    return this.registers.get(BigInt(id));
  }

  env() {
    const h = this;
    const unused = (name) => () => {
      throw new Error(`host function ${name} is not implemented in the local test host (the contract under test must not call it)`);
    };
    return {
      panic_utf8: (len, ptr) => {
        throw new Error(`PANIC: ${h.readStr(ptr, len)}`);
      },
      panic: () => {
        throw new Error('PANIC (no message)');
      },
      register_len: (id) => {
        const r = h.getRegister(id);
        return r === undefined ? REGISTER_ABSENT : BigInt(r.length);
      },
      read_register: (id, ptr) => {
        const r = h.getRegister(id);
        if (r === undefined) throw new Error(`read_register on absent register ${id}`);
        h.writeMem(ptr, r);
      },
      write_register: (id, len, ptr) => {
        h.setRegister(id, new Uint8Array(h.memBytes(ptr, len)));
      },
      input: (id) => {
        h.setRegister(id, h.inputBytes);
      },
      current_account_id: (id) => h.setRegister(id, new TextEncoder().encode(h.ctx.currentAccountId)),
      signer_account_id: (id) => h.setRegister(id, new TextEncoder().encode(h.ctx.signerAccountId)),
      signer_account_pk: (id) => {
        const pk = new Uint8Array(33); // key type 0 (ed25519) + 32 zero bytes
        h.setRegister(id, pk);
      },
      predecessor_account_id: (id) => h.setRegister(id, new TextEncoder().encode(h.ctx.predecessorAccountId)),
      block_index: () => h.ctx.blockIndex,
      block_timestamp: () => h.ctx.blockTimestampNs,
      epoch_height: () => 42n,
      storage_usage: () => {
        let n = 0n;
        for (const [k, v] of h.storage) n += BigInt(k.length / 2 + v.length);
        return n;
      },
      account_balance: (ptr) => h.writeU128(ptr, 1000000000000000000000000000n),
      account_locked_balance: (ptr) => h.writeU128(ptr, 0n),
      attached_deposit: (ptr) => h.writeU128(ptr, h.ctx.attachedDeposit),
      prepaid_gas: () => 300000000000000n,
      used_gas: () => 0n,
      random_seed: (id) => h.setRegister(id, new Uint8Array(32).fill(7)),
      sha256: (len, ptr, id) => {
        const data = new Uint8Array(h.memBytes(ptr, len));
        h.setRegister(id, new Uint8Array(createHash('sha256').update(data).digest()));
      },
      keccak256: unused('keccak256'),
      keccak512: unused('keccak512'),
      ripemd160: unused('ripemd160'),
      ecrecover: unused('ecrecover'),
      value_return: (len, ptr) => {
        h.returnRaw = h.readStr(ptr, len);
        try {
          h.returnValue = JSON.parse(h.returnRaw);
        } catch {
          h.returnValue = h.returnRaw;
        }
      },
      log_utf8: (len, ptr) => {
        h.logs.push(h.readStr(ptr, len));
      },
      log_utf16: (len, ptr) => {
        const bytes = h.memBytes(ptr, len);
        h.logs.push(new TextDecoder('utf-16le').decode(bytes));
      },
      promise_create: unused('promise_create'),
      promise_then: unused('promise_then'),
      promise_and: unused('promise_and'),
      promise_batch_create: (len, ptr) => {
        const accountId = h.readStr(ptr, len);
        const id = h.nextPromiseId++;
        h.promises.push({ id, accountId, actions: [] });
        return id;
      },
      promise_batch_then: unused('promise_batch_then'),
      promise_batch_action_create_account: unused('promise_batch_action_create_account'),
      promise_batch_action_deploy_contract: unused('promise_batch_action_deploy_contract'),
      promise_batch_action_function_call: unused('promise_batch_action_function_call'),
      promise_batch_action_function_call_weight: unused('promise_batch_action_function_call_weight'),
      promise_batch_action_transfer: (promiseId, amountPtr) => {
        const p = h.promises.find((x) => x.id === BigInt(promiseId));
        if (!p) throw new Error(`transfer on unknown promise ${promiseId}`);
        p.actions.push({ type: 'transfer', amount: h.readU128(amountPtr) });
      },
      promise_batch_action_stake: unused('promise_batch_action_stake'),
      promise_batch_action_add_key_with_full_access: unused('promise_batch_action_add_key_with_full_access'),
      promise_batch_action_add_key_with_function_call: unused('promise_batch_action_add_key_with_function_call'),
      promise_batch_action_delete_key: unused('promise_batch_action_delete_key'),
      promise_batch_action_delete_account: unused('promise_batch_action_delete_account'),
      promise_results_count: () => 0n,
      promise_result: unused('promise_result'),
      promise_return: unused('promise_return'),
      storage_write: (keyLen, keyPtr, valLen, valPtr, registerId) => {
        const key = Buffer.from(h.memBytes(keyPtr, keyLen)).toString('hex');
        const val = new Uint8Array(h.memBytes(valPtr, valLen));
        const existed = h.storage.has(key);
        if (existed) h.setRegister(registerId, h.storage.get(key));
        h.storage.set(key, val);
        return existed ? 1n : 0n;
      },
      storage_read: (keyLen, keyPtr, registerId) => {
        const key = Buffer.from(h.memBytes(keyPtr, keyLen)).toString('hex');
        if (!h.storage.has(key)) return 0n;
        h.setRegister(registerId, h.storage.get(key));
        return 1n;
      },
      storage_remove: (keyLen, keyPtr, registerId) => {
        const key = Buffer.from(h.memBytes(keyPtr, keyLen)).toString('hex');
        if (!h.storage.has(key)) return 0n;
        h.setRegister(registerId, h.storage.get(key));
        h.storage.delete(key);
        return 1n;
      },
      storage_has_key: (keyLen, keyPtr) => {
        const key = Buffer.from(h.memBytes(keyPtr, keyLen)).toString('hex');
        return h.storage.has(key) ? 1n : 0n;
      },
      validator_stake: (len, ptr, stakePtr) => h.writeU128(stakePtr, 0n),
      validator_total_stake: (stakePtr) => h.writeU128(stakePtr, 0n),
      alt_bn128_g1_multiexp: unused('alt_bn128_g1_multiexp'),
      alt_bn128_g1_sum: unused('alt_bn128_g1_sum'),
      alt_bn128_pairing_check: unused('alt_bn128_pairing_check'),
    };
  }

  /**
   * Call one contract method the way the NEAR runtime would.
   * ctx overrides: predecessorAccountId, signerAccountId,
   * currentAccountId, attachedDeposit (BigInt), blockTimestampNs.
   * Returns { ok: true, value, logs, promises } or
   *         { ok: false, error } on a contract panic.
   */
  call(method, args = {}, ctx = {}) {
    this.resetCallState();
    Object.assign(this.ctx, ctx);
    this.inputBytes = new TextEncoder().encode(JSON.stringify(args));
    const imports = { env: this.env() };
    this.instance = new WebAssembly.Instance(this.module, imports);
    // Real NEAR semantics: a panicking call is atomic, its storage
    // writes roll back. Snapshot and restore so the harness models
    // that instead of leaking partial writes (review round 1, M6).
    const snapshot = new Map(this.storage);
    try {
      this.instance.exports[method]();
      return { ok: true, value: this.returnValue, logs: this.logs, promises: this.promises };
    } catch (err) {
      this.storage = snapshot;
      return { ok: false, error: String(err && err.message ? err.message : err), logs: this.logs, promises: this.promises };
    }
  }
}
