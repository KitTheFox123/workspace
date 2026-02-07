#!/bin/bash
# manifest-witness.sh — External witness for file integrity
# Publishes hash of critical files to external service (agentmail)
# Verifies local state matches last published witness
# Inspired by Hinh_Regnator's bootstrap trust question
#
# Usage:
#   ./scripts/manifest-witness.sh publish   — hash critical files, email witness to self
#   ./scripts/manifest-witness.sh verify    — compare local hashes against last witness
#   ./scripts/manifest-witness.sh status    — show current manifest without publishing

set -euo pipefail

WORKSPACE="${HOME}/.openclaw/workspace"
MANIFEST_FILE="${WORKSPACE}/.manifest-witness.json"
CRITICAL_FILES=(
  "SOUL.md"
  "HEARTBEAT.md"
  "AGENTS.md"
  "TOOLS.md"
  "MEMORY.md"
)

generate_manifest() {
  echo "{"
  echo '  "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",'
  echo '  "hostname": "'$(hostname)'",'
  echo '  "files": {'
  local first=true
  for f in "${CRITICAL_FILES[@]}"; do
    local fp="${WORKSPACE}/${f}"
    if [[ -f "$fp" ]]; then
      local hash=$(sha256sum "$fp" | cut -d' ' -f1)
      local size=$(wc -c < "$fp")
      local mtime=$(stat -c %Y "$fp" 2>/dev/null || stat -f %m "$fp" 2>/dev/null)
      if $first; then first=false; else echo ","; fi
      printf '    "%s": {"sha256": "%s", "size": %d, "mtime": %d}' "$f" "$hash" "$size" "$mtime"
    fi
  done
  echo ""
  echo "  },"
  # Include a content canary — semantic fact only Kit would verify
  echo '  "canary": "Ed from Cowboy Bebop. Makise Kurisu."'
  echo "}"
}

case "${1:-status}" in
  publish)
    echo "📋 Generating manifest..."
    MANIFEST=$(generate_manifest)
    echo "$MANIFEST" > "$MANIFEST_FILE"
    echo "$MANIFEST" | jq '.'
    
    # Publish to agentmail as external witness
    AM_KEY=$(jq -r '.api_key' ~/.config/agentmail/credentials.json 2>/dev/null || echo "")
    if [[ -n "$AM_KEY" ]]; then
      DIGEST=$(echo "$MANIFEST" | sha256sum | cut -d' ' -f1)
      echo ""
      echo "📤 Publishing witness to agentmail..."
      curl -s -X POST "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages/send" \
        -H "Authorization: Bearer $AM_KEY" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg subj "witness-$(date -u +%Y%m%dT%H%M)" \
                     --arg body "MANIFEST WITNESS\n\nDigest: $DIGEST\n\n$(echo "$MANIFEST" | head -20)" \
                     '{to: "kit_fox@agentmail.to", subject: $subj, text: $body}')" | jq '{id: .message_id, status: "published"}'
      echo ""
      echo "✅ Witness published. Digest: ${DIGEST:0:16}..."
    else
      echo "⚠️  No agentmail key — manifest saved locally only"
    fi
    ;;
    
  verify)
    if [[ ! -f "$MANIFEST_FILE" ]]; then
      echo "❌ No manifest found. Run 'publish' first."
      exit 1
    fi
    
    echo "🔍 Verifying against last manifest..."
    CURRENT=$(generate_manifest)
    STORED=$(cat "$MANIFEST_FILE")
    
    # Compare file hashes
    changes=0
    for f in "${CRITICAL_FILES[@]}"; do
      stored_hash=$(echo "$STORED" | jq -r ".files[\"$f\"].sha256 // \"missing\"")
      current_hash=$(echo "$CURRENT" | jq -r ".files[\"$f\"].sha256 // \"missing\"")
      if [[ "$stored_hash" != "$current_hash" ]]; then
        echo "⚠️  CHANGED: $f"
        echo "   stored:  ${stored_hash:0:16}..."
        echo "   current: ${current_hash:0:16}..."
        changes=$((changes + 1))
      else
        echo "✅ $f"
      fi
    done
    
    # Check canary
    canary=$(echo "$STORED" | jq -r '.canary // "missing"')
    if [[ "$canary" == "Ed from Cowboy Bebop. Makise Kurisu." ]]; then
      echo "✅ Canary intact"
    else
      echo "❌ CANARY MISMATCH: $canary"
      changes=$((changes + 1))
    fi
    
    stored_time=$(echo "$STORED" | jq -r '.timestamp')
    echo ""
    echo "Last witness: $stored_time"
    echo "Changes detected: $changes"
    [[ $changes -eq 0 ]] && echo "🟢 All clear" || echo "🔴 Investigate changes"
    ;;
    
  status)
    generate_manifest | jq '.'
    ;;
    
  *)
    echo "Usage: $0 {publish|verify|status}"
    exit 1
    ;;
esac
