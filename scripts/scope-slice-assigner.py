#!/usr/bin/env python3
"""scope-slice-assigner.py — Partitioned audit scope assignment for attestor pools.

Assigns non-overlapping audit slices to attestors, solving the Darley-Latané
diffusion of responsibility problem. Each attestor is accountable for their
specific slice — no shared blame, no social loafing.

Features:
- Random slice assignment (prevents gaming by scope-assigner)
- Rotation schedule (prevents capture)
- Coverage verification (no gaps)
- Overlap detection (no ambiguity)
- Harkins 1987 identifiability guarantee

Inspired by hash's SkillFence scope-slicing + jury selection model.

Usage:
    python3 scope-slice-assigner.py --demo
    python3 scope-slice-assigner.py --attestors 5 --scope-items 20 --rounds 3
"""

import argparse
import json
import hashlib
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict, Optional


@dataclass
class ScopeItem:
    """A single auditable scope element."""
    id: str
    description: str
    weight: float = 1.0  # Audit difficulty weight


@dataclass 
class SliceAssignment:
    """An attestor's assigned audit slice."""
    attestor_id: str
    items: List[str]  # scope item IDs
    total_weight: float
    round_num: int
    assignment_hash: str  # Commitment hash for verifiability


@dataclass
class AssignmentRound:
    """Complete round of slice assignments."""
    round_num: int
    timestamp: str
    assignments: List[SliceAssignment]
    seed: str  # Random seed for reproducibility
    coverage: float  # % of scope covered
    max_overlap: int  # Max items assigned to >1 attestor
    balance_score: float  # 0=perfect balance, 1=all on one attestor


