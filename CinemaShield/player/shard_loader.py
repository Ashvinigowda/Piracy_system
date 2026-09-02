import os
import sys

BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from storage_mesh import fetch_shard_from_mesh


def load_encrypted_shard(shard_id: str, preferred_node: str = None) -> bytes:
    """
    Fetch encrypted shard across the multi-cloud storage mesh.
    Falls back gracefully across cloud nodes (AWS, Cloudflare, Wasabi, Edge).
    """
    # First try from storage mesh
    try:
        return fetch_shard_from_mesh(shard_id, preferred_node)
    except Exception:
        pass

    # Fallback to local encrypted_shards directory if mesh directory isn't synced
    local_path = os.path.join(BACKEND_DIR, "encrypted_shards", shard_id)
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            return f.read()

    raise FileNotFoundError(f"Shard {shard_id} not available on any storage node or local cache")
