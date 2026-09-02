"""
AI Enmesh — Autonomous HTTP Object Storage Server for Mesh Nodes
Each node runs on an independent port (8001-8005) with isolated storage.
"""

import os
import sys
import time
import json
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse


class MeshNodeHandler(BaseHTTPRequestHandler):
    """
    HTTP REST handler for individual AI Enmesh storage nodes.
    Supports S3-style object storage (PUT, GET, DELETE), health checks, and outage simulation.
    """

    def _send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, PUT, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Amz-Content-Sha256, Authorization, Range')

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Health & Telemetry Endpoint
        if path == '/api/v1/health' or path == '/health':
            status = getattr(self.server, 'node_status', 'ONLINE')
            if status == 'OFFLINE':
                self.send_response(503)
                self._send_cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'node_id': self.server.node_id,
                    'status': 'OFFLINE',
                    'error': 'Service Unavailable: Node is OFFLINE'
                }).encode('utf-8'))
                return

            storage_dir = self.server.storage_dir
            objects = os.listdir(storage_dir) if os.path.exists(storage_dir) else []
            files = [f for f in objects if os.path.isfile(os.path.join(storage_dir, f))]
            total_size = sum(os.path.getsize(os.path.join(storage_dir, f)) for f in files)

            self.send_response(200)
            self._send_cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'node_id': self.server.node_id,
                'port': self.server.server_port,
                'status': status,
                'latency_ms': getattr(self.server, 'simulated_latency_ms', 10),
                'object_count': len(files),
                'total_bytes': total_size,
                'uptime_seconds': int(time.time() - self.server.start_time),
                'objects': files
            }).encode('utf-8'))
            return

        # Check offline status for object requests
        if getattr(self.server, 'node_status', 'ONLINE') == 'OFFLINE':
            self.send_response(503)
            self._send_cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'error': f'Node {self.server.node_id} is OFFLINE'
            }).encode('utf-8'))
            return

        # Object Retrieval: /api/v1/objects/<key>
        if path.startswith('/api/v1/objects/'):
            key = path[len('/api/v1/objects/'):]
            file_path = os.path.join(self.server.storage_dir, key)

            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                self.send_response(404)
                self._send_cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': f'Object {key} not found on node {self.server.node_id}'}).encode('utf-8'))
                return

            with open(file_path, 'rb') as f:
                data = f.read()

            sha256_hash = hashlib.sha256(data).hexdigest()

            self.send_response(200)
            self._send_cors()
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('ETag', f'"{sha256_hash}"')
            self.send_header('X-Node-Id', self.server.node_id)
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(404)
        self._send_cors()
        self.end_headers()

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if getattr(self.server, 'node_status', 'ONLINE') == 'OFFLINE':
            self.send_response(503)
            self._send_cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': f'Node {self.server.node_id} is OFFLINE'}).encode('utf-8'))
            return

        if path.startswith('/api/v1/objects/'):
            key = path[len('/api/v1/objects/'):]
            content_length = int(self.headers.get('Content-Length', 0))
            payload = self.rfile.read(content_length)

            file_path = os.path.join(self.server.storage_dir, key)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'wb') as f:
                f.write(payload)

            sha256_hash = hashlib.sha256(payload).hexdigest()

            self.send_response(201)
            self._send_cors()
            self.send_header('Content-Type', 'application/json')
            self.send_header('ETag', f'"{sha256_hash}"')
            self.send_header('X-Node-Id', self.server.node_id)
            self.end_headers()
            self.wfile.write(json.dumps({
                'stored': True,
                'key': key,
                'node_id': self.server.node_id,
                'bytes': len(payload),
                'sha256': sha256_hash
            }).encode('utf-8'))
            return

        self.send_response(400)
        self._send_cors()
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Toggle Outage Endpoint
        if path == '/api/v1/toggle-outage':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
            data = json.loads(body) if body else {}

            new_status = data.get('status', 'ONLINE').upper()
            if new_status in ['ONLINE', 'OFFLINE', 'DEGRADED']:
                self.server.node_status = new_status

            self.send_response(200)
            self._send_cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'node_id': self.server.node_id,
                'status': self.server.node_status
            }).encode('utf-8'))
            return

        self.send_response(404)
        self._send_cors()
        self.end_headers()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/v1/objects/'):
            key = path[len('/api/v1/objects/'):]
            file_path = os.path.join(self.server.storage_dir, key)

            if os.path.exists(file_path):
                os.remove(file_path)
                self.send_response(204)
            else:
                self.send_response(404)
            self._send_cors()
            self.end_headers()
            return

        self.send_response(400)
        self._send_cors()
        self.end_headers()

    def log_message(self, format, *args):
        pass


def create_node_server(node_id: str, port: int, storage_dir: str, latency_ms: int = 10) -> HTTPServer:
    os.makedirs(storage_dir, exist_ok=True)
    server = HTTPServer(('0.0.0.0', port), MeshNodeHandler)
    server.node_id = node_id
    server.storage_dir = storage_dir
    server.simulated_latency_ms = latency_ms
    server.node_status = 'ONLINE'
    server.start_time = time.time()
    return server
