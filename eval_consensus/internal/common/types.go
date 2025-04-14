package common

// GossipPayload represents the structure of a gossip message.
type GossipPayload struct {
	ID     string `json:"id"`
	Text   string `json:"text"`
	Time   string `json:"time"`
	Origin string `json:"origin"`
}