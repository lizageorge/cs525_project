import time
import random
import hashlib
import json
from typing import List, Dict, Set, Any
import threading
from collections import deque
import argparse


# Configuration
BLOCK_TIME = 5  # seconds between blocks
MIN_TRANSACTIONS_PER_BLOCK = 1
MAX_TRANSACTIONS_PER_BLOCK = 50
DEBUG = False  # Enable detailed logging

# Reduce the threshold for faster consensus in simulation
CONSENSUS_THRESHOLD = 0.51  # 51% instead of 2/3 for faster convergence


class Transaction:
    def __init__(self, sender: int, receiver: int, amount: float):
        self.sender = sender
        self.receiver = receiver
        self.amount = amount
        self.timestamp = time.time()
        self.tx_hash = self._calculate_hash()

    def _calculate_hash(self) -> str:
        tx_string = f"{self.sender}{self.receiver}{self.amount}{self.timestamp}"
        return hashlib.sha256(tx_string.encode()).hexdigest()

    def __str__(self) -> str:
        return (
            f"TX: {self.sender} -> {self.receiver}: {self.amount} ({self.tx_hash[:8]})"
        )


class Block:
    def __init__(
        self,
        height: int,
        prev_hash: str,
        validator: int,
        timestamp: float,
        transactions: List[Transaction] = [],
    ):
        self.height = height
        self.prev_hash = prev_hash
        self.validator = validator
        self.timestamp = timestamp
        self.transactions: List[Transaction] = transactions
        self.votes: Set[int] = set()
        self.hash = None

    def __eq__(self, other):
        if not isinstance(other, Block):
            return False
        return (
            self.height == other.height
            and self.prev_hash == other.prev_hash
            and self.validator == other.validator
            and self.timestamp == other.timestamp
            and self.transactions == other.transactions
            and self.hash == other.hash
        )

    def __str__(self) -> str:
        return f"Block #{self.height} by Validator {self.validator} with {len(self.transactions)} txs ({self.hash[:8] if self.hash else 'pending'})"

    def add_transaction(self, tx: Transaction) -> None:
        self.transactions.append(tx)

    def finalize(self) -> None:
        # Calculate the block hash only when finalized with all transactions
        block_data = {
            "height": self.height,
            "prev_hash": self.prev_hash,
            "validator": self.validator,
            "timestamp": self.timestamp,
            "transactions": [tx.tx_hash for tx in self.transactions],
        }
        block_string = json.dumps(block_data, sort_keys=True)
        self.hash = hashlib.sha256(block_string.encode()).hexdigest()

    def get_block_identifier(self) -> str:
        """Create a unique identifier for this block based on its creator and height"""
        return f"{self.height}:{self.validator}"


class MessageBus:
    """Simulates network communication between peers"""

    def __init__(self, num_peers, latency_range=(0.05, 0.2)):
        self.messages = deque()
        self.min_latency, self.max_latency = latency_range
        self.num_peers = num_peers

    def broadcast(self, sender_id: int, msg_type: str, data: Any, exclude_ids=None):
        """Schedule a message to be delivered to all peers except those in exclude_ids"""
        if exclude_ids is None:
            exclude_ids = []

        # Add sender to excluded IDs to prevent self-messaging
        if sender_id not in exclude_ids:
            exclude_ids.append(sender_id)

        for peer_id in range(self.num_peers):
            if peer_id not in exclude_ids:
                self.send(sender_id, peer_id, msg_type, data)

    def send(self, sender_id: int, receiver_id: int, msg_type: str, data: Any):
        """Schedule a message to be delivered to a specific peer"""
        # No need to deep copy here - we'll serialize/deserialize for block proposals
        # and other data is simple enough to be copied by value

        # Simulate network latency
        latency = random.uniform(self.min_latency, self.max_latency)
        delivery_time = time.time() + latency

        self.messages.append(
            {
                "sender": sender_id,
                "receiver": receiver_id,
                "type": msg_type,
                "data": data,
                "delivery_time": delivery_time,
            }
        )

    def get_deliverable_messages(self):
        """Retrieve messages that are ready to be delivered"""
        current_time = time.time()
        deliverable = []
        remaining = deque()

        while self.messages:
            msg = self.messages.popleft()
            if msg["delivery_time"] <= current_time:
                deliverable.append(msg)
            else:
                remaining.append(msg)

        self.messages = remaining
        return deliverable


