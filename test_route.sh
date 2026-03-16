#!/bin/bash

# --- Configuration ---
API_URL="http://localhost:4000/v1/chat/completions"
API_KEY="sk-1234"
MODEL="smart-proxy"

# --- Colors ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}🚀 Starting Smart Routing Integration Tests${NC}"
echo -e "Target Model: ${YELLOW}$MODEL${NC}"
echo -e "Logs Directory: ${YELLOW}logs/routing/${NC}\n"

# Function to send a test request
send_test() {
    local scenario=$1
    local prompt=$2
    
    echo -e "${BLUE}[TEST: $scenario]${NC}"
    echo -e "Prompt: \"$prompt\""
    
    # Clean up old routing logs for this test if they exist
    # (Just to make it easier to find the newest one)
    
    response=$(curl -s -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d "{
            \"model\": \"$MODEL\",
            \"messages\": [{\"role\": \"user\", \"content\": \"$prompt\"}],
            \"max_tokens\": 50
        }")
    echo -e "Response: $response"
    # Extract the model from the response if returned, or just show success
    if echo "$response" | grep -q "error"; then
        echo -e "❌ ${RED}Error:${NC} $(echo "$response" | jq -r '.error.message')"
    else
        # We look for the newest log file to see where it actually routed
        latest_log=$(ls -t logs/routing/route_*.json 2>/dev/null | head -n 1)
        if [ ! -z "$latest_log" ]; then
            target=$(jq -r '.target_logical_model' "$latest_log")
            provider=$(jq -r '.target_provider_model' "$latest_log")
            echo -e "✅ ${GREEN}Routed to:${NC} $target ($provider)"
        else
            echo -e "⚠️  ${YELLOW}No routing log found. Check if the proxy is running.${NC}"
        fi
    fi
    echo "----------------------------------------------------"
}

# 1. Test Coding Scenario
send_test "CODING" "Write a python function to sort a list of integers."

# 2. Test Reasoning Scenario
send_test "REASONING" "Think step by step: what are the implications of quantum computing on modern cryptography?"

# 3. Test Summary Scenario
send_test "SUMMARY" "Summarize the key points of the Magna Carta in three sentences."

# 4. Test Flash Scenario
send_test "FLASH" "Hello! How are you today?"

# 5. Test Default Scenario
send_test "DEFAULT" "What is the capital of France?"

echo -e "\n${BLUE}🏁 Tests Completed.${NC}"
echo -e "Check ${YELLOW}logs/routing/${NC} for full JSON routing details."
