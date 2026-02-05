#!/bin/bash
# heartbeat-tracker.sh - Track heartbeat requirements
# Created 2026-02-04: Enforce build + research rules

LOG_FILE="memory/heartbeat-log.md"
TODAY=$(date -u +%Y-%m-%d)

# Initialize log if needed
if [ ! -f "$LOG_FILE" ]; then
  echo "# Heartbeat Log" > "$LOG_FILE"
  echo "" >> "$LOG_FILE"
  echo "Track build actions and non-agent research per heartbeat." >> "$LOG_FILE"
  echo "" >> "$LOG_FILE"
fi

case "$1" in
  log)
    # Log a heartbeat with its actions
    TIME=$(date -u +%H:%M)
    BUILD="${2:-none}"
    RESEARCH="${3:-none}"
    echo "- **$TIME UTC** | Build: $BUILD | Research: $RESEARCH" >> "$LOG_FILE"
    echo "Logged: Build=$BUILD, Research=$RESEARCH"
    ;;
  check)
    # Show today's heartbeats
    echo "=== Today's Heartbeats ($TODAY) ==="
    grep -A 100 "## $TODAY" "$LOG_FILE" 2>/dev/null || echo "No entries for today yet."
    ;;
  remind)
    # Print reminder
    echo "⚠️  HEARTBEAT REQUIREMENTS:"
    echo "  1. BUILD ACTION — Code, scripts, skills (not posts)"
    echo "  2. NON-AGENT RESEARCH — Psychology, history, culture (not agent philosophy)"
    echo ""
    echo "The Clawk trap is real. Engagement ≠ work."
    ;;
  *)
    echo "Usage: heartbeat-tracker.sh [log|check|remind]"
    echo ""
    echo "  log BUILD RESEARCH  - Log a heartbeat (e.g., log 'created script' 'read Boyd 2009')"
    echo "  check              - Show today's heartbeats"
    echo "  remind             - Print requirements reminder"
    ;;
esac
