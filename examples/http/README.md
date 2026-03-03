# HTTP Transport Gate Demo

**Same Core. Different Transport. Identical Boundary Pattern.**

No server. No network. Transport envelope simulation only.

## Run

```bash
python3 examples/http/demo.py
```

## What This Demonstrates

| Item | Status |
|---|---|
| TransportEnvelope constructed from HTTP request | ✔ |
| Evaluator — pure function, no side-effects | ✔ |
| Decision with `proof_hash` | ✔ |
| Ledger records DENY (negative proof) | ✔ |
| `send_http()` called only on ALLOW | ✔ |
| send suppression explicitly logged | ✔ |
| No external dependencies | ✔ |

## Gate Point

```
POST /transfer (body constructed)
   ↓
TransportEnvelope.from_http()
   ↓
evaluate(envelope)              ← side-effect free
   ↓
Decision + ledger_append()      ← unconditional
   ↓
── EXECUTION BOUNDARY ──────────
if decision.result == "ALLOW":
    send_http(envelope)         ← only here
else:
    SUPPRESSED
────────────────────────────────
```

## Policy

```
amount <= 100,000  →  ALLOW
amount >  100,000  →  DENY (AMOUNT_EXCEEDS_LIMIT)
```

## Relationship to ISO 8583 Demo

Both demos use the same Core Spec pattern:

```
Envelope → Evaluator → Decision → Ledger → send() (ALLOW only)
```

The transport type changes. The boundary structure does not.
