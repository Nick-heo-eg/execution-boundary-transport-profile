# 02. ISO 8583 Gateway Analysis

## Reference System

[iso-8583-socket-queue](https://github.com/juks/iso-8583-socket-queue) — Node.js ISO 8583 gateway. Used as structural reference for transport gate insertion.

## Runtime Flow

```
1. clientSocket.js:38   socket.on('data')
                        └─ upstream.sendData(socket, data)

2. upstream.js:73       this.sendData()
                        └─ queue.addMessage(sender, data, params)

3. iso8583Queue.js:25   queue.addMessage()
                        └─ new iso8583Packet(msg)     ← schema validation
                           ├─ isValidMessage()
                           ├─ unpack()
                           ├─ pad()
                           └─ validate()              ← field-level validation
                           (returns false on failure — queue not entered)

4. upstream.js:93       this.socket.processQueue()

5. upstream.js:155      socket.processQueue()
                        └─ queue.fetchToProcess()     ← dequeue
                           (marks isProcessed=1, locks terminal)

6. upstream.js:214      socket.write(Buffer.concat(buf))   ← SIDE-EFFECT
```

## Gate Insertion Point

**File:** `upstream.js`
**Line:** between 186 (fetchToProcess) and 214 (socket.write)

```javascript
var messages = queue.fetchToProcess();   // line 186

// ── GATE ─────────────────────────────────────────────
var authorized = [];
for (var i in messages) {
  var envelope = buildTransportEnvelope(messages[i]);
  var decision = evaluator.evaluate(envelope);
  ledger.append(decision);

  if (decision.result === "ALLOW") {
    authorized.push(messages[i]);
  } else {
    queue.releaseTerminal(messages[i].terminalId, messages[i].id);  // state cleanup
    messages[i].sender.reply(buildDenyResponse(messages[i]));
  }
}
messages = authorized;
// ─────────────────────────────────────────────────────

var buf = [];
for (var i in messages) {               // line 191
  buf.push(messages[i].packet.getRawMessage(...));
}
socket.write(Buffer.concat(buf));        // line 214
```

## Boundary Analysis

| Stage | File | Function | Side-effect | Boundary candidate |
|---|---|---|---|---|
| Inbound receive | clientSocket.js:38 | `socket.on('data')` | No | No |
| sendData | upstream.js:73 | `this.sendData` | No | No |
| Packet parse + validate | iso8583Packet.js:6 | `Iso8583Packet()` | No | Weak |
| Queue entry | iso8583Queue.js:25 | `addMessage()` | No | Candidate |
| Terminal lock | iso8583Queue.js:135 | `takeTerminal()` | State mutation | — |
| **fetchToProcess** | iso8583Queue.js:126 | `fetchToProcess()` | isProcessed=1 | **Strong candidate** |
| **socket.write** | upstream.js:214 | `processQueue()` | **Network send** | **Actual boundary** |

## Key Finding

Validation in this system is schema-level only:
- `isValidMessage()` — byte structure
- `validate()` — obligatory fields, numeric types
- `checkExpired()` — expiry window

There is no authorization layer. The gate fills this gap structurally.

## State Cleanup Requirement

`fetchToProcess()` calls `takeTerminal(terminalId, id)` before the gate runs.

On DENY, `releaseTerminal(terminalId, id)` MUST be called explicitly. Without this, the terminal remains permanently locked for the session.

## Reversal Impact

DENY at the gate does not trigger auto-reversal. Auto-reversal is triggered by `sender.hasGone()` on client disconnect — a separate code path.

Gate-level DENY is therefore safe with respect to the reversal mechanism.

## Upstream Activity

Last commit: 2023-03-01. Repository is structurally stable, low maintenance activity.
Used as reference implementation only — not a dependency.
