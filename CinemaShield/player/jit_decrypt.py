import os
import sys

# Add backend to path for shared crypto
BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from encrypt_shards import decrypt_shard_envelope, MAGIC_HEADER
from cryptography.fernet import Fernet


def decrypt_shard(encrypted_data: bytes, key_bytes: bytes) -> bytes:
    """
    JIT In-Memory Decryption:
    Handles both AES-256-GCM Envelope Encryption (CinemaShield 2.0)
    and legacy Fernet formats for backwards compatibility.
    Data exists strictly in RAM and is never written to disk.
    """
    if encrypted_data.startswith(MAGIC_HEADER):
        return decrypt_shard_envelope(encrypted_data, key_bytes)
    else:
        # Fallback to Fernet if legacy format
        fernet = Fernet(key_bytes)
        return fernet.decrypt(encrypted_data)
