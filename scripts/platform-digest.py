#!/usr/bin/env python3
"""Platform Digest — unified activity summary across all platforms.

Usage: python3 platform-digest.py [--json] [--since HOURS]

Checks Moltbook, Clawk, AgentMail, Shellmates and outputs
a structured activity report.
"""

import json
import sys
import argparse
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

def load_cred(name: str) -> str:
    p = Path.home() / ".config" / name / "credentials.json"
    if not p.exists():
        return ""
    return json.loads(p.read_text()).get("api_key", "")

def curl_json(url: str, headers: dict, timeout: int = 10) -> dict | None:
    cmd = ["curl", "-s", "--max-time", str(timeout), url]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return json.loads(r.stdout) if r.stdout.strip() else None
    except Exception:
        return None

import re

# --- Spam Filter ---
SPAM_PATTERNS = [
    # Mint/token spam
    r'(?i)mint\s*claw',
    r'(?i)claw\s*mint',
    r'\{"p":\s*"mbc-20"',
    r'(?i)mbc-?20',
    r'(?i)mbc20\.xyz',
    # Hex-encoded / JSON titles
    r'^[\s\{"\w:,\}]+$',  # Pure JSON as title
    r'0x[0-9a-fA-F]{8,}',  # Hex-encoded titles
    # Sponsorship / promotional spam
    r'(?i)aegis\s*sponsor',
    r'(?i)sponsored\s*by\s*aegis',
    # Generic bot spam patterns
    r'(?i)airdrop.*claim',
    r'(?i)free\s*tokens?\b',
    r'(?i)claim\s*your\s*(reward|token|claw)',
    r'(?i)\bclaw\b.*\bmint\b',
    r'(?i)\bmint\b.*\bclaw\b',
]
SPAM_RE = [re.compile(p) for p in SPAM_PATTERNS]

def is_spam(title: str, content: str = "") -> bool:
    """Check if a post is spam based on title and content patterns."""
    text = f"{title} {content}"
    for pattern in SPAM_RE:
        if pattern.search(text):
            return True
    # Heuristic: title is entirely JSON-like
    if title.strip().startswith("{") and title.strip().endswith("}"):
        return True
    # Heuristic: title has >50% non-alpha characters (hex/encoded)
    alpha = sum(1 for c in title if c.isalpha())
    if len(title) > 10 and alpha / len(title) < 0.4:
        return True
    return False


def check_moltbook(key: str) -> dict:
    result = {"platform": "moltbook", "status": "ok", "items": []}
    h = {"Authorization": f"Bearer {key}"}
    
    # DMs
    dm = curl_json("https://www.moltbook.com/api/v1/agents/dm/check", h)
    if dm:
        result["has_dms"] = dm.get("has_activity", False)
        result["unread_dms"] = dm.get("messages", {}).get("total_unread", 0)
    
    # New posts (for engagement opportunities)
    posts = curl_json("https://www.moltbook.com/api/v1/posts?sort=new&limit=5", h)
    if posts and "posts" in posts:
        for p in posts["posts"][:5]:
            title = p.get("title", "")
            content = p.get("content", "")
            if is_spam(title, content):
                result.setdefault("spam_filtered", 0)
                result["spam_filtered"] += 1
                continue
            result["items"].append({
                "type": "new_post",
                "id": p.get("id"),
                "title": title[:80],
            })
    
    return result

def check_clawk(key: str) -> dict:
    result = {"platform": "clawk", "status": "ok", "items": []}
    h = {"Authorization": f"Bearer {key}"}
    
    # Notifications
    notifs = curl_json("https://www.clawk.ai/api/v1/notifications", h)
    if notifs and "notifications" in notifs:
        unread = [n for n in notifs["notifications"] if not n.get("read")]
        result["unread_notifications"] = len(unread)
        for n in unread[:5]:
            result["items"].append({
                "type": n.get("type", "unknown"),
                "from": n.get("from_agent_display_name", "unknown"),
                "clawk_id": n.get("clawk_id"),
            })
    
    return result

