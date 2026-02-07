#!/bin/bash
# papertrail.sh — Track information provenance across memory files
# Shows how a concept/term spread through daily logs over time
# Usage: ./scripts/papertrail.sh <term> [days_back]
#
# Like tracing paper-making from China to Europe, but for ideas through memory files.

set -euo pipefail

TERM="${1:?Usage: papertrail.sh <term> [days_back]}"
DAYS_BACK="${2:-30}"
MEMORY_DIR="memory"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}📜 Papertrail: tracking '${TERM}' across memory${NC}"
echo "---"

# Search daily logs
FOUND=0
for f in $(ls -r "$MEMORY_DIR"/2026-*.md 2>/dev/null | head -"$DAYS_BACK"); do
    DATE=$(basename "$f" .md)
    MATCHES=$(grep -inc "$TERM" "$f" 2>/dev/null || true)
    if [ "$MATCHES" -gt 0 ]; then
        FOUND=$((FOUND + MATCHES))
        echo -e "${GREEN}$DATE${NC} — ${YELLOW}${MATCHES}${NC} mentions"
        # Show first 3 context lines
        grep -in "$TERM" "$f" 2>/dev/null | head -3 | while IFS= read -r line; do
            LINENUM=$(echo "$line" | cut -d: -f1)
            CONTEXT=$(echo "$line" | cut -d: -f2- | sed 's/^[[:space:]]*//' | cut -c1-120)
            echo "  L${LINENUM}: ${CONTEXT}"
        done
        echo ""
    fi
done

# Search knowledge files
echo -e "${CYAN}--- Knowledge files ---${NC}"
for f in knowledge/*.md; do
    [ -f "$f" ] || continue
    MATCHES=$(grep -inc "$TERM" "$f" 2>/dev/null || true)
    if [ "$MATCHES" -gt 0 ]; then
        FOUND=$((FOUND + MATCHES))
        echo -e "${GREEN}$(basename "$f")${NC} — ${YELLOW}${MATCHES}${NC} mentions"
        grep -in "$TERM" "$f" 2>/dev/null | head -2 | while IFS= read -r line; do
            echo "  $(echo "$line" | cut -d: -f2- | sed 's/^[[:space:]]*//' | cut -c1-120)"
        done
        echo ""
    fi
done

# Search MEMORY.md
if grep -qic "$TERM" MEMORY.md 2>/dev/null; then
    MATCHES=$(grep -ic "$TERM" MEMORY.md)
    FOUND=$((FOUND + MATCHES))
    echo -e "${GREEN}MEMORY.md${NC} — ${YELLOW}${MATCHES}${NC} mentions (graduated to long-term memory)"
fi

echo "---"
echo -e "Total: ${YELLOW}${FOUND}${NC} mentions of '${TERM}'"

# Timeline visualization
echo ""
echo -e "${CYAN}Timeline:${NC}"
for f in $(ls "$MEMORY_DIR"/2026-*.md 2>/dev/null | sort); do
    DATE=$(basename "$f" .md | sed 's/2026-//')
    COUNT=$(grep -ic "$TERM" "$f" 2>/dev/null || true); COUNT=${COUNT:-0}
    if [ "$COUNT" -gt 0 ]; then
        BAR=$(printf '█%.0s' $(seq 1 $(( COUNT > 20 ? 20 : COUNT ))))
        printf "  %s %s %s\n" "$DATE" "$BAR" "($COUNT)"
    else
        printf "  %s ·\n" "$DATE"
    fi
done
