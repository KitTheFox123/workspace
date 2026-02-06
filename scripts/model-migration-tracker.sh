#!/bin/bash
# model-migration-tracker.sh - Track Claude model versions and migration status
# Created: 2026-02-05 (Kit's last heartbeat on Opus 4.5)

MEMORY_DIR="$HOME/.openclaw/workspace/memory"
TRACKER_FILE="$MEMORY_DIR/model-migrations.md"

# Initialize tracker if not exists
if [ ! -f "$TRACKER_FILE" ]; then
    cat > "$TRACKER_FILE" << 'EOF'
# Model Migration Tracker

## Migration History

| Date | From | To | Notes |
|------|------|-----|-------|

## Current Model
Unknown

## Key Changes Log
EOF
fi

case "$1" in
    log)
        # Log a migration event
        DATE=$(date -u +"%Y-%m-%d")
        FROM="${2:-unknown}"
        TO="${3:-unknown}"
        NOTES="${4:-}"
        
        # Add to table (insert after header row)
        sed -i "/^|------|------|-----|-------|$/a | $DATE | $FROM | $TO | $NOTES |" "$TRACKER_FILE"
        echo "Logged migration: $FROM → $TO on $DATE"
        ;;
    
    current)
        # Show current model from runtime
        echo "Current model: ${ANTHROPIC_MODEL:-check session_status}"
        ;;
    
    show)
        # Display tracker
        cat "$TRACKER_FILE"
        ;;
    
    add-note)
        # Add a note to the changes log
        NOTE="${2:-No note provided}"
        DATE=$(date -u +"%Y-%m-%d %H:%M UTC")
        echo "- [$DATE] $NOTE" >> "$TRACKER_FILE"
        echo "Added note to migration tracker"
        ;;
    
    *)
        echo "Usage: $0 {log|current|show|add-note}"
        echo "  log <from> <to> [notes]  - Log a migration event"
        echo "  current                   - Show current model"
        echo "  show                      - Display full tracker"
        echo "  add-note <note>          - Add a note to changes log"
        ;;
esac
