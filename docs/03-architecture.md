# 03. Architecture

**Same Core. Different Transport. Identical Boundary Pattern.**

No external dependencies. No network. No financial system.
Every claim on this page is verifiable by running the test suite.

---

## 1. What This Is

An execution boundary is a structural constraint:
a proposed action must be evaluated before it can be executed.
If the evaluator denies it, the action does not occur — and that denial is recorded.

This is not a firewall.
This is not a heuristic guard.
This is not a probabilistic policy layer.
This is a deterministic execution boundary.

The gate sits between the decision to send and the send call itself.
Authorization is pre-execution. Execution is not the default.

---

## 2. Core Contract

Five properties hold at every evaluation, across every transport type:

| Property | Guarantee |
|---|---|
| Deterministic Evaluation | Same envelope → same decision, every time |
| Transport Independence | Core logic unaffected by transport type |
| Pre-Execution Decision | Execution occurs only after ALLOW |
| Tamper Evidence | Merkle root detects any mutation to any entry |
| External Verifiability | Canonical export + root replay without live system |

These are not aspirational. Each property has automated tests that verify it directly.

---

## 3. Comparison

| Model | Characteristic |
|---|---|
| Prompt-based guard | Outcome varies by input phrasing — non-deterministic by construction |
| Post-hoc logging | Records what happened; execution has already occurred |
| Heuristic filter | Threshold-based, subject to tuning and drift |
| **Execution Boundary** | **Deterministic outcome + pre-execution decision + tamper-evident record** |

The distinction is structural, not qualitative.
A system that evaluates after execution, or that produces non-deterministic results, is not an execution boundary regardless of its name.

---

## 4. Integrity

Ledger integrity is enforced at three layers:

**Layer 1 — Per-decision: `proof_hash`**
```
proof_hash = SHA-256(decision_id + action_id + result + timestamp)
```
Unique per invocation. Non-replayable. Present on every decision — ALLOW and DENY alike.

**Layer 2 — Per-ledger: Merkle root**
```
leaf      = SHA-256(canonical_json(entry))
root      = Merkle tree over all leaves
canonical = sort_keys=True, separators=(",", ":")
```
Any mutation to any field of any entry changes the root.
Order matters — entries cannot be resequenced without detection.

**Layer 3 — Per-export: canonical file verification**
```
export_canonical(path) → writes ledger + merkle_root to JSON file
verify_from_file(path, stored_root) → recomputes root from file, compares
```
Verification requires only the file and the stored root.
No live system. No shared state. Independent replay.

---

## 5. External Verification

```python
from boundary_core.ledger import verify_from_file

# Stored root was captured at export time, held separately
result = verify_from_file("ledger_20260303_iso8583.json", stored_root)
# True  → ledger is intact
# False → at least one entry was modified after export
```

This enables verification by any party with access to the file and the root,
without access to the system that produced the ledger, at any point after export.

---

## 6. Invariant Proof

Five categories of automated tests verify the boundary properties directly:

| Category | What it verifies |
|---|---|
| Invariant tests | Transport type does not affect decision outcome (ISO 8583 vs HTTP, identical policy vector) |
| Determinism tests | Same input → same result across N=100 evaluations; fail-closed on missing amount |
| Uniqueness tests | `proof_hash` is unique per invocation; no cross-contamination between evaluations |
| Merkle tamper tests | Result mutation, amount mutation, append order all change the root |
| Export replay tests | `verify_from_file` passes on intact export; fails on any file mutation |

```
python3 -m pytest tests/ -v   # 28 passed
```

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
