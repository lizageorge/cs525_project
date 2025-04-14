package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"os"
	"os/signal"
	"strconv"
	"sync"
	"time"

	"eval_consensus/internal/blackbox"
	"eval_consensus/internal/common"

	"github.com/gorilla/websocket"
)

const INPUT_FILE_PATH = "../inputs/peersFile.json"
const LOCAL_CHAIN_FILE_PATH = "../inputs/localChain.txt"

type Client struct {
	VMID              string
	seenMessages      map[string]int // TODO this should have a pruning function
	seenMessagesMutex sync.RWMutex
	conn              *websocket.Conn
	numPeers          int
	votedThisEpoch    bool
	proposerThisEpoch int
}

func NewClient(conn *websocket.Conn) *Client {
	// Read VMID from file
	peerDataJSON, err := os.ReadFile(INPUT_FILE_PATH)
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

	return &Client{
		VMID:           peerData.VmName,
		seenMessages:   make(map[string]int),
		conn:           conn,
		votedThisEpoch: false,                 // TODO this should be reset with every epoch, once that's implementec
		numPeers:       len(peerData.VmPeers), // TODO this should be actively managed, get this info from network node
	}
}

func (c *Client) checkProposer() bool {
	vmIDNumber, err := strconv.Atoi(c.VMID[2:])
	if err != nil {
		log.Fatalf("Failed to extract number from VMID: %v", err)
	}
	return c.proposerThisEpoch == vmIDNumber
}

func (mt *Client) HasSeen(id string) bool {
	mt.seenMessagesMutex.RLock()
	defer mt.seenMessagesMutex.RUnlock()
	if _, ok := mt.seenMessages[id]; ok {
		return true
	}
	return false
}

func (mt *Client) getVotesSeen(id string) int {
	mt.seenMessagesMutex.RLock()
	defer mt.seenMessagesMutex.RUnlock()
	return mt.seenMessages[id]
}

func (mt *Client) UpdateVotesSeen(id string, int votes) {
	mt.seenMessagesMutex.Lock()
	defer mt.seenMessagesMutex.Unlock()
	mt.seenMessages[id] = votes
}

func (c *Client) generateMsgID() string {
	return strconv.Itoa(rand.Intn(99999))
}

func addToLocalChain(transactions string) error {
	f, err := os.OpenFile(LOCAL_CHAIN_FILE_PATH, os.O_APPEND|os.O_WRONLY|os.O_CREATE, 0600)
	if err != nil {
		return err
	}

	defer f.Close()

	if _, err = f.WriteString(transactions); err != nil {
		return err
	}
	return nil
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

func (c *Client) handleWebSocketMessages(done chan struct{}) {
	defer close(done)
	for {
		_, message, err := c.conn.ReadMessage()
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
			// fmt.Println("Received gossip message: ", data)

			// parse data into GossipPayload
			gossip_payload := common.GossipPayload{
				ID:     data["id"].(string),
				Text:   data["text"].(string),
				Time:   data["time"].(string),
				Origin: data["origin"].(string),
			}

			c.handleGossipBlock(gossip_payload) // (TODO: currently assuming its a block)
		} else if status, ok := msg["status"].(string); ok && status == "ok" {
			serverMsg, _ := msg["message"].(string)
			log.Printf("Server response: %s", serverMsg)
		}
	}
}

