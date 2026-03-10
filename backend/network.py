"""
network.py — Creates and manages all 7 nodes and their P2P topology.

Topology (matching the GUI diagram):
    N1 ↔ N2, N1 ↔ N3          (leader → top validators)
    N2 ↔ N3, N2 ↔ N4          (left branch)
    N3 ↔ N5, N4 ↔ N5          (right branch)
    N4 ↔ N6, N5 ↔ N7          (bottom layer)
    N6 ↔ N7                    (bottom ring closure)
    N1 ↔ N6, N1 ↔ N7          (leader redundant links)
"""

from __future__ import annotations
import logging
import threading
from typing import Any

from node import Node

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical edge list — single source of truth for the topology
# ---------------------------------------------------------------------------
TOPOLOGY_EDGES: list[tuple[str, str]] = [
    ("N1", "N2"),
    ("N1", "N3"),
    ("N2", "N3"),
    ("N2", "N4"),
    ("N3", "N5"),
    ("N4", "N5"),
    ("N4", "N6"),
    ("N5", "N7"),
    ("N6", "N7"),
    ("N1", "N6"),
    ("N1", "N7"),
]


class NetworkManager:
    """
    Manages the full P2P network: node creation, topology wiring,
    message routing, and state serialisation for the Flask frontend.
    """

    def __init__(self, num_nodes: int = 7, blockchain_factory=None):
        """
        Parameters
        ----------
        num_nodes           : number of nodes to create (default 7)
        blockchain_factory  : callable() → Blockchain instance.
                              If None, nodes are created without a chain
                              (useful for testing; attach chains later).
        """
        self._lock = threading.Lock()
        self.num_nodes = num_nodes

        # Build node objects ------------------------------------------------
        self.nodes: dict[str, Node] = {}
        for i in range(1, num_nodes + 1):
            node_id = f"N{i}"
            chain   = blockchain_factory() if blockchain_factory else None
            node    = Node(node_id=node_id, blockchain=chain, network_manager=self)
            self.nodes[node_id] = node

        # Node 0 index → "N1" is the initial leader
        self.nodes["N1"].is_leader = True

        # Wire up the peer topology
        self.connect_nodes()

        logger.info("NetworkManager initialised with %d nodes.", num_nodes)

    # ------------------------------------------------------------------
    # Topology
    # ------------------------------------------------------------------

    def connect_nodes(self) -> None:
        """
        Build the peer graph from TOPOLOGY_EDGES (bidirectional).
        Existing peer lists are cleared first so this is idempotent.
        """
        # Reset all peer lists
        for node in self.nodes.values():
            node.peers.clear()

        for a, b in TOPOLOGY_EDGES:
            if a in self.nodes and b in self.nodes:
                if b not in self.nodes[a].peers:
                    self.nodes[a].peers.append(b)
                if a not in self.nodes[b].peers:
                    self.nodes[b].peers.append(a)

        logger.debug("Topology wired: %s", TOPOLOGY_EDGES)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def broadcast(self, sender_id: str, message_type: str, payload: Any) -> None:
        """
        Route a message from sender_id to every one of its connected peers.

        Parameters
        ----------
        sender_id    : originating node
        message_type : e.g. "NEW_BLOCK", "LEADER_CHANGE", "QUARANTINE"
        payload      : arbitrary serialisable data (dict / block dict / etc.)
        """
        sender = self.nodes.get(sender_id)
        if sender is None:
            logger.error("broadcast: unknown sender '%s'", sender_id)
            return

        for peer_id in list(sender.peers):          # copy — peers may change mid-loop
            peer = self.nodes.get(peer_id)
            if peer is None or peer.status == Node.STATUS_QUARANTINED:
                continue

            logger.debug("[%s] → [%s] type=%s", sender_id, peer_id, message_type)

            try:
                if message_type == "NEW_BLOCK":
                    peer.receive_block(payload)
                # Extend here for additional message types:
                # elif message_type == "TRANSACTION": peer.receive_transaction(payload)
                else:
                    logger.warning("broadcast: unhandled message_type '%s'", message_type)
            except Exception as exc:
                logger.error("broadcast error [%s → %s]: %s", sender_id, peer_id, exc)

    # ------------------------------------------------------------------
    # Network state (for Flask / GUI)
    # ------------------------------------------------------------------

    def get_network_state(self) -> dict:
        """
        Return a full JSON snapshot of the network — nodes + edges.

        Shape
        -----
        {
            "nodes": [ { node_id, status, reputation_score, is_leader,
                         peers, chain_length }, … ],
            "edges": [ { "source": "N1", "target": "N2" }, … ]
        }
        """
        with self._lock:
            nodes_data = [node.to_dict() for node in self.nodes.values()]

            # Build de-duplicated edge list from canonical topology,
            # excluding edges where either endpoint is quarantined.
            active_edges = []
            seen: set[frozenset] = set()
            for a, b in TOPOLOGY_EDGES:
                key = frozenset([a, b])
                if key in seen:
                    continue
                node_a = self.nodes.get(a)
                node_b = self.nodes.get(b)
                if (node_a and node_b
                        and node_a.status != Node.STATUS_QUARANTINED
                        and node_b.status != Node.STATUS_QUARANTINED):
                    active_edges.append({"source": a, "target": b})
                    seen.add(key)

            return {"nodes": nodes_data, "edges": active_edges}

    # ------------------------------------------------------------------
    # Quarantine
    # ------------------------------------------------------------------

    def quarantine_node(self, node_id: str) -> bool:
        """
        Quarantine a node:
          1. Call node.quarantine() to update its own internal state.
          2. Remove it from every other node's peer list.
          3. If it was the leader, elect a new one.

        Returns True on success, False if node_id unknown.
        """
        with self._lock:
            target = self.nodes.get(node_id)
            if target is None:
                logger.error("quarantine_node: unknown node '%s'", node_id)
                return False

            was_leader = target.is_leader
            target.quarantine()                         # node clears its own peers

            # Remove target from every other node's peer list
            for node in self.nodes.values():
                if node.node_id != node_id and node_id in node.peers:
                    node.peers.remove(node_id)

            logger.warning("[%s] has been quarantined by NetworkManager.", node_id)

        if was_leader:
            self.elect_new_leader()

        return True

    # ------------------------------------------------------------------
    # Leader election
    # ------------------------------------------------------------------

    def elect_new_leader(self) -> str | None:
        """
        Find the non-quarantined node with the highest reputation score
        and designate it as the new leader.

        Returns the node_id of the new leader, or None if no eligible node exists.
        """
        with self._lock:
            # Demote current leader(s) first
            for node in self.nodes.values():
                node.is_leader = False

            candidates = [
                node for node in self.nodes.values()
                if node.status != Node.STATUS_QUARANTINED
            ]

            if not candidates:
                logger.error("elect_new_leader: no eligible candidates!")
                return None

            new_leader = max(candidates, key=lambda n: n.reputation_score)
            new_leader.is_leader = True
            logger.info("New leader elected: %s (reputation=%d)",
                        new_leader.node_id, new_leader.reputation_score)
            return new_leader.node_id

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> Node | None:
        """Return the Node object for node_id, or None."""
        return self.nodes.get(node_id)

    def get_leader(self) -> Node | None:
        """Return the current leader node, or None."""
        for node in self.nodes.values():
            if node.is_leader:
                return node
        return None

    def __repr__(self) -> str:
        leader = self.get_leader()
        return (f"NetworkManager(nodes={list(self.nodes.keys())}, "
                f"leader={leader.node_id if leader else 'None'})")