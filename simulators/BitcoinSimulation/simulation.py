import time
import random
import hashlib
import json
from typing import List, Dict, Set, Any, Tuple, Optional
from collections import deque
import threading
import argparse

# Configuration
NUM_PEERS = 20
BLOCK_TIME = 5  # seconds between blocks
MIN_TRANSACTIONS_PER_BLOCK = 1
MAX_TRANSACTIONS_PER_BLOCK = 50
SIMULATION_TIME = 120  # seconds to run the simulation
DEBUG = True  # Enable detailed logging
# Difficulty for mining (number of leading zeros in the hash)
DIFFICULTY = 5  # Adjust this for more or less difficulty

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
        return f"TX: {self.sender} -> {self.receiver}: {self.amount} ({self.tx_hash[:8]})"
    
    def to_dict(self) -> Dict:
        """Convert transaction to dictionary for serialization"""
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "tx_hash": self.tx_hash
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Transaction':
        """Create a transaction from dictionary data"""
        tx = cls(data["sender"], data["receiver"], data["amount"])
        tx.timestamp = data["timestamp"]
        tx.tx_hash = data["tx_hash"]
        return tx

class Block:
    def __init__(self, height: int, prev_hash: str, miner: int, timestamp: float):
        self.height = height
        self.prev_hash = prev_hash
        self.miner = miner  # ID of the miner who created this block
        self.timestamp = timestamp
        self.transactions: List[Transaction] = []
        self.nonce = 0  # Nonce for mining
        self.hash = None  # Will be calculated when finalized
    
    def add_transaction(self, tx: Transaction) -> None:
        self.transactions.append(tx)
    
    def finalize(self) -> None:
        # Calculate the block hash only when finalized with all transactions
        self.hash = self.calculate_hash()
    
    def mine(self) -> bool:
        """Mine the block by finding a valid hash"""
        while True:
            self.hash = self.calculate_hash()
            if self.hash.startswith('0' * DIFFICULTY):
                return True
            self.nonce += 1
    
    def calculate_hash(self) -> str:
        """Calculate the hash of the block"""
        block_data = {
            "height": self.height,
            "prev_hash": self.prev_hash,
            "miner": self.miner,
            "timestamp": self.timestamp,
            "transactions": [tx.tx_hash for tx in self.transactions],
            "nonce": self.nonce
        }
        block_string = json.dumps(block_data, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()
    
    def __str__(self) -> str:
        return f"Block #{self.height} mined by {self.miner} with {len(self.transactions)} txs ({self.hash[:8] if self.hash else 'pending'})"
    
    def to_dict(self) -> Dict:
        """Convert block to dictionary for serialization"""
        return {
            "height": self.height,
            "prev_hash": self.prev_hash,
            "miner": self.miner,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "nonce": self.nonce,
            "hash": self.hash
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Block':
        """Create a block from dictionary data"""
        block = cls(data["height"], data["prev_hash"], data["miner"], data["timestamp"])
        block.nonce = data["nonce"]
        block.hash = data["hash"]
        block.transactions = [Transaction.from_dict(tx_data) for tx_data in data["transactions"]]
        return block
    
    def verify_pow(self) -> bool:
        """Verify the proof of work for this block"""
        calculated_hash = self.calculate_hash()
        return (calculated_hash == self.hash and 
                self.hash.startswith('0' * DIFFICULTY))

class MessageBus:
    """Simulates network communication between peers"""
    def __init__(self, num_peers:int, latency_range=(0.05, 0.2)):
        self.messages = deque()
        self.min_latency, self.max_latency = latency_range
        self.num_peers = num_peers
        self.lock = threading.Lock()  # Add lock for thread safety
    
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
        
        with self.lock:
            self.messages.append({
                "sender": sender_id,
                "receiver": receiver_id,
                "type": msg_type,
                "data": data,
                "delivery_time": delivery_time
            })
    
    def get_deliverable_messages(self):
        """Retrieve messages that are ready to be delivered"""
        current_time = time.time()
        deliverable = []
        remaining = deque()
        
        with self.lock:
            while self.messages:
                msg = self.messages.popleft()
                if msg["delivery_time"] <= current_time:
                    deliverable.append(msg)
                else:
                    remaining.append(msg)
            
            self.messages = remaining
        
        return deliverable

class Peer:
    """Represents a single node in the Proof of Work network"""
    def __init__(self, peer_id: int, message_bus: MessageBus, num_peers:int):
        self.id = peer_id
        self.message_bus = message_bus
        self.num_peers = num_peers
        
        # Blockchain state
        self.blockchain: List[Block] = []
        self.pending_blocks: Dict[str, Block] = {}  # block_hash -> Block
        self.block_by_height: Dict[int, Set[str]] = {}  # height -> set of block hashes
        self.finalized_height = -1  # Genesis block is at height -1 (not explicitly stored)
        self.current_hash = "genesis_hash"
        
        # Transaction pool and seen transactions
        self.tx_pool: List[Transaction] = []
        self.tx_seen: Set[str] = set()  # Set of seen transaction hashes
        
        # Mining state
        self.block_mined = False  # Flag to indicate if this peer has mined the block
        self.lock = threading.Lock()  # Lock for thread safety
        
        # Miner state
        self.is_current_miner = False
        
        # Block request tracking
        self.pending_block_requests: Dict[Tuple[int, str], float] = {}  # (height, prev_hash) -> request_time
    
    def start(self):
        """Initialize the peer"""
        pass
    
    def process_messages(self):
        """Process any messages delivered to this peer"""
        messages = simulator.get_messages_for_peer(self.id)
        
        for msg in messages:
            if msg["type"] == "propose_block":
                self.receive_block_proposal(msg["data"], msg["sender"])
            elif msg["type"] == "transaction":
                self.receive_transaction(msg["data"])
            elif msg["type"] == "request_block":
                self.handle_block_request(msg["data"], msg["sender"])
            elif msg["type"] == "block_response":
                self.handle_block_response(msg["data"])
    
    def propose_block(self, height: int, block_mined: list):
        """Create and propose a new block if this peer is allowed to mine"""
        if not self.is_current_miner:
            return
        
        # Create a new block
        block = Block(
            height=height,
            prev_hash=self.current_hash,
            miner=self.id,
            timestamp=time.time()
        )
        
        # Add transactions from the pool
        num_tx = min(
            len(self.tx_pool),
            random.randint(MIN_TRANSACTIONS_PER_BLOCK, MAX_TRANSACTIONS_PER_BLOCK)
        )
        
        for _ in range(num_tx):
            if self.tx_pool:
                tx = self.tx_pool.pop(0)
                block.add_transaction(tx)

        # Start mining
        while not self.block_mined and not block_mined[0]:
            block.hash = block.calculate_hash()
            if block.hash.startswith('0' * DIFFICULTY):
                with self.lock:  # Use lock to prevent race conditions
                    if not block_mined[0]:  # Check again to avoid race condition
                        self.block_mined = True
                        block_mined[0] = True  # Set that a peer has mined
                        print(f"[Peer {self.id}] Mined block {block.height} with hash {block.hash[:8]}")
                        
                        # Store the block locally first
                        self.store_block(block)
                        
                        # Broadcast the mined block
                        self.message_bus.broadcast(
                            sender_id=self.id,
                            msg_type="propose_block",
                            data=block.to_dict()
                        )
                    break
            block.nonce += 1
    
    def store_block(self, block: Block):
        """Store a block in local data structures"""
        # Store by hash
        self.pending_blocks[block.hash] = block
        
        # Add to height mapping
        if block.height not in self.block_by_height:
            self.block_by_height[block.height] = set()
        self.block_by_height[block.height].add(block.hash)
        
        # If this block extends our current chain, update accordingly
        if block.height == self.finalized_height + 1 and block.prev_hash == self.current_hash:
            self.add_to_blockchain(block)
    
    def add_to_blockchain(self, block: Block):
        """Add a validated block to the blockchain"""
        self.blockchain.append(block)
        self.finalized_height = block.height
        self.current_hash = block.hash
        
        # Print confirmation of the finalized block
        if DEBUG:
            print(f"[Peer {self.id}] Finalized block {block.height} with hash {block.hash[:8]}")
        
        # Continue chain if we have the next block already
        next_height = block.height + 1
        if next_height in self.block_by_height:
            for block_hash in self.block_by_height[next_height]:
                next_block = self.pending_blocks[block_hash]
                if next_block.prev_hash == block.hash:
                    self.add_to_blockchain(next_block)
                    break
    
    def receive_block_proposal(self, block_data: Dict, sender_id: int):
        """Process a block proposal received from another peer"""
        # Create block from data
        block = Block.from_dict(block_data)
        
        # Skip if we already have this block
        if block.hash in self.pending_blocks:
            return
        
        # Verify proof of work
        if not block.verify_pow():
            print(f"[Peer {self.id}] Rejected block {block.height} with invalid proof of work")
            return
        
        # If we're missing the previous block, request it
        if block.height > 0 and block.prev_hash not in self.pending_blocks and block.prev_hash != "genesis_hash":
            self.request_block(block.height - 1, block.prev_hash, sender_id)
            # Store this block for later processing
            self.store_block(block)
            return
        
        # Store and process the block
        self.store_block(block)
        
        # Attempt chain reorganization
        self.reorganize_chain()
    
    def reorganize_chain(self):
        """Reorganize the blockchain if a longer valid chain is found"""
        # Find all possible chain tips
        tips = []
        
        # Collect all chain tips (blocks not referenced as prev_hash by any other block)
        all_hashes = set(self.pending_blocks.keys())
        all_hashes.add(self.current_hash)  # Include current chain tip
        
        prev_hashes = set()
        for block in self.pending_blocks.values():
            prev_hashes.add(block.prev_hash)
        
        tip_hashes = all_hashes - prev_hashes
        
        # For each tip, find the longest valid chain
        for tip_hash in tip_hashes:
            if tip_hash == "genesis_hash":
                continue
                
            # Start from the tip and go backwards
            chain = []
            current = tip_hash
            
            while current != "genesis_hash":
                if current not in self.pending_blocks:
                    # Chain is broken, skip this tip
                    chain = []
                    break
                
                block = self.pending_blocks[current]
                chain.append(block)
                current = block.prev_hash
            
            # Reverse to get correct order (genesis to tip)
            chain.reverse()
            
            # Validate the chain
            valid = True
            expected_height = 0
            expected_hash = "genesis_hash"
            
            for block in chain:
                if block.height != expected_height or block.prev_hash != expected_hash:
                    valid = False
                    break
                expected_height += 1
                expected_hash = block.hash
            
            if valid and chain:
                tips.append((len(chain), chain))
        
        # If we found a valid chain longer than our current one
        if tips:
            # Sort by length, descending
            tips.sort(key=lambda x: x[0], reverse=True)
            longest_length, longest_chain = tips[0]
            
            if longest_length > self.finalized_height + 1:
                # Found a longer chain, reorganize
                print(f"[Peer {self.id}] Reorganizing to a longer chain with height {longest_length - 1}")
                
                # Reset blockchain and rebuild
                self.blockchain = []
                self.finalized_height = -1
                self.current_hash = "genesis_hash"
                
                # Add each block
                for block in longest_chain:
                    self.add_to_blockchain(block)
    
    def request_block(self, height: int, block_hash: str, sender_id: int):
        """Request a missing block from a peer"""
        # Check if we've already requested this block recently
        request_key = (height, block_hash)
        current_time = time.time()
        
        if request_key in self.pending_block_requests:
            # Don't request too frequently
            last_request_time = self.pending_block_requests[request_key]
            if current_time - last_request_time < 5.0:  # 5 second cooldown
                return
        
        # Record this request
        self.pending_block_requests[request_key] = current_time
        
        # Send request to the peer we received a block from
        self.message_bus.send(
            sender_id=self.id,
            receiver_id=sender_id,
            msg_type="request_block",
            data={"height": height, "hash": block_hash}
        )
    
    def handle_block_request(self, request_data: Dict, sender_id: int):
        """Handle a request for a block from another peer"""
        height = request_data["height"]
        block_hash = request_data["hash"]
        
        # Check if we have this block
        if block_hash in self.pending_blocks:
            block = self.pending_blocks[block_hash]
            # Send the block back
            self.message_bus.send(
                sender_id=self.id,
                receiver_id=sender_id,
                msg_type="block_response",
                data=block.to_dict()
            )
    
    def handle_block_response(self, block_data: Dict):
        """Handle a response to a block request"""
        # Process the block just like a proposal
        self.receive_block_proposal(block_data, -1)  # -1 as sender means system message
    
    def receive_transaction(self, tx_data: Dict):
        """Add a transaction to the pool"""
        # Create transaction from data
        tx = Transaction.from_dict(tx_data)
        
        # Skip if we've seen this transaction before
        if tx.tx_hash in self.tx_seen:
            return
        
        # Add to seen set and pool
        self.tx_seen.add(tx.tx_hash)
        self.tx_pool.append(tx)
        
        # Forward to other peers (gossip protocol)
        self.message_bus.broadcast(
            sender_id=self.id,
            msg_type="transaction",
            data=tx.to_dict(),
            exclude_ids=[self.id]  # Exclude self to avoid loops
        )
    
    def create_transaction(self):
        """Create a random transaction"""
        receiver = random.randint(0, self.num_peers - 1)
        while receiver == self.id:
            receiver = random.randint(0, self.num_peers - 1)
        
        tx = Transaction(
            sender=self.id,
            receiver=receiver,
            amount=random.uniform(1, 100)
        )
        
        # Add to own pool and seen set
        self.tx_pool.append(tx)
        self.tx_seen.add(tx.tx_hash)
        
        # Broadcast to network
        self.message_bus.broadcast(
            sender_id=self.id,
            msg_type="transaction",
            data=tx.to_dict()
        )
        
        return tx

class PoWSimulator:
    """Manages the entire PoW simulation"""
    def __init__(self, num_peers: int, simulation_min_blocks: int):
        self.message_bus = MessageBus(num_peers)
        self.peers = []
        self.current_round = 0
        self.running = False
        self.start_time = None
        self.simulation_min_blocks = simulation_min_blocks  # Set the simulation time
        self.num_peers = num_peers  # Set the number of peers
        self.lock = threading.Lock()  # Lock for thread safety
    
    def initialize(self):
        """Set up the simulation"""
        for i in range(self.num_peers):
            peer = Peer(i, self.message_bus, self.num_peers)
            self.peers.append(peer)
            peer.start()
        
        print(f"Initialized {self.num_peers} peers.")
    
    def get_messages_for_peer(self, peer_id: int):
        """Get all messages that should be delivered to a specific peer"""
        deliverable = self.message_bus.get_deliverable_messages()
        messages_for_peer = []
        
        for msg in deliverable:
            if msg["receiver"] == peer_id:
                messages_for_peer.append(msg)
            else:
                # Put this message back with lock to avoid race conditions
                with self.message_bus.lock:
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
        
        print("Starting simulation...")
        while self.running:
            current_time = time.time()
            
            # Process messages for all peers
            for peer in self.peers:
                peer.process_messages()
            
            # Generate random transactions
            if random.random() < 0.1:  # 10% chance each loop
                peer_id = random.randint(0, self.num_peers - 1)
                tx = self.peers[peer_id].create_transaction()
            
            # Time to propose a new block?
            if current_time - last_block_time >= BLOCK_TIME:
                # Reset miner flags for new round
                for peer in self.peers:
                    peer.is_current_miner = True
                    peer.block_mined = False
                
                # New block height is the current finalized height + 1
                # Use the height from the first peer as reference
                next_height = self.peers[0].finalized_height + 1
                
                # Shared flag for miners to indicate when someone found a block
                block_mined = [False]
                
                # Create mining threads
                threads = []
                for peer in self.peers:
                    mining_thread = threading.Thread(
                        target=peer.propose_block, 
                        args=(next_height, block_mined)
                    )
                    mining_thread.start()
                    threads.append(mining_thread)
                
                # Wait for all threads to complete
                for thread in threads:
                    thread.join()
                
                # Reset block mining flags
                for peer in self.peers:
                    peer.block_mined = False
                
                last_block_time = current_time
            
            # Print status every 10 seconds
            if current_time - last_status_time >= 10:
                self.print_status()
                last_status_time = current_time
            
            # Check if the simulation should end
            min_blockchain_length = min(len(peer.blockchain) for peer in self.peers)
            if min_blockchain_length >= self.simulation_min_blocks:
                print(
                    f"\nSimulation ending: Blockchain length reached ({min_blockchain_length} blocks)"
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
        
        # Calculate agreement percentage
        agreement_count = sum(1 for h in heights if h == heights[0])
        agreement_pct = (agreement_count / len(heights)) * 100
        print(f"Peer agreement: {agreement_pct:.1f}%")
    
    def print_results(self):
        """Print simulation results"""
        print("\n===== SIMULATION RESULTS =====")
        print(f"Ran for {time.time() - self.start_time:.2f} seconds")

        lens = [len(peer.blockchain) for peer in self.peers]

        # Find the peer with the most blocks
        max_height, max_peer = max((length, i) for i, length in enumerate(lens))
        min_height, min_peer = min((length, i) for i, length in enumerate(lens))
        print(f"Maximum blockchain height: {max_height} blocks (peer {max_peer})")
        print(f"Minimum blockchain height: {min_height} blocks (peer {min_peer})")

        # Check if all peers are in sync
        if all(h == lens[0] for h in lens):
            print("All peers are in sync!")
        else:
            # Calculate percentage of peers in sync
            sync_count = {}
            for length in lens:
                if length not in sync_count:
                    sync_count[length] = 0
                sync_count[length] += 1
            
            print("Peers are at different heights:")
            for height, count in sorted(sync_count.items(), reverse=True):
                pct = (count / len(self.peers)) * 100
                print(f"  {height} blocks: {count} peers ({pct:.1f}%)")

        # Check that all peers have the same blockchain
        sample_blockchain = self.peers[max_peer].blockchain
        common_height = min(lens)
        
        # Compare only up to the common height
        common_blocks = sample_blockchain[:common_height]
        all_match = True
        
        for i, peer in enumerate(self.peers):
            peer_blocks = peer.blockchain[:common_height]
            if len(peer_blocks) < common_height:
                all_match = False
                print(f"Peer {i} has fewer blocks than expected ({len(peer_blocks)} vs {common_height})")
                continue
                
            for j, (sample_block, peer_block) in enumerate(zip(common_blocks, peer_blocks)):
                if sample_block.hash != peer_block.hash:
                    all_match = False
                    print(f"Peer {i}: Different block at height {j}")
                    print(f"  Expected: {sample_block.hash[:8]} (miner {sample_block.miner})")
                    print(f"  Found: {peer_block.hash[:8]} (miner {peer_block.miner})")
                    break
        
        if all_match:
            print(f"All peers agree on the first {common_height} blocks!")
        else:
            print(f"Peers have different views of the blockchain")

       
# Run the simulation
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a Proof of Work blockchain simulation.")
    parser.add_argument(
        "--num_peers", type=int, required=True, help="Number of peers in the simulation"
    )
    parser.add_argument(
        "--min_final_chain_length",
        type=int,
        required=True,
        help="Number of minimum blocks in final chain",
    )
    args = parser.parse_args()

    start_time = time.time()

    # Initialize the Bitcoin simulator with the specified number of peers and simulation time
    simulator = PoWSimulator(args.num_peers, args.min_final_chain_length)
    simulator.initialize()
    simulator.run()

    end_time = time.time()

    start_time_str = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(start_time)
    )
    end_time_str = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(end_time)
    )
    print(f"Simulation started at {start_time_str} and ended at {end_time_str}")