package main

import (
	"crypto/sha256"
	"fmt"
)

// ResponseData defines the structure of our JSON response
type ResponseData struct {
	InputNumber  int64 `json:"inputNumber"`
	PseudoRandom int64 `json:"pseudoRandomNumber"`
}

// Constants for the pseudorandom number generation
const (
	MULTIPLIER = 75327 // A large prime number
	MODULUS    = 10    // The number of nodes int he network
)

// Transaction represents a simple transaction structure
type Transaction struct {
	ID     string
	Amount float64
}

// generatePseudoRandom takes a number and returns a pseudorandom number
// by multiplying it by a large constant and taking the modulo
func BBgeneratePseudoRandom(num int64) int64 {
	return (num * MULTIPLIER) % MODULUS
}

// ExecuteTransactions simulates executing transactions and building a block
func BBExecuteTransactions(transactions string) Block {
	block := Block{Transactions: transactions}
	block.Hash = CalculateHash(transactions)
	block.Votes = 0
	return block
}

// CalculateHash generates a hash for the transactions
func CalculateHash(transactions string) string {
	hasher := sha256.New()
	hasher.Write([]byte(transactions))

	return fmt.Sprintf("%x", hasher.Sum(nil))
}

// VerifyBlock checks if the block's hash matches the calculated hash of its transactions
func BBVerifyBlock(block Block) bool {
	calculatedHash := CalculateHash(block.Transactions)
	return block.Hash == calculatedHash
}
