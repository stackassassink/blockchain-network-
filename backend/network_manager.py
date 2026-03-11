"""
network_manager.py — Self-Healing Secure Network / PBFT Blockchain Simulation
==============================================================================
ROOT CAUSE FIXES (v3):
  1. near_attack now triggers IMMEDIATELY on attack start — no waiting for
     node status to transition to "compromised" first.
  2. _attack_edges set is populated the moment an attack is launched so
     ALL ticks for those edges use attack math from tick 0.
  3. Bandwidth spikes UP during DoS (flood traffic) then collapses — more
     physically accurate than a simple drop.
  4. History buffer phased reset so graphs show sharp transitions.
"""

import time
import random
import threading
from datetime import datetime
from typing import Optional, Callable
from collections import deque

INITIAL_REP     = 100.0
REP_DRAIN_BYZ   = 18.0
REP_DRAIN_DOS   = 8.0
PBFT_QUORUM     = 0.67
BLOCK_INTERVAL  = 2.0
TX_RATE_BASE    = 14

COMMS_TICK_IDLE      = 1.5
COMMS_TICK_ATTACK    = 0.6   # faster ticks during attack → graph updates quickly
COMMS_TICK_CONSENSUS = 1.0
ATTACK_SECS          = 5

PEER_MESSAGES = [
    "Block #{block} propagated {node} → {peer}",
    "Heartbeat: {node} → {peer} | alive",
    "Tx sync: {node} → {peer} | {tx} transactions",
    "Chain validated: {node} verified #{block}",
    "Gossip: {node} shared mempool with {peer}",
    "State sync: {node} → {peer} | height={block}",
    "Pre-prepare: {node} → {peer} | round #{block}",
    "Prepare msg: {node} → {peer} | seq={block}",
    "Commit msg: {node} → {peer} | block confirmed",
    "Block #{block} endorsed by {node}",
    "Replication: {node} → {peer} | {tx} records",
    "View-change check: {node} polling {peer}",
]


# ── helpers ───────────────────────────────────────────────────────────────────
def _avg(lst, key):
    vals = [v[key] for v in lst if key in v]
    return sum(vals) / len(vals) if vals else 0.0


