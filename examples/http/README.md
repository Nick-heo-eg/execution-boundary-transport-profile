# HTTP Gate Demo

Demonstrates transport gate before HTTP request dispatch.

## Gate Point

Between request construction and `http_client.post()` / `fetch()` call.

## Envelope Fields

```json
{
  "action_type": "transport.http.post",
  "transport_type": "http",
  "destination": "https://api.example.com/v1/payment",
  "payload_size": 256,
  "protocol_version": "HTTP/1.1",
  "direction": "outbound"
}
```

## Scenarios

1. Allowed destination → ALLOW → request dispatched
2. Blocked destination → DENY → request suppressed, DENY logged
3. Payload size exceeded → DENY

## Status

Pending implementation.