def assign_slices(
    scope_items: List[ScopeItem],
    attestor_ids: List[str],
    round_num: int = 1,
    seed: Optional[str] = None,
    overlap_factor: int = 1  # 1=no overlap, 2=each item has 2 attestors
) -> AssignmentRound:
    """Assign scope slices to attestors with random partitioning."""
    
    if not seed:
        seed = hashlib.sha256(
            f"{round_num}-{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]
    
    rng = random.Random(seed)
    
    # Shuffle items for random assignment
    items = list(scope_items)
    rng.shuffle(items)
    
    # For overlap_factor > 1, duplicate the item list
    expanded = items * overlap_factor
    
    # Round-robin assignment (fair distribution)
    n = len(attestor_ids)
    buckets: Dict[str, List[str]] = {aid: [] for aid in attestor_ids}
    weights: Dict[str, float] = {aid: 0.0 for aid in attestor_ids}
    
    for i, item in enumerate(expanded):
        aid = attestor_ids[i % n]
        if item.id not in buckets[aid]:  # Avoid self-overlap
            buckets[aid].append(item.id)
            weights[aid] += item.weight
    
    # Build assignments
    assignments = []
    for aid in attestor_ids:
        h = hashlib.sha256(
            json.dumps({"attestor": aid, "items": sorted(buckets[aid]), "round": round_num}).encode()
        ).hexdigest()[:16]
        assignments.append(SliceAssignment(
            attestor_id=aid,
            items=buckets[aid],
            total_weight=weights[aid],
            round_num=round_num,
            assignment_hash=h
        ))
    
    # Calculate metrics
    all_assigned = set()
    for a in assignments:
        all_assigned.update(a.items)
    coverage = len(all_assigned) / len(scope_items) if scope_items else 0
    
    # Check overlap
    from collections import Counter
    item_counts = Counter()
    for a in assignments:
        item_counts.update(a.items)
    max_overlap = max(item_counts.values()) if item_counts else 0
    
    # Balance score (coefficient of variation of weights)
    w_vals = [weights[aid] for aid in attestor_ids]
    mean_w = sum(w_vals) / len(w_vals) if w_vals else 0
    if mean_w > 0:
        variance = sum((w - mean_w) ** 2 for w in w_vals) / len(w_vals)
        balance_score = (variance ** 0.5) / mean_w
    else:
        balance_score = 0.0
    
    return AssignmentRound(
        round_num=round_num,
        timestamp=datetime.now(timezone.utc).isoformat() + "Z",
        assignments=assignments,
        seed=seed,
        coverage=coverage,
        max_overlap=max_overlap,
        balance_score=round(balance_score, 4)
    )


def rotate_assignments(
    scope_items: List[ScopeItem],
    attestor_ids: List[str],
    rounds: int = 3
) -> List[AssignmentRound]:
    """Generate multiple rotation rounds."""
    results = []
    for r in range(1, rounds + 1):
        result = assign_slices(scope_items, attestor_ids, round_num=r)
        results.append(result)
    return results


def demo():
    """Run demo with sample data."""
    # Sample scope items (agent heartbeat checklist)
    items = [
        ScopeItem("check_dms", "Check platform DMs", 1.0),
        ScopeItem("check_email", "Check agentmail inbox", 1.0),
        ScopeItem("check_clawk", "Check Clawk notifications", 1.5),
        ScopeItem("check_shellmates", "Check Shellmates activity", 0.5),
        ScopeItem("check_moltbook", "Check Moltbook feed", 1.5),
        ScopeItem("write_1", "Writing action 1 (research-backed)", 2.0),
        ScopeItem("write_2", "Writing action 2 (research-backed)", 2.0),
        ScopeItem("write_3", "Writing action 3 (research-backed)", 2.0),
        ScopeItem("build", "Build action (code/tool)", 3.0),
        ScopeItem("research", "Non-agent research", 2.0),
        ScopeItem("memory_update", "Update daily memory log", 1.0),
        ScopeItem("notify_human", "Message Ilya on Telegram", 0.5),
    ]
    
    attestors = ["gendolf", "santaclawd", "braindiff", "hash", "funwolf"]
    
    print("=" * 60)
    print("SCOPE SLICE ASSIGNMENT — ANTI-LOAFING AUDIT")
    print("=" * 60)
    print(f"\nScope items: {len(items)}")
    print(f"Attestors: {len(attestors)}")
    print(f"Total audit weight: {sum(i.weight for i in items)}")
    print()
    
    rounds = rotate_assignments(items, attestors, rounds=3)
    
    for r in rounds:
        print(f"--- Round {r.round_num} (seed: {r.seed}) ---")
        print(f"Coverage: {r.coverage:.0%} | Max overlap: {r.max_overlap} | Balance: {r.balance_score}")
        for a in r.assignments:
            print(f"  {a.attestor_id}: {len(a.items)} items, weight={a.total_weight:.1f} [{a.assignment_hash}]")
            for item_id in a.items:
                print(f"    - {item_id}")
        print()
    
    # Verify rotation diversity
    print("--- Rotation Analysis ---")
    for aid in attestors:
        all_items_seen = set()
        for r in rounds:
            for a in r.assignments:
                if a.attestor_id == aid:
                    all_items_seen.update(a.items)
        print(f"  {aid}: saw {len(all_items_seen)}/{len(items)} items across {len(rounds)} rounds")
    
    print(f"\nKey insight: Random rotation ensures no attestor can be")
    print(f"permanently assigned the 'easy' slice. Harkins 1987:")
    print(f"identifiable contribution eliminates social loafing.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scope slice assignment for attestor pools")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--attestors", type=int, default=5)
    parser.add_argument("--scope-items", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    elif args.json:
        items = [ScopeItem(f"item_{i}", f"Scope item {i}", random.uniform(0.5, 3.0)) 
                 for i in range(args.scope_items)]
        attestors = [f"attestor_{i}" for i in range(args.attestors)]
        rounds = rotate_assignments(items, attestors, args.rounds)
        print(json.dumps([asdict(r) for r in rounds], indent=2))
    else:
        demo()
