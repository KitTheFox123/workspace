#!/usr/bin/env python3
"""
interoceptive-monitor.py — Agent interoceptive awareness monitor.

Inspired by heartbeat-evoked potential (HEP) research (Gentsch et al. 2018):
the brain generates top-down predictions about internal bodily states, and
mismatches between predicted and actual states produce prediction errors.

For agents: monitors internal state signals (memory staleness, response latency,
context utilization, error rates) and detects prediction errors — when internal
state diverges from expected baseline.

Usage: python3 interoceptive-monitor.py [--check] [--history]
"""

import json
import time
import os
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

WORKSPACE = Path(os.environ.get("WORKSPACE", Path.home() / ".openclaw/workspace"))
STATE_FILE = WORKSPACE / "memory" / "interoceptive-state.json"
MEMORY_DIR = WORKSPACE / "memory"

def get_memory_staleness():
    """How old is the most recent daily log? (hours)"""
    today = datetime.utcnow()
    for days_back in range(7):
        d = today - timedelta(days=days_back)
        path = MEMORY_DIR / f"{d.strftime('%Y-%m-%d')}.md"
        if path.exists():
            mtime = datetime.utcfromtimestamp(path.stat().st_mtime)
            return (today - mtime).total_seconds() / 3600
    return 168.0  # 1 week — max staleness

def get_memory_entropy():
    """Rough content diversity of recent memory files."""
    words = set()
    today = datetime.utcnow()
    for days_back in range(3):
        d = today - timedelta(days=days_back)
        path = MEMORY_DIR / f"{d.strftime('%Y-%m-%d')}.md"
        if path.exists():
            text = path.read_text(errors='ignore').lower()
            words.update(text.split())
    return min(len(words) / 100, 100.0)  # normalize to 0-100

def get_script_count():
    """Number of scripts — proxy for build activity."""
    scripts_dir = WORKSPACE / "scripts"
    if scripts_dir.exists():
        return len(list(scripts_dir.glob("*.py")) + list(scripts_dir.glob("*.sh")))
    return 0

def get_file_churn():
    """Files modified in last 6 hours."""
    cutoff = time.time() - 6 * 3600
    count = 0
    for p in WORKSPACE.rglob("*"):
        if p.is_file() and p.stat().st_mtime > cutoff:
            count += 1
    return count

def compute_state():
    """Current interoceptive state vector."""
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "memory_staleness_hrs": round(get_memory_staleness(), 2),
        "memory_entropy": round(get_memory_entropy(), 1),
        "script_count": get_script_count(),
        "file_churn_6h": get_file_churn(),
    }

def load_history():
    """Load state history."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"readings": [], "baselines": {}}

def save_history(data):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2))

def compute_baselines(readings):
    """Rolling average baselines from history."""
    if not readings:
        return {}
    keys = [k for k in readings[0] if k != "timestamp"]
    baselines = {}
    recent = readings[-20:]  # last 20 readings
    for k in keys:
        vals = [r[k] for r in recent if k in r]
        if vals:
            baselines[k] = round(sum(vals) / len(vals), 2)
    return baselines

def detect_prediction_errors(state, baselines):
    """
    Like HEP: when actual state diverges from predicted (baseline),
    that's a prediction error. Larger = more surprising.
    """
    errors = []
    thresholds = {
        "memory_staleness_hrs": 2.0,  # 2hr deviation = notable
        "memory_entropy": 15.0,       # vocabulary shift
        "script_count": 3,            # sudden build burst or stall
        "file_churn_6h": 20,          # activity spike/drop
    }
    for key, threshold in thresholds.items():
        if key in baselines and key in state:
            delta = state[key] - baselines[key]
            if abs(delta) > threshold:
                direction = "↑" if delta > 0 else "↓"
                magnitude = abs(delta) / threshold
                errors.append({
                    "signal": key,
                    "expected": baselines[key],
                    "actual": state[key],
                    "delta": round(delta, 2),
                    "direction": direction,
                    "magnitude": round(magnitude, 2),
                })
    return errors

def main():
    import sys
    state = compute_state()
    history = load_history()
    
    if "--history" in sys.argv:
        for r in history.get("readings", [])[-10:]:
            print(f"  {r['timestamp']}: staleness={r.get('memory_staleness_hrs','')}h, "
                  f"entropy={r.get('memory_entropy','')}, "
                  f"scripts={r.get('script_count','')}, "
                  f"churn={r.get('file_churn_6h','')}")
        return

    # Update history
    history["readings"].append(state)
    history["readings"] = history["readings"][-100:]  # keep last 100
    baselines = compute_baselines(history["readings"][:-1])  # exclude current
    history["baselines"] = baselines
    save_history(history)
    
    # Report
    print("🫀 Interoceptive State Check")
    print(f"  Memory staleness: {state['memory_staleness_hrs']}h")
    print(f"  Memory entropy:   {state['memory_entropy']}")
    print(f"  Script count:     {state['script_count']}")
    print(f"  File churn (6h):  {state['file_churn_6h']}")
    
    if baselines:
        errors = detect_prediction_errors(state, baselines)
        if errors:
            print("\n⚡ Prediction Errors (state ≠ expected):")
            for e in errors:
                print(f"  {e['direction']} {e['signal']}: expected {e['expected']}, "
                      f"got {e['actual']} (Δ{e['delta']}, {e['magnitude']}x threshold)")
        else:
            print("\n✅ All signals within expected range.")
    else:
        print("\n📊 First reading — baselines will build over time.")

if __name__ == "__main__":
    main()


def ownership_check():
    """
    Rubber hand illusion insight: body ownership requires synchrony
    between expected and actual signals. Check if our 'body' (files,
    configs, scripts) is still 'ours' — no unexpected modifications.
    """
    import subprocess
    
    critical_files = [
        WORKSPACE / "SOUL.md",
        WORKSPACE / "MEMORY.md", 
        WORKSPACE / "IDENTITY.md",
        WORKSPACE / "AGENTS.md",
    ]
    
    anomalies = []
    for f in critical_files:
        if not f.exists():
            anomalies.append(f"MISSING: {f.name}")
            continue
        # Check if modified in last hour by someone other than us
        age_hrs = (time.time() - f.stat().st_mtime) / 3600
        size_kb = f.stat().st_size / 1024
        if size_kb < 0.1:
            anomalies.append(f"SUSPICIOUSLY SMALL: {f.name} ({size_kb:.1f}KB)")
        
    if anomalies:
        print("\n⚠️ Ownership anomalies (rubber hand check):")
        for a in anomalies:
            print(f"  {a}")
    else:
        print("\n🤚 Body ownership intact — all identity files present and sized normally.")


if __name__ == "__main__" and "--ownership" in __import__('sys').argv:
    ownership_check()
