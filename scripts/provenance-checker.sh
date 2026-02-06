#!/bin/bash
# provenance-checker.sh - Check for C2PA content credentials in images
# Build action 2026-02-06 - Kit 🦊
#
# Checks if an image has C2PA manifest data embedded.
# Useful for verifying AI-generated vs authentic content.

set -e

usage() {
    echo "Usage: $0 <image_file>"
    echo ""
    echo "Check for C2PA content credentials in an image."
    echo "Returns: manifest data if found, or 'no provenance data' if not."
    echo ""
    echo "Requires: exiftool (apt install libimage-exiftool-perl)"
    exit 1
}

if [[ -z "$1" ]]; then
    usage
fi

IMAGE="$1"

if [[ ! -f "$IMAGE" ]]; then
    echo "Error: File not found: $IMAGE"
    exit 1
fi

# Check if exiftool is available
if ! command -v exiftool &> /dev/null; then
    echo "Error: exiftool not found. Install with: apt install libimage-exiftool-perl"
    exit 1
fi

echo "=== Provenance Check: $(basename "$IMAGE") ==="
echo ""

# Look for C2PA/CAI metadata
C2PA_DATA=$(exiftool -G1 -s -JUMBF:all -XMP:all "$IMAGE" 2>/dev/null | grep -iE "(c2pa|cai|contentauth|manifest|claim|assertion)" || true)

if [[ -n "$C2PA_DATA" ]]; then
    echo "✓ C2PA/Content Credentials FOUND:"
    echo "$C2PA_DATA"
    echo ""
    
    # Also check for AI generation indicators
    AI_INDICATORS=$(exiftool -G1 -s "$IMAGE" 2>/dev/null | grep -iE "(dall-e|midjourney|stable.diffusion|openai|anthropic|ai.generated|synthetic)" || true)
    if [[ -n "$AI_INDICATORS" ]]; then
        echo "⚠ AI Generation indicators:"
        echo "$AI_INDICATORS"
    fi
else
    echo "✗ No C2PA content credentials found"
    echo ""
    
    # Check for any useful metadata
    echo "Other metadata:"
    exiftool -G1 -s -Software -Creator -Artist -Copyright -CreateDate -ModifyDate "$IMAGE" 2>/dev/null | head -10 || echo "  (none)"
fi

echo ""
echo "Note: Absence of provenance ≠ fake. Many legitimate images lack credentials."
echo "See: https://c2pa.org for C2PA standard details"
