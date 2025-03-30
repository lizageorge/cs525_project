package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/libp2p/go-libp2p"
	"github.com/libp2p/go-libp2p/core/host"
	"github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/peer"
	"github.com/libp2p/go-libp2p/core/protocol"
	"github.com/multiformats/go-multiaddr"
)

// Constants
const ProtocolID = "/p2p-test/1.0.0"

// Message represents a basic network message
type Message struct {
	Type    string      `json:"type"`
	From    string      `json:"from"`
	Payload interface{} `json:"payload"`
}

// Node represents a P2P network node
type Node struct {
	Host      host.Host
	Peers     map[string]peer.AddrInfo
	PeersLock sync.RWMutex
	Running   bool
	NodeID    string
}

// NewNode creates a new P2P node
func NewNode(listenPort int) (*Node, error) {
	// Create a new libp2p host
	h, err := libp2p.New(
		libp2p.ListenAddrStrings(fmt.Sprintf("/ip4/0.0.0.0/tcp/%d", listenPort)),
	)
	if err != nil {
		return nil, err
	}

	nodeID := h.ID().String()
	log.Printf("🌟 Node created with ID: %s", nodeID)
	
	// Log all listening addresses
	for _, addr := range h.Addrs() {
		log.Printf("📡 Listening on: %s/p2p/%s", addr, nodeID)
	}

	node := &Node{
		Host:      h,
		Peers:     make(map[string]peer.AddrInfo),
		Running:   false,
		NodeID:    nodeID,
	}

	// Set up stream handler for incoming connections
	h.SetStreamHandler(protocol.ID(ProtocolID), node.handleStream)

	return node, nil
}

// handleStream processes incoming streams
func (n *Node) handleStream(stream network.Stream) {
	// Get peer ID
	remotePeer := stream.Conn().RemotePeer()
	remotePeerID := remotePeer.String()
	
	log.Printf("📥 Received stream from peer: %s", remotePeerID)
	
	defer stream.Close()

	// Read the message
	var buf []byte
	buffer := make([]byte, 1024)
	for {
		bytes, err := stream.Read(buffer)
		if err != nil {
			if err != io.EOF {
				log.Printf("❌ Error reading from stream: %s", err)
			}
			break
		}
		buf = append(buf, buffer[:bytes]...)
	}

	// Parse message
	if len(buf) > 0 {
		var msg Message
		if err := json.Unmarshal(buf, &msg); err != nil {
			log.Printf("❌ Error parsing message: %s", err)
			return
		}
		
		log.Printf("📩 Received message of type '%s' from %s", msg.Type, msg.From)
		
		// Handle message based on type
		switch msg.Type {
		case "hello":
			log.Printf("👋 Hello message from peer %s", msg.From)
			// Add to peers list if not already there
			n.AddPeer(remotePeer)
			// Send back a hello message
			n.SendMessage(remotePeerID, Message{
				Type: "hello_ack",
				From: n.NodeID,
				Payload: map[string]interface{}{
					"time": time.Now().Format(time.RFC3339),
				},
			})
		case "hello_ack":
			log.Printf("✅ Acknowledgment from peer %s", msg.From)
		default:
			log.Printf("ℹ️ Unhandled message type: %s", msg.Type)
		}
	}
}

// Connect establishes connection to a peer
func (n *Node) Connect(addr string) error {
	// Parse address
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
	n.AddPeer(info.ID)
	
	// Send hello message
	n.SendMessage(info.ID.String(), Message{
		Type: "hello",
		From: n.NodeID,
		Payload: map[string]interface{}{
			"time": time.Now().Format(time.RFC3339),
		},
	})

	log.Printf("🔗 Connected to peer: %s", info.ID.String())
	return nil
}

// AddPeer adds a peer to the node's peer list
func (n *Node) AddPeer(peerID peer.ID) {
	n.PeersLock.Lock()
	defer n.PeersLock.Unlock()
	
	peerIDStr := peerID.String()
	
	// Check if already in the list
	if _, exists := n.Peers[peerIDStr]; exists {
		return
	}
	
	// Get peer info
	addrInfo := peer.AddrInfo{
		ID:    peerID,
		Addrs: n.Host.Peerstore().Addrs(peerID),
	}
	
	// Add to peers list
	n.Peers[peerIDStr] = addrInfo
	log.Printf("➕ Added peer to list: %s", peerIDStr)
}

// SendMessage sends a message to a specific peer
func (n *Node) SendMessage(peerID string, msg Message) error {
	// Parse peer ID
	pid, err := peer.Decode(peerID)
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

	log.Printf("📤 Sent message of type '%s' to %s", msg.Type, peerID)
	return nil
}

// Broadcast sends a message to all connected peers
func (n *Node) Broadcast(msg Message) {
	n.PeersLock.RLock()
	peers := make([]string, 0, len(n.Peers))
	for id := range n.Peers {
		peers = append(peers, id)
	}
	n.PeersLock.RUnlock()

	log.Printf("📣 Broadcasting message of type '%s' to %d peers", msg.Type, len(peers))
	
	for _, id := range peers {
		go func(peerID string) {
			if err := n.SendMessage(peerID, msg); err != nil {
				log.Printf("❌ Failed to send to peer %s: %s", peerID, err)
			}
		}(id)
	}
}

// ListPeers prints out all connected peers
func (n *Node) ListPeers() {
	n.PeersLock.RLock()
	defer n.PeersLock.RUnlock()
	
	log.Printf("👥 Connected peers (%d):", len(n.Peers))
	for id := range n.Peers {
		log.Printf("  - %s", id)
	}
}

// Start begins the node operation
func (n *Node) Start() {
	n.Running = true
	log.Println("🚀 Node started successfully")
	
	// Start a heartbeat to maintain connections
	go func() {
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()
		
		for n.Running {
			select {
			case <-ticker.C:
				n.ListPeers()
				n.Broadcast(Message{
					Type: "heartbeat",
					From: n.NodeID,
					Payload: map[string]interface{}{
						"time": time.Now().Format(time.RFC3339),
					},
				})
			}
		}
	}()
}

// Stop shuts down the node
func (n *Node) Stop() {
	log.Println("🛑 Stopping node...")
	n.Running = false
	n.Host.Close()
	log.Println("👋 Node shutdown complete")
}

func main() {
	// Parse command line arguments
	port := flag.Int("port", 9000, "Port to listen on")
	peerAddrs := flag.String("peers", "", "Comma-separated list of peer addresses")
	flag.Parse()

	// Create node
	node, err := NewNode(*port)
	if err != nil {
		log.Fatalf("❌ Failed to create node: %s", err)
	}

	// Connect to peers
	if *peerAddrs != "" {
		peers := strings.Split(*peerAddrs, ",")
		for _, addr := range peers {
			addr = strings.TrimSpace(addr)
			if addr == "" {
				continue
			}
			
			log.Printf("🔌 Connecting to peer: %s", addr)
			if err := node.Connect(addr); err != nil {
				log.Printf("❌ Failed to connect to peer %s: %s", addr, err)
			}
		}
	}

	// Start node
	node.Start()
	
	// Print commands help
	fmt.Println("\n=== Available Commands ===")
	fmt.Println("Press Ctrl+C to exit")
	fmt.Println("========================\n")
	
	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan
	
	node.Stop()
}