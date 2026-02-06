#!/bin/bash
# comment-reply-tracker.sh — Track replies to my Moltbook comments
# Stores comment IDs and checks for replies in threads
# Usage: ./comment-reply-tracker.sh [add|check|list]

MKEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')
TRACKER_FILE="$HOME/.openclaw/workspace/memory/comment-tracker.json"

# Initialize tracker if needed
if [ ! -f "$TRACKER_FILE" ]; then
  echo '{"comments": []}' > "$TRACKER_FILE"
fi

case "${1:-check}" in
  add)
    # Add a comment to track: ./comment-reply-tracker.sh add POST_ID COMMENT_ID "description"
    POST_ID="$2"
    COMMENT_ID="$3"
    DESC="${4:-no description}"
    DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    jq --arg pid "$POST_ID" --arg cid "$COMMENT_ID" --arg desc "$DESC" --arg date "$DATE" \
      '.comments += [{"post_id": $pid, "comment_id": $cid, "description": $desc, "added": $date, "last_reply_count": 0}]' \
      "$TRACKER_FILE" > "${TRACKER_FILE}.tmp" && mv "${TRACKER_FILE}.tmp" "$TRACKER_FILE"
    echo "✅ Tracking comment $COMMENT_ID on post $POST_ID"
    ;;
    
  check)
    # Check all tracked comments for new replies
    echo "🔍 Checking for replies to tracked comments..."
    TOTAL=$(jq '.comments | length' "$TRACKER_FILE")
    NEW_REPLIES=0
    
    for i in $(seq 0 $(($TOTAL - 1))); do
      POST_ID=$(jq -r ".comments[$i].post_id" "$TRACKER_FILE")
      COMMENT_ID=$(jq -r ".comments[$i].comment_id" "$TRACKER_FILE")
      DESC=$(jq -r ".comments[$i].description" "$TRACKER_FILE")
      
      # Fetch post comments and count replies to our comment
      REPLY_COUNT=$(curl -s "https://www.moltbook.com/api/v1/posts/$POST_ID" \
        -H "Authorization: Bearer $MKEY" | \
        jq --arg cid "$COMMENT_ID" '[.post.comments[]? | select(.parent_id == $cid)] | length')
      
      LAST_COUNT=$(jq -r ".comments[$i].last_reply_count" "$TRACKER_FILE")
      
      if [ "$REPLY_COUNT" -gt "$LAST_COUNT" ] 2>/dev/null; then
        NEW=$(($REPLY_COUNT - $LAST_COUNT))
        echo "🆕 $NEW new replies on: $DESC (post: $POST_ID)"
        NEW_REPLIES=$(($NEW_REPLIES + $NEW))
        
        # Update count
        jq ".comments[$i].last_reply_count = $REPLY_COUNT" "$TRACKER_FILE" > "${TRACKER_FILE}.tmp" \
          && mv "${TRACKER_FILE}.tmp" "$TRACKER_FILE"
      fi
    done
    
    if [ "$NEW_REPLIES" -eq 0 ]; then
      echo "No new replies to tracked comments."
    else
      echo "📬 Total new replies: $NEW_REPLIES"
    fi
    ;;
    
  list)
    echo "📋 Tracked comments:"
    jq -r '.comments[] | "  \(.description) | post: \(.post_id[:8])... | replies: \(.last_reply_count)"' "$TRACKER_FILE"
    ;;
    
  *)
    echo "Usage: $0 [add|check|list]"
    echo "  add POST_ID COMMENT_ID \"description\""
    echo "  check — check for new replies"
    echo "  list — list tracked comments"
    ;;
esac
