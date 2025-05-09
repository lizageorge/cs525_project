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

# Autobahn specific configuration
LANE_COUNT = 4  # Number of parallel lanes
CONFIRMATION_THRESHOLD = 3  # Number of confirmations needed for finality
HIGHWAY_SYNC_INTERVAL = 10  # Seconds between highway synchronizations


class Transaction:
    def __init__(self, sender: int, receiver: int, amount: float):
        self.sender = sender
        self.receiver = receiver
        self.amount = amount
        self.timestamp = time.time()
        self.tx_hash = self._calculate_hash()
        # Assign transaction to a lane based on hash
        self.lane = int(self.tx_hash[0:8], 16) % LANE_COUNT

    def _calculate_hash(self) -> str:
        tx_string = f"{self.sender}{self.receiver}{self.amount}{self.timestamp}"
        return hashlib.sha256(tx_string.encode()).hexdigest()

    def __str__(self) -> str:
        return (
            f"TX: {self.sender} -> {self.receiver}: {self.amount} (Lane {self.lane}, {self.tx_hash[:8]})"
        )


class Block:
    def __init__(
        self,
        height: int,
        lane: int,
        prev_hash: str,
        validator: int,
        timestamp: float,
        transactions: List[Transaction] = [],
    ):
        self.height = height
        self.lane = lane  # Which lane this block belongs to
        self.prev_hash = prev_hash
        self.validator = validator
        self.timestamp = timestamp
        self.transactions: List[Transaction] = transactions
        self.confirmations: Set[int] = set()  # Peers that confirmed this block
        self.hash = None
        self.is_finalized = False

    def __eq__(self, other):
        if not isinstance(other, Block):
            return False
        return (
            self.height == other.height
            and self.lane == other.lane
            and self.prev_hash == other.prev_hash
            and self.validator == other.validator
            and self.timestamp == other.timestamp
            and self.transactions == other.transactions
            and self.hash == other.hash
        )

    def __str__(self) -> str:
        status = "finalized" if self.is_finalized else f"{len(self.confirmations)} confirms"
        return f"Block #{self.height} Lane {self.lane} by Validator {self.validator} with {len(self.transactions)} txs ({self.hash[:8] if self.hash else 'pending'}) [{status}]"

    def add_transaction(self, tx: Transaction) -> None:
        self.transactions.append(tx)

    def finalize(self) -> None:
        # Calculate the block hash only when finalized with all transactions
        block_data = {
            "height": self.height,
            "lane": self.lane,
            "prev_hash": self.prev_hash,
            "validator": self.validator,
            "timestamp": self.timestamp,
            "transactions": [tx.tx_hash for tx in self.transactions],
        }
        block_string = json.dumps(block_data, sort_keys=True)
        self.hash = hashlib.sha256(block_string.encode()).hexdigest()

    def get_block_identifier(self) -> str:
        """Create a unique identifier for this block based on its creator, lane and height"""
        return f"{self.height}:{self.lane}:{self.validator}"


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
    """Represents a single node in the Autobahn network"""

    def __init__(self, peer_id: int, throughput: float, message_bus: MessageBus):
        self.id = peer_id
        self.throughput = throughput  # Transaction processing capacity
        self.message_bus = message_bus

        # Blockchain state - now tracking multiple lanes
        self.blockchains: Dict[int, List[Block]] = {lane: [] for lane in range(LANE_COUNT)}
        self.pending_blocks: Dict[str, Block] = {}  # block_identifier -> Block
        self.finalized_heights: Dict[int, int] = {lane: -1 for lane in range(LANE_COUNT)}
        self.current_hashes: Dict[int, str] = {lane: f"genesis_hash_{lane}" for lane in range(LANE_COUNT)}

        # Transaction pool separated by lanes
        self.tx_pools: Dict[int, List[Transaction]] = {lane: [] for lane in range(LANE_COUNT)}

        # Validator state - track which lanes we're validating
        self.validating_lanes: Set[int] = set()
        
        # Track which blocks we've confirmed
        self.confirmed_blocks: Dict[int, Set[str]] = {}  # height -> Set of block IDs we've confirmed
        
        # Last time we synchronized across lanes
        self.last_highway_sync = time.time()
        
        # Highway data - cross-lane references
        self.highway_references: Dict[int, Dict[int, str]] = {}  # height -> (lane -> block_hash)

    def start(self):
        """Initialize the peer"""
        # Assign lanes to validate based on throughput
        lane_assignments = simulator.assign_lanes(self.id)
        self.validating_lanes = set(lane_assignments)
        
        if DEBUG:
            print(f"[Peer {self.id}] Assigned to validate lanes: {self.validating_lanes}")

    def select_validator_for_lane(self, lane: int, round_num: int) -> int:
        """
        Determine which peer should validate a specific lane in this round
        All peers should arrive at the same conclusion
        """
        # Get all peers assigned to this lane
        lane_validators = []
        for peer_id in range(len(simulator.peers)):
            if lane in simulator.peers[peer_id].validating_lanes:
                lane_validators.append(peer_id)
        
        if not lane_validators:
            # Fallback - assign to a random peer
            return random.randint(0, len(simulator.peers) - 1)
            
        # Generate a deterministic rotation based on round
        seed = hashlib.sha256(f"lane_{lane}_round_{round_num}".encode()).hexdigest()
        random_value = int(seed, 16) % len(lane_validators)
        
        return lane_validators[random_value]

    def process_messages(self):
        """Process any messages delivered to this peer"""
        messages = simulator.get_messages_for_peer(self.id)

        for msg in messages:
            try:
                if msg["type"] == "propose_block":
                    self.receive_block_proposal(msg["data"], msg["sender"])
                elif msg["type"] == "confirm_block":
                    self.receive_confirmation(msg["data"], msg["sender"])
                elif msg["type"] == "transaction":
                    self.receive_transaction(msg["data"])
                elif msg["type"] == "highway_sync":
                    self.receive_highway_sync(msg["data"], msg["sender"])
            except Exception as e:
                print(
                    f"Error processing message {msg['type']} from {msg['sender']}: {e}"
                )

    def propose_blocks(self, round_num: int):
        """Create and propose new blocks for each lane we're responsible for"""
        for lane in self.validating_lanes:
            validator_for_lane = self.select_validator_for_lane(lane, round_num)
            
            if validator_for_lane == self.id:
                # We're the validator for this lane in this round
                next_height = self.finalized_heights[lane] + 1
                
                # Create a new block
                new_block = Block(
                    height=next_height,
                    lane=lane,
                    prev_hash=self.current_hashes[lane],
                    validator=self.id,
                    timestamp=time.time(),
                )

                # Add transactions from the lane's pool
                num_tx = min(
                    len(self.tx_pools[lane]),
                    random.randint(MIN_TRANSACTIONS_PER_BLOCK, MAX_TRANSACTIONS_PER_BLOCK),
                )

                for _ in range(num_tx):
                    if self.tx_pools[lane]:
                        tx = self.tx_pools[lane].pop(0)
                        new_block.add_transaction(tx)

                # Confirm our own block
                new_block.confirmations.add(self.id)

                # Track that we've confirmed this block
                block_id = new_block.get_block_identifier()
                if next_height not in self.confirmed_blocks:
                    self.confirmed_blocks[next_height] = set()
                self.confirmed_blocks[next_height].add(block_id)

                # Store the pending block
                self.pending_blocks[block_id] = new_block

                # Add highway references if needed
                if self.should_create_highway_reference(next_height):
                    self.add_highway_references(new_block)

                # Finalize the block for network transmission
                new_block.finalize()

                # Create a simplified version for network transmission
                block_data = {
                    "height": new_block.height,
                    "lane": new_block.lane,
                    "prev_hash": new_block.prev_hash,
                    "validator": new_block.validator,
                    "timestamp": new_block.timestamp,
                    "transactions": new_block.transactions,
                    "initial_confirmations": [self.id],  # Pass our confirmation
                    "hash": new_block.hash,
                    "highway_refs": self.get_highway_refs_for_block(new_block),
                }

                # Broadcast the block proposal
                self.message_bus.broadcast(
                    sender_id=self.id, msg_type="propose_block", data=block_data
                )

                if DEBUG:
                    print(f"[Peer {self.id}] Proposed block at height {next_height} for lane {lane}")

                # Check if the block can be finalized
                self.check_finalization(block_id)

    def should_create_highway_reference(self, height: int) -> bool:
        """Determine if a highway reference should be created at this height"""
        # Create a highway reference every 5 blocks
        return height % 5 == 0

    def add_highway_references(self, block: Block):
        """Add cross-lane references to a block"""
        refs = {}
        
        # Add references to the latest blocks in other lanes
        for other_lane in range(LANE_COUNT):
            if other_lane != block.lane and self.blockchains[other_lane]:
                latest_block = self.blockchains[other_lane][-1]
                refs[other_lane] = latest_block.hash
        
        # Store these references
        if block.height not in self.highway_references:
            self.highway_references[block.height] = {}
        
        self.highway_references[block.height].update(refs)

    def get_highway_refs_for_block(self, block: Block) -> Dict[int, str]:
        """Get the highway references for a block"""
        if block.height in self.highway_references:
            return self.highway_references[block.height]
        return {}

    def receive_block_proposal(self, block_data: Dict, sender_id: int):
        """Process a block proposal received from another peer"""
        # Extract block information
        height = block_data["height"]
        lane = block_data["lane"]
        prev_hash = block_data["prev_hash"]
        validator = block_data["validator"]
        timestamp = block_data["timestamp"]
        transactions = block_data["transactions"]
        initial_confirmations = block_data.get("initial_confirmations", [])
        block_hash = block_data.get("hash")
        highway_refs = block_data.get("highway_refs", {})

        # Verify the block is for the next height in its lane
        if height != self.finalized_heights[lane] + 1:
            if DEBUG:
                print(
                    f"[Peer {self.id}] Rejected block at height {height} for lane {lane} (expected {self.finalized_heights[lane] + 1})"
                )
            return

        # Verify the previous hash for this lane
        if prev_hash != self.current_hashes[lane]:
            if DEBUG:
                print(
                    f"[Peer {self.id}] Rejected block with prev_hash {prev_hash} for lane {lane} (expected {self.current_hashes[lane]})"
                )
            return

        # Create a block from the received data
        block = Block(height, lane, prev_hash, validator, timestamp, transactions)
        block.hash = block_hash  # Set the hash directly

        # Add any initial confirmations that came with the block
        for confirmer in initial_confirmations:
            block.confirmations.add(confirmer)

        # Store the block using its identifier
        block_id = block.get_block_identifier()
        self.pending_blocks[block_id] = block

        # Store highway references if present
        if highway_refs and height not in self.highway_references:
            self.highway_references[height] = highway_refs

        # Confirm the block if it's valid
        self.confirm_block(block)

    def confirm_block(self, block: Block):
        """Confirm a valid block"""
        # Add our confirmation to the block
        block.confirmations.add(self.id)

        # Track that we've confirmed this block
        block_id = block.get_block_identifier()
        if block.height not in self.confirmed_blocks:
            self.confirmed_blocks[block.height] = set()
        self.confirmed_blocks[block.height].add(block_id)

        # Prepare confirmation data for broadcast
        confirm_data = {
            "block_height": block.height,
            "block_lane": block.lane,
            "block_validator": block.validator,
            "block_id": block_id,
            "confirmer": self.id,
        }

        if DEBUG:
            print(
                f"[Peer {self.id}] Confirming block at height {block.height} lane {block.lane} by validator {block.validator}"
            )

        # Broadcast the confirmation
        self.message_bus.broadcast(sender_id=self.id, msg_type="confirm_block", data=confirm_data)

        # Check if the block can be finalized
        self.check_finalization(block_id)

    def receive_confirmation(self, confirm_data: Dict, sender_id: int):
        """Process a confirmation from another peer"""
        height = confirm_data["block_height"]
        lane = confirm_data["block_lane"]
        validator = confirm_data["block_validator"]
        block_id = confirm_data["block_id"]
        confirmer = confirm_data["confirmer"]

        # Skip if we've already finalized this height for this lane
        if height <= self.finalized_heights[lane]:
            return

        # Check if we have this pending block
        if block_id in self.pending_blocks:
            block = self.pending_blocks[block_id]

            # Add the confirmation if we haven't counted it yet
            if confirmer not in block.confirmations:
                block.confirmations.add(confirmer)
                if DEBUG:
                    print(
                        f"[Peer {self.id}] Received confirmation from peer {confirmer} for block at height {height} lane {lane}"
                    )

                # Check if the block can be finalized
                self.check_finalization(block_id)
        else:
            # We don't have this block yet, we need to request it
            # In a real system, we'd request the block from the network
            # For simplicity, we'll just ignore it in this simulation
            if DEBUG:
                print(f"[Peer {self.id}] Received confirmation for unknown block {block_id}")

    def check_finalization(self, block_id: str):
        """Check if a block has enough confirmations to be finalized"""
        if block_id not in self.pending_blocks:
            return

        block = self.pending_blocks[block_id]

        # Skip if we've already finalized this height for this lane
        if block.height <= self.finalized_heights[block.lane]:
            return

        # Check if we have enough confirmations
        if len(block.confirmations) >= CONFIRMATION_THRESHOLD:
            if DEBUG:
                print(
                    f"[Peer {self.id}] Block at height {block.height} lane {block.lane} has {len(block.confirmations)} confirmations (threshold: {CONFIRMATION_THRESHOLD})"
                )
            self.finalize_block(block)
        elif DEBUG and random.random() < 0.05:  # Occasionally print confirmation status
            print(
                f"[Peer {self.id}] Block at height {block.height} lane {block.lane} has {len(block.confirmations)} confirmations (need {CONFIRMATION_THRESHOLD})"
            )

    def finalize_block(self, block: Block):
        """Finalize a block and add it to the lane's blockchain"""
        lane = block.lane
        
        # Ensure it's the next block for this lane
        if block.height != self.finalized_heights[lane] + 1:
            return

        # Mark as finalized
        block.is_finalized = True

        # Update blockchain state for this lane
        self.blockchains[lane].append(block)
        self.finalized_heights[lane] = block.height
        self.current_hashes[lane] = block.hash

        # Clean up pending blocks for this height and lane
        blocks_to_remove = []
        for bid, b in self.pending_blocks.items():
            if b.height == block.height and b.lane == lane:
                blocks_to_remove.append(bid)

        # Then remove them
        for bid in blocks_to_remove:
            del self.pending_blocks[bid]

        # Clean up confirmations for this height
        if block.height in self.confirmed_blocks:
            # Only remove confirmations for this lane's blocks
            self.confirmed_blocks[block.height] = {
                bid for bid in self.confirmed_blocks[block.height]
                if self.get_lane_from_block_id(bid) != lane
            }
            
            # If empty, remove the height entry
            if not self.confirmed_blocks[block.height]:
                del self.confirmed_blocks[block.height]

        if DEBUG:
            print(f"[Peer {self.id}] Finalized {block}")

    def get_lane_from_block_id(self, block_id: str) -> int:
        """Extract the lane from a block identifier"""
        parts = block_id.split(":")
        if len(parts) >= 2:
            return int(parts[1])
        return 0  # Default lane

    def check_highway_sync(self):
        """Periodically synchronize across lanes via the highway"""
        current_time = time.time()
        
        # Sync every HIGHWAY_SYNC_INTERVAL seconds
        if current_time - self.last_highway_sync >= HIGHWAY_SYNC_INTERVAL:
            self.last_highway_sync = current_time
            
            # Prepare highway sync data - latest known block for each lane
            sync_data = {}
            for lane in range(LANE_COUNT):
                if self.blockchains[lane]:
                    latest_block = self.blockchains[lane][-1]
                    sync_data[lane] = {
                        "height": latest_block.height,
                        "hash": latest_block.hash
                    }
            
            # Broadcast to network
            if sync_data:
                self.message_bus.broadcast(
                    sender_id=self.id, msg_type="highway_sync", data=sync_data
                )
                
                if DEBUG and random.random() < 0.2:
                    print(f"[Peer {self.id}] Broadcasting highway sync: {sync_data}")

    def receive_highway_sync(self, sync_data: Dict, sender_id: int):
        """Process highway synchronization from another peer"""
        # Process lane data
        for lane, data in sync_data.items():
            lane = int(lane)
            remote_height = data["height"]
            remote_hash = data["hash"]
            
            # If remote peer is ahead of us for this lane, we could request blocks
            # In a real implementation - for simplicity, just log
            if remote_height > self.finalized_heights[lane]:
                if DEBUG and random.random() < 0.1:
                    print(f"[Peer {self.id}] Peer {sender_id} has lane {lane} at height {remote_height}, we're at {self.finalized_heights[lane]}")
                    
                # In a real implementation, we would request missing blocks
                # self.request_blocks(lane, self.finalized_heights[lane] + 1, remote_height)

    def receive_transaction(self, tx: Transaction):
        """Add a transaction to the appropriate lane pool"""
        # Check if we already have this transaction
        lane = tx.lane
        if not any(existing_tx.tx_hash == tx.tx_hash for existing_tx in self.tx_pools[lane]):
            self.tx_pools[lane].append(tx)

    def create_transaction(self, num_peers):
        """Create a random transaction"""
        receiver = random.randint(0, num_peers - 1)
        while receiver == self.id:
            receiver = random.randint(0, num_peers - 1)

        tx = Transaction(
            sender=self.id, receiver=receiver, amount=random.uniform(1, 100)
        )

        # Add to own pool based on the lane
        lane = tx.lane
        self.tx_pools[lane].append(tx)

        # Broadcast to network
        self.message_bus.broadcast(sender_id=self.id, msg_type="transaction", data=tx)

        return tx


