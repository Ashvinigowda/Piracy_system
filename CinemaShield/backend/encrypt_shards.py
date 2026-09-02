import os
import sys
import time
import json
import secrets
import struct
from typing import List, Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# -----------------------------
# CONFIG
# -----------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SHARDS_FOLDER = os.path.join(BACKEND_DIR, "shards")
ENCRYPTED_FOLDER = os.path.join(BACKEND_DIR, "encrypted_shards")
KEY_FILE = os.path.join(BACKEND_DIR, "secret.key")

MAGIC_HEADER = b"CSGCM1"  # CinemaShield AES-256-GCM envelope format version 1

os.makedirs(ENCRYPTED_FOLDER, exist_ok=True)


def normalize_key_bytes(raw_key: bytes) -> bytes:
    """Normalize arbitrary key input (hex, base64, raw) to 32-byte AESGCM key."""
    if len(raw_key) == 32:
        return raw_key
    if len(raw_key) == 64:
        try:
            return bytes.fromhex(raw_key.decode('ascii'))
        except Exception:
            pass
    if len(raw_key) == 44:
        try:
            import base64
            decoded = base64.urlsafe_b64decode(raw_key)
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass
    import hashlib
    return hashlib.sha256(raw_key).digest()


def generate_master_kek() -> bytes:
    """Generate a cryptographically secure 256-bit Master Key Encryption Key (KEK)."""
    return AESGCM.generate_key(bit_length=256)


def load_or_create_master_kek(key_path: str = KEY_FILE) -> bytes:
    """Load existing master KEK or create a new 256-bit key."""
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            raw = f.read()
        return normalize_key_bytes(raw)
    key = generate_master_kek()
    with open(key_path, "wb") as f:
        f.write(key)
    return key


def encrypt_shard_envelope(plaintext_data: bytes, master_kek: bytes) -> bytes:
    """
    Envelope Encryption using AES-256-GCM:
    1. Generate ephemeral 256-bit Data Encryption Key (DEK).
    2. Encrypt plaintext payload with DEK using AES-GCM (12-byte IV, 16-byte tag).
    3. Encrypt the DEK with the Master KEK using AES-GCM.
    4. Package: MAGIC(6) | IV_DEK(12) | ENC_DEK_LEN(2) | ENC_DEK | IV_DATA(12) | CIPHERTEXT+TAG
    """
    master_kek = normalize_key_bytes(master_kek)
    # 1. Generate unique DEK & data IV
    dek = AESGCM.generate_key(bit_length=256)
    aesgcm_dek = AESGCM(dek)
    data_iv = secrets.token_bytes(12)
    data_ciphertext = aesgcm_dek.encrypt(data_iv, plaintext_data, None)

    # 2. Encrypt DEK under master KEK
    aesgcm_kek = AESGCM(master_kek)
    dek_iv = secrets.token_bytes(12)
    enc_dek = aesgcm_kek.encrypt(dek_iv, dek, None)

    # 3. Pack envelope format
    header = struct.pack(">6s12sH", MAGIC_HEADER, dek_iv, len(enc_dek))
    envelope = header + enc_dek + data_iv + data_ciphertext
    return envelope


def decrypt_shard_envelope(encrypted_data: bytes, master_kek: bytes) -> bytes:
    """
    Decrypt envelope encrypted payload:
    1. Parse header and extract encrypted DEK and IVs.
    2. Decrypt DEK using Master KEK.
    3. Decrypt ciphertext payload using DEK.
    """
    master_kek = normalize_key_bytes(master_kek)
    if len(encrypted_data) < 32:
        raise ValueError("Invalid encrypted payload: too short")

    magic = encrypted_data[:6]
    if magic != MAGIC_HEADER:
        raise ValueError("Invalid header magic: not a CinemaShield AES-256-GCM envelope")

    dek_iv = encrypted_data[6:18]
    enc_dek_len = struct.unpack(">H", encrypted_data[18:20])[0]
    
    offset = 20
    enc_dek = encrypted_data[offset:offset + enc_dek_len]
    offset += enc_dek_len

    data_iv = encrypted_data[offset:offset + 12]
    offset += 12

    data_ciphertext = encrypted_data[offset:]

    # Decrypt DEK
    aesgcm_kek = AESGCM(master_kek)
    dek = aesgcm_kek.decrypt(dek_iv, enc_dek, None)

    # Decrypt Data
    aesgcm_dek = AESGCM(dek)
    plaintext = aesgcm_dek.decrypt(data_iv, data_ciphertext, None)
    return plaintext


def _encrypt_one(shard_file: str, shards_dir: str, encrypted_dir: str, master_kek: bytes):
    """Read, envelope encrypt with AES-256-GCM, write .enc, and delete plaintext shard."""
    shard_path = os.path.join(shards_dir, shard_file)
    with open(shard_path, "rb") as f:
        data = f.read()

    encrypted_data = encrypt_shard_envelope(data, master_kek)

    encrypted_path = os.path.join(encrypted_dir, shard_file + ".enc")
    with open(encrypted_path, "wb") as f:
        f.write(encrypted_data)

    os.remove(shard_path)
    return shard_file


def encrypt_all_shards(
    shards_dir: str = SHARDS_FOLDER,
    encrypted_dir: str = ENCRYPTED_FOLDER,
    key_path: str = KEY_FILE
) -> Dict[str, Any]:
    """
    Reads plaintext shards and envelope-encrypts each 1:1 with AES-256-GCM.
    Each shard receives a unique ephemeral DEK, sealed under the Master KEK.
    """
    os.makedirs(encrypted_dir, exist_ok=True)
    master_kek = load_or_create_master_kek(key_path)

    shard_files = sorted([
        f for f in os.listdir(shards_dir)
        if os.path.isfile(os.path.join(shards_dir, f)) and f.endswith(".mp4")
    ])
    if not shard_files:
        print("No shards found to encrypt!")
        return {"processed": [], "data_count": 0}

    print(f" Encrypting {len(shard_files)} sequential shard(s) with AES-256-GCM Envelope Encryption...")
    start = time.perf_counter()

    workers = min(len(shard_files), os.cpu_count() or 8)
    processed = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_encrypt_one, s, shards_dir, encrypted_dir, master_kek): s for s in shard_files}
        for future in as_completed(futures):
            name = future.result()
            processed.append(name)

    elapsed = time.perf_counter() - start
    print(f" All {len(processed)} sequential shards sealed with AES-256-GCM in {elapsed:.3f}s")
    
    return {
        "processed": sorted(processed),
        "data_count": len(processed)
    }


if __name__ == "__main__":
    encrypt_all_shards()
