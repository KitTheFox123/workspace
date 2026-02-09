#!/usr/bin/env python3
"""Heartbeat Timer — track gaps between heartbeats, alert if overdue.

Usage: python3 heartbeat-timer.py [--log] [--check] [--stats]

--log    Record a heartbeat timestamp
--check  Check if overdue (exit 1 if gap > threshold)
--stats  Show streak and timing stats
"""

import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

DATA_FILE = Path.home() / ".openclaw" / "workspace" / "memory" / "heartbeat-times.json"
THRESHOLD_MINUTES = 20

def load_data() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"heartbeats": [], "alerts": 0, "longest_streak": 0}

def save_data(data: dict):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2))

def log_heartbeat(data: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    data["heartbeats"].append(now)
    # Keep last 200
    data["heartbeats"] = data["heartbeats"][-200:]
    save_data(data)
    
    if len(data["heartbeats"]) >= 2:
        prev = datetime.fromisoformat(data["heartbeats"][-2])
        curr = datetime.fromisoformat(now)
        gap = (curr - prev).total_seconds() / 60
        print(f"✅ Heartbeat logged at {now[:19]}Z (gap: {gap:.1f} min)")
    else:
        print(f"✅ First heartbeat logged at {now[:19]}Z")
    return data

def check_overdue(data: dict) -> bool:
    if not data["heartbeats"]:
        print("⚠️  No heartbeats recorded yet")
        return True
    
    last = datetime.fromisoformat(data["heartbeats"][-1])
    now = datetime.now(timezone.utc)
    gap = (now - last).total_seconds() / 60
    
    if gap > THRESHOLD_MINUTES:
        print(f"🚨 OVERDUE! Last heartbeat was {gap:.1f} min ago (threshold: {THRESHOLD_MINUTES} min)")
        data["alerts"] += 1
        save_data(data)
        return True
    else:
        remaining = THRESHOLD_MINUTES - gap
        print(f"✅ On track. Last heartbeat {gap:.1f} min ago. Next due in {remaining:.1f} min.")
        return False

def show_stats(data: dict):
    beats = data["heartbeats"]
    if len(beats) < 2:
        print("Not enough data for stats.")
        return
    
    gaps = []
    for i in range(1, len(beats)):
        prev = datetime.fromisoformat(beats[i-1])
        curr = datetime.fromisoformat(beats[i])
        gap = (curr - prev).total_seconds() / 60
        gaps.append(gap)
    
    # Today only
    today = datetime.now(timezone.utc).date().isoformat()
    today_beats = [b for b in beats if b.startswith(today)]
    today_gaps = []
    for i in range(1, len(today_beats)):
        prev = datetime.fromisoformat(today_beats[i-1])
        curr = datetime.fromisoformat(today_beats[i])
        today_gaps.append((curr - prev).total_seconds() / 60)
    
    # Streak (consecutive heartbeats within threshold)
    streak = 0
    for g in reversed(gaps):
        if g <= THRESHOLD_MINUTES:
            streak += 1
        else:
            break
    
    if streak > data.get("longest_streak", 0):
        data["longest_streak"] = streak
        save_data(data)
    
    print(f"📊 Heartbeat Stats")
    print(f"{'=' * 40}")
    print(f"  Total recorded:    {len(beats)}")
    print(f"  Today:             {len(today_beats)}")
    print(f"  Current streak:    {streak} (on-time)")
    print(f"  Longest streak:    {data.get('longest_streak', 0)}")
    print(f"  Overdue alerts:    {data.get('alerts', 0)}")
    
    if gaps:
        avg = sum(gaps) / len(gaps)
        print(f"\n  Avg gap (all):     {avg:.1f} min")
        print(f"  Min gap:           {min(gaps):.1f} min")
        print(f"  Max gap:           {max(gaps):.1f} min")
    
    if today_gaps:
        avg_today = sum(today_gaps) / len(today_gaps)
        print(f"\n  Avg gap (today):   {avg_today:.1f} min")
        print(f"  Min gap (today):   {min(today_gaps):.1f} min")
        print(f"  Max gap (today):   {max(today_gaps):.1f} min")

def main():
    parser = argparse.ArgumentParser(description="Heartbeat timer")
    parser.add_argument("--log", action="store_true", help="Log a heartbeat")
    parser.add_argument("--check", action="store_true", help="Check if overdue")
    parser.add_argument("--stats", action="store_true", help="Show stats")
    args = parser.parse_args()
    
    data = load_data()
    
    if args.log:
        log_heartbeat(data)
    elif args.check:
        overdue = check_overdue(data)
        exit(1 if overdue else 0)
    elif args.stats:
        show_stats(data)
    else:
        # Default: log + stats
        log_heartbeat(data)
        print()
        show_stats(data)

if __name__ == "__main__":
    main()
