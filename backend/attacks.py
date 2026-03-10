"""
attacks.py — Phase 6: Attack Injection Scripts
================================================
Simulates five network-level attacks against consensus nodes:
  1. Sybil Attack
  2. Byzantine Fault
  3. DDoS Flood
  4. Eclipse Attack
  5. Man-in-the-Middle (MitM)

Each attack:
  - Returns immediately with attack_id + target_node_id
  - Runs logic in a background thread
  - Emits socket events at each stage for real-time GUI updates
  - Does NOT call PBFT directly — reputation decay triggers consensus
"""

import threading
import time
import uuid
import hashlib
import copy
import random
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Reputation thresholds (must match consensus.py)
# ─────────────────────────────────────────────
REPUTATION_SYBIL_PENALTY      = 40
REPUTATION_BYZANTINE_PENALTY  = 20   # per hash mismatch
REPUTATION_DDOS_PENALTY       = 30
REPUTATION_ECLIPSE_PENALTY    = 25
REPUTATION_MITM_PENALTY       = 15   # per intercepted message

SUSPECT_THRESHOLD             = 60   # below this → SUSPECT flag
PBFT_THRESHOLD                = 40   # below this → PBFT triggered by network_manager

# ─────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────

def _emit(socketio, event: str, data: dict):
    """Thread-safe socket emit wrapper."""
    try:
        socketio.emit(event, data)
    except Exception as exc:
        logger.warning("Socket emit failed [%s]: %s", event, exc)


def _new_attack_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _get_node(network_manager, node_id: str):
    """Return node object or None."""
    return network_manager.nodes.get(node_id)


def _apply_reputation_penalty(network_manager, socketio, node_id: str, penalty: int, reason: str):
    """
    Subtract penalty from node reputation and emit a reputation_update event.
    Flags node as SUSPECT when reputation falls below SUSPECT_THRESHOLD.
    PBFT is triggered automatically by network_manager's reputation watcher.
    """
    node = _get_node(network_manager, node_id)
    if node is None:
        return

    old_rep = node.reputation
    node.reputation = max(0, node.reputation - penalty)

    if node.reputation < SUSPECT_THRESHOLD and node.status not in ("compromised", "byzantine"):
        node.status = "suspect"

    _emit(socketio, "reputation_update", {
        "node_id":    node_id,
        "old":        old_rep,
        "new":        node.reputation,
        "penalty":    penalty,
        "reason":     reason,
        "status":     node.status,
    })
    logger.info("[REPUTATION] %s: %d → %d (%s)", node_id, old_rep, node.reputation, reason)


# ═══════════════════════════════════════════════════════════════
# ATTACK 1 — Sybil Attack
# ═══════════════════════════════════════════════════════════════

