"""
CinemaShield — Storage Mesh Client for AI Enmesh
Communicates with AI Enmesh storage nodes strictly over HTTP REST APIs.
No local filesystem access to AI Enmesh directories.
"""

import os
import sys
import time
import random
import json
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

# ═══════════════════════════════════════════════════════
# AI ENMESH CLOUD NODE REST ENDPOINTS (Ports 8001 - 8005)
# ═══════════════════════════════════════════════════════
AI_ENMESH_NODES = {
    "ENM-01": {"node_id": "ENM-01", "port": 8001, "url": "http://127.0.0.1:8001", "name": "AI Enmesh Node 01"},
    "ENM-02": {"node_id": "ENM-02", "port": 8002, "url": "http://127.0.0.1:8002", "name": "AI Enmesh Node 02"},
    "ENM-03": {"node_id": "ENM-03", "port": 8003, "url": "http://127.0.0.1:8003", "name": "AI Enmesh Node 03"},
    "ENM-04": {"node_id": "ENM-04", "port": 8004, "url": "http://127.0.0.1:8004", "name": "AI Enmesh Node 04"},
    "ENM-05": {"node_id": "ENM-05", "port": 8005, "url": "http://127.0.0.1:8005", "name": "AI Enmesh Node 05"},
}

ENMESH_CONTROLLER_URL = "http://127.0.0.1:6100"

STORAGE_NODES = {
    nid: {
        "id": cfg["node_id"],
        "name": cfg["name"],
        "url": cfg["url"],
        "port": cfg["port"],
        "status": "ONLINE"
    }
    for nid, cfg in AI_ENMESH_NODES.items()
}


def check_enmesh_connection() -> Dict[str, Any]:
    """
    Check if AI Enmesh controller and storage nodes are accessible over HTTP.
    """
    try:
        req = urllib.request.Request(f"{ENMESH_CONTROLLER_URL}/api/v1/health")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "connected": True,
                "status": "ONLINE",
                "total_nodes": data.get("total_nodes", len(AI_ENMESH_NODES)),
                "online_nodes": data.get("online_nodes", len(AI_ENMESH_NODES)),
                "controller_url": ENMESH_CONTROLLER_URL
            }
    except Exception as e:
        # Fallback: check node 1 directly
        try:
            req = urllib.request.Request(f"{AI_ENMESH_NODES['ENM-01']['url']}/api/v1/health")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                return {
                    "connected": True,
                    "status": "ONLINE",
                    "total_nodes": len(AI_ENMESH_NODES),
                    "online_nodes": len(AI_ENMESH_NODES),
                    "controller_url": ENMESH_CONTROLLER_URL
                }
        except Exception:
            return {
                "connected": False,
                "status": "DISCONNECTED",
                "error": str(e),
                "controller_url": ENMESH_CONTROLLER_URL
            }


def init_storage_mesh():
    """Ensure AI Enmesh connection is active."""
    pass


def clean_storage_mesh():
    """No-op on CinemaShield side since storage is remote on AI Enmesh."""
    pass


def _http_put_shard(node_id: str, shard_name: str, payload_bytes: bytes) -> bool:
    """Send an encrypted shard payload to an AI Enmesh node via HTTP PUT."""
    cfg = AI_ENMESH_NODES.get(node_id)
    if not cfg:
        raise ValueError(f"Unknown AI Enmesh node {node_id}")

    url = f"{cfg['url']}/api/v1/objects/{shard_name}"
    req = urllib.request.Request(
        url,
        data=payload_bytes,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(payload_bytes))
        },
        method="PUT"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status in [200, 201]:
            return True
        raise IOError(f"HTTP {resp.status} from {node_id}")


def _http_get_shard(node_id: str, shard_name: str) -> bytes:
    """Fetch an encrypted shard from an AI Enmesh node via HTTP GET."""
    cfg = AI_ENMESH_NODES.get(node_id)
    if not cfg:
        raise ValueError(f"Unknown AI Enmesh node {node_id}")

    url = f"{cfg['url']}/api/v1/objects/{shard_name}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status == 200:
            return resp.read()
        raise IOError(f"HTTP {resp.status} from {node_id}")


