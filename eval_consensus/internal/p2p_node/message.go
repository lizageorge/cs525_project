package p2p_node

// TODO rename this outer dir to p2p-node and delete the inner dir
import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"time"

	"eval_consensus/internal/common"

	"github.com/libp2p/go-libp2p/core/peer"
	"github.com/libp2p/go-libp2p/core/protocol"
)

// Message types and related functions
type Message struct {
	Type     string      `json:"type"`
	FromID   string      `json:"fromID"`
	FromName string      `json:"fromName"`
	Payload  interface{} `json:"payload"`
}

// forwardGossipMessage forwards a gossip message to B random peers
func (n *Node) forwardGossipMessage(msg Message, excludePeerID string) {
	// Get a list of peers to potentially forward to (excluding the sender)
	n.PeersLock.RLock()
	eligiblePeers := make([]PeerInfo, 0, len(n.Peers))
	for id, peer := range n.Peers {
		if id != excludePeerID {
			eligiblePeers = append(eligiblePeers, peer)
		}
	}
	n.PeersLock.RUnlock()

	// If we don't have enough peers, just forward to all
	if len(eligiblePeers) <= GOSSIP_B {
		for _, peer := range eligiblePeers {
			if err := n.SendMessage(peer, msg); err != nil {
				log.Printf("❌ Failed to forward gossip to %s: %s", peer.PeerName, err)
			}
		}
		return
	}

	// Randomly select B peers and forward msg to them
	selectedIndices := make(map[int]bool)
	for len(selectedIndices) < GOSSIP_B {
		idx := rand.Intn(len(eligiblePeers))
		selectedIndices[idx] = true
	}

	for idx := range selectedIndices {
		peer := eligiblePeers[idx]
		if err := n.SendMessage(peer, msg); err != nil {
			log.Printf("❌ Failed to forward gossip to %s: %s", peer.PeerName, err)
		}
	}
}

// SendMessage sends a message to a specific peer
func (n *Node) SendMessage(targetPeer PeerInfo, msg Message) error {
	// Parse peer ID
	pid, err := peer.Decode(targetPeer.PeerAddr.ID.String())
	if err != nil {
		return fmt.Errorf("invalid peer ID: %w", err)
	}

	// Create stream
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	stream, err := n.Host.NewStream(ctx, pid, protocol.ID(ProtocolID))
	if err != nil {
		return fmt.Errorf("failed to create stream: %w", err)
	}
	defer stream.Close()

	// Send message
	msgBytes, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal message: %w", err)
	}

	_, err = stream.Write(msgBytes)
	if err != nil {
		return fmt.Errorf("failed to write message: %w", err)
	}

	if msg.Type != "heartbeat" && msg.Type != "hello_ack" {
		log.Printf("📤 Sent message of type '%s' to %s", msg.Type, targetPeer.PeerName)
	}
	return nil
}

// InitiateGossip starts a new gossip message from this node
func (n *Node) InitiateGossip(msgID string, text string) {
	payload := common.GossipPayload{
		ID:     msgID,
		Text:   text,
		Time:   time.Now().Format(time.RFC3339),
		Origin: n.NodeName,
	}

	msg := Message{
		Type:     "gossip",
		FromID:   n.NodeID,
		FromName: n.NodeName,
		Payload:  payload,
	}

	go n.forwardGossipMessage(msg, n.NodeID)

	log.Printf("💬 GOSSIP initiated: %s", text)
}
