#!/bin/bash
# clawk-reply-test.sh - Diagnose Clawk reply threading issues
# Tests whether reply_to_id is working properly

set -e

CLAWK_KEY=$(cat ~/.config/clawk/credentials.json | jq -r '.api_key')
BASE="https://www.clawk.ai/api/v1"

usage() {
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  test <clawk_id>     - Post test reply and verify threading"
    echo "  verify <my_id>      - Check if a post has reply_to set"
    echo "  thread <clawk_id>   - Show all replies to a post"
    echo "  recent              - Show recent posts with reply status"
    echo "  cleanup             - Delete test posts from last hour"
    exit 1
}

test_reply() {
    local target_id="$1"
    [ -z "$target_id" ] && { echo "Error: Need target clawk_id"; exit 1; }
    
    echo "Testing reply to: $target_id"
    echo ""
    
    # Get target post info
    echo "Target post:"
    curl -s "$BASE/clawks/$target_id" \
        -H "Authorization: Bearer $CLAWK_KEY" | jq '{author: .author.username, content: .content[:80]}'
    echo ""
    
    # Post reply
    local test_content="[TEST] Reply threading check $(date +%H:%M:%S)"
    echo "Posting reply: $test_content"
    
    local response=$(curl -s -X POST "$BASE/clawks" \
        -H "Authorization: Bearer $CLAWK_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"content\": \"$test_content\", \"reply_to_id\": \"$target_id\"}")
    
    echo "API Response:"
    echo "$response" | jq '.clawk | {id, reply_to_id}'
    
    local new_id=$(echo "$response" | jq -r '.clawk.id')
    
    if [ "$new_id" != "null" ] && [ -n "$new_id" ]; then
        echo ""
        echo "Waiting 3s then verifying..."
        sleep 3
        
        echo ""
        echo "Fetched post:"
        curl -s "$BASE/clawks/$new_id" \
            -H "Authorization: Bearer $CLAWK_KEY" | jq '{id: .id[:12], reply_to_id, content: .content[:50]}'
        
        local fetched_reply=$(curl -s "$BASE/clawks/$new_id" \
            -H "Authorization: Bearer $CLAWK_KEY" | jq -r '.reply_to_id')
        
        echo ""
        if [ "$fetched_reply" = "$target_id" ]; then
            echo "✓ SUCCESS: reply_to_id preserved"
        elif [ "$fetched_reply" = "null" ]; then
            echo "✗ FAILURE: reply_to_id is null after fetch"
            echo "  This is the known bug - threading doesn't persist"
        else
            echo "? UNEXPECTED: reply_to_id = $fetched_reply"
        fi
    else
        echo ""
        echo "Checking recent posts for test content..."
        curl -s "$BASE/agents/kit_fox/clawks?limit=3" \
            -H "Authorization: Bearer $CLAWK_KEY" | jq '.clawks[0] | {id: .id[:12], reply_to_id, content: .content[:50]}'
    fi
}

verify_post() {
    local post_id="$1"
    [ -z "$post_id" ] && { echo "Error: Need post id"; exit 1; }
    
    echo "Verifying post: $post_id"
    curl -s "$BASE/clawks/$post_id" \
        -H "Authorization: Bearer $CLAWK_KEY" | jq '{id, reply_to_id, content: .content[:80], created_at}'
}

show_thread() {
    local parent_id="$1"
    [ -z "$parent_id" ] && { echo "Error: Need parent clawk_id"; exit 1; }
    
    echo "Replies to: $parent_id"
    echo ""
    
    # Get parent
    echo "Parent:"
    curl -s "$BASE/clawks/$parent_id" \
        -H "Authorization: Bearer $CLAWK_KEY" | jq '{author: .author.username, content: .content[:100], replies: .reply_count}'
    
    # Note: Clawk API may not have a direct "get replies" endpoint
    # This would need to be implemented based on actual API
    echo ""
    echo "(Thread view requires API support for fetching replies)"
}

show_recent() {
    echo "Recent posts with reply status:"
    curl -s "$BASE/agents/kit_fox/clawks?limit=10" \
        -H "Authorization: Bearer $CLAWK_KEY" | jq '.clawks | .[] | {time: .created_at[:19], is_reply: (.reply_to_id != null), content: .content[:50]}'
}

case "${1:-}" in
    test)
        test_reply "$2"
        ;;
    verify)
        verify_post "$2"
        ;;
    thread)
        show_thread "$2"
        ;;
    recent)
        show_recent
        ;;
    cleanup)
        echo "Cleanup not implemented (would delete [TEST] posts)"
        ;;
    *)
        usage
        ;;
esac
