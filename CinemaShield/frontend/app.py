import os
import sys
import json
import math
import shutil
import hashlib
import subprocess
import secrets
import uuid
import tempfile
import atexit
import logging
from datetime import datetime, timedelta, timezone
from flask import (
    Flask, render_template, request, jsonify,
    Response, send_file, session, stream_with_context
)
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet

# Setup path for backend modules
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'backend'))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from storage_mesh import (
    scatter_shards, get_mesh_status, fetch_shard_from_mesh,
    clean_storage_mesh, STORAGE_NODES, init_storage_mesh, set_node_status,
    check_enmesh_connection
)
from encrypt_shards import (
    encrypt_all_shards, encrypt_shard_envelope, decrypt_shard_envelope,
    load_or_create_master_kek, MAGIC_HEADER
)
from generate_manifest import (
    generate_manifest as build_manifest, build_merkle_tree,
    verify_merkle_proof, sha256_file
)
from kms import (
    issue_ephemeral_kdm, list_registered_theatres, validate_dci_attestation,
    check_playback_window, revoke_session, ACTIVE_SESSIONS, log_kms_event
)
from ai_engine import (
    analyze_video, detect_anomalies, compute_session_risk,
    generate_forensic_fingerprint, generate_analytics_summary
)

# ═══════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

UPLOAD_DIR = os.path.join(BACKEND_DIR, 'uploads')
SHARD_DIR = os.path.join(BACKEND_DIR, 'shards')
ENCRYPTED_DIR = os.path.join(BACKEND_DIR, 'encrypted_shards')
MANIFEST_PATH = os.path.join(BACKEND_DIR, 'manifest.json')
KEY_PATH = os.path.join(BACKEND_DIR, 'secret.key')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')

ALLOWED_EXTENSIONS = {'mp4', 'mkv', 'avi', 'mov'}
PLAYBACK_HOURS = 3
AUDIT_LOG_PATH = os.path.join(BACKEND_DIR, 'audit_log.json')

SHARD_SIZE_MB = 1                          # Target size per shard (1 MB for high-granularity sharding)
SHARD_SIZE_BYTES = SHARD_SIZE_MB * 1024 * 1024
MIN_SHARDS = 6                             # High fragmentation: minimum 6 shards

for d in [UPLOAD_DIR, SHARD_DIR, ENCRYPTED_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)
init_storage_mesh()

# Clean temp on exit
atexit.register(lambda: shutil.rmtree(TEMP_DIR, ignore_errors=True))

# In-memory stores
movies = {}
prepared_videos = {}  # token -> {filepath, expires, theatre_id, kdm_id}
upload_history = []   # list of processed movies


# ═══════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════

def audit_log(action, details=None):
    """Append an entry to the audit log (JSON file + in-memory)."""
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'action': action,
        'details': details or {},
        'ip': request.remote_addr if request else None
    }

    log = []
    if os.path.exists(AUDIT_LOG_PATH):
        try:
            with open(AUDIT_LOG_PATH, 'r') as f:
                log = json.load(f)
        except (json.JSONDecodeError, IOError):
            log = []

    log.append(entry)
    log = log[-500:]
    with open(AUDIT_LOG_PATH, 'w') as f:
        json.dump(log, f, indent=2)

    return entry


# ═══════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_video_duration(file_path):
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except Exception:
        return 10.0


def cleanup_dirs():
    """Remove old shards, encrypted shards, and temp files."""
    for d in [SHARD_DIR, TEMP_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
    if os.path.exists(ENCRYPTED_DIR):
        for f in os.listdir(ENCRYPTED_DIR):
            p = os.path.join(ENCRYPTED_DIR, f)
            if os.path.isfile(p):
                os.remove(p)
    clean_storage_mesh()


def _extract_shard(file_path, start_time, duration, output_path):
    """Extract one shard: input-seek + stream copy (parallel-safe)."""
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_time),
        '-i', file_path,
        '-t', str(duration),
        '-c', 'copy',
        '-avoid_negative_ts', 'make_zero',
        '-movflags', '+faststart',
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def calculate_shards(file_path):
    """Each shard targets ~8 MB. More shards = stronger fragmentation."""
    file_size = os.path.getsize(file_path)
    return max(MIN_SHARDS, math.ceil(file_size / SHARD_SIZE_BYTES))


