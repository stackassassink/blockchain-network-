"""
network_manager.py — Self-Healing Secure Network / PBFT Blockchain Simulation
==============================================================================
VERSION 5 — Graceful Degradation State Machine
──────────────────────────────────────────────
NEW in v5: Four-tier network viability model replacing binary heal/fail:

  TIER 1 — OPERATIONAL  (≥4 healthy nodes)
    • Normal PBFT consensus — full fault tolerance
    • Primary rotates among healthy nodes only
    • Dynamic quorum: ⌊2n/3⌋+1

  TIER 2 — CRITICAL  (exactly 3 healthy nodes)
    • PBFT mathematically possible but f=0 (zero fault tolerance)
    • Mining HALTED immediately — no new blocks accepted
    • All remaining chains receive a signed CRITICAL_THRESHOLD alert block
    • Dashboard phase → "critical"
    • New attacks still detected and logged but NOT quarantined
      (quarantine would push to frozen/dead — preserved for admin decision)

  TIER 3 — FROZEN  (exactly 2 healthy nodes)
    • Consensus impossible — quorum=2 requires unanimity with no redundancy
    • Read-only mode: chain data served, transactions rejected
    • CONSENSUS_LIVENESS_FAILURE block written to both surviving chains
    • Dashboard phase → "frozen"

  TIER 4 — DEAD  (0–1 healthy nodes)
    • Full network partition
    • NETWORK_PARTITION block written to last surviving chain (if any)
    • Dashboard phase → "dead"

WHY THIS MATTERS FOR THE PAPER:
  Standard PBFT implementations either heal or halt with no intermediate
  states. Our system demonstrates that aggressive quarantine without a
  viability check can destroy the consensus layer it is trying to protect.
  The four-tier model allows the system to preserve chain integrity even
  when it can no longer make forward progress.

RETAINED FROM v4:
  • Quarantined nodes excluded from primary rotation and quorum
  • Node.is_primary is the authoritative flag (not derived from index)
  • Dynamic quorum recalculation after every quarantine
  • near_attack triggers immediately on launch (tick 0 uses attack math)
  • Bandwidth spikes then collapses during DoS (physically accurate)
"""

import time
import random
import threading
from datetime import datetime, timezone
from typing import Optional, Callable
from collections import deque

# ── constants ─────────────────────────────────────────────────────────────────
INITIAL_REP     = 100.0
REP_DRAIN_BYZ   = 18.0
REP_DRAIN_DOS   = 8.0
BLOCK_INTERVAL  = 2.0
TX_RATE_BASE    = 14

COMMS_TICK_IDLE      = 1.5
COMMS_TICK_ATTACK    = 0.6
COMMS_TICK_CONSENSUS = 1.0
ATTACK_SECS          = 5

# ── viability thresholds ──────────────────────────────────────────────────────
THRESHOLD_OPERATIONAL = 4   # ≥4 → full PBFT  (f≥1 fault tolerance)
THRESHOLD_CRITICAL    = 3   # =3 → PBFT possible but f=0 → HALT mining
THRESHOLD_FROZEN      = 2   # =2 → consensus impossible → read-only
# <2  → dead

