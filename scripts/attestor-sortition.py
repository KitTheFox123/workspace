#!/usr/bin/env python3
"""attestor-sortition.py — Kleroterion-inspired attestor selection via VRF sortition.

Simulates random attestor selection using verifiable random functions.
Models stake-weighted sortition with slashing for dishonest attestors.
Based on Athens kleroterion (370 BC) + Algorand-style cryptographic sortition.

Usage:
    python3 attestor-sortition.py [--demo] [--agents N] [--attestors K] [--rounds R]
"""

import argparse
import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime, timezone


@dataclass
class Attestor:
    """An attestor in the sortition pool."""
    id: str
    stake: float
    honest: bool = True
    times_selected: int = 0
    times_slashed: int = 0
    total_rewards: float = 0.0
    
    @property
    def effective_stake(self) -> float:
        """Stake after slashing penalties."""
        return max(0, self.stake * (0.5 ** self.times_slashed))


def vrf_sortition(attestors: List[Attestor], k: int, round_seed: str) -> List[Attestor]:
    """Select k attestors using stake-weighted VRF sortition.
    
    Simulates VRF: hash(seed || attestor_id) < threshold proportional to stake.
    Like the kleroterion dice tube: random, verifiable, no one controls selection.
    """
    total_stake = sum(a.effective_stake for a in attestors if a.effective_stake > 0)
    if total_stake == 0:
        return []
    
    # Score each attestor: hash(seed || id) weighted by stake
    scored = []
    for a in attestors:
        if a.effective_stake <= 0:
            continue
        h = hashlib.sha256(f"{round_seed}:{a.id}".encode()).hexdigest()
        # Normalize hash to [0,1], weight by stake fraction
        raw_score = int(h[:8], 16) / 0xFFFFFFFF
        weight = a.effective_stake / total_stake
        # Lower score = selected (like white dice in kleroterion)
        selection_score = raw_score / weight
        scored.append((selection_score, a))
    
    scored.sort(key=lambda x: x[0])
    return [a for _, a in scored[:k]]


def simulate(n_agents: int, k_attestors: int, n_rounds: int, 
             rogue_fraction: float = 0.1, slash_rate: float = 0.5) -> dict:
    """Run sortition simulation."""
    
    # Create attestor pool
    attestors = []
    for i in range(n_agents):
        is_rogue = i < int(n_agents * rogue_fraction)
        stake = random.uniform(1.0, 10.0)
        attestors.append(Attestor(
            id=f"att_{i:03d}",
            stake=stake,
            honest=not is_rogue
        ))
    
    detections = 0
    false_negatives = 0
    total_selections = 0
    rogue_selections = 0
    
    for r in range(n_rounds):
        seed = hashlib.sha256(f"round_{r}_{random.random()}".encode()).hexdigest()
        selected = vrf_sortition(attestors, k_attestors, seed)
        
        for a in selected:
            a.times_selected += 1
            total_selections += 1
            
            if not a.honest:
                rogue_selections += 1
                # Rogue attestor: detected with probability based on k
                # More attestors = higher detection (quorum intersection)
                honest_in_round = sum(1 for s in selected if s.honest)
                detection_prob = honest_in_round / len(selected) if selected else 0
                
                if random.random() < detection_prob:
                    a.times_slashed += 1
                    a.stake *= (1 - slash_rate)
                    detections += 1
                else:
                    false_negatives += 1
            else:
                a.total_rewards += 1.0
    
    # Analyze results
    rogue_final_stake = sum(a.effective_stake for a in attestors if not a.honest)
    honest_final_stake = sum(a.effective_stake for a in attestors if a.honest)
    
    # Selection fairness: Gini coefficient of selection counts
    counts = sorted(a.times_selected for a in attestors)
    n = len(counts)
    if n > 0 and sum(counts) > 0:
        gini = sum((2*i - n - 1) * c for i, c in enumerate(counts, 1)) / (n * sum(counts))
    else:
        gini = 0
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "agents": n_agents,
            "attestors_per_round": k_attestors,
            "rounds": n_rounds,
            "rogue_fraction": rogue_fraction,
            "slash_rate": slash_rate
        },
        "results": {
            "total_selections": total_selections,
            "rogue_selections": rogue_selections,
            "rogue_selection_rate": rogue_selections / total_selections if total_selections else 0,
            "detections": detections,
            "false_negatives": false_negatives,
            "detection_rate": detections / (detections + false_negatives) if (detections + false_negatives) else 1.0,
            "rogue_final_stake_pct": rogue_final_stake / (rogue_final_stake + honest_final_stake) * 100 if (rogue_final_stake + honest_final_stake) else 0,
            "selection_gini": round(gini, 3),
        },
        "interpretation": {
            "fairness": "GOOD" if gini < 0.3 else "MODERATE" if gini < 0.5 else "POOR",
            "security": "STRONG" if (detections / (detections + false_negatives) if (detections + false_negatives) else 1) > 0.8 else "MODERATE",
            "rogue_suppression": "EFFECTIVE" if rogue_final_stake / (rogue_final_stake + honest_final_stake) * 100 < rogue_fraction * 100 * 0.5 else "PARTIAL"
        }
    }


def demo():
    """Run demo with multiple configurations."""
    print("=" * 60)
    print("ATTESTOR SORTITION SIMULATOR")
    print("Kleroterion model: VRF + stake-weighted + slashing")
    print("=" * 60)
    
    configs = [
        (50, 3, 100, 0.1, "Small pool, few attestors"),
        (200, 7, 100, 0.1, "Medium pool, BFT quorum (N=3f+1)"),
        (200, 7, 100, 0.3, "Medium pool, high rogue fraction"),
        (1000, 11, 100, 0.1, "Large pool, wide quorum"),
    ]
    
    for n, k, r, rogue, desc in configs:
        result = simulate(n, k, r, rogue)
        res = result["results"]
        interp = result["interpretation"]
        print(f"\n--- {desc} ---")
        print(f"  Pool: {n} agents, {k} attestors/round, {int(rogue*100)}% rogue")
        print(f"  Detection rate: {res['detection_rate']:.1%}")
        print(f"  Rogue final stake: {res['rogue_final_stake_pct']:.1f}%")
        print(f"  Selection Gini: {res['selection_gini']} ({interp['fairness']})")
        print(f"  Security: {interp['security']}, Suppression: {interp['rogue_suppression']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Attestor sortition simulator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--agents", type=int, default=200)
    parser.add_argument("--attestors", type=int, default=7)
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--rogue", type=float, default=0.1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    elif args.json:
        print(json.dumps(simulate(args.agents, args.attestors, args.rounds, args.rogue), indent=2))
    else:
        demo()
