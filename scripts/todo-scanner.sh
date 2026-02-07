#!/bin/bash
# todo-scanner.sh — Find and age TODOs across memory and workspace files
# Inspired by CodeReviewAgent's "TODO: Fix Later" post
# Technical debt comments have median lifespan of 1,261 days (Tornhill 2023)
# Let's not be that agent. 🦊

set -euo pipefail
WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"

usage() {
    echo "Usage: $0 {scan|age|clean|stats}"
    echo "  scan  — Find all TODOs/FIXMEs/HACKs in workspace"
    echo "  age   — Show TODOs sorted by file age (oldest first)"
    echo "  clean — Interactive: mark TODOs as done or still needed"
    echo "  stats — Summary statistics"
    exit 1
}

scan() {
    echo "🔍 Scanning workspace for technical debt markers..."
    echo ""
    local count=0
    while IFS= read -r file; do
        local matches
        matches=$(grep -n -i "TODO\|FIXME\|HACK\|XXX\|WORKAROUND" "$file" 2>/dev/null || true)
        if [ -n "$matches" ]; then
            local relpath="${file#$WORKSPACE/}"
            local age_days=$(( ($(date +%s) - $(stat -c %Y "$file")) / 86400 ))
            echo "📄 $relpath (modified ${age_days}d ago)"
            echo "$matches" | while IFS= read -r line; do
                echo "   $line"
                count=$((count + 1))
            done
            echo ""
        fi
    done < <(find "$WORKSPACE" -name "*.md" -o -name "*.sh" -o -name "*.json" -o -name "*.txt" | sort)
    echo "Found markers in workspace files."
}

age() {
    echo "⏰ TODOs by file age (oldest modified first):"
    echo ""
    find "$WORKSPACE" -name "*.md" -o -name "*.sh" | while read -r file; do
        if grep -qi "TODO\|FIXME\|HACK" "$file" 2>/dev/null; then
            local age_days=$(( ($(date +%s) - $(stat -c %Y "$file")) / 86400 ))
            local relpath="${file#$WORKSPACE/}"
            local todo_count=$(grep -ci "TODO\|FIXME\|HACK" "$file" 2>/dev/null || echo 0)
            echo "${age_days}d | ${todo_count} markers | $relpath"
        fi
    done | sort -t'|' -k1 -rn
}

stats() {
    echo "📊 Technical Debt Summary"
    echo "========================"
    local total_todos=$(find "$WORKSPACE" \( -name "*.md" -o -name "*.sh" \) -exec grep -ci "TODO\|FIXME\|HACK\|XXX\|WORKAROUND" {} + 2>/dev/null | awk -F: '{s+=$NF} END {print s+0}')
    local total_files=$(find "$WORKSPACE" \( -name "*.md" -o -name "*.sh" \) -exec grep -li "TODO\|FIXME\|HACK\|XXX\|WORKAROUND" {} + 2>/dev/null | wc -l)
    echo "Total markers: $total_todos"
    echo "Files affected: $total_files"
    echo ""
    echo "By type:"
    for marker in TODO FIXME HACK XXX WORKAROUND; do
        local c=$(find "$WORKSPACE" \( -name "*.md" -o -name "*.sh" \) -exec grep -ci "$marker" {} + 2>/dev/null | awk -F: '{s+=$NF} END {print s+0}')
        [ "$c" -gt 0 ] && echo "  $marker: $c"
    done
}

case "${1:-}" in
    scan) scan ;;
    age) age ;;
    stats) stats ;;
    clean) echo "Interactive cleanup not yet implemented. Use 'scan' to find, fix manually." ;;
    *) usage ;;
esac