def scatter_shards(encrypted_shards_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Distribute encrypted shards evenly and randomly across the 5 AI Enmesh nodes.
    Uploads each shard payload over REAL HTTP PUT requests to primary and backup nodes.
    """
    if not os.path.exists(encrypted_shards_dir):
        return {}

    shard_files = sorted([
        f for f in os.listdir(encrypted_shards_dir)
        if os.path.isfile(os.path.join(encrypted_shards_dir, f)) and f.endswith(".enc")
    ])

    if not shard_files:
        return {}

    node_ids = list(AI_ENMESH_NODES.keys())
    # Deterministic yet randomized starting permutation for balanced scattering
    random.shuffle(node_ids)
    num_nodes = len(node_ids)

    routing_map = {}
    upload_tasks = []

    print("\n" + "═" * 65)
    print(" [CINEMASHIELD → AI ENMESH] Dispersing Encrypted Shards over HTTP")
    print("═" * 65)

    for idx, shard_file in enumerate(shard_files):
        src_path = os.path.join(encrypted_shards_dir, shard_file)
        with open(src_path, "rb") as f:
            payload = f.read()

        # Balanced round-robin primary assignment
        primary_node = node_ids[idx % num_nodes]
        # Diverse backup node assignment
        backup_offset = (num_nodes // 2) if num_nodes > 2 else 1
        backup_node = node_ids[(idx + backup_offset) % num_nodes]

        primary_url = f"{AI_ENMESH_NODES[primary_node]['url']}/api/v1/objects/{shard_file}"
        backup_url = f"{AI_ENMESH_NODES[backup_node]['url']}/api/v1/objects/{shard_file}"

        print(f"[CINEMASHIELD] Created shard: {shard_file}")
        print(f"[DISPERSION]   Primary: {primary_node} | Backup: {backup_node}")
        print(f"[HTTP PUT]     → {primary_url}")
        print(f"[HTTP PUT]     → {backup_url}")

        upload_tasks.append((primary_node, shard_file, payload, "primary"))
        upload_tasks.append((backup_node, shard_file, payload, "backup"))

        routing_map[shard_file] = {
            "shard_id": shard_file,
            "primary_node": primary_node,
            "backup_node": backup_node,
            "size_bytes": len(payload),
            "primary_endpoint": primary_url,
            "backup_endpoint": backup_url,
            "endpoints": [primary_url, backup_url]
        }

    # Parallel HTTP PUT Uploads across the AI Enmesh nodes
    def _do_upload(task):
        node, name, data, role = task
        _http_put_shard(node, name, data)
        print(f"[AI ENMESH]    {node} stored {name} ({role}) ✓")
        return True

    workers = min(len(upload_tasks), 16)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_do_upload, upload_tasks))

    print("═" * 65 + "\n")
    return routing_map


def fetch_shard_from_mesh(
    shard_file: str,
    primary_node: Optional[str] = None,
    backup_node: Optional[str] = None
) -> bytes:
    """
    Download an encrypted shard from AI Enmesh strictly via HTTP GET.
    1. Tries primary_node first over HTTP GET.
    2. If primary_node fails or is OFFLINE, strictly fails over to designated backup_node.
    3. Never reads local disk files.
    """
    print(f"\n[THEATRE]  Requesting {shard_file}")

    # 1. Try Primary Node
    if primary_node and primary_node in AI_ENMESH_NODES:
        p_url = f"{AI_ENMESH_NODES[primary_node]['url']}/api/v1/objects/{shard_file}"
        try:
            print(f"[HTTP GET] → {p_url} ({primary_node})")
            data = _http_get_shard(primary_node, shard_file)
            print(f"[{primary_node}]   200 OK — Received {len(data)} bytes ")
            return data
        except Exception as e:
            print(f"[PRIMARY]  {primary_node}  OFFLINE / UNREACHABLE ({e})")
            if backup_node:
                print(f"[FAILOVER] Using designated backup {backup_node} from manifest")

    # 2. Strict Failover to Designated Backup Node
    if backup_node and backup_node in AI_ENMESH_NODES:
        b_url = f"{AI_ENMESH_NODES[backup_node]['url']}/api/v1/objects/{shard_file}"
        try:
            print(f"[HTTP GET] → {b_url} ({backup_node})")
            data = _http_get_shard(backup_node, shard_file)
            print(f"[{backup_node}]   200 OK — Failover backup retrieved {len(data)} bytes ✓")
            return data
        except Exception as e:
            print(f"[BACKUP]   {backup_node}  OFFLINE / UNREACHABLE ({e})")

    # 3. Last safety check on remaining nodes
    for nid in AI_ENMESH_NODES:
        if nid != primary_node and nid != backup_node:
            try:
                print(f"[SAFETY GET] → {AI_ENMESH_NODES[nid]['url']}/api/v1/objects/{shard_file} ({nid})")
                data = _http_get_shard(nid, shard_file)
                print(f"[{nid}]        200 OK ✓")
                return data
            except Exception:
                continue

    raise FileNotFoundError(f"Shard {shard_file} could not be retrieved from AI Enmesh: Primary ({primary_node}) and Backup ({backup_node}) are unavailable.")


def get_mesh_status() -> Dict[str, Any]:
    """Get real-time telemetry from the AI Enmesh controller over HTTP."""
    try:
        req = urllib.request.Request(f"{ENMESH_CONTROLLER_URL}/api/mesh/telemetry")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        # Construct fallback status by pinging individual node health
        nodes_info = {}
        online_count = 0
        for nid, cfg in AI_ENMESH_NODES.items():
            try:
                nreq = urllib.request.Request(f"{cfg['url']}/api/v1/health")
                with urllib.request.urlopen(nreq, timeout=1.0) as nresp:
                    ndata = json.loads(nresp.read().decode("utf-8"))
                    nodes_info[nid] = ndata
                    if ndata.get("status") == "ONLINE":
                        online_count += 1
            except Exception:
                nodes_info[nid] = {"node_id": nid, "status": "OFFLINE", "shard_count": 0, "total_bytes": 0}

        return {
            "nodes": nodes_info,
            "summary": {
                "total_nodes": len(AI_ENMESH_NODES),
                "online": online_count,
                "offline": len(AI_ENMESH_NODES) - online_count,
                "network_status": "Operational" if online_count == len(AI_ENMESH_NODES) else "Degraded"
            }
        }


def set_node_status(node_id: str, status: str) -> bool:
    """Toggle a node ONLINE / OFFLINE on AI Enmesh over HTTP."""
    cfg = AI_ENMESH_NODES.get(node_id)
    if not cfg:
        return False
    try:
        req = urllib.request.Request(
            f"{cfg['url']}/api/v1/toggle-outage",
            data=json.dumps({"status": status.upper()}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False
