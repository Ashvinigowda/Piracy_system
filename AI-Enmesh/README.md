# AI Enmesh

**Distributed Storage Mesh Network Monitoring Dashboard**

A standalone real-time network topology visualization and monitoring console for distributed cloud storage mesh infrastructure.

## Quick Start

```bash
# 1. Install dependencies
pip install -r backend/requirements.txt

# 2. Start the dashboard (port 6100)
python backend/app.py
```

Open **http://localhost:6100** in your browser.

## Prerequisites

The AI Enmesh dashboard monitors CinemaShield cloud mesh nodes running on ports 8001-8005.
Make sure CinemaShield is running first so the mesh nodes are active.

## Architecture

```
AI-Enmesh/
+-- backend/
|   +-- app.py               # Flask REST API server (port 6100)
|   +-- requirements.txt     # Python dependencies
+-- frontend/
|   +-- index.html            # Dashboard page
|   +-- css/style.css         # Dark modern styling
|   +-- js/
|       +-- app.js            # Main application controller
|       +-- graph.js          # Canvas network graph engine
|       +-- telemetry.js      # Live telemetry fetcher
+-- README.md
```

## API Endpoints

| Method | Endpoint                     | Description                  |
|--------|------------------------------|------------------------------|
| GET    | `/api/mesh/telemetry`        | Full mesh node telemetry     |
| GET    | `/api/mesh/nodes/<node_id>`  | Single node detail           |
| POST   | `/api/mesh/toggle/<node_id>` | Toggle node ONLINE/OFFLINE   |

## Features

- Real-time animated network topology graph
- Live node health monitoring with color-coded status
- Animated data-flow particles along connections
- Interactive hover tooltips and click selection
- Pan and zoom support
- Automatic backup relationship detection
- Compact mesh status summary panel
