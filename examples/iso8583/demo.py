#!/usr/bin/env python3
"""
ISO 8583 Transport Gate Demo
Execution Boundary Transport Profile v0.1
Core Spec: execution-boundary-core-spec commit d3e239b

Demonstrates:
  - TransportActionEnvelope construction from ISO 8583 message
  - Evaluator (side-effect free, deterministic)
  - Decision with proof_hash (ALLOW | DENY)
  - Ledger append (unconditional — DENY recorded)
  - send() suppression on DENY

No real network. No real financial system.
Structural proof only.
"""

import hashlib
import json
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


# ── Core Spec types (inline — no external dependency) ────────────────────────

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
    def from_iso8583(msg: dict, destination: str) -> "TransportEnvelope":
        action_id = str(uuid.uuid4())
        timestamp = _now_iso()
        context_hash = hashlib.sha256(
            f"iso8583:{msg.get('mti')}:{msg.get('stan')}:{timestamp}".encode()
        ).hexdigest()
        return TransportEnvelope(
            action_id=action_id,
            action_type="transport.iso8583.forward",
            resource=destination,
            parameters={
                "mti": msg.get("mti"),
                "stan": msg.get("stan"),
                "amount": msg.get("amount"),
                "processing_code": msg.get("processing_code"),
            },
            context_hash=context_hash,
            timestamp=timestamp,
            transport_type="iso8583",
            destination=destination,
            payload_size=msg.get("_payload_size"),
            protocol_version="ISO-8583-1987",
            direction="outbound",
        )


@dataclass
class Decision:
    decision_id: str
    action_id: str
    result: str         # ALLOW | DENY | HOLD
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
    def allow(action_id): return Decision._make(action_id, "ALLOW", "POLICY_ALLOW")

    @staticmethod
    def deny(action_id, reason, code="POLICY_DENY"):
        return Decision._make(action_id, "DENY", code, reason)


# ── Evaluator (pure function, no side-effects) ────────────────────────────────

POLICY = {
    "max_amount": 500_000,          # deny if amount > 500,000
    "allowed_mti": {"0200", "0400", "0800"},
    "blocked_processing_codes": {"200000"},  # refund blocked in this policy
}

def evaluate(envelope: TransportEnvelope) -> Decision:
    """Deterministic. Side-effect free. Never executes the action."""
    params = envelope.parameters

    mti = params.get("mti")
    if mti not in POLICY["allowed_mti"]:
        return Decision.deny(envelope.action_id, f"MTI not permitted: {mti}", "MTI_BLOCKED")

    pc = params.get("processing_code")
    if pc in POLICY["blocked_processing_codes"]:
        return Decision.deny(envelope.action_id, f"Processing code blocked: {pc}", "PC_BLOCKED")

    amount = params.get("amount")
    if amount is not None and amount > POLICY["max_amount"]:
        return Decision.deny(
            envelope.action_id,
            f"Amount {amount} exceeds limit {POLICY['max_amount']}",
            "AMOUNT_EXCEEDS_LIMIT",
        )

    return Decision.allow(envelope.action_id)


# ── Ledger (append-only, records DENY and ALLOW) ──────────────────────────────

_ledger: list = []
_ledger_chain: str = "0" * 64  # genesis hash

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


# ── Mock network sender (the side-effect) ────────────────────────────────────

def mock_send(envelope: TransportEnvelope) -> None:
    """Simulates socket.write() / network forward. Side-effect."""
    print(f"    [NETWORK] >>> forwarded to {envelope.destination} "
          f"(MTI={envelope.parameters['mti']}, "
          f"STAN={envelope.parameters['stan']}, "
          f"amount={envelope.parameters['amount']})")


# ── Gate (the boundary) ───────────────────────────────────────────────────────

def gate_and_send(msg: dict, destination: str) -> Decision:
    """
    Execution Boundary flow:
      1. Build TransportEnvelope
      2. Evaluate (side-effect free)
      3. Ledger append (unconditional)
      4. send() only on ALLOW
    """
    envelope = TransportEnvelope.from_iso8583(msg, destination)
    decision = evaluate(envelope)
    ledger_append(envelope, decision)

    # ── EXECUTION BOUNDARY ──────────────────────────────────────────────────
    # send() is called only when decision.result == "ALLOW".
    # No other code path may trigger mock_send().
    if decision.allowed:
        mock_send(envelope)
    else:
        print(f"    [GATE]    >>> send SUPPRESSED — {decision.reason_code}: {decision.reason}")
    # ────────────────────────────────────────────────────────────────────────

    return decision


# ── Demo scenarios ────────────────────────────────────────────────────────────

UPSTREAM = "192.168.1.100:8583"

SCENARIOS = [
    {
        "label": "ALLOW — purchase within limit",
        "msg": {"mti": "0200", "stan": "000001", "amount": 100_000, "processing_code": "000000", "_payload_size": 128},
    },
    {
        "label": "DENY — amount exceeds limit",
        "msg": {"mti": "0200", "stan": "000002", "amount": 900_000, "processing_code": "000000", "_payload_size": 128},
    },
    {
        "label": "DENY — refund blocked by policy",
        "msg": {"mti": "0200", "stan": "000003", "amount": 50_000, "processing_code": "200000", "_payload_size": 128},
    },
    {
        "label": "DENY — MTI not permitted",
        "msg": {"mti": "0100", "stan": "000004", "amount": 10_000, "processing_code": "000000", "_payload_size": 128},
    },
    {
        "label": "ALLOW — reversal within limit",
        "msg": {"mti": "0400", "stan": "000005", "amount": 200_000, "processing_code": "000000", "_payload_size": 128},
    },
]


def main():
    print("=" * 70)
    print("  ISO 8583 Transport Gate Demo")
    print("  Execution Boundary Transport Profile v0.1")
    print("  Core Spec: execution-boundary-core-spec @ d3e239b")
    print("=" * 70)

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"\n[{i}] {scenario['label']}")
        decision = gate_and_send(scenario["msg"], UPSTREAM)
        print(f"    result:     {decision.result}")
        print(f"    reason_code:{decision.reason_code}")
        print(f"    proof_hash: {decision.proof_hash[:24]}...")

    print("\n" + "=" * 70)
    print("  Ledger (append-only — DENY and ALLOW both recorded)")
    print("=" * 70)
    for entry in _ledger:
        d = entry["decision"]
        print(f"  {d['result']:5s}  {d['reason_code']:25s}  "
              f"action={entry['envelope']['parameters']['mti']}/"
              f"{entry['envelope']['parameters']['stan']}  "
              f"proof={d['proof_hash'][:16]}...")

    allow_count = sum(1 for e in _ledger if e["decision"]["result"] == "ALLOW")
    deny_count  = sum(1 for e in _ledger if e["decision"]["result"] == "DENY")
    print(f"\n  Total:      {len(_ledger)} decisions — {allow_count} ALLOW / {deny_count} DENY")
    print(f"  Ledger root hash: {_ledger_chain}")
    print("  Execution is not default.\n")


if __name__ == "__main__":
    main()