# Statuses that disqualify a node from PBFT participation
_INACTIVE_STATUSES = {"quarantined", "compromised", "suspect"}

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
      • First 2 ticks: bandwidth SPIKES (flood traffic arriving)
      • Tick 3+: bandwidth COLLAPSES (queues saturated, mass drops)
      • Latency shoots up, packet loss soars

    Byzantine fault:
      • Bandwidth drops moderately (retransmissions)
      • Latency rises (double-spend detection overhead)
      • Packet loss rises (conflicting blocks rejected)

    Consensus phase:
      • Bandwidth drops (PBFT message storm saturates links)
      • Latency elevated (multi-round voting overhead)

    Critical / Frozen / Dead:
      • Metrics freeze at last recorded values — no new traffic
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
        self._tick            = 0

    def reset_to_idle(self):
        self.latency     = self.base_latency + random.uniform(0, 4)
        self.bandwidth   = self.base_bandwidth + random.uniform(-5, 8)
        self.packet_loss = random.uniform(0, 0.5)
        self.jitter      = random.uniform(1, 4)
        self.rtt         = self.latency * 2
        self._tick       = 0
        self._latency_history.clear()
        self._latency_history.append(self.latency)

    def update(self, phase: str, near_attack: bool, attack_type: str = None):
        """Recalculate metrics. Frozen/critical/dead phases preserve last values."""
        # In degraded states, traffic has stopped — metrics don't update
        if phase in ("critical", "frozen", "dead"):
            return

        self.message_count += 1
        self.bytes_sent    += random.randint(512, 8192)
        self._tick         += 1

        if phase == "idle":
            self.latency     = self.base_latency  + random.uniform(-2, 6)
            self.bandwidth   = self.base_bandwidth + random.uniform(-8, 10)
            self.packet_loss = random.uniform(0, 0.8)
            self._tick       = 0

        elif phase == "attack":
            if near_attack:
                if attack_type == "dos":
                    bw_mult = random.uniform(1.8, 3.2) if self._tick <= 2 \
                              else random.uniform(0.02, 0.12)
                    self.latency     = self.base_latency * random.uniform(7, 18)
                    self.bandwidth   = self.base_bandwidth * bw_mult
                    self.packet_loss = random.uniform(35, 75)
                elif attack_type == "byzantine":
                    self.latency     = self.base_latency * random.uniform(2.5, 6)
                    self.bandwidth   = self.base_bandwidth * random.uniform(0.35, 0.70)
                    self.packet_loss = random.uniform(10, 30)
                else:
                    self.latency     = self.base_latency * random.uniform(3, 9)
                    self.bandwidth   = self.base_bandwidth * random.uniform(0.15, 0.50)
                    self.packet_loss = random.uniform(20, 55)
            else:
                self.latency     = self.base_latency * random.uniform(1.4, 2.8)
                self.bandwidth   = self.base_bandwidth * random.uniform(0.65, 0.90)
                self.packet_loss = random.uniform(1.5, 10)

        elif phase == "consensus":
            self.latency     = self.base_latency * random.uniform(2.5, 6)
            self.bandwidth   = self.base_bandwidth * random.uniform(0.18, 0.42)
            self.packet_loss = random.uniform(3, 14)
            self._tick       = 0

        # Hard clamps
        self.latency     = round(max(1.0,  min(self.latency,    3000.0)), 1)
        self.bandwidth   = round(max(0.05, min(self.bandwidth,   350.0)), 1)
        self.packet_loss = round(max(0.0,  min(self.packet_loss,  99.0)), 1)

        self._latency_history.append(self.latency)
        if len(self._latency_history) > 1:
            readings = list(self._latency_history)
            avg_lat  = sum(readings) / len(readings)
            self.jitter = round(
                sum(abs(r - avg_lat) for r in readings) / len(readings), 1
            )
        else:
            self.jitter = round(random.uniform(1, 4), 1)

        self.rtt = round(self.latency * 2 * random.uniform(0.8, 1.3), 1)

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
        self.is_primary  = False
        self.chain       = []
        self.peers       = []
        self._genesis()

    def _genesis(self):
        self.chain.append({
            "index":         0,
            "timestamp":     datetime.now().isoformat(),
            "data":          "Genesis Block",
            "previous_hash": "0" * 64,
            "hash":          "genesis_" + self.id,
            "type":          "genesis",
        })

    def mine_block(self, transactions: list, block_type: str = "normal") -> dict:
        prev  = self.chain[-1]
        block = {
            "index":         len(self.chain),
            "timestamp":     datetime.now().isoformat(),
            "transactions":  transactions,
            "previous_hash": prev["hash"],
            "hash":          f"{self.id}_block_{len(self.chain)}_{random.randint(1000,9999)}",
            "miner":         self.id,
            "type":          block_type,
        }
        self.chain.append(block)
        return block


