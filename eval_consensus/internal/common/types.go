package common

// GossipPayload represents the structure of a gossip message.
type GossipPayload struct {
	ID     string `json:"id"`
	Text   string `json:"text"`
	Time   string `json:"time"`
	Origin string `json:"origin"`
}

// Block represents a block with a hash, transactions, and votes
type Block struct {
	Hash         string `json:"hash"`
	Transactions string `json:"transactions"`
	Votes        int    `json:"votes"`
}