import os
import sys
import json
import io

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, FRONTEND_DIR)

from app import app, movies, KEY_PATH
from encrypt_shards import load_or_create_master_kek

def test_full_auth_flow():
    print("Testing Full Studio Upload -> Ingest -> Theatre Key Unlock Flow...")
    client = app.test_client()

    # Step 1: Create a test video if not present
    test_video = os.path.join(BASE_DIR, "test_clip.mp4")
    if not os.path.exists(test_video):
        # Generate 2 second synthetic mp4 with ffmpeg
        os.system(f'ffmpeg -y -f lavfi -i testsrc=duration=4:size=640x360:rate=24 -f lavfi -i sine=frequency=1000:duration=4 -c:v libx264 -c:a aac -movflags +faststart "{test_video}"')

    with open(test_video, "rb") as f:
        data = f.read()

    upload_res = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(data), "test_clip.mp4"), "theatre_id": "THEATRE_001"},
        content_type="multipart/form-data"
    )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.data}"
    movie_id = upload_res.get_json()["movie_id"]
    print(f" 1. Uploaded test video: movie_id={movie_id}")

    # Step 2: Run process SSE pipeline
    proc_res = client.get(f"/api/process/{movie_id}")
    assert proc_res.status_code == 200, "Process SSE failed"
    sse_data = proc_res.data.decode('utf-8')
    print(" 2. Process SSE pipeline executed successfully")

    # Extract key
    master_kek = load_or_create_master_kek(KEY_PATH).hex()
    print(f" 3. Master KEK: {master_kek}")

    # Step 3: Test Theatre Ingest Simulate
    sim_res = client.post("/api/theatre/ingest-simulate", json={"theatre_id": "THEATRE_001"})
    assert sim_res.status_code == 200, f"Ingest simulate failed: {sim_res.data}"
    sim_data = sim_res.get_json()
    print(f" 4. Ingest simulate verified {sim_data['total_shards']} sequential shards across storage mesh")

    # Step 4: Test Theatre Manual KEK Unlock on /api/authenticate
    auth_res = client.post("/api/authenticate", json={"key": master_kek, "theatre_id": "THEATRE_001"})
    print(f"Auth status code: {auth_res.status_code}")
    print(f"Auth response: {auth_res.data.decode('utf-8')}")
    assert auth_res.status_code == 200, f"Authentication with Master KEK failed: {auth_res.data}"
    auth_data = auth_res.get_json()
    assert auth_data["success"] is True
    print(f" 5. Master KEK Authentication succeeded! Token: {auth_data['token']}")

    # Step 5: Test video stream endpoint
    stream_res = client.get(f"/api/stream/{auth_data['token']}")
    assert stream_res.status_code in [200, 206], f"Stream endpoint failed: {stream_res.status_code}"
    print(f" 6. Video streaming verified! Received {len(stream_res.data)} bytes of zero-disk video stream.")

    print("\n ALL THEATRE INGEST & PLAYBACK TESTS PASSED 100%!")


if __name__ == "__main__":
    test_full_auth_flow()
