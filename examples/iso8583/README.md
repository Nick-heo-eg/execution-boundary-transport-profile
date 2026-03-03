# ISO 8583 Gate Demo

Demonstrates transport gate insertion in an ISO 8583 gateway.

## Gate Point

`upstream.js` — between `queue.fetchToProcess()` and `socket.write(Buffer.concat(buf))`

See [docs/02-iso8583-analysis.md](../../docs/02-iso8583-analysis.md) for full structural analysis.

## Scenarios

1. **Baseline** — valid ISO 8583 message → ALLOW → send succeeds
2. **Schema reject** — malformed packet → validation fails → queue not entered
3. **Gate DENY** — valid schema, policy reject → send suppressed → DENY ledger entry

## Status

Reference analysis complete. Implementation pending.
