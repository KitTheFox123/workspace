#!/bin/bash
# captcha-solver-or.sh — Moltbook captcha solver using OpenRouter (DeepSeek)
# Usage: ./captcha-solver-or.sh "CHALLENGE_TEXT"
# Returns: number with 2 decimal places (e.g., "46.00")
# Falls back to captcha-solver-v3.sh (regex) if OpenRouter fails

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
challenge="${1:-$(cat)}"

OR_KEY=$(jq -r '.api_key' ~/.config/openrouter/credentials.json 2>/dev/null || echo "")

if [[ -z "$OR_KEY" ]]; then
  exec "$SCRIPT_DIR/captcha-solver-v3.sh" "$challenge"
fi

# Strip "lobster claw" prefix, normalize case, ask for just the math
prompt="Ignore 'lobster' and 'claw'. The remaining words are numbers and an operation (+, -, times, product). Solve the math. Reply with ONLY the number.

Example: 'LoObStEr ClAw ThIrTy TwO + FoUrTeEn' → 46
Example: 'lobster claw fifty times three' → 150

Solve: $challenge"

response=$(curl -s --max-time 20 https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OR_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg p "$prompt" '{
    model: "deepseek/deepseek-chat-v3.1",
    messages: [{role: "system", content: "You are a math solver. Reply with ONLY a number. No explanation."}, {role: "user", content: $p}],
    max_tokens: 10,
    temperature: 0
  }')" 2>/dev/null)

answer=$(echo "$response" | jq -r '.choices[0].message.content // empty' 2>/dev/null | grep -oE '[0-9]+(\.[0-9]+)?' | head -1)

if [[ -n "$answer" ]]; then
  printf "%.2f\n" "$answer"
else
  # Fallback to regex solver
  "$SCRIPT_DIR/captcha-solver-v3.sh" "$challenge"
fi
