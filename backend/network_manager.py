"""
network_manager.py — Fully decentralised PBFT blockchain simulation.
Attacks: Byzantine Fault and DoS Flood.

KEY FIX: _simulate_comms now updates ALL edges every tick and emits a
single "all_edge_metrics" event with the full snapshot. Attack edges
(near compromised nodes) are always updated so degradation is visible.
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
# Comms tick: update all edges every N seconds
COMMS_TICK_IDLE      = 1.5   # seconds between full-network metric updates (idle)
COMMS_TICK_ATTACK    = 0.8   # faster during attack so degradation shows instantly
COMMS_TICK_CONSENSUS = 1.2
ATTACK_SECS     = 5

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


# ── EdgeMetrics ───────────────────────────────────────────────────────────────

class EdgeMetrics:
    """
    Tracks live network metrics for one edge.
    Latency, Bandwidth, Jitter, Round-Trip Time, Packet Loss.
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

    def update(self, phase: str, near_attack: bool, attack_type: str = None):
        """Recalculate all metrics. Called every tick regardless of node status."""
        self.message_count += 1
        self.bytes_sent    += random.randint(512, 8192)

        if phase == "idle":
            self.latency      = self.base_latency + random.uniform(-2, 6)
            self.bandwidth    = self.base_bandwidth + random.uniform(-8, 10)
            self.packet_loss  = random.uniform(0, 0.8)

        elif phase == "attack":
            if near_attack:
                if attack_type == "dos":
                    self.latency     = self.base_latency * random.uniform(6, 16)
                    self.bandwidth   = self.base_bandwidth * random.uniform(0.02, 0.15)
                    self.packet_loss = random.uniform(30, 70)
                elif attack_type == "byzantine":
                    self.latency     = self.base_latency * random.uniform(2, 5)
                    self.bandwidth   = self.base_bandwidth * random.uniform(0.40, 0.75)
                    self.packet_loss = random.uniform(8, 25)
                else:
                    self.latency     = self.base_latency * random.uniform(3, 8)
                    self.bandwidth   = self.base_bandwidth * random.uniform(0.20, 0.55)
                    self.packet_loss = random.uniform(15, 45)
            else:
                # Indirect congestion — still visibly worse than idle
                self.latency     = self.base_latency * random.uniform(1.3, 2.5)
                self.bandwidth   = self.base_bandwidth * random.uniform(0.70, 0.95)
                self.packet_loss = random.uniform(1, 8)

        elif phase == "consensus":
            self.latency     = self.base_latency * random.uniform(2.5, 5.5)
            self.bandwidth   = self.base_bandwidth * random.uniform(0.20, 0.45)
            self.packet_loss = random.uniform(3, 12)

        # Clamp
        self.latency     = round(max(1.0,  min(self.latency,    2500.0)), 1)
        self.bandwidth   = round(max(0.1,  min(self.bandwidth,   200.0)), 1)
        self.packet_loss = round(max(0.0,  min(self.packet_loss,  99.0)), 1)

        # Jitter = mean absolute deviation of recent latency readings
        self._latency_history.append(self.latency)
        if len(self._latency_history) > 1:
            readings = list(self._latency_history)
            avg = sum(readings) / len(readings)
            self.jitter = round(
                sum(abs(x - avg) for x in readings) / len(readings), 1
            )

        self.rtt = round((self.latency * 2) + random.uniform(0.5, 4.0), 1)

    def health_score(self) -> float:
        lat_score    = max(0, 100 - (self.latency / 25))
        bw_score     = (self.bandwidth / self.base_bandwidth) * 100
        loss_score   = max(0, 100 - (self.packet_loss * 3))
        jitter_score = max(0, 100 - (self.jitter * 4))
        return round(
            lat_score * 0.35 + bw_score * 0.30 +
            loss_score * 0.25 + jitter_score * 0.10, 1
        )

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
            "health":        self.health_score(),
            "message_count": self.message_count,
            "bytes_sent":    self.bytes_sent,
        }


# ── Node ──────────────────────────────────────────────────────────────────────

