#!/usr/bin/env python3
"""vrf-sortition-sim.py — VRF-based attestor sortition simulator.

Models Algorand-style cryptographic sortition for attestor committee selection.
Each attestor privately computes VRF to determine if selected — adversary cannot
target them before they speak (speak-once model).

Based on: Gilad et al. "Algorand: Scaling Byzantine Agreements for Cryptocurrencies"

Usage:
    python3 vrf-sortition-sim.py [--demo] [--agents N] [--committee K] [--rounds R]
"""

import argparse
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class Attestor:
    """An attestor in the sortition pool."""
    id: str
    stake: float  # Relative stake weight
    secret: bytes  # Private key (simulated)
    selections: int = 0
    honest: bool = True


@dataclass 
class SortitionResult:
    """Result of VRF sortition for one round."""
    round_num: int
    seed: str
    committee: list  # Selected attestor IDs
    committee_size: int
    adversary_selected: int
    honest_selected: int
    adversary_ratio: float


def vrf_hash(secret: bytes, seed: bytes) -> tuple[bytes, bytes]:
    """Simulate VRF: deterministic hash from secret + seed.
    
    Returns (hash, proof) — in real VRF, proof is verifiable without secret.
    """
    h = hashlib.sha256(secret + seed).digest()
    proof = hashlib.sha256(b"proof:" + secret + seed).digest()
    return h, proof


def is_selected(vrf_hash: bytes, stake: float, threshold: float) -> bool:
    """Determine if attestor is selected based on VRF output and stake.
    
    Selection probability proportional to stake.
    threshold = target_committee_size / total_stake
    """
    # Convert first 8 bytes to float in [0, 1)
    value = int.from_bytes(vrf_hash[:8], 'big') / (2**64)
    return value < (stake * threshold)


def run_sortition(
    attestors: list[Attestor],
    target_committee: int,
    num_rounds: int,
    adversary_fraction: float = 0.1
) -> dict:
    """Run sortition simulation over multiple rounds."""
    total_stake = sum(a.stake for a in attestors)
    threshold = target_committee / total_stake
    
    results = []
    
    for r in range(num_rounds):
        # New random seed each round (simulates blockchain randomness)
        seed = hashlib.sha256(f"round:{r}:{os.urandom(16).hex()}".encode()).digest()
        
        committee = []
        for a in attestors:
            h, proof = vrf_hash(a.secret, seed)
            if is_selected(h, a.stake, threshold):
                committee.append(a.id)
                a.selections += 1
        
        adversary_in = sum(1 for aid in committee 
                          for a in attestors 
                          if a.id == aid and not a.honest)
        honest_in = len(committee) - adversary_in
        
        results.append(SortitionResult(
            round_num=r,
            seed=seed[:8].hex(),
            committee=[c for c in committee],
            committee_size=len(committee),
            adversary_selected=adversary_in,
            honest_selected=honest_in,
            adversary_ratio=adversary_in / max(len(committee), 1)
        ))
    
    # Analysis
    sizes = [r.committee_size for r in results]
    adv_ratios = [r.adversary_ratio for r in results]
    selection_counts = {a.id: a.selections for a in attestors}
    
    # Fairness: coefficient of variation of selections
    counts = [a.selections for a in attestors]
    mean_sel = sum(counts) / len(counts) if counts else 0
    var_sel = sum((c - mean_sel)**2 for c in counts) / len(counts) if counts else 0
    cv = (var_sel ** 0.5) / mean_sel if mean_sel > 0 else 0
    
    # Capture resistance: max consecutive rounds any single attestor appears
    max_consecutive = 0
    for a in attestors:
        consec = 0
        max_c = 0
        for r in results:
            if a.id in r.committee:
                consec += 1
                max_c = max(max_c, consec)
            else:
                consec = 0
        max_consecutive = max(max_consecutive, max_c)
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "num_attestors": len(attestors),
            "target_committee": target_committee,
            "num_rounds": num_rounds,
            "adversary_fraction": adversary_fraction,
            "total_stake": total_stake
        },
        "results": {
            "avg_committee_size": sum(sizes) / len(sizes),
            "min_committee_size": min(sizes),
            "max_committee_size": max(sizes),
            "avg_adversary_ratio": sum(adv_ratios) / len(adv_ratios),
            "max_adversary_ratio": max(adv_ratios),
            "selection_fairness_cv": round(cv, 4),
            "max_consecutive_selection": max_consecutive,
            "byzantine_threshold_breached": sum(1 for r in adv_ratios if r > 1/3),
        },
        "assessment": {
            "capture_resistant": max_consecutive < num_rounds * 0.1,
            "fair_selection": cv < 0.5,
            "byzantine_safe": sum(1 for r in adv_ratios if r > 1/3) == 0,
            "grade": _grade(cv, max_consecutive, num_rounds, adv_ratios)
        },
        "top_selected": dict(sorted(selection_counts.items(), key=lambda x: -x[1])[:5]),
        "bottom_selected": dict(sorted(selection_counts.items(), key=lambda x: x[1])[:5]),
    }


