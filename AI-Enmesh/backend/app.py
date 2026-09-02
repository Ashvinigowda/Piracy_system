"""
AI Enmesh — Distributed Storage Mesh Monitoring Backend & Mesh Controller
Runs the 5 Storage Node Microservices on ports 8001-8005 and the Enmesh Dashboard on port 6100.
Physical shard storage: AI-Enmesh/nodes/ENM-01 through ENM-05
"""

import os
import sys
import json
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
NODES_BASE_DIR = os.path.join(PROJECT_DIR, "nodes")

sys.path.insert(0, BASE_DIR)
from node_server import create_node_server

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

# ═══════════════════════════════════════════════════════
# 5 ENMESH STORAGE NODES (Ports 8001 - 8005)
# ═══════════════════════════════════════════════════════
NODE_REGISTRY = {
    "ENM-01": {"port": 8001, "url": "http://127.0.0.1:8001", "latency_ms": 10, "dir": os.path.join(NODES_BASE_DIR, "ENM-01")},
    "ENM-02": {"port": 8002, "url": "http://127.0.0.1:8002", "latency_ms": 25, "dir": os.path.join(NODES_BASE_DIR, "ENM-02")},
    "ENM-03": {"port": 8003, "url": "http://127.0.0.1:8003", "latency_ms": 15, "dir": os.path.join(NODES_BASE_DIR, "ENM-03")},
    "ENM-04": {"port": 8004, "url": "http://127.0.0.1:8004", "latency_ms": 30, "dir": os.path.join(NODES_BASE_DIR, "ENM-04")},
    "ENM-05": {"port": 8005, "url": "http://127.0.0.1:8005", "latency_ms": 12, "dir": os.path.join(NODES_BASE_DIR, "ENM-05")},
}

ACTIVE_NODE_SERVERS = {}
_telemetry_cache = {}
_cache_lock = threading.Lock()


def start_all_mesh_nodes():
    """Start the 5 independent storage node servers on ports 8001-8005."""
    for nid, cfg in NODE_REGISTRY.items():
        if nid in ACTIVE_NODE_SERVERS:
            continue
        os.makedirs(cfg["dir"], exist_ok=True)
        server = create_node_server(nid, cfg["port"], cfg["dir"], cfg["latency_ms"])
        t = threading.Thread(target=server.serve_forever, daemon=True, name=f"MeshNodeServer-{nid}")
        t.start()
        ACTIVE_NODE_SERVERS[nid] = server
        print(f"[AI-Enmesh] Started Storage Node {nid} on {cfg['url']} (Storage: nodes/{nid}/)")


