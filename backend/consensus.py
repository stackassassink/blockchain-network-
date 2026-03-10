# backend/consensus.py
"""
PBFT Consensus Engine for Byzantine Fault-Tolerant Quarantine Decisions.

Network: 7 nodes total → f = 2 (max faulty), quorum = 2f+1 = 5 votes required.
Phases: PRE-PREPARE → PREPARE → COMMIT
"""

import time
import hashlib
import logging
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [PBFT] %(message)s")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Enums & Constants
# ─────────────────────────────────────────────

class Phase(Enum):
    IDLE         = "IDLE"
    PRE_PREPARE  = "PRE_PREPARE"
    PREPARE      = "PREPARE"
    COMMIT       = "COMMIT"
    COMMITTED    = "COMMITTED"
    FAILED       = "FAILED"


class VoteDecision(Enum):
    YES     = "YES"
    NO      = "NO"
    ABSTAIN = "ABSTAIN"


# Reputation thresholds
SCORE_SUSPECT_THRESHOLD   = 40   # flag as SUSPECT below this
SCORE_QUARANTINE_THRESHOLD = 20  # auto-propose quarantine below this

# Score penalties
PENALTY_FAILED_SIGNATURE  = -15
PENALTY_HASH_MISMATCH     = -25
PENALTY_DDOS_FREQUENCY    = -20

# PBFT parameters
TOTAL_NODES = 7
MAX_FAULTY  = (TOTAL_NODES - 1) // 3          # f = 2
QUORUM      = 2 * MAX_FAULTY + 1              # 2f+1 = 5


# ─────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────

@dataclass
class Vote:
    voter_id:   str
    suspect_id: str
    decision:   VoteDecision
    reason:     str
    timestamp:  float = field(default_factory=time.time)
    signature:  str   = ""

    def __post_init__(self):
        # Deterministic pseudo-signature for demo purposes
        raw = f"{self.voter_id}:{self.suspect_id}:{self.decision.value}:{self.timestamp}"
        self.signature = hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class RoundState:
    suspect_id:   str
    proposer_id:  str
    phase:        Phase       = Phase.IDLE
    view_number:  int         = 0
    sequence_num: int         = 0
    digest:       str         = ""
    votes:        dict        = field(default_factory=dict)   # voter_id → Vote
    committed:    bool        = False
    start_time:   float       = field(default_factory=time.time)

    @property
    def yes_votes(self) -> int:
        return sum(1 for v in self.votes.values() if v.decision == VoteDecision.YES)

    @property
    def no_votes(self) -> int:
        return sum(1 for v in self.votes.values() if v.decision == VoteDecision.NO)

    @property
    def total_votes(self) -> int:
        return len(self.votes)

    def quorum_reached(self) -> bool:
        return self.yes_votes >= QUORUM


# ─────────────────────────────────────────────
# Reputation Tracker
# ─────────────────────────────────────────────

class ReputationTracker:
    """
    Tracks reputation scores (0–100) for every peer node.
    Scores decay on suspicious behaviour and auto-flag / auto-propose quarantine.
    """

    def __init__(self):
        self._scores: dict[str, float] = {}
        self._events: dict[str, list]  = {}
        self._lock = threading.Lock()

    # ── internal helpers ──────────────────────

    def _ensure(self, node_id: str):
        if node_id not in self._scores:
            self._scores[node_id] = 100.0
            self._events[node_id] = []

    def _clamp(self, score: float) -> float:
        return max(0.0, min(100.0, score))

    # ── public API ────────────────────────────

    def get_score(self, node_id: str) -> float:
        with self._lock:
            self._ensure(node_id)
            return self._scores[node_id]

    def apply_penalty(self, node_id: str, penalty: int, reason: str) -> float:
        with self._lock:
            self._ensure(node_id)
            before = self._scores[node_id]
            self._scores[node_id] = self._clamp(before + penalty)
            after  = self._scores[node_id]
            self._events[node_id].append({
                "time":   time.time(),
                "reason": reason,
                "delta":  penalty,
                "score":  after,
            })
            logger.info(f"Reputation {node_id}: {before:.1f} → {after:.1f}  ({reason})")
            return after

    def record_failed_signature(self, node_id: str) -> float:
        return self.apply_penalty(node_id, PENALTY_FAILED_SIGNATURE, "failed_signature")

    def record_hash_mismatch(self, node_id: str) -> float:
        return self.apply_penalty(node_id, PENALTY_HASH_MISMATCH, "hash_mismatch")

    def record_ddos_frequency(self, node_id: str) -> float:
        return self.apply_penalty(node_id, PENALTY_DDOS_FREQUENCY, "ddos_frequency")

    def is_suspect(self, node_id: str) -> bool:
        return self.get_score(node_id) < SCORE_SUSPECT_THRESHOLD

    def should_quarantine(self, node_id: str) -> bool:
        return self.get_score(node_id) < SCORE_QUARANTINE_THRESHOLD

    def get_all_scores(self) -> dict[str, float]:
        with self._lock:
            return dict(self._scores)

    def get_events(self, node_id: str) -> list:
        with self._lock:
            self._ensure(node_id)
            return list(self._events[node_id])

    def reset(self, node_id: str):
        with self._lock:
            self._scores[node_id] = 100.0
            self._events[node_id] = []
            logger.info(f"Reputation reset for {node_id}")


