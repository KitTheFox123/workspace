#!/usr/bin/env python3
"""
commit-window-analyzer.py — Elster precommitment model for agent scope commits.

Analyzes the time gap between scope-commit (hash published) and scope-audit
(output verified). Based on Elster's Ulysses binding (1979) and CT log MMD.

Key insight: commitment is only meaningful if reversal is costly.
A commit window that's too wide allows retroactive fabrication.
Too tight trips alarms on legitimate async work.

Usage:
    python3 commit-window-analyzer.py [--log FILE] [--mmd SECONDS]
"""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def hash_scope(scope_text: str) -> str:
    """SHA-256 hash of scope text (the commitment)."""
    return hashlib.sha256(scope_text.encode()).hexdigest()[:16]


def analyze_window(commit_time: float, audit_time: float, mmd_seconds: float) -> dict:
    """
    Analyze a commit window against the Maximum Merge Delay.
    
    Returns risk assessment:
    - window_seconds: actual gap
    - mmd_ratio: window / MMD (>1.0 = exceeded)
    - risk_level: low/medium/high/critical
    - elster_score: precommitment strength (0-1)
    """
    window = audit_time - commit_time
    ratio = window / mmd_seconds if mmd_seconds > 0 else float('inf')
    
    # Elster score: commitment strength decays with window width
    # At 0 seconds = perfect binding (score 1.0)
    # At MMD = acceptable (score 0.5)
    # At 2x MMD = weak (score 0.25)
    elster_score = 1.0 / (1.0 + ratio) if ratio >= 0 else 0.0
    
    if ratio < 0:
        risk = "invalid"  # audit before commit = time travel
    elif ratio <= 0.5:
        risk = "low"
    elif ratio <= 1.0:
        risk = "medium"
    elif ratio <= 2.0:
        risk = "high"
    else:
        risk = "critical"  # retroactive fabrication likely
    
    return {
        "window_seconds": round(window, 2),
        "mmd_ratio": round(ratio, 3),
        "risk_level": risk,
        "elster_score": round(elster_score, 3),
        "binding_type": classify_binding(ratio),
    }


def classify_binding(ratio: float) -> str:
    """Classify the type of precommitment based on Elster's taxonomy."""
    if ratio <= 0.1:
        return "mast_binding"  # Ulysses: physically impossible to deviate
    elif ratio <= 0.5:
        return "costly_reversal"  # Schelling: reversal possible but expensive
    elif ratio <= 1.0:
        return "reputation_stake"  # Public commitment, social cost to break
    elif ratio <= 2.0:
        return "weak_promise"  # Intention without enforcement
    else:
        return "theater"  # No real commitment — free reversal


def analyze_heartbeat_log(log_path: str, mmd_seconds: float) -> list:
    """
    Analyze a JSONL log of scope commits and audits.
    
    Expected format per line:
    {"type": "commit"|"audit", "scope_hash": "...", "timestamp": epoch, "scope_text": "..."}
    """
    commits = {}
    results = []
    
    path = Path(log_path)
    if not path.exists():
        return []
    
    for line in path.read_text().strip().split('\n'):
        if not line.strip():
            continue
        entry = json.loads(line)
        
        if entry["type"] == "commit":
            commits[entry["scope_hash"]] = entry["timestamp"]
        elif entry["type"] == "audit":
            scope_hash = entry["scope_hash"]
            if scope_hash in commits:
                analysis = analyze_window(
                    commits[scope_hash], entry["timestamp"], mmd_seconds
                )
                analysis["scope_hash"] = scope_hash
                results.append(analysis)
            else:
                results.append({
                    "scope_hash": scope_hash,
                    "risk_level": "critical",
                    "error": "audit_without_commit",
                    "note": "Output verified but no prior commitment found — possible retroactive fabrication",
                })
    
    return results


def demo():
    """Demo with synthetic heartbeat data."""
    print("=== Commit Window Analyzer (Elster Model) ===\n")
    
    mmd = 2400  # 40 minutes (heartbeat interval)
    
    scenarios = [
        ("Tight binding (5min window)", 0, 300),
        ("Normal heartbeat (20min)", 0, 1200),
        ("At MMD limit (40min)", 0, 2400),
        ("Exceeded MMD (80min)", 0, 4800),
        ("Retroactive fabrication (3hr)", 0, 10800),
    ]
    
    for name, commit_t, audit_t in scenarios:
        result = analyze_window(commit_t, audit_t, mmd)
        print(f"{name}:")
        print(f"  Window: {result['window_seconds']}s | MMD ratio: {result['mmd_ratio']}")
        print(f"  Risk: {result['risk_level']} | Elster score: {result['elster_score']}")
        print(f"  Binding type: {result['binding_type']}")
        print()
    
    # Show scope hashing
    scope = "Check Clawk notifications, reply to mentions, post 1 research thread"
    h = hash_scope(scope)
    print(f"Scope commit example:")
    print(f"  Text: {scope}")
    print(f"  Hash: {h}")
    print(f"  Publish this hash BEFORE execution. Verify output against scope AFTER.")
    print(f"  The log is the evidence. Self-reporting is confession, not proof.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Commit window analyzer (Elster model)")
    parser.add_argument("--log", help="JSONL log file of commits/audits")
    parser.add_argument("--mmd", type=float, default=2400, help="Max merge delay in seconds (default: 2400)")
    parser.add_argument("--demo", action="store_true", help="Run demo with synthetic data")
    args = parser.parse_args()
    
    if args.log:
        results = analyze_heartbeat_log(args.log, args.mmd)
        for r in results:
            print(json.dumps(r, indent=2))
    else:
        demo()
