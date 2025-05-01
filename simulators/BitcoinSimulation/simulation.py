import time
import random
import hashlib
import json
from typing import List, Dict, Set, Any
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
        block_data = {
            "height": self.height,
            "prev_hash": self.prev_hash,
            "miner": self.miner,
            "timestamp": self.timestamp,
            "transactions": [tx.tx_hash for tx in self.transactions],
            "nonce": self.nonce
        }
        block_string = json.dumps(block_data, sort_keys=True)
        self.hash = hashlib.sha256(block_string.encode()).hexdigest()
    
    def mine(self):
        """Mine the block by finding a valid hash"""
        while True:
            self.hash = self.calculate_hash()
            if self.hash.startswith('0' * DIFFICULTY):
                break
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

class MessageBus:
    """Simulates network communication between peers"""
    def __init__(self, num_peers:int, latency_range=(0.05, 0.2)):
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
        self.pending_blocks: Dict[str, Block] = {}  # block_identifier -> Block
        self.finalized_height = -1  # Genesis block is at height -1 (not explicitly stored)
        self.current_hash = "genesis_hash"
        
        # Transaction pool
        self.tx_pool: List[Transaction] = []
        
        # Mining state
        self.block_mined = False  # Flag to indicate if this peer has mined the block
        self.lock = threading.Lock()  # Lock for thread safety
        
        # Miner state
        self.is_current_miner = False
    
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
    
    def propose_block(self, height: int, block_mined: bool):
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
        """Mine the block by finding a valid hash"""
        while not self.block_mined and not block_mined[0]:
            block.hash = block.calculate_hash()
            if block.hash.startswith('0' * DIFFICULTY):
                if not block_mined[0]:  # Check again to avoid race condition
                    self.block_mined = True
                    block_mined[0] = True  # Set that a peer has mined
                    print(f"[Peer {self.id}] Mined block {block.height} with hash {block.hash}")
                    # Broadcast the mined block
                    self.message_bus.broadcast(
                        sender_id=self.id,
                        msg_type="propose_block",
                        data={
                            "height": block.height,
                            "prev_hash": block.prev_hash,
                            "miner": self.id,
                            "timestamp": block.timestamp,
                            "transactions": [tx.tx_hash for tx in block.transactions],
                            "nonce": block.nonce,
                            "hash": block.hash
                        }
                    )
                else:
                    print("someone else got it")
                break
            block.nonce += 1

    def receive_block_proposal(self, block_data: Dict, sender_id: int):
        """Process a block proposal received from another peer"""
        # Extract block information
        height = block_data["height"]
        prev_hash = block_data["prev_hash"]
        miner = block_data["miner"]
        timestamp = block_data["timestamp"]
        block_hash = block_data["hash"]
        
        # Extract transactions from the block data
        transactions = block_data["transactions"]

        # Check if the block height is valid
        if height <= self.finalized_height:
            # print(f"[Peer {self.id}] Rejected block {height} (already have a longer chain)")
            return

        # Verify the previous hash
        if prev_hash != self.current_hash:
            # print(f"[Peer {self.id}] Rejected block {height} with prev_hash {prev_hash} (expected {self.current_hash})")
            return

        # Create a block from the received data
        block = Block(height, prev_hash, miner, timestamp)
        block.hash = block_hash
        block.transactions = transactions  # Add the transactions to the block

        # Store the block temporarily
        self.pending_blocks[height] = block

        # Check if we can finalize the block
        if height == self.finalized_height + 1:
            self.finalize_block(block)
        else:
            print(f"[Peer {self.id}] Received block {height} but cannot finalize yet.")

        # After storing the block temporarily, check for reorganizing the chain
        self.reorganize_chain()

    def finalize_block(self, block: Block):
        """Finalize a block and add it to the blockchain"""
        if block.height != self.finalized_height + 1:
            return
        
        # Update blockchain state
        self.blockchain.append(block)
        self.finalized_height = block.height
        self.current_hash = block.hash
        
        # print(f"[Peer {self.id}] Finalized block {block.height} with hash {block.hash}")
        
        # Broadcast the finalized block to all peers
        self.message_bus.broadcast(
            sender_id=self.id,
            msg_type="propose_block",
            data={
                "height": block.height,
                "prev_hash": block.prev_hash,
                "miner": self.id,
                "timestamp": block.timestamp,
                "transactions":  block.transactions,
                "nonce": block.nonce,
                "hash": block.hash
            }
        )

    def receive_transaction(self, tx: Transaction):
        """Add a transaction to the pool"""
        if not any(existing_tx.tx_hash == tx.tx_hash for existing_tx in self.tx_pool):
            self.tx_pool.append(tx)
    
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
        
        # Add to own pool
        self.tx_pool.append(tx)
        
        # Broadcast to network
        self.message_bus.broadcast(
            sender_id=self.id,
            msg_type="transaction",
            data=tx
        )
        
        return tx

    def reorganize_chain(self):
        """Reorganize the blockchain if a longer chain is found"""
        longest_chain = []
        for height in sorted(self.pending_blocks.keys()):
            block = self.pending_blocks[height]
            if not longest_chain or block.prev_hash == longest_chain[-1].hash:
                longest_chain.append(block)
        
        # If the longest chain is longer than the current blockchain, adopt it
        if len(longest_chain) > len(self.blockchain):
            self.blockchain = longest_chain
            self.finalized_height = longest_chain[-1].height
            self.current_hash = longest_chain[-1].hash
            print(f"[Peer {self.id}] Reorganized to a longer chain with height {self.finalized_height}")

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
        self.block_mined = False  # Shared variable to indicate if a block has been mined
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
        print("Start time:")
        while self.running:
            current_time = time.time()
            
            # Process messages for all peers
            for peer in self.peers:
                peer.process_messages()
            
            # Generate random transactions
            if random.random() < 0.1:  # 10% chance each loop
                peer_id = random.randint(0, self.num_peers - 1)
                tx = self.peers[peer_id].create_transaction()
                # if DEBUG:
                #     print(f"[Peer {peer_id}] Created {tx}")
            
            # Time to propose a new block?
            if current_time - last_block_time >= BLOCK_TIME:
                # Allow all peers to mine
                for peer in self.peers:
                    peer.is_current_miner = True  # Set all peers as potential miners
                
                # New block height is the current finalized height + 1
                next_height = self.peers[0].finalized_height + 1
                
                block_mined = [False]
                # Tell all peers to propose a block
                
                threads = []
                for peer in self.peers:
                    mining_thread = threading.Thread(target=peer.propose_block, args=(next_height, block_mined))
                    mining_thread.start()
                    threads.append(mining_thread)

                    # Wait for all threads to complete
                for thread in threads:
                    thread.join()
                
                for peer in self.peers:
                    peer.block_mined = False

                last_block_time = current_time
            
            # Print status every 10 seconds
            if current_time - last_status_time >= 10:
                self.print_status()
                last_status_time = current_time

             # Check if the simulation should end
            max_blockchain_length = max(len(peer.blockchain) for peer in self.peers)
            if max_blockchain_length >= self.simulation_min_blocks:
                print(
                    f"\nSimulation ending: Blockchain length reached ({max_blockchain_length} blocks)"
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
                # for block in peer.blockchain:
                #     print(f"  {block}")

       
# Run the simulation
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a Bitcoin blockchain simulation.")
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

    start_time = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(start_time)
    )
    end_time = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(end_time)
    )
    print(f"Simulation started at {start_time} and ended at {end_time}")