class Node:
    def __init__(self, node_id: str):
        self.id              = node_id
        self.type            = "validator"
        self.status          = "healthy"
        self.reputation      = INITIAL_REP
        self.is_primary      = False
        self.blockchain      = []
        self.block_count     = 0
        self.connected_peers = []
        self.last_seen       = time.time()
        self.attack_type     = None
        self._add_genesis()

    def _add_genesis(self):
        self.blockchain.append({
            "index":         0,
            "timestamp":     datetime.utcnow().isoformat(),
            "transactions":  [],
            "previous_hash": "0" * 64,
            "hash":          f"genesis_{self.id}",
            "proposer":      self.id,
            "round":         0,
        })
        self.block_count = 1

    def add_block(self, tx_count: int, round_num: int):
        prev  = self.blockchain[-1]
        block = {
            "index":         len(self.blockchain),
            "timestamp":     datetime.utcnow().isoformat(),
            "transactions":  [
                {
                    "tx_id":  f"tx_{random.randint(10000,99999)}",
                    "amount": round(random.uniform(0.1, 10.0), 4),
                    "from":   f"addr_{random.randint(100,999)}",
                    "to":     f"addr_{random.randint(100,999)}",
                }
                for _ in range(tx_count)
            ],
            "previous_hash": prev["hash"],
            "hash":          f"{self.id}_{len(self.blockchain)}_{random.randint(100000,999999)}",
            "proposer":      self.id,
            "round":         round_num,
        }
        self.blockchain.append(block)
        self.block_count += 1
        return block

    def drain_reputation(self, amount: float):
        self.reputation = max(0.0, self.reputation - amount)

    def restore(self):
        self.reputation  = INITIAL_REP
        self.status      = "healthy"
        self.attack_type = None
        self.is_primary  = False
        self.type        = "validator"

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "type":            self.type,
            "status":          self.status,
            "reputation":      round(self.reputation, 1),
            "is_primary":      self.is_primary,
            "block_count":     self.block_count,
            "connected_peers": self.connected_peers,
            "attack_type":     self.attack_type,
            "last_seen":       self.last_seen,
        }


# ── NetworkManager ────────────────────────────────────────────────────────────

