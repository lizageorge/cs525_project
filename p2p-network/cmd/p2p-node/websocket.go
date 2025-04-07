package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"

	"github.com/gorilla/websocket"
)

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
				ID 	string `json:"id"`
			}

			if err := json.Unmarshal(message, &cmd); err != nil {
				log.Printf("❌ Invalid WebSocket command: %s", err)
				continue
			}

			if cmd.Action == "gossip" && cmd.Text != "" && cmd.ID != "" {
				fmt.Println("Received gossip command:", cmd.Text)


				log.Printf("📣 Initiating gossip via WebSocket: %s", cmd.Text)
				n.InitiateGossip(cmd.Text, cmd.ID)
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