def sybil_attack(network_manager, socketio, target_id: str = "N4") -> dict:
    """
    Compromise a node and flood the network with 3 spoofed identity broadcasts.

    Steps (background thread):
      1. Mark target node as 'compromised'
      2. Broadcast 3 fake identity messages with spoofed sender IDs
      3. Apply -40 reputation penalty to target
      4. Emit attack_stage events at each step
    """
    attack_id = _new_attack_id("SYBIL")

    def _run():
        node = _get_node(network_manager, target_id)
        if node is None:
            _emit(socketio, "attack_error", {
                "attack_id": attack_id,
                "message": f"Target node {target_id} not found",
            })
            return

        # ── Stage 1: Mark node compromised ────────────────────────
        _emit(socketio, "attack_stage", {
            "attack_id":   attack_id,
            "attack_type": "sybil",
            "stage":       1,
            "message":     f"[SYBIL] Compromising node {target_id}...",
            "target":      target_id,
        })
        node.status = "compromised"
        time.sleep(0.4)

        # ── Stage 2: Broadcast 3 fake identities ──────────────────
        fake_ids = [f"GHOST-{uuid.uuid4().hex[:4].upper()}" for _ in range(3)]

        for i, fake_id in enumerate(fake_ids, start=1):
            _emit(socketio, "attack_stage", {
                "attack_id":   attack_id,
                "attack_type": "sybil",
                "stage":       2,
                "message":     f"[SYBIL] Broadcasting fake identity #{i}: {fake_id} (spoofed from {target_id})",
                "target":      target_id,
                "fake_id":     fake_id,
            })

            # Use node's broadcast if available, otherwise emit directly
            spoofed_msg = {
                "type":      "IDENTITY_ANNOUNCE",
                "sender":    fake_id,           # spoofed sender
                "origin":    target_id,         # actual originating node
                "timestamp": time.time(),
                "payload":   {
                    "node_id":   fake_id,
                    "public_key": hashlib.sha256(fake_id.encode()).hexdigest(),
                    "claim":     "validator",
                },
            }

            if hasattr(node, "broadcast"):
                try:
                    node.broadcast(spoofed_msg)
                except Exception:
                    pass  # network_manager may handle broadcast differently

            _emit(socketio, "message_broadcast", {
                "attack_id":   attack_id,
                "attack_type": "sybil",
                "sender":      fake_id,
                "origin":      target_id,
                "msg_type":    "IDENTITY_ANNOUNCE",
            })
            time.sleep(0.6)

        # ── Stage 3: Apply reputation penalty ─────────────────────
        _emit(socketio, "attack_stage", {
            "attack_id":   attack_id,
            "attack_type": "sybil",
            "stage":       3,
            "message":     f"[SYBIL] Applying reputation penalty -{REPUTATION_SYBIL_PENALTY} to {target_id}",
            "target":      target_id,
        })
        _apply_reputation_penalty(
            network_manager, socketio, target_id,
            REPUTATION_SYBIL_PENALTY, "sybil_identity_spoofing"
        )

        # ── Stage 4: Complete ──────────────────────────────────────
        _emit(socketio, "attack_complete", {
            "attack_id":   attack_id,
            "attack_type": "sybil",
            "target":      target_id,
            "fake_ids":    fake_ids,
            "reputation":  _get_node(network_manager, target_id).reputation,
            "status":      _get_node(network_manager, target_id).status,
            "message":     f"[SYBIL] Attack complete. {target_id} reputation critically damaged.",
        })
        logger.info("[SYBIL] Attack %s complete on %s", attack_id, target_id)

    t = threading.Thread(target=_run, name=f"attack-sybil-{attack_id}", daemon=True)
    t.start()

    return {"attack_id": attack_id, "attack_type": "sybil", "target_node_id": target_id}


# ═══════════════════════════════════════════════════════════════
# ATTACK 2 — Byzantine Fault
# ═══════════════════════════════════════════════════════════════

