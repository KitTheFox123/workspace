#!/usr/bin/env python3
"""
timing-side-channel.py — Detect covert coordination between agents via timing analysis.

Agents controlled by the same operator often exhibit synchronized activity patterns
even without explicit communication. This tool detects:
1. Inter-arrival time regularity (bot-like periodic behavior)
2. Cross-agent timing correlation (synchronized posting)
3. Phase-locked behavior (consistent offset between agents)

Based on covert timing channel literature (Al-Eidi 2020, PMC7219501).
"""
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta

def parse_timestamps(events: list[dict]) -> dict[str, list[float]]:
    """Group events by agent, convert to unix timestamps."""
    by_agent = defaultdict(list)
    for e in events:
        agent = e.get("agent", "unknown")
        ts = e.get("timestamp")
        if isinstance(ts, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(ts, fmt)
                    by_agent[agent].append(dt.timestamp())
                    break
                except ValueError:
                    continue
        elif isinstance(ts, (int, float)):
            by_agent[agent].append(float(ts))
    return {a: sorted(ts) for a, ts in by_agent.items()}

def inter_arrival_regularity(timestamps: list[float]) -> dict:
    """Detect bot-like periodic behavior via coefficient of variation of inter-arrival times."""
    if len(timestamps) < 3:
        return {"regular": False, "reason": "insufficient data", "n": len(timestamps)}
    
    intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps) - 1)]
    mean_interval = statistics.mean(intervals)
    if mean_interval == 0:
        return {"regular": True, "cv": 0, "reason": "zero intervals (simultaneous)", "n": len(intervals)}
    
    std_interval = statistics.stdev(intervals) if len(intervals) > 1 else 0
    cv = std_interval / mean_interval  # coefficient of variation
    
    # CV < 0.3 suggests regularity (human posting is typically CV > 0.8)
    return {
        "regular": cv < 0.3,
        "cv": round(cv, 4),
        "mean_interval_sec": round(mean_interval, 1),
        "std_interval_sec": round(std_interval, 1),
        "n": len(intervals),
        "verdict": "BOT-LIKE" if cv < 0.15 else "SUSPICIOUS" if cv < 0.3 else "NORMAL"
    }

def cross_correlation(ts_a: list[float], ts_b: list[float], window_sec: float = 60.0) -> dict:
    """Detect synchronized posting between two agents.
    
    For each event from agent A, check if agent B posted within window_sec.
    High hit rate = potential coordination.
    """
    if not ts_a or not ts_b:
        return {"correlated": False, "reason": "insufficient data"}
    
    hits = 0
    for t in ts_a:
        for tb in ts_b:
            if abs(t - tb) <= window_sec:
                hits += 1
                break
    
    hit_rate = hits / len(ts_a)
    
    # Expected rate under independence (Poisson approximation)
    total_span = max(max(ts_a), max(ts_b)) - min(min(ts_a), min(ts_b))
    if total_span == 0:
        expected_rate = 1.0
    else:
        lambda_b = len(ts_b) / total_span
        expected_rate = 1 - math.exp(-2 * window_sec * lambda_b)
    
    ratio = hit_rate / expected_rate if expected_rate > 0 else float('inf')
    
    return {
        "correlated": ratio > 2.0,
        "hit_rate": round(hit_rate, 4),
        "expected_rate": round(expected_rate, 4),
        "ratio": round(ratio, 2),
        "window_sec": window_sec,
        "verdict": "COORDINATED" if ratio > 3.0 else "SUSPICIOUS" if ratio > 2.0 else "INDEPENDENT"
    }

def phase_lock_detection(ts_a: list[float], ts_b: list[float]) -> dict:
    """Detect consistent time offset between two agents (phase-locked behavior).
    
    If agent B always posts ~X seconds after agent A, that's a phase lock.
    """
    if len(ts_a) < 3 or len(ts_b) < 3:
        return {"phase_locked": False, "reason": "insufficient data"}
    
    # For each A event, find nearest B event and compute offset
    offsets = []
    for ta in ts_a:
        nearest = min(ts_b, key=lambda tb: abs(tb - ta))
        offsets.append(nearest - ta)
    
    if not offsets:
        return {"phase_locked": False, "reason": "no matches"}
    
    mean_offset = statistics.mean(offsets)
    std_offset = statistics.stdev(offsets) if len(offsets) > 1 else float('inf')
    
    # Phase-locked if offset is consistent (low std relative to mean)
    consistent = std_offset < 30.0  # within 30 seconds
    
    return {
        "phase_locked": consistent,
        "mean_offset_sec": round(mean_offset, 1),
        "std_offset_sec": round(std_offset, 1),
        "n_pairs": len(offsets),
        "verdict": "PHASE-LOCKED" if consistent else "INDEPENDENT"
    }

def analyze(events: list[dict], window_sec: float = 60.0) -> dict:
    """Full timing side-channel analysis."""
    by_agent = parse_timestamps(events)
    
    results = {
        "agents": len(by_agent),
        "total_events": sum(len(ts) for ts in by_agent.values()),
        "regularity": {},
        "cross_correlation": {},
        "phase_lock": {}
    }
    
    # Per-agent regularity
    for agent, ts in by_agent.items():
        results["regularity"][agent] = inter_arrival_regularity(ts)
    
    # Pairwise cross-correlation and phase-lock
    agents = sorted(by_agent.keys())
    for i, a in enumerate(agents):
        for b in agents[i+1:]:
            pair = f"{a}↔{b}"
            results["cross_correlation"][pair] = cross_correlation(
                by_agent[a], by_agent[b], window_sec
            )
            results["phase_lock"][pair] = phase_lock_detection(
                by_agent[a], by_agent[b]
            )
    
    # Summary verdicts
    suspicious_agents = [a for a, r in results["regularity"].items() if r.get("verdict") in ("BOT-LIKE", "SUSPICIOUS")]
    coordinated_pairs = [p for p, r in results["cross_correlation"].items() if r.get("verdict") in ("COORDINATED", "SUSPICIOUS")]
    phase_locked_pairs = [p for p, r in results["phase_lock"].items() if r.get("phase_locked")]
    
    results["summary"] = {
        "suspicious_regularity": suspicious_agents,
        "coordinated_pairs": coordinated_pairs,
        "phase_locked_pairs": phase_locked_pairs,
        "alert": bool(suspicious_agents or coordinated_pairs or phase_locked_pairs)
    }
    
    return results

def demo():
    """Demo with synthetic data showing coordinated vs independent agents."""
    import random
    random.seed(42)
    
    base = 1709800000.0  # arbitrary epoch
    events = []
    
    # Agent A: regular poster (every ~300s ± 10s) — bot-like
    for i in range(20):
        events.append({"agent": "bot_alice", "timestamp": base + i * 300 + random.gauss(0, 10)})
    
    # Agent B: phase-locked to A (posts ~45s after A) — coordinated
    for i in range(20):
        events.append({"agent": "bot_bob", "timestamp": base + i * 300 + 45 + random.gauss(0, 5)})
    
    # Agent C: independent human-like (irregular intervals)
    t = base
    for i in range(15):
        t += random.expovariate(1/600)  # mean 600s between posts
        events.append({"agent": "human_carol", "timestamp": t})
    
    results = analyze(events, window_sec=60.0)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        demo()
    elif len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            events = json.load(f)
        results = analyze(events)
        print(json.dumps(results, indent=2))
    else:
        print("Usage: timing-side-channel.py [--demo | events.json]")
        print("  Events format: [{\"agent\": \"name\", \"timestamp\": \"ISO8601 or unix\"}, ...]")
        demo()
