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
	"github.com/libp2p/go-libp2p/core/crypto"
	"github.com/libp2p/go-libp2p/core/host"
	"github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/peer"
	"github.com/libp2p/go-libp2p/core/protocol"
	"github.com/multiformats/go-multiaddr"
)

// Constants
const ProtocolID = "/p2p-test/1.0.0"

type Message struct {
	Type    string      `json:"type"`
	FromID    string      `json:"fromID"`
	FromName    string      `json:"fromName"`
	Payload interface{} `json:"payload"`
}

type PeerInfo struct {
    PeerAddr peer.AddrInfo
    PeerName string
}

type Node struct {
	Host      host.Host
	Peers     map[string]PeerInfo
	PeersLock sync.RWMutex
	Running   bool
	NodeID    string
	NodeName  string
}

func NewNode(listenPort int, keyPath string, nodeName string) (*Node, error) {
	// Check or generate private key
    priv, err := loadOrCreatePrivateKey(keyPath)
    if err != nil {
        return nil, fmt.Errorf("failed to get private key: %w", err)
    }

    // Create a new libp2p host with the persistent private key
    h, err := libp2p.New(
        libp2p.ListenAddrStrings(fmt.Sprintf("/ip4/0.0.0.0/tcp/%d", listenPort)),
        libp2p.Identity(priv),
    )
    if err != nil {
        return nil, err
    }

	nodeID := h.ID().String()
	log.Printf("🌟 Node created with  name: %s, ID: %s", nodeName, nodeID)
	
	// Log all listening addresses
	for _, addr := range h.Addrs() {
		log.Printf("📡 Listening on: %s/p2p/%s", addr, nodeID)
	}

	node := &Node{
		Host:      h,
		Peers:     make(map[string]PeerInfo),
		Running:   false,
		NodeID:    nodeID,
		NodeName:  nodeName,
	}

	// Set up stream handler for incoming connections
	h.SetStreamHandler(protocol.ID(ProtocolID), node.handleStream)

	return node, nil
}

// loadOrCreatePrivateKey loads an existing key from disk or creates a new one if it doesn't exist
func loadOrCreatePrivateKey(keyPath string) (crypto.PrivKey, error) {
    // Check if private key file exists
    if _, err := os.Stat(keyPath); os.IsNotExist(err) {
        // Key doesn't exist, generate a new one
        priv, _, err := crypto.GenerateKeyPair(crypto.Ed25519, -1)
        if err != nil {
            return nil, err
        }
        
        // Save the private key to file
        keyBytes, err := crypto.MarshalPrivateKey(priv)
        if err != nil {
            return nil, err
        }
        
        err = os.WriteFile(keyPath, keyBytes, 0600)
        if err != nil {
            return nil, err
        }
        
        log.Printf("✅ Generated and saved new private key to %s", keyPath)
        return priv, nil
    }
    
    // Key exists, load it
    keyBytes, err := os.ReadFile(keyPath)
    if err != nil {
        return nil, err
    }
    
    priv, err := crypto.UnmarshalPrivateKey(keyBytes)
    if err != nil {
        return nil, err
    }
    
    log.Printf("✅ Loaded existing private key from %s", keyPath)
    return priv, nil
}

// handleStream processes incoming streams
func (n *Node) handleStream(stream network.Stream) {
	// Get peer ID
	remotePeer := stream.Conn().RemotePeer()
	
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
		
		if msg.Type != "heartbeat" {
			log.Printf("📩 Received message of type '%s' from %s", msg.Type, msg.FromName)
		}
		
		// Handle message based on type
		switch msg.Type {
		case "hello":
			log.Printf("👋 Hello message from peer %s", msg.FromName)
			// Add to peers list if not already there
			targetPeer := n.AddPeer(remotePeer, msg.FromName)
			// Send back a hello message
			n.SendMessage(targetPeer, Message{
				Type: "hello_ack",
				FromID: n.NodeID,
				FromName: n.NodeName,
				Payload: map[string]interface{}{
					"time": time.Now().Format(time.RFC3339),
				},
			})
		case "hello_ack":
			log.Printf("✅ Acknowledgment from peer %s", msg.FromName)
		default:
			if msg.Type != "heartbeat" {
				log.Printf("ℹ️ Unhandled message type: %s", msg.Type)
			}
		}
	}
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
	newPeer := n.AddPeer(info.ID, name) // TODO change at other uses to add peer to use peer struct
	
	// Send hello message TODO change this first para
	n.SendMessage(newPeer, Message{ 
		Type: "hello",
		FromName: n.NodeName,
		FromID: n.NodeID,
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

	if msg.Type != "heartbeat" {
		log.Printf("📤 Sent message of type '%s' to %s", msg.Type, targetPeer.PeerName)
	}
	return nil
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

// ListPeers prints out all connected peers
func (n *Node) ListPeers() {
	n.PeersLock.RLock()
	defer n.PeersLock.RUnlock()
	
	log.Printf("👥 Connected peers (%d):", len(n.Peers))
	for _, peer := range n.Peers {
		log.Printf("  - %s", peer.PeerName)
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
					FromID: n.NodeID,
					FromName: n.NodeName,
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
	keyPath := flag.String("keyPath", "keyPath.pem", "Path to private key file")
	peersFilePath := flag.String("peersFile", "peersFile.json", "Path to file containing peer addresses and this node's name")
	flag.Parse()


	// Read peer data from file
	peerDataJSON, err := os.ReadFile(*peersFilePath)
	if err != nil {
		log.Fatalf("❌ Failed to read peers file: %s", err)
	}

	// Parse JSON data
	var peerData struct {
		VmName	 string   `json:"vmName"`
		VmPeers []struct {
			Address  string `json:"addr"`
			Name string `json:"name"`
		} `json:"vmPeers"`
	}
	if err := json.Unmarshal(peerDataJSON, &peerData); err != nil {
		log.Fatalf("❌ Failed to parse peers file: %s", err)
	}

	// Create node
	node, err := NewNode(*port, *keyPath, peerData.VmName)
	if err != nil {
		log.Fatalf("❌ Failed to create node: %s", err)
	}

	// Connect to each peer
	for _, peer := range peerData.VmPeers {
		addr := strings.TrimSpace(peer.Address)
		name := strings.TrimSpace(peer.Name)
		if addr == "" || name == "" {
			continue
		}

		if name == node.NodeName {
			continue
		}

		log.Printf("🔌 Connecting to peer: %s", name)
		if err := node.Connect(addr, name); err != nil {
			log.Printf("❌ Failed to connect to peer %s: %s", addr, err)
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