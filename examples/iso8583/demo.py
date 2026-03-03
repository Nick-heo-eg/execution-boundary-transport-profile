#!/usr/bin/env python3
"""
ISO 8583 Transport Gate Demo
Execution Boundary Transport Profile v0.1
Core Spec: execution-boundary-core-spec commit 6ff7d64

Structural proof: gate sits between fetchToProcess() and socket.write().
No real network. No real financial system.
"""

import hashlib
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from boundary_core.evaluator import TransportEnvelope, Decision, evaluate  # noqa: F401
from boundary_core.ledger import MerkleLedger, verify_from_file

POLICY = {
    "max_amount": 500_000,
    "allowed_mti": {"0200", "0400", "0800"},
    "blocked_processing_codes": {"200000"},
}


def evaluate_iso(envelope: TransportEnvelope) -> Decision:
    """ISO-specific evaluator: extends base evaluator with MTI and PC checks."""
    params = envelope.parameters

    mti = params.get("mti")
    if mti not in POLICY["allowed_mti"]:
        return Decision.deny(envelope.action_id, f"MTI not permitted: {mti}", "MTI_BLOCKED")

    pc = params.get("processing_code")
    if pc in POLICY["blocked_processing_codes"]:
        return Decision.deny(envelope.action_id, f"Processing code blocked: {pc}", "PC_BLOCKED")

    return evaluate(envelope, policy={"max_amount": POLICY["max_amount"]})


def build_envelope(msg: dict, destination: str) -> TransportEnvelope:
    action_id = str(uuid.uuid4())
    ts_now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    context_hash = hashlib.sha256(
        f"iso8583:{msg.get('mti')}:{msg.get('stan')}:{ts_now}".encode()
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
        timestamp=ts_now,
        transport_type="iso8583",
        destination=destination,
        payload_size=msg.get("_payload_size"),
        protocol_version="ISO-8583-1987",
        direction="outbound",
    )


def mock_send(envelope: TransportEnvelope) -> None:
    p = envelope.parameters
    print(f"    [NETWORK] >>> forwarded to {envelope.destination} "
          f"(MTI={p['mti']}, STAN={p['stan']}, amount={p['amount']})")


UPSTREAM = "192.168.1.100:8583"

SCENARIOS = [
    {"label": "ALLOW — purchase within limit",
     "msg": {"mti": "0200", "stan": "000001", "amount": 100_000, "processing_code": "000000", "_payload_size": 128}},
    {"label": "DENY  — amount exceeds limit",
     "msg": {"mti": "0200", "stan": "000002", "amount": 900_000, "processing_code": "000000", "_payload_size": 128}},
    {"label": "DENY  — refund blocked by policy",
     "msg": {"mti": "0200", "stan": "000003", "amount": 50_000, "processing_code": "200000", "_payload_size": 128}},
    {"label": "DENY  — MTI not permitted",
     "msg": {"mti": "0100", "stan": "000004", "amount": 10_000, "processing_code": "000000", "_payload_size": 128}},
    {"label": "ALLOW — reversal within limit",
     "msg": {"mti": "0400", "stan": "000005", "amount": 200_000, "processing_code": "000000", "_payload_size": 128}},
]


def main():
    ledger = MerkleLedger()

    print("=" * 70)
    print("  ISO 8583 Transport Gate Demo")
    print("  Execution Boundary Transport Profile v0.1")
    print("  Core Spec: execution-boundary-core-spec @ 6ff7d64")
    print("=" * 70)

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"\n[{i}] {scenario['label']}")
        envelope = build_envelope(scenario["msg"], UPSTREAM)
        decision = evaluate_iso(envelope)
        ledger.append(envelope, decision)

        # ── EXECUTION BOUNDARY ──────────────────────────────────────────────
        # mock_send() is called only when decision.result == "ALLOW".
        if decision.allowed:
            mock_send(envelope)
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
              f"action={p['mti']}/{p['stan']}  proof={d['proof_hash'][:16]}...")

    import datetime
    date_tag = datetime.date.today().strftime("%Y%m%d")
    export_path = f"ledger_{date_tag}_iso8583.json"
    root = ledger.export_canonical(export_path)

    print(f"\n  Total:      {len(ledger.entries)} decisions — {ledger.allow_count()} ALLOW / {ledger.deny_count()} DENY")
    print(f"  Merkle root: {root}")
    print(f"  Exported:    {export_path}")
    print(f"  Verified:    {verify_from_file(export_path, root)}")
    print("  Execution is not default.\n")


if __name__ == "__main__":
    main()
