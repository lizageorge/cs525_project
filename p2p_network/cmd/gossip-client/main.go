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

func main() {
	wsURL := flag.String("ws", "ws://localhost:8080/ws", "WebSocket server URL")
	message := flag.String("msg", "Hello from gossip client!", "Gossip message to send")
	flag.Parse()

	// Connect to WebSocket server
	log.Printf("Connecting to WebSocket server at %s...", *wsURL)
	c, _, err := websocket.DefaultDialer.Dial(*wsURL, nil)
	if err != nil {
		log.Fatalf("Failed to connect to WebSocket server: %v", err)
	}
	defer c.Close()
	log.Println("Connected to WebSocket server")

	// Set up channel to receive interrupt signals
	interrupt := make(chan os.Signal, 1)
	signal.Notify(interrupt, os.Interrupt)

	// Set up a channel for received messages
	done := make(chan struct{})

	// Handle incoming messages from the WebSocket
	go func() {
		defer close(done)
		for {
			_, message, err := c.ReadMessage()
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
	}()

	// Send a single gossip message
	log.Printf("Sending gossip message: %s", *message)
	cmd := map[string]string{
		"action": "gossip",
		"text":   *message,
	}

	jsonCmd, err := json.Marshal(cmd)
	if err != nil {
		log.Fatalf("Failed to marshal command: %v", err)
	}

	if err := c.WriteMessage(websocket.TextMessage, jsonCmd); err != nil {
		log.Fatalf("Failed to send message: %v", err)
	}

	// Wait for the message to be processed
	time.Sleep(500 * time.Millisecond)

	// Keep running until interrupted
	for {
		select {
		case <-done:
			return
		case <-interrupt:
			log.Println("Interrupt received, closing connection...")
			
			// Cleanly close the connection
			err := c.WriteMessage(
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
			return
		}
	}
}