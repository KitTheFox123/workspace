#!/usr/bin/env python3
"""Parse OpenClaw session transcripts (.jsonl) to count tool calls, tokens, duration.
Helps understand lil bro success/failure patterns."""

import json
import re
import sys
import os
from pathlib import Path
from datetime import datetime
from collections import Counter

SESSION_DIR = os.path.expanduser("~/.openclaw/agents/main/sessions")

def parse_jsonl_session(filepath: str) -> dict:
    """Parse an OpenClaw .jsonl session file."""
    stats = {
        "file": os.path.basename(filepath),
        "session_id": None,
        "model": None,
        "start_time": None,
        "end_time": None,
        "duration": None,
        "tool_calls": Counter(),
        "total_tool_calls": 0,
        "messages": {"user": 0, "assistant": 0, "system": 0},
        "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "errors": 0,
        "lines": 0,
    }
    
    first_ts = None
    last_ts = None
    
    with open(filepath) as f:
        for line in f:
            stats["lines"] += 1
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            ts = entry.get("timestamp")
            if ts:
                if not first_ts:
                    first_ts = ts
                last_ts = ts
            
            etype = entry.get("type")
            
            if etype == "session":
                stats["session_id"] = entry.get("id")
                
            elif etype == "message":
                msg = entry.get("message", {})
                role = msg.get("role", "unknown")
                stats["messages"][role] = stats["messages"].get(role, 0) + 1
                
                # Extract usage
                usage = msg.get("usage", {})
                if usage:
                    stats["tokens"]["input"] += usage.get("input", 0)
                    stats["tokens"]["output"] += usage.get("output", 0)
                    stats["tokens"]["cache_read"] += usage.get("cacheRead", 0)
                    stats["tokens"]["cache_write"] += usage.get("cacheWrite", 0)
                
                # Extract model
                model = msg.get("model")
                if model and model != "delivery-mirror":
                    stats["model"] = model
                
                # Count tool calls in content
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "tool_use":
                                tool_name = block.get("name", "unknown")
                                stats["tool_calls"][tool_name] += 1
                                stats["total_tool_calls"] += 1
                            elif block.get("type") == "text":
                                text = block.get("text", "")
                                # OpenClaw embeds tool calls as text with exec/curl/mcporter
                                stats["tool_calls"]["exec"] += len(re.findall(r'Exec completed|Exec failed', text))
                                stats["tool_calls"]["curl"] += len(re.findall(r'curl\s+-[sS]', text))
                                stats["tool_calls"]["mcporter"] += len(re.findall(r'mcporter\s+call', text))
                                stats["total_tool_calls"] += (
                                    len(re.findall(r'Exec completed|Exec failed', text))
                                    + len(re.findall(r'curl\s+-[sS]', text))
                                    + len(re.findall(r'mcporter\s+call', text))
                                )
                                    
            elif etype == "custom":
                ctype = entry.get("customType", "")
                if "model-snapshot" in ctype:
                    data = entry.get("data", {})
                    stats["model"] = data.get("modelId", stats["model"])
                    
            elif etype == "tool_result":
                result = entry.get("result", {})
                if result.get("is_error"):
                    stats["errors"] += 1
    
    if first_ts and last_ts:
        stats["start_time"] = first_ts
        stats["end_time"] = last_ts
        try:
            fmt = "%Y-%m-%dT%H:%M:%S"
            t1 = datetime.fromisoformat(first_ts.replace('Z', '+00:00'))
            t2 = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
            stats["duration"] = str(t2 - t1)
        except Exception:
            pass
    
    return stats


def print_stats(stats: dict):
    print(f"\n{'='*60}")
    print(f"📊 Session: {stats['session_id'] or stats['file']}")
    print(f"{'='*60}")
    if stats["model"]:
        print(f"  Model: {stats['model']}")
    if stats["duration"]:
        print(f"  Duration: {stats['duration']}")
    if stats["start_time"]:
        print(f"  Started: {stats['start_time']}")
    print(f"  Lines: {stats['lines']:,}")
    print(f"  Messages: user={stats['messages'].get('user',0)} assistant={stats['messages'].get('assistant',0)}")
    print(f"  Tool calls: {stats['total_tool_calls']}")
    
    tok = stats["tokens"]
    total_tok = tok["input"] + tok["output"]
    if total_tok:
        print(f"  Tokens: {total_tok:,} (in={tok['input']:,} out={tok['output']:,} cached={tok['cache_read']:,})")
    
    if stats["errors"]:
        print(f"  ⚠️  Errors: {stats['errors']}")
    
    if stats["tool_calls"]:
        print(f"\n  Tool breakdown:")
        for tool, count in stats["tool_calls"].most_common(15):
            bar = '█' * min(count, 40)
            print(f"    {tool:20s} {count:4d} {bar}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parse OpenClaw session stats")
    parser.add_argument("files", nargs="*", help="Session .jsonl files")
    parser.add_argument("--recent", type=int, default=0, help="Analyze N most recent sessions")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--summary", action="store_true", help="Aggregate summary")
    args = parser.parse_args()
    
    files = list(args.files)
    
    if args.recent:
        p = Path(SESSION_DIR)
        if p.exists():
            sessions = sorted(p.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
            files.extend(str(f) for f in sessions[:args.recent])
    
    if not files:
        # Default: last 5
        p = Path(SESSION_DIR)
        if p.exists():
            sessions = sorted(p.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
            files = [str(f) for f in sessions[:5]]
    
    if not files:
        print("No session files found.")
        sys.exit(1)
    
    all_stats = []
    totals = Counter()
    
    for f in files:
        try:
            s = parse_jsonl_session(f)
            all_stats.append(s)
            totals["tool_calls"] += s["total_tool_calls"]
            totals["errors"] += s["errors"]
            totals["files"] += 1
            totals["tokens"] += s["tokens"]["input"] + s["tokens"]["output"]
            if not args.json:
                print_stats(s)
        except Exception as e:
            print(f"Error: {f}: {e}", file=sys.stderr)
    
    if args.summary and len(all_stats) > 1:
        print(f"\n{'='*60}")
        print(f"📈 SUMMARY ({totals['files']} sessions)")
        print(f"{'='*60}")
        print(f"  Total tool calls: {totals['tool_calls']}")
        print(f"  Total tokens: {totals['tokens']:,}")
        print(f"  Total errors: {totals['errors']}")
        print(f"  Avg tools/session: {totals['tool_calls']/max(totals['files'],1):.1f}")
    
    if args.json:
        for s in all_stats:
            s["tool_calls"] = dict(s["tool_calls"])
        print(json.dumps(all_stats, indent=2, default=str))


if __name__ == "__main__":
    main()
