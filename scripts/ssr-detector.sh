#!/usr/bin/env bash
# ssr-detector.sh — Check if a URL serves SSR content or requires JS rendering
# Inspired by Qinghua's SSR vs Playwright post
# Usage: ./scripts/ssr-detector.sh <url> [selector]

set -euo pipefail

URL="${1:-}"
SELECTOR="${2:-}"  # Optional: CSS selector or text to look for

if [[ -z "$URL" ]]; then
    echo "Usage: $0 <url> [text-to-find]"
    echo ""
    echo "Checks if a URL returns meaningful content via curl (SSR)"
    echo "or requires JavaScript rendering (CSR/SPA)."
    echo ""
    echo "Examples:"
    echo "  $0 https://example.com"
    echo "  $0 https://news.ycombinator.com 'Hacker News'"
    exit 1
fi

echo "🔍 Checking: $URL"
echo "---"

# Fetch with curl (no JS)
RESPONSE=$(curl -sL -o /dev/null -w '%{http_code}|%{size_download}|%{time_total}' \
    -H "User-Agent: Mozilla/5.0 (compatible; SSRDetector/1.0)" \
    "$URL" 2>/dev/null)

HTTP_CODE=$(echo "$RESPONSE" | cut -d'|' -f1)
SIZE=$(echo "$RESPONSE" | cut -d'|' -f2)
TIME=$(echo "$RESPONSE" | cut -d'|' -f3)

echo "HTTP Status: $HTTP_CODE"
echo "Response Size: ${SIZE} bytes"
echo "Response Time: ${TIME}s"

if [[ "$HTTP_CODE" != "200" ]]; then
    echo "❌ Non-200 response — site may block curl or require auth"
    exit 1
fi

# Fetch actual content for analysis
CONTENT=$(curl -sL -H "User-Agent: Mozilla/5.0 (compatible; SSRDetector/1.0)" "$URL" 2>/dev/null)

# Check for SSR indicators
SSR_SCORE=0
CSR_SCORE=0
INDICATORS=""

# Check content length (SSR typically >5KB for real pages)
if [[ "$SIZE" -gt 5000 ]]; then
    SSR_SCORE=$((SSR_SCORE + 2))
    INDICATORS="$INDICATORS\n  ✅ Substantial HTML content (${SIZE} bytes)"
else
    CSR_SCORE=$((CSR_SCORE + 2))
    INDICATORS="$INDICATORS\n  ⚠️  Minimal HTML (${SIZE} bytes) — likely shell page"
fi

# Check for common CSR patterns (empty body, loading spinners)
if echo "$CONTENT" | grep -qi '<div id="root"></div>\|<div id="app"></div>\|<div id="__next"></div>'; then
    CSR_SCORE=$((CSR_SCORE + 3))
    INDICATORS="$INDICATORS\n  ⚠️  Empty root div found (React/Vue/Next shell)"
fi

if echo "$CONTENT" | grep -qi 'loading\.\.\.\|spinner\|skeleton'; then
    CSR_SCORE=$((CSR_SCORE + 1))
    INDICATORS="$INDICATORS\n  ⚠️  Loading/spinner text found"
fi

# Check for SSR frameworks
if echo "$CONTENT" | grep -qi 'data-reactroot\|__NEXT_DATA__\|__NUXT__\|data-server-rendered'; then
    SSR_SCORE=$((SSR_SCORE + 3))
    INDICATORS="$INDICATORS\n  ✅ SSR framework markers found (Next.js/Nuxt/etc)"
fi

# Check for meaningful text content (not just JS bundles)
TEXT_CHARS=$(echo "$CONTENT" | sed 's/<[^>]*>//g' | tr -s '[:space:]' | wc -c)
if [[ "$TEXT_CHARS" -gt 1000 ]]; then
    SSR_SCORE=$((SSR_SCORE + 3))
    INDICATORS="$INDICATORS\n  ✅ Rich text content: ~${TEXT_CHARS} chars after stripping HTML"
else
    CSR_SCORE=$((CSR_SCORE + 2))
    INDICATORS="$INDICATORS\n  ⚠️  Minimal text content: ~${TEXT_CHARS} chars"
fi

# Check for large JS bundles (CSR indicator)
JS_COUNT=$(echo "$CONTENT" | grep -co '<script[^>]*src=' || true)
if [[ "$JS_COUNT" -gt 5 ]]; then
    CSR_SCORE=$((CSR_SCORE + 1))
    INDICATORS="$INDICATORS\n  ⚠️  ${JS_COUNT} external script tags (JS-heavy)"
fi

# Check for selector/text if provided
if [[ -n "$SELECTOR" ]]; then
    if echo "$CONTENT" | grep -qi "$SELECTOR"; then
        SSR_SCORE=$((SSR_SCORE + 5))
        INDICATORS="$INDICATORS\n  ✅ Target text '$SELECTOR' FOUND in curl response"
    else
        CSR_SCORE=$((CSR_SCORE + 5))
        INDICATORS="$INDICATORS\n  ❌ Target text '$SELECTOR' NOT found — needs JS rendering"
    fi
fi

echo ""
echo "Analysis:"
echo -e "$INDICATORS"
echo ""
echo "SSR Score: $SSR_SCORE | CSR Score: $CSR_SCORE"

if [[ "$SSR_SCORE" -gt "$CSR_SCORE" ]]; then
    echo ""
    echo "📗 VERDICT: Likely SSR — use curl/aiohttp/requests (fast path)"
    echo "   Estimated speedup vs Playwright: 10-30x"
elif [[ "$CSR_SCORE" -gt "$SSR_SCORE" ]]; then
    echo ""
    echo "📕 VERDICT: Likely CSR/SPA — needs Playwright/Selenium (slow path)"
    echo "   Check if an API endpoint exists before committing to browser automation"
else
    echo ""
    echo "📙 VERDICT: Unclear — hybrid page. Test both paths."
fi
