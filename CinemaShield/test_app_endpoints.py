import os
import sys
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
sys.path.insert(0, FRONTEND_DIR)

from app import app

def test_flask_app():
    print("Testing CinemaShield Flask Web Application Endpoints...")
    client = app.test_client()

    # 1. Test Page Routes
    pages = ["/", "/producer", "/theatre", "/analytics"]
    for p in pages:
        res = client.get(p)
        assert res.status_code == 200, f"Failed loading {p} (status {res.status_code})"
        print(f"✔ Page route {p} -> 200 OK")

    # 2. Test Storage Mesh API
    mesh_res = client.get("/api/storage-mesh")
    assert mesh_res.status_code == 200
    mesh_data = mesh_res.get_json()
    assert "nodes" in mesh_data and len(mesh_data["nodes"]) == 5
    print("✔ GET /api/storage-mesh -> 200 OK (5 active cloud nodes verified)")

    # 3. Test Merkle Tree API
    merkle_res = client.get("/api/merkle-tree")
    assert merkle_res.status_code == 200
    merkle_data = merkle_res.get_json()
    assert "merkle_root" in merkle_data
    print(f"✔ GET /api/merkle-tree -> 200 OK (Root: {merkle_data['merkle_root'][:16]}...)")

    # 4. Test Theatres & DCI Certs API
    theatres_res = client.get("/api/theatres/certs")
    assert theatres_res.status_code == 200
    theatres_data = theatres_res.get_json()
    assert "THEATRE_001" in theatres_data
    print(f"✔ GET /api/theatres/certs -> 200 OK ({len(theatres_data)} DCI endpoints registered)")

    # 5. Test DCI Hardware Attestation & KMS KDM Request API
    kdm_res = client.post("/api/kms/request-kdm", json={"theatre_id": "THEATRE_001"})
    assert kdm_res.status_code == 200
    kdm_data = kdm_res.get_json()
    assert "kdm_id" in kdm_data
    print(f"✔ POST /api/kms/request-kdm -> 200 OK (Issued KDM: {kdm_data['kdm_id']})")

    # 6. Test Ingest Simulation API
    ingest_res = client.post("/api/theatre/ingest-simulate", json={"theatre_id": "THEATRE_001"})
    assert ingest_res.status_code == 200
    ingest_data = ingest_res.get_json()
    assert ingest_data.get("all_verified") is True
    print(f"✔ POST /api/theatre/ingest-simulate -> 200 OK ({ingest_data['total_shards']} shards verified)")

    # 7. Test Analytics Summary & AI Threats API
    analytics_res = client.get("/api/ai/analytics-summary")
    assert analytics_res.status_code == 200
    analytics_data = analytics_res.get_json()
    assert "threats" in analytics_data
    print("✔ GET /api/ai/analytics-summary -> 200 OK")

    print("\n🎉 ALL FLASK WEB ENDPOINTS TESTED AND VALIDATED SUCCESSFULLY!")

if __name__ == "__main__":
    test_flask_app()
