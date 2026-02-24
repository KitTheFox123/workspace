#!/usr/bin/env python3
"""
Attestation Burst Detector
Detects sybil-like temporal clustering in attestation streams.
Healthy attestations accumulate gradually; sybil farms attest in bursts.

Usage:
  python3 attestation-burst-detector.py [--demo]
  echo '{"timestamps": ["2026-02-24T04:00:00Z", ...]}' | python3 attestation-burst-detector.py
"""

import json
import sys
import statistics
from datetime import datetime, timezone


def parse_timestamps(timestamps: list[str]) -> list[float]:
    """Parse ISO timestamps to epoch seconds."""
    parsed = []
    for ts in timestamps:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        parsed.append(dt.timestamp())
    parsed.sort()
    return parsed


def compute_intervals(epochs: list[float]) -> list[float]:
    """Compute inter-attestation intervals in seconds."""
    return [epochs[i+1] - epochs[i] for i in range(len(epochs) - 1)]


def detect_burst(timestamps: list[str], burst_threshold_cv: float = 0.5) -> dict:
    """
    Detect burst patterns in attestation timestamps.
    
    Healthy pattern: high CV (coefficient of variation) — irregular intervals
    Sybil pattern: low CV — suspiciously regular OR very short intervals
    Burst pattern: very high CV with some near-zero intervals — clustering
    
    Returns risk assessment dict.
    """
    if len(timestamps) < 3:
        return {"risk": "insufficient_data", "n_attestations": len(timestamps)}
    
    epochs = parse_timestamps(timestamps)
    intervals = compute_intervals(epochs)
    
    mean_interval = statistics.mean(intervals)
    stdev_interval = statistics.stdev(intervals) if len(intervals) > 1 else 0
    cv = stdev_interval / mean_interval if mean_interval > 0 else float('inf')
    
    # Count "burst" intervals (< 60 seconds)
    burst_count = sum(1 for i in intervals if i < 60)
    burst_ratio = burst_count / len(intervals)
    
    # Count "healthy" intervals (> 1 hour)
    healthy_count = sum(1 for i in intervals if i > 3600)
    healthy_ratio = healthy_count / len(intervals)
    
    # Time span
    span_hours = (epochs[-1] - epochs[0]) / 3600
    
    # Risk scoring
    risk_score = 0
    reasons = []
    
    # Burst clustering: many attestations in short time
    if burst_ratio > 0.5:
        risk_score += 40
        reasons.append(f"{burst_ratio:.0%} of intervals < 60s")
    
    # Suspiciously regular (low CV = metronomic)
    if cv < 0.3 and len(intervals) > 5:
        risk_score += 25
        reasons.append(f"CV={cv:.2f} (suspiciously regular)")
    
    # High density: many attestations per hour
    density = len(timestamps) / max(span_hours, 0.01)
    if density > 10:
        risk_score += 25
        reasons.append(f"density={density:.1f}/hour")
    
    # Short total span with many attestations
    if span_hours < 1 and len(timestamps) > 5:
        risk_score += 20
        reasons.append(f"{len(timestamps)} attestations in {span_hours:.1f}h")
    
    # Healthy signals reduce risk
    if healthy_ratio > 0.3:
        risk_score = max(0, risk_score - 20)
    
    risk_level = "low" if risk_score < 30 else "medium" if risk_score < 60 else "high"
    
    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "reasons": reasons,
        "stats": {
            "n_attestations": len(timestamps),
            "span_hours": round(span_hours, 2),
            "mean_interval_sec": round(mean_interval, 1),
            "stdev_interval_sec": round(stdev_interval, 1),
            "cv": round(cv, 3),
            "burst_ratio": round(burst_ratio, 3),
            "density_per_hour": round(density, 2),
        }
    }


def demo():
    """Run demo with healthy vs sybil patterns."""
    # Healthy pattern: organic accumulation over days
    healthy = [
        "2026-02-20T10:15:00Z",
        "2026-02-20T18:42:00Z",
        "2026-02-21T09:03:00Z",
        "2026-02-22T14:27:00Z",
        "2026-02-23T08:11:00Z",
        "2026-02-23T22:45:00Z",
        "2026-02-24T04:30:00Z",
    ]
    
    # Sybil burst: 7 attestations in 5 minutes
    sybil = [
        "2026-02-24T03:00:00Z",
        "2026-02-24T03:00:45Z",
        "2026-02-24T03:01:20Z",
        "2026-02-24T03:02:05Z",
        "2026-02-24T03:02:50Z",
        "2026-02-24T03:03:30Z",
        "2026-02-24T03:04:15Z",
    ]
    
    # Mixed: some organic, some burst
    mixed = [
        "2026-02-20T10:15:00Z",
        "2026-02-21T14:00:00Z",
        "2026-02-23T08:00:00Z",
        "2026-02-23T08:00:30Z",
        "2026-02-23T08:01:00Z",
        "2026-02-23T08:01:30Z",
        "2026-02-24T12:00:00Z",
    ]
    
    for name, ts in [("healthy", healthy), ("sybil_burst", sybil), ("mixed", mixed)]:
        result = detect_burst(ts)
        print(f"\n=== {name.upper()} ===")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        data = json.load(sys.stdin)
        ts = data.get("timestamps", data) if isinstance(data, dict) else data
        print(json.dumps(detect_burst(ts), indent=2))
