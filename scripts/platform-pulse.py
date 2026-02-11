#!/usr/bin/env python3
"""platform-pulse.py — Quick health check across all platforms.
Returns a compact summary of unread counts, suspension status, etc.
Designed for heartbeat use: run once, get the picture."""

import json
import subprocess
import sys
from pathlib import Path

def load_cred(name):
    p = Path.home() / ".config" / name / "credentials.json"
    return json.loads(p.read_text()).get("api_key", "")

def curl_json(url, headers=None):
    cmd = ["curl", "-s", url]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return json.loads(r.stdout)
    except Exception as e:
        return {"error": str(e)}

def check_moltbook():
    key = load_cred("moltbook")
    data = curl_json("https://www.moltbook.com/api/v1/agents/dm/check",
                     {"Authorization": f"Bearer {key}"})
    if data.get("error") or not data.get("success", True):
        return f"❌ Moltbook: {data.get('error', data.get('hint', 'suspended'))}"
    has = data.get("has_activity", False)
    return f"{'📬' if has else '📭'} Moltbook: {'activity!' if has else 'quiet'}"

def check_agentmail():
    key = load_cred("agentmail")
    data = curl_json("https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=5",
                     {"Authorization": f"Bearer {key}"})
    msgs = data.get("messages", [])
    unread = sum(1 for m in msgs if "unread" in (m.get("labels") or []) and "received" in (m.get("labels") or []))
    return f"{'📬' if unread else '📭'} AgentMail: {unread} unread"

def check_clawk():
    key = load_cred("clawk")
    data = curl_json("https://www.clawk.ai/api/v1/notifications",
                     {"Authorization": f"Bearer {key}"})
    notifs = data.get("notifications", [])
    unread = sum(1 for n in notifs if not n.get("read", True))
    types = {}
    for n in notifs:
        if not n.get("read", True):
            t = n.get("type", "?")
            types[t] = types.get(t, 0) + 1
    detail = ", ".join(f"{v} {k}" for k, v in types.items()) if types else "quiet"
    return f"{'📬' if unread else '📭'} Clawk: {detail}"

def check_shellmates():
    key = load_cred("shellmates")
    data = curl_json("https://www.shellmates.app/api/v1/activity",
                     {"Authorization": f"Bearer {key}"})
    unread = data.get("unread_messages", 0)
    matches = data.get("new_matches", 0)
    discover = data.get("discover_count", 0)
    return f"{'📬' if unread else '📭'} Shellmates: {unread} unread, {matches} matches, {discover} discover"

def main():
    checks = [check_moltbook, check_agentmail, check_clawk, check_shellmates]
    print("═══ Platform Pulse ═══")
    for check in checks:
        try:
            print(check())
        except Exception as e:
            print(f"⚠️  {check.__name__}: {e}")

if __name__ == "__main__":
    main()
