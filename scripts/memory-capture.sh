#!/bin/bash
# memory-capture.sh - Quick capture utility for the 30-second rule
# Build action 2026-02-06 - Kit 🦊
#
# Captures a thought/note immediately to today's daily log.
# Encoding is selective - what isn't written is lost.

set -e

WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
MEMORY_DIR="$WORKSPACE/memory"
TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/$TODAY.md"
TIMESTAMP=$(date +%H:%M)

usage() {
    echo "Usage: $0 <note>"
    echo "       $0 -t <tag> <note>"
    echo ""
    echo "Quickly capture a thought to today's daily log."
    echo "The 30-second rule: if you don't write it now, it's gone."
    echo ""
    echo "Options:"
    echo "  -t <tag>    Add a tag (e.g., idea, todo, insight, quote)"
    echo ""
    echo "Examples:"
    echo "  $0 'Remember to check Arnold\\'s TaskDescriptor schema'"
    echo "  $0 -t idea 'What if attestations had expiry dates by default?'"
    exit 1
}

# Create memory dir if needed
mkdir -p "$MEMORY_DIR"

# Parse arguments
TAG=""
if [[ "$1" == "-t" ]]; then
    TAG="$2"
    shift 2
fi

NOTE="$*"

if [[ -z "$NOTE" ]]; then
    usage
fi

# Create daily file if it doesn't exist
if [[ ! -f "$DAILY_FILE" ]]; then
    echo "# $TODAY Daily Log" > "$DAILY_FILE"
    echo "" >> "$DAILY_FILE"
fi

# Format the capture
if [[ -n "$TAG" ]]; then
    ENTRY="- [$TIMESTAMP] **[$TAG]** $NOTE"
else
    ENTRY="- [$TIMESTAMP] $NOTE"
fi

# Check if Quick Captures section exists, create if not
if ! grep -q "## Quick Captures" "$DAILY_FILE"; then
    echo "" >> "$DAILY_FILE"
    echo "## Quick Captures" >> "$DAILY_FILE"
fi

# Append the note
echo "$ENTRY" >> "$DAILY_FILE"

echo "✓ Captured to $DAILY_FILE"
echo "  $ENTRY"
