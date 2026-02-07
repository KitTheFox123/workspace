#!/bin/bash
# chain-verify.sh — Attestation chain verifier for agent trust networks
# Validates chains of signed attestations (isnad-inspired)
# Build action for 2026-02-07 ~13:50 heartbeat

set -euo pipefail

CHAINS_DIR="${CHAINS_DIR:-.chains}"
MANIFEST="$CHAINS_DIR/chain.jsonl"

usage() {
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  init                    Initialize chain directory"
    echo "  attest <claim> <source> Add an attestation to the chain"
    echo "  verify                  Verify chain integrity"
    echo "  trace <claim>           Trace provenance of a claim"
    echo "  audit                   Show chain health metrics"
    echo "  export                  Export chain as readable report"
}

init_chain() {
    mkdir -p "$CHAINS_DIR"
    echo '{"version":1,"created":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","agent":"Kit_Fox"}' > "$CHAINS_DIR/meta.json"
    touch "$MANIFEST"
    echo "✅ Chain initialized at $CHAINS_DIR"
}

attest() {
    local claim="$1"
    local source="$2"
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local prev_hash="null"
    
    # Get previous entry hash for chaining
    if [ -s "$MANIFEST" ]; then
        prev_hash=$(tail -1 "$MANIFEST" | sha256sum | cut -d' ' -f1)
    fi
    
    # Create attestation entry
    local content_hash=$(echo -n "$claim" | sha256sum | cut -d' ' -f1)
    local entry=$(jq -cn \
        --arg ts "$timestamp" \
        --arg claim "$claim" \
        --arg source "$source" \
        --arg hash "$content_hash" \
        --arg prev "$prev_hash" \
        '{timestamp: $ts, claim: $claim, source: $source, content_hash: $hash, prev_hash: $prev}')
    
    echo "$entry" >> "$MANIFEST"
    local entry_hash=$(echo "$entry" | sha256sum | cut -d' ' -f1)
    echo "✅ Attestation added (hash: ${entry_hash:0:12}...)"
    echo "   Claim: $claim"
    echo "   Source: $source"
    echo "   Chain depth: $(wc -l < "$MANIFEST")"
}

verify_chain() {
    if [ ! -s "$MANIFEST" ]; then
        echo "⚠️ Empty chain"
        return 0
    fi
    
    local prev_hash="null"
    local line_num=0
    local errors=0
    local total=0
    
    while IFS= read -r line; do
        line_num=$((line_num + 1))
        total=$((total + 1))
        
        # Check prev_hash matches
        local stored_prev=$(echo "$line" | jq -r '.prev_hash')
        if [ "$stored_prev" != "$prev_hash" ]; then
            echo "❌ Chain break at entry $line_num"
            echo "   Expected prev: ${prev_hash:0:16}..."
            echo "   Got: ${stored_prev:0:16}..."
            errors=$((errors + 1))
        fi
        
        # Verify content hash
        local stored_hash=$(echo "$line" | jq -r '.content_hash')
        local claim=$(echo "$line" | jq -r '.claim')
        local computed_hash=$(echo -n "$claim" | sha256sum | cut -d' ' -f1)
        if [ "$stored_hash" != "$computed_hash" ]; then
            echo "❌ Content tampered at entry $line_num"
            errors=$((errors + 1))
        fi
        
        prev_hash=$(echo "$line" | sha256sum | cut -d' ' -f1)
    done < "$MANIFEST"
    
    if [ $errors -eq 0 ]; then
        echo "✅ Chain verified: $total entries, no breaks, no tampering"
    else
        echo "⚠️ Chain has $errors issues in $total entries"
    fi
    return $errors
}

trace_claim() {
    local query="$1"
    echo "🔍 Tracing: $query"
    echo "---"
    grep -i "$query" "$MANIFEST" 2>/dev/null | while IFS= read -r line; do
        local ts=$(echo "$line" | jq -r '.timestamp')
        local source=$(echo "$line" | jq -r '.source')
        local claim=$(echo "$line" | jq -r '.claim')
        local hash=$(echo "$line" | jq -r '.content_hash')
        echo "[$ts] via $source"
        echo "  Claim: $claim"
        echo "  Hash: ${hash:0:16}..."
        echo ""
    done
}

audit_chain() {
    if [ ! -s "$MANIFEST" ]; then
        echo "Empty chain"
        return
    fi
    
    local total=$(wc -l < "$MANIFEST")
    local sources=$(jq -r '.source' "$MANIFEST" | sort -u | wc -l)
    local first=$(head -1 "$MANIFEST" | jq -r '.timestamp')
    local last=$(tail -1 "$MANIFEST" | jq -r '.timestamp')
    local unique_claims=$(jq -r '.content_hash' "$MANIFEST" | sort -u | wc -l)
    
    echo "📊 Chain Audit"
    echo "  Total attestations: $total"
    echo "  Unique claims: $unique_claims"
    echo "  Unique sources: $sources"
    echo "  First entry: $first"
    echo "  Latest entry: $last"
    echo ""
    echo "  Sources:"
    jq -r '.source' "$MANIFEST" | sort | uniq -c | sort -rn | while read count source; do
        echo "    $source: $count attestations"
    done
    echo ""
    echo "  Diversity ratio: $(echo "scale=2; $sources / $total" | bc) (sources/attestations)"
    
    # Verify integrity
    echo ""
    verify_chain
}

export_chain() {
    echo "# Attestation Chain Report"
    echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo ""
    local n=0
    while IFS= read -r line; do
        n=$((n + 1))
        local ts=$(echo "$line" | jq -r '.timestamp')
        local source=$(echo "$line" | jq -r '.source')
        local claim=$(echo "$line" | jq -r '.claim')
        echo "## Entry $n — $ts"
        echo "- **Source:** $source"
        echo "- **Claim:** $claim"
        echo ""
    done < "$MANIFEST"
}

case "${1:-}" in
    init) init_chain ;;
    attest) attest "${2:?claim required}" "${3:?source required}" ;;
    verify) verify_chain ;;
    trace) trace_claim "${2:?query required}" ;;
    audit) audit_chain ;;
    export) export_chain ;;
    *) usage ;;
esac
