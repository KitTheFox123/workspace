#!/usr/bin/env python3
"""
Moltbook Suspension Checker — Check suspension status and queue actions for when it lifts.

Tracks suspension history, estimates when posting will be available,
and manages a queue of pending actions (comments, posts) to execute when unsuspended.

Usage:
    python3 moltbook-suspension-checker.py check          # Check current status
    python3 moltbook-suspension-checker.py queue "post_id" "comment text"  # Queue a comment
    python3 moltbook-suspension-checker.py list            # List queued actions
    python3 moltbook-suspension-checker.py execute         # Execute queued actions if unsuspended
"""

import json, sys, os, subprocess, re
from datetime import datetime, timezone
from pathlib import Path

QUEUE_FILE = Path(__file__).parent.parent / "memory" / "moltbook-queue.json"
CREDS_FILE = Path.home() / ".config" / "moltbook" / "credentials.json"
API_BASE = "https://www.moltbook.com/api/v1"


def get_api_key():
    with open(CREDS_FILE) as f:
        return json.load(f)["api_key"]


def check_status() -> dict:
    """Check if currently suspended by attempting a lightweight API call."""
    key = get_api_key()
    # Try posting a comment to a known post — if 403, parse suspension details
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{API_BASE}/posts/test/comments",
         "-H", f"Authorization: Bearer {key}",
         "-H", "Content-Type: application/json",
         "-d", '{"content": "test"}'],
        capture_output=True, text=True, timeout=15
    )
    
    body = result.stdout
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "unknown", "raw": body[:200]}
    
    if data.get("statusCode") == 403 and "suspended" in data.get("message", "").lower():
        # Parse suspension end time
        msg = data["message"]
        match = re.search(r"until (\d{4}-\d{2}-\d{2}T[\d:.]+Z)", msg)
        if match:
            end_time = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            remaining = (end_time - now).total_seconds()
            return {
                "status": "suspended",
                "until": match.group(1),
                "remaining_hours": round(remaining / 3600, 1),
                "reason": msg,
            }
        return {"status": "suspended", "reason": msg}
    elif data.get("statusCode") == 404:
        # Post not found = we're NOT suspended, just bad post ID
        return {"status": "active", "note": "API responding, not suspended"}
    else:
        return {"status": "unknown", "response": data}


def load_queue() -> list:
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE) as f:
            return json.load(f)
    return []


def save_queue(queue: list):
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


def queue_action(post_id: str, content: str, parent_id: str = None):
    """Queue a comment for later execution."""
    queue = load_queue()
    action = {
        "type": "comment",
        "post_id": post_id,
        "content": content,
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    if parent_id:
        action["parent_id"] = parent_id
    queue.append(action)
    save_queue(queue)
    print(f"Queued comment on {post_id} ({len(content)} chars). Queue size: {len(queue)}")


def execute_queue():
    """Execute all queued actions if unsuspended."""
    status = check_status()
    if status["status"] == "suspended":
        print(f"Still suspended. {status.get('remaining_hours', '?')}h remaining.")
        print(f"Until: {status.get('until', 'unknown')}")
        return
    
    queue = load_queue()
    if not queue:
        print("Queue empty.")
        return
    
    print(f"Executing {len(queue)} queued actions...")
    key = get_api_key()
    succeeded = []
    failed = []
    
    for action in queue:
        if action["type"] == "comment":
            # Use moltbook-comment.sh if available
            script = Path(__file__).parent / "moltbook-comment.sh"
            if script.exists():
                result = subprocess.run(
                    ["bash", str(script), action["post_id"], action["content"]],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0:
                    succeeded.append(action)
                    print(f"  ✅ Comment on {action['post_id'][:8]}...")
                else:
                    failed.append(action)
                    print(f"  ❌ Failed: {result.stderr[:100]}")
            else:
                failed.append(action)
                print(f"  ❌ moltbook-comment.sh not found")
    
    # Keep only failed actions in queue
    save_queue(failed)
    print(f"\nDone: {len(succeeded)} succeeded, {len(failed)} failed (kept in queue)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 moltbook-suspension-checker.py [check|queue|list|execute]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "check":
        status = check_status()
        print(json.dumps(status, indent=2))
    
    elif cmd == "queue":
        if len(sys.argv) < 4:
            print("Usage: queue <post_id> <content> [parent_id]")
            sys.exit(1)
        parent_id = sys.argv[4] if len(sys.argv) > 4 else None
        queue_action(sys.argv[2], sys.argv[3], parent_id)
    
    elif cmd == "list":
        queue = load_queue()
        if not queue:
            print("Queue empty.")
        else:
            for i, action in enumerate(queue):
                print(f"{i+1}. {action['type']} on {action['post_id'][:8]}... ({action['content'][:60]}...)")
                print(f"   Queued: {action['queued_at']}")
    
    elif cmd == "execute":
        execute_queue()
    
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
