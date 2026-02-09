#!/usr/bin/env python3
"""post-audit.py — Verify all tracked Moltbook post IDs still exist, clean up invalid entries.

Reads memory/moltbook-posts.md, extracts UUIDs, checks each against the Moltbook API.
Reports valid/missing/error posts and optionally removes invalid entries from the file.

Usage:
    python3 scripts/post-audit.py              # Check all posts
    python3 scripts/post-audit.py --clean      # Remove invalid entries from file
    python3 scripts/post-audit.py --json       # JSON output
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

POSTS_FILE = Path(__file__).parent.parent / "memory" / "moltbook-posts.md"
CREDS_FILE = Path.home() / ".config" / "moltbook" / "credentials.json"
API_BASE = "https://www.moltbook.com/api/v1"

UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def load_api_key():
    with open(CREDS_FILE) as f:
        return json.load(f)["api_key"]


def extract_uuids(text):
    """Extract all unique UUIDs from the posts file."""
    return list(dict.fromkeys(UUID_RE.findall(text)))  # preserve order, deduplicate


def check_post(uuid, api_key):
    """Check if a post exists. Returns (status_code, title_or_error)."""
    url = f"{API_BASE}/posts/{uuid}"
    req = Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            title = data.get("post", data).get("title", "untitled")
            return resp.status, title
    except HTTPError as e:
        return e.code, str(e.reason)
    except (URLError, TimeoutError) as e:
        return 0, str(e)


def clean_file(posts_text, invalid_uuids):
    """Remove lines containing invalid UUIDs from the posts file."""
    lines = posts_text.split("\n")
    cleaned = []
    removed = 0
    for line in lines:
        found = UUID_RE.findall(line)
        if any(u in invalid_uuids for u in found):
            removed += 1
            continue
        cleaned.append(line)
    return "\n".join(cleaned), removed


def main():
    parser = argparse.ArgumentParser(description="Audit Moltbook post IDs")
    parser.add_argument("--clean", action="store_true", help="Remove invalid entries from file")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if not POSTS_FILE.exists():
        print(f"Error: {POSTS_FILE} not found", file=sys.stderr)
        sys.exit(1)

    api_key = load_api_key()
    posts_text = POSTS_FILE.read_text()
    uuids = extract_uuids(posts_text)

    print(f"Found {len(uuids)} unique post IDs to check\n")

    results = {"valid": [], "missing": [], "error": []}
    
    for i, uuid in enumerate(uuids):
        status, info = check_post(uuid, api_key)
        if status == 200:
            results["valid"].append({"id": uuid, "title": info})
            marker = "✅"
        elif status == 404:
            results["missing"].append({"id": uuid, "error": info})
            marker = "❌ 404"
        else:
            results["error"].append({"id": uuid, "status": status, "error": info})
            marker = f"⚠️  {status}"
        
        if not args.json:
            short = info[:50] + "..." if len(info) > 50 else info
            print(f"  [{i+1}/{len(uuids)}] {uuid} {marker} {short}")
        
        time.sleep(0.3)  # rate limiting

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"\n{'='*60}")
    print(f"Valid: {len(results['valid'])}  |  Missing: {len(results['missing'])}  |  Errors: {len(results['error'])}")

    if results["missing"]:
        print(f"\n❌ Missing posts:")
        for p in results["missing"]:
            print(f"  {p['id']}")

    if args.clean and results["missing"]:
        invalid_ids = {p["id"] for p in results["missing"]}
        cleaned_text, removed = clean_file(posts_text, invalid_ids)
        POSTS_FILE.write_text(cleaned_text)
        print(f"\n🧹 Removed {removed} lines containing invalid post IDs")
    elif results["missing"] and not args.clean:
        print(f"\nRun with --clean to remove invalid entries")


if __name__ == "__main__":
    main()
