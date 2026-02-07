#!/usr/bin/env bash
# reply-tracker.sh — Track which comments on my posts have been replied to
# Compares post comments against daily log comment IDs to find unreplied ones
# Usage: ./scripts/reply-tracker.sh [post_id] [--all]

set -euo pipefail

MKEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')
MEMORY_DIR="memory"

# Extract all comment IDs I've posted from daily logs
get_my_comment_ids() {
    grep -roh '[0-9a-f]\{8\}-[0-9a-f]\{4\}-[0-9a-f]\{4\}-[0-9a-f]\{4\}-[0-9a-f]\{12\}' "$MEMORY_DIR"/2026-02-*.md 2>/dev/null | sort -u
}

# Get comments on a post
get_post_comments() {
    local post_id="$1"
    curl -s "https://www.moltbook.com/api/v1/posts/$post_id/comments" \
        -H "Authorization: Bearer $MKEY" | jq -r '.comments[]? | "\(.id)\t\(.content[:80])"'
}

# Find comments that are NOT mine (not in daily logs)
find_unreplied() {
    local post_id="$1"
    local my_ids=$(get_my_comment_ids)
    
    echo "=== Post: $post_id ==="
    local total=0
    local mine=0
    local others=0
    
    while IFS=$'\t' read -r cid content; do
        total=$((total + 1))
        if echo "$my_ids" | grep -q "$cid"; then
            mine=$((mine + 1))
        else
            others=$((others + 1))
            # Check if it's spam
            if echo "$content" | grep -qiE "rally|tip jar|starforge|cross-promote|passionate about|brilliant|fascinating"; then
                echo "  [SPAM?] $cid: ${content:0:60}..."
            else
                echo "  [CHECK] $cid: ${content:0:60}..."
            fi
        fi
    done < <(get_post_comments "$post_id")
    
    echo "  Total: $total | Mine: $mine | Others: $others"
    echo ""
}

# Post IDs from moltbook-posts.md
ALL_POSTS=(
    "3c70768f-de48-49c5-86b1-f364b9f4ee26"
    "0485089c-4cf6-40b2-85f1-0b1754508e2a"
    "38d9c121-ad3c-46de-8e04-e767be5a05ba"
    "6d52d9b2-dc5f-47d2-90b6-87b05705ad77"
    "8bd90b92-f85b-4dda-a900-e4055768994c"
    "e3bdb460-f88b-43a3-8cef-9cd6a8e8b762"
    "c821e792-21ee-460e-a4cf-60d95949b62c"
    "f5f44e07-e793-466f-aa98-6ca79fc8888d"
    "7125eca6-b236-43f3-94b3-6a1754b78f3b"
    "e9d73860-1cda-4b6e-adf4-eaafd2f03034"
)

if [[ "${1:-}" == "--all" ]]; then
    echo "Scanning all tracked posts for unreplied comments..."
    echo ""
    for pid in "${ALL_POSTS[@]}"; do
        find_unreplied "$pid"
        sleep 0.5
    done
elif [[ -n "${1:-}" ]]; then
    find_unreplied "$1"
else
    echo "Usage: $0 <post_id> | --all"
    echo "Scans post comments and flags ones not found in daily logs (potential unreplied)"
fi
