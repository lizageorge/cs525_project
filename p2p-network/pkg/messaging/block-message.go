package messaging

import (
	"encoding/json"
)

// Block represents a block with a hash, transactions, and votes
// TODO need to figure out how to move to some external file and share properly
type Block struct {
	Hash        string `json:"hash"`
	Transactions string `json:"transactions"`
	Votes       int    `json:"votes"`
}

// EncodeBlock encodes a Block object into a JSON string
func EncodeBlock(block Block) (string, error) {
	encoded, err := json.Marshal(block)
	if err != nil {
		return "", err
	}
	return string(encoded), nil
}

// DecodeBlock decodes a JSON string into a Block object
func DecodeBlock(data string) (Block, error) {
	var block Block
	err := json.Unmarshal([]byte(data), &block)
	if err != nil {
		return Block{}, err
	}
	return block, nil
}

// func main() {
// 	// Create a sample Block
// 	block := Block{
// 		Hash:        "abc123",
// 		Transactions: "tx1,tx2,tx3",
// 		Votes:       5,
// 	}
// 	fmt.Println(block)

// 	// Encode the Block
// 	encodedBlock, err := EncodeBlock(block)
// 	if err != nil {
// 		fmt.Println("Error encoding block:", err)
// 		return
// 	}
// 	fmt.Println("Encoded Block:", encodedBlock)

// 	// Decode the Block
// 	decodedBlock, err := DecodeBlock(encodedBlock)
// 	if err != nil {
// 		fmt.Println("Error decoding block:", err)
// 		return
// 	}
// 	fmt.Println("Decoded Block:", decodedBlock)
// }