class NetworkManager:

    def __init__(self):
        self._lock              = threading.Lock()
        self._pbft_cancel       = threading.Event()
        self.nodes              = {}
        self.edges              = []
        self.edge_metrics       = {}
        self.emit_cb            = None
        self._block_timer       = None
        self._comms_timer       = None
        self._tx_rate           = TX_RATE_BASE
        self._total_blocks      = 0
        self._round             = 0
        self._primary_idx       = 0
        self._attack_active     = False
        self._paused            = False
        self._compromised_nodes = set()
        self._phase             = "idle"

        self._build_network()
        self._start_miner()
        self._start_comms()

    def _build_network(self):
        for nid in ["N1","N2","N3","N4","N5","N6","N7"]:
            self.nodes[nid] = Node(nid)

        pairs = [
            ("N1","N2"),("N1","N3"),("N1","N4"),
            ("N2","N3"),("N2","N5"),
            ("N3","N6"),
            ("N4","N5"),("N4","N7"),
            ("N5","N6"),
            ("N6","N7"),
        ]
        for a, b in pairs:
            self.edges.append({"source": a, "target": b, "active": True})
            self.nodes[a].connected_peers.append(b)
            self.nodes[b].connected_peers.append(a)
            self.edge_metrics[f"{a}-{b}"] = EdgeMetrics(a, b)

        self._update_primary()
        self._emit_log("🟢 Decentralised network online — 7 validators, 10 edges", "success")
        self._emit_log("🔄 Primary rotates round-robin — no permanent leader", "info")

    def _healthy_nodes(self):
        return [n for n in self.nodes.values() if n.status == "healthy"]

    def _update_primary(self):
        healthy = self._healthy_nodes()
        if not healthy:
            return None
        for n in self.nodes.values():
            n.is_primary = False
            if n.type == "primary":
                n.type = "validator"
        self._primary_idx = self._primary_idx % len(healthy)
        p = healthy[self._primary_idx]
        p.is_primary = True
        p.type = "primary"
        return p

    # ── Miner ─────────────────────────────────────────────────────────────

    def _start_miner(self):
        self._schedule_mine()

    def _schedule_mine(self):
        if self._paused:        
            return
        t = threading.Timer(BLOCK_INTERVAL, self._mine_block)
        t.daemon = True
        self._block_timer = t
        t.start()

    def _mine_block(self):
        proposer_id = None
        block_num   = 0
        tx_count    = 0

        with self._lock:
            healthy = self._healthy_nodes()
            if healthy:
                primary = next((n for n in healthy if n.is_primary), healthy[0])
                tx_count           = random.randint(3, 8)
                self._round       += 1
                primary.add_block(tx_count=tx_count, round_num=self._round)
                self._total_blocks += 1
                self._tx_rate      = TX_RATE_BASE + random.randint(-2, 6)
                proposer_id        = primary.id
                block_num          = self._total_blocks
                self._primary_idx  = (self._primary_idx + 1) % len(healthy)
                for n in healthy:
                    n.is_primary = False
                    n.type       = "validator"
                nxt            = healthy[self._primary_idx % len(healthy)]
                nxt.is_primary = True
                nxt.type       = "primary"

        if proposer_id:
            self._emit_log(
                f"⛏  Block #{block_num} by {proposer_id} | "
                f"{tx_count} txs | {self._tx_rate} tx/s | round {self._round}",
                "block"
            )

        state = self._full_state()
        self._emit("graph_update", {"nodes": state["nodes"], "edges": state["edges"]})
        self._emit("stats_update", {
            "block_count":       state["block_count"],
            "tx_rate":           state["tx_rate"],
            "attack_active":     state["attack_active"],
            "compromised_nodes": state["compromised_nodes"],
        })
        self._schedule_mine()

    # ── Comms tick — THE KEY FIX ───────────────────────────────────────────
    # OLD: picked one random edge, skipped compromised nodes
    # NEW: updates ALL edges every tick, attack edges get degraded values

    def _start_comms(self):
        self._schedule_comms()

    def _schedule_comms(self):
        if self._paused:        
            return
        if self._phase == "attack":
            delay = COMMS_TICK_ATTACK
        elif self._phase == "consensus":
            delay = COMMS_TICK_CONSENSUS
        else:
            delay = COMMS_TICK_IDLE + random.uniform(-0.2, 0.3)

        t = threading.Timer(delay, self._simulate_comms)
        t.daemon = True
        self._comms_timer = t
        t.start()

    def _simulate_comms(self):
        with self._lock:
            compromised = {
                nid for nid, n in self.nodes.items()
                if n.status in ("compromised", "quarantined")
            }
            attack_type = None
            for nid in compromised:
                nd = self.nodes.get(nid)
                if nd and nd.attack_type:
                    attack_type = nd.attack_type
                    break
            block_num = self._total_blocks
            phase     = self._phase

            # ── Update ALL edges every tick ────────────────────────────────
            all_metrics = {}
            for edge in self.edges:
                src = edge["source"]
                tgt = edge["target"]
                key = f"{src}-{tgt}"

                # An edge is "near attack" if either endpoint is compromised
                near = (src in compromised or tgt in compromised)

                metrics = self.edge_metrics.get(key)
                if metrics:
                    metrics.update(
                        phase=phase,
                        near_attack=near,
                        attack_type=attack_type
                    )
                    all_metrics[key] = metrics.to_dict()

        # Emit one event with the FULL metrics snapshot
        # Frontend receives all 10 edges at once → accurate averages immediately
        if all_metrics:
            self._emit("all_edge_metrics", all_metrics)

        # One representative log line
        if all_metrics:
            vals = list(all_metrics.values())
            sample = random.choice(vals)
            src, tgt = sample["source"], sample["target"]

            if phase == "attack" and compromised:
                near_samples = [v for v in vals
                                if v["source"] in compromised or v["target"] in compromised]
                if near_samples:
                    worst = max(near_samples, key=lambda v: v["latency"])
                    self._emit_log(
                        f"⚡ {worst['source']}→{worst['target']} | "
                        f"lat={worst['latency']}ms rtt={worst['rtt']}ms "
                        f"bw={worst['bandwidth']}Mbps loss={worst['packet_loss']}% | DEGRADED",
                        "warning"
                    )
                else:
                    self._emit_log(
                        f"🔍 anomaly scan | avg-lat={_avg(vals,'latency'):.1f}ms "
                        f"avg-loss={_avg(vals,'packet_loss'):.1f}%", "warning"
                    )
            else:
                msg = random.choice(PEER_MESSAGES).format(
                    node=src, peer=tgt,
                    block=block_num, tx=random.randint(1, 9), lat=round(sample["latency"])
                )
                self._emit_log(
                    f"{msg} | lat={sample['latency']}ms rtt={sample['rtt']}ms "
                    f"bw={sample['bandwidth']}Mbps jitter={sample['jitter']}ms",
                    "info"
                )

        self._schedule_comms()

    # ── Public API ────────────────────────────────────────────────────────

    def get_network_state(self):
        with self._lock:
            return self._full_state()

    def get_chain(self, node_id):
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return {"error": f"Node {node_id} not found"}
            return {"node_id": node_id, "block_count": node.block_count,
                    "chain": node.blockchain}

    def get_metrics(self):
        with self._lock:
            return {k: v.to_dict() for k, v in self.edge_metrics.items()}

    def trigger_attack(self, attack_type: str, target_id: str):
        if attack_type not in ("byzantine", "dos"):
            attack_type = "byzantine"
        with self._lock:
            node = self.nodes.get(target_id)
            if not node:
                return {"error": f"Node {target_id} not found"}
            if node.status == "quarantined":
                return {"error": f"{target_id} already quarantined"}
            node.status         = "compromised"
            node.attack_type    = attack_type
            node.type           = "compromised"
            node.is_primary     = False
            self._compromised_nodes.add(target_id)
            self._attack_active = True
            self._phase         = "attack"

        self._emit("attack_started", {"type": attack_type, "target_id": target_id,
                                      "timestamp": _ts()})
        self._emit("phase_change", {"phase": "attack"})
        self._emit_log(
            f"🚨 {attack_type.upper()} ATTACK on {target_id} — node compromised!", "error"
        )
        self._push_update()
        threading.Thread(
            target=self._attack_then_pbft, args=(attack_type, target_id), daemon=True
        ).start()
        return {"status": "attack_started", "type": attack_type, "target": target_id}

    def trigger_heal(self):
        with self._lock:
            suspects = [nid for nid, n in self.nodes.items()
                        if n.status in ("suspect", "compromised")]
        for nid in suspects:
            threading.Thread(target=self._pbft_round, args=(nid,), daemon=True).start()
        return {"status": "healing_started", "targets": suspects}

    def reset_network(self):
        if self._block_timer:  self._block_timer.cancel()
        if self._comms_timer:  self._comms_timer.cancel()
        with self._lock:
            for node in self.nodes.values():
                node.restore()
            for edge in self.edges:
                edge["active"] = True
            for key in list(self.edge_metrics.keys()):
                parts = key.split("-")
                self.edge_metrics[key] = EdgeMetrics(parts[0], parts[1])
            self._compromised_nodes.clear()
            self._attack_active  = False
            self._total_blocks   = 0
            self._round          = 0
            self._primary_idx    = 0
            self._phase          = "idle"
            self.nodes["N1"].is_primary = True
            self.nodes["N1"].type       = "primary"

        self._push_update()
        self._emit("phase_change", {"phase": "idle"})
        self._emit_log("🔄 NETWORK RESET — 7 validators restored", "success")
        self._start_miner()
        self._start_comms()
        return {"status": "reset_complete"}
    
    def pause_network(self):
        with self._lock:
            if self._paused:
                return {"status": "already_paused"}
            self._paused = True
            self._phase  = "paused"

        if self._block_timer:
            self._block_timer.cancel()
        if self._comms_timer:
            self._comms_timer.cancel()

        self._emit("phase_change", {"phase": "paused"})
        self._emit_log("⏸  NETWORK PAUSED — all simulation timers halted", "warning")
        self._push_update()
        return {"status": "paused"}

    def resume_network(self):
        with self._lock:
            if not self._paused:
                return {"status": "not_paused"}
            self._paused = False
            self._phase  = "idle"

        self._emit("phase_change", {"phase": "idle"})
        self._emit_log("▶  NETWORK RESUMED — simulation restarted", "success")
        self._push_update()
        self._start_miner()
        self._start_comms()
        return {"status": "resumed"}

    # ── Attack sequence ───────────────────────────────────────────────────

    def _attack_then_pbft(self, attack_type: str, target_id: str):
        drain = REP_DRAIN_BYZ if attack_type == "byzantine" else REP_DRAIN_DOS
        delay = ATTACK_SECS / 5
        for step in range(5):
            time.sleep(delay)
            with self._lock:
                node = self.nodes.get(target_id)
                if not node or node.status == "quarantined":
                    return
                node.drain_reputation(drain * (0.5 if step < 2 else 1.0))
                rep    = node.reputation
                hash_a = f"{random.randint(0xa000,0xffff):04x}{random.randint(0,0xffff):04x}"
                hash_b = f"{random.randint(0xa000,0xffff):04x}{random.randint(0,0xffff):04x}"
            self._emit("anomaly_detected", {"node_id": target_id,
                "reason": f"{attack_type} behaviour", "rep_score": round(rep, 1)})
            self._push_update()
            if attack_type == "byzantine":
                self._emit_log(
                    f"⚠  {target_id} | expected={hash_a} got={hash_b} | "
                    f"rep={round(rep,1)} | CONFLICTING BLOCK HASH", "warning"
                )
            else:
                self._emit_log(
                    f"⚠  {target_id} | tx_flood | rep={round(rep,1)} | "
                    f"BANDWIDTH SATURATED", "warning"
                )
        self._emit_log(
            f"🤖 Anomaly confirmed — PBFT triggered for {target_id}", "error"
        )
        time.sleep(0.4)
        self._phase = "consensus"
        self._emit("phase_change", {"phase": "consensus"})
        self._pbft_round(target_id)

    # ── PBFT ──────────────────────────────────────────────────────────────

    def _pbft_round(self, target_id: str):
        self._pbft_cancel.clear()
        with self._lock:
            voters = [nid for nid, n in self.nodes.items()
                    if nid != target_id and n.status == "healthy"]
            total = len(voters)
        if total == 0:
            return
        quorum = int(total * PBFT_QUORUM) + 1
        random.shuffle(voters)

        accuser = voters[0]
        self._emit_log(f"📡 PRE-PREPARE: {accuser} broadcasts accusation → {target_id}", "info")
        self._emit_log(f"   {total} validators initiating verification", "info")

        for _ in range(4):
            if self._pbft_cancel.is_set(): return
            time.sleep(0.1)

        prepare_acks = 0
        self._emit_log(f"📋 PREPARE: validators cross-checking {target_id}", "info")
        for vid in voters:
            if self._pbft_cancel.is_set(): return
            time.sleep(0.2)
            ack = random.random() < 0.92
            if ack:
                prepare_acks += 1
            self._emit_log(
                f"  {'✔' if ack else '✘'} {vid} prepare-ack | {prepare_acks}/{total}", "info"
            )

        if prepare_acks < quorum:
            self._emit_log(f"⚠  Prepare failed — {target_id} marked SUSPECT", "warning")
            with self._lock:
                node = self.nodes.get(target_id)
                if node and node.status != "quarantined":
                    node.status = "suspect"
            self._phase = "idle"
            self._emit("phase_change", {"phase": "idle"})
            self._push_update()
            return

        self._emit_log(f"🔐 COMMIT: {prepare_acks} validators committing verdict on {target_id}", "info")
        commit_votes = 0
        for vid in voters:
            if self._pbft_cancel.is_set(): return
            time.sleep(0.3)
            vote = "quarantine" if random.random() < 0.88 else "abstain"
            if vote == "quarantine":
                commit_votes += 1
            self._emit("vote_cast", {"voter_id": vid, "target_id": target_id,
                "vote": vote, "count": commit_votes, "total": total})
            self._emit("consensus_votes", {target_id: {
                "count": commit_votes, "total": total,
                "needed": quorum, "vote": vote}})
            self._emit_log(
                f"  {'✅' if vote=='quarantine' else '⬜'} {vid} → {vote.upper()} | {commit_votes}/{quorum}",
                "info"
            )
            if commit_votes >= quorum:
                if not self._pbft_cancel.is_set():
                    self._quarantine(target_id)
                return

        if not self._pbft_cancel.is_set():
            with self._lock:
                node = self.nodes.get(target_id)
                if node and node.status != "quarantined":
                    node.status = "suspect"
            self._phase = "idle"
            self._emit("phase_change", {"phase": "idle"})
            self._push_update()
            self._emit_log(f"⚠  Commit quorum not reached — {target_id} SUSPECT", "warning")

    # ── Quarantine ────────────────────────────────────────────────────────

    def _quarantine(self, node_id: str):
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return
            was_primary     = node.is_primary
            node.status     = "quarantined"
            node.type       = "quarantined"
            node.is_primary = False
            for edge in self.edges:
                if edge["source"] == node_id or edge["target"] == node_id:
                    edge["active"] = False
            self._compromised_nodes.discard(node_id)
            self._attack_active = len(self._compromised_nodes) > 0

        self._emit("node_quarantined", {"node_id": node_id, "timestamp": _ts()})
        self._emit_log(f"🔒 {node_id} QUARANTINED by PBFT consensus", "error")
        self._emit_log(f"   No votes · no proposals · read-only", "warning")
        self._push_update()

        if was_primary:
            time.sleep(0.4)
            with self._lock:
                healthy = self._healthy_nodes()
                if healthy:
                    for n in healthy:
                        n.is_primary = False
                        n.type = "validator"
                    self._primary_idx = self._primary_idx % len(healthy)
                    nxt = healthy[self._primary_idx % len(healthy)]
                    nxt.is_primary = True
                    nxt.type = "primary"
                    nxt_id = nxt.id
            self._emit_log(f"🔄 Primary rotated to {nxt_id}", "success")
            self._push_update()

        healthy_count = sum(1 for n in self.nodes.values() if n.status == "healthy")
        self._phase = "idle"
        self._emit("phase_change", {"phase": "idle"})
        self._emit("network_healed", {"timestamp": _ts(),
                                      "operational_nodes": healthy_count})
        self._emit_log(
            f"✅ Network healed — {healthy_count}/7 validators operational", "success"
        )
        self._push_update()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _push_update(self):
        state = self._full_state()
        self._emit("graph_update", {"nodes": state["nodes"], "edges": state["edges"]})
        self._emit("stats_update", {
            "block_count":       state["block_count"],
            "tx_rate":           state["tx_rate"],
            "attack_active":     state["attack_active"],
            "compromised_nodes": state["compromised_nodes"],
        })

    def _full_state(self):
        return {
            "nodes":             [n.to_dict() for n in self.nodes.values()],
            "edges":             self.edges,
            "block_count":       self._total_blocks,
            "tx_rate":           self._tx_rate,
            "attack_active":     self._attack_active,
            "compromised_nodes": list(self._compromised_nodes),
            "timestamp":         _ts(),
        }

    def _emit(self, event: str, payload: dict):
        if self.emit_cb:
            try:
                self.emit_cb(event, payload)
            except Exception:
                pass

    def _emit_log(self, msg: str, log_type: str = "info"):
        self._emit("log_event", {"message": msg, "type": log_type,
                                  "timestamp": _ts()})


def _avg(items: list, key: str) -> float:
    return sum(i[key] for i in items) / len(items) if items else 0.0


def _ts():
    return datetime.utcnow().isoformat() + "Z"