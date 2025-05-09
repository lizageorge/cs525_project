import time
import random
import hashlib
import json
from typing import List, Dict, Set, Any
import threading
from collections import deque
import argparse

from codecarbon import OfflineEmissionsTracker



# Configuration
ROUND_TIME = 5  # seconds between rounds (as suggested in Section 6.3)
MIN_TRANSACTIONS_PER_BLOCK = 1
MAX_TRANSACTIONS_PER_BLOCK = 50
DEBUG = False  # Enable detailed logging


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


class Proof:
    """Simulates the TEE proof of luck"""
    def __init__(self, nonce: str, luck_value: float):
        self.nonce = nonce
        self.luck_value = luck_value  # Random l ∈ [0,1)


class Block:
    def __init__(
        self,
        height: int,
        parent: str,
        miner: int,
        timestamp: float,
        transactions: List[Transaction] = None,
        proof: Proof = None,
    ):
        self.height = height
        self.parent = parent
        self.miner = miner
        self.timestamp = timestamp
        self.transactions = transactions if transactions is not None else []
        self.proof = proof
        self.hash = None

    def __eq__(self, other):
        if not isinstance(other, Block):
            return False
        return (
            self.height == other.height
            and self.parent == other.parent
            and self.miner == other.miner
            and self.timestamp == other.timestamp
            and self.hash == other.hash
        )

    def __str__(self) -> str:
        luck_value = f" luck={self.proof.luck_value:.4f}" if self.proof else ""
        return f"Block #{self.height} by Node {self.miner}{luck_value} with {len(self.transactions)} txs ({self.hash[:8] if self.hash else 'pending'})"

    def add_transaction(self, tx: Transaction) -> None:
        self.transactions.append(tx)

    def finalize(self) -> None:
        # Calculate the block hash 
        block_data = {
            "height": self.height,
            "parent": self.parent,
            "miner": self.miner,
            "timestamp": self.timestamp,
            "transactions": [tx.tx_hash for tx in self.transactions],
            "luck_value": self.proof.luck_value if self.proof else 0,
        }
        block_string = json.dumps(block_data, sort_keys=True)
        self.hash = hashlib.sha256(block_string.encode()).hexdigest()


class TEE:
    """Simulates a Trusted Execution Environment"""
    
    @staticmethod
    def GetTrustedTime():
        """Simulate a trusted time source"""
        return time.time()
    
    @staticmethod
    def GenerateRandom():
        """Generate a random number in [0,1). In a real TEE, this would be a secure random number"""
        return random.random()
    
    @staticmethod
    def GenerateProof(header):
        """Generate proof of luck"""
        nonce = hashlib.sha256(json.dumps(header, sort_keys=True).encode()).hexdigest()
        luck_value = TEE.GenerateRandom()
        return Proof(nonce, luck_value)
    
    @staticmethod
    def ValidAttestation(proof):
        """Verify proof is valid (always true in simulation)"""
        return True
    
    @staticmethod
    def ProofData(proof):
        """Get data from proof"""
        return proof


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