class Peer:
    """Represents a single node in the Proof of Stake network"""

    def __init__(self, peer_id: int, stake: float, message_bus: MessageBus):
        self.id = peer_id
        self.stake = stake
        self.message_bus = message_bus

        # Blockchain state
        self.blockchain: List[Block] = []
        self.pending_blocks: Dict[str, Block] = {}  # block_identifier -> Block
        self.finalized_height = (
            -1
        )  # Genesis block is at height -1 (not explicitly stored)
        self.current_hash = "genesis_hash"

        # Transaction pool
        self.tx_pool: List[Transaction] = []

        # Validator state
        self.is_current_validator = False

        # Keep track of votes we've already cast to avoid duplicate voting
        self.votes_cast: Dict[int, Set[str]] = (
            {}
        )  # height -> Set of block identifiers we've voted for

    def start(self):
        """Initialize the peer"""
        # Nothing special needed at startup
        pass

    def select_proposer(self, round_num: int, num_peers: int) -> int:
        """
        Deterministic validator selection based on stake weights
        All peers should arrive at the same conclusion
        """
        # Get all peer stakes (in a real network, this would be on-chain)
        stakes = [simulator.peers[i].stake for i in range(num_peers)]
        total_stake = sum(stakes)

        # Generate a pseudo-random number based on the round number
        # In a real blockchain, this would use VRF or similar
        seed = hashlib.sha256(f"round_{round_num}".encode()).hexdigest()
        random_value = int(seed, 16) / 2**256

        # Select validator weighted by stake
        cumulative = 0
        for i in range(num_peers):
            cumulative += stakes[i] / total_stake
            if random_value < cumulative:
                return i

        return num_peers - 1  # Fallback

    def process_messages(self):
        """Process any messages delivered to this peer"""
        messages = simulator.get_messages_for_peer(self.id)

        for msg in messages:
            try:
                if msg["type"] == "propose_block":
                    self.receive_block_proposal(msg["data"], msg["sender"])
                elif msg["type"] == "vote":
                    self.receive_vote(msg["data"], msg["sender"])
                elif msg["type"] == "transaction":
                    self.receive_transaction(msg["data"])
            except Exception as e:
                print(
                    f"Error processing message {msg['type']} from {msg['sender']}: {e}"
                )

    def propose_block(self, height: int):
        """Create and propose a new block if this peer is the validator"""
        if not self.is_current_validator:
            return

        # Create a new block
        new_block = Block(
            height=height,
            prev_hash=self.current_hash,
            validator=self.id,
            timestamp=time.time(),
        )

        # Add transactions from the pool
        num_tx = min(
            len(self.tx_pool),
            random.randint(MIN_TRANSACTIONS_PER_BLOCK, MAX_TRANSACTIONS_PER_BLOCK),
        )

        for _ in range(num_tx):
            if self.tx_pool:
                tx = self.tx_pool.pop(0)
                new_block.add_transaction(tx)

        # Vote for our own block
        new_block.votes.add(self.id)

        # Track that we've voted for this block
        if height not in self.votes_cast:
            self.votes_cast[height] = set()
        self.votes_cast[height].add(new_block.get_block_identifier())

        # Store the pending block
        block_id = new_block.get_block_identifier()
        self.pending_blocks[block_id] = new_block

        # Create a simplified version for network transmission
        block_data = {
            "height": new_block.height,
            "prev_hash": new_block.prev_hash,
            "validator": new_block.validator,
            "timestamp": new_block.timestamp,
            "transactions": new_block.transactions,
            "initial_votes": [self.id],  # Pass our vote along with the block
        }

        # Broadcast the block proposal
        self.message_bus.broadcast(
            sender_id=self.id, msg_type="propose_block", data=block_data
        )

        if DEBUG:
            print(f"[Peer {self.id}] Proposed block {height}")

        # Check if the block can be finalized (in case of a single validator)
        self.check_finalization(block_id)

    def receive_block_proposal(self, block_data: Dict, sender_id: int):
        """Process a block proposal received from another peer"""
        # Extract block information
        height = block_data["height"]
        prev_hash = block_data["prev_hash"]
        validator = block_data["validator"]
        timestamp = block_data["timestamp"]
        transactions = block_data["transactions"]
        initial_votes = block_data.get("initial_votes", [])

        # Verify the block is for the next height
        if height != self.finalized_height + 1:
            if DEBUG:
                print(
                    f"[Peer {self.id}] Rejected block at height {height} (expected {self.finalized_height + 1})"
                )
            return

        # Verify the previous hash
        if prev_hash != self.current_hash:
            if DEBUG:
                print(
                    f"[Peer {self.id}] Rejected block with prev_hash {prev_hash} (expected {self.current_hash})"
                )
            return

        # TODO attest the transactions in the block?

        # Create a block from the received data
        block = Block(height, prev_hash, validator, timestamp, transactions)

        # Add any initial votes that came with the block
        for voter in initial_votes:
            block.votes.add(voter)

        # Store the block using its identifier
        block_id = block.get_block_identifier()
        self.pending_blocks[block_id] = block

        # Vote for the block if we haven't voted for this height yet
        if height not in self.votes_cast or len(self.votes_cast[height]) == 0:
            self.vote_for_block(block)

    def vote_for_block(self, block: Block):
        """Vote for a valid block"""
        # Add our vote to the block
        block.votes.add(self.id)

        # Track that we've voted for this block
        block_id = block.get_block_identifier()
        if block.height not in self.votes_cast:
            self.votes_cast[block.height] = set()
        self.votes_cast[block.height].add(block_id)

        # Prepare vote data for broadcast
        vote_data = {
            "block_height": block.height,
            "block_validator": block.validator,
            "block_id": block_id,
            "voter": self.id,
        }

        if DEBUG:
            print(
                f"[Peer {self.id}] Voting for block at height {block.height} by validator {block.validator}"
            )

        # Broadcast the vote
        self.message_bus.broadcast(sender_id=self.id, msg_type="vote", data=vote_data)

        # Check if the block can be finalized
        self.check_finalization(block_id)

    def receive_vote(self, vote_data: Dict, sender_id: int):
        """Process a vote from another peer"""
        height = vote_data["block_height"]
        validator = vote_data["block_validator"]
        block_id = vote_data["block_id"]
        voter = vote_data["voter"]

        # Skip if we've already finalized this height
        if height <= self.finalized_height:
            return

        # Check if we have this pending block
        if block_id in self.pending_blocks:
            block = self.pending_blocks[block_id]

            # Add the vote if we haven't counted it yet
            if voter not in block.votes:
                block.votes.add(voter)
                if DEBUG:
                    print(
                        f"[Peer {self.id}] Received vote from peer {voter} for block at height {height}"
                    )

                # Check if the block can be finalized
                self.check_finalization(block_id)
        else:
            # We don't have this block yet, we need to request it
            # In a real system, we'd request the block from the network
            # For simplicity, we'll just ignore it in this simulation
            if DEBUG:
                print(f"[Peer {self.id}] Received vote for unknown block {block_id}")

    def check_finalization(self, block_id: str):
        """Check if a block has enough votes to be finalized"""
        if block_id not in self.pending_blocks:
            return

        block = self.pending_blocks[block_id]

        # Skip if we've already finalized this height or higher
        if block.height <= self.finalized_height:
            return

        # Get total stake and voter stake
        total_stake = sum(peer.stake for peer in simulator.peers)
        voter_stake = sum(
            simulator.peers[voter_id].stake
            for voter_id in block.votes
            if voter_id < len(simulator.peers)
        )

        # Check if we have enough stake voting for this block
        threshold = total_stake * CONSENSUS_THRESHOLD
        if voter_stake >= threshold:
            if DEBUG:
                print(
                    f"[Peer {self.id}] Block at height {block.height} has {len(block.votes)} votes with {voter_stake:.2f}/{total_stake:.2f} stake (threshold: {threshold:.2f})"
                )
            self.finalize_block(block)
        elif DEBUG and random.random() < 0.05:  # Occasionally print vote status
            print(
                f"[Peer {self.id}] Block at height {block.height} has {len(block.votes)} votes with {voter_stake:.2f}/{total_stake:.2f} stake (need {threshold:.2f})"
            )

    def finalize_block(self, block: Block):
        """Finalize a block and add it to the blockchain"""
        # Ensure it's the next block
        if block.height != self.finalized_height + 1:
            return

        # Finalize the block (calculates the hash)
        block.finalize()

        # Update blockchain state
        self.blockchain.append(block)
        self.finalized_height = block.height
        self.current_hash = block.hash

        # Clean up pending blocks for this height
        # First, collect all block IDs for this height
        blocks_to_remove = []
        for bid, b in self.pending_blocks.items():
            if b.height == block.height:
                blocks_to_remove.append(bid)

        # Then remove them
        for bid in blocks_to_remove:
            del self.pending_blocks[bid]

        # Clean up votes cast for this height
        if block.height in self.votes_cast:
            del self.votes_cast[block.height]

        if DEBUG:
            print(f"[Peer {self.id}] Finalized {block}")

    def receive_transaction(self, tx: Transaction):
        """Add a transaction to the pool"""
        # Real implementations would validate transactions
        # Check if we already have this transaction
        if not any(existing_tx.tx_hash == tx.tx_hash for existing_tx in self.tx_pool):
            self.tx_pool.append(tx)

    def create_transaction(self, num_peers):
        """Create a random transaction"""
        receiver = random.randint(0, num_peers - 1)
        while receiver == self.id:
            receiver = random.randint(0, num_peers - 1)

        tx = Transaction(
            sender=self.id, receiver=receiver, amount=random.uniform(1, 100)
        )

        # Add to own pool
        self.tx_pool.append(tx)

        # Broadcast to network
        self.message_bus.broadcast(sender_id=self.id, msg_type="transaction", data=tx)

        return tx


