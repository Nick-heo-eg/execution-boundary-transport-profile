# 03. Architecture

**Same Core. Different Transport. Identical Boundary Pattern.**

No external dependencies. No network. No financial system.
Every claim on this page is verifiable by running the test suite.

---

## 1. What This Is

An execution boundary is a structural constraint: a proposed action must pass through an evaluator before it can be executed. If the evaluator denies it, the action does not occur — and that denial is recorded.

This profile applies that constraint to transport-layer systems, where the side-effect is a network send:

```
socket.write()   http_client.post()   channel.publish()   stub.Method()
```

The gate sits between the decision to send and the send call itself.

This is not a firewall. It is not a rate limiter. It is not a content filter.
It is a pre-execution authorization boundary with cryptographic proof of every decision.

---

## 2. Core Contract

```
TransportEnvelope
    ↓
evaluate(envelope)          ← pure function, no side effects, no I/O
    ↓
Decision(result, proof_hash)
    ↓
Ledger.append()             ← unconditional: ALLOW and DENY both recorded
    ↓
if ALLOW → send()           ← execution boundary: the only path to the wire
```

Five properties hold at every evaluation:

| Property | Guarantee |
|---|---|
| Deterministic | Same policy vector → same result, every time |
| Transport-independent | ISO 8583 and HTTP produce identical outcomes for identical inputs |
| Fail-closed | Missing or invalid amount → DENY, never ALLOW |
| Proof-bearing | Every decision carries a unique SHA-256 `proof_hash` |
| Append-only | DENY entries cannot be removed or suppressed from the ledger |

---

## 3. Threat Model

This boundary addresses a specific failure mode: execution that proceeds without a recorded authorization decision.

| Pattern | Problem | This boundary |
|---|---|---|
| Randomized guard | Non-deterministic — same input may produce different outcome | Evaluator is pure: determinism verified at N=100 |
| LLM-based policy | Probabilistic by construction — not auditable | No probabilistic component anywhere in the evaluation path |
| Post-hoc logging | Records what happened, not what was authorized | Decision is recorded before execution. DENY is recorded even though nothing happened |
| Silent suppression | Denial leaves no trace | Every DENY appended to ledger with `proof_hash` |
| Log mutation | Audit trail can be altered | Merkle root: any entry mutation changes the root |

The boundary does not prevent a caller from bypassing it entirely.
What it guarantees: if the boundary is used, the record is complete and tamper-evident.

---

## 4. Integrity

Ledger integrity is enforced at three layers:

**Per-decision**: `proof_hash = SHA-256(decision_id + action_id + result + timestamp)`
Unique per invocation. Non-replayable. Cannot be fabricated without the original inputs.

**Per-ledger (in-memory)**: Merkle root over canonical JSON of all entries.
`leaf = SHA-256(canonical_json(entry))` where canonical = `sort_keys=True, separators=(",", ":")`.
Any mutation to any field of any entry changes the root.

**Per-export (on-disk)**: `export_canonical(path)` writes the full ledger with its Merkle root embedded.
`verify_from_file(path, root)` recomputes the root from the file and compares — no live ledger required.

```
entries[0..n]
    ↓ SHA-256(canonical JSON)
leaf_hashes[0..n]
    ↓ Bitcoin-style Merkle tree (odd count: last leaf duplicated)
merkle_root
    ↓ written to ledger_YYYYMMDD.json
export file
    ↓ verify_from_file(path, stored_root)
True / False
```

---

## 5. External Verification

The exported ledger file is self-contained. Verification requires only:
- the file
- the expected root (stored separately from the file)

```python
from boundary_core.ledger import verify_from_file

result = verify_from_file("ledger_20260303_iso8583.json", stored_root)
# True  → ledger is intact
# False → at least one entry was modified after export
```

This enables verification by any party with access to the file and the root,
without access to the system that produced the ledger.

---

## 6. Invariant Proof

The following properties are verified automatically on every run:

```
python3 -m pytest tests/ -v
```

| Test file | Coverage | Count |
|---|---|---|
| `test_pattern_invariant.py` | Transport independence (ISO 8583 / HTTP), fail-closed, negative proof, proof_hash presence | 7 |
| `test_determinism.py` | Result stability N=100, reason_code stability, proof_hash format (valid SHA-256), uniqueness per invocation, independence across evaluations | 5 |
| `test_merkle_ledger.py` | Root determinism, tamper detection (result mutation, amount mutation), append sensitivity, order sensitivity, verify round-trip, empty/single-entry edge cases | 9 |
| `test_canonical_export.py` | Export structure, verify pass/fail, file-level tamper detection, idempotency, canonical JSON format | 7 |
| **Total** | | **28** |

All 28 tests are structural — they verify the boundary properties directly, not indirectly through integration paths.

---

## 7. Running the Demos

No setup beyond the standard library.

```bash
python3 examples/iso8583/demo.py
python3 examples/http/demo.py
```

Each demo:
1. Builds `TransportEnvelope` objects for 5 scenarios
2. Evaluates each through the shared `evaluate()` function
3. Appends all decisions (ALLOW and DENY) to a `MerkleLedger`
4. Exports a canonical JSON ledger file
5. Verifies the exported file against the Merkle root

Expected output ends with:
```
Merkle root: <64-char hex>
Exported:    ledger_YYYYMMDD_{transport}.json
Verified:    True
Execution is not default.
```
