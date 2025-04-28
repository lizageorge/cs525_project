package p2p_node

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/libp2p/go-libp2p/core/peer"
	"github.com/multiformats/go-multiaddr"
)

type PeerInfo struct {
	PeerAddr peer.AddrInfo
	PeerName string
}

// Connect establishes connection to a peer
func (n *Node) Connect(addr string, name string) error {
	maddr, err := multiaddr.NewMultiaddr(addr)
	if err != nil {
		return fmt.Errorf("invalid address: %w", err)
	}

	// Extract peer info
	info, err := peer.AddrInfoFromP2pAddr(maddr)
	if err != nil {
		return fmt.Errorf("invalid peer info: %w", err)
	}

	// Connect to peer
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := n.Host.Connect(ctx, *info); err != nil {
		return fmt.Errorf("connection failed: %w", err)
	}

	// Add to peers list
	newPeer := n.AddPeer(info.ID, name)

	// Send hello message
	n.SendMessage(newPeer, Message{
		Type:     "hello",
		FromName: n.NodeName,
		FromID:   n.NodeID,
		Payload: map[string]interface{}{
			"time": time.Now().Format(time.RFC3339),
		},
	})

	log.Printf("🔗 Connected to peer: %s", name)
	return nil
}

// AddPeer adds a peer to the node's peer list
func (n *Node) AddPeer(peerID peer.ID, peerName string) PeerInfo {
	n.PeersLock.Lock()
	defer n.PeersLock.Unlock()

	peerIDStr := peerID.String()

	// Check if already in the list
	if _, exists := n.Peers[peerIDStr]; exists {
		return n.Peers[peerIDStr]
	}

	// Add to peers list
	peerAddr := peer.AddrInfo{
		ID:    peerID,
		Addrs: n.Host.Peerstore().Addrs(peerID),
	}
	newPeer := PeerInfo{
		PeerAddr: peerAddr,
		PeerName: peerName,
	}
	n.Peers[peerIDStr] = newPeer
	log.Printf("➕ Added peer to list: %s", peerName)

	return newPeer
}

// ListPeers prints out all connected peers
func (n *Node) ListPeers() {
	n.PeersLock.RLock()
	defer n.PeersLock.RUnlock()

	log.Printf("👥 Connected peers (%d):", len(n.Peers))
	for _, peer := range n.Peers {
		log.Printf("  - %s", peer.PeerName)
	}
}

// Broadcast sends a message to all connected peers
func (n *Node) Broadcast(msg Message) {
	n.PeersLock.RLock()
	peersCopy := make(map[string]PeerInfo)
	for id, peer := range n.Peers {
		peersCopy[id] = peer
	}
	n.PeersLock.RUnlock()

	log.Printf("📣 Broadcasting message of type '%s' to %d peers", msg.Type, len(peersCopy))

	for _, peer := range peersCopy {
		if err := n.SendMessage(peer, msg); err != nil {
			log.Printf("❌ Failed to send to peer %s: %s", peer.PeerName, err)
		}
	}
}
