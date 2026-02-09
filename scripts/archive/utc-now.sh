#!/bin/bash
# utc-now.sh — Get real UTC time for heartbeat logs
# Usage: source scripts/utc-now.sh; echo "$UTC_NOW"
# Or:    scripts/utc-now.sh  (prints timestamp)

UTC_NOW=$(date -u '+%Y-%m-%d %H:%M UTC')
UTC_ISO=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
UTC_HOUR=$(date -u '+%H:%M')

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "$UTC_NOW"
fi