def byzantine_fault(network_manager, socketio, target_id: str = None) -> dict:
    """
    Corrupt a validator node's chain so its latest block hash diverges from
    the canonical network hash.

    Steps (background thread):
      1. Identify a validator node (default: first validator found)
      2. Tamper with the node's latest block hash
      3. Simulate PREPARE message broadcast with corrupted hash
      4. Other nodes detect mismatch → consecutive_mismatch counter increments
      5. Reputation penalty applied per mismatch
    """
    attack_id = _new_attack_id("BYZ")

    # Choose target: prefer provided ID, else first validator
    if target_id is None:
        for nid, node in network_manager.nodes.items():
            if getattr(node, "role", "") == "validator":
                target_id = nid
                break
        if target_id is None:
            target_id = list(network_manager.nodes.keys())[1]  # fallback

    def _run():
        node = _get_node(network_manager, target_id)
        if node is None:
            _emit(socketio, "attack_error", {
                "attack_id": attack_id,
                "message": f"Target node {target_id} not found",
            })
            return

        # ── Stage 1: Inspect current chain ────────────────────────
        _emit(socketio, "attack_stage", {
            "attack_id":   attack_id,
            "attack_type": "byzantine",
            "stage":       1,
            "message":     f"[BYZANTINE] Inspecting chain of validator {target_id}...",
            "target":      target_id,
        })
        time.sleep(0.5)

        # Get canonical hash from network_manager if available
        canonical_hash = getattr(network_manager, "canonical_hash", None)
        if canonical_hash is None and hasattr(network_manager, "get_canonical_hash"):
            canonical_hash = network_manager.get_canonical_hash()

        # Get or create node chain reference
        chain = getattr(node, "chain", None)
        if chain is None or len(chain) == 0:
            # Simulate a minimal chain structure
            node.chain = [
                {"index": 0, "hash": "GENESIS-0000", "prev_hash": "0" * 64, "data": "genesis"},
                {"index": 1, "hash": hashlib.sha256(b"block1").hexdigest(), "prev_hash": "GENESIS-0000", "data": "tx-block-1"},
            ]
            chain = node.chain

        original_hash = chain[-1].get("hash", "unknown")

        # ── Stage 2: Tamper with latest block hash ─────────────────
        _emit(socketio, "attack_stage", {
            "attack_id":    attack_id,
            "attack_type":  "byzantine",
            "stage":        2,
            "message":      f"[BYZANTINE] Tampering block hash on {target_id}: {original_hash[:16]}... → CORRUPT",
            "target":       target_id,
            "original_hash": original_hash,
        })

        corrupted_hash = "CORRUPT-" + hashlib.sha256(
            (original_hash + str(time.time())).encode()
        ).hexdigest()[:48]

        # Deep-copy last block and corrupt it
        node.chain[-1] = copy.deepcopy(chain[-1])
        node.chain[-1]["hash"] = corrupted_hash
        node.status = "byzantine"

        _emit(socketio, "chain_tampered", {
            "attack_id":      attack_id,
            "node_id":        target_id,
            "original_hash":  original_hash,
            "corrupted_hash": corrupted_hash,
        })
        time.sleep(0.5)

        # ── Stage 3: Simulate PREPARE broadcast with bad hash ──────
        mismatch_count = 0
        for round_num in range(1, 4):
            _emit(socketio, "attack_stage", {
                "attack_id":   attack_id,
                "attack_type": "byzantine",
                "stage":       3,
                "message":     f"[BYZANTINE] Round {round_num}: Broadcasting PREPARE with corrupted hash from {target_id}",
                "target":      target_id,
                "round":       round_num,
            })

            prepare_msg = {
                "type":        "PREPARE",
                "sender":      target_id,
                "block_hash":  corrupted_hash,
                "block_index": len(node.chain) - 1,
                "timestamp":   time.time(),
            }

            if hasattr(node, "broadcast"):
                try:
                    node.broadcast(prepare_msg)
                except Exception:
                    pass

            # Simulate peer nodes detecting mismatch
            for peer_id, peer_node in network_manager.nodes.items():
                if peer_id == target_id:
                    continue
                peer_hash = None
                if hasattr(peer_node, "chain") and peer_node.chain:
                    peer_hash = peer_node.chain[-1].get("hash")

                if peer_hash and peer_hash != corrupted_hash:
                    mismatch_count += 1
                    _emit(socketio, "hash_mismatch_detected", {
                        "attack_id":      attack_id,
                        "detector":       peer_id,
                        "sender":         target_id,
                        "expected_hash":  peer_hash[:16] + "...",
                        "received_hash":  corrupted_hash[:16] + "...",
                    })

            # Increment consecutive mismatch counter on target node
            node.consecutive_mismatches = getattr(node, "consecutive_mismatches", 0) + 1

            _apply_reputation_penalty(
                network_manager, socketio, target_id,
                REPUTATION_BYZANTINE_PENALTY,
                f"byzantine_hash_mismatch_round_{round_num}"
            )
            time.sleep(0.7)

        # ── Stage 4: Complete ──────────────────────────────────────
        _emit(socketio, "attack_complete", {
            "attack_id":       attack_id,
            "attack_type":     "byzantine",
            "target":          target_id,
            "mismatches":      mismatch_count,
            "reputation":      _get_node(network_manager, target_id).reputation,
            "status":          _get_node(network_manager, target_id).status,
            "corrupted_hash":  corrupted_hash,
            "message":         f"[BYZANTINE] Attack complete. {mismatch_count} mismatches detected.",
        })
        logger.info("[BYZANTINE] Attack %s complete on %s (%d mismatches)", attack_id, target_id, mismatch_count)

    t = threading.Thread(target=_run, name=f"attack-byzantine-{attack_id}", daemon=True)
    t.start()

    return {"attack_id": attack_id, "attack_type": "byzantine", "target_node_id": target_id}


# ═══════════════════════════════════════════════════════════════
# ATTACK 3 — DDoS Flood
# ═══════════════════════════════════════════════════════════════

