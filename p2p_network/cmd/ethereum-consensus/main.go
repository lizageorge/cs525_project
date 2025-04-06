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
)

// setupWebSocket establishes a connection to the WebSocket server
func setupWebSocket() (*websocket.Conn, error) {
	wsURL := flag.String("ws", "ws://localhost:8080/ws", "WebSocket server URL")
	flag.Parse()

	log.Printf("Connecting to WebSocket server at %s...", wsURL)
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to WebSocket server: %v", err)
	}
	log.Println("Connected to WebSocket server")
	return conn, nil
}

// handleWebSocketMessages processes incoming messages from the WebSocket
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
			from, _ := data["from"].(string)
			text, _ := data["text"].(string)
			origin, _ := data["origin"].(string)
			time, _ := data["time"].(string)

			fmt.Printf("\n📨 Received gossip from %s (origin: %s) at %s:\n   %s\n\n", 
				from, origin, time, text)
		} else if status, ok := msg["status"].(string); ok && status == "ok" {
			serverMsg, _ := msg["message"].(string)
			log.Printf("Server response: %s", serverMsg)
		}
	}
}

// WaitForInterrupt blocks until an interrupt signal is received
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
            websocket.FormatCloseMessage(websocket.CloseNormalClosure, "")
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
func sendGossipMessage(conn *websocket.Conn, message string) error {
	log.Printf("Sending gossip message: %s", message)
	cmd := map[string]string{
		"action": "gossip",
		"text":   message,
	}

	jsonCmd, err := json.Marshal(cmd)
	if err != nil {
		return fmt.Errorf("failed to marshal command: %v", err)
	}

	if err := conn.WriteMessage(websocket.TextMessage, jsonCmd); err != nil {
		return fmt.Errorf("failed to send message: %v", err)
	}

	// Wait for the message to be processed
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
	// Send a single gossip message
	message := flag.String("msg", "Hello from gossip client!", "Gossip message to send")
	if err := sendGossipMessage(conn, *message); err != nil {
		log.Fatalf("%v", err)
	}

	
	WaitForInterrupt(done, c)
}