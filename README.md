# 🛡️ Self-Healing Secure Network Using Blockchain

> A research-grade prototype simulating network attacks and autonomous
> blockchain-coordinated self-healing — built with Python, Flask,
> React, and a decentralised PBFT consensus layer.

---

## 📌 Project Overview

This system simulates a 7-node peer-to-peer blockchain network that:
- Detects attacks in real time (Byzantine Fault, DDoS Flood)
- Logs attack and consensus events immutably on a per-node blockchain
- Automatically isolates malicious nodes via decentralised PBFT consensus
- Restores network topology through autonomous primary rotation
- Visualises live network topology, consensus voting, and network metrics

The network uses a **rotating primary** model with no permanent leader —
every validator has equal authority. After each block, the primary role
rotates round-robin across all healthy nodes.

---

## 🏗️ Architecture

```
blockchain-network/
├── backend/
│   ├── app.py                # Flask entry point, REST API & WebSocket server
│   └── network_manager.py    # Core simulation: nodes, edges, PBFT, attacks,
│                             # EdgeMetrics (latency/bandwidth/jitter/RTT)
├── frontend/
│   └── src/
│       ├── App.jsx           # Main dashboard, Socket.IO client
│       └── components/
│           ├── NetworkGraph.jsx   # D3.js live topology with fixed layout
│           ├── LogFeed.jsx        # Real-time event log (newest on top)
│           ├── ConsensusBar.jsx   # PBFT voting progress visualiser
│           ├── MetricsPanel.jsx   # Per-edge metrics table (live values)
│           └── MetricsGraphs.jsx  # Canvas sparkline graphs for all metrics
└── README.md
```

> **Note:** The project uses a single `network_manager.py` file for all
> backend logic. There are no separate `node.py`, `chain.py`,
> `consensus.py`, `attacks.py`, or `contracts/` directories.

---

## ⚙️ Tech Stack

| Layer        | Technology                                      |
|--------------|-------------------------------------------------|
| Backend      | Python 3.10+, Flask 3.x, Flask-SocketIO 5.x    |
| Blockchain   | Custom per-node chain (simulated) + Ganache 7.x |
| Frontend     | React 18, Vite 5, D3.js v7                      |
| Realtime     | Socket.IO (WebSocket + polling fallback)         |
| Consensus    | Decentralised PBFT — Pre-Prepare / Prepare / Commit |
| Graphs       | HTML5 Canvas (no chart library dependency)       |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18 LTS (not v19/v20 — required for React 18 compatibility)
- Ganache v7 (`npm install -g ganache`)

### 1. Start Ganache

```bash
ganache --port 7545
```

### 2. Backend Setup

```bash
cd backend
pip install flask==3.0.3 flask-socketio==5.3.6 flask-cors==4.0.1 \
            python-socketio==5.11.3 python-engineio==4.9.1 \
            web3==6.20.0 python-dotenv==1.0.1
python app.py
```

Backend runs at: `http://localhost:5000`

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: `http://localhost:5173`

---

## 🔬 Features

### Network Simulation
- 7-node partial mesh topology (10 edges) — mirrors real P2P network design
- Rotating primary — no permanent leader, N1 → N2 → ... round-robin per block
- Per-node independent blockchain with genesis block and full transaction history
- Block mining every 2 seconds with 3–8 transactions per block

### Attack Simulation
- **Byzantine Fault** — node broadcasts conflicting block hashes to different peers,
  reputation drains at 18%/step
- **DDoS Flood** — node saturates bandwidth with transaction spam,
  reputation drains at 8%/step

### Decentralised PBFT Consensus (3-phase)
1. **Pre-Prepare** — random accuser broadcasts anomaly accusation
2. **Prepare** — all validators independently cross-check (92% ack rate)
3. **Commit** — validators vote quarantine/abstain (88% commit rate)
   — quorum = ⌊2n/3⌋ + 1, fault tolerance f = ⌊(n−1)/3⌋

### Self-Healing
- Quarantined node edges severed (backend `active=False`, not just visual)
- Primary automatically rotated if quarantined node held primary role
- Full reset restores all nodes, edges, and metrics to baseline

### Live Network Metrics (per edge)
| Metric      | Idle baseline | DoS attack (near) | Byzantine (near) | PBFT consensus |
|-------------|---------------|-------------------|------------------|----------------|
| Latency     | 8–35 ms       | ×5–14             | ×1.5–3.5         | ×2.5–5         |
| Bandwidth   | 80–120 Mbps   | 3–18% of base     | 55–82% of base   | 25–45% of base |
| Jitter      | 1–4 ms        | spikes high        | moderate spike   | elevated       |
| Packet Loss | 0–0.5%        | 25–65%            | 5–18%            | 3–10%          |
| RTT         | latency × 2   | scales with lat   | scales with lat  | scales with lat|

### Dashboard Panels
- **Network Graph** — D3.js force layout with fixed positions, animated packet
  dots, per-node reputation bars, pulse rings for active/compromised nodes
- **Node Registry** — live REP / BLK / peer count per node with status badges
- **Metrics Panel** — toggleable table of all 10 edges with health scores
- **Metrics Graphs** — canvas sparklines for LAT / RTT / BW / JITTER / LOSS,
  selectable per edge, colour-coded warn/crit thresholds
- **Live Event Log** — real-time feed, newest event on top, 300-event buffer

---

## 🔌 API Reference

| Method | Endpoint         | Description                        |
|--------|------------------|------------------------------------|
| GET    | `/api/state`     | Full network snapshot              |
| POST   | `/api/attack`    | Trigger attack `{type, target}`    |
| POST   | `/api/reset`     | Restore all nodes and edges        |
| POST   | `/api/heal`      | Manually trigger PBFT on suspects  |
| GET    | `/api/metrics`   | All edge metrics snapshot          |
| GET    | `/api/chain/:id` | Blockchain for a specific node     |
| GET    | `/health`        | Backend health check               |

### Socket.IO Events

**Backend → Frontend:**
`graph_update` · `stats_update` · `phase_change` · `log_event` ·
`consensus_votes` · `vote_cast` · `attack_started` · `anomaly_detected` ·
`node_quarantined` · `network_healed` · `edge_metrics_update`

**Frontend → Backend:**
`request_state`

---

## 📊 Research Context

This project explores:
- **Distributed Systems Security** — Byzantine and DoS threat modelling
  in partial-mesh P2P topologies
- **Blockchain as a trust layer** — immutable per-node ledgers for
  tamper-evident attack logging
- **Autonomous network recovery** — PBFT-driven quarantine and
  primary rotation without central authority
- **Network performance under attack** — realistic latency/bandwidth
  degradation models for edge-level impact analysis

The PBFT implementation follows Castro & Liskov (1999) with quorum
formula 2f+1 across n=7 nodes (f=2), giving tolerance to 2 simultaneous
Byzantine failures.

---

## 🐛 Known Issues & Limitations

- Ganache runs but individual simulated blocks are not submitted to
  the Ganache chain per tick — the blockchain layer operates at
  simulation level above Ganache for performance
- Node.js v19+ causes React 18 / Recharts incompatibility — use v18 LTS
- On Windows, run backend on `host="127.0.0.1"` (not `0.0.0.0`)
  to avoid Windows Defender Firewall prompts

---

## 👩‍💻 Author

**Khushyi Laddha**
Engineering Student | Blockchain & Network Security Research

---

## 📄 License

This project is for academic and research demonstration purposes.