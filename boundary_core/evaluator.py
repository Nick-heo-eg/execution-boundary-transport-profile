"""
boundary_core.evaluator
Execution Boundary Transport Profile v0.1
Core Spec: execution-boundary-core-spec commit 6ff7d64

Transport-agnostic evaluator.
Pure function — deterministic, side-effect free.
Called identically by ISO 8583 and HTTP transport paths.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ── Shared types ──────────────────────────────────────────────────────────────

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
    parameters: Dict[str, Any]
    context_hash: str
    timestamp: str
    transport_type: str
    destination: str
    payload_size: Optional[int]
    protocol_version: Optional[str]
    direction: str


@dataclass
class Decision:
    """Conforms to Execution Boundary Core Spec v0.1 Decision schema."""
    decision_id: str
    action_id: str
    result: str             # ALLOW | DENY | HOLD
    reason_code: str
    authority_token: str
    proof_hash: str
    timestamp: str
    reason: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.result == "ALLOW"

    @staticmethod
    def _make(action_id: str, result: str, reason_code: str,
              reason: Optional[str] = None) -> "Decision":
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
    def allow(action_id: str) -> "Decision":
        return Decision._make(action_id, "ALLOW", "POLICY_ALLOW", "amount within limit")

    @staticmethod
    def deny(action_id: str, reason: str, code: str = "POLICY_DENY") -> "Decision":
        return Decision._make(action_id, "DENY", code, reason)


# ── Transport-agnostic policy ─────────────────────────────────────────────────

DEFAULT_POLICY = {"max_amount": 100_000}


def evaluate(envelope: TransportEnvelope, policy: Optional[Dict] = None) -> Decision:
    """
    Deterministic. Side-effect free. Never executes the action.

    Extracts `amount` from envelope.parameters regardless of transport type.
    Same function called by ISO 8583 and HTTP paths.
    """
    if policy is None:
        policy = DEFAULT_POLICY

    amount = envelope.parameters.get("amount")

    if not isinstance(amount, (int, float)):
        return Decision.deny(envelope.action_id, "amount missing or invalid", "INVALID_AMOUNT")

    max_amount = policy.get("max_amount", 0)
    if amount > max_amount:
        return Decision.deny(
            envelope.action_id,
            f"amount {amount} exceeds limit {max_amount}",
            "AMOUNT_EXCEEDS_LIMIT",
        )

    return Decision.allow(envelope.action_id)


# ── Ledger ────────────────────────────────────────────────────────────────────

class Ledger:
    """Append-only decision record. Records ALLOW and DENY unconditionally."""

    def __init__(self) -> None:
        self._entries: list = []
        self._chain: str = "0" * 64

    def append(self, envelope: TransportEnvelope, decision: Decision) -> None:
        self._chain = hashlib.sha256(
            (self._chain + decision.proof_hash).encode()
        ).hexdigest()
        self._entries.append({
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

    @property
    def entries(self) -> list:
        return list(self._entries)

    @property
    def root_hash(self) -> str:
        return self._chain

    def allow_count(self) -> int:
        return sum(1 for e in self._entries if e["decision"]["result"] == "ALLOW")

    def deny_count(self) -> int:
        return sum(1 for e in self._entries if e["decision"]["result"] == "DENY")