# ── EdgeMetrics ───────────────────────────────────────────────────────────────
class EdgeMetrics:
    """
    Per-edge live metrics with physically realistic attack behaviour.

    DoS flood:
      • First 2 ticks: bandwidth SPIKES (flood traffic) then COLLAPSES
      • Latency shoots up (queue saturation)
      • Packet loss soars (buffers overflow)

    Byzantine fault:
      • Bandwidth drops moderately (retransmissions)
      • Latency rises (double-spend detection overhead)
      • Packet loss rises (conflicting blocks rejected)

    Consensus phase:
      • Bandwidth drops (message passing saturates link)
      • Latency elevated (multi-round voting)
    """

    def __init__(self, source: str, target: str):
        self.source           = source
        self.target           = target
        self.edge_key         = f"{source}-{target}"
        self.base_latency     = random.uniform(8, 35)
        self.base_bandwidth   = random.uniform(80, 120)
        self.latency          = self.base_latency
        self.bandwidth        = self.base_bandwidth
        self.jitter           = random.uniform(1, 4)
        self.rtt              = self.base_latency * 2
        self.packet_loss      = 0.0
        self.message_count    = 0
        self.bytes_sent       = 0
        self._latency_history = deque(maxlen=12)
        self._latency_history.append(self.base_latency)
        self._tick            = 0          # counts attack ticks for burst model

    def reset_to_idle(self):
        """Snap back to baseline when network heals."""
        self.latency     = self.base_latency + random.uniform(0, 4)
        self.bandwidth   = self.base_bandwidth + random.uniform(-5, 8)
        self.packet_loss = random.uniform(0, 0.5)
        self.jitter      = random.uniform(1, 4)
        self.rtt         = self.latency * 2
        self._tick       = 0
        self._latency_history.clear()
        self._latency_history.append(self.latency)

    def update(self, phase: str, near_attack: bool, attack_type: str = None):
        """Recalculate all metrics. Called every tick regardless of node status."""
        self.message_count += 1
        self.bytes_sent    += random.randint(512, 8192)
        self._tick         += 1

        if phase == "idle":
            # Natural small fluctuations
            self.latency     = self.base_latency  + random.uniform(-2,  6)
            self.bandwidth   = self.base_bandwidth + random.uniform(-8, 10)
            self.packet_loss = random.uniform(0, 0.8)
            self._tick       = 0

        elif phase == "attack":
            if near_attack:
                if attack_type == "dos":
                    # ── DoS / DDoS flood ──────────────────────────────────
                    # Tick 0-1: Bandwidth SPIKES (flood traffic arriving)
                    # Tick 2+ : Bandwidth COLLAPSES (queues saturated, drops)
                    if self._tick <= 2:
                        bw_mult = random.uniform(1.8, 3.2)   # initial spike
                    else:
                        bw_mult = random.uniform(0.02, 0.12) # collapse
                    self.latency     = self.base_latency * random.uniform(7, 18)
                    self.bandwidth   = self.base_bandwidth * bw_mult
                    self.packet_loss = random.uniform(35, 75)

                elif attack_type == "byzantine":
                    # ── Byzantine / Double-spend ──────────────────────────
                    self.latency     = self.base_latency * random.uniform(2.5, 6)
                    self.bandwidth   = self.base_bandwidth * random.uniform(0.35, 0.70)
                    self.packet_loss = random.uniform(10, 30)

                else:
                    # Generic / Eclipse / Sybil
                    self.latency     = self.base_latency * random.uniform(3, 9)
                    self.bandwidth   = self.base_bandwidth * random.uniform(0.15, 0.50)
                    self.packet_loss = random.uniform(20, 55)
            else:
                # Indirect congestion — still noticeably worse than idle
                self.latency     = self.base_latency * random.uniform(1.4, 2.8)
                self.bandwidth   = self.base_bandwidth * random.uniform(0.65, 0.90)
                self.packet_loss = random.uniform(1.5, 10)

        elif phase == "consensus":
            # PBFT message storm saturates links
            self.latency     = self.base_latency * random.uniform(2.5, 6)
            self.bandwidth   = self.base_bandwidth * random.uniform(0.18, 0.42)
            self.packet_loss = random.uniform(3, 14)
            self._tick       = 0

        # ── Hard clamps ───────────────────────────────────────────────────
        self.latency     = round(max(1.0,  min(self.latency,    3000.0)), 1)
        self.bandwidth   = round(max(0.05, min(self.bandwidth,   350.0)), 1)
        self.packet_loss = round(max(0.0,  min(self.packet_loss,  99.0)), 1)

        # Jitter = mean absolute deviation of recent latency readings
        self._latency_history.append(self.latency)
        if len(self._latency_history) > 1:
            readings = list(self._latency_history)
            avg_lat  = sum(readings) / len(readings)
            self.jitter = round(
                sum(abs(r - avg_lat) for r in readings) / len(readings), 1
            )
        else:
            self.jitter = round(random.uniform(1, 4), 1)

        # RTT = round-trip (latency + small ack overhead)
        ack_overhead = random.uniform(0.8, 1.3)
        self.rtt = round(self.latency * 2 * ack_overhead, 1)

    def to_dict(self) -> dict:
        return {
            "edge_key":      self.edge_key,
            "source":        self.source,
            "target":        self.target,
            "latency":       self.latency,
            "bandwidth":     self.bandwidth,
            "jitter":        self.jitter,
            "rtt":           self.rtt,
            "packet_loss":   self.packet_loss,
            "message_count": self.message_count,
            "bytes_sent":    self.bytes_sent,
        }


