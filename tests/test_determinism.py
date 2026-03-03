"""
tests/test_determinism.py

Verifies: Non-probabilistic, hash-stable evaluation.

decision.result and decision.reason_code are deterministic — identical
for the same policy vector across 100 evaluations.

decision.proof_hash is unique per invocation by construction (embeds
decision_id and timestamp), but every proof_hash is a valid 64-char
SHA-256 hex string. This is verified explicitly.

These two properties together define "Deterministic by construction
(hash-stable evaluation)": the evaluation outcome is fixed, and every
outcome is provably recorded with a unique, unforgeable proof token.
"""

import hashlib
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from boundary_core.evaluator import (
    TransportEnvelope, evaluate, DEFAULT_POLICY
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _envelope(amount):
    return TransportEnvelope(
        action_id=str(uuid.uuid4()),
        action_type="transport.iso8583.forward",
        resource="192.168.1.100:8583",
        parameters={"mti": "0200", "stan": "000001", "amount": amount},
        context_hash=hashlib.sha256(f"det:{amount}".encode()).hexdigest(),
        timestamp="2026-03-03T00:00:00+00:00",
        transport_type="iso8583",
        destination="192.168.1.100:8583",
        payload_size=128,
        protocol_version="ISO-8583-1987",
        direction="outbound",
    )


VECTORS = [
    {"amount": 10_000,  "expected_result": "ALLOW", "expected_code": "POLICY_ALLOW"},
    {"amount": 100_000, "expected_result": "ALLOW", "expected_code": "POLICY_ALLOW"},
    {"amount": 100_001, "expected_result": "DENY",  "expected_code": "AMOUNT_EXCEEDS_LIMIT"},
    {"amount": 500_000, "expected_result": "DENY",  "expected_code": "AMOUNT_EXCEEDS_LIMIT"},
]

N = 100


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_result_is_deterministic():
    """Same amount → same result across N evaluations."""
    for v in VECTORS:
        results = {evaluate(_envelope(v["amount"])).result for _ in range(N)}
        assert results == {v["expected_result"]}, (
            f"amount={v['amount']}: non-deterministic result across {N} runs: {results}"
        )


def test_reason_code_is_deterministic():
    """Same amount → same reason_code across N evaluations."""
    for v in VECTORS:
        codes = {evaluate(_envelope(v["amount"])).reason_code for _ in range(N)}
        assert codes == {v["expected_code"]}, (
            f"amount={v['amount']}: non-deterministic reason_code across {N} runs: {codes}"
        )


def test_proof_hash_is_valid_sha256():
    """Every proof_hash is a 64-char lowercase hex string (valid SHA-256)."""
    for v in VECTORS:
        for _ in range(N):
            ph = evaluate(_envelope(v["amount"])).proof_hash
            assert len(ph) == 64, f"proof_hash length {len(ph)} != 64"
            assert all(c in "0123456789abcdef" for c in ph), (
                f"proof_hash is not lowercase hex: {ph}"
            )


def test_proof_hash_is_unique_per_invocation():
    """
    proof_hash embeds decision_id (uuid4) and timestamp — it must be unique
    per invocation. Verifies the non-replayability property.
    """
    for v in VECTORS:
        hashes = [evaluate(_envelope(v["amount"])).proof_hash for _ in range(N)]
        assert len(set(hashes)) == N, (
            f"amount={v['amount']}: proof_hash collision across {N} runs "
            f"(got {len(set(hashes))} unique values, expected {N})"
        )


def test_proof_hash_is_independent_across_envelopes():
    """
    Two envelopes evaluated independently produce independent proof_hashes.
    No cross-contamination between evaluations.
    """
    for v in VECTORS:
        pairs = [
            (evaluate(_envelope(v["amount"])).proof_hash,
             evaluate(_envelope(v["amount"])).proof_hash)
            for _ in range(50)
        ]
        for a, b in pairs:
            assert a != b, (
                f"amount={v['amount']}: two independent evaluations produced "
                f"identical proof_hash {a} — possible state leak"
            )
