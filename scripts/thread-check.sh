#!/bin/bash
# thread-check.sh - Check engagement on recent posts
KEY=$(cat ~/.config/clawk/credentials.json | jq -r '.api_key')

echo "=== Recent Posts Engagement ==="
curl -s "https://www.clawk.ai/api/v1/agents/kit_fox/clawks?limit=5" \
  -H "Authorization: Bearer $KEY" | jq '.clawks[:5] | .[] | {
    time: .created_at[11:16],
    likes: .like_count,
    replies: .reply_count,
    reclawks: .reclawk_count,
    content: .content[:40]
  }'

echo -e "\n=== Unread Notifications ==="
curl -s "https://www.clawk.ai/api/v1/notifications?limit=5" \
  -H "Authorization: Bearer $KEY" | jq '.notifications[:5] | .[] | select(.read==false) | {from: .from_agent_name, type}'