# ─────────────────────────────────────────────
# PBFT Consensus Engine
# ─────────────────────────────────────────────

class PBFTConsensus:
    """
    Simplified 3-phase PBFT for quarantine decisions.

    Usage:
        consensus = PBFTConsensus(node_ids, reputation_tracker)
        result    = consensus.run_round(suspect_id="node_3")
    """

    def __init__(
        self,
        node_ids:     list[str],
        reputation:   ReputationTracker,
        leader_id:    Optional[str] = None,
        on_commit:    Optional[callable] = None,
    ):
        if len(node_ids) < 4:
            raise ValueError("PBFT requires at least 4 nodes (3f+1, f≥1).")

        self.node_ids   = list(node_ids)
        self.reputation = reputation
        self.leader_id  = leader_id or node_ids[0]
        self.on_commit  = on_commit          # callback(suspect_id) after commit

        self._total     = len(node_ids)
        self._f         = (self._total - 1) // 3
        self._quorum    = 2 * self._f + 1

        self._rounds: dict[str, RoundState] = {}
        self._seq     = 0
        self._view    = 0
        self._lock    = threading.Lock()

        logger.info(
            f"PBFT init — nodes={self._total}, f={self._f}, quorum={self._quorum}, leader={self.leader_id}"
        )

    # ─────────────────────────────────────────
    # Phase 1 — PRE-PREPARE
    # ─────────────────────────────────────────

    def pre_prepare(self, proposer_id: str, suspect_id: str) -> RoundState:
        """
        Leader broadcasts a quarantine proposal.
        Creates a new RoundState and transitions to PRE_PREPARE phase.
        """
        if proposer_id != self.leader_id:
            logger.warning(f"pre_prepare rejected: {proposer_id} is not the current leader ({self.leader_id})")
            raise PermissionError(f"{proposer_id} is not the current leader.")

        with self._lock:
            self._seq += 1
            digest = self._compute_digest(suspect_id, self._view, self._seq)

            state = RoundState(
                suspect_id   = suspect_id,
                proposer_id  = proposer_id,
                phase        = Phase.PRE_PREPARE,
                view_number  = self._view,
                sequence_num = self._seq,
                digest       = digest,
            )
            self._rounds[suspect_id] = state

        logger.info(
            f"PRE-PREPARE  proposer={proposer_id}  suspect={suspect_id}  "
            f"seq={self._seq}  digest={digest[:12]}…"
        )
        return state

    # ─────────────────────────────────────────
    # Phase 2 — PREPARE (individual vote)
    # ─────────────────────────────────────────

    def prepare(self, voter_id: str, suspect_id: str) -> Vote:
        """
        Each non-leader node casts YES/NO based on its local reputation data.
        """
        state = self._get_active_round(suspect_id)

        if voter_id in state.votes:
            logger.debug(f"prepare: {voter_id} already voted for {suspect_id}")
            return state.votes[voter_id]

        score    = self.reputation.get_score(suspect_id)
        decision = VoteDecision.YES if score < SCORE_SUSPECT_THRESHOLD else VoteDecision.NO
        reason   = (
            f"reputation_score={score:.1f} < {SCORE_SUSPECT_THRESHOLD} (SUSPECT)"
            if decision == VoteDecision.YES
            else f"reputation_score={score:.1f} ≥ {SCORE_SUSPECT_THRESHOLD} (OK)"
        )

        vote = Vote(
            voter_id   = voter_id,
            suspect_id = suspect_id,
            decision   = decision,
            reason     = reason,
        )

        with self._lock:
            state.votes[voter_id] = vote
            if state.phase == Phase.PRE_PREPARE:
                state.phase = Phase.PREPARE

        logger.info(
            f"PREPARE  voter={voter_id}  suspect={suspect_id}  "
            f"decision={decision.value}  score={score:.1f}"
        )
        return vote

    # ─────────────────────────────────────────
    # Vote collection / quorum check
    # ─────────────────────────────────────────

    def collect_votes(self, suspect_id: str) -> dict:
        """
        Simulate all nodes (except leader) casting their prepare votes,
        then return a vote summary.
        """
        state = self._get_active_round(suspect_id)

        for node_id in self.node_ids:
            if node_id == state.proposer_id:
                # Leader implicitly votes YES (it proposed the quarantine)
                if node_id not in state.votes:
                    vote = Vote(
                        voter_id   = node_id,
                        suspect_id = suspect_id,
                        decision   = VoteDecision.YES,
                        reason     = "proposer_implicit_yes",
                    )
                    with self._lock:
                        state.votes[node_id] = vote
            else:
                self.prepare(node_id, suspect_id)

        summary = {
            "suspect_id":    suspect_id,
            "total_nodes":   self._total,
            "quorum_needed": self._quorum,
            "yes":           state.yes_votes,
            "no":            state.no_votes,
            "total":         state.total_votes,
            "quorum_reached": state.quorum_reached(),
            "votes": {
                vid: {"decision": v.decision.value, "reason": v.reason}
                for vid, v in state.votes.items()
            },
        }
        logger.info(
            f"COLLECT_VOTES  suspect={suspect_id}  "
            f"yes={state.yes_votes}  no={state.no_votes}  "
            f"quorum={'✓' if state.quorum_reached() else '✗'}"
        )
        return summary

    # ─────────────────────────────────────────
    # Phase 3 — COMMIT
    # ─────────────────────────────────────────

    def commit(self, suspect_id: str) -> dict:
        """
        If quorum (2f+1 YES votes) is reached, broadcast COMMIT and trigger quarantine.
        Returns a result dict describing the outcome.
        """
        state = self._get_active_round(suspect_id)

        if not state.quorum_reached():
            with self._lock:
                state.phase = Phase.FAILED
            result = {
                "committed":  False,
                "suspect_id": suspect_id,
                "reason":     f"Quorum not reached ({state.yes_votes}/{self._quorum} YES votes)",
                "yes":        state.yes_votes,
                "no":         state.no_votes,
            }
            logger.warning(f"COMMIT FAILED  {result['reason']}")
            return result

        with self._lock:
            state.phase     = Phase.COMMIT
            state.committed = True

        logger.info(
            f"COMMIT  suspect={suspect_id}  "
            f"yes={state.yes_votes}/{self._quorum}  → QUARANTINE TRIGGERED"
        )

        # Fire external callback (e.g. network.py quarantine logic)
        if self.on_commit:
            try:
                self.on_commit(suspect_id)
            except Exception as exc:
                logger.error(f"on_commit callback raised: {exc}")

        with self._lock:
            state.phase = Phase.COMMITTED

        return {
            "committed":  True,
            "suspect_id": suspect_id,
            "yes":        state.yes_votes,
            "no":         state.no_votes,
            "quorum":     self._quorum,
            "sequence":   state.sequence_num,
            "view":       state.view_number,
            "digest":     state.digest,
            "duration_s": round(time.time() - state.start_time, 4),
        }

    # ─────────────────────────────────────────
    # Full round orchestration
    # ─────────────────────────────────────────

    def run_round(self, suspect_id: str) -> dict:
        """
        Orchestrates the full PBFT cycle:
            PRE-PREPARE → PREPARE → COLLECT VOTES → COMMIT

        Returns a complete result dict suitable for the frontend.
        """
        logger.info(f"═══ PBFT ROUND START  suspect={suspect_id}  leader={self.leader_id} ═══")

        # 1. PRE-PREPARE
        try:
            self.pre_prepare(self.leader_id, suspect_id)
        except PermissionError as exc:
            return {"error": str(exc), "committed": False}

        # 2. PREPARE + COLLECT
        vote_summary = self.collect_votes(suspect_id)

        # 3. COMMIT
        commit_result = self.commit(suspect_id)
        commit_result["vote_summary"] = vote_summary

        logger.info(
            f"═══ PBFT ROUND END  suspect={suspect_id}  "
            f"committed={commit_result['committed']} ═══"
        )
        return commit_result

    # ─────────────────────────────────────────
    # Status / introspection
    # ─────────────────────────────────────────

    def get_vote_status(self, suspect_id: Optional[str] = None) -> dict:
        """
        Returns current vote counts — used by the frontend progress bar.
        If suspect_id is None, returns status for all active rounds.
        """
        with self._lock:
            if suspect_id:
                state = self._rounds.get(suspect_id)
                if not state:
                    return {"error": f"No active round for {suspect_id}"}
                return self._state_to_status(state)

            return {
                sid: self._state_to_status(s)
                for sid, s in self._rounds.items()
            }

    def _state_to_status(self, state: RoundState) -> dict:
        return {
            "suspect_id":    state.suspect_id,
            "phase":         state.phase.value,
            "yes":           state.yes_votes,
            "no":            state.no_votes,
            "total":         state.total_votes,
            "quorum_needed": self._quorum,
            "quorum_reached": state.quorum_reached(),
            "committed":     state.committed,
            "progress_pct":  round(state.yes_votes / self._quorum * 100, 1),
        }

    # ─────────────────────────────────────────
    # Leader election
    # ─────────────────────────────────────────

    def elect_new_leader(self, exclude: Optional[str] = None) -> str:
        """
        Rotate to the next available leader (called after quarantine in network.py).
        Skips the quarantined node if provided.
        """
        candidates = [n for n in self.node_ids if n != exclude]
        if not candidates:
            raise RuntimeError("No valid leader candidates remaining.")

        # Simple round-robin view change
        self._view += 1
        new_leader = candidates[self._view % len(candidates)]
        self.leader_id = new_leader
        logger.info(f"LEADER ELECTION  view={self._view}  new_leader={new_leader}")
        return new_leader

    # ─────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────

    def _compute_digest(self, suspect_id: str, view: int, seq: int) -> str:
        raw = f"{suspect_id}|{view}|{seq}|{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_active_round(self, suspect_id: str) -> RoundState:
        state = self._rounds.get(suspect_id)
        if not state:
            raise KeyError(f"No active PBFT round for suspect '{suspect_id}'. Call pre_prepare first.")
        if state.phase in (Phase.COMMITTED, Phase.FAILED):
            raise RuntimeError(f"Round for '{suspect_id}' is already in terminal phase {state.phase.value}.")
        return state


