import os
import sys
import hashlib
import hmac
import struct
import json
from typing import List, Dict, Any, Tuple, Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

MAGIC_WATERMARK_A = b"CS_WATERMARK_VARIANT_A_TAG0"
MAGIC_WATERMARK_B = b"CS_WATERMARK_VARIANT_B_TAG1"


def generate_theatre_ab_sequence(theatre_id: str, total_shards: int, seed_salt: str = "CINEMASHIELD_2026") -> List[str]:
    """
    Generates a deterministic, unique binary A/B sequence for a specific theatre.
    Uses HMAC-SHA256 expansion so that every theatre receives a unique combination.
    """
    key = f"{seed_salt}:{theatre_id}".encode('utf-8')
    h = hmac.new(key, b"SHARD_AB_COMBINATION", hashlib.sha256).digest()
    
    # Expand digest bits to total_shards
    sequence = []
    bit_index = 0
    for i in range(total_shards):
        byte_pos = (bit_index // 8) % len(h)
        bit_pos = bit_index % 8
        bit = (h[byte_pos] >> bit_pos) & 1
        sequence.append("B" if bit == 1 else "A")
        bit_index += 1

    return sequence


def embed_steganographic_tag(payload_bytes: bytes, variant: str, shard_index: int, theatre_id: str = "") -> bytes:
    """
    Embeds an imperceptible forensic metadata tag into the shard container.
    Injects a custom zero-overhead MP4 user-data tag or footer trailer.
    """
    tag_magic = MAGIC_WATERMARK_A if variant == "A" else MAGIC_WATERMARK_B
    meta = f"CS_FP:{variant}:IDX_{shard_index:03d}:{theatre_id}".encode('utf-8')
    trailer = tag_magic + struct.pack(">H", len(meta)) + meta
    return payload_bytes + trailer


def extract_steganographic_tag(shard_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Extracts the embedded forensic tag from a shard or video frame buffer.
    """
    if MAGIC_WATERMARK_A in shard_bytes:
        pos = shard_bytes.rfind(MAGIC_WATERMARK_A)
        variant = "A"
        tag_len = len(MAGIC_WATERMARK_A)
    elif MAGIC_WATERMARK_B in shard_bytes:
        pos = shard_bytes.rfind(MAGIC_WATERMARK_B)
        variant = "B"
        tag_len = len(MAGIC_WATERMARK_B)
    else:
        return None

    try:
        offset = pos + tag_len
        meta_len = struct.unpack(">H", shard_bytes[offset:offset+2])[0]
        meta_str = shard_bytes[offset+2:offset+2+meta_len].decode('utf-8', errors='ignore')
        parts = meta_str.split(":")
        return {
            "variant": variant,
            "shard_index": parts[2] if len(parts) > 2 else "UNKNOWN",
            "theatre_id": parts[3] if len(parts) > 3 else "UNKNOWN",
            "raw_meta": meta_str
        }
    except Exception:
        return {"variant": variant, "raw_meta": "PARSING_ERROR"}


def create_ab_shard_pair(shard_file: str, shards_dir: str, out_dir: str, shard_index: int) -> Tuple[str, str]:
    """
    Takes a single video shard and produces both Variant A and Variant B in out_dir.
    Returns: (variant_a_filename, variant_b_filename)
    """
    os.makedirs(out_dir, exist_ok=True)
    src_path = os.path.join(shards_dir, shard_file)
    with open(src_path, "rb") as f:
        data = f.read()

    base_name = os.path.splitext(shard_file)[0]

    # Generate Variant A
    data_a = embed_steganographic_tag(data, "A", shard_index)
    file_a = f"{base_name}_varA.mp4"
    path_a = os.path.join(out_dir, file_a)
    with open(path_a, "wb") as f:
        f.write(data_a)

    # Generate Variant B
    data_b = embed_steganographic_tag(data, "B", shard_index)
    file_b = f"{base_name}_varB.mp4"
    path_b = os.path.join(out_dir, file_b)
    with open(path_b, "wb") as f:
        f.write(data_b)

    return file_a, file_b


def trace_leaked_fingerprint(
    observed_sequence: List[str],
    registered_theatres: List[str],
    total_shards: int
) -> Dict[str, Any]:
    """
    Reverse-lookup forensic tracer:
    Compares an extracted/observed A/B sequence against all registered theatres.
    Calculates exact Hamming distance and confidence score to pinpoint the leaking theatre.
    """
    if not observed_sequence:
        return {"matched": False, "reason": "Empty observed sequence"}

    best_match = None
    best_score = -1
    all_scores = []

    for tid in registered_theatres:
        theatre_seq = generate_theatre_ab_sequence(tid, total_shards)
        # Compare overlapping length
        compare_len = min(len(observed_sequence), len(theatre_seq))
        matches = sum(1 for i in range(compare_len) if observed_sequence[i] == theatre_seq[i])
        pct = round((matches / compare_len) * 100, 1) if compare_len > 0 else 0

        score_info = {
            "theatre_id": tid,
            "match_percentage": pct,
            "matching_shards": matches,
            "total_compared": compare_len,
            "theatre_sequence": theatre_seq[:compare_len]
        }
        all_scores.append(score_info)

        if pct > best_score:
            best_score = pct
            best_match = score_info

    confidence = "HIGH" if best_score >= 90 else ("MEDIUM" if best_score >= 70 else "LOW")

    return {
        "matched": best_score >= 70,
        "best_match": best_match,
        "confidence": confidence,
        "observed_sequence": observed_sequence,
        "all_candidates": sorted(all_scores, key=lambda x: x["match_percentage"], reverse=True)
    }


if __name__ == "__main__":
    theatres = ["THEATRE_001", "THEATRE_002", "THEATRE_003"]
    print("CinemaShield A/B Dual-Variant Forensic Engine Test:")
    for t in theatres:
        seq = generate_theatre_ab_sequence(t, 8)
        print(f"  {t} Assigned Sequence: {'-'.join(seq)} (Binary: {''.join('1' if x=='B' else '0' for x in seq)})")

    test_observed = generate_theatre_ab_sequence("THEATRE_002", 8)
    trace = trace_leaked_fingerprint(test_observed, theatres, 8)
    print("\nReverse-Lookup Trace Result for THEATRE_002 signature:")
    print(f"  Identified: {trace['best_match']['theatre_id']} with {trace['best_match']['match_percentage']}% confidence ({trace['confidence']})")