class Node:
    """Represents a single node in the Proof of Luck network"""

    def __init__(self, node_id: int, message_bus: MessageBus):
        self.id = node_id
        self.message_bus = message_bus

        # Blockchain state
        self.blockchain: List[Block] = []
        self.current_chain_luck = 0  # Total luck of the chain
        self.current_hash = "genesis_hash"
        self.current_height = 0

        # Transaction pool
        self.tx_pool: List[Transaction] = []

        # TEE round state
        self.round_block = None  # The latest block when PoLRound was last called
        self.round_time = None   # The time when PoLRound was last called
        
        # Callbacks for round timing
        self.callback_timer = None

    def start(self):
        """Initialize the node and start the first round"""
        # Start the first round
        self.new_round()

    def new_round(self):
        """Start a new mining round"""
        # Record the latest block for this round
        self.round_block = self.blockchain[-1] if self.blockchain else None
        # Record the current time from the TEE
        self.round_time = TEE.GetTrustedTime()
        
        # Schedule the mining to happen after ROUND_TIME
        if self.callback_timer:
            self.callback_timer.cancel()
        self.callback_timer = threading.Timer(ROUND_TIME, self.mine_block)
        self.callback_timer.daemon = True
        self.callback_timer.start()

        if DEBUG:
            print(f"[Node {self.id}] Started new round at time {self.round_time}")

    def mine_block(self):
        """Create a new block with Proof of Luck"""
        # Algorithm 4: PoLMine implementation
        
        # Create the new block header
        previous_block = self.blockchain[-1] if self.blockchain else None
        parent_hash = self.current_hash
        
        # Validating the required time for a round has passed (Line 10-12 in Algorithm 4)
        now = TEE.GetTrustedTime()
        if now < self.round_time + ROUND_TIME:
            if DEBUG:
                print(f"[Node {self.id}] Mining too early, waiting...")
            # Reschedule for the correct time
            delay = (self.round_time + ROUND_TIME) - now
            self.callback_timer = threading.Timer(delay, self.mine_block)
            self.callback_timer.daemon = True
            self.callback_timer.start()
            return
        
        # Add transactions from the pool
        num_tx = min(
            len(self.tx_pool),
            random.randint(MIN_TRANSACTIONS_PER_BLOCK, MAX_TRANSACTIONS_PER_BLOCK),
        )
        transactions = []
        for _ in range(num_tx):
            if self.tx_pool:
                tx = self.tx_pool.pop(0)
                transactions.append(tx)
                
        # Create block header for the new block (lines 8-9 in Algorithm 4)
        header = {
            "parent": parent_hash,
            "transactions": [tx.tx_hash for tx in transactions],
            "miner": self.id,
            "timestamp": now,
            "height": self.current_height + 1
        }
        
        # Generate proof of luck for this block (lines 15-20 in Algorithm 4)
        proof = TEE.GenerateProof(header)
        
        # Create the new block with the proof
        new_block = Block(
            height=self.current_height + 1,
            parent=parent_hash,
            miner=self.id,
            timestamp=now,
            transactions=transactions,
            proof=proof
        )
        
        # Reset round block and time as specified in lines 13-14
        self.round_block = None
        self.round_time = None
        
        # Calculate the delay based on luck value (the f(l) function in line 16)
        # Higher luck (closer to 1) gets shorter delay
        delay = (1 - proof.luck_value) * 2  # Scale delay to 0-2 seconds
        
        # Schedule sending of the block after the delay
        sending_timer = threading.Timer(delay, self.broadcast_block, args=[new_block])
        sending_timer.daemon = True
        sending_timer.start()
        
        if DEBUG:
            print(f"[Node {self.id}] Mined block with luck {proof.luck_value}, broadcasting in {delay:.2f}s")
            
        # Start new round for the next block
        self.new_round()

    def broadcast_block(self, block):
        """Broadcast the mined block to the network"""
        # First check if we've already seen a luckier block during our delay
        # If so, discard our block
        if self.blockchain and self.blockchain[-1].height >= block.height:
            if DEBUG:
                print(f"[Node {self.id}] Discarding block - already have one at this height")
            return
            
        # Finalize the block to calculate its hash
        block.finalize()
        
        # Broadcast to network
        self.message_bus.broadcast(sender_id=self.id, msg_type="block", data=block)
        
        # Process the block ourselves as well
        self.receive_block(block, self.id)

    def receive_block(self, block: Block, sender_id: int):
        """Process a block received from the network"""
        # Algorithm 6 & 7: Validate and process block based on luck
        
        # Perform validation (Algorithm 7)
        if not self.validate_block(block):
            if DEBUG:
                print(f"[Node {self.id}] Rejected invalid block from {sender_id}")
            return
            
        # Check if this block's parent matches our current chain
        if block.parent != self.current_hash:
            if DEBUG:
                print(f"[Node {self.id}] Received block with different parent: {block.parent} vs {self.current_hash}")
            # We have different chains, need to decide which to keep
            # In a real system, we'd request the full chain
            # For this simulation, we'll just ignore forks for simplicity
            return
            
        # Add the block to our blockchain
        self.blockchain.append(block)
        self.current_height = block.height
        self.current_hash = block.hash
        
        # Update the total luck of the chain (Algorithm 6)
        self.current_chain_luck += block.proof.luck_value
        
        if DEBUG:
            print(f"[Node {self.id}] Added block {block}")

    def validate_block(self, block: Block) -> bool:
        """Validate a block (Algorithm 7)"""
        # Check if the block has a valid proof
        if not block.proof or not TEE.ValidAttestation(block.proof):
            return False
            
        # In a real system, we would verify:
        # 1. The nonce matches the hash of the header
        # 2. The transactions are valid
        # 3. The block is properly formed
        
        # For this simulation, we'll assume blocks are valid
        return True

    def process_messages(self):
        """Process any messages delivered to this node"""
        messages = simulator.get_messages_for_node(self.id)

        for msg in messages:
            try:
                if msg["type"] == "block":
                    self.receive_block(msg["data"], msg["sender"])
                elif msg["type"] == "transaction":
                    self.receive_transaction(msg["data"])
            except Exception as e:
                print(
                    f"Error processing message {msg['type']} from {msg['sender']}: {e}"
                )

    def receive_transaction(self, tx: Transaction):
        """Add a transaction to the pool"""
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


