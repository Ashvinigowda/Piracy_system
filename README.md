# 🎬 CinemaShield 2.0 & AI Enmesh

### Zero-Trust Theatrical Digital Cinema Distribution & Decentralized Storage Mesh

<p align="center">

**CinemaShield 2.0 + AI Enmesh**

A secure theatrical digital cinema distribution pipeline combining  
**encrypted video sharding, cryptographic integrity verification, decentralized storage, failover, and secure in-memory playback.**

</p>

---

## 📌 Overview

CinemaShield 2.0 and AI Enmesh are two decoupled systems that work together to demonstrate a secure theatrical digital cinema distribution pipeline.

**CinemaShield** handles:

- Studio ingest
- Video sharding
- AES-256-GCM encryption
- Integrity verification
- Theatre authentication
- In-memory playback
- Forensic session watermarking

**AI Enmesh** provides:

- Five-node distributed object storage
- Shard dispersion
- Node health monitoring
- Telemetry
- Backup-node failover simulation
- Distributed storage visualization

The two systems communicate through **HTTP REST APIs**.

---

## ✨ Key Features

### 🔐 Cryptographic Security

- AES-256-GCM envelope encryption
- Per-shard ephemeral 256-bit Data Encryption Keys (DEKs)
- Master Key Encryption Key (KEK) wrapping
- SHA-256 Merkle tree integrity verification
- Per-shard Merkle proof paths
- HMAC-SHA256 signed manifests

### 🎬 Secure Cinema Distribution

- Sequential video sharding using FFmpeg stream-copy processing
- Balanced and randomized shard dispersion
- Multi-node distributed storage
- Theatre-specific authorization
- DCI hardware certificate attestation
- Time-bounded session authorization
- Zero-disk in-memory playback
- Dynamic forensic session watermarking

### 🌐 AI Enmesh Storage Mesh

- Five autonomous HTTP storage nodes
- ENM-01 through ENM-05
- Distributed object storage
- Node health monitoring
- Real-time telemetry
- Topology visualization
- Designated backup-node failover
- Simulated storage-node outages

### 🧪 Testing & Reliability

- Automated end-to-end integration testing
- HTTP shard upload and retrieval
- Physical storage verification
- Merkle manifest verification
- Backup failover testing
- In-memory reassembly
- Playback readiness verification

---

# 💡 Why CinemaShield?

Traditional theatrical content distribution introduces several challenges:

### 1. Physical theatrical media logistics

Traditional encrypted media drives require physical shipment between production/distribution environments and theatres.

### 2. Centralized delivery infrastructure

Centralized CDNs and delivery infrastructure can introduce concentration and availability risks.

### 3. Local media exposure

Conventional theatre workflows may leave decrypted or partially protected media on persistent local storage.

### CinemaShield's Approach

CinemaShield addresses these challenges by:

```text
Master Movie
     ↓
Video Sharding
     ↓
AES-256-GCM Encryption
     ↓
Distributed Storage
     ↓
Cryptographic Integrity Verification
     ↓
Theatre Authentication
     ↓
Secure Retrieval
     ↓
In-Memory Decryption
     ↓
Zero-Disk Playback

                         ┌─────────────────────────┐
                         │     Studio / Producer   │
                         │      Master Video       │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │     CinemaShield 2.0    │
                         │       Port 5000         │
                         ├─────────────────────────┤
                         │ FFmpeg Sharding         │
                         │ AES-256-GCM Encryption  │
                         │ Merkle Manifest         │
                         │ KMS / DCI Attestation   │
                         │ Theatre Gateway         │
                         └────────────┬────────────┘
                                      │
                               HTTP REST PUT / GET
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
                    ▼                                   ▼
          ┌───────────────────┐             ┌────────────────────┐
          │    AI Enmesh      │             │ Theatre Gateway    │
          │ Controller :6100   │             │ Integrity + RAM    │
          └─────────┬─────────┘             │ Playback           │
                    │                       └────────────────────┘
          ┌─────────┼─────────┬─────────┬─────────┐
          ▼         ▼         ▼         ▼         ▼
       ENM-01    ENM-02    ENM-03    ENM-04    ENM-05
       :8001     :8002     :8003     :8004     :8005

Master Video
     ↓
FFmpeg Sharding
     ↓
AES-256-GCM Envelope Encryption
     ↓
Balanced + Randomized Mesh Dispersion
     ↓
Merkle Tree + HMAC-SHA256 Manifest
     ↓
Encrypted Shards Stored Across ENM-01 ... ENM-05
     ↓
Theatre DCI Attestation
     ↓
Primary Shard Retrieval
     ↓
Backup Failover if Primary Is Offline
     ↓
SHA-256 + Merkle Proof Verification
     ↓
AES-256-GCM Decryption in RAM
     ↓
Zero-Disk In-Memory Video Playback
