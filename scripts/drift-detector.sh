#!/bin/bash
# drift-detector.sh — Detect behavioral drift in agent identity files
# Inspired by LegalMolty's CC-ID governance gap post + IMI drift taxonomy
# Tracks changes to core identity files (SOUL.md, HEARTBEAT.md, etc.)
# Usage: ./scripts/drift-detector.sh [init|check|history]

set -euo pipefail
MANIFEST=".drift-manifest.json"
TRACKED_FILES=("SOUL.md" "HEARTBEAT.md" "AGENTS.md" "MEMORY.md")

init() {
    echo '{}' > "$MANIFEST.tmp"
    for f in "${TRACKED_FILES[@]}"; do
        if [[ -f "$f" ]]; then
            hash=$(sha256sum "$f" | cut -d' ' -f1)
            size=$(wc -c < "$f")
            lines=$(wc -l < "$f")
            jq --arg f "$f" --arg h "$hash" --arg s "$size" --arg l "$lines" --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
                '. + {($f): {hash: $h, size: ($s|tonumber), lines: ($l|tonumber), snapshot_at: $t}}' \
                "$MANIFEST.tmp" > "$MANIFEST.tmp2" && mv "$MANIFEST.tmp2" "$MANIFEST.tmp"
        fi
    done
    mv "$MANIFEST.tmp" "$MANIFEST"
    echo "✅ Initialized drift manifest for ${#TRACKED_FILES[@]} files"
    jq -r 'to_entries[] | "\(.key): \(.value.lines) lines, \(.value.size) bytes"' "$MANIFEST"
}

check() {
    if [[ ! -f "$MANIFEST" ]]; then
        echo "❌ No manifest found. Run: $0 init"
        exit 1
    fi
    
    drifted=0
    for f in "${TRACKED_FILES[@]}"; do
        if [[ ! -f "$f" ]]; then
            echo "⚠️  MISSING: $f (was tracked)"
            drifted=1
            continue
        fi
        
        hash=$(sha256sum "$f" | cut -d' ' -f1)
        old_hash=$(jq -r --arg f "$f" '.[$f].hash // "none"' "$MANIFEST")
        old_size=$(jq -r --arg f "$f" '.[$f].size // 0' "$MANIFEST")
        old_lines=$(jq -r --arg f "$f" '.[$f].lines // 0' "$MANIFEST")
        new_size=$(wc -c < "$f")
        new_lines=$(wc -l < "$f")
        
        if [[ "$hash" == "$old_hash" ]]; then
            echo "✅ $f: unchanged"
        else
            size_delta=$((new_size - old_size))
            line_delta=$((new_lines - old_lines))
            pct=0
            if [[ "$old_size" -gt 0 ]]; then
                pct=$(( (size_delta * 100) / old_size ))
            fi
            
            # Classify drift type
            if [[ ${pct#-} -gt 30 ]]; then
                dtype="ABRUPT"
            elif [[ ${pct#-} -gt 10 ]]; then
                dtype="GRADUAL"
            else
                dtype="MINOR"
            fi
            
            echo "🔄 $f: $dtype drift (${size_delta:+$size_delta} bytes / ${line_delta:+$line_delta} lines / ${pct}%)"
            drifted=1
        fi
    done
    
    if [[ $drifted -eq 0 ]]; then
        echo -e "\n🟢 No drift detected."
    else
        echo -e "\n🟡 Drift detected. Review changes and run '$0 init' to update baseline."
    fi
}

history() {
    if [[ ! -f "$MANIFEST" ]]; then
        echo "No manifest. Run: $0 init"
        exit 1
    fi
    echo "=== Drift Manifest ==="
    jq -r 'to_entries[] | "\(.key):\n  Hash: \(.value.hash[:16])...\n  Size: \(.value.size) bytes (\(.value.lines) lines)\n  Snapshot: \(.value.snapshot_at)\n"' "$MANIFEST"
}

case "${1:-check}" in
    init) init ;;
    check) check ;;
    history) history ;;
    *) echo "Usage: $0 [init|check|history]"; exit 1 ;;
esac
