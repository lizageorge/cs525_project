package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"
)

// ResponseData defines the structure of our JSON response
type ResponseData struct {
	InputNumber     int64 `json:"inputNumber"`
	PseudoRandom    int64 `json:"pseudoRandomNumber"`
}

// Constants for the pseudorandom number generation
const (
	MULTIPLIER = 75327 // A large prime number
	MODULUS    = 10 // The number of nodes int he network
)

// Transaction represents a simple transaction structure
type Transaction struct {
	ID      string
	Amount  float64
}

// Block represents a block containing transactions
type Block struct {
	Transactions []Transaction `json:"transactions"`
	Hash         string        `json:"hash"`
}

// generatePseudoRandom takes a number and returns a pseudorandom number
// by multiplying it by a large constant and taking the modulo
func generatePseudoRandom(num int64) int64 {
	return (num * MULTIPLIER) % MODULUS
}

// ExecuteTransactions simulates executing transactions and building a block
func ExecuteTransactions(transactions []Transaction) Block {
	block := Block{Transactions: transactions}
	block.Hash = CalculateHash(transactions)
	return block
}

// CalculateHash generates a hash for the transactions
func CalculateHash(transactions []Transaction) string {
	hasher := sha256.New()
	for _, tx := range transactions {
		hasher.Write([]byte(tx.ID))
		hasher.Write([]byte(fmt.Sprintf("%f", tx.Amount)))
	}
	return fmt.Sprintf("%x", hasher.Sum(nil))
}

// VerifyBlock checks if the block's hash matches the calculated hash of its transactions
func VerifyBlock(block Block) bool {
	calculatedHash := CalculateHash(block.Transactions)
	return block.Hash == calculatedHash
}

func randomHandler(w http.ResponseWriter, r *http.Request) {
	// Set response content type
	w.Header().Set("Content-Type", "application/json")
	
	// Get the input number from the query parameter
	numStr := r.URL.Query().Get("number")
	
	if numStr == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{
			"error": "Missing number parameter. Please provide a valid integer.",
		})
		return
	}
	
	// Parse the input number
	num, err := strconv.ParseInt(numStr, 10, 64)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{
			"error": "Invalid number parameter. Please provide a valid integer.",
		})
		return
	}
	
	// Generate the pseudorandom number
	pseudoRandom := generatePseudoRandom(num)
	
	// Create response data
	response := ResponseData{
		InputNumber:  num,
		PseudoRandom: pseudoRandom,
	}
	
	// Log the operation
	log.Printf("Generated pseudorandom number %d from input %d", pseudoRandom, num)
	
	// Return success status
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(response)
}

func executeTransactionHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Invalid request method", http.StatusMethodNotAllowed)
		return
	}

	// Parse the form data
	err := r.ParseForm()
	if err != nil {
		http.Error(w, "Error parsing form", http.StatusBadRequest)
		return
	}

	// Get the transactions from the form data
	transactionsStr := r.FormValue("transactions")
	transactions := parseTransactions(transactionsStr)

	// Execute the transactions
	block := ExecuteTransactions(transactions)

	// Respond with the block hash
	fmt.Fprintf(w, "Block Hash: %s", block.Hash)
}

// parseTransactions converts a string of transactions into a slice of Transaction
func parseTransactions(transactionsStr string) []Transaction {
	var transactions []Transaction
	// Split the string by commas and create Transaction objects
	for _, txStr := range strings.Split(transactionsStr, ",") {
		parts := strings.Split(txStr, ":")
		if len(parts) == 2 {
			id := parts[0]
			amount, err := strconv.ParseFloat(parts[1], 64)
			if err == nil {
				transactions = append(transactions, Transaction{ID: id, Amount: amount})
			}
		}
	}
	return transactions
}

// verifyBlockHandler handles the verification of a block
func verifyBlockHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Invalid request method", http.StatusMethodNotAllowed)
		return
	}

	// Parse the form data
	err := r.ParseForm()
	if err != nil {
		http.Error(w, "Error parsing form", http.StatusBadRequest)
		return
	}

	// Get the transactions from the form data
	transactionsStr := r.FormValue("transactions")
	transactions := parseTransactions(transactionsStr)

	// Get the hash from the form data
	blockHash := r.FormValue("hash")

	// Verify the block
	isValid := VerifyBlock(Block{Transactions: transactions, Hash: blockHash})
	if isValid {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Block is valid"))
	} else {
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte("Block is invalid"))
	}
}

func main() {
	// Define the endpoint
	http.HandleFunc("/random", randomHandler)
	http.HandleFunc("/execute-transactions", executeTransactionHandler)
	http.HandleFunc("/verify-block", verifyBlockHandler)
	// http.HandleFunc("/verify-signature", randomHandler)
	
	// Set the port
	port := 8080
	fmt.Printf("Server starting on port %d...\n", port)
	fmt.Printf("Access the Random API at: http://localhost:%d/random?number=YOUR_NUMBER\n", port)
	
	// Start the server
	log.Fatal(http.ListenAndServe(fmt.Sprintf(":%d", port), nil))
}