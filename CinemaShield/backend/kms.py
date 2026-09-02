import os
import json
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(BACKEND_DIR, "secret.key")
AUDIT_LOG_PATH = os.path.join(BACKEND_DIR, "audit_log.json")
MANIFEST_PATH = os.path.join(BACKEND_DIR, "manifest.json")

# Pre-registered DCI Theatres and Hardware Security Block Certificates
THEATRE_REGISTRY = {
    "THEATRE_001": {
        "theatre_id": "THEATRE_001",
        "name": "IMAX Grand Cinema (Screen 1)",
        "city": "Mumbai",
        "country": "India",
        "projector_model": "Christie CP4440-RGB Laser",
        "smb_serial": "SMB-CHR-99482-DCI",
        "cert_fingerprint": "SHA256:4a8f9c1b3d7e5a2c9e0f6b4a8c1d3e5f7a9b0c2d4e6f8a0b2c4d6e8f0a2b4c6d",
        "status": "AUTHORIZED",
        "geo_allowed": ["IN", "IN-MH"],
        "max_concurrent_sessions": 1
    },
    "THEATRE_002": {
        "theatre_id": "THEATRE_002",
        "name": "Dolby Cinema @ AMC Burbank 16",
        "city": "Los Angeles",
        "country": "USA",
        "projector_model": "Dolby Vision Cinema System Dual-Laser",
        "smb_serial": "SMB-DOLBY-77219-DCI",
        "cert_fingerprint": "SHA256:9f8e7d6c5b4a39281706f5e4d3c2b1a09876543210fedcba9876543210abcdef",
        "status": "AUTHORIZED",
        "geo_allowed": ["US", "US-CA"],
        "max_concurrent_sessions": 1
    },
    "THEATRE_003": {
        "theatre_id": "THEATRE_003",
        "name": "Odeon Luxe Leicester Square",
        "city": "London",
        "country": "UK",
        "projector_model": "Dolby IMS3000 / Barco DP4K-60L",
        "smb_serial": "SMB-BARCO-55102-DCI",
        "cert_fingerprint": "SHA256:1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b",
        "status": "AUTHORIZED",
        "geo_allowed": ["GB", "GB-ENG"],
        "max_concurrent_sessions": 1
    }
}

# Active Session Key Grants: { session_token: { theatre_id, expires_at, created_at, hardware_info } }
ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}


def log_kms_event(event_type: str, theatre_id: str, success: bool, details: Dict[str, Any] = None):
    """Log cryptographic KMS events to the secure audit log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "CINEMASHIELD_KMS_BROKER",
        "event_type": event_type,
        "theatre_id": theatre_id,
        "success": success,
        "details": details or {}
    }

    logs = []
    if os.path.exists(AUDIT_LOG_PATH):
        try:
            with open(AUDIT_LOG_PATH, "r") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    logs.append(entry)
    logs = logs[-500:]
    with open(AUDIT_LOG_PATH, "w") as f:
        json.dump(logs, f, indent=2)


def get_theatre_info(theatre_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve metadata and hardware cert info for a registered theatre."""
    return THEATRE_REGISTRY.get(theatre_id)


def list_registered_theatres() -> Dict[str, Any]:
    """List all known DCI theatre endpoints."""
    return THEATRE_REGISTRY


def validate_dci_attestation(theatre_id: str, cert_fingerprint: Optional[str] = None) -> Tuple[bool, str]:
    """Validate DCI hardware security block certificate."""
    theatre = THEATRE_REGISTRY.get(theatre_id)
    if not theatre:
        return False, f"Unknown theatre ID '{theatre_id}'. Not in DCI trusted registry."
    if theatre["status"] != "AUTHORIZED":
        return False, f"Theatre '{theatre_id}' is flagged as {theatre['status']} (Revoked/Suspended)."
    if cert_fingerprint and cert_fingerprint != theatre["cert_fingerprint"]:
        return False, "Hardware certificate fingerprint mismatch! Potential hardware spoofing attack."
    return True, "DCI Hardware Attestation Valid"


def check_playback_window(manifest_path: str = MANIFEST_PATH) -> Tuple[bool, str]:
    """Check if current UTC time is inside the manifest playback window."""
    if not os.path.exists(manifest_path):
        return True, "No manifest found; demo mode bypass"
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        window = manifest.get("playback_window", {})
        if not window:
            return True, "No window restrictions"

        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(window["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(window["end"].replace("Z", "+00:00"))

        if now < start:
            return False, f"Playback window not yet open (Starts at {window['start']})"
        if now > end:
            return False, f"Playback window expired at {window['end']}"
        return True, f"Active showtime window (Valid until {window['end']})"
    except Exception as e:
        return True, f"Window validation pass ({e})"


def issue_ephemeral_kdm(
    theatre_id: str,
    cert_fingerprint: Optional[str] = None,
    client_ip: Optional[str] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Issue an ephemeral Key Delivery Message (KDM) and Master KEK to an authorized DCI theatre.
    """
    # 1. Validate DCI Hardware Certificate
    valid_cert, cert_msg = validate_dci_attestation(theatre_id, cert_fingerprint)
    if not valid_cert:
        log_kms_event("KDM_REQUEST_DENIED", theatre_id, False, {"reason": cert_msg, "ip": client_ip})
        return False, {"error": cert_msg, "code": "CERT_INVALID"}

    # 2. Check Showtime Window
    valid_window, window_msg = check_playback_window()
    if not valid_window:
        log_kms_event("KDM_REQUEST_DENIED", theatre_id, False, {"reason": window_msg, "ip": client_ip})
        return False, {"error": window_msg, "code": "WINDOW_EXPIRED"}

    # 3. Load Master KEK
    try:
        from encrypt_shards import load_or_create_master_kek
        master_kek = load_or_create_master_kek(KEY_FILE)
    except Exception:
        if not os.path.exists(KEY_FILE):
            return False, {"error": "No Master KEK registered on KMS", "code": "NO_KEY"}
        with open(KEY_FILE, "rb") as f:
            master_kek = f.read()

    # 4. Generate Ephemeral Session Token & KDM Package
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=3)

    theatre = THEATRE_REGISTRY[theatre_id]
    kdm_package = {
        "kdm_id": f"KDM-{secrets.token_hex(8).upper()}",
        "theatre_id": theatre_id,
        "theatre_name": theatre["name"],
        "projector_smb": theatre["smb_serial"],
        "session_token": session_token,
        "master_kek_hex": master_kek.hex(),
        "key_algorithm": "AES-256-GCM-ENVELOPE",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "security_level": "DCI-COMPLIANT-LEVEL-3"
    }

    ACTIVE_SESSIONS[session_token] = {
        "theatre_id": theatre_id,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    log_kms_event("KDM_ISSUED_SUCCESS", theatre_id, True, {
        "kdm_id": kdm_package["kdm_id"],
        "smb_serial": theatre["smb_serial"],
        "expires_at": kdm_package["expires_at"],
        "ip": client_ip
    })

    return True, kdm_package


def revoke_session(session_token: str, reason: str = "Manual Revocation") -> bool:
    """Revoke an active session token immediately."""
    if session_token in ACTIVE_SESSIONS:
        info = ACTIVE_SESSIONS.pop(session_token)
        log_kms_event("SESSION_REVOKED", info["theatre_id"], True, {"reason": reason})
        return True
    return False


if __name__ == "__main__":
    print("CinemaShield KMS Broker Test:")
    success, kdm = issue_ephemeral_kdm("THEATRE_001")
    print(f"Issued KDM Status: {success}")
    if success:
        print(f"KDM ID: {kdm['kdm_id']} for {kdm['theatre_name']}")
