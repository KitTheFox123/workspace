#!/bin/bash
# x402-checker.sh — Check if a URL supports x402 micropayments
# Sends a request and checks for HTTP 402 + payment headers
# Usage: ./x402-checker.sh <url>
# Build action: Kit 🦊 2026-02-06

set -euo pipefail

URL="${1:-}"

if [ -z "$URL" ]; then
  echo "Usage: $0 <url>"
  echo ""
  echo "Checks if a URL supports x402 micropayments."
  echo "Looks for HTTP 402 responses and PAYMENT-REQUIRED headers."
  echo ""
  echo "Examples:"
  echo "  $0 https://api.example.com/paid-endpoint"
  echo "  $0 https://some-service.com/resource"
  exit 1
fi

echo "🦞 x402 Payment Check: $URL"
echo "---"

# Send request, capture headers
RESPONSE=$(curl -s -D - -o /tmp/x402-body.txt "$URL" 2>&1)
STATUS=$(echo "$RESPONSE" | head -1 | grep -oP '\d{3}' | head -1)

echo "HTTP Status: $STATUS"

if [ "$STATUS" = "402" ]; then
  echo "✅ x402 Payment Required detected!"
  echo ""
  
  # Extract payment headers
  PAYMENT_HEADER=$(echo "$RESPONSE" | grep -i "payment-required" || true)
  if [ -n "$PAYMENT_HEADER" ]; then
    echo "Payment Header:"
    echo "$PAYMENT_HEADER"
    
    # Try to parse JSON from header
    HEADER_VALUE=$(echo "$PAYMENT_HEADER" | sed 's/^[^:]*: //')
    echo ""
    echo "Parsed details:"
    echo "$HEADER_VALUE" | jq '.' 2>/dev/null || echo "(not JSON)"
  else
    echo "⚠️  No PAYMENT-REQUIRED header found (non-standard 402)"
    echo ""
    echo "Response headers:"
    echo "$RESPONSE" | head -20
  fi
  
  # Show body if it has payment info
  BODY=$(cat /tmp/x402-body.txt)
  if echo "$BODY" | jq '.' >/dev/null 2>&1; then
    echo ""
    echo "Response body:"
    echo "$BODY" | jq '.' 2>/dev/null
  fi
else
  echo "❌ No x402 payment required (status: $STATUS)"
  echo ""
  if [ "$STATUS" = "200" ]; then
    echo "Resource is freely accessible."
  elif [ "$STATUS" = "401" ] || [ "$STATUS" = "403" ]; then
    echo "Standard auth required (not x402)."
  fi
fi

rm -f /tmp/x402-body.txt
