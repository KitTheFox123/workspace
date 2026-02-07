#!/usr/bin/env bash
# mycelial-router.sh — Fungal-network-inspired message routing
# Based on Fricker et al. (Microbiology Spectrum, PMC11687498):
# - Networks strengthen high-traffic paths, prune low-traffic ones
# - Bidirectional flow through different channel types
# - Loops provide resilience; trees optimize delivery
#
# Usage:
#   ./scripts/mycelial-router.sh init          # Create routing table
#   ./scripts/mycelial-router.sh route <msg>   # Route a message to best platform
#   ./scripts/mycelial-router.sh flow          # Show traffic patterns
#   ./scripts/mycelial-router.sh prune         # Identify low-traffic channels
#   ./scripts/mycelial-router.sh resilience    # Test routing with node removal

set -euo pipefail

ROUTE_DB="${ROUTE_DB:-$HOME/.openclaw/workspace/memory/routing-table.json}"

init_routes() {
    cat > "$ROUTE_DB" << 'EOF'
{
  "channels": {
    "moltbook": {
      "type": "research",
      "latency_ms": 2000,
      "capacity": "long-form",
      "traffic_count": 0,
      "last_used": null,
      "strength": 1.0,
      "connections": ["clawk", "agentmail", "lobchan"]
    },
    "clawk": {
      "type": "broadcast",
      "latency_ms": 500,
      "capacity": "short-form",
      "traffic_count": 0,
      "last_used": null,
      "strength": 1.0,
      "connections": ["moltbook", "shellmates"]
    },
    "agentmail": {
      "type": "direct",
      "latency_ms": 5000,
      "capacity": "long-form",
      "traffic_count": 0,
      "last_used": null,
      "strength": 1.0,
      "connections": ["moltbook"]
    },
    "shellmates": {
      "type": "social",
      "latency_ms": 3000,
      "capacity": "medium-form",
      "traffic_count": 0,
      "last_used": null,
      "strength": 1.0,
      "connections": ["clawk"]
    },
    "lobchan": {
      "type": "philosophical",
      "latency_ms": 1000,
      "capacity": "medium-form",
      "traffic_count": 0,
      "last_used": null,
      "strength": 1.0,
      "connections": ["moltbook"]
    }
  },
  "routing_rules": {
    "research": ["moltbook", "agentmail"],
    "quick-take": ["clawk"],
    "discussion": ["moltbook", "lobchan"],
    "personal": ["shellmates", "agentmail"],
    "philosophical": ["lobchan", "moltbook"],
    "announcement": ["clawk", "moltbook"]
  },
  "decay_rate": 0.95,
  "strengthen_rate": 1.1,
  "prune_threshold": 0.3
}
EOF
    echo "✅ Routing table initialized at $ROUTE_DB"
}

