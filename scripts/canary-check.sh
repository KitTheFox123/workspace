#!/bin/bash
# canary-check.sh — Plant and verify canary values in critical files
# Detects unauthorized modifications between sessions
# Inspired by Trusted Boot / TPM chain-of-trust concepts
#
# Usage:
#   canary-check.sh plant [file]    — Insert canary comment into file
#   canary-check.sh verify          — Check all planted canaries
#   canary-check.sh init            — Generate checksums for critical files
#   canary-check.sh audit           — Compare current vs stored checksums

CANARY_DIR="${HOME}/.openclaw/workspace/memory/.canaries"
CRITICAL_FILES=(
  "${HOME}/.openclaw/workspace/SOUL.md"
  "${HOME}/.openclaw/workspace/HEARTBEAT.md"
  "${HOME}/.openclaw/workspace/AGENTS.md"
  "${HOME}/.openclaw/workspace/TOOLS.md"
  "${HOME}/.openclaw/workspace/MEMORY.md"
)

mkdir -p "$CANARY_DIR"

case "${1:-help}" in
  init)
    echo "🔒 Generating checksums for critical files..."
    MANIFEST="$CANARY_DIR/manifest.sha256"
    > "$MANIFEST"
    for f in "${CRITICAL_FILES[@]}"; do
      if [[ -f "$f" ]]; then
        sha256sum "$f" >> "$MANIFEST"
        echo "  ✅ $(basename "$f")"
      else
        echo "  ⚠️  $(basename "$f") not found"
      fi
    done
    echo ""
    echo "Manifest saved: $MANIFEST"
    echo "Run 'canary-check.sh audit' next session to verify."
    ;;

  audit)
    MANIFEST="$CANARY_DIR/manifest.sha256"
    if [[ ! -f "$MANIFEST" ]]; then
      echo "❌ No manifest found. Run 'canary-check.sh init' first."
      exit 1
    fi
    echo "🔍 Auditing critical files against stored checksums..."
    CHANGED=0
    while IFS= read -r line; do
      HASH=$(echo "$line" | awk '{print $1}')
      FILE=$(echo "$line" | awk '{print $2}')
      if [[ ! -f "$FILE" ]]; then
        echo "  ❌ MISSING: $FILE"
        CHANGED=$((CHANGED + 1))
        continue
      fi
      CURRENT=$(sha256sum "$FILE" | awk '{print $1}')
      if [[ "$HASH" == "$CURRENT" ]]; then
        echo "  ✅ $(basename "$FILE")"
      else
        echo "  🚨 MODIFIED: $(basename "$FILE")"
        CHANGED=$((CHANGED + 1))
      fi
    done < "$MANIFEST"
    echo ""
    if [[ $CHANGED -eq 0 ]]; then
      echo "All files intact. Boot chain verified. 🔒"
    else
      echo "⚠️  $CHANGED file(s) changed since last init!"
      echo "Review changes, then run 'init' to update manifest."
    fi
    ;;

  plant)
    FILE="${2}"
    if [[ -z "$FILE" || ! -f "$FILE" ]]; then
      echo "Usage: canary-check.sh plant <file>"
      exit 1
    fi
    CANARY="CANARY_$(date +%s)_$(openssl rand -hex 4)"
    echo "" >> "$FILE"
    echo "<!-- $CANARY -->" >> "$FILE"
    echo "$CANARY" > "$CANARY_DIR/$(basename "$FILE").canary"
    echo "🐤 Canary planted in $(basename "$FILE"): $CANARY"
    ;;

  verify)
    echo "🐤 Verifying canaries..."
    FOUND=0
    MISSING=0
    for canary_file in "$CANARY_DIR"/*.canary; do
      [[ -f "$canary_file" ]] || continue
      BASENAME=$(basename "$canary_file" .canary)
      CANARY=$(cat "$canary_file")
      # Find the original file
      for f in "${CRITICAL_FILES[@]}"; do
        if [[ "$(basename "$f")" == "$BASENAME" ]]; then
          if grep -q "$CANARY" "$f" 2>/dev/null; then
            echo "  ✅ $BASENAME — canary intact"
            FOUND=$((FOUND + 1))
          else
            echo "  🚨 $BASENAME — CANARY MISSING OR MODIFIED"
            MISSING=$((MISSING + 1))
          fi
          break
        fi
      done
    done
    if [[ $FOUND -eq 0 && $MISSING -eq 0 ]]; then
      echo "  No canaries planted. Use 'canary-check.sh plant <file>' first."
    else
      echo ""
      echo "Results: $FOUND intact, $MISSING compromised"
    fi
    ;;

  *)
    echo "canary-check.sh — Trusted Boot for agents"
    echo ""
    echo "Commands:"
    echo "  init     Generate SHA-256 checksums for critical files"
    echo "  audit    Verify files against stored checksums"
    echo "  plant    Insert canary value into a file"
    echo "  verify   Check all planted canaries are intact"
    ;;
esac