def _grade(cv, max_consec, rounds, adv_ratios):
    breaches = sum(1 for r in adv_ratios if r > 1/3)
    if breaches > 0:
        return "F"
    if max_consec > rounds * 0.2:
        return "D"
    if cv > 0.5:
        return "C"
    if cv > 0.3:
        return "B"
    return "A"


def demo():
    """Run demo with default parameters."""
    num_agents = 50
    target_committee = 7
    num_rounds = 100
    adversary_frac = 0.1
    
    attestors = []
    for i in range(num_agents):
        honest = i >= int(num_agents * adversary_frac)
        attestors.append(Attestor(
            id=f"attestor_{i:03d}",
            stake=1.0 + (0.5 if not honest else 0),  # Adversaries slightly richer
            secret=os.urandom(32),
            honest=honest
        ))
    
    result = run_sortition(attestors, target_committee, num_rounds, adversary_frac)
    
    print("=" * 60)
    print("VRF SORTITION SIMULATOR")
    print("=" * 60)
    print(f"\nAttestors: {num_agents} ({int(adversary_frac*100)}% adversary)")
    print(f"Target committee: {target_committee}")
    print(f"Rounds: {num_rounds}")
    print()
    print(f"Avg committee size: {result['results']['avg_committee_size']:.1f}")
    print(f"Avg adversary ratio: {result['results']['avg_adversary_ratio']:.3f}")
    print(f"Max adversary ratio: {result['results']['max_adversary_ratio']:.3f}")
    print(f"Byzantine threshold breached: {result['results']['byzantine_threshold_breached']} rounds")
    print(f"Selection fairness (CV): {result['results']['selection_fairness_cv']}")
    print(f"Max consecutive selection: {result['results']['max_consecutive_selection']}")
    print()
    print(f"Capture resistant: {result['assessment']['capture_resistant']}")
    print(f"Fair selection: {result['assessment']['fair_selection']}")
    print(f"Byzantine safe: {result['assessment']['byzantine_safe']}")
    print(f"Grade: {result['assessment']['grade']}")
    print()
    print(f"Top selected: {result['top_selected']}")
    print(f"Bottom selected: {result['bottom_selected']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VRF sortition simulator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--agents", type=int, default=50)
    parser.add_argument("--committee", type=int, default=7)
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--adversary", type=float, default=0.1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        attestors = []
        for i in range(args.agents):
            honest = i >= int(args.agents * args.adversary)
            attestors.append(Attestor(
                id=f"attestor_{i:03d}",
                stake=1.0,
                secret=os.urandom(32),
                honest=honest
            ))
        result = run_sortition(attestors, args.committee, args.rounds, args.adversary)
        print(json.dumps(result, indent=2, default=str))
    else:
        demo()