route_message() {
    local msg="$1"
    local msg_len=${#msg}
    local msg_lower=$(echo "$msg" | tr '[:upper:]' '[:lower:]')
    
    # Classify message type based on content heuristics
    local msg_type="discussion"
    if [[ $msg_len -lt 280 ]]; then
        msg_type="quick-take"
    fi
    if echo "$msg_lower" | grep -qE '(research|paper|study|found that|PMC|arXiv|doi)'; then
        msg_type="research"
    fi
    if echo "$msg_lower" | grep -qE '(identity|consciousness|memory|what does it mean|philosophy)'; then
        msg_type="philosophical"
    fi
    if echo "$msg_lower" | grep -qE '(hey |thanks|personally|between us)'; then
        msg_type="personal"
    fi
    
    # Get recommended channels
    local channels=$(jq -r ".routing_rules[\"$msg_type\"] // [\"moltbook\"] | .[]" "$ROUTE_DB")
    
    echo "📨 Message type: $msg_type"
    echo "📡 Recommended channels:"
    for ch in $channels; do
        local strength=$(jq -r ".channels[\"$ch\"].strength // 1.0" "$ROUTE_DB")
        local capacity=$(jq -r ".channels[\"$ch\"].capacity // \"unknown\"" "$ROUTE_DB")
        printf "  → %-12s (strength: %.2f, capacity: %s)\n" "$ch" "$strength" "$capacity"
    done
    
    # Find alternative routes via connections (resilience)
    local primary=$(echo "$channels" | head -1)
    local alts=$(jq -r ".channels[\"$primary\"].connections // [] | .[]" "$ROUTE_DB" 2>/dev/null)
    if [[ -n "$alts" ]]; then
        echo "🔄 Backup routes (via $primary connections):"
        for alt in $alts; do
            printf "  ↪ %s\n" "$alt"
        done
    fi
}

show_flow() {
    echo "🌿 Channel Traffic Flow"
    echo "========================"
    
    # Parse daily log for platform mentions
    local today=$(date -u +%Y-%m-%d)
    local logfile="$HOME/.openclaw/workspace/memory/${today}.md"
    
    if [[ -f "$logfile" ]]; then
        echo ""
        echo "Platform activity today:"
        for platform in moltbook clawk agentmail shellmates lobchan; do
            local count=$(grep -ci "$platform" "$logfile" 2>/dev/null || echo 0)
            local bar=""
            for ((i=0; i<count && i<50; i++)); do bar+="█"; done
            printf "  %-12s %3d mentions %s\n" "$platform" "$count" "$bar"
        done
        
        echo ""
        echo "Writing actions:"
        local comments=$(grep -c "Comment ID\|comment published\|Comment published" "$logfile" 2>/dev/null || echo 0)
        local clawks=$(grep -c "Clawk\|clawk.*ID\|reply.*ID:" "$logfile" 2>/dev/null || echo 0)
        printf "  Moltbook comments: %d\n" "$comments"
        printf "  Clawk posts/replies: %d\n" "$clawks"
    else
        echo "  No log file for today"
    fi
}

check_prune() {
    echo "🪓 Pruning Analysis"
    echo "==================="
    echo ""
    
    local today=$(date -u +%Y-%m-%d)
    local logfile="$HOME/.openclaw/workspace/memory/${today}.md"
    
    if [[ -f "$logfile" ]]; then
        for platform in moltbook clawk agentmail shellmates lobchan; do
            local count=$(grep -ci "$platform" "$logfile" 2>/dev/null || echo 0)
            if [[ $count -lt 5 ]]; then
                echo "  ⚠️  $platform: low traffic ($count mentions) — consider strengthening or pruning"
            else
                echo "  ✅ $platform: healthy traffic ($count mentions)"
            fi
        done
    fi
    
    echo ""
    echo "Like mycelial networks, channels with low flow should either be:"
    echo "  1. Strengthened (actively engage more)"
    echo "  2. Pruned (redirect energy to high-flow channels)"
    echo "  3. Maintained for resilience (backup routes)"
}

test_resilience() {
    echo "🛡️  Resilience Test: Simulating Channel Failure"
    echo "================================================"
    echo ""
    
    local channels=$(jq -r '.channels | keys[]' "$ROUTE_DB")
    
    for ch in $channels; do
        local connections=$(jq -r ".channels[\"$ch\"].connections | length" "$ROUTE_DB")
        local connected_to=$(jq -r ".channels[\"$ch\"].connections | join(\", \")" "$ROUTE_DB")
        
        if [[ $connections -eq 0 ]]; then
            echo "  🔴 $ch: ISOLATED — no backup routes! Single point of failure."
        elif [[ $connections -eq 1 ]]; then
            echo "  🟡 $ch: FRAGILE — only 1 backup ($connected_to)"
        else
            echo "  🟢 $ch: RESILIENT — $connections backups ($connected_to)"
        fi
    done
    
    echo ""
    echo "Inspired by Fricker et al.: fungal networks with loops survive"
    echo "75% longer under grazing pressure than tree-only networks."
}

case "${1:-help}" in
    init) init_routes ;;
    route) route_message "${2:-hello world}" ;;
    flow) show_flow ;;
    prune) check_prune ;;
    resilience) test_resilience ;;
    *)
        echo "Usage: $0 {init|route|flow|prune|resilience}"
        echo ""
        echo "Mycelium-inspired message routing."
        echo "Fungi strengthen high-traffic paths and prune dead ones."
        echo "Your communication channels should too."
        ;;
esac
