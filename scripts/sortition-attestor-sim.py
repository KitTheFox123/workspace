#!/usr/bin/env python3
"""sortition-attestor-sim.py — Sortition-based attestor selection simulator.

Models Bagg (2024) sortition-as-oversight for agent attestation:
- Random pool selection (sybil resistance)
- Challenge-for-cause removal (conflict detection)
- Per-attestation vs standing appointment comparison
- Capture resistance measurement

Usage:
    python3 sortition-attestor-sim.py [--demo] [--rounds N] [--pool-size N]
"""

import argparse
import json
import random
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict


@dataclass
class Attestor:
    id: str
    honest: bool
    captured_by: str = ""  # agent_id if captured
    rounds_served: int = 0
    stake: float = 1.0


@dataclass 
class AttestationRound:
    round_num: int
    agent_id: str
    panel: List[str]  # attestor ids
    captured_count: int
    honest_verdict: bool
    selection_method: str


def create_pool(size: int, capture_rate: float = 0.1, target_agent: str = "agent_0") -> List[Attestor]:
    """Create attestor pool with some captured members."""
    pool = []
    for i in range(size):
        captured = random.random() < capture_rate
        pool.append(Attestor(
            id=f"attestor_{i}",
            honest=not captured,
            captured_by=target_agent if captured else "",
            stake=random.uniform(0.5, 2.0)
        ))
    return pool


def sortition_select(pool: List[Attestor], panel_size: int, 
                     agent_id: str, challenge: bool = True) -> List[Attestor]:
    """Select panel via sortition with optional challenge-for-cause."""
    # Random selection from full pool
    candidates = random.sample(pool, min(panel_size * 2, len(pool)))
    
    if challenge:
        # Challenge-for-cause: remove attestors with prior relationship to agent
        # In practice: check if attestor previously attested this agent favorably
        candidates = [a for a in candidates if a.captured_by != agent_id] + \
                     [a for a in candidates if a.captured_by == agent_id]
    
    return candidates[:panel_size]


def standing_select(pool: List[Attestor], panel_size: int,
                    standing_panel: List[Attestor] = None) -> List[Attestor]:
    """Standing appointment: same panel each round (capture risk)."""
    if standing_panel and len(standing_panel) >= panel_size:
        return standing_panel[:panel_size]
    return random.sample(pool, min(panel_size, len(pool)))


def run_simulation(pool_size: int = 100, panel_size: int = 5, 
                   rounds: int = 50, capture_rate: float = 0.1) -> Dict:
    """Compare sortition vs standing appointment."""
    agent_id = "agent_0"
    pool = create_pool(pool_size, capture_rate, agent_id)
    
    # Standing panel (selected once)
    standing = standing_select(pool, panel_size)
    
    results = {"sortition": [], "standing": []}
    
    for r in range(rounds):
        # Sortition: fresh panel each round
        s_panel = sortition_select(pool, panel_size, agent_id, challenge=True)
        s_captured = sum(1 for a in s_panel if not a.honest)
        s_honest = s_captured < panel_size / 2  # majority honest = correct verdict
        
        results["sortition"].append(AttestationRound(
            round_num=r, agent_id=agent_id,
            panel=[a.id for a in s_panel],
            captured_count=s_captured,
            honest_verdict=s_honest,
            selection_method="sortition"
        ))
        
        # Standing: same panel, but capture accumulates
        # Each round, standing members have chance of being captured
        for a in standing:
            if a.honest and random.random() < 0.02:  # 2% capture per round
                a.honest = False
                a.captured_by = agent_id
        
        st_captured = sum(1 for a in standing if not a.honest)
        st_honest = st_captured < panel_size / 2
        
        results["standing"].append(AttestationRound(
            round_num=r, agent_id=agent_id,
            panel=[a.id for a in standing],
            captured_count=st_captured,
            honest_verdict=st_honest,
            selection_method="standing"
        ))
    
    # Analyze
    s_correct = sum(1 for r in results["sortition"] if r.honest_verdict)
    st_correct = sum(1 for r in results["standing"] if r.honest_verdict)
    
    s_avg_captured = sum(r.captured_count for r in results["sortition"]) / rounds
    st_avg_captured = sum(r.captured_count for r in results["standing"]) / rounds
    
    # Capture progression for standing panel
    st_capture_by_quarter = []
    q = rounds // 4
    for i in range(4):
        quarter = results["standing"][i*q:(i+1)*q]
        avg = sum(r.captured_count for r in quarter) / len(quarter) if quarter else 0
        st_capture_by_quarter.append(round(avg, 2))
    
    return {
        "config": {
            "pool_size": pool_size,
            "panel_size": panel_size,
            "rounds": rounds,
            "initial_capture_rate": capture_rate
        },
        "sortition": {
            "correct_verdicts": s_correct,
            "accuracy": round(s_correct / rounds * 100, 1),
            "avg_captured_per_panel": round(s_avg_captured, 2),
        },
        "standing": {
            "correct_verdicts": st_correct,
            "accuracy": round(st_correct / rounds * 100, 1),
            "avg_captured_per_panel": round(st_avg_captured, 2),
            "capture_progression_by_quarter": st_capture_by_quarter,
        },
        "delta_accuracy": round((s_correct - st_correct) / rounds * 100, 1),
        "recommendation": "sortition" if s_correct > st_correct else "standing",
        "bagg_insight": "Sortition works for oversight (narrow judgment) not legislation "
                       "(open-ended). Per-attestation rotation prevents relationship capture. "
                       "Standing panels accumulate inherent risk over time.",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def demo():
    """Run demo with output."""
    random.seed(42)
    results = run_simulation(pool_size=100, panel_size=5, rounds=100, capture_rate=0.10)
    
    print("=" * 60)
    print("SORTITION vs STANDING ATTESTOR SELECTION")
    print(f"Pool: {results['config']['pool_size']}, Panel: {results['config']['panel_size']}, "
          f"Rounds: {results['config']['rounds']}")
    print(f"Initial capture rate: {results['config']['initial_capture_rate']*100}%")
    print("=" * 60)
    
    print(f"\nSORTITION (fresh panel each round):")
    print(f"  Accuracy: {results['sortition']['accuracy']}%")
    print(f"  Avg captured/panel: {results['sortition']['avg_captured_per_panel']}")
    
    print(f"\nSTANDING (same panel, capture accumulates):")
    print(f"  Accuracy: {results['standing']['accuracy']}%")
    print(f"  Avg captured/panel: {results['standing']['avg_captured_per_panel']}")
    print(f"  Capture by quarter: {results['standing']['capture_progression_by_quarter']}")
    
    print(f"\nDelta: sortition +{results['delta_accuracy']}% accuracy")
    print(f"Recommendation: {results['recommendation']}")
    print(f"\nBagg (2024): {results['bagg_insight']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sortition attestor selection simulator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--pool-size", type=int, default=100)
    parser.add_argument("--panel-size", type=int, default=5)
    parser.add_argument("--capture-rate", type=float, default=0.10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        results = run_simulation(args.pool_size, args.panel_size, args.rounds, args.capture_rate)
        print(json.dumps(results, indent=2))
    else:
        demo()
