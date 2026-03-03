# 00. Overview

## Reading Order

1. [00-overview.md](00-overview.md) — what this profile defines
2. [01-evaluation-boundary.md](01-evaluation-boundary.md) — where the gate sits
3. [03-architecture.md](03-architecture.md) — core contract, threat model, integrity, verification
4. [02-iso8583-analysis.md](02-iso8583-analysis.md) — reference analysis: ISO 8583 gateway

---

## What This Profile Defines

This profile extends the Execution Boundary Core Spec for transport-layer systems.

A transport-layer system is one where the primary side-effect is the transmission of a message or request across a network boundary.

The gate sits between the decision to send and the actual send call.

## The Transport Gate Point

In most transport systems, a single function call produces the side-effect:

```
socket.write(data)
http_client.post(url, body)
channel.publish(message)
stub.Method(request)
```

The gate intercepts the path to this call.

```
[message ready to send]
         ↓
[TransportActionEnvelope.build()]
         ↓
[Evaluator]
         ↓
[Decision → Ledger]
         ↓
[send() only if ALLOW]
```

## Relationship to Core Spec

This profile does not redefine core interfaces. It extends them.

| Interface | Core Spec | This profile |
|---|---|---|
| ActionEnvelope | Base fields | + transport_type, destination, payload_size, protocol_version, direction |
| Evaluator | `evaluate(envelope) -> Decision` | Same interface, transport-aware policy |
| Decision | As defined | Unchanged |
| Ledger | Append-only | Unchanged |
| Runtime Adapter | Executes on ALLOW | `send()` is the side-effect |

## What This Profile Does Not Define

- Transport protocol implementations
- Message format parsing (ISO 8583, HTTP, gRPC)
- Policy rules or rule language
- Encryption or authentication
