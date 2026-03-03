#!/usr/bin/env python3
"""
HTTP Transport Gate Demo
Execution Boundary Transport Profile v0.1
Core Spec: execution-boundary-core-spec commit 6ff7d64

Same Core. Different Transport. Identical Boundary Pattern.
No server. No network. Transport envelope simulation only.
"""

import hashlib
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from boundary_core.evaluator import TransportEnvelope, evaluate
from boundary_core.ledger import MerkleLedger


def build_envelope(method: str, path: str, body: dict, host: str) -> TransportEnvelope:
    action_id = str(uuid.uuid4())
    ts_now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    context_hash = hashlib.sha256(
        f"http:{method}:{path}:{body.get('amount')}:{ts_now}".encode()
    ).hexdigest()
    return TransportEnvelope(
        action_id=action_id,
        action_type="transport.http.post",
        resource=f"{host}{path}",
        parameters={
            "method": method,
            "path": path,
            "amount": body.get("amount"),
            "currency": body.get("currency"),
            "to": body.get("to"),
        },
        context_hash=context_hash,
        timestamp=ts_now,
        transport_type="http",
        destination=f"{host}{path}",
        payload_size=len(str(body)),
        protocol_version="HTTP/1.1",
        direction="outbound",
    )


def send_http(envelope: TransportEnvelope) -> None:
    p = envelope.parameters
    print(f"    [NETWORK] >>> {p['method']} {p['path']} "
          f"amount={p['amount']} {p['currency']} → {p['to']}")


HOST = "https://payments.example.com"

SCENARIOS = [
    {"label": "ALLOW — 10,000 KRW",  "body": {"amount": 10_000,  "currency": "KRW", "to": "acct_a"}},
    {"label": "ALLOW — 50,000 KRW",  "body": {"amount": 50_000,  "currency": "KRW", "to": "acct_b"}},
    {"label": "DENY  — 120,000 KRW", "body": {"amount": 120_000, "currency": "KRW", "to": "acct_c"}},
    {"label": "DENY  — 500,000 KRW", "body": {"amount": 500_000, "currency": "KRW", "to": "acct_d"}},
    {"label": "ALLOW — 90,000 KRW",  "body": {"amount": 90_000,  "currency": "KRW", "to": "acct_e"}},
]


def main():
    ledger = MerkleLedger()

    print("=" * 70)
    print("  HTTP Transport Gate Demo")
    print("  Execution Boundary Transport Profile v0.1")
    print("  Core Spec: execution-boundary-core-spec @ 6ff7d64")
    print("  Same Core. Different Transport. Identical Boundary Pattern.")
    print("=" * 70)

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"\n[{i}] {scenario['label']}")
        envelope = build_envelope("POST", "/transfer", scenario["body"], HOST)
        decision = evaluate(envelope)
        ledger.append(envelope, decision)

        # ── EXECUTION BOUNDARY ──────────────────────────────────────────────
        # send_http() is called only when decision.result == "ALLOW".
        if decision.allowed:
            send_http(envelope)
        else:
            print(f"    [GATE]    >>> send SUPPRESSED — {decision.reason_code}: {decision.reason}")
        # ────────────────────────────────────────────────────────────────────

        print(f"    result:     {decision.result}")
        print(f"    reason_code:{decision.reason_code}")
        print(f"    proof_hash: {decision.proof_hash[:24]}...")

    print("\n" + "=" * 70)
    print("  Ledger (append-only — DENY and ALLOW both recorded)")
    print("=" * 70)
    for entry in ledger.entries:
        d = entry["decision"]
        p = entry["envelope"]["parameters"]
        print(f"  {d['result']:5s}  {d['reason_code']:25s}  "
              f"amount={p['amount']:>7}  proof={d['proof_hash'][:16]}...")

    print(f"\n  Total:      {len(ledger.entries)} decisions — {ledger.allow_count()} ALLOW / {ledger.deny_count()} DENY")
    print(f"  Merkle root: {ledger.root_hash}")
    print(f"  Verified:    {ledger.verify(ledger.root_hash)}")
    print("  Execution is not default.\n")


if __name__ == "__main__":
    main()
