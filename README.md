🎬 CinemaShield 2.0 & AI Enmesh

Zero-Trust Theatrical Digital Cinema Distribution & Decentralized Storage Mesh

CinemaShield 2.0 and AI Enmesh are two decoupled systems that work together to demonstrate a secure theatrical digital cinema distribution pipeline. CinemaShield handles studio ingest, video sharding, encryption, integrity verification, theatre authentication, and in-memory playback, while AI Enmesh provides a five-node distributed object-storage mesh with telemetry and failover simulation.

✨ Key Features

🔐 AES-256-GCM envelope encryption with per-shard ephemeral 256-bit DEKs

🧩 Sequential video sharding using FFmpeg stream-copy processing

🌳 SHA-256 Merkle tree integrity verification with per-shard proof paths

✍️ HMAC-SHA256 signed manifests

🌐 Five-node distributed storage mesh (ENM-01–ENM-05)

⚖️ Balanced and randomized shard dispersion

🔁 Designated backup-node failover when a primary node is unavailable

🏛️ DCI hardware certificate attestation and time-bounded session authorization

💾 Zero-disk in-memory playback: decrypted video is assembled and streamed from volatile memory according to the project design

🕵️ Dynamic forensic session watermarking

📡 Real-time telemetry and topology visualization

🧪 Automated end-to-end integration testing

🚨 Simulated storage-node outages for disaster/failover testing

🧠 Why CinemaShield?

The project addresses three challenges described in the project specification:

Physical theatrical media logistics — traditional encrypted media drives require physical shipment.

Centralized delivery infrastructure — centralized CDNs can introduce infrastructure concentration and availability risks.

Local media exposure — conventional theatre workflows may leave decrypted or partially protected media on persistent local storage.

CinemaShield and AI Enmesh instead divide the movie into encrypted shards, distribute those encrypted shards across independent storage nodes, verify integrity using cryptographic proofs, and retrieve/decrypt the content for playback through the theatre gateway.

🏗️ Architecture

The system is split into two independently running applications communicating through HTTP REST APIs:

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

End-to-end pipeline

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

🔐 Security Design

AES-256-GCM envelope encryption

Each video shard receives its own ephemeral 256-bit Data Encryption Key (DEK). The shard payload is encrypted using AES-GCM, while the DEK is wrapped using the master Key Encryption Key (KEK).

The project uses the custom CSGCM1 envelope format:

[MAGIC: 6B]
[DEK IV: 12B]
[ENCRYPTED DEK LENGTH: 2B]
[ENCRYPTED DEK]
[DATA IV: 12B]
[CIPHERTEXT + AUTH TAG]

Merkle integrity verification

Encrypted shards are hashed using SHA-256 and organized into a binary Merkle tree. Each shard has a proof path that allows the theatre gateway to reconstruct and verify the expected Merkle Root before decryption.

Manifest signing

The distribution manifest is protected using HMAC-SHA256 and binds the Merkle Root, authorized theatre, and distribution timestamp.

Theatre authorization

The KMS broker validates registered DCI theatre hardware information and applies a playback validity window before issuing an ephemeral session authorization.

Forensic watermarking

The project generates a session fingerprint using theatre/session information and renders a dynamic forensic watermark over the playback interface.

🌐 AI Enmesh Storage Mesh

AI Enmesh provides five autonomous HTTP storage-node microservices:

Node

Port

Role

ENM-01

8001

Distributed object storage

ENM-02

8002

Distributed object storage

ENM-03

8003

Distributed object storage

ENM-04

8004

Distributed object storage

ENM-05

8005

Distributed object storage

The documented REST endpoints include:

PUT    /api/v1/objects/<key>
GET    /api/v1/objects/<key>
GET    /api/v1/health
POST   /api/v1/toggle-outage
DELETE /api/v1/objects/<key>

Each shard has a primary node and a designated backup node. If the primary node becomes unavailable, CinemaShield retrieves the encrypted shard from its designated backup.

🛠️ Technology Stack

Category

Technologies

Backend

Python 3.10+, Flask 3.0+

Frontend

HTML5, CSS3, JavaScript ES6+

Video Processing

FFmpeg, FFprobe

Encryption

AES-256-GCM

Integrity

SHA-256, Merkle Tree

Signing

HMAC-SHA256

Communication

HTTP REST, SSE, Range Requests

Storage

Five HTTP object-storage microservices

Visualization

HTML5 Canvas

Concurrency

ThreadPoolExecutor, Python threading

Security

DCI attestation, ephemeral KDM/session authorization, forensic watermarking

The documented dependency requirements include Flask, Flask-CORS, cryptography, and Werkzeug. FFmpeg/FFprobe must also be available through the system PATH.

📁 Project Structure

