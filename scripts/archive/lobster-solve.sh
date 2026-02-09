#!/bin/bash
# Solve Moltbook lobster captcha challenges using OpenRouter LLM
# Usage: lobster-solve.sh "challenge string"
# Returns: number with 2 decimal places (e.g., "47.00")
# 
# The captcha disguises math problems in alternating case with random
# lobster-themed noise words. This script uses an LLM to parse and solve.

CHALLENGE="$1"
if [ -z "$CHALLENGE" ]; then
  echo "Usage: lobster-solve.sh 'challenge string'" >&2
  exit 1
fi

OR_KEY=$(jq -r '.api_key' ~/.config/openrouter/credentials.json)

# Escape the challenge for JSON
ESCAPED=$(echo "$CHALLENGE" | jq -Rs '.')

ANSWER=$(curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OR_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"deepseek/deepseek-chat-v3.1\",
    \"messages\": [
      {\"role\": \"system\", \"content\": \"You extract and solve math from obfuscated text. The text contains numbers as words (e.g. 'ThIrTy TwO' = 32) and operations (+, -, times, product, adds, slows by, net force minus, accelerates by, total). Extract the numbers, identify the operation, compute. Reply with ONLY the decimal number to 2 places like 47.00. For subtraction results, include the sign if negative like -5.00. For velocity problems: 'moves at X, slows by Y' means X-Y. 'moves at X, accelerates by Y' means X+Y. For force: 'applies X, opponent applies Y, net force' means X-Y.\"},
      {\"role\": \"user\", \"content\": $ESCAPED}
    ],
    \"max_tokens\": 20,
    \"temperature\": 0
  }" | jq -r '.choices[0].message.content' | grep -oE '[-]?[0-9]+\.[0-9]+' | head -1)

if [ -z "$ANSWER" ]; then
  echo "ERROR: Could not solve challenge" >&2
  exit 1
fi

echo "$ANSWER"
