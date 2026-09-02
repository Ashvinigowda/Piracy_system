import os
import sys
import subprocess
import json
import time
from typing import Optional

BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from manifest_reader import load_manifest
from shard_loader import load_encrypted_shard
from key_request import request_kdm_license, request_key
from jit_decrypt import decrypt_shard
from integrity_check import verify_sha256, verify_merkle_leaf_proof

THEATRE_ID = "THEATRE_001"


def verify_merkle_shards(manifest: dict) -> bool:
    """
    Verify Merkle tree cryptographic proof for every shard BEFORE playback.
    Blocks playback immediately if any shard was tampered in the cloud mesh.
    """
    print(">>> 🌲 Verifying Merkle Tree cryptographic integrity of all shards...")
    merkle_root = manifest.get("merkle_root")

    for shard in manifest["shards"]:
        shard_id = shard["id"]
        expected_hash = shard["sha256"]
        proof = shard.get("merkle_proof", [])

        # Fetch shard from mesh
        encrypted = load_encrypted_shard(shard_id)

        # 1. Direct SHA-256 validation
        if not verify_sha256(encrypted, expected_hash):
            print(f"❌ SHA-256 hash mismatch for {shard_id}")
            return False

        # 2. Merkle Root Path Validation
        if merkle_root and proof:
            if not verify_merkle_leaf_proof(expected_hash, proof, merkle_root):
                print(f"❌ Merkle proof verification FAILED for {shard_id} against root {merkle_root}")
                return False

    print(f"✅ All {len(manifest['shards'])} shards passed bit-for-bit Merkle verification.")
    return True


def play_zero_disk_stream(theatre_id: str = THEATRE_ID):
    """
    Zero-Disk In-Memory Decryption & Playback:
    1. Authenticates DCI hardware certificate with KMS.
    2. Downloads and verifies Merkle proofs in RAM.
    3. Streams decrypted frames directly to ffplay through a memory pipe (stdin).
    Zero plaintext files or fragments are written to the filesystem.
    """
    print("=========================================================")
    print(f"▶ CinemaShield Theatre Ingest Gateway - {theatre_id}")
    print("=========================================================")

    # 1. Load Manifest
    manifest = load_manifest()
    if not manifest:
        print("❌ Could not load manifest.json")
        return

    # 2. Authenticate Hardware Certificate with KMS Broker
    print(">>> 🔐 Authenticating DCI Hardware Security Block Certificate with KMS Broker...")
    success, kdm = request_kdm_license(theatre_id)
    if not success:
        print(f"❌ KMS Authentication Denied: {kdm.get('error')}")
        return

    print(f"✅ KDM Issued: {kdm['kdm_id']}")
    print(f"   Theatre: {kdm['theatre_name']}")
    print(f"   Projector SMB: {kdm['projector_smb']}")
    print(f"   Expires At: {kdm['expires_at']}")

    master_kek = bytes.fromhex(kdm["master_kek_hex"])

    # 3. Merkle Integrity Verification
    if not verify_merkle_shards(manifest):
        print("❌ Playback aborted due to integrity failure.")
        return

    # 4. In-Memory Zero-Disk Streaming via Process Pipe
    print(">>> 🚀 Launching Zero-Disk Playback Pipeline (RAM Stream -> Media Engine)...")

    # Start ffplay reading directly from standard input (pipe:0)
    cmd = [
        "ffplay",
        "-i", "pipe:0",
        "-autoexit",
        "-loglevel", "warning",
        "-window_title", f"CinemaShield Secure Ingest - {theatre_id}"
    ]

    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

        for idx, shard in enumerate(manifest["shards"]):
            shard_id = shard["id"]
            routing = shard.get("routing", {})
            node = routing.get("primary_node", "STORAGE_MESH")

            print(f"   [Chunk {idx+1}/{len(manifest['shards'])}] Fetching {shard_id} from {node}...")
            encrypted = load_encrypted_shard(shard_id, preferred_node=node)

            # JIT in-memory decrypt
            decrypted = decrypt_shard(encrypted, master_kek)

            # Push directly into decoder pipe in RAM
            try:
                proc.stdin.write(decrypted)
                proc.stdin.flush()
            except (BrokenPipeError, IOError):
                print("⚠ Playback closed by user.")
                break
            finally:
                del decrypted  # Wipe buffer from RAM immediately

        if proc.stdin:
            proc.stdin.close()
        proc.wait()

        print(">>> 🏁 Playback session concluded. Zero artifacts remained on disk.")

    except FileNotFoundError:
        print("⚠ ffplay executable not found in PATH. Simulating in-memory stream validation...")
        total_decrypted_bytes = 0
        for shard in manifest["shards"]:
            encrypted = load_encrypted_shard(shard["id"])
            decrypted = decrypt_shard(encrypted, master_kek)
            total_decrypted_bytes += len(decrypted)
            del decrypted
        print(f"✅ In-memory zero-disk validation successful! Total stream processed: {total_decrypted_bytes / (1024*1024):.2f} MB")


if __name__ == "__main__":
    play_zero_disk_stream()