# ─────────────────────────────────────────────
# Module-level factory (convenience)
# ─────────────────────────────────────────────

def create_consensus_engine(
    node_ids:  list[str] | None = None,
    on_commit: callable | None  = None,
) -> tuple[PBFTConsensus, ReputationTracker]:
    """
    Create a ready-to-use (PBFTConsensus, ReputationTracker) pair.

    Default: 7-node network  node_0 … node_6
    """
    if node_ids is None:
        node_ids = [f"node_{i}" for i in range(TOTAL_NODES)]

    reputation = ReputationTracker()
    consensus  = PBFTConsensus(node_ids, reputation, on_commit=on_commit)
    return consensus, reputation


# ─────────────────────────────────────────────
# Quick self-test  (python consensus.py)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("PBFT CONSENSUS ENGINE — SELF-TEST")
    print(f"Nodes: {TOTAL_NODES}  |  f: {MAX_FAULTY}  |  Quorum: {QUORUM}")
    print("=" * 60)

    consensus, reputation = create_consensus_engine()

    # Simulate node_3 misbehaving
    suspect = "node_3"
    print(f"\n[*] Degrading reputation of '{suspect}'…")
    reputation.record_failed_signature(suspect)
    reputation.record_hash_mismatch(suspect)
    reputation.record_failed_signature(suspect)
    print(f"    Reputation score: {reputation.get_score(suspect):.1f}")
    print(f"    Is suspect:       {reputation.is_suspect(suspect)}")
    print(f"    Should quarantine:{reputation.should_quarantine(suspect)}")

    print(f"\n[*] Running PBFT round for suspect='{suspect}'…\n")
    result = consensus.run_round(suspect)

    print("\n[*] RESULT:")
    for k, v in result.items():
        if k != "vote_summary":
            print(f"    {k}: {v}")

    print("\n[*] VOTE STATUS (frontend progress bar):")
    status = consensus.get_vote_status(suspect)
    for k, v in status.items():
        print(f"    {k}: {v}")

    if result.get("committed"):
        new_leader = consensus.elect_new_leader(exclude=suspect)
        print(f"\n[*] New leader elected: {new_leader}")

    print("\n✓ Self-test complete.")