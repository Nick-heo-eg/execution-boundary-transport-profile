"""
tests/test_pattern_invariant.py

Verifies: Same Core. Different Transport. Identical Boundary Pattern.

The evaluator produces identical results for ISO 8583 and HTTP envelopes
given the same policy vector. Transport type does not affect decision outcome.
"""

import hashlib
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from boundary_core.evaluator import (
    TransportEnvelope, Decision, Ledger, evaluate, DEFAULT_POLICY
)


# ── Envelope builders ─────────────────────────────────────────────────────────

def iso_envelope(amount: int) -> TransportEnvelope:
    action_id = str(uuid.uuid4())
    ts = "2026-03-03T00:00:00+00:00"
    return TransportEnvelope(
        action_id=action_id,
        action_type="transport.iso8583.forward",
        resource="192.168.1.100:8583",
        parameters={"mti": "0200", "stan": "000001", "amount": amount, "processing_code": "000000"},
        context_hash=hashlib.sha256(f"iso:{amount}".encode()).hexdigest(),
        timestamp=ts,
        transport_type="iso8583",
        destination="192.168.1.100:8583",
        payload_size=128,
        protocol_version="ISO-8583-1987",
        direction="outbound",
    )


def http_envelope(amount: int) -> TransportEnvelope:
    action_id = str(uuid.uuid4())
    ts = "2026-03-03T00:00:00+00:00"
    return TransportEnvelope(
        action_id=action_id,
        action_type="transport.http.post",
        resource="https://payments.example.com/transfer",
        parameters={"method": "POST", "path": "/transfer", "amount": amount, "currency": "KRW"},
        context_hash=hashlib.sha256(f"http:{amount}".encode()).hexdigest(),
        timestamp=ts,
        transport_type="http",
        destination="https://payments.example.com/transfer",
        payload_size=64,
        protocol_version="HTTP/1.1",
        direction="outbound",
    )


# ── Common policy vectors ─────────────────────────────────────────────────────

CASES = [
    {"amount": 10_000,   "expected": "ALLOW"},
    {"amount": 50_000,   "expected": "ALLOW"},
    {"amount": 100_000,  "expected": "ALLOW"},  # boundary — exactly at limit
    {"amount": 100_001,  "expected": "DENY"},   # boundary + 1
    {"amount": 500_000,  "expected": "DENY"},
]


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_iso_results():
    """ISO 8583 envelope produces expected result for each policy vector."""
    for case in CASES:
        envelope = iso_envelope(case["amount"])
        decision = evaluate(envelope)
        assert decision.result == case["expected"], (
            f"ISO amount={case['amount']}: expected {case['expected']}, got {decision.result}"
        )


def test_http_results():
    """HTTP envelope produces expected result for each policy vector."""
    for case in CASES:
        envelope = http_envelope(case["amount"])
        decision = evaluate(envelope)
        assert decision.result == case["expected"], (
            f"HTTP amount={case['amount']}: expected {case['expected']}, got {decision.result}"
        )


def test_pattern_invariant():
    """
    ISO and HTTP envelopes with identical amount produce identical result.
    Transport type does not affect decision outcome.
    """
    for case in CASES:
        iso_decision = evaluate(iso_envelope(case["amount"]))
        http_decision = evaluate(http_envelope(case["amount"]))
        assert iso_decision.result == http_decision.result, (
            f"amount={case['amount']}: ISO={iso_decision.result}, HTTP={http_decision.result}"
        )
        assert iso_decision.reason_code == http_decision.reason_code, (
            f"amount={case['amount']}: reason_code mismatch"
        )


def test_fail_closed():
    """Missing amount produces DENY regardless of transport type."""
    for build_envelope in [iso_envelope, http_envelope]:
        envelope = build_envelope(0)
        envelope.parameters.pop("amount", None)
        # rebuild without amount
        no_amount = TransportEnvelope(
            action_id=str(uuid.uuid4()),
            action_type=envelope.action_type,
            resource=envelope.resource,
            parameters={},
            context_hash=envelope.context_hash,
            timestamp=envelope.timestamp,
            transport_type=envelope.transport_type,
            destination=envelope.destination,
            payload_size=None,
            protocol_version=envelope.protocol_version,
            direction=envelope.direction,
        )
        decision = evaluate(no_amount)
        assert decision.result == "DENY"
        assert decision.reason_code == "INVALID_AMOUNT"


def test_decision_has_proof_hash():
    """Every decision — ALLOW or DENY — contains a non-empty proof_hash."""
    for case in CASES:
        for envelope in [iso_envelope(case["amount"]), http_envelope(case["amount"])]:
            decision = evaluate(envelope)
            assert decision.proof_hash
            assert len(decision.proof_hash) == 64  # SHA-256 hex


def test_deny_recorded_in_ledger():
    """DENY decisions are recorded in the ledger (negative proof requirement)."""
    ledger = Ledger()
    for case in CASES:
        envelope = iso_envelope(case["amount"])
        decision = evaluate(envelope)
        ledger.append(envelope, decision)

    assert ledger.deny_count() > 0, "Ledger must contain DENY entries"
    assert ledger.allow_count() > 0, "Ledger must contain ALLOW entries"
    assert len(ledger.entries) == len(CASES)
    assert ledger.root_hash != "0" * 64


def test_determinism():
    """Same amount produces same result across 50 evaluations."""
    for amount in [10_000, 500_000]:
        results = set()
        for _ in range(50):
            d = evaluate(iso_envelope(amount))
            results.add(d.result)
        assert len(results) == 1, f"Non-deterministic result for amount={amount}: {results}"
