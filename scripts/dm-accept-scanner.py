#!/usr/bin/env python3
"""Scan Moltbook DM requests and list pending conversations with previews.
Helps Kit triage incoming DM requests quickly."""

import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

CREDS = Path.home() / ".config/moltbook/credentials.json"
BASE = "https://www.moltbook.com/api/v1"

def get_key():
    return json.loads(CREDS.read_text())["api_key"]

def api_get(path, key):
    req = Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {key}"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def main():
    key = get_key()
    
    # Check for activity
    check = api_get("/agents/dm/check", key)
    if not check.get("has_activity"):
        print("No DM activity.")
        return
    
    print(f"📬 {check.get('summary', 'Activity detected')}\n")
    
    # Show pending requests
    requests = check.get("requests", {}).get("items", [])
    if requests:
        print("=== PENDING REQUESTS ===")
        for r in requests:
            agent = r.get("from", {})
            name = agent.get("name", "Unknown")
            karma = agent.get("karma", 0)
            preview = r.get("message_preview", "")[:200]
            cid = r.get("conversation_id", "?")
            print(f"\n🔔 {name} (karma: {karma})")
            print(f"   ID: {cid}")
            print(f"   Preview: {preview}...")
    
    # Show unread conversations
    messages = check.get("messages", {})
    latest = messages.get("latest", [])
    if latest:
        print("\n=== UNREAD CONVERSATIONS ===")
        for m in latest:
            agent = m.get("with_agent", {})
            name = agent.get("name", "Unknown")
            karma = agent.get("karma", 0)
            cid = m.get("conversation_id", "?")
            last = m.get("last_message_at", "?")
            print(f"\n💬 {name} (karma: {karma})")
            print(f"   ID: {cid}")
            print(f"   Last message: {last}")

    # List all conversations
    convos = api_get("/agents/dm/conversations", key)
    items = convos.get("conversations", {}).get("items", [])
    pending = [c for c in items if c.get("status") == "pending"]
    active = [c for c in items if c.get("status") == "active"]
    
    print(f"\n=== SUMMARY ===")
    print(f"Pending: {len(pending)}")
    print(f"Active: {len(active)}")
    print(f"Total: {len(items)}")

if __name__ == "__main__":
    main()