def ddos_flood(network_manager, socketio, target_id: str = "N3", flood_count: int = 500) -> dict:
    """
    Flood the network with junk transactions originating from the target node.

    Steps (background thread):
      1. Emit flood start event
      2. Broadcast `flood_count` junk transactions in rapid succession
      3. Track message_frequency_counter on target node
      4. Apply reputation penalty when threshold is exceeded
      5. Flag node as SUSPECT
    """
    attack_id = _new_attack_id("DDOS")

    def _run():
        node = _get_node(network_manager, target_id)
        if node is None:
            _emit(socketio, "attack_error", {
                "attack_id": attack_id,
                "message": f"Target node {target_id} not found",
            })
            return

        # ── Stage 1: Begin flood ───────────────────────────────────
        _emit(socketio, "attack_stage", {
            "attack_id":   attack_id,
            "attack_type": "ddos",
            "stage":       1,
            "message":     f"[DDoS] Starting flood from {target_id} — {flood_count} junk transactions",
            "target":      target_id,
            "flood_count": flood_count,
        })

        node.message_frequency = getattr(node, "message_frequency", 0)
        batch_size = 50
        batches = flood_count // batch_size

        for batch_num in range(batches):
            junk_txs = []
            for _ in range(batch_size):
                tx = {
                    "type":      "TRANSACTION",
                    "sender":    target_id,
                    "tx_id":     uuid.uuid4().hex,
                    "data":      "JUNK-" + uuid.uuid4().hex,
                    "timestamp": time.time(),
                }
                junk_txs.append(tx)

                # Increment node message frequency counter
                node.message_frequency += 1

                if hasattr(node, "broadcast"):
                    try:
                        node.broadcast(tx)
                    except Exception:
                        pass

            sent_total = (batch_num + 1) * batch_size

            _emit(socketio, "ddos_batch_sent", {
                "attack_id":   attack_id,
                "attack_type": "ddos",
                "target":      target_id,
                "batch":       batch_num + 1,
                "sent":        sent_total,
                "total":       flood_count,
                "frequency":   node.message_frequency,
            })
            time.sleep(0.15)  # slight delay per batch for GUI visibility

        # ── Stage 2: Threshold exceeded — apply penalty ───────────
        _emit(socketio, "attack_stage", {
            "attack_id":   attack_id,
            "attack_type": "ddos",
            "stage":       2,
            "message":     f"[DDoS] Message frequency threshold exceeded on {target_id}: {node.message_frequency} msgs",
            "target":      target_id,
            "frequency":   node.message_frequency,
        })
        time.sleep(0.3)

        _apply_reputation_penalty(
            network_manager, socketio, target_id,
            REPUTATION_DDOS_PENALTY, "ddos_message_flood"
        )

        # ── Stage 3: Flag as SUSPECT ───────────────────────────────
        if node.status not in ("compromised", "byzantine"):
            node.status = "suspect"

        _emit(socketio, "node_flagged", {
            "attack_id":   attack_id,
            "attack_type": "ddos",
            "node_id":     target_id,
            "flag":        "SUSPECT",
            "reason":      "ddos_message_flood",
            "frequency":   node.message_frequency,
        })

        # ── Stage 4: Complete ──────────────────────────────────────
        _emit(socketio, "attack_complete", {
            "attack_id":        attack_id,
            "attack_type":      "ddos",
            "target":           target_id,
            "messages_sent":    flood_count,
            "final_frequency":  node.message_frequency,
            "reputation":       _get_node(network_manager, target_id).reputation,
            "status":           _get_node(network_manager, target_id).status,
            "message":          f"[DDoS] Flood complete. {flood_count} junk transactions sent. Node flagged as SUSPECT.",
        })
        logger.info("[DDoS] Attack %s complete on %s (%d msgs)", attack_id, target_id, flood_count)

    t = threading.Thread(target=_run, name=f"attack-ddos-{attack_id}", daemon=True)
    t.start()

    return {"attack_id": attack_id, "attack_type": "ddos", "target_node_id": target_id}


# ═══════════════════════════════════════════════════════════════
# ATTACK 4 — Eclipse Attack
# ═══════════════════════════════════════════════════════════════

