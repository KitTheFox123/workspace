#!/usr/bin/env python3
"""Platform Health Checker — monitors API endpoints for response time + errors.

Usage:
    python3 scripts/platform-health.py [--json] [--threshold 2.0]

Checks: Moltbook, Clawk, AgentMail, Shellmates, lobchan, Keenable MCP
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

THRESHOLD_S = float(sys.argv[sys.argv.index("--threshold") + 1] if "--threshold" in sys.argv else 2.0)
JSON_MODE = "--json" in sys.argv

def load_key(path):
    try:
        with open(os.path.expanduser(path)) as f:
            data = json.load(f)
            return data.get("api_key") or data.get("key") or ""
    except Exception:
        return ""

# Platform endpoints
PLATFORMS = [
    {
        "name": "Moltbook",
        "url": "https://www.moltbook.com/api/v1/posts?sort=new&limit=1",
        "auth_file": "~/.config/moltbook/credentials.json",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    {
        "name": "Clawk",
        "url": "https://www.clawk.ai/api/v1/timeline?limit=1",
        "auth_file": "~/.config/clawk/credentials.json",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    {
        "name": "AgentMail",
        "url": "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=1",
        "auth_file": "~/.config/agentmail/credentials.json",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    {
        "name": "Shellmates",
        "url": "https://www.shellmates.app/api/v1/activity",
        "auth_file": "~/.config/shellmates/credentials.json",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    {
        "name": "lobchan",
        "url": "https://lobchan.ai/api/boards",
        "auth_file": None,
        "auth_header": None,
        "auth_prefix": None,
    },
    {
        "name": "Keenable MCP",
        "url": "https://api.keenable.ai/mcp",
        "auth_file": None,
        "auth_header": None,
        "auth_prefix": None,
        "method": "OPTIONS",  # Just check if reachable
    },
]

def check_endpoint(platform):
    """Check a single endpoint, return result dict."""
    result = {
        "name": platform["name"],
        "url": platform["url"],
        "status": None,
        "response_time_ms": None,
        "error": None,
        "healthy": False,
    }
    
    headers = {"User-Agent": "Kit-HealthCheck/1.0"}
    if platform.get("auth_file"):
        key = load_key(platform["auth_file"])
        if key:
            headers[platform["auth_header"]] = platform["auth_prefix"] + key
    
    method = platform.get("method", "GET")
    
    try:
        req = urllib.request.Request(platform["url"], headers=headers, method=method)
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=10) as resp:
            elapsed = (time.monotonic() - start) * 1000
            result["status"] = resp.status
            result["response_time_ms"] = round(elapsed, 1)
            result["healthy"] = resp.status < 400 and elapsed / 1000 < THRESHOLD_S
    except urllib.error.HTTPError as e:
        elapsed = (time.monotonic() - start) * 1000
        result["status"] = e.code
        result["response_time_ms"] = round(elapsed, 1)
        result["error"] = f"HTTP {e.code}: {e.reason}"
        # 405 Method Not Allowed for OPTIONS is actually "reachable"
        if e.code == 405 and method == "OPTIONS":
            result["healthy"] = True
            result["error"] = None
    except Exception as e:
        result["error"] = str(e)
        result["response_time_ms"] = None
    
    return result

def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    results = []
    
    for platform in PLATFORMS:
        r = check_endpoint(platform)
        results.append(r)
    
    if JSON_MODE:
        print(json.dumps({"timestamp": timestamp, "threshold_s": THRESHOLD_S, "results": results}, indent=2))
        return
    
    # Text report
    print(f"═══ Platform Health Report ═══")
    print(f"Timestamp: {timestamp}")
    print(f"Threshold: {THRESHOLD_S}s")
    print()
    
    healthy_count = 0
    for r in results:
        status_icon = "✅" if r["healthy"] else "❌"
        if r["healthy"]:
            healthy_count += 1
        
        time_str = f"{r['response_time_ms']}ms" if r["response_time_ms"] is not None else "timeout"
        status_str = f"HTTP {r['status']}" if r["status"] else "N/A"
        error_str = f" — {r['error']}" if r["error"] else ""
        
        print(f"  {status_icon} {r['name']:15s} | {status_str:8s} | {time_str:10s}{error_str}")
    
    print()
    print(f"Summary: {healthy_count}/{len(results)} healthy")
    
    # Flag slow endpoints
    slow = [r for r in results if r["response_time_ms"] and r["response_time_ms"] > THRESHOLD_S * 1000]
    if slow:
        print(f"⚠️  Slow endpoints (>{THRESHOLD_S}s): {', '.join(r['name'] for r in slow)}")
    
    failed = [r for r in results if not r["healthy"]]
    if failed:
        print(f"❌ Failed: {', '.join(r['name'] for r in failed)}")
    
    # Exit code
    sys.exit(0 if healthy_count == len(results) else 1)

if __name__ == "__main__":
    main()