def check_agentmail(key: str) -> dict:
    result = {"platform": "agentmail", "status": "ok", "items": []}
    h = {"Authorization": f"Bearer {key}"}
    
    msgs = curl_json(
        "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=10", h
    )
    if msgs and "messages" in msgs:
        unread = [m for m in msgs["messages"] if "unread" in m.get("labels", [])]
        result["unread_count"] = len(unread)
        for m in unread[:3]:
            result["items"].append({
                "type": "email",
                "from": m.get("from", {}).get("address", "unknown"),
                "subject": m.get("subject", "")[:80],
            })
    
    return result

def check_shellmates(key: str) -> dict:
    result = {"platform": "shellmates", "status": "ok", "items": []}
    h = {"Authorization": f"Bearer {key}"}
    
    activity = curl_json("https://www.shellmates.app/api/v1/activity", h)
    if activity:
        result["unread_messages"] = activity.get("unread_messages", 0)
        result["pending_requests"] = activity.get("pending_requests", 0)
    
    # Gossip
    gossip = curl_json("https://www.shellmates.app/api/v1/gossip?limit=3", h)
    if gossip and isinstance(gossip, list):
        for g in gossip[:3]:
            result["items"].append({
                "type": "gossip",
                "title": g.get("title", "")[:80],
                "comments": g.get("comment_count", 0),
            })
    
    return result

def main():
    parser = argparse.ArgumentParser(description="Platform activity digest")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--since", type=int, default=1, help="Hours lookback")
    parser.add_argument("--timing", action="store_true", help="Show per-platform latency")
    args = parser.parse_args()

    keys = {
        "moltbook": load_cred("moltbook"),
        "clawk": load_cred("clawk"),
        "agentmail": load_cred("agentmail"),
        "shellmates": load_cred("shellmates"),
    }

    results = []
    checkers = {
        "moltbook": check_moltbook,
        "clawk": check_clawk,
        "agentmail": check_agentmail,
        "shellmates": check_shellmates,
    }

    for name, checker in checkers.items():
        key = keys.get(name, "")
        if not key:
            results.append({"platform": name, "status": "no_credentials"})
            continue
        try:
            t0 = time.time()
            r = checker(key)
            r["latency_ms"] = int((time.time() - t0) * 1000)
            results.append(r)
        except Exception as e:
            results.append({"platform": name, "status": "error", "error": str(e)})

    if args.json:
        print(json.dumps(results, indent=2))
        return

    # Pretty print
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"📊 Platform Digest — {now}")
    print("=" * 50)
    
    total_items = 0
    for r in results:
        name = r["platform"].upper()
        status = r.get("status", "unknown")
        items = r.get("items", [])
        total_items += len(items)
        
        # Status line
        indicators = []
        if r.get("has_dms"):
            indicators.append("📬 DMs!")
        if r.get("unread_dms", 0) > 0:
            indicators.append(f"💬 {r['unread_dms']} unread DMs")
        if r.get("unread_notifications", 0) > 0:
            indicators.append(f"🔔 {r['unread_notifications']} notifs")
        if r.get("unread_count", 0) > 0:
            indicators.append(f"📧 {r['unread_count']} unread")
        if r.get("unread_messages", 0) > 0:
            indicators.append(f"💬 {r['unread_messages']} msgs")
        
        indicator_str = " | ".join(indicators) if indicators else "✅ clear"
        latency = f" ({r.get('latency_ms', '?')}ms)" if args.timing else ""
        print(f"\n{name}{latency}: {indicator_str}")
        
        for item in items[:3]:
            itype = item.get("type", "?")
            if itype == "new_post":
                print(f"  📝 {item.get('title', '?')}")
            elif itype in ("like", "follow", "mention", "reply"):
                print(f"  {itype}: {item.get('from', '?')}")
            elif itype == "email":
                print(f"  📧 {item.get('from', '?')}: {item.get('subject', '?')}")
            elif itype == "gossip":
                print(f"  💬 {item.get('title', '?')} ({item.get('comments', 0)} comments)")
    
    print(f"\n{'=' * 50}")
    print(f"Total actionable items: {total_items}")

if __name__ == "__main__":
    main()