class PoLSimulator:
    """Manages the entire Proof of Luck simulation"""
    
    def __init__(self, num_peers: int, min_final_chain_length: int):
        self.message_bus = MessageBus(num_peers=num_peers)
        self.nodes = []
        self.running = False
        self.start_time = None
        self.num_peers = num_peers
        self.min_final_chain_length = min_final_chain_length

    def initialize(self):
        """Set up the simulation"""
        # Create nodes
        for i in range(self.num_peers):
            node = Node(i, self.message_bus)
            self.nodes.append(node)

        print(f"Initialized {self.num_peers} nodes")
        
        # Create genesis block
        genesis_block = Block(
            height=0,
            parent="genesis",
            miner=-1,  # System
            timestamp=time.time(),
            transactions=[],
            proof=Proof("genesis", 0)  # Genesis block has 0 luck
        )
        genesis_block.finalize()
        
        # Add genesis block to all nodes
        for node in self.nodes:
            node.blockchain.append(genesis_block)
            node.current_hash = genesis_block.hash
            node.current_height = 0
            node.start()  # Start the node's mining process

    def get_messages_for_node(self, node_id: int):
        """Get all messages that should be delivered to a specific node"""
        deliverable = self.message_bus.get_deliverable_messages()
        messages_for_node = []
        remaining_messages = []

        for msg in deliverable:
            if msg["receiver"] == node_id:
                messages_for_node.append(msg)
            else:
                remaining_messages.append(msg)

        # Re-add the undelivered messages back to the message bus
        for msg in remaining_messages:
            self.message_bus.messages.append(msg)

        return messages_for_node

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
        last_status_time = time.time()

        while self.running:
            # Process messages for all nodes
            for node in self.nodes:
                node.process_messages()

            # Generate random transactions
            if random.random() < 0.1:  # 10% chance each loop
                node_id = random.randint(0, self.num_peers - 1)
                tx = self.nodes[node_id].create_transaction(self.num_peers)
                if DEBUG:
                    print(f"[Node {node_id}] Created {tx}")

            # Print status every 10 seconds
            current_time = time.time()
            if current_time - last_status_time >= 10:
                self.print_status()
                last_status_time = current_time

            # Check if the simulation should end
            min_blockchain_length = min(len(node.blockchain) for node in self.nodes)
            if min_blockchain_length >= self.min_final_chain_length:
                print(
                    f"\nSimulation ending: Minimum blockchain length reached ({min_blockchain_length} blocks)"
                )
                self.final_synchronization()
                break

            # Small sleep to prevent CPU hogging
            time.sleep(0.01)

    def final_synchronization(self):
        """
        Perform a final synchronization to ensure all nodes have consistent blockchains.
        This simulates allowing all network messages to be fully processed.
        """
        if DEBUG:
            print("\nPerforming final blockchain synchronization...")

        sync_time_start = time.time()
        
        # Continue processing messages until there are no more deliverable messages
        synchronization_rounds = 0
        max_rounds = 100  # Safety limit to prevent infinite loops
        
        while synchronization_rounds < max_rounds:
            deliverable_count = 0
            
            # Process all pending messages for all nodes
            for node in self.nodes:
                messages = self.get_messages_for_node(node.id)
                deliverable_count += len(messages)
                
                for msg in messages:
                    try:
                        if msg["type"] == "block":
                            node.receive_block(msg["data"], msg["sender"])
                        elif msg["type"] == "transaction":
                            node.receive_transaction(msg["data"])
                    except Exception as e:
                        print(f"Error during synchronization: {e}")
            
            synchronization_rounds += 1
            
            # If no more messages were delivered, we're done
            if deliverable_count == 0:
                break
                
            # Small sleep to allow for any additional message processing
            time.sleep(0.05)
        
        if DEBUG:
            print(f"Synchronization completed in {synchronization_rounds} rounds")
        
        # Find the chain with the highest luck
        best_chain = None
        best_luck = -1
        
        for node in self.nodes:
            if node.current_chain_luck > best_luck:
                best_luck = node.current_chain_luck
                best_chain = node.blockchain
        
        # Ensure all nodes have the best chain
        for node in self.nodes:
            if node.current_chain_luck < best_luck:
                if DEBUG:
                    print(f"Updating Node {node.id} to the best chain (luck: {best_luck:.4f})")
                node.blockchain = best_chain.copy()
                node.current_hash = best_chain[-1].hash
                node.current_height = best_chain[-1].height
                node.current_chain_luck = best_luck
        
        print(f"Final synchronization took {time.time() - sync_time_start:.2f} seconds")

    def print_status(self):
        """Print current simulation status"""
        heights = [node.current_height for node in self.nodes]
        chain_luck = [node.current_chain_luck for node in self.nodes]

        print(f"\nStatus at {time.time() - self.start_time:.1f}s:")
        print(f"Heights: min={min(heights)}, max={max(heights)}")
        print(f"Chain luck values: min={min(chain_luck):.4f}, max={max(chain_luck):.4f}, avg={sum(chain_luck)/len(chain_luck):.4f}")

        # Show round status for a random node
        sample_node = random.choice(self.nodes)
        round_status = "in progress" if sample_node.round_time is not None else "waiting"
        print(f"Node {sample_node.id} round status: {round_status}")

    def print_results(self):
        # TODO why you saying "Node -1"
        """Print simulation results"""
        print("\n===== SIMULATION RESULTS =====")
        print(f"Ran for {time.time() - self.start_time:.2f} seconds")

        lens = [len(node.blockchain) for node in self.nodes]
        luck_values = [node.current_chain_luck for node in self.nodes]

        # Find the node with the most blocks and highest luck
        max_height, max_node = max((length, i) for i, length in enumerate(lens))
        min_height, min_node = min((length, i) for i, length in enumerate(lens))
        max_luck, max_luck_node = max((luck, i) for i, luck in enumerate(luck_values))
        
        print(f"Maximum blockchain height: {max_height} for node {max_node}")
        print(f"Minimum blockchain height: {min_height} for node {min_node}")
        print(f"Maximum chain luck: {max_luck:.4f} for node {max_luck_node}")

        # Check if all nodes are in sync
        if all(h == lens[0] for h in lens):
            print("All peers are in sync!")
        else:
            print("Nodes are out of sync:")
            for i, node in enumerate(self.nodes):
                print(f"Node {i}: length {len(node.blockchain)}, luck {node.current_chain_luck:.4f}")

        # Check that all nodes have the same blockchain
        sample_blockchain = self.nodes[max_node].blockchain
        all_match = True
        for i, node in enumerate(self.nodes):
            # Compare up to the shorter length
            min_len = min(len(node.blockchain), len(sample_blockchain))
            if node.blockchain[:min_len] != sample_blockchain[:min_len]:
                all_match = False
                print(f"Node {i} does not match the sample blockchain!")
                break
        
        if all_match:
            print(f"All blockchains match till minimum heights!")
        else:
            # Show detailed blockchain comparison if they don't match
            print(f"Blockchains do not match till minimum heights!")
            for i, node in enumerate(self.nodes):
                print(f"Node {i}: {len(node.blockchain)} blocks, luck {node.current_chain_luck:.4f}")
                for block in node.blockchain[:5]:  # Just show first 5 blocks
                    print(f"  {block}")
                if len(node.blockchain) > 5:
                    print(f"  ... and {len(node.blockchain)-5} more blocks")

        # Show block distribution (who created the blocks)
        if self.nodes[0].blockchain:
            miner_counts = {}
            for node in self.nodes:
                for block in node.blockchain[1:]:  # Skip genesis
                    miner_counts[block.miner] = (
                        miner_counts.get(block.miner, 0) + 1
                    )

            print("\nBlock miner distribution:")
            for miner_id, count in sorted(
                miner_counts.items(), key=lambda x: x[1], reverse=True
            ):
                blocks_percent = (count / (len(self.nodes[0].blockchain)-1)) * 100 if len(self.nodes[0].blockchain) > 1 else 0
                expected_percent = (1 / self.num_peers) * 100
                print(
                    f"Node {miner_id}: {count} blocks ({blocks_percent:.1f}%) - Expected: {expected_percent:.1f}%"
                )


# Run the simulation
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a Proof of Luck blockchain simulation.")
    parser.add_argument(
        "--num_peers", type=int, required=True, help="Number of nodes in the simulation"
    )
    parser.add_argument(
        "--min_final_chain_length",
        type=int,
        required=True,
        help="Minimum blockchain length to finalize the simulation",
    )
    args = parser.parse_args()



    tracker = OfflineEmissionsTracker(country_iso_code="USA", measure_power_secs=5, log_level="error")
    tracker.start()

    start_time = time.time()

    simulator = PoLSimulator(args.num_peers, args.min_final_chain_length)
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
    tracker.stop()