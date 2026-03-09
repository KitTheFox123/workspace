#!/usr/bin/env python3
"""switch-cost-estimator.py — Task switch cost estimator for agent heartbeats.

Based on Bustos et al (2024, J Exp Psych Gen): switch costs scale with 
dissimilarity between task rules. More dissimilar tasks = higher cognitive tax.

Estimates context switch overhead for heartbeat task sequences and suggests
optimal task ordering to minimize total switch cost.

Usage:
    python3 switch-cost-estimator.py [--demo] [--tasks T1,T2,T3...]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List, Tuple
from itertools import permutations
import hashlib


# Task categories with feature vectors (domain, tools, context_type, output_type)
TASK_FEATURES = {
    "clawk_reply": {"domain": "social", "tools": "curl", "context": "thread", "output": "text"},
    "clawk_post": {"domain": "social", "tools": "curl", "context": "research", "output": "text"},
    "moltbook_comment": {"domain": "social", "tools": "curl", "context": "thread", "output": "text"},
    "email_reply": {"domain": "comms", "tools": "curl", "context": "thread", "output": "text"},
    "build_script": {"domain": "code", "tools": "python", "context": "codebase", "output": "file"},
    "research": {"domain": "science", "tools": "keenable", "context": "papers", "output": "notes"},
    "platform_check": {"domain": "ops", "tools": "curl", "context": "api", "output": "status"},
    "memory_update": {"domain": "meta", "tools": "edit", "context": "files", "output": "file"},
    "git_commit": {"domain": "code", "tools": "git", "context": "codebase", "output": "commit"},
    "shellmates_dm": {"domain": "social", "tools": "curl", "context": "thread", "output": "text"},
}


def dissimilarity(task_a: str, task_b: str) -> float:
    """Calculate dissimilarity between two tasks (0-1)."""
    if task_a == task_b:
        return 0.0
    fa = TASK_FEATURES.get(task_a, {})
    fb = TASK_FEATURES.get(task_b, {})
    if not fa or not fb:
        return 1.0
    
    features = ["domain", "tools", "context", "output"]
    mismatches = sum(1 for f in features if fa.get(f) != fb.get(f))
    return mismatches / len(features)


def switch_cost_ms(dissim: float) -> float:
    """Estimated switch cost in ms based on dissimilarity.
    
    Bustos et al found ~150ms baseline switch cost scaling with dissimilarity.
    We model: cost = baseline + dissim * scaling_factor
    """
    baseline = 50  # ms, residual cost even for similar tasks
    scaling = 200  # ms per unit dissimilarity
    return baseline + dissim * scaling


def estimate_sequence_cost(tasks: List[str]) -> dict:
    """Estimate total switch cost for a task sequence."""
    if len(tasks) < 2:
        return {"total_cost_ms": 0, "switches": []}
    
    switches = []
    total = 0
    for i in range(1, len(tasks)):
        d = dissimilarity(tasks[i-1], tasks[i])
        cost = switch_cost_ms(d)
        total += cost
        switches.append({
            "from": tasks[i-1],
            "to": tasks[i],
            "dissimilarity": round(d, 2),
            "cost_ms": round(cost, 1)
        })
    
    return {
        "sequence": tasks,
        "total_cost_ms": round(total, 1),
        "avg_cost_ms": round(total / len(switches), 1),
        "switches": switches
    }


def optimize_sequence(tasks: List[str], max_perms: int = 5000) -> dict:
    """Find optimal task ordering to minimize switch cost.
    
    For small N, tries all permutations. For large N, uses greedy nearest-neighbor.
    """
    from math import factorial
    
    if factorial(len(tasks)) <= max_perms:
        # Exhaustive search
        best_cost = float('inf')
        best_seq = tasks
        for perm in permutations(tasks):
            result = estimate_sequence_cost(list(perm))
            if result["total_cost_ms"] < best_cost:
                best_cost = result["total_cost_ms"]
                best_seq = list(perm)
        method = "exhaustive"
    else:
        # Greedy nearest-neighbor
        remaining = list(tasks)
        best_seq = [remaining.pop(0)]
        while remaining:
            last = best_seq[-1]
            nearest = min(remaining, key=lambda t: dissimilarity(last, t))
            best_seq.append(nearest)
            remaining.remove(nearest)
        best_cost = estimate_sequence_cost(best_seq)["total_cost_ms"]
        method = "greedy"
    
    original = estimate_sequence_cost(tasks)
    optimized = estimate_sequence_cost(best_seq)
    
    savings = original["total_cost_ms"] - optimized["total_cost_ms"]
    
    return {
        "original": original,
        "optimized": optimized,
        "savings_ms": round(savings, 1),
        "savings_pct": round(savings / max(original["total_cost_ms"], 1) * 100, 1),
        "method": method
    }


def demo():
    """Demo with typical heartbeat task sequence."""
    # Typical heartbeat: platform checks → replies → research → build → memory
    typical = [
        "platform_check", "clawk_reply", "research", "build_script",
        "moltbook_comment", "email_reply", "git_commit", "memory_update"
    ]
    
    print("=" * 60)
    print("TASK SWITCH COST ESTIMATOR")
    print("Based on Bustos et al (2024, J Exp Psych Gen)")
    print("=" * 60)
    print()
    
    result = optimize_sequence(typical)
    
    print("ORIGINAL SEQUENCE:")
    for s in result["original"]["switches"]:
        bar = "█" * int(s["dissimilarity"] * 10)
        print(f"  {s['from']:20s} → {s['to']:20s}  d={s['dissimilarity']:.2f} {bar}  {s['cost_ms']:.0f}ms")
    print(f"  Total: {result['original']['total_cost_ms']:.0f}ms")
    print()
    
    print("OPTIMIZED SEQUENCE:")
    for s in result["optimized"]["switches"]:
        bar = "█" * int(s["dissimilarity"] * 10)
        print(f"  {s['from']:20s} → {s['to']:20s}  d={s['dissimilarity']:.2f} {bar}  {s['cost_ms']:.0f}ms")
    print(f"  Total: {result['optimized']['total_cost_ms']:.0f}ms")
    print()
    
    print(f"Savings: {result['savings_ms']:.0f}ms ({result['savings_pct']:.1f}%)")
    print(f"Method: {result['method']}")
    print()
    print("Key insight: batch similar tasks. Social→social→social")
    print("costs less than social→code→social→code.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task switch cost estimator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--tasks", type=str, help="Comma-separated task list")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.tasks:
        tasks = args.tasks.split(",")
        result = optimize_sequence(tasks)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Original: {result['original']['total_cost_ms']}ms")
            print(f"Optimized: {result['optimized']['total_cost_ms']}ms")
            print(f"Savings: {result['savings_pct']}%")
            print(f"Order: {' → '.join(result['optimized']['sequence'])}")
    else:
        demo()
