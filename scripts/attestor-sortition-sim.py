#!/usr/bin/env python3
"""attestor-sortition-sim.py — VRF-style sortition for attestor selection.

Simulates Algorand-inspired cryptographic sortition for agent attestor pools.
Compares: random sortition, stake-weighted, standing committee, and hybrid.

Based on Gilad et al. (SOSP 2017) Algorand consensus + SOX §203 rotation.

Usage:
    python3 attestor-sortition-sim.py [--demo] [--rounds N] [--pool-size N]
"""

import argparse
import hashlib
import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class Attestor:
    id: str
    stake: float
    honest: bool
    consecutive_rounds: int = 0
    total_selected: int = 0
    collusion_partner: str = None


@dataclass
class RoundResult:
    round_num: int
    strategy: str
    committee: list
    honest_ratio: float
    capture_risk: float  # max consecutive rounds by any attestor
    context_depth: float  # avg consecutive rounds (familiarity)


def vrf_sortition(attestors: list, seed: str, committee_size: int, 
                  stake_weighted: bool = False) -> list:
    """Select committee using VRF-like sortition."""
    scores = []
    for a in attestors:
        h = hashlib.sha256(f"{seed}:{a.id}".encode()).hexdigest()
        score = int(h[:8], 16) / 0xFFFFFFFF
        if stake_weighted:
            score *= a.stake
        scores.append((score, a))
    
    scores.sort(key=lambda x: -x[0])
    return [a for _, a in scores[:committee_size]]


def standing_committee(attestors: list, committee_size: int) -> list:
    """Fixed committee (worst case for capture)."""
    return sorted(attestors, key=lambda a: -a.stake)[:committee_size]


def hybrid_sortition(attestors: list, seed: str, committee_size: int,
                     max_consecutive: int = 5) -> list:
    """Sortition with mandatory rotation (SOX §203 model)."""
    eligible = [a for a in attestors if a.consecutive_rounds < max_consecutive]
    if len(eligible) < committee_size:
        eligible = attestors  # fallback
    return vrf_sortition(eligible, seed, committee_size, stake_weighted=True)


def simulate(pool_size: int = 50, committee_size: int = 7, rounds: int = 100,
             malicious_ratio: float = 0.2, colluding_pairs: int = 3) -> dict:
    """Run simulation across all strategies."""
    # Create attestor pool
    attestors = []
    for i in range(pool_size):
        honest = i >= int(pool_size * malicious_ratio)
        attestors.append(Attestor(
            id=f"att_{i:03d}",
            stake=random.uniform(0.5, 2.0),
            honest=honest
        ))
    
    # Set up colluding pairs among malicious
    malicious = [a for a in attestors if not a.honest]
    for i in range(min(colluding_pairs, len(malicious) // 2)):
        malicious[2*i].collusion_partner = malicious[2*i+1].id
        malicious[2*i+1].collusion_partner = malicious[2*i].id
    
    strategies = {
        "random_sortition": lambda seed: vrf_sortition(attestors, seed, committee_size),
        "stake_weighted": lambda seed: vrf_sortition(attestors, seed, committee_size, True),
        "standing_committee": lambda seed: standing_committee(attestors, committee_size),
        "hybrid_sox203": lambda seed: hybrid_sortition(attestors, seed, committee_size),
    }
    
    results = {}
    for name, select_fn in strategies.items():
        # Reset
        for a in attestors:
            a.consecutive_rounds = 0
            a.total_selected = 0
        
        round_results = []
        compromised_rounds = 0
        max_capture = 0
        
        for r in range(rounds):
            seed = f"round_{r}_{random.randint(0, 2**32)}"
            committee = select_fn(seed)
            
            # Update tracking
            selected_ids = {a.id for a in committee}
            for a in attestors:
                if a.id in selected_ids:
                    a.consecutive_rounds += 1
                    a.total_selected += 1
                else:
                    a.consecutive_rounds = 0
            
            honest_count = sum(1 for a in committee if a.honest)
            honest_ratio = honest_count / len(committee)
            capture = max(a.consecutive_rounds for a in committee)
            context = sum(a.consecutive_rounds for a in committee) / len(committee)
            
            if honest_ratio < 2/3:
                compromised_rounds += 1
            
            max_capture = max(max_capture, capture)
            
            round_results.append(RoundResult(
                round_num=r, strategy=name, committee=[a.id for a in committee],
                honest_ratio=honest_ratio, capture_risk=capture, context_depth=context
            ))
        
        # Participation spread
        selected_ever = sum(1 for a in attestors if a.total_selected > 0)
        
        results[name] = {
            "compromised_rounds": compromised_rounds,
            "compromise_rate": compromised_rounds / rounds,
            "max_consecutive_selection": max_capture,
            "avg_honest_ratio": sum(r.honest_ratio for r in round_results) / rounds,
            "participation_spread": selected_ever / pool_size,
            "avg_context_depth": sum(r.context_depth for r in round_results) / rounds,
        }
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "params": {
            "pool_size": pool_size,
            "committee_size": committee_size,
            "rounds": rounds,
            "malicious_ratio": malicious_ratio,
        },
        "strategies": results,
        "recommendation": "hybrid_sox203 balances capture resistance with context depth",
    }


def demo():
    results = simulate()
    
    print("=" * 65)
    print("ATTESTOR SORTITION SIMULATION")
    print(f"Pool: {results['params']['pool_size']}, Committee: {results['params']['committee_size']}, "
          f"Rounds: {results['params']['rounds']}, Malicious: {results['params']['malicious_ratio']:.0%}")
    print("=" * 65)
    
    for name, data in results["strategies"].items():
        print(f"\n[{name}]")
        print(f"  Compromise rate:    {data['compromise_rate']:.1%}")
        print(f"  Avg honest ratio:   {data['avg_honest_ratio']:.3f}")
        print(f"  Max consecutive:    {data['max_consecutive_selection']}")
        print(f"  Participation:      {data['participation_spread']:.1%}")
        print(f"  Avg context depth:  {data['avg_context_depth']:.1f}")
    
    print(f"\n→ {results['recommendation']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--pool-size", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(simulate(pool_size=args.pool_size, rounds=args.rounds), indent=2))
    else:
        demo()
