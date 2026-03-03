"""
tests/test_merkle_ledger.py

Verifies: Tamper-evident Merkle-rooted ledger.

Properties tested:
  - Determinism: same sequence of entries → same root
  - Tamper detection: any mutation → root changes
  - Append sensitivity: adding an entry → root changes
  - Order sensitivity: reordered entries → root changes
  - Verify round-trip: verify(root_hash) == True
  - Empty root: empty ledger → '0' * 64
  - Single entry: root == leaf hash
"""

import hashlib
import uuid
import copy
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from boundary_core.evaluator import TransportEnvelope, evaluate
from boundary_core.ledger import MerkleLedger, _merkle_root, _leaf_hash


# ── Helpers ───────────────────────────────────────────────────────────────────

def _envelope(amount: int, transport: str = "iso8583") -> TransportEnvelope:
    if transport == "iso8583":
        return TransportEnvelope(
            action_id=str(uuid.uuid4()),
            action_type="transport.iso8583.forward",
            resource="192.168.1.100:8583",
            parameters={"mti": "0200", "stan": "000001", "amount": amount},
            context_hash=hashlib.sha256(f"mkl:{amount}".encode()).hexdigest(),
            timestamp="2026-03-03T00:00:00+00:00",
            transport_type="iso8583",
            destination="192.168.1.100:8583",
            payload_size=128,
            protocol_version="ISO-8583-1987",
            direction="outbound",
        )
    return TransportEnvelope(
        action_id=str(uuid.uuid4()),
        action_type="transport.http.post",
        resource="https://payments.example.com/transfer",
        parameters={"method": "POST", "path": "/transfer", "amount": amount},
        context_hash=hashlib.sha256(f"mkl-http:{amount}".encode()).hexdigest(),
        timestamp="2026-03-03T00:00:00+00:00",
        transport_type="http",
        destination="https://payments.example.com/transfer",
        payload_size=64,
        protocol_version="HTTP/1.1",
        direction="outbound",
    )


AMOUNTS = [10_000, 50_000, 100_001, 500_000]


def _filled_ledger() -> MerkleLedger:
    ledger = MerkleLedger()
    for amt in AMOUNTS:
        env = _envelope(amt)
        dec = evaluate(env)
        ledger.append(env, dec)
    return ledger


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_empty_ledger_root():
    """Empty ledger root is '0' * 64."""
    ledger = MerkleLedger()
    assert ledger.root_hash == "0" * 64


def test_single_entry_root_equals_leaf():
    """Single-entry ledger: root == leaf hash of that entry."""
    ledger = MerkleLedger()
    env = _envelope(10_000)
    dec = evaluate(env)
    ledger.append(env, dec)
    assert len(ledger.leaf_hashes) == 1
    assert ledger.root_hash == ledger.leaf_hashes[0]


def test_root_is_deterministic():
    """
    Two ledgers with identical entries produce the same root.
    Build entries once, append the same frozen entry objects to both ledgers.
    """
    from boundary_core.evaluator import Decision

    ledger_a = MerkleLedger()
    ledger_b = MerkleLedger()

    # Build envelope + decision pairs once; reuse for both ledgers.
    pairs = []
    for amt in AMOUNTS:
        action_id = str(uuid.uuid4())
        ts = "2026-03-03T00:00:00+00:00"
        env = TransportEnvelope(
            action_id=action_id,
            action_type="transport.iso8583.forward",
            resource="192.168.1.100:8583",
            parameters={"mti": "0200", "stan": "000001", "amount": amt},
            context_hash=hashlib.sha256(f"det:{amt}".encode()).hexdigest(),
            timestamp=ts,
            transport_type="iso8583",
            destination="192.168.1.100:8583",
            payload_size=128,
            protocol_version="ISO-8583-1987",
            direction="outbound",
        )
        dec = evaluate(env)
        # Pin all fields so the same Decision object is used for both ledgers.
        pinned = Decision(
            decision_id=dec.decision_id,
            action_id=dec.action_id,
            result=dec.result,
            reason_code=dec.reason_code,
            authority_token=dec.authority_token,
            proof_hash=dec.proof_hash,
            timestamp=dec.timestamp,
            reason=dec.reason,
        )
        pairs.append((env, pinned))

    for env, dec in pairs:
        ledger_a.append(env, dec)
    for env, dec in pairs:
        ledger_b.append(env, dec)

    assert ledger_a.root_hash == ledger_b.root_hash


def test_tamper_detection_mutate_result():
    """Mutating a decision result changes the root."""
    ledger = _filled_ledger()
    original_root = ledger.root_hash

    tampered = copy.deepcopy(ledger._entries)
    # Find the first DENY entry and flip it to ALLOW
    for entry in tampered:
        if entry["decision"]["result"] == "DENY":
            entry["decision"]["result"] = "ALLOW"
            break

    tampered_root = _merkle_root([_leaf_hash(e) for e in tampered])
    assert tampered_root != original_root


def test_tamper_detection_mutate_amount():
    """Mutating an envelope parameter changes the root."""
    ledger = _filled_ledger()
    original_root = ledger.root_hash

    tampered = copy.deepcopy(ledger._entries)
    tampered[1]["envelope"]["parameters"]["amount"] = 1  # change amount

    tampered_root = _merkle_root([_leaf_hash(e) for e in tampered])
    assert tampered_root != original_root


def test_append_changes_root():
    """Adding an entry changes the root."""
    ledger = MerkleLedger()
    env = _envelope(10_000)
    dec = evaluate(env)
    ledger.append(env, dec)
    root_before = ledger.root_hash

    env2 = _envelope(50_000)
    dec2 = evaluate(env2)
    ledger.append(env2, dec2)
    root_after = ledger.root_hash

    assert root_before != root_after


def test_order_sensitivity():
    """Different append order → different root."""
    amounts = [10_000, 50_000]

    envs_decs = []
    for amt in amounts:
        env = _envelope(amt)
        dec = evaluate(env)
        envs_decs.append((env, dec))

    ledger_ab = MerkleLedger()
    ledger_ab.append(*envs_decs[0])
    ledger_ab.append(*envs_decs[1])

    ledger_ba = MerkleLedger()
    ledger_ba.append(*envs_decs[1])
    ledger_ba.append(*envs_decs[0])

    assert ledger_ab.root_hash != ledger_ba.root_hash


def test_verify_round_trip():
    """verify(root_hash) returns True; verify(wrong) returns False."""
    ledger = _filled_ledger()
    assert ledger.verify(ledger.root_hash) is True
    assert ledger.verify("0" * 64) is False


def test_deny_and_allow_both_recorded():
    """DENY and ALLOW entries are both present in the ledger."""
    ledger = _filled_ledger()
    assert ledger.allow_count() > 0
    assert ledger.deny_count() > 0
    assert ledger.allow_count() + ledger.deny_count() == len(AMOUNTS)
