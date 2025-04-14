package common

import (
	"encoding/json"
)


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