ignite/
├── CinemaShield/
│   ├── backend/
│   │   ├── encrypt_shards.py
│   │   ├── generate_manifest.py
│   │   ├── storage_mesh.py
│   │   ├── kms.py
│   │   ├── shard_movie.py
│   │   ├── forensic_ab.py
│   │   └── erasure_coding.py
│   ├── frontend/
│   │   ├── app.py
│   │   ├── ai_engine.py
│   │   ├── templates/
│   │   └── static/
│   ├── requirements.txt
│   └── test_cinemashield_enmesh_e2e.py
│
└── AI-Enmesh/
    ├── backend/
    │   ├── app.py
    │   ├── node_server.py
    │   └── requirements.txt
    ├── frontend/
    │   ├── index.html
    │   ├── css/
    │   └── js/
    └── nodes/
        ├── ENM-01/
        ├── ENM-02/
        ├── ENM-03/
        ├── ENM-04/
        └── ENM-05/

💻 Requirements

Software

Python 3.10+

Recommended Python: 3.11 or 3.12

FFmpeg 4.4+ (6.0+ recommended)

FFprobe

Pip 22.0+

Modern browser with HTML5 Canvas, EventSource, Fetch/Range/Blob support

Local development hardware

The documented minimum for running CinemaShield and all five storage nodes together is:

4-core x86_64/ARM64 CPU

8 GB RAM

10 GB free SSD space

1366×768 display

Local loopback networking

16 GB RAM or higher is recommended for concurrent services and the documented in-memory playback design.

🚀 Installation & Running

1. Install CinemaShield dependencies

From the CinemaShield directory:

pip install -r requirements.txt

2. Install AI Enmesh dependencies

From the AI-Enmesh directory:

pip install -r backend/requirements.txt

3. Start AI Enmesh first

Open Terminal 1:

python backend/app.py

Dashboard:

http://localhost:6100

This starts the controller and storage nodes on ports 8001–8005.

4. Start CinemaShield

Open Terminal 2:

python frontend/app.py

CinemaShield:

Home       → http://localhost:5000
Producer   → http://localhost:5000/producer
Theatre    → http://localhost:5000/theatre
Analytics  → http://localhost:5000/analytics

🎬 Demo Workflow

Open the AI Enmesh dashboard at http://localhost:6100.

Open the CinemaShield Producer portal.

Select a target theatre.

Upload a supported test video.

Start Secure, Shard & Disperse.

Observe the seven-stage security pipeline.

Verify shard counts and node telemetry in AI Enmesh.

Copy the generated Master KEK for the demonstration.

Open the Theatre Gateway.

Enter the Master KEK and start playback.

Observe integrity verification, retrieval, decryption, and playback.

Optionally take one storage node offline and verify designated-backup failover.

🧪 Testing

Run the documented end-to-end integration test:

python test_cinemashield_enmesh_e2e.py

The documented test flow covers:

AI Enmesh health

Movie sharding and encryption

HTTP shard upload

Balanced shard distribution

Physical storage verification

Telemetry

Merkle manifest generation

Local temporary-shard cleanup

HTTP retrieval

Backup failover

SHA-256 and Merkle verification

KEK-based decryption

In-memory reassembly

Playback readiness

🚨 Failover Demonstration

AI Enmesh supports simulated node outages.

For example, take ENM-02 offline from the Theatre Gateway or dashboard, then run the playback workflow again. CinemaShield should detect the unavailable primary node and request the shard from its designated backup node.

The project documentation demonstrates this with a primary ENM-02 failure followed by retrieval from backup ENM-04.

📸 Screenshots

The project includes screenshots demonstrating:

AI Enmesh distributed topology dashboard

CinemaShield home portal

Studio ingest and zero-trust pipeline

Theatre gateway

Video playback interface

Security and mesh analytics

Threat/tamper monitoring

DCI hardware attestation metrics

Session fingerprint generation

Place repository-ready images under:

docs/images/

and add them to this section when the final screenshots are selected.

📚 Documentation

The project documentation covers:

Project overview and component specifications

System requirements

Architecture and design analysis

Technology stack

Installation and execution

End-to-end testing

Failover simulation

Security and cryptographic design

⚠️ Security / Repository Notes

Do not commit sensitive or generated material to GitHub, including:

Master KEKs

Production cryptographic keys

Session tokens

Real theatre credentials/certificates

Uploaded movie files

Generated encrypted movie shards

Local node storage contents

Python virtual environments

.env files containing secrets

Use environment variables or local configuration for secrets where applicable.

👩‍💻 Project

CinemaShield 2.0 & AI Enmesh

A project focused on zero-trust theatrical content distribution, encrypted video sharding, decentralized storage, cryptographic integrity, failover, and secure in-memory playback.

⭐ If you find the architecture interesting, feel free to explore the code and documentation.
