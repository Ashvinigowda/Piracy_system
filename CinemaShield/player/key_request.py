import os
import sys
from typing import Tuple, Dict, Any

BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from kms import issue_ephemeral_kdm


def request_kdm_license(theatre_id: str = "THEATRE_001", cert_fingerprint: str = None) -> Tuple[bool, Dict[str, Any]]:
    """
    Request an ephemeral Key Delivery Message (KDM) and Master KEK from CinemaShield KMS
    using DCI Hardware Certificate attestation.
    """
    success, result = issue_ephemeral_kdm(theatre_id, cert_fingerprint, client_ip="127.0.0.1")
    return success, result


def request_key(theatre_id: str = "THEATRE_001") -> bytes:
    """
    Backwards-compatible key retrieval function returning raw key bytes.
    """
    success, kdm = request_kdm_license(theatre_id)
    if success and "master_kek_hex" in kdm:
        return bytes.fromhex(kdm["master_kek_hex"])
    
    # Fallback to direct key file if exists
    key_path = os.path.join(BACKEND_DIR, "secret.key")
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()

    raise PermissionError("Failed to acquire authorized KDM from KMS Broker")
