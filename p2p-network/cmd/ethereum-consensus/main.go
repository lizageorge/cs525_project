package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"time"

	"github.com/gorilla/websocket"

	// "p2p-network/pkg/messaging"
)

// TODO this should def be refer to the same as in node code
type GossipPayload struct {
	ID     string `json:"id"`
	Text   string `json:"text"`
	Time   string `json:"time"`
	Origin string `json:"origin"`
}

func setupWebSocket() (*websocket.Conn, error) {
	wsURL := flag.String("ws", "ws://localhost:8080/ws", "WebSocket server URL")
	flag.Parse()

	log.Printf("Connecting to WebSocket server at %s...", *wsURL)
	conn, _, err := websocket.DefaultDialer.Dial(*wsURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to WebSocket server: %v", err)
	}
	log.Println("Connected to WebSocket server")
	return conn, nil
}

func handleWebSocketMessages(conn *websocket.Conn, done chan struct{}) {
	defer close(done)
	for {
		_, message, err := conn.ReadMessage()
		if err != nil {
			log.Printf("WebSocket read error: %v", err)
			return
		}

		var msg map[string]interface{}
		if err := json.Unmarshal(message, &msg); err != nil {
			log.Printf("Failed to parse message: %v", err)
			continue
		}

		msgType, _ := msg["type"].(string)
		if msgType == "gossip_received" {
			data, _ := msg["data"].(map[string]interface{})
			// parse data into GossipPayload
			gossip_payload := GossipPayload{
				ID:     data["id"].(string),
				Text:   data["text"].(string),
				Time:   data["time"].(string),
				Origin: data["origin"].(string),
			}

			// Decode the block (assuming its a block)
			block, err := DecodeBlock(gossip_payload.Text)
			if err != nil {
				log.Printf("Failed to decode block: %v", err)
				continue
			}
			fmt.Printf("\n📨 Received gossiped block from %s :\n   %s\n\n",
				gossip_payload.Origin, block.Hash)
		} else if status, ok := msg["status"].(string); ok && status == "ok" {
			serverMsg, _ := msg["message"].(string)
			log.Printf("Server response: %s", serverMsg)
		}
	}
}

func WaitForInterrupt(done chan struct{}, conn *websocket.Conn) {
	// Set up channel to receive interrupt signals
	interrupt := make(chan os.Signal, 1)
	signal.Notify(interrupt, os.Interrupt)

	// Wait for either done signal or interrupt
	select {
	case <-done:
		return
	case <-interrupt:
		log.Println("Interrupt received, closing connection...")

		// Cleanly close the connection
		err := conn.WriteMessage(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""),
		)
		if err != nil {
			log.Printf("Error during close: %v", err)
		}

		// Wait for the server to close the connection
		select {
		case <-done:
		case <-time.After(time.Second):
		}
	}
}

// sendGossipMessage sends a message to the WebSocket server
func sendGossipMessage(conn *websocket.Conn, block string, transactions string, votes int) error {
	// Encode block intro string first
	encodedBlock, err := EncodeBlock(Block{
		Hash:         block,
		Transactions: transactions,
		Votes:        votes,
	})
	if err != nil {
		return fmt.Errorf("Failed to encode block: %v", err)
	}

	log.Printf("Sending gossip message: %s", block)
	cmd := map[string]string{
		"action": "gossip",
		"text":   encodedBlock,
	}

	jsonCmd, err := json.Marshal(cmd)
	if err != nil {
		return fmt.Errorf("failed to marshal command: %v", err)
	}

	if err := conn.WriteMessage(websocket.TextMessage, jsonCmd); err != nil {
		return fmt.Errorf("failed to send message: %v", err)
	}

	// Wait for the message to be processed TODO check if this is needed
	time.Sleep(500 * time.Millisecond)

	return nil
}

func main() {
	// Websocket setup
	conn, err := setupWebSocket()
	if err != nil {
		log.Fatalf("%v", err)
	}
	defer conn.Close()

	interrupt := make(chan os.Signal, 1)
	signal.Notify(interrupt, os.Interrupt)

	done := make(chan struct{})

	go handleWebSocketMessages(conn, done)

	// MAIN FUNCTIONALITY
	// Send a single block as gossip message
	block := "abcdef"
	transactions := "tx1,tx2,tx3"
	votes := 3
	if err := sendGossipMessage(conn, block, transactions, votes); err != nil {
		log.Fatalf("%v", err)
	}

	// -----

	// maintain list of seen messages

	// call BB to get proposer ID

	// if self = proposer
	// generate block (BB)

	// add vote to block

	// attest (BB)

	// send block to gossip network
	// mark as seen

	// constantly listening for blocks
	// if block msg id is seen
	// ignore

	// if i haven't voted yet
	// attest (BB)
	// add vote to block
	// change block id
	// if enough votes,
	// add to local chain

	// mark this block id as seen
	// forward it

	// -----

	WaitForInterrupt(done, conn)
}
