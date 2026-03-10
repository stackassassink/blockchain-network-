# 🛡️ Self-Healing Secure Network Using Blockchain

> A research-grade prototype simulating network attacks and autonomous 
> blockchain-coordinated self-healing — built with Python, Flask, 
> React, and a custom blockchain layer.

---

## 📌 Project Overview

This system simulates a peer-to-peer network that:
- Detects attacks in real time (Byzantine, Sybil, Blackhole, DDoS)
- Logs attack events immutably on a blockchain
- Automatically heals by rerouting traffic and isolating malicious nodes
- Visualizes network topology, consensus state, and metrics live

---

## 🏗️ Architecture
```
blockchain-network/
├── backend/               # Python Flask + SocketIO server
│   ├── app.py             # Entry point, REST API & WebSocket
│   ├── network_manager.py # Core network orchestration
│   ├── network.py         # Network topology simulation
│   ├── node.py            # Node model
│   ├── chain.py           # Blockchain layer
│   ├── consensus.py       # Consensus mechanism
│   └── attacks.py         # Attack simulation engine
├── frontend/              # React + Vite dashboard
│   ├── App.jsx            # Main app
│   ├── NetworkGraph.jsx   # Live D3 network topology
│   ├── AttackPanel.jsx    # Attack control panel
│   ├── MetricsGraphs.jsx  # RTT, latency, throughput graphs
│   ├── ConsensusBar.jsx   # Blockchain consensus visualizer
│   └── ...
└── contracts/             # Smart contracts (Ganache)
```

---

## ⚙️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask, Flask-SocketIO |
| Blockchain | Custom chain + Ganache simulation |
| Frontend | React, Vite, D3.js, Axios |
| Realtime | WebSockets (Socket.IO) |
| Consensus | Custom Byzantine Fault Tolerant logic |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+
- Ganache (for blockchain simulation)

### Backend Setup
```bash
cd backend
pip install flask flask-socketio flask-cors
python app.py
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: `http://localhost:5173`  
Backend runs at: `http://localhost:5000`

---

## 🔬 Features

- ✅ Real-time network topology visualization
- ✅ Attack simulation: Byzantine, Sybil, Blackhole, Packet Drop
- ✅ Blockchain-logged attack events (immutable ledger)
- ✅ Autonomous self-healing with consensus validation
- ✅ Live metrics: RTT, packet loss, latency, throughput
- ✅ WebSocket-powered live dashboard

---

## 📊 Research Context

This project explores the intersection of:
- Distributed Systems Security
- Blockchain as a trust layer
- Autonomous network recovery

---

## 👨‍💻 Author

**Khushyi Laddha**  
Engineering Student | Blockchain & Network Security Research