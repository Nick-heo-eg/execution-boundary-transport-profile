"""
tests/test_canonical_export.py

Verifies: External verifiability via canonical ledger export.

Properties tested:
  - export produces valid JSON with merkle_root, entry_count, entries
  - verify_from_file(path, root) == True for unmodified export
  - verify_from_file(path, wrong_root) == False
  - file mutation (result flip) → verify_from_file returns False
  - file mutation (amount change) → verify_from_file returns False
  - export is idempotent — same root on re-export
  - exported JSON is UTF-8 canonical (sort_keys, no spaces)
"""

import hashlib
import json
import os
import tempfile
import uuid
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from boundary_core.evaluator import TransportEnvelope, evaluate
from boundary_core.ledger import MerkleLedger, verify_from_file


# ── Helpers ───────────────────────────────────────────────────────────────────

def _envelope(amount: int) -> TransportEnvelope:
    return TransportEnvelope(
        action_id=str(uuid.uuid4()),
        action_type="transport.iso8583.forward",
        resource="192.168.1.100:8583",
        parameters={"mti": "0200", "stan": "000001", "amount": amount},
        context_hash=hashlib.sha256(f"exp:{amount}".encode()).hexdigest(),
        timestamp="2026-03-03T00:00:00+00:00",
        transport_type="iso8583",
        destination="192.168.1.100:8583",
        payload_size=128,
        protocol_version="ISO-8583-1987",
        direction="outbound",
    )


AMOUNTS = [10_000, 50_000, 100_001, 500_000]


def _filled_ledger() -> MerkleLedger:
    ledger = MerkleLedger()
    for amt in AMOUNTS:
        ledger.append(_envelope(amt), evaluate(_envelope(amt)))
    return ledger


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_export_structure():
    """Exported JSON contains merkle_root, entry_count, entries."""
    ledger = _filled_ledger()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        ledger.export_canonical(path)
        with open(path, encoding="utf-8") as f:
            snapshot = json.loads(f.read())
        assert "merkle_root" in snapshot
        assert "entry_count" in snapshot
        assert "entries" in snapshot
        assert snapshot["entry_count"] == len(AMOUNTS)
        assert len(snapshot["entries"]) == len(AMOUNTS)
        assert snapshot["merkle_root"] == ledger.root_hash
    finally:
        os.unlink(path)


def test_verify_from_file_pass():
    """verify_from_file returns True for unmodified export."""
    ledger = _filled_ledger()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        root = ledger.export_canonical(path)
        assert verify_from_file(path, root) is True
    finally:
        os.unlink(path)


def test_verify_from_file_wrong_root():
    """verify_from_file returns False for wrong expected_root."""
    ledger = _filled_ledger()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        ledger.export_canonical(path)
        assert verify_from_file(path, "0" * 64) is False
    finally:
        os.unlink(path)


def test_verify_fails_after_result_mutation():
    """Flipping a decision result in the exported file breaks verification."""
    ledger = _filled_ledger()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = f.name
    try:
        root = ledger.export_canonical(path)

        with open(path, encoding="utf-8") as f:
            snapshot = json.loads(f.read())

        # Flip the first DENY → ALLOW
        for entry in snapshot["entries"]:
            if entry["decision"]["result"] == "DENY":
                entry["decision"]["result"] = "ALLOW"
                break

        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f)

        assert verify_from_file(path, root) is False
    finally:
        os.unlink(path)


def test_verify_fails_after_amount_mutation():
    """Changing an envelope amount in the exported file breaks verification."""
    ledger = _filled_ledger()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = f.name
    try:
        root = ledger.export_canonical(path)

        with open(path, encoding="utf-8") as f:
            snapshot = json.loads(f.read())

        snapshot["entries"][0]["envelope"]["parameters"]["amount"] = 1

        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f)

        assert verify_from_file(path, root) is False
    finally:
        os.unlink(path)


def test_export_is_idempotent():
    """Exporting the same ledger twice produces the same root and file content."""
    ledger = _filled_ledger()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path_a = f.name
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path_b = f.name
    try:
        root_a = ledger.export_canonical(path_a)
        root_b = ledger.export_canonical(path_b)
        assert root_a == root_b

        with open(path_a, encoding="utf-8") as f:
            content_a = f.read()
        with open(path_b, encoding="utf-8") as f:
            content_b = f.read()
        assert content_a == content_b
    finally:
        os.unlink(path_a)
        os.unlink(path_b)


def test_export_is_canonical_json():
    """
    Exported JSON uses sort_keys and no extra whitespace.
    Canonical form is stable and transport-safe.
    """
    ledger = _filled_ledger()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        ledger.export_canonical(path)
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        # No pretty-print whitespace — separators=(",",":")
        assert "\n" not in raw
        assert ": " not in raw
        assert ", " not in raw
        # Valid JSON
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)
    finally:
        os.unlink(path)