class PosSimulator:
    """Manages the entire PoS simulation"""

    
    def __init__(self, num_peers: int, min_final_chain_length: int):
        self.message_bus = MessageBus(num_peers=num_peers)
        self.peers = []
        self.current_round = 0
        self.running = False
        self.start_time = None
        self.num_peers = num_peers
        self.min_final_chain_length = min_final_chain_length

    def initialize(self):
        """Set up the simulation"""
        # Create peers with random stake
        for i in range(self.num_peers):
            # Random stake between 10 and 100
            stake = random.uniform(10, 100)
            peer = Peer(i, stake, self.message_bus)
            self.peers.append(peer)
            peer.start()

        total_stake = sum(peer.stake for peer in self.peers)
        print(f"Initialized {self.num_peers} peers with total stake: {total_stake:.2f}")

        # Display stake distribution
        print("Stake distribution:")
        for i, peer in enumerate(self.peers):
            print(f"Peer {i}: {peer.stake:.2f} ({(peer.stake/total_stake)*100:.1f}%)")

    def get_messages_for_peer(self, peer_id: int):
        """Get all messages that should be delivered to a specific peer"""
        deliverable = self.message_bus.get_deliverable_messages()
        messages_for_peer = []
        remaining_messages = []

        for msg in deliverable:
            if msg["receiver"] == peer_id:
                messages_for_peer.append(msg)
            else:
                remaining_messages.append(msg)

        # Re-add the undelivered messages back to the message bus
        for msg in remaining_messages:
            self.message_bus.messages.append(msg)

        return messages_for_peer

    def run(self):
        """Run the simulation"""
        self.running = True
        self.start_time = time.time()

        try:
            self.simulation_loop()
        except KeyboardInterrupt:
            print("\nSimulation stopped by user")
        finally:
            self.running = False
            self.print_results()

    def simulation_loop(self):
        """Main simulation loop"""
        last_block_time = time.time()
        last_status_time = time.time()

        while self.running:
            current_time = time.time()

            # Process messages for all peers
            for peer in self.peers:
                peer.process_messages()

            # Generate random transactions
            if random.random() < 0.1:  # 10% chance each loop
                peer_id = random.randint(0, self.num_peers - 1)
                tx = self.peers[peer_id].create_transaction(self.num_peers)
                if DEBUG:
                    print(f"[Peer {peer_id}] Created {tx}")

            # Time to propose a new block?
            if current_time - last_block_time >= BLOCK_TIME:
                # Select proposer for this round
                self.current_round += 1
                proposer_id = self.peers[0].select_proposer(self.current_round, self.num_peers)

                # Set validator status for all peers
                for i, peer in enumerate(self.peers):
                    peer.is_current_validator = i == proposer_id

                # New block height is the current finalized height + 1
                next_height = self.peers[0].finalized_height + 1

                # Tell validator to propose a block
                print(
                    f"\nRound {self.current_round}: Peer {proposer_id} selected as validator for height {next_height}"
                )
                self.peers[proposer_id].propose_block(next_height)

                last_block_time = current_time

            # Print status every 10 seconds (on debug mode)
            if current_time - last_status_time >= 10:
                self.print_status()
                last_status_time = current_time

            # Check if the simulation should end
            min_blockchain_length = min(len(peer.blockchain) for peer in self.peers)
            if min_blockchain_length >= self.min_final_chain_length:
                print(
                    f"\nSimulation ending: Minimum blockchain length reached ({min_blockchain_length} blocks)"
                )
                break

            # Small sleep to prevent CPU hogging
            time.sleep(0.01)

    def print_status(self):
        """Print current simulation status"""
        heights = [peer.finalized_height for peer in self.peers]
        avg_height = sum(heights) / len(heights)

        print(f"\nStatus at {time.time() - self.start_time:.1f}s:")
        print(f"Average blockchain height: {avg_height:.1f}")
        print(f"Heights: min={min(heights)}, max={max(heights)}")

        # Show pending blocks for a random peer
        sample_peer = random.choice(self.peers)
        print(
            f"Peer {sample_peer.id} has {len(sample_peer.pending_blocks)} pending blocks"
        )

        # Check vote status for current height
        next_height = max(heights) + 1
        vote_counts = {}

        for peer in self.peers:
            for _, block in peer.pending_blocks.items():
                if block.height == next_height:
                    validator = block.validator
                    if validator not in vote_counts:
                        vote_counts[validator] = []
                    vote_counts[validator].append(len(block.votes))

        if vote_counts:
            print("Votes for current height blocks:")
            for validator, counts in vote_counts.items():
                print(f"  Validator {validator}: votes seen by peers: {counts}")

            # Calculate total stake for the current height
            total_stake = sum(peer.stake for peer in self.peers)
            threshold = total_stake * CONSENSUS_THRESHOLD
            print(
                f"  Consensus threshold: {threshold:.2f} of {total_stake:.2f} total stake"
            )

    def print_results(self):
        """Print simulation results"""
        print("\n===== SIMULATION RESULTS =====")
        print(f"Ran for {time.time() - self.start_time:.2f} seconds")

        lens = [len(peer.blockchain) for peer in self.peers]

        # Find the peer with the most blocks
        max_height, max_peer = max((length, i) for i, length in enumerate(lens))
        min_height, min_peer = min((length, i) for i, length in enumerate(lens))
        print(f"Maximum blockchain height: {max_height} for peer {max_peer}")
        print(f"Minimum blockchain height: {min_height} for peer {min_peer}")

        # Check if all peers are in sync
        if all(h == lens[0] for h in lens):
            print("All peers are in sync!")
        else:
            print("Peers are out of sync:")
            for i, peer in enumerate(self.peers):
                print(f"Peer {i}: length {len(peer.blockchain)}")

        # Check that all peers have the same minimum blockchain
        sample_blockchain = self.peers[max_peer].blockchain
        all_match = True
        for i, peer in enumerate(self.peers):
            if peer.blockchain != sample_blockchain[: len(peer.blockchain)]:
                all_match = False
                print(f"Peer {i} does not match the sample blockchain!")
                print(f"  Peer {i} blockchain: {peer.blockchain}")
                print(
                    f"  Sample blockchain: {sample_blockchain[: len(peer.blockchain)]}"
                )
                break
        if all_match:
            print(f"All blockchains match till minimum heights!")
        else:
            print(f"Blockchains do not match till minimum heights!")
            for i, peer in enumerate(self.peers):
                print(f"Peer {i}: {len(peer.blockchain)} blocks")
                for block in peer.blockchain:
                    print(f"  {block}")

        # Show block distribution (who created the blocks)
        if self.peers[0].blockchain:
            validator_counts = {}
            for peer in self.peers:
                for block in peer.blockchain:
                    validator_counts[block.validator] = (
                        validator_counts.get(block.validator, 0) + 1
                    )

            print("\nBlock validator distribution:")
            for proposer_id, count in sorted(
                validator_counts.items(), key=lambda x: x[1], reverse=True
            ):
                validator_stake = self.peers[proposer_id].stake
                total_stake = sum(peer.stake for peer in self.peers)
                stake_percent = (validator_stake / total_stake) * 100
                blocks_percent = (count / len(self.peers[0].blockchain)) * 100
                print(
                    f"Peer {proposer_id}: {count} blocks ({blocks_percent:.1f}%) - Stake: {stake_percent:.1f}%"
                )


# Run the simulation
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a Proof-of-Stake blockchain simulation.")
    parser.add_argument(
        "--num_peers", type=int, required=True, help="Number of peers in the simulation"
    )
    parser.add_argument(
        "--min_final_chain_length",
        type=int,
        required=True,
        help="Minimum blockchain length to finalize the simulation",
    )
    args = parser.parse_args()


    start_time = time.time()

    simulator = PosSimulator(args.num_peers, args.min_final_chain_length)
    simulator.initialize()
    simulator.run()

    end_time = time.time()

    start_time = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(start_time)
    )
    end_time = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(end_time)
    )
    print(f"Simulation started at {start_time} and ended at {end_time}")

