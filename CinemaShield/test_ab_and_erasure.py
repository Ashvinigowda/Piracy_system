import os
import sys
import json
import hashlib

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, FRONTEND_DIR)

from forensic_ab import (
    generate_theatre_ab_sequence, embed_steganographic_tag,
    extract_steganographic_tag, trace_leaked_fingerprint
)
from erasure_coding import (
    encode_parity_shards, reconstruct_data_shards
)
from storage_mesh import set_node_status, fetch_shard_from_mesh, scatter_shards, clean_storage_mesh
from encrypt_shards import encrypt_all_shards, load_or_create_master_kek
from app import app


def run_feature_tests():
    print("=================================================================")
    print("🧬 FEATURE 1 & 3: A/B FORENSIC SHARDING & REED-SOLOMON TEST SUITE")
    print("=================================================================\n")

    # ─────────────────────────────────────────────────────────────
    # TEST 1: A/B DUAL-VARIANT STEGANOGRAPHY & UNIQUENESS
    # ─────────────────────────────────────────────────────────────
    print("[1/5] Testing A/B Forensic Dual-Variant Watermarking...")
    dummy_payload = b"TEST_VIDEO_FRAME_BLOCK_CINEMA_SHIELD_PAYLOAD_12345678"
    
    tagged_a = embed_steganographic_tag(dummy_payload, "A", shard_index=1, theatre_id="THEATRE_001")
    tagged_b = embed_steganographic_tag(dummy_payload, "B", shard_index=1, theatre_id="THEATRE_001")
    
    assert tagged_a != tagged_b, "Variant A and B must be distinct byte payloads"
    
    extracted_a = extract_steganographic_tag(tagged_a)
    extracted_b = extract_steganographic_tag(tagged_b)
    
    assert extracted_a["variant"] == "A", "Extracted variant must be A"
    assert extracted_b["variant"] == "B", "Extracted variant must be B"
    print("✔ A/B Steganographic watermarks successfully embedded and extracted.")

    # ─────────────────────────────────────────────────────────────
    # TEST 2: THEATRE FORENSIC COMBINATION UNIQUENESS & LEAK TRACER
    # ─────────────────────────────────────────────────────────────
    print("\n[2/5] Testing Theatre Forensic Combination Uniqueness & Leak Tracer...")
    theatres = ["THEATRE_001", "THEATRE_002", "THEATRE_003"]
    sequences = {t: generate_theatre_ab_sequence(t, 8) for t in theatres}

    # Verify each theatre receives a unique sequence
    assert sequences["THEATRE_001"] != sequences["THEATRE_002"]
    assert sequences["THEATRE_002"] != sequences["THEATRE_003"]
    assert sequences["THEATRE_001"] != sequences["THEATRE_003"]

    print("✔ Assigned Sequences:")
    for t, seq in sequences.items():
        print(f"   - {t}: {'-'.join(seq)} (Binary: {''.join('1' if x=='B' else '0' for x in seq)})")

    # Simulate finding a leaked video matching THEATRE_002
    leaked_clip_seq = sequences["THEATRE_002"]
    trace_result = trace_leaked_fingerprint(leaked_clip_seq, theatres, 8)

    assert trace_result["matched"] is True
    assert trace_result["best_match"]["theatre_id"] == "THEATRE_002"
    assert trace_result["best_match"]["match_percentage"] == 100.0
    print(f"✔ Leak Reverse-Lookup Scanner: Correctly identified {trace_result['best_match']['theatre_id']} with 100% confidence!")

    # ─────────────────────────────────────────────────────────────
    # TEST 3: REED-SOLOMON GALOIS FIELD ERASURE ENCODING
    # ─────────────────────────────────────────────────────────────
    print("\n[3/5] Testing Reed-Solomon Galois Field GF(2^8) Erasure Encoding...")
    data_shards = [
        b"CinemaShield_Data_Block_00_Payload",
        b"CinemaShield_Data_Block_01_Payload",
        b"CinemaShield_Data_Block_02_Payload",
        b"CinemaShield_Data_Block_03_Payload",
        b"CinemaShield_Data_Block_04_Payload",
        b"CinemaShield_Data_Block_05_Payload",
    ]

    parity_shards = encode_parity_shards(data_shards, parity_count=2)
    assert len(parity_shards) == 2, "Must produce 2 parity shards"
    print(f"✔ Generated 2 Reed-Solomon parity shards from 6 data shards (Total: {len(data_shards) + len(parity_shards)} shards).")

    # ─────────────────────────────────────────────────────────────
    # TEST 4: MULTI-CLOUD OUTAGE RECOVERY (SELF-HEALING)
    # ─────────────────────────────────────────────────────────────
    print("\n[4/5] Testing Multi-Cloud Outage Recovery (Simulating losing Shards 1 & 4)...")
    # Simulate total loss of Shard 1 and Shard 4 (e.g. AWS and Wasabi down)
    surviving_pool = {
        0: data_shards[0],
        2: data_shards[2],
        3: data_shards[3],
        5: data_shards[5],
        6: parity_shards[0],  # Parity 0
        7: parity_shards[1]   # Parity 1
    }

    recovered = reconstruct_data_shards(surviving_pool, total_data_count=6, parity_count=2)
    for i in range(6):
        assert recovered[i] == data_shards[i], f"Reconstructed data shard {i} must match original bit-for-bit"
    print("✔ REED-SOLOMON SELF-HEALING SUCCESS: 100% of data shards reconstructed bit-for-bit from parity pool!")

    # ─────────────────────────────────────────────────────────────
    # TEST 5: FLASK REST ENDPOINTS FOR A/B TRACE & NODE TOGGLE
    # ─────────────────────────────────────────────────────────────
    print("\n[5/5] Testing Flask REST Endpoints for Forensic Trace & Node Outage Toggle...")
    client = app.test_client()

    # Test Node Toggle
    toggle_res = client.post("/api/storage-mesh/node-toggle", json={"node_id": "WASABI_AP_SOUTH", "status": "OFFLINE"})
    assert toggle_res.status_code == 200
    toggle_data = toggle_res.get_json()
    assert toggle_data["status"] == "OFFLINE"
    print("✔ POST /api/storage-mesh/node-toggle (Set WASABI_AP_SOUTH OFFLINE) -> 200 OK")

    # Test Forensic Trace Endpoint
    trace_res = client.post("/api/forensic/trace", json={"sequence": "A-A-A-B-A-B-B-A"})
    assert trace_res.status_code == 200
    trace_api_data = trace_res.get_json()
    assert trace_api_data["matched"] is True
    print(f"✔ POST /api/forensic/trace -> 200 OK (Matched: {trace_api_data['best_match']['theatre_id']})")

    # Restore node back to ONLINE
    client.post("/api/storage-mesh/node-toggle", json={"node_id": "WASABI_AP_SOUTH", "status": "ONLINE"})
    print("✔ Restored WASABI_AP_SOUTH to ONLINE.")

    print("\n=================================================================")
    print("🎉 ALL FEATURE 1 (A/B SHARDING) & FEATURE 3 (REED-SOLOMON) TESTS PASSED!")
    print("=================================================================\n")


if __name__ == "__main__":
    run_feature_tests()
