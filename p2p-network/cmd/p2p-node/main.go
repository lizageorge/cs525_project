package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"
)




func main() {
	// Parse command line arguments
	port := flag.Int("port", 9000, "Port to listen on")
	keyPath := flag.String("keyPath", "../inputs/keyPath.pem", "Path to private key file")
	peersFilePath := flag.String("peersFile", "../inputs/peersFile.json", "Path to file containing peer addresses and this node's name")
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
