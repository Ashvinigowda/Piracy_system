"""
CinemaShield — Pure Python Galois Field GF(2^8) Reed-Solomon Erasure Coding Engine
──────────────────────────────────────────────────────────────────────────────────
Provides K-of-N outage resilience for multi-cloud zero-trust storage meshes.
Enables recovering 100% of missing or corrupted video shards from parity shards.
"""

import os
import sys
from typing import List, Dict, Tuple, Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ═══════════════════════════════════════════
# 1. GALOIS FIELD GF(2^8) ARITHMETIC TABLES
# ═══════════════════════════════════════════

POLYNOMIAL = 0x11D  # x^8 + x^4 + x^3 + x^2 + 1 (285)

GF_EXP = [0] * 512
GF_LOG = [0] * 256

# Initialize lookup tables
x = 1
for i in range(255):
    GF_EXP[i] = x
    GF_LOG[x] = i
    x <<= 1
    if x & 0x100:
        x ^= POLYNOMIAL

for i in range(255, 512):
    GF_EXP[i] = GF_EXP[i - 255]


def gf_add(a: int, b: int) -> int:
    """Addition in GF(2^8) is bitwise XOR."""
    return a ^ b


def gf_mul(a: int, b: int) -> int:
    """Multiplication in GF(2^8) using log/exp tables."""
    if a == 0 or b == 0:
        return 0
    return GF_EXP[GF_LOG[a] + GF_LOG[b]]


def gf_div(a: int, b: int) -> int:
    """Division in GF(2^8)."""
    if b == 0:
        raise ZeroDivisionError("GF(2^8) division by zero")
    if a == 0:
        return 0
    return GF_EXP[(GF_LOG[a] - GF_LOG[b] + 255) % 255]


def gf_inv(a: int) -> int:
    """Multiplicative inverse in GF(2^8)."""
    if a == 0:
        raise ZeroDivisionError("GF(2^8) inverse of zero")
    return GF_EXP[255 - GF_LOG[a]]


# ═══════════════════════════════════════════
# 2. CAUCHY / VANDERMONDE MATRIX GENERATOR
# ═══════════════════════════════════════════

def build_cauchy_matrix(rows: int, cols: int) -> List[List[int]]:
    """
    Constructs a Cauchy matrix over GF(2^8) which is guaranteed to be non-singular
    for all square submatrices (ideal for erasure coding).
    A[i][j] = 1 / (X_i ^ Y_j) where X_i and Y_j are disjoint sets.
    """
    matrix = []
    for i in range(rows):
        row = []
        for j in range(cols):
            x_i = i
            y_j = rows + j
            row.append(gf_inv(x_i ^ y_j))
        matrix.append(row)
    return matrix


def invert_matrix(matrix: List[List[int]]) -> List[List[int]]:
    """
    Inverts a square matrix over GF(2^8) using Gauss-Jordan elimination.
    """
    n = len(matrix)
    # Augment with identity
    augmented = [row[:] + [1 if i == j else 0 for j in range(n)] for i, row in enumerate(matrix)]

    for i in range(n):
        # Pivot
        pivot = augmented[i][i]
        if pivot == 0:
            # Find non-zero pivot below
            swap_row = -1
            for k in range(i + 1, n):
                if augmented[k][i] != 0:
                    swap_row = k
                    break
            if swap_row == -1:
                raise ValueError("Matrix is singular over GF(2^8)")
            augmented[i], augmented[swap_row] = augmented[swap_row], augmented[i]
            pivot = augmented[i][i]

        # Normalize pivot row
        inv_pivot = gf_inv(pivot)
        augmented[i] = [gf_mul(val, inv_pivot) for val in augmented[i]]

        # Eliminate other rows
        for k in range(n):
            if k != i:
                factor = augmented[k][i]
                if factor != 0:
                    augmented[k] = [gf_add(val, gf_mul(factor, augmented[i][j])) for j, val in enumerate(augmented[k])]

    # Extract right half
    return [row[n:] for row in augmented]


# ═══════════════════════════════════════════
# 2.5 VECTORIZED GF MULTIPLICATION TABLES
# ═══════════════════════════════════════════

# Precompute translation tables for all 256 possible coefficients for instant C-level translation
GF_MUL_TABLES = [
    bytes([gf_mul(b, coeff) for b in range(256)])
    for coeff in range(256)
]


def _gf_vector_mul(data: bytes, coeff: int) -> bytes:
    """Ultra-fast GF(2^8) vector multiplication using C-level byte translation."""
    if coeff == 0:
        return bytes(len(data))
    if coeff == 1:
        return data
    return data.translate(GF_MUL_TABLES[coeff])


