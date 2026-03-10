"""
node.py — Represents a single participant in the P2P blockchain network.
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from network import NetworkManager

logger = logging.getLogger(__name__)


class Node:
    """
    A Node is one participant in the distributed blockchain network.
    It maintains its own copy of the blockchain and communicates with peers.
    """

    STATUS_ACTIVE      = "active"
    STATUS_SUSPECT     = "suspect"
    STATUS_QUARANTINED = "quarantined"

    def __init__(self, node_id: str, blockchain=None, network_manager: "NetworkManager | None" = None):
        """
        Parameters
        ----------
        node_id          : unique identifier, e.g. "N1"
        blockchain       : a Blockchain instance (or None — assigned later)
        network_manager  : back-reference to the NetworkManager for broadcasts
        """
        self.node_id: str          = node_id
        self.chain                 = blockchain          # Blockchain instance
        self.peers: list[str]      = []                 # list of connected node_ids
        self.status: str           = self.STATUS_ACTIVE
        self.reputation_score: int = 100                # starts at full reputation
        self.is_leader: bool       = False
        self._network: "NetworkManager | None" = network_manager

    # ------------------------------------------------------------------
    # Broadcast / Receive
    # ------------------------------------------------------------------

    def broadcast_block(self, block) -> None:
        """
        Send a newly mined block to every connected peer via the NetworkManager.
        Does nothing if the node is quarantined or has no network reference.
        """
        if self.status == self.STATUS_QUARANTINED:
            logger.warning("[%s] Quarantined — broadcast suppressed.", self.node_id)
            return

        if self._network is None:
            logger.error("[%s] No NetworkManager attached — cannot broadcast.", self.node_id)
            return

        logger.info("[%s] Broadcasting block #%s to peers %s",
                    self.node_id, block.index, self.peers)

        self._network.broadcast(
            sender_id    = self.node_id,
            message_type = "NEW_BLOCK",
            payload      = block.to_dict() if hasattr(block, "to_dict") else block,
        )

    def receive_block(self, block_data: dict) -> bool:
        """
        Validate and append an incoming block to the local chain.

        Returns True if the block was accepted, False otherwise.
        """
        if self.status == self.STATUS_QUARANTINED:
            logger.warning("[%s] Quarantined — block reception rejected.", self.node_id)
            return False

        if self.chain is None:
            logger.error("[%s] No blockchain attached.", self.node_id)
            return False

        # Reconstruct a Block object if necessary
        try:
            from blockchain import Block  # local import to avoid circular deps
            if isinstance(block_data, dict):
                block = Block(
                    index        = block_data["index"],
                    transactions = block_data.get("transactions", []),
                    previous_hash= block_data.get("previous_hash", "0"),
                    timestamp    = block_data.get("timestamp"),
                    nonce        = block_data.get("nonce", 0),
                )
                block.hash = block_data.get("hash", block.compute_hash())
            else:
                block = block_data  # already a Block instance
        except Exception as exc:
            logger.error("[%s] Failed to deserialise block: %s", self.node_id, exc)
            return False

        # Delegate validation + append to the Blockchain
        if self.chain.is_valid_block(block):
            self.chain.add_block_direct(block)
            self.update_reputation(+1)          # reward for valid receipt
            logger.info("[%s] Accepted block #%s.", self.node_id, block.index)
            return True
        else:
            self.update_reputation(-5)          # penalise for invalid block
            logger.warning("[%s] Rejected invalid block #%s.", self.node_id, block.index)
            return False

    # ------------------------------------------------------------------
    # Reputation
    # ------------------------------------------------------------------

    def update_reputation(self, delta: int) -> None:
        """
        Modify reputation_score by delta, clamped to [0, 100].

        Positive delta  → reward (e.g. valid block relayed)
        Negative delta  → penalty (e.g. invalid block, timeout)
        """
        self.reputation_score = max(0, min(100, self.reputation_score + delta))
        logger.debug("[%s] Reputation updated by %+d → %d",
                     self.node_id, delta, self.reputation_score)

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def flag_suspect(self) -> None:
        """
        Mark this node as suspect (possible misbehaviour detected).
        Does not yet disconnect the node from its peers.
        """
        if self.status != self.STATUS_QUARANTINED:
            self.status = self.STATUS_SUSPECT
            self.update_reputation(-10)
            logger.warning("[%s] Flagged as SUSPECT.", self.node_id)

    def quarantine(self) -> None:
        """
        Quarantine this node: change status and disconnect from all peers.
        The NetworkManager's peer lists are updated via quarantine_node(); this
        method only handles the node's own internal state.
        """
        self.status = self.STATUS_QUARANTINED
        self.is_leader = False
        self.peers.clear()
        self.update_reputation(-20)
        logger.warning("[%s] QUARANTINED — disconnected from all peers.", self.node_id)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-serialisable snapshot of this node's state for the GUI."""
        return {
            "node_id"         : self.node_id,
            "status"          : self.status,
            "reputation_score": self.reputation_score,
            "is_leader"       : self.is_leader,
            "peers"           : list(self.peers),
            "chain_length"    : len(self.chain.chain) if self.chain else 0,
        }

    def __repr__(self) -> str:
        return (f"Node({self.node_id}, status={self.status}, "
                f"rep={self.reputation_score}, leader={self.is_leader})")