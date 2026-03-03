# Execution Boundary Transport Profile (v0.1)

Transport-layer application profile for [Execution Boundary Core Spec](https://github.com/Nick-heo-eg/execution-boundary-core-spec) (commit: `d3e239b`).

Extends the core boundary model for systems where side-effects occur at a network send point: `socket.write()`, HTTP POST, gRPC call, ISO 8583 upstream forward.

---

## Layered Model

```
execution-boundary-core-spec          ← structural definition
         ↑
execution-boundary-transport-profile  ← this repository (transport profile)
         ↑
execution-gate                        (reference implementation)
```

---

## Dependency

**[execution-boundary-core-spec v0.1](https://github.com/Nick-heo-eg/execution-boundary-core-spec)**

Core Spec defines the base ActionEnvelope, Decision, Ledger, and Runtime Adapter interfaces. This profile extends them for transport contexts. Core fields are not modified.

---

## 1. Scope

This profile applies to systems where:

- A message or request is proposed for transmission
- The transmission constitutes an observable side-effect
- Authorization must be determined before the send occurs

Applicable transports:

| Transport | Side-effect point |
|---|---|
| TCP socket | `socket.write()` |
| HTTP | POST / PUT / PATCH request dispatch |
| gRPC | `stub.Method()` call |
| ISO 8583 | Upstream forward to acquiring host |
| Message broker | `publish()` / `produce()` |
| RPC | Remote procedure invocation |

---

## 2. Transport ActionEnvelope Extension

Base fields are defined in Core Spec. This profile adds:

```json
{
  "action_id": "uuid",
  "action_type": "transport.send",
  "resource": "string",
  "parameters": "object",
  "context_hash": "string",
  "timestamp": "string",

  "transport_type": "tcp | http | grpc | iso8583 | amqp | kafka",
  "destination": "string",
  "payload_size": "number | null",
  "protocol_version": "string | null",
  "direction": "outbound | inbound"
}
```

### Extended Field Definitions

**`transport_type`**
Protocol identifier. Determines how `destination` and `parameters` are interpreted.
Values: `tcp`, `http`, `grpc`, `iso8583`, `amqp`, `kafka`

**`destination`**
Target endpoint. Format is transport-specific.
Examples: `"192.168.1.1:8583"`, `"https://api.example.com/v1/payment"`, `"orders.topic"`

**`payload_size`**
Byte length of the payload at proposal time. `null` if unavailable.
Used for policy evaluation (e.g. size limits). Does not affect authorization by itself.

**`protocol_version`**
Protocol version string. `null` if not applicable.
Examples: `"HTTP/1.1"`, `"ISO-8583-1987"`, `"gRPC/1.0"`

**`direction`**
`outbound` — gateway initiates send to upstream.
`inbound` — gateway receives and forwards inward.

---

## 3. Extension Rules

Extension is **add-only**.

- Core Spec fields MUST NOT be modified or removed
- Transport-specific fields are additive
- `action_type` for transport sends MUST be `"transport.send"` or a namespaced variant (e.g. `"transport.iso8583.forward"`)
- Extended fields that are unavailable MUST be set to `null`, not omitted

---

## 4. Evaluation Boundary

The gate sits between validation and the send call.

```
Inbound message
   ↓
Schema validation (transport-level)
   ↓
Transport ActionEnvelope (built here)
   ↓
Evaluator (side-effect free)
   ↓
Decision (ALLOW | DENY | HOLD)
   ↓
Ledger Append (unconditional)
   ↓
[ send() / socket.write() / publish() ]  ← ALLOW only
   ↓
Upstream / peer
```

**Validation ≠ Authorization.**
A message that passes schema validation may still be DENY at the authorization boundary.

---

## 5. State Model

Inherits Core Spec state model:

```
PROPOSED → EVALUATED → ALLOWED → EXECUTED (send occurred)
                     → DENIED  → CLOSED   (send suppressed)
                     → HOLD    → PENDING  (deferred)
```

On DENY: the send MUST NOT occur. The Decision is appended to the ledger. Suppression is provable via `proof_hash`.

---

## 6. Fail-Closed

Inherits Core Spec fail-closed requirement.

Transport-specific implication: if the Evaluator is unavailable or times out, the send MUST NOT proceed. The system defaults to DENY.

A transport gateway that sends on evaluator failure is not a gated system.

---

## 7. Negative Proof

On DENY, the ledger entry provides proof that:

- A message was proposed for transmission
- It was evaluated and denied
- The send did not occur

This is structurally distinct from a message that was never proposed.

---

## 8. Reference Demonstrations

Same Core. Different Transport. Identical Boundary Pattern.

### ISO 8583 — `examples/iso8583/demo.py`

```bash
python3 examples/iso8583/demo.py
```

Gate between `queue.fetchToProcess()` and `socket.write()` in an ISO 8583 gateway.
5 scenarios — MTI filter, amount threshold, processing code block.
Ledger root hash included.

### HTTP — `examples/http/demo.py`

```bash
python3 examples/http/demo.py
```

Gate before `http_client.post()` dispatch.
5 scenarios — amount threshold policy.
Same Envelope → Evaluator → Decision → Ledger → send() pattern.

### Socket — `examples/socket/` _(pending)_

Minimal TCP gate before `socket.write()`.

---

## 9. Non-Goals

This profile does not define:

- Transport protocol implementations
- Message format specifications
- Encryption or TLS configuration
- Network topology or routing
- Policy language or rule syntax

---

## 10. Repository Structure

```
/docs
  00-overview.md
  01-evaluation-boundary.md
  02-iso8583-analysis.md
/spec
  transport-envelope.schema.json
/examples
  /iso8583
  /http
  /socket
README.md
```

---

## License

MIT