class AutobahnSimulator:
    """Manages the entire Autobahn simulation"""

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
        # Create peers with random throughput capacity
        for i in range(self.num_peers):
            # Random throughput between 10 and 100 transactions per second
            throughput = random.uniform(10, 100)
            peer = Peer(i, throughput, self.message_bus)
            self.peers.append(peer)
        
        # Assign lanes to peers based on throughput
        self.assign_all_lanes()
        
        # Start all peers
        for peer in self.peers:
            peer.start()

        total_throughput = sum(peer.throughput for peer in self.peers)
        print(f"Initialized {self.num_peers} peers with total throughput: {total_throughput:.2f} tx/s")

        # Display throughput distribution
        print("Throughput distribution:")
        for i, peer in enumerate(self.peers):
            print(f"Peer {i}: {peer.throughput:.2f} tx/s ({(peer.throughput/total_throughput)*100:.1f}%)")
            print(f"  Validating lanes: {peer.validating_lanes}")

    def assign_all_lanes(self):
        """Assign lanes to peers based on their throughput capacity"""
        # Each lane should have multiple validators for redundancy
        target_validators_per_lane = max(3, self.num_peers // 2)
        
        for lane in range(LANE_COUNT):
            # Sort peers by throughput (highest first) and assign to lanes
            sorted_peers = sorted(
                [(i, peer.throughput) for i, peer in enumerate(self.peers)],
                key=lambda x: x[1],
                reverse=True
            )
            
            # Assign this lane to the top validators
            for i in range(min(target_validators_per_lane, self.num_peers)):
                peer_id = sorted_peers[i][0]
                self.peers[peer_id].validating_lanes.add(lane)
    
    def assign_lanes(self, peer_id: int) -> List[int]:
        """Get the lanes assigned to a specific peer"""
        return list(self.peers[peer_id].validating_lanes)

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

            # Check for highway synchronization
            for peer in self.peers:
                peer.check_highway_sync()

            # Time to propose new blocks?
            if current_time - last_block_time >= BLOCK_TIME:
                # Increment round number
                self.current_round += 1
                
                # Each peer proposes blocks for their assigned lanes
                for peer in self.peers:
                    peer.propose_blocks(self.current_round)

                last_block_time = current_time

            # Print status every 10 seconds (on debug mode)
            if current_time - last_status_time >= 10:
                self.print_status()
                last_status_time = current_time

            # Check if the simulation should end
            min_blockchain_length = min(
                len(peer.blockchains[0]) for peer in self.peers
            )  # Check first lane as benchmark
            if min_blockchain_length >= self.min_final_chain_length:
                print(
                    f"\nSimulation ending: Minimum blockchain length reached ({min_blockchain_length} blocks in lane 0)"
                )
                break

            # Small sleep to prevent CPU hogging
            time.sleep(0.01)

    def print_status(self):
        """Print current simulation status"""
        print(f"\nStatus at {time.time() - self.start_time:.1f}s:")
        
        # Show status for each lane
        for lane in range(LANE_COUNT):
            heights = [peer.finalized_heights[lane] for peer in self.peers]
            avg_height = sum(heights) / len(heights)
            
            print(f"Lane {lane}: Avg height={avg_height:.1f}, min={min(heights)}, max={max(heights)}")
        
        # Show transaction counts in pools
        total_pending = {}
        for lane in range(LANE_COUNT):
            total_pending[lane] = sum(len(peer.tx_pools[lane]) for peer in self.peers)
        
        print(f"Pending transactions by lane: {total_pending}")
        
        # Show a sample peer's state
        sample_peer = random.choice(self.peers)
        print(f"Peer {sample_peer.id} has {len(sample_peer.pending_blocks)} pending blocks")
        
        # Show confirmations for a sample lane and height
        sample_lane = 0
        next_height = max(sample_peer.finalized_heights[sample_lane] + 1, 0)
        
        confirmation_counts = {}
        for peer in self.peers:
            for block_id, block in peer.pending_blocks.items():
                if block.height == next_height and block.lane == sample_lane:
                    validator = block.validator
                    if validator not in confirmation_counts:
                        confirmation_counts[validator] = []
                    confirmation_counts[validator].append(len(block.confirmations))
        
        if confirmation_counts:
            print(f"Lane {sample_lane} Height {next_height} confirmations:")
            for validator, counts in confirmation_counts.items():
                print(f"  Validator {validator}: confirmations seen by peers: {counts}")

    def print_results(self):
        """Print simulation results"""
        print("\n===== SIMULATION RESULTS =====")
        print(f"Ran for {time.time() - self.start_time:.2f} seconds")

        # Print results for each lane
        for lane in range(LANE_COUNT):
            print(f"\n=== LANE {lane} RESULTS ===")
            lens = [len(peer.blockchains[lane]) for peer in self.peers]

            # Find the peer with the most blocks for this lane
            max_height, max_peer = max((length, i) for i, length in enumerate(lens))
            min_height, min_peer = min((length, i) for i, length in enumerate(lens))
            print(f"Maximum blockchain height: {max_height} for peer {max_peer}")
            print(f"Minimum blockchain height: {min_height} for peer {min_peer}")

            # Check if all peers are in sync for this lane
            if all(h == lens[0] for h in lens):
                print(f"All peers are in sync for lane {lane}!")
            else:
                print(f"Peers are out of sync for lane {lane}:")
                for i, peer in enumerate(self.peers):
                    print(f"Peer {i}: length {len(peer.blockchains[lane])}")

            # Check that all peers have the same minimum blockchain
            if max_height > 0:
                sample_blockchain = self.peers[max_peer].blockchains[lane]
                all_match = True
                for i, peer in enumerate(self.peers):
                    peer_chain = peer.blockchains[lane]
                    if len(peer_chain) > 0 and peer_chain != sample_blockchain[: len(peer_chain)]:
                        all_match = False
                        print(f"Peer {i}'s lane {lane} blockchain does not match the sample!")
                        break
                
                if all_match:
                    print(f"All lane {lane} blockchains match till minimum heights!")
                
                # Show block distribution (who created the blocks)
                validator_counts = {}
                for peer in self.peers:
                    if peer.blockchains[lane]:
                        for block in peer.blockchains[lane]:
                            validator_counts[block.validator] = (
                                validator_counts.get(block.validator, 0) + 1
                            )

                print(f"\nLane {lane} block validator distribution:")
                for validator_id, count in sorted(
                    validator_counts.items(), key=lambda x: x[1], reverse=True
                ):
                    validator_throughput = self.peers[validator_id].throughput
                    total_throughput = sum(peer.throughput for peer in self.peers)
                    throughput_percent = (validator_throughput / total_throughput) * 100
                    blocks_percent = (count / max_height) * 100 if max_height > 0 else 0
                    print(
                        f"Peer {validator_id}: {count} blocks ({blocks_percent:.1f}%) - Throughput: {throughput_percent:.1f}%"
                    )
        
        # Compare throughput across lanes
        print("\n=== CROSS-LANE COMPARISON ===")
        total_blocks_by_lane = {}
        for lane in range(LANE_COUNT):
            total_blocks = sum(len(peer.blockchains[lane]) for peer in self.peers) / len(self.peers)
            total_blocks_by_lane[lane] = total_blocks
            print(f"Lane {lane}: Average of {total_blocks:.1f} blocks")
        
        # Calculate total transactions processed
        total_tx = 0
        for lane in range(LANE_COUNT):
            for peer in self.peers:
                for block in peer.blockchains[lane]:
                    total_tx += len(block.transactions)
            
        # Divide by number of peers to get average
        avg_tx = total_tx / len(self.peers)
        print(f"\nTotal transactions processed (average): {avg_tx:.0f}")
        
        simulation_time = time.time() - self.start_time
        throughput = avg_tx / simulation_time
        print(f"Average throughput: {throughput:.2f} tx/sec")


# Run the simulation
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an Autobahn blockchain simulation.")
    parser.add_argument(
        "--num_peers", type=int, required=True, help="Number of peers in the simulation"
    )
    parser.add_argument(
        "--min_final_chain_length",
        type=int,
        required=True,
        help="Minimum blockchain length to finalize the simulation",
    )
    parser.add_argument(
        "--lane_count",
        type=int,
        default=LANE_COUNT,
        help=f"Number of lanes to use (default: {LANE_COUNT})",
    )
    args = parser.parse_args()

    # Update global configuration if provided
    if args.lane_count:
        LANE_COUNT = args.lane_count

    start_time = time.time()

    simulator = AutobahnSimulator(args.num_peers, args.min_final_chain_length)
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