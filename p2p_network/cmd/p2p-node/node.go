package main

// TODO split this up over some files
import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/gorilla/websocket"
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
const GOSSIP_B = 3
const MAX_SEEN_MESSAGES = 50

type Message struct {
	Type     string      `json:"type"`
	FromID   string      `json:"fromID"`
	FromName string      `json:"fromName"`
	Payload  interface{} `json:"payload"`
}

type GossipPayload struct {
	ID     string `json:"id"`
	Text   string `json:"text"`
	Time   string `json:"time"`
	Origin string `json:"origin"`
}

type PeerInfo struct {
	PeerAddr peer.AddrInfo
	PeerName string
}

type Node struct {
	NodeID       string
	NodeName     string
	Host         host.Host
	Running      bool
	Peers        map[string]PeerInfo
	PeersLock    sync.RWMutex
	SeenMsgs     map[string]bool // Track seen gossip message IDs
	SeenMsgsLock sync.RWMutex
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
		SeenMsgs:  make(map[string]bool),
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

// Add a function to broadcast to all WebSocket clients
func (n *Node) broadcastToClients(msgType string, data interface{}) {
	message := map[string]interface{}{
		"type": msgType,
		"data": data,
	}

	jsonMsg, err := json.Marshal(message)
	if err != nil {
		log.Printf("❌ Error marshaling WebSocket message: %s", err)
		return
	}

	n.wsClientsMux.Lock()
	defer n.wsClientsMux.Unlock()

	for client := range n.wsClients {
		if err := client.WriteMessage(websocket.TextMessage, jsonMsg); err != nil {
			log.Printf("❌ Error sending to WebSocket client: %s", err)
			client.Close()
			delete(n.wsClients, client)
		}
	}
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
			if payload, ok := msg.Payload.(map[string]interface{}); ok {
				if msgID, ok := payload["id"].(string); ok {

					// Check if we've seen this message before
					n.SeenMsgsLock.RLock()
					seen := n.SeenMsgs[msgID]
					n.SeenMsgsLock.RUnlock()
					if seen {
						// log.Printf("👻 Ignoring already seen gossip message: %s", msgID)
						return
					}

					msgText := "unknown"
					if text, ok := payload["text"].(string); ok {
						msgText = text
					}
					msgOrigin := "unknown"
					if origin, ok := payload["origin"].(string); ok {
						msgOrigin = origin
					}

					// Store this message as seen
					n.SeenMsgsLock.Lock()
					if len(n.SeenMsgs) >= MAX_SEEN_MESSAGES {
						n.pruneSeenMessages()
					}
					n.SeenMsgs[msgID] = true
					n.SeenMsgsLock.Unlock()

					log.Printf("💬 GOSSIP from %s (origin: %s): %s", msg.FromName, msgOrigin, msgText)

					go n.forwardGossipMessage(msg, remotePeer.String())

					// Notify WebSocket clients about the received gossip
					n.broadcastToClients("gossip_received", map[string]interface{}{
						"from":   msg.FromName,
						"origin": msgOrigin,
						"text":   msgText,
						"time":   time.Now().Format(time.RFC3339),
					})
				}
			}
		default:
			if msg.Type != "heartbeat" {
				log.Printf("ℹ️ Unhandled message type: %s", msg.Type)
			}
		}
	}
}

func (n *Node) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	upgrader := websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
		CheckOrigin: func(r *http.Request) bool {
			return true // Allow all connections
		},
	}

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("❌ WebSocket upgrade error: %s", err)
		return
	}

	// Add client to the map
	n.wsClientsMux.Lock()
	n.wsClients[conn] = true
	n.wsClientsMux.Unlock()

	log.Printf("🔌 New WebSocket client connected")

	// Handle incoming messages from the WebSocket client
	go func() {
		defer func() {
			conn.Close()
			n.wsClientsMux.Lock()
			delete(n.wsClients, conn)
			n.wsClientsMux.Unlock()
			log.Printf("🔌 WebSocket client disconnected")
		}()

		for {
			_, message, err := conn.ReadMessage()
			if err != nil {
				if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
					log.Printf("❌ WebSocket error: %v", err)
				}
				break
			}

			var cmd struct {
				Action string `json:"action"`
				Text   string `json:"text"`
			}

			if err := json.Unmarshal(message, &cmd); err != nil {
				log.Printf("❌ Invalid WebSocket command: %s", err)
				continue
			}

			if cmd.Action == "gossip" && cmd.Text != "" {
				log.Printf("📣 Initiating gossip via WebSocket: %s", cmd.Text)
				n.InitiateGossip(cmd.Text)
				conn.WriteJSON(map[string]string{"status": "ok", "message": "Gossip initiated"})
			}
		}
	}()
}

func (n *Node) StartWebSocketServer(port int) {
	// Create a new HTTP server mux (WebSockets work over HTTP initially)
	mux := http.NewServeMux()

	// Handle WebSocket connections at /ws endpoint
	mux.HandleFunc("/ws", n.handleWebSocket)

	// Start the server in a goroutine
	go func() {
		addr := fmt.Sprintf(":%d", port)
		log.Printf("🌐 Starting WebSocket server on %s", addr)
		if err := http.ListenAndServe(addr, mux); err != nil {
			log.Printf("❌ WebSocket server error: %s", err)
		}
	}()
}

// pruneSeenMessages removes half of old seen message IDs when the cache gets too full.
// Very rough implementation (assuming keys are roughly time-ordered by insertion)
func (n *Node) pruneSeenMessages() {
	toDelete := len(n.SeenMsgs) / 2
	deleteCount := 0
	for key := range n.SeenMsgs {
		delete(n.SeenMsgs, key)
		deleteCount++
		if deleteCount >= toDelete {
			break
		}
	}

	log.Printf("🧹 Pruned %d old message IDs from seen cache", deleteCount)
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

// InitiateGossip starts a new gossip message from this node
func (n *Node) InitiateGossip(text string) {
	// Create gossip payload with unique message ID
	msgID := fmt.Sprintf("%s-%d", n.NodeID[:8], time.Now().UnixNano())
	payload := GossipPayload{
		ID:     msgID,
		Text:   text,
		Time:   time.Now().Format(time.RFC3339),
		Origin: n.NodeName,
	}

	// Mark this message as seen by current node
	n.SeenMsgsLock.Lock()
	n.SeenMsgs[msgID] = true
	n.SeenMsgsLock.Unlock()

	msg := Message{
		Type:     "gossip",
		FromID:   n.NodeID,
		FromName: n.NodeName,
		Payload:  payload,
	}

	go n.forwardGossipMessage(msg, n.NodeID)

	log.Printf("💬 GOSSIP initiated: %s", text)
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
				n.InitiateGossip(msgText)
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
		ticker := time.NewTicker(30 * time.Second)
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
		VmName  string `json:"vmName"`
		VmPeers []struct {
			Address string `json:"addr"`
			Name    string `json:"name"`
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
			log.Printf("❌ Failed to connect to peer %s: %s", name, err)
		}
	}

	// Start node
	node.Start()
	node.StartWebSocketServer(8080)

	// Print commands help
	fmt.Println("\n=== Available Commands ===")
	fmt.Println("Press 'g' then ENTER to send a gossip message")
	fmt.Println("Press Ctrl+C to exit")
	fmt.Println("========================")

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan

	node.Stop()
}
