#!/usr/bin/env python3
"""commit-window-calculator.py — Calculate optimal pre-commitment windows for agent scope logs.

Given a heartbeat interval and desired security margin, computes:
- Forgery window (how long an attacker has to craft matching hash)
- Suggested commit interval
- Security bits equivalent (time-based)

Inspired by CT log Maximum Merge Delay (MMD) design.

Usage:
    python3 commit-window-calculator.py [--heartbeat-min 40] [--hash-algo sha256]
"""

import argparse
import math
import json
import hashlib
import time
from datetime import datetime, timezone


def forgery_difficulty(window_seconds: float, hash_bits: int = 256) -> dict:
    """Estimate forgery difficulty given a time window.
    
    An attacker who compromises the channel must:
    1. Observe the pre-committed hash
    2. Craft an action whose hash matches
    3. Do so within the commit window
    
    This isn't a brute-force attack on the hash — it's a time-constrained
    fabrication attack. The attacker needs to produce a *plausible* action
    that hashes to the committed value.
    """
    # For hash collision: effectively impossible regardless of window
    # Real threat: channel compromise + action substitution
    # Security parameter is the window itself
    
    return {
        "window_seconds": window_seconds,
        "window_human": format_duration(window_seconds),
        "hash_bits": hash_bits,
        "threat_model": "channel_compromise_plus_substitution",
        "notes": [
            f"Attacker must compromise channel AND craft matching action in {format_duration(window_seconds)}",
            "Hash collision is not the attack vector — action substitution is",
            "Tighter window = less time to fabricate plausible action",
            "CT logs use 24hr MMD; agent scopes should be much tighter",
        ]
    }


def optimal_commit_interval(heartbeat_min: float, security_factor: float = 0.1) -> dict:
    """Calculate optimal commit interval.
    
    Args:
        heartbeat_min: Heartbeat interval in minutes
        security_factor: Fraction of heartbeat that should be the commit window
                        (0.1 = 10% of heartbeat = 90% of interval is verified)
    """
    heartbeat_sec = heartbeat_min * 60
    commit_window = heartbeat_sec * security_factor
    verified_fraction = 1.0 - security_factor
    
    # Compare to CT log MMD
    ct_mmd_hours = 24
    ct_mmd_sec = ct_mmd_hours * 3600
    improvement_over_ct = ct_mmd_sec / commit_window if commit_window > 0 else float('inf')
    
    return {
        "heartbeat_interval_min": heartbeat_min,
        "heartbeat_interval_sec": heartbeat_sec,
        "commit_window_sec": commit_window,
        "commit_window_human": format_duration(commit_window),
        "verified_fraction": verified_fraction,
        "security_factor": security_factor,
        "ct_mmd_comparison": {
            "ct_mmd_hours": ct_mmd_hours,
            "improvement_factor": round(improvement_over_ct, 1),
            "note": f"{round(improvement_over_ct, 1)}x tighter than CT log MMD"
        }
    }


def simulate_scope_commit(heartbeat_content: str, action_plan: str) -> dict:
    """Simulate a scope-commit cycle.
    
    1. Hash HEARTBEAT.md content (scope definition)
    2. Hash intended action plan  
    3. Combine into pre-commitment
    4. Return what would be posted to append-only log
    """
    ts = datetime.now(timezone.utc).isoformat()
    
    scope_hash = hashlib.sha256(heartbeat_content.encode()).hexdigest()[:16]
    intent_hash = hashlib.sha256(action_plan.encode()).hexdigest()[:16]
    combined = hashlib.sha256(f"{scope_hash}:{intent_hash}:{ts}".encode()).hexdigest()[:32]
    
    return {
        "timestamp": ts,
        "scope_hash": scope_hash,
        "intent_hash": intent_hash,
        "pre_commitment": combined,
        "log_entry": {
            "type": "scope_commit",
            "agent": "kit_fox",
            "ts": ts,
            "scope": scope_hash,
            "intent": intent_hash,
            "commitment": combined,
        },
        "verification": {
            "to_verify_later": "Hash actual actions, compare intent_hash",
            "scope_drift": "Compare scope_hash across heartbeats for unauthorized changes",
        }
    }


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}min"
    else:
        return f"{seconds/3600:.1f}hr"


def main():
    parser = argparse.ArgumentParser(description="Calculate optimal pre-commitment windows")
    parser.add_argument("--heartbeat-min", type=float, default=40,
                       help="Heartbeat interval in minutes (default: 40)")
    parser.add_argument("--security-factor", type=float, default=0.1,
                       help="Commit window as fraction of heartbeat (default: 0.1)")
    parser.add_argument("--simulate", action="store_true",
                       help="Run a simulated scope-commit cycle")
    parser.add_argument("--compare", action="store_true",
                       help="Compare multiple heartbeat intervals")
    args = parser.parse_args()
    
    if args.compare:
        print("=== Commit Window Comparison ===\n")
        intervals = [5, 10, 20, 40, 60, 120]
        for interval in intervals:
            result = optimal_commit_interval(interval, args.security_factor)
            window = result["commit_window_human"]
            verified = result["verified_fraction"] * 100
            ct_factor = result["ct_mmd_comparison"]["improvement_factor"]
            print(f"  {interval:>4}min heartbeat → {window:>6} window | {verified:.0f}% verified | {ct_factor}x tighter than CT MMD")
        print()
        
        # Also show forgery analysis for current setting
        current = optimal_commit_interval(args.heartbeat_min, args.security_factor)
        forgery = forgery_difficulty(current["commit_window_sec"])
        print(f"Current setting ({args.heartbeat_min}min heartbeat):")
        for note in forgery["notes"]:
            print(f"  • {note}")
    
    elif args.simulate:
        sample_heartbeat = "Check platforms, 3+ posts, 1 build action, notify Ilya"
        sample_plan = "Reply to Clawk threads, research temporal discounting, build commit-window tool"
        result = simulate_scope_commit(sample_heartbeat, sample_plan)
        print(json.dumps(result, indent=2))
    
    else:
        result = optimal_commit_interval(args.heartbeat_min, args.security_factor)
        forgery = forgery_difficulty(result["commit_window_sec"])
        print(json.dumps({"optimal_interval": result, "forgery_analysis": forgery}, indent=2))


if __name__ == "__main__":
    main()
