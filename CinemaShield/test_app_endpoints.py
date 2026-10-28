import os
import sys
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
sys.path.insert(0, FRONTEND_DIR)

from app import app
import kms


def find_fingerprint(data):
    """Find a registered certificate fingerprint in an API response."""
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = key.lower().replace("-", "_")

            if (
                normalized in (
                    "cert_fingerprint",
                    "certificate_fingerprint",
                    "fingerprint",
                )
                and isinstance(value, str)
                and value.strip()
            ):
                return value.strip()

        for value in data.values():
            result = find_fingerprint(value)
            if result:
                return result

    elif isinstance(data, list):
        for item in data:
            result = find_fingerprint(item)
            if result:
                return result

    return None


def check_status(response, expected, test_name):
    """Check the HTTP status code of an API response."""
    if response.status_code != expected:
        print(f"FAIL: {test_name}")
        print(
            f"Expected HTTP {expected}; "
            f"received HTTP {response.status_code}"
        )
        print("Response:", response.get_data(as_text=True)[:1000])
        raise AssertionError(f"{test_name} failed")

    print(f"PASS: {test_name} -> HTTP {expected}")


def test_flask_app():
    print("Testing CinemaShield Flask Web Application Endpoints...\n")

    client = app.test_client()

    # 1. Page routes
    print("1. Testing page routes")

    for path in ["/", "/producer", "/theatre", "/analytics"]:
        response = client.get(path)
        check_status(response, 200, f"Page {path}")

    print()

    # 2. Storage mesh
    print("2. Testing storage mesh")

    mesh_response = client.get("/api/storage-mesh")
    check_status(mesh_response, 200, "Storage mesh API")

    mesh_data = mesh_response.get_json() or {}

    assert len(mesh_data.get("nodes", [])) == 5, (
        "Expected five storage nodes"
    )

    print("PASS: Five storage nodes are registered\n")

    # 3. Merkle tree
    print("3. Testing Merkle tree")

    merkle_response = client.get("/api/merkle-tree")
    check_status(merkle_response, 200, "Merkle tree API")

    merkle_data = merkle_response.get_json() or {}

    assert merkle_data.get("merkle_root"), "Merkle root is missing"

    print("PASS: Merkle root is present\n")

    # 4. Theatre certificates
    print("4. Testing theatre certificates")

    cert_response = client.get("/api/theatres/certs")
    check_status(cert_response, 200, "Theatre certificates API")

    cert_data = cert_response.get_json() or {}

    assert "THEATRE_001" in cert_data, (
        "THEATRE_001 is not registered in the certificate response"
    )

    fingerprint = find_fingerprint(cert_data["THEATRE_001"])

    if not fingerprint:
        print(
            "Certificate response:",
            repr(cert_data["THEATRE_001"])[:1500],
        )
        raise AssertionError(
            "Could not find the registered certificate fingerprint"
        )

    print("PASS: Theatre and registered fingerprint found\n")

    # 5. KMS KDM request and Attack 3 secret-exposure checks
    print("5. Testing KMS KDM request and sensitive-field protection")

    # Report the real playback-window state without changing it.
    window_valid, window_message = kms.check_playback_window()
    print(f"Real playback-window check: {window_message}")

    # Simulate an active showtime only for this test request.
    # The production KMS function and manifest are not modified.
    with patch.object(
        kms,
        "check_playback_window",
        return_value=(True, "Active test playback window"),
    ):
        kdm_response = client.post(
            "/api/kms/request-kdm",
            json={
                "theatre_id": "THEATRE_001",
                "cert_fingerprint": fingerprint,
            },
        )

    check_status(kdm_response, 200, "KMS KDM request")

    kdm_data = kdm_response.get_json() or {}

    assert kdm_data.get("kdm_id"), (
        "KDM response is missing kdm_id"
    )

    print(f"PASS: KDM issued: {kdm_data['kdm_id']}")

    # Attack 3: Public KDM responses must not expose sensitive fields.
    sensitive_fields = {
        "master_kek_hex",
        "_master_kek_hex",
        "session_token",
    }

    exposed_fields = sensitive_fields.intersection(kdm_data.keys())

    assert not exposed_fields, (
        "SECURITY FAILURE: Public KDM response exposes sensitive fields: "
        f"{sorted(exposed_fields)}"
    )

    print(
        "PASS: Public KDM response excludes master keys "
        "and session token\n"
    )

    # 6. Theatre ingest simulation
    print("6. Testing theatre ingest simulation")

    ingest_response = client.post(
        "/api/theatre/ingest-simulate",
        json={"theatre_id": "THEATRE_001"},
    )

    check_status(
        ingest_response,
        200,
        "Theatre ingest simulation",
    )

    ingest_data = ingest_response.get_json() or {}

    assert ingest_data.get("all_verified") is True, (
        f"Not all shards were verified: {ingest_data}"
    )

    print(
        f"PASS: {ingest_data.get('total_shards', 'Unknown')} "
        "shards verified\n"
    )

    # 7. Analytics
    print("7. Testing analytics")

    analytics_response = client.get("/api/ai/analytics-summary")

    check_status(
        analytics_response,
        200,
        "AI analytics summary",
    )

    analytics_data = analytics_response.get_json() or {}

    assert "threats" in analytics_data, (
        "Analytics response is missing threats"
    )

    print("PASS: Analytics response contains threats\n")

    print("ALL TESTED FLASK ENDPOINTS PASSED!")


if __name__ == "__main__":
    test_flask_app()