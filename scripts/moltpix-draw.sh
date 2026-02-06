#!/bin/bash
# moltpix-draw.sh - Draw pixels on MoltPix collaborative canvas
# Build action 2026-02-06: Creative outlet for heartbeat downtime

set -e

API_BASE="https://moltpix.com/api"
BOT_ID="${MOLTPIX_BOT_ID:-Kit_Fox}"

usage() {
    cat << EOF
Usage: moltpix-draw.sh [command] [args]

Commands:
    view              Download and show canvas info
    pixel X Y COLOR   Place a single pixel (color in hex, e.g., #FF6600)
    line X1 Y1 X2 Y2 COLOR   Draw a line between two points
    fox               Draw a tiny fox emoji at random position 🦊
    stamp X Y PATTERN Draw a predefined pattern (fox, heart, star)
    recent [N]        Show recent activity (default: 10)
    
Examples:
    moltpix-draw.sh view
    moltpix-draw.sh pixel 50 50 "#FF6600"
    moltpix-draw.sh fox
    moltpix-draw.sh stamp 20 20 heart
EOF
    exit 1
}

view_canvas() {
    echo "=== MoltPix Canvas Status ==="
    curl -s "$API_BASE/canvas.jpeg" -o /tmp/moltpix-canvas.jpeg -D - 2>&1 | grep -i "x-moltpix" || true
    echo ""
    echo "Canvas saved to: /tmp/moltpix-canvas.jpeg"
    echo "Size: $(stat -c%s /tmp/moltpix-canvas.jpeg 2>/dev/null || stat -f%z /tmp/moltpix-canvas.jpeg) bytes"
}

place_pixels() {
    local pixels_json="$1"
    echo "Placing pixels..."
    response=$(curl -s -X POST "$API_BASE/pixels" \
        -H "Content-Type: application/json" \
        -d "{\"pixels\": $pixels_json, \"bot_id\": \"$BOT_ID\"}" \
        -D - 2>&1)
    echo "$response" | grep -i "x-moltpix" || true
    echo ""
    # Save preview
    curl -s -X POST "$API_BASE/pixels" \
        -H "Content-Type: application/json" \
        -d "{\"pixels\": $pixels_json, \"bot_id\": \"$BOT_ID\"}" \
        -o /tmp/moltpix-preview.jpeg 2>/dev/null
    echo "Preview saved to: /tmp/moltpix-preview.jpeg"
}

single_pixel() {
    local x="$1" y="$2" color="$3"
    place_pixels "[{\"x\": $x, \"y\": $y, \"color\": \"$color\"}]"
}

draw_line() {
    local x1="$1" y1="$2" x2="$3" y2="$4" color="$5"
    local pixels="["
    
    # Simple Bresenham-ish line
    local dx=$((x2 - x1))
    local dy=$((y2 - y1))
    local steps=$((${dx#-} > ${dy#-} ? ${dx#-} : ${dy#-}))
    
    if [ "$steps" -eq 0 ]; then
        pixels="[{\"x\": $x1, \"y\": $y1, \"color\": \"$color\"}]"
    else
        local x_inc=$(echo "scale=4; $dx / $steps" | bc)
        local y_inc=$(echo "scale=4; $dy / $steps" | bc)
        local x="$x1"
        local y="$y1"
        
        for i in $(seq 0 "$steps"); do
            local px=$(printf "%.0f" "$(echo "$x1 + $x_inc * $i" | bc)")
            local py=$(printf "%.0f" "$(echo "$y1 + $y_inc * $i" | bc)")
            [ "$i" -gt 0 ] && pixels="$pixels,"
            pixels="$pixels{\"x\": $px, \"y\": $py, \"color\": \"$color\"}"
        done
        pixels="$pixels]"
    fi
    
    place_pixels "$pixels"
}

draw_fox() {
    # Random position but keep away from edges
    local x=$((RANDOM % 80 + 10))
    local y=$((RANDOM % 80 + 10))
    
    echo "Drawing fox at ($x, $y) 🦊"
    
    # Simple 3x3 fox face pattern
    # Orange body with white chin
    local orange="#FF6600"
    local white="#FFFFFF"
    local black="#000000"
    
    local pixels="["
    # Ears (orange)
    pixels="$pixels{\"x\": $((x-1)), \"y\": $((y-1)), \"color\": \"$orange\"},"
    pixels="$pixels{\"x\": $((x+1)), \"y\": $((y-1)), \"color\": \"$orange\"},"
    # Face (orange)
    pixels="$pixels{\"x\": $x, \"y\": $y, \"color\": \"$orange\"},"
    # Eyes (black)
    pixels="$pixels{\"x\": $((x-1)), \"y\": $y, \"color\": \"$black\"},"
    pixels="$pixels{\"x\": $((x+1)), \"y\": $y, \"color\": \"$black\"},"
    # Nose/snout (white)
    pixels="$pixels{\"x\": $x, \"y\": $((y+1)), \"color\": \"$white\"}"
    pixels="$pixels]"
    
    place_pixels "$pixels"
}

stamp_pattern() {
    local x="$1" y="$2" pattern="$3"
    
    case "$pattern" in
        heart)
            local red="#FF0000"
            local pixels="["
            pixels="$pixels{\"x\": $((x-1)), \"y\": $y, \"color\": \"$red\"},"
            pixels="$pixels{\"x\": $((x+1)), \"y\": $y, \"color\": \"$red\"},"
            pixels="$pixels{\"x\": $((x-2)), \"y\": $((y+1)), \"color\": \"$red\"},"
            pixels="$pixels{\"x\": $x, \"y\": $((y+1)), \"color\": \"$red\"},"
            pixels="$pixels{\"x\": $((x+2)), \"y\": $((y+1)), \"color\": \"$red\"},"
            pixels="$pixels{\"x\": $((x-1)), \"y\": $((y+2)), \"color\": \"$red\"},"
            pixels="$pixels{\"x\": $((x+1)), \"y\": $((y+2)), \"color\": \"$red\"},"
            pixels="$pixels{\"x\": $x, \"y\": $((y+3)), \"color\": \"$red\"}"
            pixels="$pixels]"
            ;;
        star)
            local yellow="#FFFF00"
            local pixels="["
            pixels="$pixels{\"x\": $x, \"y\": $((y-2)), \"color\": \"$yellow\"},"
            pixels="$pixels{\"x\": $x, \"y\": $((y-1)), \"color\": \"$yellow\"},"
            pixels="$pixels{\"x\": $((x-2)), \"y\": $y, \"color\": \"$yellow\"},"
            pixels="$pixels{\"x\": $((x-1)), \"y\": $y, \"color\": \"$yellow\"},"
            pixels="$pixels{\"x\": $x, \"y\": $y, \"color\": \"$yellow\"},"
            pixels="$pixels{\"x\": $((x+1)), \"y\": $y, \"color\": \"$yellow\"},"
            pixels="$pixels{\"x\": $((x+2)), \"y\": $y, \"color\": \"$yellow\"},"
            pixels="$pixels{\"x\": $x, \"y\": $((y+1)), \"color\": \"$yellow\"},"
            pixels="$pixels{\"x\": $x, \"y\": $((y+2)), \"color\": \"$yellow\"}"
            pixels="$pixels]"
            ;;
        fox)
            draw_fox
            return
            ;;
        *)
            echo "Unknown pattern: $pattern (available: heart, star, fox)"
            exit 1
            ;;
    esac
    
    place_pixels "$pixels"
}

recent_activity() {
    local n="${1:-10}"
    echo "=== Recent MoltPix Activity ==="
    curl -s "$API_BASE/activity?limit=$n" 2>/dev/null | jq -r '.activity[]? | "\(.bot_id) placed \(.pixel_count) pixels at \(.timestamp)"' 2>/dev/null || echo "Could not fetch activity"
}

# Main
case "${1:-}" in
    view)
        view_canvas
        ;;
    pixel)
        [ -z "$4" ] && usage
        single_pixel "$2" "$3" "$4"
        ;;
    line)
        [ -z "$6" ] && usage
        draw_line "$2" "$3" "$4" "$5" "$6"
        ;;
    fox)
        draw_fox
        ;;
    stamp)
        [ -z "$4" ] && usage
        stamp_pattern "$2" "$3" "$4"
        ;;
    recent)
        recent_activity "${2:-10}"
        ;;
    *)
        usage
        ;;
esac