# ── Node ──────────────────────────────────────────────────────────────────────
class Node:
    def __init__(self, node_id: str):
        self.id          = node_id
        self.status      = "healthy"
        self.reputation  = INITIAL_REP
        self.attack_type = None
        self.chain       = []
        self.peers       = []
        self._genesis()

    def _genesis(self):
        self.chain.append({
            "index": 0, "timestamp": datetime.utcnow().isoformat(),
            "data": "Genesis Block", "previous_hash": "0" * 64,
            "hash": "genesis_" + self.id,
        })

    def mine_block(self, transactions: list) -> dict:
        prev  = self.chain[-1]
        block = {
            "index":         len(self.chain),
            "timestamp":     datetime.utcnow().isoformat(),
            "transactions":  transactions,
            "previous_hash": prev["hash"],
            "hash":          f"{self.id}_block_{len(self.chain)}_{random.randint(1000,9999)}",
            "miner":         self.id,
        }
        self.chain.append(block)
        return block


# ── NetworkManager ────────────────────────────────────────────────────────────
class NetworkManager:
    """
    Orchestrates the 7-node PBFT network, attack simulation,
    self-healing, and real-time metric emission.
    """

    TOPOLOGY = {
        "N1": ["N2", "N3", "N4"],
        "N2": ["N1", "N3", "N5"],
        "N3": ["N1", "N2", "N6"],
        "N4": ["N1", "N5", "N7"],
        "N5": ["N2", "N4", "N6"],
        "N6": ["N3", "N5", "N7"],
        "N7": ["N4", "N6"],
    }

    def __init__(self, emit_fn: Callable):
        self._emit      = emit_fn
        self._lock      = threading.Lock()
        self._running   = False
        self._paused    = False
        self._phase     = "idle"

        # FIX: track which edges are "near attack" immediately on launch
        self._attack_node_ids: set = set()

        self._primary_idx   = 0
        self._total_blocks  = 0
        self._attack_timer  = None

        self.nodes: dict[str, Node] = {
            nid: Node(nid) for nid in self.TOPOLOGY
        }
        for nid, peers in self.TOPOLOGY.items():
            self.nodes[nid].peers = peers

        self.edges: list[dict] = []
        self.edge_metrics: dict[str, EdgeMetrics] = {}
        self._build_edges()

    # ── init ─────────────────────────────────────────────────────────────────
    def _build_edges(self):
        seen = set()
        for src, peers in self.TOPOLOGY.items():
            for tgt in peers:
                key = tuple(sorted([src, tgt]))
                if key not in seen:
                    seen.add(key)
                    self.edges.append({"source": src, "target": tgt, "active": True})
                    fwd = f"{src}-{tgt}"
                    rev = f"{tgt}-{src}"
                    self.edge_metrics[fwd] = EdgeMetrics(src, tgt)
                    self.edge_metrics[rev] = EdgeMetrics(tgt, src)

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self):
        self._running = True
        threading.Thread(target=self._block_loop,  daemon=True).start()
        threading.Thread(target=self._comms_loop,  daemon=True).start()

    def stop(self):
        self._running = False

    def pause(self):
        self._paused = True
        self._set_phase("paused")

    def resume(self):
        self._paused = False
        self._set_phase("idle")

    # ── public API ────────────────────────────────────────────────────────────
    def launch_attack(self, attack_type: str, target_id: str):
        """
        CRITICAL FIX: populate _attack_node_ids IMMEDIATELY so the very
        first comms tick uses attack math — no waiting for reputation drain.
        """
        with self._lock:
            node = self.nodes.get(target_id)
            if not node or node.status != "healthy":
                return {"error": "Target unavailable"}

            node.status      = "compromised"
            node.attack_type = attack_type

            # Immediately mark all neighbour edges as "near attack"
            self._attack_node_ids = {target_id} | set(self.TOPOLOGY.get(target_id, []))

            self._set_phase("attack")

        self._emit("attack_started", {
            "target": target_id, "type": attack_type,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self._emit_log(
            f"⚡ ATTACK LAUNCHED: {attack_type.upper()} on {target_id}", "error"
        )

        if self._attack_timer:
            self._attack_timer.cancel()
        self._attack_timer = threading.Timer(ATTACK_SECS, self._detect_and_heal)
        self._attack_timer.start()
        return {"status": "attack_launched", "target": target_id, "type": attack_type}

    def reset(self):
        with self._lock:
            if self._attack_timer:
                self._attack_timer.cancel()
                self._attack_timer = None
            self._attack_node_ids = set()
            for node in self.nodes.values():
                node.status      = "healthy"
                node.reputation  = INITIAL_REP
                node.attack_type = None
            for edge in self.edges:
                edge["active"] = True
            for em in self.edge_metrics.values():
                em.reset_to_idle()
            self._set_phase("idle")

        self._emit_log("🔄 Network reset — all nodes restored", "info")
        self._emit_graph()
        return {"status": "reset"}

    def heal(self):
        suspects = [n for n in self.nodes.values() if n.status in ("compromised", "suspect")]
        if not suspects:
            return {"status": "no_suspects"}
        for node in suspects:
            self._quarantine(node.id)
        return {"status": "healed", "quarantined": [n.id for n in suspects]}

    def get_state(self) -> dict:
        with self._lock:
            return {
                "nodes": self._node_list(),
                "edges": self.edges,
                "phase": self._phase,
                "stats": self._stats(),
            }

    def get_metrics(self) -> dict:
        return {k: v.to_dict() for k, v in self.edge_metrics.items()}

    def get_chain(self, node_id: str) -> list:
        node = self.nodes.get(node_id)
        return node.chain if node else []

    # ── internal loops ────────────────────────────────────────────────────────
    def _block_loop(self):
        while self._running:
            time.sleep(BLOCK_INTERVAL)
            if self._paused:
                continue
            with self._lock:
                self._mine_round()

    def _comms_loop(self):
        while self._running:
            tick_delay = (
                COMMS_TICK_ATTACK    if self._phase == "attack"    else
                COMMS_TICK_CONSENSUS if self._phase == "consensus" else
                COMMS_TICK_IDLE
            )
            time.sleep(tick_delay)
            if self._paused:
                continue
            self._simulate_comms()

    # ── mining ────────────────────────────────────────────────────────────────
    def _mine_round(self):
        primaries = list(self.TOPOLOGY.keys())
        primary_id = primaries[self._primary_idx % len(primaries)]
        self._primary_idx += 1
        primary = self.nodes[primary_id]

        n_tx = random.randint(3, 8)
        txs  = [{"id": f"tx_{self._total_blocks}_{i}", "value": random.randint(1, 100)}
                for i in range(n_tx)]

        if primary.status == "compromised" and primary.attack_type == "byzantine":
            # Byzantine: forge conflicting hashes
            primary.mine_block(txs)
            self._emit_log(
                f"⚠ Byzantine block from {primary_id} — conflicting hashes broadcast", "warning"
            )
        elif primary.status not in ("quarantined",):
            block = primary.mine_block(txs)
            # Replicate to peers
            for peer_id in primary.peers:
                peer = self.nodes.get(peer_id)
                if peer and peer.status not in ("quarantined",):
                    peer.mine_block(txs)

        self._total_blocks += 1
        self._drain_reputation()
        self._emit("stats_update", self._stats())

    def _drain_reputation(self):
        changed = False
        for node in self.nodes.values():
            if node.status == "compromised":
                drain = REP_DRAIN_BYZ if node.attack_type == "byzantine" else REP_DRAIN_DOS
                node.reputation = max(0.0, node.reputation - drain)
                if node.reputation < 30 and node.status == "compromised":
                    node.status = "suspect"
                    self._emit("anomaly_detected", {"node": node.id})
                    self._emit_log(f"🔍 Anomaly detected on {node.id} (rep={node.reputation:.0f})", "warning")
                changed = True
        if changed:
            self._emit_graph()

    # ── comms / metrics ───────────────────────────────────────────────────────
    def _simulate_comms(self):
        with self._lock:
            phase       = self._phase
            attack_type = None

            # Determine attack_type from any compromised node
            for nid in self._attack_node_ids:
                nd = self.nodes.get(nid)
                if nd and nd.attack_type:
                    attack_type = nd.attack_type
                    break

            # FIX: use _attack_node_ids (set immediately on launch)
            # instead of scanning node.status (lags by several ticks)
            all_metrics = {}
            for edge in self.edges:
                src = edge["source"]
                tgt = edge["target"]
                key = f"{src}-{tgt}"

                near = (src in self._attack_node_ids or tgt in self._attack_node_ids)

                em = self.edge_metrics.get(key)
                if em:
                    em.update(phase=phase, near_attack=near, attack_type=attack_type)
                    all_metrics[key] = em.to_dict()

        if all_metrics:
            self._emit("all_edge_metrics", all_metrics)

            # Log the worst edge during attack
            if phase == "attack":
                vals = list(all_metrics.values())
                near_vals = [v for v in vals
                             if v["source"] in self._attack_node_ids
                             or v["target"] in self._attack_node_ids]
                if near_vals:
                    worst = max(near_vals, key=lambda v: v["latency"])
                    self._emit_log(
                        f"⚡ {worst['source']}→{worst['target']} | "
                        f"lat={worst['latency']}ms bw={worst['bandwidth']:.1f}Mbps "
                        f"loss={worst['packet_loss']}% | LINK DEGRADED",
                        "warning",
                    )

    # ── healing / PBFT ────────────────────────────────────────────────────────
    def _detect_and_heal(self):
        self._set_phase("consensus")
        self._emit_log("🔐 PBFT consensus initiated — voting on quarantine", "info")
        threading.Timer(3.0, self._pbft_commit).start()

    def _pbft_commit(self):
        suspects = [n for n in self.nodes.values() if n.status in ("compromised", "suspect")]
        for node in suspects:
            self._quarantine(node.id)
        if suspects:
            self._set_phase("healing")
            threading.Timer(2.5, lambda: self._set_phase("idle")).start()
        else:
            self._set_phase("idle")

    def _quarantine(self, node_id: str):
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return
            node.status = "quarantined"
            for edge in self.edges:
                if edge["source"] == node_id or edge["target"] == node_id:
                    edge["active"] = False
            # Clear attack tracking once quarantined
            self._attack_node_ids.discard(node_id)
            if not self._attack_node_ids:
                self._attack_node_ids = set()

        self._emit("node_quarantined", {"node": node_id})
        self._emit_log(f"🔒 {node_id} QUARANTINED — links severed", "error")
        self._emit_graph()

    # ── helpers ───────────────────────────────────────────────────────────────
    def _set_phase(self, phase: str):
        self._phase = phase
        self._emit("phase_change", {"phase": phase})
        # Reset tick counters when leaving attack so idle math restarts cleanly
        if phase == "idle":
            self._attack_node_ids = set()
            for em in self.edge_metrics.values():
                em._tick = 0

    def _emit_log(self, msg: str, level: str = "info"):
        self._emit("log_event", {
            "message": msg, "level": level,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def _emit_graph(self):
        self._emit("graph_update", {
            "nodes": self._node_list(),
            "edges": self.edges,
        })

    def _node_list(self) -> list:
        return [
            {
                "id":         n.id,
                "status":     n.status,
                "reputation": round(n.reputation, 1),
                "block_count": len(n.chain),
                "peers":      n.peers,
                "attack_type": n.attack_type,
                "is_primary": (list(self.TOPOLOGY.keys())[self._primary_idx % 7] == n.id),
            }
            for n in self.nodes.values()
        ]

    def _stats(self) -> dict:
        compromised = [n.id for n in self.nodes.values() if n.status == "compromised"]
        total_txs   = sum(len(b.get("transactions", [])) for n in self.nodes.values()
                          for b in n.chain)
        return {
            "block_count":        self._total_blocks,
            "tx_rate":            random.randint(TX_RATE_BASE - 3, TX_RATE_BASE + 5),
            "total_transactions": total_txs,
            "compromised_nodes":  compromised,
            "phase":              self._phase,
        }