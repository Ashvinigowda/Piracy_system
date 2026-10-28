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
    Return key bytes only after successful KMS authorization.
    Never fall back to reading the master key file directly.
    """
    success, kdm = request_kdm_license(theatre_id)

    if not success:
        raise PermissionError("KMS authorization failed; key not issued.")

    key_hex = kdm.get("_master_kek_hex")
    if not isinstance(key_hex, str) or not key_hex:
        raise PermissionError("KMS response did not contain an authorized key.")

    try:
        return bytes.fromhex(key_hex)
    except ValueError as exc:
        raise PermissionError("KMS returned an invalid key encoding.") from exc
