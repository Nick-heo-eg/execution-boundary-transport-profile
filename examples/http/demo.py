#!/usr/bin/env python3
"""
HTTP Transport Gate Demo
Execution Boundary Transport Profile v0.1
Core Spec: execution-boundary-core-spec commit 6ff7d64

Same Core. Different Transport. Identical Boundary Pattern.

No server. No network. Transport envelope simulation only.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# ── Core Spec types ───────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _proof_hash(decision_id: str, action_id: str, result: str, timestamp: str) -> str:
    raw = f"{decision_id}{action_id}{result}{timestamp}"
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class TransportEnvelope:
    """Core ActionEnvelope + Transport Profile extension fields."""
    action_id: str
    action_type: str
    resource: str
    parameters: dict
    context_hash: str
    timestamp: str
    # Transport profile extension
    transport_type: str
    destination: str
    payload_size: Optional[int]
    protocol_version: Optional[str]
    direction: str

    @staticmethod
    def from_http(method: str, path: str, body: dict, host: str) -> "TransportEnvelope":
        action_id = str(uuid.uuid4())
        timestamp = _now_iso()
        context_hash = hashlib.sha256(
            f"http:{method}:{path}:{body.get('amount')}:{timestamp}".encode()
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
            timestamp=timestamp,
            transport_type="http",
            destination=f"{host}{path}",
            payload_size=len(str(body)),
            protocol_version="HTTP/1.1",
            direction="outbound",
        )


@dataclass
class Decision:
    decision_id: str
    action_id: str
    result: str         # ALLOW | DENY
    reason_code: str
    authority_token: str
    proof_hash: str
    timestamp: str
    reason: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.result == "ALLOW"

    @staticmethod
    def _make(action_id, result, reason_code, reason=None) -> "Decision":
        decision_id = str(uuid.uuid4())
        timestamp = _now_iso()
        return Decision(
            decision_id=decision_id,
            action_id=action_id,
            result=result,
            reason_code=reason_code,
            authority_token="transport-gate/v0.1",
            proof_hash=_proof_hash(decision_id, action_id, result, timestamp),
            timestamp=timestamp,
            reason=reason,
        )

    @staticmethod
    def allow(action_id):
        return Decision._make(action_id, "ALLOW", "POLICY_ALLOW", "amount within limit")

    @staticmethod
    def deny(action_id, reason, code="POLICY_DENY"):
        return Decision._make(action_id, "DENY", code, reason)


# ── Evaluator (pure function, no side-effects) ────────────────────────────────

POLICY = {"max_amount": 100_000}

def evaluate(envelope: TransportEnvelope) -> Decision:
    """Deterministic. Side-effect free. Never executes the action."""
    amount = envelope.parameters.get("amount")

    if not isinstance(amount, (int, float)):
        return Decision.deny(envelope.action_id, "amount missing or invalid", "INVALID_AMOUNT")

    if amount > POLICY["max_amount"]:
        return Decision.deny(
            envelope.action_id,
            f"amount {amount} exceeds limit {POLICY['max_amount']}",
            "AMOUNT_EXCEEDS_LIMIT",
        )

    return Decision.allow(envelope.action_id)


# ── Ledger (append-only) ──────────────────────────────────────────────────────

_ledger: list = []
_ledger_chain: str = "0" * 64

def ledger_append(envelope: TransportEnvelope, decision: Decision) -> None:
    global _ledger_chain
    _ledger_chain = hashlib.sha256(
        (_ledger_chain + decision.proof_hash).encode()
    ).hexdigest()
    _ledger.append({
        "envelope": {
            "action_id": envelope.action_id,
            "action_type": envelope.action_type,
            "transport_type": envelope.transport_type,
            "destination": envelope.destination,
            "parameters": envelope.parameters,
        },
        "decision": {
            "decision_id": decision.decision_id,
            "action_id": decision.action_id,
            "result": decision.result,
            "reason_code": decision.reason_code,
            "authority_token": decision.authority_token,
            "proof_hash": decision.proof_hash,
            "reason": decision.reason,
        },
    })


# ── Mock HTTP sender (the side-effect) ───────────────────────────────────────

def send_http(envelope: TransportEnvelope) -> None:
    """Simulates http_client.post(). Side-effect."""
    p = envelope.parameters
    print(f"    [NETWORK] >>> {p['method']} {p['path']} "
          f"amount={p['amount']} {p['currency']} → {p['to']}")


# ── Gate (the boundary) ───────────────────────────────────────────────────────

HOST = "https://payments.example.com"

def gate_and_send(body: dict) -> Decision:
    """
    Execution Boundary flow:
      1. Build TransportEnvelope
      2. Evaluate (side-effect free)
      3. Ledger append (unconditional)
      4. send() only on ALLOW
    """
    envelope = TransportEnvelope.from_http("POST", "/transfer", body, HOST)
    decision = evaluate(envelope)
    ledger_append(envelope, decision)

    # ── EXECUTION BOUNDARY ──────────────────────────────────────────────────
    # send_http() is called only when decision.result == "ALLOW".
    # No other code path may trigger send_http().
    if decision.allowed:
        send_http(envelope)
    else:
        print(f"    [GATE]    >>> send SUPPRESSED — {decision.reason_code}: {decision.reason}")
    # ────────────────────────────────────────────────────────────────────────

    return decision


# ── Demo scenarios ────────────────────────────────────────────────────────────

SCENARIOS = [
    {"label": "ALLOW — 10,000 KRW",  "body": {"amount": 10_000,  "currency": "KRW", "to": "acct_a"}},
    {"label": "ALLOW — 50,000 KRW",  "body": {"amount": 50_000,  "currency": "KRW", "to": "acct_b"}},
    {"label": "DENY  — 120,000 KRW", "body": {"amount": 120_000, "currency": "KRW", "to": "acct_c"}},
    {"label": "DENY  — 500,000 KRW", "body": {"amount": 500_000, "currency": "KRW", "to": "acct_d"}},
    {"label": "ALLOW — 90,000 KRW",  "body": {"amount": 90_000,  "currency": "KRW", "to": "acct_e"}},
]


def main():
    print("=" * 70)
    print("  HTTP Transport Gate Demo")
    print("  Execution Boundary Transport Profile v0.1")
    print("  Core Spec: execution-boundary-core-spec @ 6ff7d64")
    print("  Same Core. Different Transport. Identical Boundary Pattern.")
    print("=" * 70)

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"\n[{i}] {scenario['label']}")
        decision = gate_and_send(scenario["body"])
        print(f"    result:     {decision.result}")
        print(f"    reason_code:{decision.reason_code}")
        print(f"    proof_hash: {decision.proof_hash[:24]}...")

    print("\n" + "=" * 70)
    print("  Ledger (append-only — DENY and ALLOW both recorded)")
    print("=" * 70)
    for entry in _ledger:
        d = entry["decision"]
        p = entry["envelope"]["parameters"]
        print(f"  {d['result']:5s}  {d['reason_code']:25s}  "
              f"amount={p['amount']:>7}  proof={d['proof_hash'][:16]}...")

    allow_count = sum(1 for e in _ledger if e["decision"]["result"] == "ALLOW")
    deny_count  = sum(1 for e in _ledger if e["decision"]["result"] == "DENY")
    print(f"\n  Total:      {len(_ledger)} decisions — {allow_count} ALLOW / {deny_count} DENY")
    print(f"  Ledger root hash: {_ledger_chain}")
    print("  Execution is not default.\n")


if __name__ == "__main__":
    main()