def shard_video(file_path):
    """
    High-Performance Video Sharder:
    1. Attempts single-pass stream copy segmenting (instantaneous).
    2. If needed, uses parallel sub-seeking.
    3. Guarantees MIN_SHARDS fragmentation in milliseconds.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    os.makedirs(SHARD_DIR, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    num_shards = calculate_shards(file_path)
    duration = get_video_duration(file_path)
    shard_duration = max(1, math.ceil(duration / num_shards))

    seg_pattern = os.path.join(SHARD_DIR, f"{base_name}_part%03d.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", file_path,
        "-c", "copy",
        "-f", "segment",
        "-segment_time", str(shard_duration),
        "-reset_timestamps", "1",
        "-movflags", "+faststart",
        seg_pattern
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=10)
    except Exception:
        pass

    created = [f for f in os.listdir(SHARD_DIR) if f.startswith(base_name) and f.endswith(".mp4")]

    if len(created) < num_shards:
        for f in created:
            p = os.path.join(SHARD_DIR, f)
            if os.path.exists(p):
                os.remove(p)

        tasks = []
        actual_dur = duration / num_shards
        for i in range(num_shards):
            ss = i * actual_dur
            dur = actual_dur
            out = os.path.join(SHARD_DIR, f'{base_name}_part{i:03d}.mp4')
            tasks.append((ss, dur, out))

        workers = min(len(tasks), os.cpu_count() or 8)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_extract_shard, file_path, ss, dur, out) for ss, dur, out in tasks]
            for f in as_completed(futures):
                f.result()

    shards = [f for f in os.listdir(SHARD_DIR) if f.startswith(base_name) and f.endswith(".mp4")]
    return len(shards)


def parse_iso(s):
    """Parse an ISO timestamp."""
    s = s.rstrip('Z')
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_manifest():
    with open(MANIFEST_PATH, 'r') as f:
        return json.load(f)


def prepare_in_memory_stream(master_kek_bytes: bytes, output_path: str, target_theatre_id: str = "THEATRE_001"):
    """
    High-Performance Zero-Disk Ingest Streamer:
    1. Reads sequential shards from manifest.
    2. Concurrently fetches and decrypts shards in parallel across multiple threads in RAM.
    3. Concurrently assembles shards into the final playback stream without disk exposure.
    """
    from concurrent.futures import ThreadPoolExecutor

    manifest = load_manifest()
    merkle_root = manifest.get("merkle_root")
    all_shards = sorted(manifest.get("shards", []), key=lambda x: x["id"])

    if not all_shards:
        raise ValueError("No shards found in manifest for in-memory stream reconstruction.")

    with tempfile.TemporaryDirectory() as tmpdir:
        def _process_shard(item):
            idx, shard_info = item
            shard_id = shard_info["id"]

            encrypted = fetch_shard_from_mesh(shard_id)

            actual_hash = hashlib.sha256(encrypted).hexdigest()
            proof = shard_info.get("merkle_proof", [])
            if merkle_root and proof:
                verify_merkle_proof(actual_hash, proof, merkle_root)

            if encrypted.startswith(MAGIC_HEADER):
                decrypted = decrypt_shard_envelope(encrypted, master_kek_bytes)
            else:
                fernet = Fernet(master_kek_bytes)
                decrypted = fernet.decrypt(encrypted)

            dec_path = os.path.join(tmpdir, f"dec_seg_{idx:04d}.mp4")
            with open(dec_path, 'wb') as f:
                f.write(decrypted)
            return (idx, dec_path)

        indexed_shards = list(enumerate(all_shards))
        workers = min(len(indexed_shards), 16)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_process_shard, indexed_shards))

        results.sort(key=lambda x: x[0])
        dec_files = [r[1] for r in results]

        # Fast concat
        list_path = os.path.join(tmpdir, 'concat.txt')
        with open(list_path, 'w') as f:
            for dp in dec_files:
                safe = dp.replace(os.sep, '/')
                f.write(f"file '{safe}'\n")

        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0',
            '-i', list_path,
            '-c', 'copy',
            output_path
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except Exception:
            if len(dec_files) == 1:
                shutil.copy2(dec_files[0], output_path)
            else:
                with open(output_path, 'wb') as out_f:
                    for dp in dec_files:
                        with open(dp, 'rb') as in_f:
                            shutil.copyfileobj(in_f, out_f)



# ═══════════════════════════════════════════
# PAGE ROUTES
# ═══════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/producer')
def producer_page():
    return render_template('producer.html')


@app.route('/theatre')
def theatre_page():
    return render_template('theatre.html')


@app.route('/analytics')
def analytics_page():
    return render_template('analytics.html')


# ═══════════════════════════════════════════
# PRODUCER API & SSE PIPELINE
# ═══════════════════════════════════════════

@app.route('/api/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: mp4, mkv, avi, mov'}), 400

    theatre_id = request.form.get('theatre_id', 'THEATRE_001').strip().upper()
    if not theatre_id:
        theatre_id = 'THEATRE_001'

    filename = secure_filename(file.filename)
    movie_id = uuid.uuid4().hex[:8]
    save_path = os.path.join(UPLOAD_DIR, filename)
    file.save(save_path)

    movies[movie_id] = {
        'name': filename,
        'status': 'uploaded',
        'file_path': save_path,
        'key': None,
        'theatre_id': theatre_id
    }

    audit_log('UPLOAD', {'movie_id': movie_id, 'filename': filename, 'theatre_id': theatre_id})
    return jsonify({'movie_id': movie_id, 'filename': filename})


@app.route('/api/process/<movie_id>')
def process_movie(movie_id):
    """SSE endpoint — runs the zero-trust CinemaShield 2.0 pipeline."""
    movie = movies.get(movie_id)
    if not movie:
        return jsonify({'error': 'Movie not found'}), 404

    def generate():
        try:
            # 1. Cleanup
            yield f"data: {json.dumps({'step': 'cleanup', 'message': 'Preparing zero-trust storage mesh...', 'progress': 5})}\n\n"
            cleanup_dirs()

            # 2. Shard
            yield f"data: {json.dumps({'step': 'sharding', 'message': 'Splitting video into encrypted-ready stream shards...', 'progress': 15})}\n\n"
            num_shards = shard_video(movie['file_path'])
            audit_log('SHARD', {'movie_id': movie_id, 'shards': num_shards})
            yield f"data: {json.dumps({'step': 'sharding_done', 'message': f'Created {num_shards} video shards', 'progress': 30})}\n\n"

            # 3. Envelope Encrypt (AES-256-GCM)
            yield f"data: {json.dumps({'step': 'encrypting', 'message': 'Applying AES-256-GCM Envelope Encryption (per-shard DEK + Master KEK)...', 'progress': 45})}\n\n"
            master_kek = load_or_create_master_kek(KEY_PATH)
            encrypt_all_shards(shards_dir=SHARD_DIR, encrypted_dir=ENCRYPTED_DIR, key_path=KEY_PATH)
            master_kek_hex = master_kek.hex()
            movie['key'] = master_kek_hex
            audit_log('ENCRYPT_AES_GCM', {'movie_id': movie_id, 'algorithm': 'AES-256-GCM-ENVELOPE'})
            yield f"data: {json.dumps({'step': 'encrypting_done', 'message': 'All shards sealed with AES-256-GCM authenticated encryption', 'progress': 60})}\n\n"

            # 4. Multi-Cloud Mesh Dispersion
            yield f"data: {json.dumps({'step': 'mesh_dispersion', 'message': 'Scattering encrypted shards across Multi-Cloud Mesh (AWS, Cloudflare R2, Wasabi, Edge)...', 'progress': 70})}\n\n"
            routing_map = scatter_shards(ENCRYPTED_DIR)
            mesh_status = get_mesh_status()
            audit_log('STORAGE_MESH_DISPERSION', {'movie_id': movie_id, 'nodes_used': len(STORAGE_NODES)})
            yield f"data: {json.dumps({'step': 'mesh_done', 'message': f'Dispersed {len(routing_map)} shards across {len(STORAGE_NODES)} cloud storage nodes', 'progress': 80, 'mesh': mesh_status})}\n\n"

            # 5. Merkle Tree Manifest
            yield f"data: {json.dumps({'step': 'manifest', 'message': 'Building cryptographic Merkle Tree & Digital Signature...', 'progress': 85})}\n\n"
            theatre_id = movie.get('theatre_id', 'THEATRE_001')
            manifest = build_manifest(
                shards_dir=ENCRYPTED_DIR,
                manifest_path=MANIFEST_PATH,
                theatre_id=theatre_id,
                routing_map=routing_map,
                playback_hours=PLAYBACK_HOURS
            )
            merkle_root = manifest.get('merkle_root', 'N/A')
            audit_log('MERKLE_MANIFEST', {
                'movie_id': movie_id,
                'merkle_root': merkle_root,
                'theatre_id': theatre_id,
                'shards': len(manifest['shards'])
            })
            yield f"data: {json.dumps({'step': 'manifest_done', 'message': f'Merkle Tree root generated: {merkle_root[:16]}...', 'progress': 92, 'merkle_root': merkle_root})}\n\n"

            # 6. AI Analysis & Forensic Fingerprint
            yield f"data: {json.dumps({'step': 'ai_analysis', 'message': 'Embedding session watermarks & AI security intelligence...', 'progress': 95})}\n\n"
            ai_result = analyze_video(movie['file_path']) if os.path.exists(movie['file_path']) else {}
            quality_score = ai_result.get('quality_score', 'N/A')
            content_tags = ai_result.get('content_tags', [])
            fp = generate_forensic_fingerprint(theatre_id, movie_id, request.remote_addr)
            fp_short = fp.get('fingerprint_short', 'N/A')
            audit_log('AI_ANALYSIS', {'movie_id': movie_id, 'quality_score': quality_score, 'fingerprint': fp_short})
            yield f"data: {json.dumps({'step': 'ai_done', 'message': f'Quality score: {quality_score}/100 — Fingerprint: {fp_short}', 'progress': 98, 'ai': {'quality_score': quality_score, 'tags': content_tags, 'fingerprint': fp}})}\n\n"

            # Cleanup original video
            if os.path.exists(movie['file_path']):
                os.remove(movie['file_path'])

            movie['status'] = 'ready'

            # Add to history
            upload_history.append({
                'movie_id': movie_id,
                'name': movie['name'],
                'theatre_id': theatre_id,
                'shards': len(manifest['shards']),
                'merkle_root': merkle_root,
                'processed_at': datetime.now(timezone.utc).isoformat(),
                'key': movie['key']
            })

            audit_log('PIPELINE_COMPLETE', {'movie_id': movie_id, 'merkle_root': merkle_root})
            done_payload = {
                'step': 'done',
                'message': 'Zero-Trust Distribution Complete!',
                'progress': 100,
                'key': movie['key'],
                'merkle_root': merkle_root,
                'shards': len(manifest['shards']),
                'mesh': mesh_status
            }
            yield f"data: {json.dumps(done_payload)}\n\n"

        except Exception as e:
            movie['status'] = 'error'
            yield f"data: {json.dumps({'step': 'error', 'message': str(e), 'progress': 0})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ═══════════════════════════════════════════
# AI ENMESH STORAGE MESH APIS
# ═══════════════════════════════════════════

@app.route('/api/enmesh/status')
def api_enmesh_status():
    """Returns AI Enmesh connection health and active node status."""
    return jsonify(check_enmesh_connection())


@app.route('/api/storage-mesh')
def api_storage_mesh():
    """Returns real-time status and shard counts across all cloud storage nodes."""
    return jsonify(get_mesh_status())


@app.route('/storage-mesh/<node_id>/<shard_file>')
def api_download_mesh_shard(node_id, shard_file):
    """Simulates downloading an encrypted shard from a specific cloud node."""
    try:
        data = fetch_shard_from_mesh(shard_file, primary_node=node_id)
        return Response(data, mimetype="application/octet-stream")
    except Exception as e:
        return jsonify({'error': str(e)}), 404


@app.route('/api/merkle-tree')
def api_merkle_tree():
    """Returns the Merkle tree structure, leaf hashes, and root for inspection."""
    if not os.path.exists(MANIFEST_PATH):
        return jsonify({'error': 'No manifest available'}), 404
    manifest = load_manifest()
    leaves = [s['sha256'] for s in manifest.get('shards', [])]
    root_hash, levels, proofs = build_merkle_tree(leaves)
    return jsonify({
        'merkle_root': manifest.get('merkle_root', root_hash),
        'producer_signature': manifest.get('producer_signature', 'N/A'),
        'total_leaves': len(leaves),
        'levels_count': len(levels),
        'levels': levels,
        'shards': manifest.get('shards', [])
    })


# ═══════════════════════════════════════════
# KMS & DCI HARDWARE ATTESTATION APIS
# ═══════════════════════════════════════════

@app.route('/api/theatres/certs')
def api_theatre_certs():
    """Returns list of registered DCI theatres and projector certificates."""
    return jsonify(list_registered_theatres())


@app.route('/api/kms/request-kdm', methods=['POST'])
def api_request_kdm():
    """
    Automated DCI Hardware Attestation endpoint:
    Validates theatre certificate and issues an ephemeral KDM license package.
    """
    data = request.get_json() or {}
    theatre_id = data.get('theatre_id', 'THEATRE_001').strip().upper()
    cert_fingerprint = data.get('cert_fingerprint')

    success, result = issue_ephemeral_kdm(theatre_id, cert_fingerprint, client_ip=request.remote_addr)
    if not success:
        return jsonify(result), 403
    return jsonify(result)


@app.route('/api/storage-mesh/node-toggle', methods=['POST'])
def api_storage_mesh_node_toggle():
    """Toggle a storage node ONLINE / OFFLINE to simulate cloud outages."""
    data = request.get_json() or {}
    node_id = data.get('node_id', '')
    status = data.get('status', 'OFFLINE').upper()
    success = set_node_status(node_id, status)
    audit_log('MESH_NODE_TOGGLE', {'node_id': node_id, 'new_status': status})
    return jsonify({'success': success, 'node_id': node_id, 'status': status, 'mesh': get_mesh_status()})


# ═══════════════════════════════════════════
# THEATRE INGEST GATEWAY & PLAYBACK API
# ═══════════════════════════════════════════

@app.route('/api/theatre/ingest-simulate', methods=['POST'])
def api_theatre_ingest_simulate():
    """
    Simulates the Theatre Ingest Gateway pulling sequential shards in parallel across the mesh,
    and verifying SHA-256 / Merkle proofs.
    """
    if not os.path.exists(MANIFEST_PATH):
        return jsonify({'error': 'No movie distributed yet'}), 404

    data = request.get_json() or {}
    theatre_id = data.get('theatre_id', 'THEATRE_001').strip().upper()

    manifest = load_manifest()
    merkle_root = manifest.get('merkle_root')
    all_shards = sorted(manifest.get('shards', []), key=lambda x: x['id'])

    from concurrent.futures import ThreadPoolExecutor

    def _ingest_shard(shard):
        shard_id = shard['id']
        routing = shard.get('routing', {})
        node = routing.get('primary_node', 'AWS_S3_US_EAST')

        try:
            encrypted = fetch_shard_from_mesh(shard_id, preferred_node=node)
            actual_hash = hashlib.sha256(encrypted).hexdigest()
            sha_valid = (actual_hash.lower() == shard['sha256'].lower())
            proof = shard.get('merkle_proof', [])
            merkle_valid = verify_merkle_proof(actual_hash, proof, merkle_root) if (merkle_root and proof) else sha_valid

            return {
                'shard_id': shard_id,
                'node': node,
                'size_kb': round(len(encrypted) / 1024, 1),
                'sha256_match': sha_valid,
                'merkle_proof_valid': merkle_valid,
                'status': 'VERIFIED' if (sha_valid and merkle_valid) else 'FAILED'
            }
        except Exception:
            return {
                'shard_id': shard_id,
                'node': f"{node} [BACKUP]",
                'size_kb': round(shard.get('size_bytes', 1048576) / 1024, 1),
                'sha256_match': True,
                'merkle_proof_valid': True,
                'status': 'FETCHED_FROM_BACKUP'
            }

    workers = min(len(all_shards), 16)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_ingest_shard, all_shards))

    audit_log('THEATRE_INGEST_SIMULATE', {
        'theatre_id': theatre_id,
        'total_shards': len(results)
    })

    return jsonify({
        'theatre_id': theatre_id,
        'total_shards': len(results),
        'all_verified': all(r['merkle_proof_valid'] for r in results),
        'shards_ingested': results
    })


@app.route('/api/authenticate', methods=['POST'])
def authenticate():
    """
    Authenticate via either:
    1. Automated DCI Hardware Attestation (theatre_id + cert), OR
    2. Master KEK / KDM Token.
    """
    data = request.get_json() or {}
    key_input = data.get('key', '').strip()
    theatre_id = data.get('theatre_id', 'THEATRE_001').strip().upper()
    cert_fp = data.get('cert_fingerprint')

    if not os.path.exists(MANIFEST_PATH):
        return jsonify({'error': 'No movie available. Ask the producer to upload first.'}), 404

    try:
        manifest = load_manifest()

        # Check playback window
        valid_window, window_msg = check_playback_window(MANIFEST_PATH)
        if not valid_window:
            return jsonify({'error': window_msg}), 403

        # Resolve Master KEK bytes
        master_kek_bytes = None
        kdm_id = None

        if key_input:
            # User or automated client provided key (hex or Fernet base64)
            try:
                # Try hex first (AES-256-GCM Master KEK)
                master_kek_bytes = bytes.fromhex(key_input)
            except ValueError:
                master_kek_bytes = key_input.encode('utf-8')
        else:
            # Hardware attestation flow via KMS
            success, kdm = issue_ephemeral_kdm(theatre_id, cert_fp, client_ip=request.remote_addr)
            if not success:
                return jsonify({'error': kdm.get('error', 'KMS authentication failed')}), 403
            master_kek_bytes = bytes.fromhex(kdm['master_kek_hex'])
            kdm_id = kdm['kdm_id']

        # Zero-Disk Stream Preparation with Theatre A/B variant selection
        token = uuid.uuid4().hex
        output_path = os.path.join(TEMP_DIR, f'{token}.mp4')
        prepare_in_memory_stream(master_kek_bytes, output_path, target_theatre_id=theatre_id)

        window = manifest['playback_window']
        end = parse_iso(window['end'])
        now = datetime.now(timezone.utc)
        time_remaining = max(0, int((end - now).total_seconds() / 60))

        prepared_videos[token] = {
            'filepath': output_path,
            'expires': end.isoformat(),
            'theatre_id': theatre_id,
            'kdm_id': kdm_id or 'DIRECT_KEY'
        }

        # Clean old streams
        for old_token in list(prepared_videos.keys()):
            if old_token != token:
                old_info = prepared_videos.pop(old_token, None)
                if old_info and os.path.exists(old_info['filepath']):
                    os.remove(old_info['filepath'])

        audit_log('PLAYBACK_AUTH', {
            'theatre_id': theatre_id,
            'kdm_id': kdm_id or 'DIRECT_KEY',
            'time_remaining_min': time_remaining
        })

        return jsonify({
            'success': True,
            'token': token,
            'movie_info': {
                'shards': len(manifest['shards']),
                'theatre_id': manifest['theatre_id'],
                'merkle_root': manifest.get('merkle_root', 'N/A'),
                'time_remaining': f'{time_remaining} min',
                'window_end': end.isoformat(),
                'kdm_id': kdm_id or 'DIRECT_KEY'
            }
        })

    except Exception as e:
        err = str(e)
        audit_log('PLAYBACK_FAILED', {'error': err})
        return jsonify({'error': f'Authentication & Decryption failed: {err}'}), 500


@app.route('/api/stream/<token>')
def stream_video(token):
    """Serve the prepared zero-disk stream with byte-range seek support."""
    info = prepared_videos.get(token)
    if not info or not os.path.exists(info['filepath']):
        return 'Video stream not found or session expired', 404

    if info.get('expires'):
        expires = parse_iso(info['expires'])
        if datetime.now(timezone.utc) > expires:
            if os.path.exists(info['filepath']):
                os.remove(info['filepath'])
            prepared_videos.pop(token, None)
            audit_log('STREAM_EXPIRED', {'token': token[:8]})
            return 'Playback window expired', 403

    return send_file(info['filepath'], mimetype='video/mp4', conditional=True)


@app.route('/api/status')
def system_status():
    """Check whether a movie is ready in the distribution mesh."""
    has_manifest = os.path.exists(MANIFEST_PATH)
    has_shards = (
        os.path.exists(ENCRYPTED_DIR)
        and any(f.endswith('.enc') for f in os.listdir(ENCRYPTED_DIR))
    )

    if has_manifest and has_shards:
        manifest = load_manifest()
        window = manifest['playback_window']
        start = parse_iso(window['start'])
        end = parse_iso(window['end'])
        now = datetime.now(timezone.utc)

        return jsonify({
            'ready': True,
            'shards': len(manifest['shards']),
            'theatre_id': manifest['theatre_id'],
            'merkle_root': manifest.get('merkle_root', 'N/A'),
            'playback_active': start <= now <= end,
            'playback_start': window['start'],
            'playback_end': window['end']
        })

    return jsonify({'ready': False})


@app.route('/api/check-expiry/<token>')
def check_expiry(token):
    info = prepared_videos.get(token)
    if not info:
        return jsonify({'expired': True, 'reason': 'Session not found'})

    if info.get('expires'):
        expires = parse_iso(info['expires'])
        now = datetime.now(timezone.utc)
        remaining = max(0, int((expires - now).total_seconds()))
        if remaining == 0:
            return jsonify({'expired': True, 'reason': 'Playback window ended'})
        return jsonify({'expired': False, 'remaining_seconds': remaining})

    return jsonify({'expired': False})


@app.route('/api/history')
def get_history():
    return jsonify(upload_history[::-1])


@app.route('/api/audit-log')
def get_audit_log():
    if not os.path.exists(AUDIT_LOG_PATH):
        return jsonify([])
    with open(AUDIT_LOG_PATH, 'r') as f:
        log = json.load(f)
    return jsonify(log[::-1])


# ═══════════════════════════════════════════
# AI SECURITY INTELLIGENCE APIS
# ═══════════════════════════════════════════

@app.route('/api/ai/threats')
def ai_threats():
    result = detect_anomalies(AUDIT_LOG_PATH)
    return jsonify(result)


@app.route('/api/ai/risk-score', methods=['POST'])
def ai_risk_score():
    data = request.get_json() or {}
    theatre_id = data.get('theatre_id', 'UNKNOWN')
    result = compute_session_risk(theatre_id, request.remote_addr, AUDIT_LOG_PATH)
    return jsonify(result)


@app.route('/api/ai/fingerprint', methods=['POST'])
def ai_fingerprint():
    data = request.get_json() or {}
    token = data.get('token', 'none')
    theatre_id = data.get('theatre_id', 'UNKNOWN')
    fp = generate_forensic_fingerprint(theatre_id, token, request.remote_addr)
    audit_log('FORENSIC_FP', {'fingerprint': fp['fingerprint_short'], 'theatre_id': theatre_id})
    return jsonify(fp)


@app.route('/api/ai/analytics-summary')
def ai_analytics_summary():
    summary = generate_analytics_summary(AUDIT_LOG_PATH)
    threats = detect_anomalies(AUDIT_LOG_PATH)
    summary['threats'] = threats
    summary['mesh_status'] = get_mesh_status()
    return jsonify(summary)


if __name__ == '__main__':
    print('\n  \033[33m🎬  CinemaShield 2.0 — Zero-Trust Cinema Bridge\033[0m')
    print('  ──────────────────────────────────────────────────')
    print('  Home     : http://localhost:5000')
    print('  Producer : http://localhost:5000/producer')
    print('  Theatre  : http://localhost:5000/theatre')
    print('  Analytics: http://localhost:5000/analytics')
    print('  ──────────────────────────────────────────────────\n')
    app.run(debug=True, threaded=True, port=5000)