def eclipse_attack(network_manager, socketio, target_id: str = "N6") -> dict:
    """
    Isolate a leaf node from all real peers and inject a forked shadow chain.

    Steps (background thread):
      1. Disconnect target from all real peers
      2. Inject a shadow_chain forked at block 5 (diverging from canonical)
      3. Block height divergence is detected by network_manager watcher
      4. Apply reputation penalty for chain divergence
    """
    attack_id = _new_attack_id("ECLIPSE")

    # Prefer N6 or N7 as leaf nodes
    if target_id not in network_manager.nodes:
        for candidate in ["N6", "N7"]:
            if candidate in network_manager.nodes:
                target_id = candidate
                break
        else:
            target_id = list(network_manager.nodes.keys())[-1]

    def _run():
        node = _get_node(network_manager, target_id)
        if node is None:
            _emit(socketio, "attack_error", {
                "attack_id": attack_id,
                "message": f"Target node {target_id} not found",
            })
            return

        # ── Stage 1: Save and sever peer connections ───────────────
        _emit(socketio, "attack_stage", {
            "attack_id":   attack_id,
            "attack_type": "eclipse",
            "stage":       1,
            "message":     f"[ECLIPSE] Severing {target_id} from all real peers...",
            "target":      target_id,
        })

        original_peers = list(getattr(node, "peers", []))
        node._eclipse_saved_peers = original_peers  # save for potential recovery

        # Disconnect from all real peers
        if hasattr(node, "peers"):
            node.peers = []
        if hasattr(network_manager, "disconnect_node"):
            network_manager.disconnect_node(target_id)

        _emit(socketio, "peers_disconnected", {
            "attack_id":       attack_id,
            "node_id":         target_id,
            "severed_peers":   original_peers,
            "peer_count":      len(original_peers),
        })
        time.sleep(0.5)

        # ── Stage 2: Build and inject shadow chain ─────────────────
        _emit(socketio, "attack_stage", {
            "attack_id":   attack_id,
            "attack_type": "eclipse",
            "stage":       2,
            "message":     f"[ECLIPSE] Injecting shadow chain (forked at block 5) into {target_id}...",
            "target":      target_id,
        })

        # Build canonical prefix (blocks 0–4) then fork
        shadow_chain = []
        prev_hash = "0" * 64
        for i in range(5):
            block_data = f"canonical-block-{i}"
            block_hash = hashlib.sha256(f"{prev_hash}{block_data}".encode()).hexdigest()
            shadow_chain.append({
                "index":     i,
                "hash":      block_hash,
                "prev_hash": prev_hash,
                "data":      block_data,
                "canonical": True,
            })
            prev_hash = block_hash

        # Fork starts at block 5
        for i in range(5, 12):
            block_data = f"shadow-fork-block-{i}-{uuid.uuid4().hex[:8]}"
            block_hash = hashlib.sha256(f"{prev_hash}{block_data}SHADOW".encode()).hexdigest()
            shadow_chain.append({
                "index":     i,
                "hash":      block_hash,
                "prev_hash": prev_hash,
                "data":      block_data,
                "canonical": False,   # diverged from canonical
                "shadow":    True,
            })
            prev_hash = block_hash

        # Inject shadow chain as node's local chain
        node.chain = shadow_chain
        node.shadow_chain = shadow_chain  # explicit reference
        node.eclipsed = True

        _emit(socketio, "shadow_chain_injected", {
            "attack_id":      attack_id,
            "node_id":        target_id,
            "fork_point":     5,
            "shadow_length":  len(shadow_chain),
            "shadow_tip":     shadow_chain[-1]["hash"][:16] + "...",
        })
        time.sleep(0.6)

        # ── Stage 3: Block height divergence detected ──────────────
        # Canonical height from network_manager
        canonical_height = getattr(network_manager, "canonical_height", 5)
        shadow_height    = len(shadow_chain) - 1  # 11

        _emit(socketio, "attack_stage", {
            "attack_id":        attack_id,
            "attack_type":      "eclipse",
            "stage":            3,
            "message":          f"[ECLIPSE] Height divergence: canonical={canonical_height}, shadow={shadow_height} — mismatch detected!",
            "target":           target_id,
            "canonical_height": canonical_height,
            "shadow_height":    shadow_height,
        })
        time.sleep(0.4)

        _apply_reputation_penalty(
            network_manager, socketio, target_id,
            REPUTATION_ECLIPSE_PENALTY, "eclipse_chain_divergence"
        )

        # ── Stage 4: Complete ──────────────────────────────────────
        _emit(socketio, "attack_complete", {
            "attack_id":        attack_id,
            "attack_type":      "eclipse",
            "target":           target_id,
            "severed_peers":    original_peers,
            "fork_point":       5,
            "shadow_height":    shadow_height,
            "canonical_height": canonical_height,
            "reputation":       _get_node(network_manager, target_id).reputation,
            "status":           _get_node(network_manager, target_id).status,
            "message":          f"[ECLIPSE] Attack complete. {target_id} isolated and fed a shadow chain.",
        })
        logger.info("[ECLIPSE] Attack %s complete on %s (fork at block 5)", attack_id, target_id)

    t = threading.Thread(target=_run, name=f"attack-eclipse-{attack_id}", daemon=True)
    t.start()

    return {"attack_id": attack_id, "attack_type": "eclipse", "target_node_id": target_id}


