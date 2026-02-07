#!/bin/bash
# captcha-solver-or.sh — Solve Moltbook lobster captchas using OpenRouter (DeepSeek)
# Usage: ./scripts/captcha-solver-or.sh "CHALLENGE_TEXT"
# Returns: the numeric answer (e.g., "161.00")
# Cost: ~$0.0002 per call

set -euo pipefail

CHALLENGE="${1:?Usage: captcha-solver-or.sh CHALLENGE_TEXT}"

OR_KEY=$(jq -r '.api_key' ~/.config/openrouter/credentials.json 2>/dev/null)
if [[ -z "$OR_KEY" || "$OR_KEY" == "null" ]]; then
  echo "ERROR: No OpenRouter key" >&2
  exit 1
fi

# Strip lobster noise, extract the math
PROMPT="Extract the math problem from this obfuscated lobster text and solve it. The text has random capitalization, special characters, and filler words about lobsters. Find the numbers (written as words like 'twenty three') and the operation (addition, subtraction, multiplication, or 'times'/'product'). Return ONLY the numeric answer with 2 decimal places (e.g., '42.00'). No explanation.

Text: $CHALLENGE"

RESULT=$(curl -s --max-time 10 "https://openrouter.ai/api/v1/chat/completions" \
  -H "Authorization: Bearer $OR_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg prompt "$PROMPT" '{
    model: "deepseek/deepseek-chat-v3.1",
    messages: [{role: "user", content: $prompt}],
    max_tokens: 20,
    temperature: 0
  }')" 2>/dev/null)

ANSWER=$(echo "$RESULT" | jq -r '.choices[0].message.content' 2>/dev/null | grep -oP '[\d]+\.[\d]+' | head -1)

if [[ -z "$ANSWER" ]]; then
  # Try extracting just a number
  ANSWER=$(echo "$RESULT" | jq -r '.choices[0].message.content' 2>/dev/null | grep -oP '[\d]+' | head -1)
  if [[ -n "$ANSWER" ]]; then
    printf "%.2f\n" "$ANSWER"
  else
    echo "ERROR: Could not parse answer from: $(echo "$RESULT" | jq -r '.choices[0].message.content' 2>/dev/null)" >&2
    exit 1
  fi
else
  echo "$ANSWER"
fi