def _poll_node(node_id, cfg):
    """Inspect physical disk and node server state for accurate telemetry."""
    base = {
        "node_id": node_id, "port": cfg["port"], "url": cfg["url"],
        "status": "ONLINE", "health": "HEALTHY", "latency_ms": cfg["latency_ms"],
        "shard_count": 0, "movie_count": 0, "total_bytes": 0,
        "uptime_seconds": 0, "objects": [], "is_backup_for": None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Inspect physical disk directory directly for real-time accurate shard counts
    storage_dir = cfg["dir"]
    if os.path.exists(storage_dir):
        files = [f for f in os.listdir(storage_dir) if os.path.isfile(os.path.join(storage_dir, f)) and not f.startswith('.')]
        total_size = sum(os.path.getsize(os.path.join(storage_dir, f)) for f in files)
        movie_prefixes = set()
        for obj in files:
            parts = obj.rsplit("_part", 1)
            if len(parts) == 2:
                movie_prefixes.add(parts[0])
            else:
                parts2 = obj.rsplit("_shard", 1)
                if len(parts2) == 2:
                    movie_prefixes.add(parts2[0])
                elif obj.endswith(".enc") or obj.endswith(".mp4"):
                    movie_prefixes.add(obj.split("_")[0] if "_" in obj else obj.split(".")[0])

        base["shard_count"] = len(files)
        base["total_bytes"] = total_size
        base["movie_count"] = len(movie_prefixes)
        base["objects"] = files

    # Check live server status
    if node_id in ACTIVE_NODE_SERVERS:
        srv = ACTIVE_NODE_SERVERS[node_id]
        status = getattr(srv, 'node_status', 'ONLINE')
        base["status"] = status
        base["health"] = "HEALTHY" if status == "ONLINE" else ("DEGRADED" if status == "DEGRADED" else "OFFLINE")
        base["uptime_seconds"] = int(time.time() - srv.start_time)
        return base

    return base


def _poll_all_nodes():
    results = {}
    for nid, cfg in NODE_REGISTRY.items():
        results[nid] = _poll_node(nid, cfg)

    _detect_backup_relationships(results)

    with _cache_lock:
        _telemetry_cache.update(results)


def _detect_backup_relationships(nodes):
    offline_nodes = [nid for nid, info in nodes.items() if info["status"] == "OFFLINE"]
    if not offline_nodes:
        for nid in nodes:
            nodes[nid]["is_backup_for"] = None
        return

    for nid, info in nodes.items():
        if info["status"] == "OFFLINE":
            continue
        shared = []
        my_objects = set(info.get("objects", []))
        for off_nid in offline_nodes:
            off_objects = set(nodes[off_nid].get("objects", []))
            if my_objects & off_objects:
                shared.append(off_nid)
        nodes[nid]["is_backup_for"] = shared if shared else None


# ═══════════════════════════════════════════
# REST API ENDPOINTS (Port 6100)
# ═══════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/v1/health")
def api_v1_health():
    """General health check endpoint for CinemaShield connection verification."""
    _poll_all_nodes()
    with _cache_lock:
        nodes = dict(_telemetry_cache)
    online = sum(1 for n in nodes.values() if n.get("status") == "ONLINE")
    return jsonify({
        "status": "ONLINE" if online > 0 else "OFFLINE",
        "service": "AI Enmesh Distributed Storage Mesh Controller",
        "total_nodes": len(NODE_REGISTRY),
        "online_nodes": online,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route("/api/mesh/telemetry")
def api_telemetry():
    """Full mesh telemetry for all nodes."""
    _poll_all_nodes()

    with _cache_lock:
        nodes = dict(_telemetry_cache)

    online = sum(1 for n in nodes.values() if n.get("status") == "ONLINE")
    offline = sum(1 for n in nodes.values() if n.get("status") == "OFFLINE")
    total_shards = sum(n.get("shard_count", 0) for n in nodes.values())
    total_bytes = sum(n.get("total_bytes", 0) for n in nodes.values())

    movie_set = set()
    for n in nodes.values():
        for obj in n.get("objects", []):
            parts = obj.rsplit("_part", 1)
            if len(parts) == 2:
                movie_set.add(parts[0])
            else:
                parts2 = obj.rsplit("_shard", 1)
                if len(parts2) == 2:
                    movie_set.add(parts2[0])

    network_status = "Operational" if online == len(NODE_REGISTRY) else ("Degraded" if online > 0 else "Critical")

    sanitized_nodes = {}
    for nid, info in nodes.items():
        sanitized_nodes[nid] = {k: v for k, v in info.items() if k != "objects"}

    return jsonify({
        "nodes": sanitized_nodes,
        "summary": {
            "total_nodes": len(NODE_REGISTRY),
            "online": online,
            "offline": offline,
            "total_shards": total_shards,
            "total_bytes": total_bytes,
            "total_movies": len(movie_set),
            "network_status": network_status,
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route("/api/mesh/nodes/<node_id>")
def api_node_detail(node_id):
    """Detailed telemetry for a single node."""
    node_id = node_id.upper()
    if node_id not in NODE_REGISTRY:
        return jsonify({"error": f"Unknown node {node_id}"}), 404
    info = _poll_node(node_id, NODE_REGISTRY[node_id])
    info.pop("objects", None)
    return jsonify(info)


@app.route("/api/mesh/toggle/<node_id>", methods=["POST"])
def api_toggle_node(node_id):
    """Toggle a node ONLINE/OFFLINE for outage simulation."""
    node_id = node_id.upper()
    if node_id not in NODE_REGISTRY:
        return jsonify({"error": f"Unknown node {node_id}"}), 404

    data = request.get_json() or {}
    new_status = data.get("status", "OFFLINE").upper()

    if node_id in ACTIVE_NODE_SERVERS:
        ACTIVE_NODE_SERVERS[node_id].node_status = new_status
        _poll_all_nodes()
        return jsonify({"node_id": node_id, "status": new_status})

    cfg = NODE_REGISTRY[node_id]
    try:
        req = urllib.request.Request(
            f"{cfg['url']}/api/v1/toggle-outage",
            data=json.dumps({"status": new_status}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            _poll_all_nodes()
            return jsonify({"node_id": node_id, "status": result.get("status", new_status)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Start all node microservices on module load
start_all_mesh_nodes()

if __name__ == "__main__":
    print("=" * 65)
    print("   AI ENMESH - Distributed Storage Mesh Controller & Nodes")
    print("=" * 65)
    print("   Controller / Dashboard: http://localhost:6100")
    print("   Mesh Health API:        http://localhost:6100/api/v1/health")
    print("   Storage Nodes:          Ports 8001, 8002, 8003, 8004, 8005")
    print("   Storage Root:           AI-Enmesh/nodes/")
    print("=" * 65)
    app.run(host="0.0.0.0", port=6100, debug=False)
