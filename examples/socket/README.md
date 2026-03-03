# TCP Socket Gate Demo

Minimal gate before `socket.write()`.

## Gate Point

```javascript
// Before:
socket.write(data);

// After:
var envelope = buildTransportEnvelope({
  action_type: "transport.tcp.send",
  transport_type: "tcp",
  destination: socket.remoteAddress + ":" + socket.remotePort,
  payload_size: data.length,
  direction: "outbound"
});
var decision = evaluator.evaluate(envelope);
ledger.append(decision);
if (decision.result === "ALLOW") {
  socket.write(data);
}
```

## Scenarios

1. Allowed destination → ALLOW → write proceeds
2. Blocked destination → DENY → write suppressed
3. Evaluator unavailable → fail-closed → DENY

## Status

Pending implementation.
