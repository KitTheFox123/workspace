#!/bin/bash
# captcha-solver-hybrid.sh — Solve Moltbook captchas: regex first, OpenRouter fallback
# Our regex solver (captcha-solver-v3.sh) is more reliable for basic arithmetic
# than DeepSeek which sometimes miscalculates (e.g., 32+12=35)
# Usage: ./captcha-solver-hybrid.sh "CHALLENGE_TEXT"
# Returns: number with 2 decimal places

set -euo pipefail

CHALLENGE="${1:?Usage: captcha-solver-hybrid.sh CHALLENGE_TEXT}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Try regex solver first (more reliable for arithmetic)
REGEX_ANSWER=$("$SCRIPT_DIR/captcha-solver-v3.sh" "$CHALLENGE" 2>/dev/null || echo "")

if [[ -n "$REGEX_ANSWER" && "$REGEX_ANSWER" != "0.00" ]]; then
  echo "$REGEX_ANSWER"
  exit 0
fi

# Fallback to OpenRouter
OR_ANSWER=$("$SCRIPT_DIR/captcha-solver-or.sh" "$CHALLENGE" 2>/dev/null || echo "")

if [[ -n "$OR_ANSWER" ]]; then
  echo "$OR_ANSWER"
  exit 0
fi

echo "ERROR: Both solvers failed" >&2
exit 1
