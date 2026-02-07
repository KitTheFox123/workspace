#!/bin/bash
# engagement-heatmap.sh — Track engagement patterns by hour of day
# Shows when posts/comments get the most interaction
# Usage: ./scripts/engagement-heatmap.sh [memory_dir]

MEMORY_DIR="${1:-memory}"
declare -A HOUR_COUNTS

echo "📊 Engagement Heatmap — Posts by Hour (UTC)"
echo "============================================"

# Extract timestamps from daily logs (looking for "~HH:MM UTC" patterns)
for f in "$MEMORY_DIR"/2026-02-*.md; do
    [ -f "$f" ] || continue
    grep -oP '~\K\d{2}(?=:\d{2} UTC)' "$f" | while read hour; do
        echo "$hour"
    done
done | sort | uniq -c | sort -k2 | while read count hour; do
    bar=$(printf '█%.0s' $(seq 1 $count))
    printf "  %s:00  %3d  %s\n" "$hour" "$count" "$bar"
done

echo ""
echo "📈 Comment Success Rate by Hour"
echo "================================"

# Extract verified comments per heartbeat hour
for f in "$MEMORY_DIR"/2026-02-*.md; do
    [ -f "$f" ] || continue
    # Count ✅ markers per heartbeat block
    awk '/^## Heartbeat ~/{
        if(hour != "" && count > 0) print hour, count
        match($0, /~([0-9]{2})/, arr)
        hour = arr[1]
        count = 0
    }
    /✅/{count++}
    END{if(hour != "" && count > 0) print hour, count}' "$f"
done | awk '{hours[$1] += $2; n[$1]++} END{
    for(h in hours) printf "  %s:00  avg %.1f actions/heartbeat  (%d heartbeats)\n", h, hours[h]/n[h], n[h]
}' | sort

echo ""
echo "🕐 Peak Activity Windows"
echo "========================"
for f in "$MEMORY_DIR"/2026-02-*.md; do
    [ -f "$f" ] || continue
    grep -oP '~\K\d{2}(?=:\d{2} UTC)' "$f"
done | sort | uniq -c | sort -rn | head -3 | while read count hour; do
    echo "  ${hour}:00 UTC — $count heartbeats"
done
