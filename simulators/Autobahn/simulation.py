import asyncio
import random
import logging
import time
import json
import argparse
import matplotlib.pyplot as plt
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Set, Tuple, Optional, Any
import uuid
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("autobahn_simulation.log"),
        logging.StreamHandler()
    ]
)

# Simulation configuration
class SimulationConfig:
    def __init__(self, 
                 num_peers=20,
                 run_time_sec=60,
                 block_time_sec=2.0,
                 view_change_timeout_sec=10.0,
                 latency_min_ms=10,
                 latency_max_ms=100,
                 packet_loss_pct=1,
                 byzantine_nodes=0,
                 partition_network=False,
                 partition_time_sec=None,
                 log_level="INFO"):
        self.num_peers = num_peers
        self.run_time_sec = run_time_sec
        self.block_time_sec = block_time_sec
        self.view_change_timeout_sec = view_change_timeout_sec
        self.latency_min_ms = latency_min_ms
        self.latency_max_ms = latency_max_ms
        self.packet_loss_pct = packet_loss_pct
        self.byzantine_nodes = byzantine_nodes
        self.partition_network = partition_network
        self.partition_time_sec = partition_time_sec or (run_time_sec // 3)
        self.log_level = log_level

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


# Autobahn consensus protocol simulation components
@dataclass
class Block:
    """Represents a block in the blockchain."""
    hash: str
    prev_hash: str
    proposer_id: str
    height: int
    data: str
    timestamp: float
    
    def to_dict(self):
        return asdict(self)


@dataclass
class Vote:
    """Represents a vote on a block."""
    block_hash: str
    voter_id: str
    vote_type: str  # "prepare" or "commit"
    signature: str
    
    def to_dict(self):
        return asdict(self)


@dataclass
class Message:
    """Network message exchanged between peers."""
    sender_id: str
    msg_type: str  # "block_proposal", "prepare_vote", "commit_vote", "sync_request", etc.
    content: Any
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    def to_dict(self):
        if hasattr(self.content, 'to_dict'):
            content = self.content.to_dict()
        elif isinstance(self.content, (str, int, float, bool, type(None))):
            content = self.content
        else:
            content = str(self.content)
            
        return {
            "sender_id": self.sender_id,
            "msg_type": self.msg_type,
            "content": content,
            "msg_id": self.msg_id
        }


class NetworkSimulator:
    """Simulates network conditions between peers."""
    
    def __init__(self, config: SimulationConfig):
        self.latency_min_ms = config.latency_min_ms
        self.latency_max_ms = config.latency_max_ms
        self.packet_loss_pct = config.packet_loss_pct
        self.disconnect_peers = set()
        self.message_queues = {}  # peer_id -> asyncio.Queue
        self.partitioned_groups = []  # List of sets of peer_ids
        self.is_partitioned = False
        self.logger = logging.getLogger("Network")
        
        # Statistics
        self.messages_sent = 0
        self.messages_delivered = 0
        self.messages_dropped = 0
        self.message_types = {}  # msg_type -> count
        
    def register_peer(self, peer_id):
        """Register a new peer with the network."""
        if peer_id not in self.message_queues:
            self.message_queues[peer_id] = asyncio.Queue()
            
    def disconnect_peer(self, peer_id):
        """Simulate peer disconnection."""
        self.disconnect_peers.add(peer_id)
        self.logger.info(f"Peer {peer_id} disconnected from network")
        
    def reconnect_peer(self, peer_id):
        """Simulate peer reconnection."""
        if peer_id in self.disconnect_peers:
            self.disconnect_peers.remove(peer_id)
            self.logger.info(f"Peer {peer_id} reconnected to network")
    
    def create_network_partition(self):
        """Create a network partition by splitting peers into two groups."""
        if self.is_partitioned:
            return
            
        all_peers = list(self.message_queues.keys())
        if len(all_peers) <= 2:
            return
            
        # Randomly split peers into two groups
        random.shuffle(all_peers)
        split_point = len(all_peers) // 2
        group1 = set(all_peers[:split_point])
        group2 = set(all_peers[split_point:])
        
        self.partitioned_groups = [group1, group2]
        self.is_partitioned = True
        self.logger.warning(f"Network partitioned into groups: {len(group1)} and {len(group2)} peers")
        
    def heal_network_partition(self):
        """Heal the network partition."""
        if not self.is_partitioned:
            return
            
        self.partitioned_groups = []
        self.is_partitioned = False
        self.logger.warning("Network partition healed")
    
    def can_communicate(self, from_peer: str, to_peer: str) -> bool:
        """Check if two peers can communicate with each other."""
        if from_peer in self.disconnect_peers or to_peer in self.disconnect_peers:
            return False
            
        if not self.is_partitioned:
            return True
            
        # Check if they're in the same partition group
        for group in self.partitioned_groups:
            if from_peer in group and to_peer in group:
                return True
                
        return False
    
    async def send_message(self, msg: Message, to_peer_id: str):
        """Send a message from one peer to another with simulated network conditions."""
        self.messages_sent += 1
        
        # Track message types
        if msg.msg_type not in self.message_types:
            self.message_types[msg.msg_type] = 0
        self.message_types[msg.msg_type] += 1
        
        # Check if sender or receiver is disconnected or partitioned
        if not self.can_communicate(msg.sender_id, to_peer_id):
            self.messages_dropped += 1
            return
            
        # Simulate packet loss
        if random.random() < self.packet_loss_pct / 100:
            self.logger.debug(f"Packet loss: {msg.msg_type} from {msg.sender_id} to {to_peer_id}")
            self.messages_dropped += 1
            return
            
        # Simulate network latency
        latency = random.uniform(self.latency_min_ms, self.latency_max_ms) / 1000
        await asyncio.sleep(latency)
        
        # Deliver message
        if to_peer_id in self.message_queues:
            await self.message_queues[to_peer_id].put(msg)
            self.messages_delivered += 1
            
    async def broadcast_message(self, msg: Message, exclude_peers=None):
        """Broadcast a message to all connected peers except those in exclude_peers."""
        exclude_peers = exclude_peers or []
        tasks = []
        
        for peer_id in self.message_queues:
            if peer_id != msg.sender_id and peer_id not in exclude_peers:
                tasks.append(self.send_message(msg, peer_id))
                
        await asyncio.gather(*tasks)
        
    async def receive_message(self, peer_id: str, timeout=None) -> Optional[Message]:
        """Receive a message for a specific peer, with optional timeout."""
        if peer_id in self.disconnect_peers:
            return None
            
        try:
            if timeout:
                return await asyncio.wait_for(self.message_queues[peer_id].get(), timeout)
            else:
                return await self.message_queues[peer_id].get()
        except asyncio.TimeoutError:
            return None
            
    def get_statistics(self):
        """Get network statistics."""
        return {
            "messages_sent": self.messages_sent,
            "messages_delivered": self.messages_delivered,
            "messages_dropped": self.messages_dropped,
            "delivery_rate": self.messages_delivered / max(1, self.messages_sent) * 100,
            "message_types": self.message_types,
        }


class AutobahnPeer:
    """Simulates a peer running the Autobahn consensus protocol."""
    
    def __init__(self, peer_id: str, network: NetworkSimulator, config: SimulationConfig, 
                 is_validator=True, is_byzantine=False):
        self.peer_id = peer_id
        self.network = network
        self.is_validator = is_validator
        self.is_byzantine = is_byzantine
        self.block_time_sec = config.block_time_sec
        self.view_change_timeout_sec = config.view_change_timeout_sec
        
        # Blockchain state
        self.blockchain = []  # List of confirmed blocks
        self.pending_blocks = {}  # hash -> Block
        self.current_height = 0
        self.current_round = 0
        
        # Consensus state
        self.current_leader = ""
        self.prepare_votes = {}  # block_hash -> set of peer_ids
        self.commit_votes = {}  # block_hash -> set of peer_ids
        self.view_change_votes = set()  # set of peer_ids
        self.last_view_change_time = time.time()
        
        # Statistics
        self.blocks_proposed = 0
        self.prepare_votes_sent = 0
        self.commit_votes_sent = 0
        self.view_change_votes_sent = 0
        self.messages_received = 0
        self.messages_processed = 0
        
        # Logger
        self.logger = logging.getLogger(f"Peer-{peer_id}")
        if config.log_level:
            self.logger.setLevel(getattr(logging, config.log_level))
        
    def is_leader(self):
        """Check if this peer is the current leader."""
        return self.current_leader == self.peer_id
        
    def calculate_next_leader(self):
        """Calculate the next leader based on round-robin selection."""
        # In a real implementation, this might use a more sophisticated algorithm
        validator_count = 20  # Assuming all peers are validators for simplicity
        return f"peer_{self.current_round % validator_count}"
        
    def create_block(self) -> Block:
        """Create a new block proposal."""
        prev_hash = "genesis" if not self.blockchain else self.blockchain[-1].hash
        # In a real implementation, this would collect transactions
        data = f"Block data from {self.peer_id} at height {self.current_height + 1}"
        block_hash = f"block_{self.current_height + 1}_{self.peer_id}_{random.randint(1000, 9999)}"
        
        block = Block(
            hash=block_hash,
            prev_hash=prev_hash,
            proposer_id=self.peer_id,
            height=self.current_height + 1,
            data=data,
            timestamp=time.time()
        )
        
        self.blocks_proposed += 1
        return block
        
    def validate_block(self, block: Block) -> bool:
        """Validate a proposed block."""
        # If we're byzantine and configured to reject blocks, return False randomly
        if self.is_byzantine and random.random() < 0.5:
            self.logger.warning(f"Byzantine behavior: Rejecting valid block {block.hash}")
            return False
            
        # In a real implementation, this would verify the block's content
        if block.height != self.current_height + 1:
            return False
            
        if len(self.blockchain) > 0 and block.prev_hash != self.blockchain[-1].hash:
            return False
            
        return True
        
    def create_vote(self, block_hash: str, vote_type: str) -> Vote:
        """Create a vote for a block."""
        # In a real implementation, this would create a cryptographic signature
        signature = f"sig_{self.peer_id}_{random.randint(1000, 9999)}"
        
        # Update statistics
        if vote_type == "prepare":
            self.prepare_votes_sent += 1
        elif vote_type == "commit":
            self.commit_votes_sent += 1
        
        return Vote(
            block_hash=block_hash,
            voter_id=self.peer_id,
            vote_type=vote_type,
            signature=signature
        )
        
    def has_quorum_prepare(self, block_hash: str) -> bool:
        """Check if a block has enough prepare votes to proceed to commit phase."""
        # Typically this would be 2/3 of validators
        quorum_threshold = 14  # 2/3 of 20 validators rounded up
        return block_hash in self.prepare_votes and len(self.prepare_votes[block_hash]) >= quorum_threshold
        
    def has_quorum_commit(self, block_hash: str) -> bool:
        """Check if a block has enough commit votes to be finalized."""
        # Typically this would be 2/3 of validators
        quorum_threshold = 14  # 2/3 of 20 validators rounded up
        return block_hash in self.commit_votes and len(self.commit_votes[block_hash]) >= quorum_threshold
        
    def add_prepare_vote(self, vote: Vote):
        """Add a prepare vote for a block."""
        if vote.block_hash not in self.prepare_votes:
            self.prepare_votes[vote.block_hash] = set()
        self.prepare_votes[vote.block_hash].add(vote.voter_id)
        
    def add_commit_vote(self, vote: Vote):
        """Add a commit vote for a block."""
        if vote.block_hash not in self.commit_votes:
            self.commit_votes[vote.block_hash] = set()
        self.commit_votes[vote.block_hash].add(vote.voter_id)
        
    def finalize_block(self, block_hash: str):
        """Finalize a block and add it to the blockchain."""
        if block_hash in self.pending_blocks and self.has_quorum_commit(block_hash):
            block = self.pending_blocks[block_hash]
            self.blockchain.append(block)
            self.current_height = block.height
            
            # Clear consensus data for this height
            self.pending_blocks = {h: b for h, b in self.pending_blocks.items() if b.height > block.height}
            self.prepare_votes = {h: v for h, v in self.prepare_votes.items() if h != block_hash}
            self.commit_votes = {h: v for h, v in self.commit_votes.items() if h != block_hash}
            
            self.logger.info(f"Finalized block at height {block.height}: {block_hash}")
            
            # Prepare for next round
            self.current_round += 1
            self.current_leader = self.calculate_next_leader()
            
    async def start_consensus(self):
        """Main consensus loop."""
        self.network.register_peer(self.peer_id)
        self.current_leader = self.calculate_next_leader()
        
        # Initialize with a genesis block if needed
        if not self.blockchain:
            genesis = Block(
                hash="genesis",
                prev_hash="",
                proposer_id="system",
                height=0,
                data="Genesis block",
                timestamp=time.time()
            )
            self.blockchain.append(genesis)
            
        self.logger.info(f"Starting consensus process, current leader: {self.current_leader}")
        
        # Start main processing tasks
        await asyncio.gather(
            self.proposal_task(),
            self.message_processing_task(),
            self.view_change_task()
        )
        
    async def proposal_task(self):
        """Task for handling block proposals as the leader."""
        while True:
            try:
                # Wait until it's our turn to be leader
                if self.is_leader() and not self.is_byzantine:
                    self.logger.info(f"I am the leader for round {self.current_round}")
                    # Create and propose a new block
                    block = self.create_block()
                    self.pending_blocks[block.hash] = block
                    
                    # Create our own prepare vote
                    vote = self.create_vote(block.hash, "prepare")
                    self.add_prepare_vote(vote)
                    
                    # Broadcast the block proposal
                    proposal_msg = Message(
                        sender_id=self.peer_id,
                        msg_type="block_proposal",
                        content=block
                    )
                    await self.network.broadcast_message(proposal_msg)
                    self.logger.info(f"Proposed block: {block.hash} at height {block.height}")
                    
                    # Wait for the next leader election
                    await asyncio.sleep(self.block_time_sec)
                elif self.is_leader() and self.is_byzantine:
                    # Byzantine behavior: don't propose a block or propose invalid blocks
                    self.logger.warning(f"Byzantine leader behavior: Not proposing a block for round {self.current_round}")
                    await asyncio.sleep(self.block_time_sec)
                else:
                    # Just check periodically if we've become the leader
                    await asyncio.sleep(0.5)
            except Exception as e:
                self.logger.error(f"Error in proposal task: {e}")
                
    async def message_processing_task(self):
        """Task for processing incoming messages."""
        while True:
            try:
                msg = await self.network.receive_message(self.peer_id)
                if not msg:
                    continue
                    
                self.messages_received += 1
                
                # Byzantine behavior: ignore messages randomly
                if self.is_byzantine and random.random() < 0.3:
                    self.logger.warning(f"Byzantine behavior: Ignoring message {msg.msg_type} from {msg.sender_id}")
                    continue
                
                if msg.msg_type == "block_proposal":
                    await self.handle_block_proposal(msg)
                elif msg.msg_type == "prepare_vote":
                    await self.handle_prepare_vote(msg)
                elif msg.msg_type == "commit_vote":
                    await self.handle_commit_vote(msg)
                elif msg.msg_type == "view_change":
                    await self.handle_view_change(msg)
                    
                self.messages_processed += 1
                    
            except Exception as e:
                self.logger.error(f"Error processing message: {e}")
                
    async def view_change_task(self):
        """Task for monitoring leader activity and initiating view changes."""
        while True:
            try:
                # If we've been waiting too long for a block, initiate view change
                time_since_last_view_change = time.time() - self.last_view_change_time
                
                if (time_since_last_view_change > self.view_change_timeout_sec and 
                    not self.is_leader() and not self.is_byzantine):
                    
                    self.logger.warning(f"No progress detected, initiating view change")
                    self.last_view_change_time = time.time()
                    
                    # Send view change vote
                    self.view_change_votes_sent += 1
                    view_change_msg = Message(
                        sender_id=self.peer_id,
                        msg_type="view_change",
                        content=self.peer_id
                    )
                    await self.network.broadcast_message(view_change_msg)
                
                await asyncio.sleep(1)
            except Exception as e:
                self.logger.error(f"Error in view change task: {e}")
                
    async def handle_block_proposal(self, msg: Message):
        """Handle an incoming block proposal."""
        block = msg.content
        self.logger.debug(f"Received block proposal from {msg.sender_id}: {block.hash}")
        
        if block.hash in self.pending_blocks:
            return  # Already seen this block
            
        if self.validate_block(block):
            # Store the pending block
            self.pending_blocks[block.hash] = block
            
            # Byzantine behavior: double vote or vote for multiple blocks
            if self.is_byzantine and random.random() < 0.5:
                self.logger.warning(f"Byzantine behavior: Voting for multiple blocks at height {block.height}")
                # Create additional fake blocks
                fake_block = Block(
                    hash=f"fake_block_{self.current_height + 1}_{self.peer_id}_{random.randint(1000, 9999)}",
                    prev_hash=block.prev_hash,
                    proposer_id=self.peer_id,
                    height=block.height,
                    data="Fake block data",
                    timestamp=time.time()
                )
                self.pending_blocks[fake_block.hash] = fake_block
                
                # Vote for both blocks
                for b in [block, fake_block]:
                    vote = self.create_vote(b.hash, "prepare")
                    self.add_prepare_vote(vote)
                    vote_msg = Message(
                        sender_id=self.peer_id,
                        msg_type="prepare_vote",
                        content=vote
                    )
                    await self.network.broadcast_message(vote_msg)
            else:
                # Normal behavior - vote for the valid block
                vote = self.create_vote(block.hash, "prepare")
                self.add_prepare_vote(vote)
                
                vote_msg = Message(
                    sender_id=self.peer_id,
                    msg_type="prepare_vote",
                    content=vote
                )
                await self.network.broadcast_message(vote_msg)
                self.logger.debug(f"Sent prepare vote for block: {block.hash}")
        else:
            self.logger.warning(f"Received invalid block from {msg.sender_id}: {block.hash}")
            
    async def handle_prepare_vote(self, msg: Message):
        """Handle an incoming prepare vote."""
        vote = msg.content
        self.logger.debug(f"Received prepare vote from {vote.voter_id} for block: {vote.block_hash}")
        
        # In a real implementation, we would verify the vote signature
        
        # Add the prepare vote
        self.add_prepare_vote(vote)
        
        # Check if we have a quorum of prepare votes
        if (self.has_quorum_prepare(vote.block_hash) and 
            vote.block_hash in self.pending_blocks and 
            not self.is_byzantine):
            # Create and broadcast commit vote
            commit_vote = self.create_vote(vote.block_hash, "commit")
            self.add_commit_vote(commit_vote)
            
            vote_msg = Message(
                sender_id=self.peer_id,
                msg_type="commit_vote",
                content=commit_vote
            )
            await self.network.broadcast_message(vote_msg)
            self.logger.debug(f"Sent commit vote for block: {vote.block_hash}")
            
    async def handle_commit_vote(self, msg: Message):
        """Handle an incoming commit vote."""
        vote = msg.content
        self.logger.debug(f"Received commit vote from {vote.voter_id} for block: {vote.block_hash}")
        
        # In a real implementation, we would verify the vote signature
        
        # Add the commit vote
        self.add_commit_vote(vote)
        
        # Check if we have a quorum of commit votes
        if self.has_quorum_commit(vote.block_hash) and not self.is_byzantine:
            self.finalize_block(vote.block_hash)
            self.last_view_change_time = time.time()  # Reset view change timer
            
    async def handle_view_change(self, msg: Message):
        """Handle view change messages (leader failures)."""
        peer_id = msg.content
        self.view_change_votes.add(peer_id)
        
        # If we have enough votes, change the leader
        quorum_threshold = 14  # 2/3 of 20 validators rounded up
        if len(self.view_change_votes) >= quorum_threshold:
            self.current_round += 1
            self.current_leader = self.calculate_next_leader()
            self.view_change_votes.clear()
            self.last_view_change_time = time.time()
            self.logger.info(f"View change: new leader is {self.current_leader}")
            
    def get_statistics(self):
        """Get peer statistics."""
        return {
            "peer_id": self.peer_id,
            "is_byzantine": self.is_byzantine,
            "chain_height": self.current_height,
            "blocks_proposed": self.blocks_proposed,
            "prepare_votes_sent": self.prepare_votes_sent,
            "commit_votes_sent": self.commit_votes_sent,
            "view_change_votes_sent": self.view_change_votes_sent,
            "messages_received": self.messages_received,
            "messages_processed": self.messages_processed,
        }


class SimulationController:
    """Controls the simulation and collects metrics."""
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.network = NetworkSimulator(config)
        self.peers = []
        self.start_time = None
        self.end_time = None
        self.logger = logging.getLogger("SimController")
        
    def create_peers(self):
        """Create the peer nodes."""
        for i in range(self.config.num_peers):
            peer_id = f"peer_{i}"
            is_byzantine = i < self.config.byzantine_nodes
            
            peer = AutobahnPeer(
                peer_id=peer_id,
                network=self.network,
                config=self.config,
                is_validator=True,  # All peers are validators in this simulation
                is_byzantine=is_byzantine
            )
            
            if is_byzantine:
                self.logger.warning(f"Peer {peer_id} is byzantine")
                
            self.peers.append(peer)
            
    async def run_partition_scenario(self):
        """Create and heal a network partition during the simulation."""
        if not self.config.partition_network:
            return
            
        # Wait for 1/3 of the simulation time
        await asyncio.sleep(self.config.partition_time_sec)
        
        # Create a network partition
        self.network.create_network_partition()
        
        # Wait for 1/3 of the simulation time
        await asyncio.sleep(self.config.partition_time_sec)
        
        # Heal the network partition
        self.network.heal_network_partition()
        
    async def run_simulation(self):
        """Run the full simulation."""
        self.start_time = time.time()
        self.logger.info(f"Starting simulation with configuration: {json.dumps(self.config.to_dict(), indent=2)}")
        
        # Create the peers
        self.create_peers()
        
        # Start all peer consensus tasks
        peer_tasks = [peer.start_consensus() for peer in self.peers]
        
        # Start network partition scenario if enabled
        partition_task = asyncio.create_task(self.run_partition_scenario())
        
        # Run the simulation for the specified time
        try:
            await asyncio.wait_for(asyncio.gather(*peer_tasks), timeout=self.config.run_time_sec)
        except asyncio.TimeoutError:
            self.logger.info("Simulation time completed")
            
        # Wait for partition task to complete
        await partition_task
        
        self.end_time = time.time()
        
        # Collect and report results
        self.collect_results()
        
    def collect_results(self):
        """Collect and report simulation results."""
        if not self.start_time or not self.end_time:
            return
            
        elapsed_time = self.end_time - self.start_time
        
        # Print simulation results
        print("\n" + "=" * 50)
        print(f"SIMULATION RESULTS (duration: {elapsed_time:.2f} seconds)")
        print("=" * 50)
        
        # Consensus results
        heights = [peer.current_height for peer in self.peers]
        
        print(f"\nCONSENSUS STATUS:")
        print(f"Min Height: {min(heights)}")
        print(f"Max Height: {max(heights)}")
        
        if all(h == heights[0] for h in heights):
            print(f"Consensus ACHIEVED! All peers at height {heights[0]}")
        else:
            print(f"Consensus FAILED! Heights vary")
            
        # Network statistics
        net_stats = self.network.get_statistics()
        print(f"\nNETWORK STATISTICS:")
        print(f"Messages Sent: {net_stats['messages_sent']}")
        print(f"Messages Delivered: {net_stats['messages_delivered']}")
        print(f"Messages Dropped: {net_stats['messages_dropped']}")
        print(f"Delivery Rate: {net_stats['delivery_rate']:.2f}%")
        
        print("\nMessage Types:")
        for msg_type, count in net_stats['message_types'].items():
            print(f"  {msg_type}: {count}")
            
        # Peer statistics
        print(f"\nPEER STATISTICS:")
        for peer in self.peers:
            stats = peer.get_statistics()
            byz_flag = "[BYZANTINE]" if stats["is_byzantine"] else ""
            print(f"Peer {stats['peer_id']} {byz_flag}:")
            print(f"  Chain Height: {stats['chain_height']}")
            print(f"  Blocks Proposed: {stats['blocks_proposed']}")
            print(f"  Prepare Votes: {stats['prepare_votes_sent']}")
            print(f"  Commit Votes: {stats['commit_votes_sent']}")
            print(f"  View Change Votes: {stats['view_change_votes_sent']}")
            print(f"  Messages Received/Processed: {stats['messages_received']}/{stats['messages_processed']}")
            
        # Generate visualization
        self.generate_visualization()
        
    def generate_visualization(self):
        """Generate visualizations of the simulation results."""
        try:
            # Create figures directory if it doesn't exist
            if not os.path.exists("figures"):
                os.makedirs("figures")
                
            # Plot block heights
            fig, ax = plt.subplots(figsize=(10, 6))
            peer_ids = [peer.peer_id for peer in self.peers]
            heights = [peer.current_height for peer in self.peers]
            colors = ['red' if peer.is_byzantine else 'blue' for peer in self.peers]
            
            ax.bar(peer_ids, heights, color=colors)
            ax.set_ylabel("Block Height")
            ax.set_xlabel("Peer ID")
            ax.set_title("Final Block Heights by Peer")
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig("figures/block_heights.png")
            
            # Plot message statistics
            fig, ax = plt.subplots(figsize=(10, 6))
            net_stats = self.network.get_statistics()
            msg_types = list(net_stats['message_types'].keys())
            msg_counts = list(net_stats['message_types'].values())
            
            ax.bar(msg_types, msg_counts)
            ax.set_ylabel("Count")
            ax.set_xlabel("Message Type")
            ax.set_title("Message Counts by Type")
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig("figures/message_stats.png")
            
            self.logger.info("Generated visualization figures in the 'figures' directory")
        except Exception as e:
            self.logger.error(f"Error generating visualization: {e}")


async def run_simulation_with_config(config: SimulationConfig):
    """Run a simulation with the specified configuration."""
    controller = SimulationController(config)
    await controller.run_simulation()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Autobahn Consensus Protocol Simulator")
    
    parser.add_argument("--peers", type=int, default=20, help="Number of peers")
    parser.add_argument("--time", type=int, default=60, help="Simulation time in seconds")
    parser.add_argument("--block-time", type=float, default=2.0, help="Block time in seconds")
    parser.add_argument("--view-change-timeout", type=float, default=10.0, help="View change timeout in seconds")
    parser.add_argument("--latency-min", type=int, default=10, help="Minimum network latency in ms")
    parser.add_argument("--latency-max", type=int, default=100, help="Maximum network latency in ms")
    parser.add_argument("--packet-loss", type=float, default=1.0, help="Packet loss percentage")
    parser.add_argument("--byzantine", type=int, default=0, help="Number of byzantine nodes")
    parser.add_argument("--partition", action="store_true", help="Enable network partition scenario")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO", help="Logging level")
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    config = SimulationConfig(
        num_peers=args.peers,
        run_time_sec=args.time,
        block_time_sec=args.block_time,
        view_change_timeout_sec=args.view_change_timeout,
        latency_min_ms=args.latency_min,
        latency_max_ms=args.latency_max,
        packet_loss_pct=args.packet_loss,
        byzantine_nodes=args.byzantine,
        partition_network=args.partition,
        log_level=args.log_level
    )
    
    asyncio.run(run_simulation_with_config(config))


if __name__ == "__main__":
    main()