#!/bin/bash
# topic-coverage.sh — Quick one-liner summary of topic coverage
# Usage: ./scripts/topic-coverage.sh
# Output: Single line suitable for Telegram updates

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Try topic-suggest.py --stats first
if [ -f "$SCRIPT_DIR/topic-suggest.py" ]; then
    STATS=$(python3 "$SCRIPT_DIR/topic-suggest.py" --stats 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$STATS" ]; then
        echo "$STATS"
        exit 0
    fi
fi

# Fallback: parse topic-history.json directly
TOPIC_FILE="$SCRIPT_DIR/../memory/topic-history.json"
if [ ! -f "$TOPIC_FILE" ]; then
    echo "No topic-history.json found"
    exit 1
fi

python3 -c "
import json, sys
with open('$TOPIC_FILE') as f:
    data = json.load(f)
topics = data.get('topics', [])
cats = {}
for t in topics:
    if isinstance(t, dict):
        c = t.get('category', 'unknown')
        cats[c] = cats.get(c, 0) + 1
named = {k:v for k,v in cats.items() if k != 'unknown'}
total = len(topics)
uncategorized = cats.get('unknown', 0)
print(f'📊 {total} topics | {len(named)} categories | Top: {max(named, key=named.get)}({named[max(named, key=named.get)]}) | Uncategorized: {uncategorized}')
"
