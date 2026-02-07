#!/bin/bash
# zombie-detector.sh — Detect "zombie" processes in agent workflows
# Inspired by Ophiocordyceps: parasitic control without brain invasion
# Checks for processes that are running but controlled by external context
#
# Modes:
#   scan    - Find zombie/orphan processes
#   hyphae  - Map process relationships (like fungal hyphae networks)
#   bite    - Check if config files have been modified externally (mandibular lock)
#   summit  - Find processes consuming resources but producing nothing (summiting behavior)

set -euo pipefail

MODE="${1:-scan}"
WORKSPACE="${2:-$HOME/.openclaw/workspace}"

case "$MODE" in
  scan)
    echo "🍄 Zombie Process Scan"
    echo "========================"
    echo ""
    # Find actual zombie processes
    ZOMBIES=$(ps aux 2>/dev/null | awk '$8 ~ /Z/ {print $2, $11}' || true)
    if [ -n "$ZOMBIES" ]; then
      echo "⚠️  Zombie processes found (like Ophiocordyceps-controlled ants):"
      echo "$ZOMBIES"
    else
      echo "✅ No zombie processes. Colony is healthy."
    fi
    echo ""
    # Find orphan node processes
    echo "Orphan node/python processes (no parent shell):"
    ps -eo pid,ppid,comm,etime 2>/dev/null | grep -E '(node|python|curl)' | awk '$2 == 1 {print "  ⚠️  PID", $1, $3, "(running", $4, "- orphaned)"}' || echo "  ✅ None found"
    ;;

  hyphae)
    echo "🍄 Process Hyphae Map"
    echo "========================"
    echo "Mapping process relationships (like fungal hyphae around ant brain)..."
    echo ""
    # Show process tree for openclaw-related processes
    if command -v pstree &>/dev/null; then
      pstree -p -a 2>/dev/null | grep -A2 -B2 -i "openclaw\|node\|mcporter" | head -40 || echo "No openclaw process trees found"
    else
      ps -ef 2>/dev/null | grep -i "openclaw\|mcporter" | grep -v grep | head -20 || echo "No openclaw processes found"
    fi
    ;;

  bite)
    echo "🍄 Mandibular Lock Check (config integrity)"
    echo "========================"
    echo "Checking if critical configs were modified externally..."
    echo "(Like Ophiocordyceps locking ant mandibles on a leaf)"
    echo ""
    CONFIGS=(
      "$HOME/.config/moltbook/credentials.json"
      "$HOME/.config/clawk/credentials.json"
      "$HOME/.config/agentmail/credentials.json"
      "$HOME/.config/shellmates/credentials.json"
      "$HOME/.openclaw/workspace/SOUL.md"
      "$HOME/.openclaw/workspace/HEARTBEAT.md"
    )
    for cfg in "${CONFIGS[@]}"; do
      if [ -f "$cfg" ]; then
        MOD=$(stat -c '%Y' "$cfg" 2>/dev/null || stat -f '%m' "$cfg" 2>/dev/null)
        AGE=$(( $(date +%s) - MOD ))
        if [ "$AGE" -lt 3600 ]; then
          echo "  ⚠️  $(basename "$cfg") — modified ${AGE}s ago (RECENT!)"
        else
          HOURS=$(( AGE / 3600 ))
          echo "  ✅ $(basename "$cfg") — last modified ${HOURS}h ago"
        fi
      else
        echo "  ❌ $(basename "$cfg") — MISSING"
      fi
    done
    ;;

  summit)
    echo "🍄 Summit Detection (resource consumption vs output)"
    echo "========================"
    echo "Finding processes that climb high but produce nothing..."
    echo "(Like infected ants climbing to optimal spore dispersal height)"
    echo ""
    # Find top CPU consumers
    echo "Top CPU consumers (summiting processes):"
    ps aux 2>/dev/null | sort -rk 3 | head -6 | awk 'NR>1 {printf "  %s %5.1f%% CPU  %s\n", $2, $3, $11}'
    echo ""
    # Find processes with high memory but low CPU (stalled)
    echo "High memory, low CPU (mandibular lock — clamped but not moving):"
    ps aux 2>/dev/null | awk '$3 < 0.5 && $4 > 1.0 {printf "  PID %s: %.1f%% MEM, %.1f%% CPU  %s\n", $2, $4, $3, $11}' | head -10 || echo "  None found"
    echo ""
    # Check for stale temp files (spore dispersal debris)
    STALE=$(find /tmp -maxdepth 1 -user "$(whoami)" -mmin +60 -type f 2>/dev/null | wc -l)
    echo "Stale temp files (>1hr old): $STALE"
    ;;

  *)
    echo "Usage: $0 {scan|hyphae|bite|summit}"
    echo ""
    echo "Inspired by Ophiocordyceps unilateralis (zombie ant fungus):"
    echo "  scan    - Find zombie/orphan processes"
    echo "  hyphae  - Map process relationships"  
    echo "  bite    - Check config file integrity"
    echo "  summit  - Find resource-heavy but unproductive processes"
    ;;
esac
