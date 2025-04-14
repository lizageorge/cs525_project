package p2p_node

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/libp2p/go-libp2p"
	"github.com/libp2p/go-libp2p/core/crypto"
	"github.com/libp2p/go-libp2p/core/host"
	"github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/protocol"
)

// Constants
const ProtocolID = "/p2p-test/1.0.0"
const GOSSIP_B = 3
const MAX_SEEN_MESSAGES = 50

type Node struct {
	NodeID       string
	NodeName     string
	Host         host.Host
	Running      bool
	Peers        map[string]PeerInfo
	PeersLock    sync.RWMutex
	wsClients    map[*websocket.Conn]bool
	wsClientsMux sync.Mutex
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
		Running:   false,
		NodeID:    nodeID,
		NodeName:  nodeName,
		Peers:     make(map[string]PeerInfo),
		wsClients: make(map[*websocket.Conn]bool),
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

		if msg.Type != "heartbeat" && msg.Type != "hello_ack" {
			log.Printf("📩 Received message of type '%s' from %s", msg.Type, msg.FromName)
		}

		// Handle message based on type
		switch msg.Type {
		case "hello":
			// log.Printf("👋 Hello message from peer %s", msg.FromName)
			// Add to peers list if not already there
			targetPeer := n.AddPeer(remotePeer, msg.FromName)
			// Send back a hello message
			n.SendMessage(targetPeer, Message{
				Type:     "hello_ack",
				FromID:   n.NodeID,
				FromName: n.NodeName,
				Payload: map[string]interface{}{
					"time": time.Now().Format(time.RFC3339),
				},
			})
		case "hello_ack":
			log.Printf("✅ Acknowledgment from peer %s", msg.FromName)
		case "gossip":
			log.Printf("💬 Gossip message from peer %s", msg.FromName)
			if payload, ok := msg.Payload.(map[string]interface{}); ok {
				fmt.Println("Received gossip payload:", payload)
				n.broadcastToClients("gossip_received", map[string]interface{}{
					"id":     payload["id"],
					"origin": payload["origin"],
					"text":   payload["text"],
					"time":   payload["time"],
				})

			}
		default:
			if msg.Type != "heartbeat" {
				log.Printf("ℹ️ Unhandled message type: %s", msg.Type)
			}
		}
	}
}

func (n *Node) handleUserInput() {
	reader := bufio.NewReader(os.Stdin)
	for n.Running {
		input, err := reader.ReadString('\n')
		if err != nil {
			log.Printf("❌ Error reading input: %s", err)
			continue
		}

		input = strings.TrimSpace(input)
		if input == "g" {
			fmt.Print("Enter gossip message: ")
			msgText, err := reader.ReadString('\n')
			if err != nil {
				log.Printf("❌ Error reading message: %s", err)
				continue
			}

			msgText = strings.TrimSpace(msgText)
			if msgText != "" {
				// Generate a unique message ID
				msgID := fmt.Sprintf("%s-%d", n.NodeID[:8], time.Now().UnixNano())
				n.InitiateGossip(msgID, msgText)
			}
		}
	}
}

// Start begins the node operation
func (n *Node) Start() {
	n.Running = true
	log.Println("🚀 Node started successfully")

	// Start a heartbeat to maintain connections
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()

		for n.Running {
			<-ticker.C // Simple channel receive instead of select
			n.ListPeers()
			n.Broadcast(Message{
				Type:     "heartbeat",
				FromID:   n.NodeID,
				FromName: n.NodeName,
				Payload: map[string]interface{}{
					"time": time.Now().Format(time.RFC3339),
				},
			})
		}
	}()

	go n.handleUserInput()
}

// Stop shuts down the node
func (n *Node) Stop() {
	log.Println("🛑 Stopping node...")
	n.Running = false
	n.Host.Close()
	log.Println("👋 Node shutdown complete")
}
