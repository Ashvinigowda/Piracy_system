import os
import sys
import json
import hashlib

# Ensure utf-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure backend and player are in path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
PLAYER_DIR = os.path.join(BASE_DIR, "player")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, PLAYER_DIR)

from storage_mesh import scatter_shards, get_mesh_status, fetch_shard_from_mesh, clean_storage_mesh
from encrypt_shards import encrypt_all_shards, load_or_create_master_kek, decrypt_shard_envelope
from generate_manifest import generate_manifest, build_merkle_tree, verify_merkle_proof
from kms import issue_ephemeral_kdm, validate_dci_attestation
from integrity_check import verify_merkle_leaf_proof
from jit_decrypt import decrypt_shard

def run_all_tests():
    print("=================================================================")
    print("🎬 CINEMASHIELD 2.0 ZERO-TRUST BRIDGE VERIFICATION SUITE")
    print("=================================================================\n")

    # 1. Clean and Setup Test Shards
    print("[1/6] Setting up dummy shard payload for testing...")
    test_shards_dir = os.path.join(BACKEND_DIR, "shards")
    test_enc_dir = os.path.join(BACKEND_DIR, "encrypted_shards")
    os.makedirs(test_shards_dir, exist_ok=True)
    os.makedirs(test_enc_dir, exist_ok=True)

    dummy_payloads = [
        b"CinemaShield_Shard_001_Data_Block_Video_Frame_000000000000000001",
        b"CinemaShield_Shard_002_Data_Block_Video_Frame_000000000000000002",
        b"CinemaShield_Shard_003_Data_Block_Video_Frame_000000000000000003",
        b"CinemaShield_Shard_004_Data_Block_Video_Frame_000000000000000004",
        b"CinemaShield_Shard_005_Data_Block_Video_Frame_000000000000000005"
    ]

    for i, payload in enumerate(dummy_payloads):
        shard_path = os.path.join(test_shards_dir, f"test_clip_part{i:03d}.mp4")
        with open(shard_path, "wb") as f:
            f.write(payload)

    print(f"✔ Created {len(dummy_payloads)} test shards.")

    # 2. Test AES-256-GCM Envelope Encryption
    print("\n[2/6] Testing AES-256-GCM Envelope Encryption...")
    key_path = os.path.join(BACKEND_DIR, "secret.key")
    master_kek = load_or_create_master_kek(key_path)
    processed = encrypt_all_shards(shards_dir=test_shards_dir, encrypted_dir=test_enc_dir, key_path=key_path)
    assert len(processed) == len(dummy_payloads), "All shards must be encrypted"
    print(f"✔ Sealed {len(processed)} shards with unique DEKs under Master KEK.")

    # 3. Test Multi-Cloud Storage Mesh Dispersion
    print("\n[3/6] Testing Multi-Cloud Zero-Trust Storage Mesh Dispersion...")
    clean_storage_mesh()
    routing_map = scatter_shards(test_enc_dir)
    assert len(routing_map) == len(dummy_payloads), "All shards must have cloud routes"
    mesh_status = get_mesh_status()
    print(f"✔ Shards scattered across {mesh_status['total_nodes']} cloud nodes.")
    for nid, n in mesh_status['nodes'].items():
        print(f"   - {n['icon']} {n['name']}: {n['shard_count']} shard(s)")

    # 4. Test Merkle Tree Generation & Audit Proofs
    print("\n[4/6] Testing Merkle Tree Generation & Audit Proofs...")
    manifest_path = os.path.join(BACKEND_DIR, "manifest.json")
    manifest = generate_manifest(
        shards_dir=test_enc_dir,
        manifest_path=manifest_path,
        theatre_id="THEATRE_001",
        routing_map=routing_map
    )
    merkle_root = manifest["merkle_root"]
    assert merkle_root, "Merkle Root must be generated"
    print(f"✔ Merkle Root Hash: {merkle_root}")
    print(f"✔ Total Merkle Tree Levels: {manifest['merkle_levels']}")

    # Verify Merkle proofs for every shard
    for s in manifest["shards"]:
        proof = s["merkle_proof"]
        leaf_hash = s["sha256"]
        valid = verify_merkle_proof(leaf_hash, proof, merkle_root)
        assert valid, f"Merkle proof verification failed for {s['id']}"
    print(f"✔ 100% of shard Merkle audit proofs cryptographically verified.")

    # 5. Test DCI Hardware Certificate Attestation & KMS KDM Broker
    print("\n[5/6] Testing DCI Hardware Certificate & KMS KDM Broker...")
    valid_attest, msg = validate_dci_attestation("THEATRE_001")
    assert valid_attest, "THEATRE_001 must be recognized DCI certificate"

    success, kdm = issue_ephemeral_kdm("THEATRE_001")
    assert success, f"KMS must issue KDM for THEATRE_001 ({kdm.get('error')})"
    print(f"✔ Ephemeral KDM Issued: {kdm['kdm_id']}")
    print(f"   Theatre: {kdm['theatre_name']}")
    print(f"   Projector SMB: {kdm['projector_smb']}")

    # 6. Test In-Memory Zero-Disk Shard Retrieval & Decryption
    print("\n[6/6] Testing Zero-Disk In-Memory Decryption Pipeline...")
    kdm_kek = bytes.fromhex(kdm["master_kek_hex"])
    for i, s in enumerate(manifest["shards"]):
        shard_id = s["id"]
        # Fetch from mesh
        encrypted_bytes = fetch_shard_from_mesh(shard_id)
        # Decrypt strictly in memory
        decrypted_bytes = decrypt_shard(encrypted_bytes, kdm_kek)
        assert decrypted_bytes == dummy_payloads[i], f"Decrypted payload mismatch on shard {i}"
        del decrypted_bytes
    print("✔ All shards retrieved from multi-cloud mesh and decrypted accurately in RAM.")

    print("\n=================================================================")
    print("🎉 ALL 6 ZERO-TRUST BRIDGE VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=================================================================\n")

if __name__ == "__main__":
    run_all_tests()
