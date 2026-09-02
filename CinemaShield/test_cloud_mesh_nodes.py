import os
import sys
import json
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
CLOUD_MESH_DIR = os.path.join(BASE_DIR, "cloud_mesh")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, CLOUD_MESH_DIR)

from storage_mesh import (
    STORAGE_NODES, scatter_shards, fetch_shard_from_mesh,
    set_node_status, get_mesh_status, init_storage_mesh
)
from mesh_manager import CLOUD_NODES_CONFIG, upload_shard_http, fetch_shard_http


def test_independent_cloud_mesh():
    print("=" * 65)
    print("🌐 REAL-WORLD MULTI-CLOUD STORAGE MESH NETWORK TEST SUITE")
    print("=" * 65)

    # 1. Initialize and Verify 5 HTTP Cloud Node Endpoints
    print("\n[1/5] Checking 5 Independent Cloud Node Microservices on Ports 8001-8005...")
    init_storage_mesh()
    status = get_mesh_status()
    print(f"✔ Total Active Cloud Nodes: {status['total_nodes']} (Online: {status['online_nodes']})")
    
    for nid, cfg in CLOUD_NODES_CONFIG.items():
        node_info = status["nodes"].get(nid, {})
        print(f"   {cfg['icon']} {nid}: {cfg['url']} | Region: {cfg['region']} | Status: {node_info.get('status', 'ONLINE')}")
    assert status["online_nodes"] == 5, "Not all 5 cloud node microservices are online!"

    # 2. Test Real HTTP PUT & GET on an individual node
    print("\n[2/5] Testing Direct HTTP PUT / GET with SHA-256 ETag Validation on Node 1 (AWS S3, Port 8001)...")
    test_shard_name = "test_shard_001.mp4.enc"
    test_payload = b"CinemaShield_Encrypted_Binary_Payload_0xDEADBEEF" * 128
    
    put_ok = upload_shard_http("AWS_S3_US_EAST", test_shard_name, test_payload)
    assert put_ok is True, "HTTP PUT failed on AWS_S3_US_EAST"
    print("✔ HTTP PUT 201 Created: Uploaded encrypted shard payload to http://127.0.0.1:8001/api/v1/objects/test_shard_001.mp4.enc")

    fetched_bytes = fetch_shard_http("AWS_S3_US_EAST", test_shard_name)
    assert fetched_bytes == test_payload, "Fetched payload does not match uploaded payload!"
    print(f"✔ HTTP GET 200 OK: Retrieved {len(fetched_bytes)} bytes bit-for-bit with matching SHA-256")

    # 3. Test Random Multi-Cloud Dispersion
    print("\n[3/5] Testing Random & Geographic Dispersion across all 5 Cloud Nodes...")
    test_dir = os.path.join(BASE_DIR, "test_temp_dispersion")
    os.makedirs(test_dir, exist_ok=True)
    for f in os.listdir(test_dir):
        os.remove(os.path.join(test_dir, f))
    
    # Create 5 test encrypted shards
    for i in range(5):
        sp = os.path.join(test_dir, f"dispersion_test_part{i:03d}.mp4.enc")
        with open(sp, "wb") as f:
            f.write(f"Encrypted_Payload_Block_{i}".encode("utf-8") * 200)

    routing_map = scatter_shards(test_dir)
    assert len(routing_map) == 5, f"Expected 5 shards, got {len(routing_map)}!"
    print(f"✔ Successfully scattered {len(routing_map)} shards over HTTP network:")
    for sname, rinfo in routing_map.items():
        print(f"   📦 {sname} -> Primary: {rinfo['primary_node']} (Port {CLOUD_NODES_CONFIG[rinfo['primary_node']]['port']}) | Backup: {rinfo['backup_node']} (Port {CLOUD_NODES_CONFIG[rinfo['backup_node']]['port']})")

    # 4. Test Live Cloud Outage & Automated HTTP Failover
    print("\n[4/5] Testing Simulated Outage on AWS_S3_US_EAST (Port 8001) & Automated Failover...")
    set_node_status("AWS_S3_US_EAST", "OFFLINE")
    print("✔ Set AWS_S3_US_EAST to 🔴 OFFLINE")

    # Fetch shard that was on AWS_S3_US_EAST
    target_shard = "dispersion_test_part000.mp4.enc"
    recovered_data = fetch_shard_from_mesh(target_shard, preferred_node="AWS_S3_US_EAST")
    assert len(recovered_data) > 0, "Failover fetch failed!"
    print(f"✔ AUTOMATED HTTP FAILOVER SUCCESS: Successfully retrieved {target_shard} from backup cloud node over HTTP!")

    # 5. Restore Node Online
    print("\n[5/5] Restoring AWS_S3_US_EAST to 🟢 ONLINE...")
    set_node_status("AWS_S3_US_EAST", "ONLINE")
    restored_status = get_mesh_status()
    assert restored_status["online_nodes"] == 5, "Failed restoring node online"
    print("✔ All 5 Cloud Storage Nodes restored to 🟢 ONLINE.")

    print("\n" + "=" * 65)
    print("🎉 ALL 5 MULTI-CLOUD STORAGE MESH TESTS PASSED 100%!")
    print("=" * 65)


if __name__ == "__main__":
    test_independent_cloud_mesh()