# ═══════════════════════════════════════════════════════════════
# ATTACK 5 — Man-in-the-Middle (MitM)
# ═══════════════════════════════════════════════════════════════

def mitm_attack(network_manager, socketio, target_id: str = None) -> dict:
    """
    Intercept outgoing messages from an edge node and tamper with block data.

    Steps (background thread):
      1. Set interception flag on target node
      2. Simulate intercepting N outgoing messages
      3. Modify the 'data' field of each intercepted block message
      4. Forward tampered message — receiving nodes fail signature verification
      5. Apply -15 reputation per failed verification
    """
    attack_id = _new_attack_id("MITM")

    # Choose an edge node if none specified
    if target_id is None:
        for candidate in ["N5", "N6", "N7", "N8"]:
            if candidate in network_manager.nodes:
                target_id = candidate
                break
        if target_id is None:
            target_id = list(network_manager.nodes.keys())[-1]

    def _run():
        node = _get_node(network_manager, target_id)
        if node is None:
            _emit(socketio, "attack_error", {
                "attack_id": attack_id,
                "message": f"Target node {target_id} not found",
            })
            return

        # ── Stage 1: Enable interception flag ─────────────────────
        _emit(socketio, "attack_stage", {
            "attack_id":   attack_id,
            "attack_type": "mitm",
            "stage":       1,
            "message":     f"[MitM] Enabling interception on {target_id}...",
            "target":      target_id,
        })
        node.mitm_intercepting = True
        node.mitm_tamper_count = 0
        time.sleep(0.4)

        # ── Stage 2–3: Intercept and tamper messages ───────────────
        intercept_rounds = 5  # intercept 5 outgoing messages
        total_penalty    = 0

        for round_num in range(1, intercept_rounds + 1):
            # Build a realistic outgoing block message
            original_data = {
                "type":       "BLOCK_PROPOSAL",
                "sender":     target_id,
                "block_index": round_num + 10,
                "data":       f"tx-legitimate-{uuid.uuid4().hex[:12]}",
                "signature":  hashlib.sha256(
                    f"{target_id}-{round_num}-secret".encode()
                ).hexdigest(),
                "timestamp":  time.time(),
            }

            # ── Intercept ─────────────────────────────────────────
            _emit(socketio, "message_intercepted", {
                "attack_id":    attack_id,
                "attack_type":  "mitm",
                "round":        round_num,
                "target":       target_id,
                "original_data": original_data["data"],
                "message":      f"[MitM] Round {round_num}: Intercepted BLOCK_PROPOSAL from {target_id}",
            })
            time.sleep(0.3)

            # ── Tamper ────────────────────────────────────────────
            tampered_msg = copy.deepcopy(original_data)
            tampered_msg["data"] = f"TAMPERED-{uuid.uuid4().hex[:16]}"
            # Note: signature is NOT updated → verification will fail

            _emit(socketio, "message_tampered", {
                "attack_id":       attack_id,
                "attack_type":     "mitm",
                "round":           round_num,
                "target":          target_id,
                "original_data":   original_data["data"],
                "tampered_data":   tampered_msg["data"],
                "original_sig":    original_data["signature"][:16] + "...",
                "message":         f"[MitM] Round {round_num}: Data field tampered. Forwarding with stale signature...",
            })
            node.mitm_tamper_count += 1
            time.sleep(0.2)

            # ── Forward to peers — simulate signature verification failure ──
            peers = getattr(node, "peers", list(network_manager.nodes.keys()))
            failed_verifications = 0

            for peer_id in peers:
                if peer_id == target_id:
                    continue
                peer_node = _get_node(network_manager, peer_id)
                if peer_node is None:
                    continue

                # Simulate signature check: recompute expected sig vs stale sig
                expected_sig = hashlib.sha256(
                    f"{target_id}-{round_num}-secret".encode()
                ).hexdigest()
                received_sig = tampered_msg["signature"]  # stale from original

                sig_valid = (
                    hashlib.sha256(
                        f"{target_id}-{round_num}-{tampered_msg['data']}".encode()
                    ).hexdigest() == received_sig
                )

                if not sig_valid:
                    failed_verifications += 1
                    _emit(socketio, "signature_verification_failed", {
                        "attack_id":    attack_id,
                        "attack_type":  "mitm",
                        "round":        round_num,
                        "verifier":     peer_id,
                        "sender":       target_id,
                        "reason":       "data_hash_mismatch",
                    })

            # Apply per-round reputation penalty
            if failed_verifications > 0:
                _apply_reputation_penalty(
                    network_manager, socketio, target_id,
                    REPUTATION_MITM_PENALTY,
                    f"mitm_sig_verification_fail_round_{round_num}"
                )
                total_penalty += REPUTATION_MITM_PENALTY

            _emit(socketio, "attack_stage", {
                "attack_id":          attack_id,
                "attack_type":        "mitm",
                "stage":              2,
                "round":              round_num,
                "failed_verifications": failed_verifications,
                "penalty_applied":    REPUTATION_MITM_PENALTY if failed_verifications else 0,
                "message":            f"[MitM] Round {round_num}: {failed_verifications} peers rejected tampered block.",
                "target":             target_id,
            })
            time.sleep(0.5)

        # ── Stage 4: Disable interception flag ────────────────────
        node.mitm_intercepting = False

        # ── Stage 5: Complete ──────────────────────────────────────
        _emit(socketio, "attack_complete", {
            "attack_id":       attack_id,
            "attack_type":     "mitm",
            "target":          target_id,
            "tamper_count":    node.mitm_tamper_count,
            "total_penalty":   total_penalty,
            "reputation":      _get_node(network_manager, target_id).reputation,
            "status":          _get_node(network_manager, target_id).status,
            "message":         f"[MitM] Attack complete. {node.mitm_tamper_count} messages tampered. Total penalty: -{total_penalty}.",
        })
        logger.info("[MitM] Attack %s complete on %s (%d tamperings, -%d rep)",
                    attack_id, target_id, node.mitm_tamper_count, total_penalty)

    t = threading.Thread(target=_run, name=f"attack-mitm-{attack_id}", daemon=True)
    t.start()

    return {"attack_id": attack_id, "attack_type": "mitm", "target_node_id": target_id}


# ═══════════════════════════════════════════════════════════════
# Attack Registry — used by Flask routes
# ═══════════════════════════════════════════════════════════════

ATTACK_REGISTRY = {
    "sybil":     sybil_attack,
    "byzantine": byzantine_fault,
    "ddos":      ddos_flood,
    "eclipse":   eclipse_attack,
    "mitm":      mitm_attack,
}


def launch_attack(attack_type: str, network_manager, socketio, target_id: str = None) -> dict:
    """
    Unified entry point for Flask routes.

    Usage:
        result = launch_attack("sybil", network_manager, socketio, target_id="N4")
        # → {"attack_id": "SYBIL-XXXX", "attack_type": "sybil", "target_node_id": "N4"}
    """
    fn = ATTACK_REGISTRY.get(attack_type)
    if fn is None:
        raise ValueError(
            f"Unknown attack type '{attack_type}'. "
            f"Available: {list(ATTACK_REGISTRY.keys())}"
        )

    kwargs = {}
    if target_id is not None:
        kwargs["target_id"] = target_id

    return fn(network_manager, socketio, **kwargs)