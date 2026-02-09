#!/usr/bin/env python3
"""Monitor lil bro (sub-agent) sessions. Track spawn→complete times, stall rates."""
import json, sys, os, glob
from datetime import datetime, timezone

SESSIONS_DIR = os.path.expanduser("~/.openclaw/agents/main/sessions")

def parse_session(path):
    """Parse a session JSONL for basic stats."""
    lines = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
    except:
        return None
    
    if not lines:
        return {"path": path, "status": "empty", "tokens": 0, "tools": 0, "duration_s": 0}
    
    first_ts = None
    last_ts = None
    total_out = 0
    tool_count = 0
    
    for entry in lines:
        ts = entry.get("timestamp") or entry.get("ts")
        if ts:
            if isinstance(ts, (int, float)):
                t = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
            else:
                continue
            if first_ts is None or t < first_ts:
                first_ts = t
            if last_ts is None or t > last_ts:
                last_ts = t
        
        usage = entry.get("usage", {})
        total_out += usage.get("output", 0)
        
        content = entry.get("content", [])
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "toolCall":
                    tool_count += 1
    
    duration = (last_ts - first_ts).total_seconds() if first_ts and last_ts else 0
    
    return {
        "path": os.path.basename(path),
        "status": "completed" if total_out > 100 else "stalled",
        "tokens": total_out,
        "tools": tool_count,
        "duration_s": round(duration),
        "start": first_ts.isoformat() if first_ts else None,
    }

def main():
    import argparse
    p = argparse.ArgumentParser(description="Monitor lil bro sessions")
    p.add_argument("--recent", type=int, default=10, help="Number of recent sessions")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    
    files = sorted(glob.glob(f"{SESSIONS_DIR}/*.jsonl"), key=os.path.getmtime, reverse=True)
    
    results = []
    stalled = 0
    completed = 0
    
    for f in files[:args.recent]:
        info = parse_session(f)
        if info:
            results.append(info)
            if info["status"] == "stalled":
                stalled += 1
            else:
                completed += 1
    
    if args.json:
        json.dump(results, sys.stdout, indent=2, default=str)
    else:
        total = stalled + completed
        rate = completed / total * 100 if total else 0
        print(f"📊 Lil Bro Monitor — {total} recent sessions")
        print(f"   ✅ Completed: {completed} | ❌ Stalled: {stalled} | Rate: {rate:.0f}%")
        print()
        for r in results:
            icon = "✅" if r["status"] == "completed" else "❌"
            dur = f"{r['duration_s']//60}m{r['duration_s']%60:02d}s" if r["duration_s"] else "0s"
            print(f"  {icon} {r['path'][:12]}... | {r['tokens']:,} tok | {r['tools']} tools | {dur}")

if __name__ == "__main__":
    main()
