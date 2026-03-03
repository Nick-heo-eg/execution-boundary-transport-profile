# Deterministic by Construction: Defining the Execution Boundary

Most AI safety discussion focuses on what a model *says*.
This is about what a system *does*.

---

## The Problem Is Structural

When an AI system takes an action — sends a payment, calls an API, writes to a database — the question is not "did the model sound confident?" The question is:

**Was the action authorized? Is there a verifiable record that it was authorized before it happened?**

Prompt-based guards answer this probabilistically. The same input can produce a different output. The guard that blocks a request today might not block the same request tomorrow. That's not a tuning problem. That's a category problem.

A heuristic filter and an execution boundary are not the same kind of thing.

---

## What an Execution Boundary Is

An execution boundary is a structural constraint with five properties:

| Property | Guarantee |
|---|---|
| Deterministic Evaluation | Same envelope → same decision, every time |
| Transport Independence | Core logic unaffected by transport type |
| Pre-Execution Decision | Execution occurs only after ALLOW |
| Tamper Evidence | Merkle root detects any mutation to any entry |
| External Verifiability | Canonical export + root replay without live system |

These are not goals. They are verifiable properties. Each one has automated tests.

The boundary sits between the decision to act and the act itself:

```
Envelope → evaluate() → Decision → Ledger → [ execute only if ALLOW ]
```

`evaluate()` is a pure function. No I/O. No side effects. No randomness.
The decision is recorded before execution — not after.

---

## Why "Deterministic" Is the Defining Property

A system that produces non-deterministic results cannot provide an audit trail that means anything. If the same input might have been allowed or denied depending on conditions you can't reproduce, the record is not a record — it's a log of outcomes that could have been otherwise.

Determinism is not a performance optimization. It's what makes a decision *verifiable*.

> A system that evaluates after execution, or that produces non-deterministic results, is not an execution boundary regardless of its name.

---

## Integrity at Three Layers

The record is protected at three layers:

**Per-decision**: every decision — ALLOW and DENY — carries a `proof_hash`:
```
SHA-256(decision_id + action_id + result + timestamp)
```
Unique per invocation. Non-replayable.

**Per-ledger**: a Merkle root over all decisions. Any mutation to any entry changes the root. Order is preserved.

**Per-export**: the ledger can be exported as canonical JSON. Verification requires only the file and the stored root — no live system, no shared state.

```python
verify_from_file("ledger_20260303.json", stored_root)  # True or False
```

A DENY that left no trace is indistinguishable from an action that was never proposed. That's the gap this structure closes.

---

## Transport Is Irrelevant to the Boundary

The same evaluator handles ISO 8583 financial messages and HTTP POST requests identically. The transport type does not affect the decision. The Core pattern is:

```
build envelope → evaluate → record → execute only if ALLOW
```

This holds regardless of whether the side-effect is `socket.write()`, `http_client.post()`, or `channel.publish()`.

Transport independence is verified automatically: the test suite confirms that identical policy vectors produce identical outcomes across transport types.

---

## What This Is Not

- Not a firewall (operates on semantics, not packets)
- Not a rate limiter (operates on authorization, not volume)
- Not a content filter (operates on structured envelopes, not free text)
- Not an LLM guard (deterministic, not probabilistic)
- Not post-hoc logging (decision is pre-execution, record is pre-execution)

---

## The Open Question

This reference implementation demonstrates the pattern for transport-layer systems: financial messaging, HTTP APIs, TCP sockets.

The same boundary model applies to any system where an agent proposes an action that has real-world consequences — file writes, database mutations, external API calls, code execution.

The question worth discussing:

**What does it take for a system to qualify as an execution boundary — and what disqualifies it?**

The five properties above are a starting point. The definition should be stress-tested.

---

## Reference

Implementation: [execution-boundary-transport-profile](https://github.com/Nick-heo-eg/execution-boundary-transport-profile)

```bash
git clone https://github.com/Nick-heo-eg/execution-boundary-transport-profile
python3 -m pytest tests/ -v          # 28 tests
python3 examples/iso8583/demo.py     # ISO 8583 gate + Merkle export
python3 examples/http/demo.py        # HTTP gate + Merkle export
```

Architecture definition: [docs/03-architecture.md](docs/03-architecture.md)