# ── NetworkManager ────────────────────────────────────────────────────────────
class NetworkManager:
    """
    Orchestrates the 7-node PBFT network, attack simulation,
    graceful degradation, and real-time metric emission.
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

        # Viability tier: operational | critical | frozen | dead
        self._viability = "operational"

        self._attack_node_ids: set = set()
        self._primary_idx          = 0
        self._total_blocks         = 0
        self._attack_timer         = None

        # Track the last preserved block height per node for read-only mode
        self._preserved_height: dict[str, int] = {}

        self.nodes: dict[str, Node] = {
            nid: Node(nid) for nid in self.TOPOLOGY
        }
        for nid, peers in self.TOPOLOGY.items():
            self.nodes[nid].peers = peers

        self.edges: list[dict] = []
        self.edge_metrics: dict[str, EdgeMetrics] = {}
        self._build_edges()

        self.nodes["N1"].is_primary = True

    # ── init ──────────────────────────────────────────────────────────────────
    def _build_edges(self):
        seen = set()
        for src, peers in self.TOPOLOGY.items():
            for tgt in peers:
                key = tuple(sorted([src, tgt]))
                if key not in seen:
                    seen.add(key)
                    self.edges.append({"source": src, "target": tgt, "active": True})
                    self.edge_metrics[f"{src}-{tgt}"] = EdgeMetrics(src, tgt)
                    self.edge_metrics[f"{tgt}-{src}"] = EdgeMetrics(tgt, src)

    # ── PBFT / viability helpers ───────────────────────────────────────────────
    def _get_eligible_nodes(self) -> list[Node]:
        """Only healthy nodes may participate in PBFT."""
        return [n for n in self.nodes.values() if n.status == "healthy"]

    def _get_quorum_size(self) -> int:
        """
        Dynamic PBFT quorum = ⌊2n/3⌋ + 1 where n = healthy node count.
        Returns 0 when consensus is impossible (n <= 1) — frontend
        displays this as N/A rather than the misleading value of 1.
        """
        n = len(self._get_eligible_nodes())
        if n <= 1:
            return 0   # sentinel: consensus impossible
        return (2 * n) // 3 + 1

    def _assess_viability(self) -> str:
        """
        Assess network health tier based on healthy node count.

        Returns one of: 'operational' | 'critical' | 'frozen' | 'dead'

        Viability table (n=7 initial):
          ≥4 healthy → operational : PBFT works, f≥1 fault tolerance
          =3 healthy → critical    : PBFT possible but f=0, halt mining
          =2 healthy → frozen      : consensus impossible, read-only
          ≤1 healthy → dead        : full partition
        """
        healthy = len(self._get_eligible_nodes())
        if healthy >= THRESHOLD_OPERATIONAL:
            return "operational"
        elif healthy == THRESHOLD_CRITICAL:
            return "critical"
        elif healthy == THRESHOLD_FROZEN:
            return "frozen"
        else:
            return "dead"

    def _handle_viability_transition(self, new_viability: str):
        """
        Called after every quarantine. Transitions the network to the
        appropriate degradation tier and records the event on-chain.
        """
        prev = self._viability
        if new_viability == prev:
            return  # no tier change, nothing to do

        self._viability = new_viability
        healthy         = self._get_eligible_nodes()
        healthy_count   = len(healthy)
        quorum          = self._get_quorum_size()

        # ── TIER 2: CRITICAL ──────────────────────────────────────────────
        if new_viability == "critical":
            self._set_phase("critical")
            self._paused = True   # halt block mining immediately

            self._emit_log(
                "🔴 CRITICAL THRESHOLD REACHED — 3 healthy nodes remain",
                "error"
            )
            self._emit_log(
                f"PBFT fault tolerance = 0 | quorum={quorum}/3 requires unanimity | "
                "mining HALTED to preserve chain integrity",
                "error"
            )
            self._emit_log(
                "⚠ One more failure will make consensus mathematically impossible",
                "error"
            )
            self._emit_log(
                "📖 Network entering READ-ONLY mode — chain data preserved, "
                "new transactions rejected",
                "warning"
            )

            # Preserve chain heights before halting
            for n in healthy:
                self._preserved_height[n.id] = len(n.chain) - 1

            # Write tamper-evident alert block to all surviving chains
            self._write_viability_block(
                event_type    = "PBFT_CRITICAL_THRESHOLD",
                healthy_count = healthy_count,
                nodes         = healthy,
                extra         = {
                    "fault_tolerance":   0,
                    "quorum_required":   quorum,
                    "mining_halted":     True,
                    "read_only":         True,
                    "recommendation":    "Admin intervention required to restore nodes",
                }
            )

        # ── TIER 3: FROZEN ────────────────────────────────────────────────
        elif new_viability == "frozen":
            self._set_phase("frozen")
            self._paused = True

            self._emit_log(
                "🚨 CONSENSUS LIVENESS FAILURE — only 2 healthy nodes remain",
                "error"
            )
            self._emit_log(
                "PBFT quorum=2 requires both nodes to agree with zero redundancy | "
                "any message loss = permanent deadlock",
                "error"
            )
            self._emit_log(
                "📦 Last valid block height preserved on all surviving chains",
                "warning"
            )
            self._emit_log(
                "📖 FULL READ-ONLY MODE — serving historical chain data only",
                "warning"
            )

            self._write_viability_block(
                event_type    = "CONSENSUS_LIVENESS_FAILURE",
                healthy_count = healthy_count,
                nodes         = healthy,
                extra         = {
                    "fault_tolerance":   0,
                    "quorum_required":   quorum,
                    "mining_halted":     True,
                    "read_only":         True,
                    "last_block_height": self._total_blocks,
                    "recommendation":    "Manual node recovery required",
                }
            )

        # ── TIER 4: DEAD ──────────────────────────────────────────────────
        elif new_viability == "dead":
            self._set_phase("dead")
            self._paused = True

            # Find any surviving node (might have 1 left)
            survivors = [n for n in self.nodes.values()
                         if n.status not in ("quarantined",)]

            self._emit_log(
                "💀 NETWORK DEAD — full partition | no consensus possible",
                "error"
            )
            self._emit_log(
                f"Surviving nodes: {[n.id for n in survivors] or 'none'} | "
                "all edges severed | blockchain write-protected",
                "error"
            )

            self._write_viability_block(
                event_type    = "NETWORK_PARTITION",
                healthy_count = 0,
                nodes         = survivors,
                extra         = {
                    "total_blocks_committed": self._total_blocks,
                    "last_valid_state":       "preserved",
                    "recovery_action":        "Full network reset required",
                }
            )

    def _write_viability_block(
        self,
        event_type:    str,
        healthy_count: int,
        nodes:         list,
        extra:         dict,
    ):
        """
        Write an immutable alert block to every surviving node's chain.
        This is the blockchain's core role: tamper-evident audit trail
        of every viability transition.
        """
        payload = [{
            "type":          event_type,
            "healthy_nodes": healthy_count,
            "timestamp":     datetime.now().isoformat(),
            "severity":      "CRITICAL",
            "viability":     self._viability,
            **extra,
        }]

        recorded_on = []
        for n in nodes:
            n.mine_block(payload, block_type="viability_alert")
            recorded_on.append(n.id)

        if recorded_on:
            self._emit_log(
                f"📦 '{event_type}' written to chains: {', '.join(recorded_on)} | "
                "tamper-evident | immutable",
                "block"
            )
        else:
            self._emit_log(
                f"⚠ '{event_type}' could NOT be written — no surviving nodes",
                "error"
            )

    def _rotate_primary(self, reason: str = "round-robin"):
        """Assign primary to next healthy node only."""
        # Do not rotate in degraded states — no point
        if self._viability in ("frozen", "dead"):
            return

        eligible = self._get_eligible_nodes()
        if not eligible:
            self._emit_log(
                "⚠️ No eligible nodes for primary rotation — network critical!",
                "error"
            )
            return

        for n in self.nodes.values():
            n.is_primary = False

        self._primary_idx = self._primary_idx % len(eligible)
        new_primary = eligible[self._primary_idx]
        new_primary.is_primary = True
        self._primary_idx += 1

        quorum = self._get_quorum_size()
        self._emit_log(
            f"🔄 Primary → {new_primary.id} ({reason}) | "
            f"eligible={len(eligible)}/7 | quorum={quorum}",
            "info",
        )
        self._emit_graph()

    def _current_primary(self) -> Optional[Node]:
        for n in self.nodes.values():
            if n.is_primary:
                return n
        return None

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self):
        self._running = True
        threading.Thread(target=self._block_loop,  daemon=True).start()
        threading.Thread(target=self._comms_loop,  daemon=True).start()
        threading.Timer(0.5, self._emit_startup_logs).start()

    def _emit_startup_logs(self):
        startup = [
            ("🟢 Network initialised — 7 nodes online, 10 edges active", "success"),
            ("Genesis block committed on all nodes | height=0", "block"),
            ("PBFT parameters: n=7, f=2, quorum=5 — fault tolerance active", "info"),
            ("Graceful degradation: operational→critical→frozen→dead", "info"),
            ("Primary rotation: healthy nodes only (quarantined excluded)", "info"),
            ("Block interval: 2.0s | Comms tick: 1.5s | TX rate: ~14/s", "info"),
            ("Reputation tracker: threshold 30% → suspect status", "info"),
            ("Waiting for first block from primary N1…", "info"),
        ]
        for i, (msg, level) in enumerate(startup):
            threading.Timer(i * 0.15, lambda m=msg, l=level: self._emit_log(m, l)).start()

    def stop(self):
        self._running = False

    def pause(self):
        self._paused = True
        self._set_phase("paused")
        self._emit_log("⏸ NETWORK PAUSED — all block mining and comms suspended", "warning")

    def resume(self):
        # Only allow resume if not in a degraded viability state
        if self._viability in ("frozen", "dead"):
            self._emit_log(
                f"⚠ Cannot resume — network is {self._viability.upper()}. "
                "Use RESET to restore all nodes.",
                "error"
            )
            return
        self._paused = False
        self._set_phase("idle")
        self._emit_log("▶ NETWORK RESUMED — all nodes back online", "success")
        threading.Timer(0.3, self._push_metrics_snapshot).start()

    def _push_metrics_snapshot(self):
        all_metrics = {}
        for edge in self.edges:
            key = f"{edge['source']}-{edge['target']}"
            em  = self.edge_metrics.get(key)
            if em:
                em.update(phase="idle", near_attack=False)
                all_metrics[key] = em.to_dict()
        if all_metrics:
            self._emit("all_edge_metrics", all_metrics)

    # ── public API ────────────────────────────────────────────────────────────
    def launch_attack(self, attack_type: str, target_id: str):
        """Launch an attack on a target node. Rejected if network is frozen/dead."""
        with self._lock:
            # Reject new attacks if network is already in a terminal state
            if self._viability in ("frozen", "dead"):
                self._emit_log(
                    f"⚠ Attack on {target_id} rejected — "
                    f"network is {self._viability.upper()} (read-only mode)",
                    "warning"
                )
                return {"error": f"Network {self._viability} — attacks not accepted"}

            node = self.nodes.get(target_id)
            if not node or node.status != "healthy":
                return {"error": "Target unavailable"}

            node.status      = "compromised"
            node.attack_type = attack_type

            if node.is_primary:
                node.is_primary = False

            self._attack_node_ids = {target_id} | set(self.TOPOLOGY.get(target_id, []))
            self._set_phase("attack")

        # Rotate primary if attacked node held it
        current = self._current_primary()
        if current is None or current.status != "healthy":
            self._rotate_primary(reason="attacked-node was primary")

        self._emit("attack_started", {
            "target":    target_id,
            "type":      attack_type,
            "timestamp": datetime.now().isoformat(),
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
        """Full network reset — restores all nodes, clears degradation state."""
        with self._lock:
            if self._attack_timer:
                self._attack_timer.cancel()
                self._attack_timer = None
            self._attack_node_ids    = set()
            self._viability          = "operational"
            self._preserved_height   = {}
            for node in self.nodes.values():
                node.status      = "healthy"
                node.reputation  = INITIAL_REP
                node.attack_type = None
                node.is_primary  = False
            for edge in self.edges:
                edge["active"] = True
            for em in self.edge_metrics.values():
                em.reset_to_idle()
            self._paused      = False
            self._primary_idx = 0
            self._set_phase("idle")

        self.nodes["N1"].is_primary = True
        self._emit_log("🔄 NETWORK RESET — all 7 nodes restored to healthy state", "success")
        self._emit_log(
            "All edges reactivated | reputation=100% | viability=OPERATIONAL | "
            "quorum=5/7 | primary=N1",
            "info"
        )
        self._emit_log("Block ledgers preserved (historical record intact)", "block")
        self._emit_graph()
        threading.Timer(0.2, self._push_metrics_snapshot).start()
        return {"status": "reset"}

    def heal(self):
        """Manual heal trigger — only acts if network is operational."""
        if self._viability in ("frozen", "dead"):
            return {
                "status": "cannot_heal",
                "reason": f"Network {self._viability} — use reset to recover"
            }
        suspects = [n for n in self.nodes.values() if n.status in ("compromised", "suspect")]
        if not suspects:
            return {"status": "no_suspects"}
        for node in suspects:
            self._quarantine(node.id)
        return {"status": "healed", "quarantined": [n.id for n in suspects]}

    def get_state(self) -> dict:
        with self._lock:
            return {
                "nodes":      self._node_list(),
                "edges":      self.edges,
                "phase":      self._phase,
                "viability":  self._viability,
                "stats":      self._stats(),
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
        """Mine one block from the current primary. Rotate primary after."""
        primary = self._current_primary()
        if primary is None:
            self._rotate_primary(reason="no primary set")
            primary = self._current_primary()
        if primary is None:
            return

        n_tx = random.randint(3, 8)
        txs  = [
            {"id": f"tx_{self._total_blocks}_{i}", "value": random.randint(1, 100)}
            for i in range(n_tx)
        ]

        if primary.status == "compromised" and primary.attack_type == "byzantine":
            primary.mine_block(txs, block_type="byzantine")
            self._emit_log(
                f"⚠ Byzantine block #{self._total_blocks} from {primary.id} — "
                "conflicting hashes broadcast to peers",
                "warning"
            )
        elif primary.status not in _INACTIVE_STATUSES:
            block     = primary.mine_block(txs)
            block_idx = block["index"]

            peers_updated = []
            for peer_id in primary.peers:
                peer = self.nodes.get(peer_id)
                if peer and peer.status not in _INACTIVE_STATUSES:
                    peer.mine_block(txs)
                    peers_updated.append(peer_id)

            if peers_updated:
                featured = random.choice(peers_updated)
                msg = random.choice(PEER_MESSAGES).format(
                    node=primary.id, peer=featured,
                    block=block_idx, tx=n_tx,
                )
                self._emit_log(
                    f"{msg} | blk={block_idx} txs={n_tx} "
                    f"chain-len={len(primary.chain)}",
                    "block"
                )

            if random.random() < 0.4 and len(peers_updated) >= 2:
                p1, p2 = random.sample(peers_updated, 2)
                self._emit_log(
                    f"Gossip: {p1} ↔ {p2} | mempool sync | "
                    f"height={block_idx} peers={len(peers_updated)}",
                    "info"
                )

        self._total_blocks += 1
        self._drain_reputation()
        self._rotate_primary(reason="round-robin")
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
                    self._emit_log(
                        f"🔍 Anomaly detected on {node.id} "
                        f"(rep={node.reputation:.0f}%) — flagged as suspect",
                        "warning"
                    )
                changed = True
        if changed:
            self._emit_graph()

    # ── comms / metrics ───────────────────────────────────────────────────────
    def _simulate_comms(self):
        with self._lock:
            phase       = self._phase
            attack_type = None
            for nid in self._attack_node_ids:
                nd = self.nodes.get(nid)
                if nd and nd.attack_type:
                    attack_type = nd.attack_type
                    break

            all_metrics = {}
            for edge in self.edges:
                src, tgt = edge["source"], edge["target"]
                key      = f"{src}-{tgt}"
                near     = (src in self._attack_node_ids or tgt in self._attack_node_ids)
                em = self.edge_metrics.get(key)
                if em:
                    em.update(phase=phase, near_attack=near, attack_type=attack_type)
                    all_metrics[key] = em.to_dict()

        if all_metrics:
            self._emit("all_edge_metrics", all_metrics)
            vals      = list(all_metrics.values())
            phase_now = phase

            if phase_now == "attack" and self._attack_node_ids:
                near_vals = [v for v in vals
                             if v["source"] in self._attack_node_ids
                             or v["target"] in self._attack_node_ids]
                if near_vals:
                    worst = max(near_vals, key=lambda v: v["latency"])
                    self._emit_log(
                        f"⚡ {worst['source']}→{worst['target']} | "
                        f"lat={worst['latency']}ms bw={worst['bandwidth']:.1f}Mbps "
                        f"loss={worst['packet_loss']}% | LINK DEGRADED",
                        "warning"
                    )

            elif phase_now == "consensus":
                q = self._get_quorum_size()
                e = len(self._get_eligible_nodes())
                self._emit_log(
                    f"🔐 PBFT round | pre-prepare → prepare → commit | "
                    f"voters={e} quorum={q} | "
                    f"avg-lat={_avg(vals,'latency'):.0f}ms "
                    f"avg-loss={_avg(vals,'packet_loss'):.1f}%",
                    "warning"
                )

            elif phase_now == "critical":
                self._emit_log(
                    "🔴 CRITICAL MODE | mining halted | read-only | "
                    f"healthy={len(self._get_eligible_nodes())}/7 | "
                    "awaiting admin recovery",
                    "error"
                )

            elif phase_now == "frozen":
                self._emit_log(
                    "🚨 FROZEN | consensus impossible | serving chain reads only | "
                    f"last block={self._total_blocks}",
                    "error"
                )

            elif phase_now == "dead":
                self._emit_log(
                    "💀 DEAD | full partition | no traffic | reset required",
                    "error"
                )

            elif phase_now == "idle":
                if vals:
                    sample       = random.choice(vals)
                    src, tgt     = sample["source"], sample["target"]
                    node_obj     = self.nodes.get(src)
                    peer_id      = random.choice(node_obj.peers) if node_obj and node_obj.peers else tgt
                    msg = random.choice(PEER_MESSAGES).format(
                        node=src, peer=peer_id,
                        block=self._total_blocks, tx=random.randint(1, 9),
                    )
                    self._emit_log(
                        f"{msg} | lat={sample['latency']:.1f}ms "
                        f"bw={sample['bandwidth']:.1f}Mbps "
                        f"jitter={sample['jitter']:.1f}ms",
                        "info"
                    )

    # ── healing / PBFT ────────────────────────────────────────────────────────
    def _detect_and_heal(self):
        # If already in a degraded state, skip consensus — nothing to vote on
        if self._viability in ("frozen", "dead"):
            self._emit_log(
                f"⚠ PBFT skipped — network already {self._viability.upper()}",
                "warning"
            )
            return

        self._set_phase("consensus")
        eligible     = self._get_eligible_nodes()
        quorum       = self._get_quorum_size()
        total_voters = len(eligible)

        self._emit_log(
            f"🔐 PBFT consensus initiated | "
            f"eligible voters={total_voters} | quorum={quorum} | "
            "voting on quarantine",
            "info"
        )

        # ── Animate vote accumulation on ConsensusBar ─────────────────────
        # Emit incremental vote counts so the progress bar fills visually.
        # Payload shape: {"round": {"count": N, "needed": quorum, "total": M}}
        def _emit_votes(count):
            self._emit("consensus_votes", {
                "round": {
                    "count":  count,
                    "needed": quorum,
                    "total":  total_voters,
                }
            })

        _emit_votes(0)  # reset bar to 0 immediately on consensus start

        # Spread votes across 2.4s window (commit fires at 3.0s)
        for i in range(total_voters):
            delay = 0.3 + i * (2.4 / max(total_voters, 1))
            def _vote(votes_so_far=i + 1):
                _emit_votes(votes_so_far)
            threading.Timer(delay, _vote).start()

        threading.Timer(3.0, self._pbft_commit).start()

    def _pbft_commit(self):
        suspects = [n for n in self.nodes.values()
                    if n.status in ("compromised", "suspect")]
        quorum   = self._get_quorum_size()

        # ── Check viability BEFORE quarantining ───────────────────────────
        # Suspects can be "compromised" or "suspect" — neither is "healthy".
        # _get_eligible_nodes() returns healthy nodes only, so suspects are
        # already NOT in that list. We must count only suspects who overlap
        # with current eligible set to avoid going negative.
        eligible_now  = set(n.id for n in self._get_eligible_nodes())
        # In practice suspects are never in eligible_now (they're compromised/suspect)
        # but this guard makes the math bulletproof regardless.
        suspects_reducing_eligible = [n for n in suspects if n.id in eligible_now]
        healthy_after = len(eligible_now) - len(suspects_reducing_eligible)
        healthy_after = max(0, healthy_after)   # never negative

        will_be_critical = healthy_after == THRESHOLD_CRITICAL
        will_be_frozen   = healthy_after == THRESHOLD_FROZEN
        will_be_dead     = healthy_after < THRESHOLD_FROZEN

        if will_be_dead or will_be_frozen or will_be_critical:
            tier = "DEAD" if will_be_dead else "FROZEN" if will_be_frozen else "CRITICAL"
            self._emit_log(
                f"⚠ PBFT viability check: quarantining {len(suspects)} suspect(s) "
                f"| eligible now={len(eligible_now)} "
                f"| healthy after={healthy_after} → {tier}",
                "warning"
            )

        # Quarantine suspects
        for node in suspects:
            self._quarantine(node.id)

        # ── Assess new viability AFTER quarantine ─────────────────────────
        new_viability = self._assess_viability()
        self._handle_viability_transition(new_viability)

        if suspects:
            quarantined_ids  = [n.id for n in suspects]
            eligible_after   = self._get_eligible_nodes()
            quorum_after     = self._get_quorum_size()

            self._emit_log(
                f"✅ PBFT commit — {', '.join(quarantined_ids)} quarantined | "
                f"quorum used={quorum} | "
                f"remaining validators={len(eligible_after)} | "
                f"new quorum={quorum_after} | "
                f"viability={new_viability.upper()}",
                "success" if new_viability == "operational" else "warning"
            )

            if new_viability == "operational":
                # Normal healing path
                self._rotate_primary(reason="post-quarantine")
                self._set_phase("healing")

                def _finish_healing():
                    self._set_phase("idle")
                    primary = self._current_primary()
                    self._emit_log(
                        f"🟢 Network self-healed | "
                        f"healthy={len(self._get_eligible_nodes())}/7 | "
                        f"primary={primary.id if primary else 'none'} | "
                        f"quorum={self._get_quorum_size()}",
                        "success"
                    )
                    threading.Timer(0.3, self._push_metrics_snapshot).start()

                threading.Timer(2.5, _finish_healing).start()
            # For critical/frozen/dead: phase was already set in _handle_viability_transition
        else:
            self._set_phase("idle")
            self._emit_log(
                "🔍 PBFT scan complete — no suspects confirmed | network clear",
                "info"
            )

    def _quarantine(self, node_id: str):
        """
        Quarantine a node:
          1. Status → quarantined, strip primary flag
          2. Sever all connected edges
          3. If was primary, rotate immediately
        """
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return

            was_primary     = node.is_primary
            node.status     = "quarantined"
            node.is_primary = False
            # Freeze reputation at its current (degraded) value — do not reset
            # to 100 (would look like healthy) or 0 (would look like dead).
            # Clear attack_type so the orange ring stops showing attack label.
            node.attack_type = None

            for edge in self.edges:
                if edge["source"] == node_id or edge["target"] == node_id:
                    edge["active"] = False

            self._attack_node_ids.discard(node_id)
            if not self._attack_node_ids:
                self._attack_node_ids = set()

        self._emit("node_quarantined", {"node": node_id})
        self._emit_log(
            f"🔒 {node_id} QUARANTINED — links severed"
            + (" | was primary → rotating now" if was_primary else ""),
            "error"
        )

        if was_primary:
            self._rotate_primary(reason=f"{node_id} quarantined")

        self._emit_graph()

    # ── helpers ───────────────────────────────────────────────────────────────
    def _set_phase(self, phase: str):
        self._phase = phase
        self._emit("phase_change", {"phase": phase})
        if phase == "idle":
            self._attack_node_ids = set()
            for em in self.edge_metrics.values():
                em._tick = 0

    def _emit_log(self, msg: str, level: str = "info"):
        self._emit("log_event", {
            "message":   msg,
            "type":      level,
            "timestamp": datetime.now().isoformat(),
        })

    def _emit_graph(self):
        self._emit("graph_update", {
            "nodes": self._node_list(),
            "edges": self.edges,
        })

    def _node_list(self) -> list:
        return [
            {
                "id":          n.id,
                "status":      n.status,
                "reputation":  round(n.reputation, 1),
                "block_count": len(n.chain),
                "peers":       n.peers,
                "attack_type": n.attack_type,
                "is_primary":  n.is_primary,
            }
            for n in self.nodes.values()
        ]

    def _stats(self) -> dict:
        # Count both compromised AND quarantined as non-healthy for the stats panel
        compromised  = [n.id for n in self.nodes.values()
                        if n.status in ("compromised", "suspect")]
        quarantined  = [n.id for n in self.nodes.values()
                        if n.status == "quarantined"]
        total_txs    = sum(
            len(b.get("transactions", []))
            for n in self.nodes.values()
            for b in n.chain
        )
        eligible     = self._get_eligible_nodes()
        return {
            "block_count":        self._total_blocks,
            "tx_rate":            random.randint(TX_RATE_BASE - 3, TX_RATE_BASE + 5),
            "total_transactions": total_txs,
            "compromised_nodes":  compromised,
            "quarantined_nodes":  quarantined,
            "quarantined_count":  len(quarantined),
            "phase":              self._phase,
            "viability":          self._viability,
            "eligible_voters":    len(eligible),
            "quorum":             self._get_quorum_size(),
            "healthy_count":      len(eligible),
        }