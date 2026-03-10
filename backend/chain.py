import hashlib
import json
import time


class Block:
    def __init__(self, index, data, previous_hash):
        self.index = index
        self.timestamp = time.time()
        self.data = data
        self.previous_hash = previous_hash
        self.nonce = 0
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        """SHA-256 hash over all block fields."""
        block_string = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce
        }, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()

    def mine_block(self, difficulty=3):
        """
        Proof-of-work: increment nonce until hash starts with
        `difficulty` leading zeros (default: '000').
        """
        target = "0" * difficulty
        print(f"  Mining block {self.index}...", end=" ")
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.calculate_hash()
        print(f"mined! nonce={self.nonce}  hash={self.hash[:20]}...")

    def to_dict(self):
        """Serialize block to a JSON-safe dict."""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash
        }


class Blockchain:
    DIFFICULTY = 3  # leading zeros required for proof-of-work

    def __init__(self):
        self.chain = [self._create_genesis_block()]

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _create_genesis_block(self):
        """Block #0 — the anchor of the chain."""
        genesis = Block(index=0, data="Genesis Block", previous_hash="0")
        genesis.mine_block(self.DIFFICULTY)
        return genesis

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def get_latest_block(self):
        """Return the most recently appended block."""
        return self.chain[-1]

    def add_block(self, data):
        """
        Create a new block, mine it, then append it to the chain.

        Args:
            data: Any JSON-serialisable payload (dict, str, list …).
        """
        new_block = Block(
            index=len(self.chain),
            data=data,
            previous_hash=self.get_latest_block().hash
        )
        new_block.mine_block(self.DIFFICULTY)
        self.chain.append(new_block)

    def is_chain_valid(self):
        """
        Walk the chain and verify two invariants for every block
        (except the genesis):

          1. The stored hash still matches a freshly recalculated hash
             — detects any tampering with block fields.
          2. previous_hash matches the actual hash of the preceding block
             — detects insertion / removal / reordering of blocks.

        Returns:
            bool: True if the entire chain is intact, False otherwise.
        """
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            # 1 — recalculate and compare hash
            if current.hash != current.calculate_hash():
                print(f"  [INVALID] Block {i} hash mismatch.")
                return False

            # 2 — verify linkage to previous block
            if current.previous_hash != previous.hash:
                print(f"  [INVALID] Block {i} broken link to block {i - 1}.")
                return False

        return True

    def to_dict(self):
        """
        Serialize the entire chain to a list of dicts, ready for
        JSON encoding and transmission over sockets.
        """
        return [block.to_dict() for block in self.chain]


# --------------------------------------------------------------------------- #
#  Standalone test — run:  python backend/chain.py                            #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    print("=" * 60)
    print("  Building blockchain …")
    print("=" * 60)

    bc = Blockchain()
    bc.add_block({"tx": "Alice -> Bob: 10 ETH"})
    bc.add_block({"tx": "Bob -> Carol: 5 ETH"})

    print()
    print(f"Chain valid: {bc.is_chain_valid()}")
    print(f"Blocks:      {len(bc.chain)}")

    print()
    print("Block summary:")
    for block in bc.chain:
        print(f"  [{block.index}] hash={block.hash[:16]}...  "
              f"prev={block.previous_hash[:16]}...  "
              f"data={str(block.data)[:30]}")

    # ------------------------------------------------------------------ #
    #  Tamper detection demo                                               #
    # ------------------------------------------------------------------ #
    print()
    print("Tampering with block 1 data …")
    bc.chain[1].data = {"tx": "Alice -> Bob: 9999 ETH"}   # mutate without re-mining
    print(f"Chain valid after tamper: {bc.is_chain_valid()}")