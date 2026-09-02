import hashlib
from typing import List, Dict, Any


def verify_sha256(data: bytes, expected_hash: str) -> bool:
    """Verify SHA-256 hash of byte buffer."""
    actual = hashlib.sha256(data).hexdigest()
    return actual.lower() == expected_hash.lower()


def verify_merkle_leaf_proof(leaf_hash: str, proof: List[Dict[str, str]], expected_root: str) -> bool:
    """
    Verify Merkle audit proof path from leaf hash to expected Merkle Root.
    """
    if not proof:
        return leaf_hash.lower() == expected_root.lower()

    current = leaf_hash
    for step in proof:
        sibling = step.get("hash", "")
        position = step.get("position", "right")
        if position == "left":
            current = hashlib.sha256((sibling + current).encode('utf-8')).hexdigest()
        else:
            current = hashlib.sha256((current + sibling).encode('utf-8')).hexdigest()

    return current.lower() == expected_root.lower()
