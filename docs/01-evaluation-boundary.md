# 01. Evaluation Boundary

## Where the Gate Sits

The gate is positioned between the last point of schema validation and the first point where a network side-effect can occur.

```
Inbound message
   ↓
Transport-level parsing / schema validation
   ↓                          ← validation ends here
TransportActionEnvelope build
   ↓
Evaluator                     ← authorization here
   ↓
Decision + Ledger append
   ↓
send() / write() / publish()  ← ALLOW only
   ↓
Upstream
```

## Validation vs Authorization

**Validation** confirms the message is well-formed.
**Authorization** determines whether sending it is permitted.

These are separate operations. A schema-valid message may still be DENY.

Example:
- An ISO 8583 0200 message with valid fields → passes validation
- The same message with amount exceeding policy limit → DENY at authorization

The gate does not replace validation. It follows it.

## The Candidate Gate Point

In a typical transport gateway, the send point is a single call in a queue-draining loop:

```javascript
// Pattern: queue.fetchToProcess() → socket.write()
var messages = queue.fetchToProcess();
var buf = [];
for (var i in messages) {
  buf.push(messages[i].packet.getRawMessage());
}
socket.write(Buffer.concat(buf));  // ← gate sits before this line
```

The gate intercepts at this point. On DENY:
- The message is not added to `buf`
- `socket.write()` does not transmit it
- A DENY Decision is appended to the ledger
- The sender receives a rejection response

## State Cleanup on DENY

Some transports maintain state between queue entry and send (e.g. terminal locking in ISO 8583 gateways).

On DENY, the gate MUST release any state that was acquired during queue processing. Failure to release will produce resource leaks or permanent lock conditions.

This is implementation-specific but must be addressed by any conformant transport adapter.

## Hold Semantics

HOLD defers the send. The message remains in a pending state until re-evaluation produces ALLOW or DENY.

Transport-specific timeout behavior on HOLD is implementation-defined.
