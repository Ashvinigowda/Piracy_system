import os
import json
import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple

# Folder where encrypted shards are stored
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SHARDS_FOLDER = os.path.join(BACKEND_DIR, "encrypted_shards")
MANIFEST_FILE = os.path.join(BACKEND_DIR, "manifest.json")
SIGNING_KEY_FILE = os.path.join(BACKEND_DIR, "producer_signing.key")

THEATRE_ID = "THEATRE_001"
PLAYBACK_HOURS = 3


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_merkle_tree(leaf_hashes: List[str]) -> Tuple[str, List[List[str]], Dict[str, List[Dict[str, str]]]]:
    """
    Constructs a Merkle Tree from list of leaf SHA-256 hashes.
    Returns:
      (root_hash, tree_levels, audit_proofs_dict)
    """
    if not leaf_hashes:
        empty_root = hashlib.sha256(b"").hexdigest()
        return empty_root, [[]], {}

    current_level = list(leaf_hashes)
    tree_levels = [current_level]

    # Build levels up to root
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            # Duplicate odd leaf
            right = current_level[i + 1] if (i + 1 < len(current_level)) else left
            parent_hash = hashlib.sha256((left + right).encode('utf-8')).hexdigest()
            next_level.append(parent_hash)
        current_level = next_level
        tree_levels.append(current_level)

    root_hash = tree_levels[-1][0]

    # Build audit proofs for each leaf
    proofs = {}
    for idx, leaf in enumerate(leaf_hashes):
        proof = []
        cur_idx = idx
        for level in tree_levels[:-1]:
            is_right = (cur_idx % 2 == 1)
            sibling_idx = cur_idx - 1 if is_right else cur_idx + 1
            if sibling_idx < len(level):
                sibling_hash = level[sibling_idx]
            else:
                sibling_hash = level[cur_idx]  # duplicate self if odd

            proof.append({
                "position": "left" if is_right else "right",
                "hash": sibling_hash
            })
            cur_idx = cur_idx // 2
        proofs[leaf] = proof

    return root_hash, tree_levels, proofs


def verify_merkle_proof(leaf_hash: str, proof: List[Dict[str, str]], expected_root: str) -> bool:
    """Verifies an individual shard leaf hash against the Merkle root using its proof path."""
    current = leaf_hash
    for step in proof:
        sibling = step["hash"]
        if step["position"] == "left":
            current = hashlib.sha256((sibling + current).encode('utf-8')).hexdigest()
        else:
            current = hashlib.sha256((current + sibling).encode('utf-8')).hexdigest()
    return current == expected_root


def get_or_create_producer_signing_key() -> str:
    """Load or generate a 256-bit HMAC producer signature key."""
    if os.path.exists(SIGNING_KEY_FILE):
        with open(SIGNING_KEY_FILE, "r") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(SIGNING_KEY_FILE, "w") as f:
        f.write(key)
    return key


def sign_manifest(root_hash: str, theatre_id: str, created_at: str) -> str:
    """Generate cryptographic signature for the manifest root & metadata."""
    key = get_or_create_producer_signing_key()
    payload = f"CS_MANIFEST:{root_hash}:{theatre_id}:{created_at}".encode('utf-8')
    return hmac.new(key.encode('utf-8'), payload, hashlib.sha256).hexdigest()


def generate_manifest(
    shards_dir: str = SHARDS_FOLDER,
    manifest_path: str = MANIFEST_FILE,
    theatre_id: str = THEATRE_ID,
    routing_map: Dict[str, Any] = None,
    playback_hours: int = PLAYBACK_HOURS
) -> Dict[str, Any]:
    """
    Generate a cryptographic Merkle Manifest with routing and integrity proofs.
    """
    if not os.path.exists(shards_dir):
        print(f" Folder '{shards_dir}' does not exist!")
        return {}

    shard_files = sorted([
        f for f in os.listdir(shards_dir)
        if os.path.isfile(os.path.join(shards_dir, f)) and f.endswith(".enc")
    ])

    if not shard_files:
        print(f" No encrypted shards found in '{shards_dir}'!")
        return {}

    now = datetime.now(timezone.utc)
    playback_start = now
    playback_end = playback_start + timedelta(hours=playback_hours)

    from concurrent.futures import ThreadPoolExecutor

    def _hash_shard(shard_file):
        shard_path = os.path.join(shards_dir, shard_file)
        shard_hash = sha256_file(shard_path)
        file_size = os.path.getsize(shard_path)
        route = routing_map.get(shard_file, {}) if routing_map else {}
        return {
            "id": shard_file,
            "sha256": shard_hash,
            "size_bytes": file_size,
            "encryption_algo": "AES-256-GCM",
            "routing": route
        }

    workers = min(len(shard_files), 16)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        shards_meta = list(pool.map(_hash_shard, shard_files))

    leaf_hashes = [s["sha256"] for s in shards_meta]

    # Build Merkle Tree
    root_hash, tree_levels, proofs = build_merkle_tree(leaf_hashes)

    # Attach Merkle proof to each shard
    for s in shards_meta:
        s["merkle_proof"] = proofs.get(s["sha256"], [])

    created_iso = now.isoformat()
    signature = sign_manifest(root_hash, theatre_id, created_iso)

    manifest_data = {
        "version": "2.0.0",
        "protocol": "CinemaShield-ZeroTrust-Bridge",
        "created_at": created_iso,
        "theatre_id": theatre_id,
        "playback_window": {
            "start": playback_start.isoformat(),
            "end": playback_end.isoformat(),
            "duration_hours": playback_hours
        },
        "merkle_root": root_hash,
        "merkle_levels": len(tree_levels),
        "producer_signature": signature,
        "total_shards": len(shards_meta),
        "shards": shards_meta
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)

    print(f" Cryptographic Merkle Manifest generated: {manifest_path}")
    print(f" Merkle Root: {root_hash}")
    print(f" Total Sequential Shards: {len(shards_meta)}")

    return manifest_data


if __name__ == "__main__":
    generate_manifest()
