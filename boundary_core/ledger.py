"""
boundary_core.ledger
Execution Boundary Transport Profile v0.1

Merkle-rooted append-only ledger.

Leaf nodes: SHA-256 of canonical JSON for each entry (envelope + decision).
Internal nodes: SHA-256 of left_hash + right_hash.
Root: deterministic for a fixed sequence of entries.

Canonical form: json.dumps(entry, sort_keys=True, separators=(",", ":"))
"""

import hashlib
import json
from typing import Any, Dict, List, Optional


# ── Merkle ────────────────────────────────────────────────────────────────────

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _merkle_root(leaves: List[str]) -> str:
    """
    Compute Merkle root from a list of leaf hashes.

    - Empty ledger: returns '0' * 64 (null root, consistent with no entries).
    - Single leaf: root == leaf hash.
    - Odd number of leaves: last leaf is duplicated (standard Bitcoin-style
      Merkle padding, avoids length-extension ambiguity).
    """
    if not leaves:
        return "0" * 64

    layer = list(leaves)
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [
            _sha256(layer[i] + layer[i + 1])
            for i in range(0, len(layer), 2)
        ]
    return layer[0]


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _leaf_hash(entry: Dict) -> str:
    return _sha256(_canonical(entry))


# ── MerkleLedger ──────────────────────────────────────────────────────────────

class MerkleLedger:
    """
    Append-only decision ledger with Merkle root.

    append(envelope, decision) → records entry, invalidates cached root.
    root_hash                  → recomputes and caches Merkle root.
    verify(expected_root)      → bool, tamper-evident check.
    leaf_hashes                → list of per-entry leaf hashes.
    """

    def __init__(self) -> None:
        self._entries: List[Dict] = []
        self._leaf_hashes: List[str] = []
        self._root_cache: Optional[str] = None

    def append(self, envelope: Any, decision: Any) -> None:
        entry = {
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
        }
        self._entries.append(entry)
        self._leaf_hashes.append(_leaf_hash(entry))
        self._root_cache = None  # invalidate

    @property
    def entries(self) -> List[Dict]:
        return list(self._entries)

    @property
    def leaf_hashes(self) -> List[str]:
        return list(self._leaf_hashes)

    @property
    def root_hash(self) -> str:
        if self._root_cache is None:
            self._root_cache = _merkle_root(self._leaf_hashes)
        return self._root_cache

    def verify(self, expected_root: str) -> bool:
        """Recompute root from entries and compare. Tamper-evident."""
        recomputed = _merkle_root([_leaf_hash(e) for e in self._entries])
        return recomputed == expected_root

    def allow_count(self) -> int:
        return sum(1 for e in self._entries if e["decision"]["result"] == "ALLOW")

    def deny_count(self) -> int:
        return sum(1 for e in self._entries if e["decision"]["result"] == "DENY")