func (c *Client) WaitForInterrupt(done chan struct{}) {
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
		err := c.conn.WriteMessage(
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

// sendGossipBlock sends a message to the WebSocket server
func (c *Client) sendGossipBlock(msgId string, unencoded_block common.Block) error {
	// Encode block into string first
	// TODO check if this is needed
	encodedBlock, err := common.EncodeBlock(unencoded_block)
	if err != nil {
		return fmt.Errorf("failed to encode block: %v", err)
	}

	// Generate message ID
	log.Printf("Sending gossip message with ID: %s", msgId)
	cmd := map[string]string{
		"action": "gossip",
		"text":   encodedBlock,
		"id":     msgId,
	}

	jsonCmd, err := json.Marshal(cmd)
	if err != nil {
		return fmt.Errorf("failed to marshal command: %v", err)
	}

	if err := c.conn.WriteMessage(websocket.TextMessage, jsonCmd); err != nil {
		return fmt.Errorf("failed to send message: %v", err)
	}

	// Wait for the message to be processed TODO check if this is needed
	time.Sleep(500 * time.Millisecond)

	return nil
}

func (c *Client) handleGossipBlock(gossip_payload common.GossipPayload) {
	// Decode the block
	block, err := common.DecodeBlock(gossip_payload.Text)
	if err != nil {
		log.Printf("Failed to decode block: %v", err)
		return
	}
	fmt.Printf("\n📨 Received gossiped block from %s :\n   %s\n\n",
		gossip_payload.Origin, gossip_payload.ID)

	// if block msg id is seen, ignore
	if c.HasSeen(gossip_payload.ID) && !c.checkProposer() {
		log.Printf("Already seen this message, ignoring: %s", gossip_payload.ID)
		if block.Votes > getVotesSeen(gossip_payload.ID) {
			if block.Votes >= int(float64(c.numPeers-1)*(0.66)) {
				log.Printf("✅ Block %s has enough votes, adding to local chain", block.Hash)
				err = addToLocalChain(block.Transactions)
				if err != nil {
					log.Printf("Failed to add block to local chain: %v", err)
					return
				}

				c.UpdateVotesSeen(gossip_payload.ID, block.Votes)
				if err := c.sendGossipBlock(gossip_payload.ID, block); err != nil {
					log.Printf("Failed to send gossip message: %v", err)
					return
				}
				fmt.Println("✅ Sent gossiped block to network", block)
			} else {
				log.Printf("❌ Block %s does not have enough votes, only has %d - ", gossip_payload.ID, block.Votes)
			}
		}

	} else {
		// if self hasn't voted yet:
		// attest (BB)
		// add vote to block
		// if block has enough votes:
		// add to local chain
		// mark this block id as seen with updated number of votes
		// forward it to gossip network
		if !c.votedThisEpoch {
			// Attest
			if blackbox.BBVerifyBlock(block) {
				log.Printf("✅ Block %s is valid, voting for it", block.Hash)
				block.Votes += 1
				c.votedThisEpoch = true
			}
			if block.Votes >= int(float64(c.numPeers-1)*(0.66)) {
				log.Printf("✅ Block %s has enough votes, adding to local chain", block.Hash)
				err = addToLocalChain(block.Transactions)
				if err != nil {
					log.Printf("Failed to add block to local chain: %v", err)
					return
				}
			} else {
				log.Printf("❌ Block %s does not have enough votes, only has %d - ", gossip_payload.ID, block.Votes)
			}
			c.UpdateVotesSeen(gossip_payload.ID, block.Votes)
			if err := c.sendGossipBlock(gossip_payload.ID, block); err != nil {
				log.Printf("Failed to send gossip message: %v", err)
				return
			}
			fmt.Println("✅ Sent gossiped block to network", block)
		}

	}

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

	// Initialize the client
	c := NewClient(conn)

	go c.handleWebSocketMessages(done)

	// MAIN FUNCTIONALITY
	// -----

	// mempool of transactions:
	transactions := "tx1:30.45,tx2:20.00,tx3:15.75,tx4:50.00,tx5:10.00"

	epoch := 1 // TODO implement multiple epochs
	c.proposerThisEpoch = int(blackbox.BBgeneratePseudoRandom(int64(epoch)))
	log.Printf("Proposer for this epoch is: %d", c.proposerThisEpoch)

	if c.checkProposer() {
		log.Printf("Proposer %s is generating a block...", c.VMID)

		block := blackbox.BBExecuteTransactions(transactions)

		new_gossip_Id := c.generateMsgID()

		// Mark this block id as seen and forward it to rest of network
		c.UpdateVotesSeen(new_gossip_Id, 0)
		if err := c.sendGossipBlock(new_gossip_Id, block); err != nil {
			log.Printf("Failed to send gossip message: %v", err)
			return
		}
		fmt.Println("✅ Sent gossiped block to network", block)

	}
	// constantly listening for blocks -> handlegossipblock
	// -----

	c.WaitForInterrupt(done)
}