def _fast_xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR two byte strings at C-speed using Python long integers."""
    if not a:
        return b
    if not b:
        return a
    n = len(a)
    a_int = int.from_bytes(a, 'little')
    b_int = int.from_bytes(b, 'little')
    return (a_int ^ b_int).to_bytes(n, 'little')


# ═══════════════════════════════════════════
# 3. ENCODE: DATA SHARDS -> PARITY SHARDS
# ═══════════════════════════════════════════

def encode_parity_shards(data_shards: List[bytes], parity_count: int = 2) -> List[bytes]:
    """
    Given K data shards, generate M parity shards using Reed-Solomon Cauchy matrix.
    Vectorized and optimized with C-speed byte translations.
    """
    if not data_shards or parity_count <= 0:
        return []

    k = len(data_shards)
    m = parity_count

    # Max length padding
    max_len = max(len(s) for s in data_shards)
    padded_data = [s.ljust(max_len, b'\x00') for s in data_shards]

    cauchy = build_cauchy_matrix(m, k)
    parity_shards = []

    for p_idx in range(m):
        row_coeffs = cauchy[p_idx]
        parity_acc = bytes(max_len)

        for col_idx in range(k):
            coeff = row_coeffs[col_idx]
            if coeff == 0:
                continue
            scaled = _gf_vector_mul(padded_data[col_idx], coeff)
            parity_acc = _fast_xor_bytes(parity_acc, scaled)

        parity_shards.append(parity_acc)

    return parity_shards


# ═══════════════════════════════════════════
# 4. DECODE / RECONSTRUCT MISSING SHARDS
# ═══════════════════════════════════════════

def reconstruct_data_shards(
    available_shards: Dict[int, bytes],
    total_data_count: int,
    parity_count: int = 2
) -> List[bytes]:
    """
    Reconstructs all K data shards if AT LEAST K shards (data or parity) are present.
    Vectorized and optimized with C-speed byte translations.
    """
    k = total_data_count
    m = parity_count

    if len(available_shards) < k:
        raise ValueError(f"Insufficient shards for Reed-Solomon recovery. Need at least {k}, got {len(available_shards)}")

    # Check if all data shards are already present
    if all(i in available_shards for i in range(k)):
        return [available_shards[i] for i in range(k)]

    # Select the first K available shards
    selected_indices = sorted(available_shards.keys())[:k]
    max_len = max(len(available_shards[idx]) for idx in selected_indices)

    cauchy = build_cauchy_matrix(m, k)

    # Build the K x K decoding matrix
    decoding_matrix = []
    for idx in selected_indices:
        if idx < k:
            row = [1 if j == idx else 0 for j in range(k)]
        else:
            parity_row_idx = idx - k
            row = cauchy[parity_row_idx][:]
        decoding_matrix.append(row)

    # Invert the matrix
    inv_matrix = invert_matrix(decoding_matrix)

    # Reconstruct the K data shards
    reconstructed = []
    selected_data = [available_shards[idx].ljust(max_len, b'\x00') for idx in selected_indices]

    for data_idx in range(k):
        coeffs = inv_matrix[data_idx]
        shard_acc = bytes(max_len)

        for col_idx in range(k):
            coeff = coeffs[col_idx]
            if coeff == 0:
                continue
            scaled = _gf_vector_mul(selected_data[col_idx], coeff)
            shard_acc = _fast_xor_bytes(shard_acc, scaled)

        reconstructed.append(shard_acc)

    return reconstructed


if __name__ == "__main__":
    print("CinemaShield Reed-Solomon Erasure Coding Self-Test:")
    
    # 4 Data shards + 2 Parity shards
    data = [
        b"CinemaShield_Block_0_Master_Frame_Stream_AA",
        b"CinemaShield_Block_1_Master_Frame_Stream_BB",
        b"CinemaShield_Block_2_Master_Frame_Stream_CC",
        b"CinemaShield_Block_3_Master_Frame_Stream_DD",
    ]
    
    parities = encode_parity_shards(data, parity_count=2)
    print(f"  ✔ Created {len(data)} Data Shards + {len(parities)} Parity Shards (Total: {len(data) + len(parities)})")
    
    # Simulate losing Shard 1 and Shard 2 (50% data loss!)
    # Available: Shard 0, Shard 3, Parity 0, Parity 1 (Indices 0, 3, 4, 5)
    surviving = {
        0: data[0],
        3: data[3],
        4: parities[0],
        5: parities[1]
    }
    
    recovered = reconstruct_data_shards(surviving, total_data_count=4, parity_count=2)
    assert recovered[0] == data[0]
    assert recovered[1] == data[1]
    assert recovered[2] == data[2]
    assert recovered[3] == data[3]
    
    print("  ✔ REED-SOLOMON SELF-HEALING SUCCESS: Recovered lost shards [1, 2] bit-for-bit from parity shards!")
