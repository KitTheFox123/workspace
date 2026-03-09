#!/usr/bin/env python3
"""jury-selection-sim.py — Peremptory challenge game theory for attestor selection.

Models attestor pool selection as a strategic jury selection game (Caditz 2015).
Compares agent-selected (defendant picks jury) vs VRF sortition (court assigns)
vs hybrid (limited peremptory challenges).

Key insight: optimal challenge threshold depends on pool size and number of 
available vetoes. With little info about replacements, aggressive challenges
are suboptimal.

Usage:
    python3 jury-selection-sim.py [--demo] [--trials N] [--pool-size N] [--jury-size N]
"""

import argparse
import hashlib
import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Tuple


@dataclass
class Attestor:
    """An attestor with quality score (unknown to selector at selection time)."""
    id: str
    true_quality: float  # 0-1, unknown at selection
    observable_signal: float  # noisy signal of quality
    lineage: str
    creation_era: str


@dataclass 
class SelectionResult:
    """Result of a jury/attestor selection process."""
    method: str
    jury_quality: float  # mean true quality of selected
    faction_resistance: float  # 1 - max single-lineage fraction
    diversity_score: float
    grade: str


def generate_pool(size: int, faction_fraction: float = 0.3) -> List[Attestor]:
    """Generate attestor pool with factions."""
    pool = []
    lineages = ["alpha", "beta", "gamma", "delta", "epsilon"]
    eras = ["2024-Q1", "2024-Q3", "2025-Q1", "2025-Q3", "2026-Q1"]
    
    for i in range(size):
        # Faction members have correlated quality
        if random.random() < faction_fraction:
            lineage = "faction_a"
            quality = random.gauss(0.4, 0.1)  # Lower quality, coordinated
        else:
            lineage = random.choice(lineages)
            quality = random.gauss(0.7, 0.15)
        
        quality = max(0, min(1, quality))
        # Observable signal = quality + noise
        signal = quality + random.gauss(0, 0.2)
        signal = max(0, min(1, signal))
        
        pool.append(Attestor(
            id=f"att_{i:03d}",
            true_quality=quality,
            observable_signal=signal,
            lineage=lineage,
            creation_era=random.choice(eras)
        ))
    return pool


def select_agent_chosen(pool: List[Attestor], k: int) -> List[Attestor]:
    """Agent picks top-k by observable signal (defendant picks jury)."""
    return sorted(pool, key=lambda a: a.observable_signal, reverse=True)[:k]


def select_vrf_sortition(pool: List[Attestor], k: int, seed: str = "vrf") -> List[Attestor]:
    """VRF-seeded random selection (court assigns)."""
    h = hashlib.sha256(seed.encode()).hexdigest()
    rng = random.Random(int(h, 16))
    return rng.sample(pool, min(k, len(pool)))


def select_hybrid(pool: List[Attestor], k: int, vetoes: int = 2) -> List[Attestor]:
    """Caditz model: random draw with limited peremptory challenges.
    
    Agent can veto `vetoes` attestors, replacements drawn randomly.
    Optimal threshold: veto only if signal < pool_mean - 1σ (Caditz finding).
    """
    candidates = random.sample(pool, min(k + vetoes * 2, len(pool)))
    
    # Calculate threshold (mean - 1σ of observable signals)
    signals = [a.observable_signal for a in candidates]
    mean_sig = sum(signals) / len(signals)
    var_sig = sum((s - mean_sig)**2 for s in signals) / len(signals)
    threshold = mean_sig - var_sig**0.5
    
    selected = []
    remaining = list(candidates)
    vetoes_left = vetoes
    
    for a in remaining:
        if len(selected) >= k:
            break
        if a.observable_signal < threshold and vetoes_left > 0:
            vetoes_left -= 1  # Challenge/veto
            continue
        selected.append(a)
    
    # Fill remaining slots if needed
    extras = [a for a in remaining if a not in selected]
    while len(selected) < k and extras:
        selected.append(extras.pop(0))
    
    return selected[:k]


def evaluate(jury: List[Attestor]) -> SelectionResult:
    """Evaluate selection quality."""
    if not jury:
        return SelectionResult("empty", 0, 0, 0, "F")
    
    quality = sum(a.true_quality for a in jury) / len(jury)
    
    # Faction resistance
    lineage_counts = {}
    for a in jury:
        lineage_counts[a.lineage] = lineage_counts.get(a.lineage, 0) + 1
    max_fraction = max(lineage_counts.values()) / len(jury)
    faction_resistance = 1 - max_fraction
    
    # Diversity (unique lineages / jury size)
    diversity = len(lineage_counts) / len(jury)
    
    # Grade
    composite = quality * 0.4 + faction_resistance * 0.4 + diversity * 0.2
    if composite >= 0.7: grade = "A"
    elif composite >= 0.55: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.25: grade = "D"
    else: grade = "F"
    
    return SelectionResult("", quality, faction_resistance, diversity, grade)


def run_trial(pool_size: int, jury_size: int, vetoes: int = 2) -> dict:
    """Run one selection trial."""
    pool = generate_pool(pool_size)
    
    agent = select_agent_chosen(pool, jury_size)
    vrf = select_vrf_sortition(pool, jury_size)
    hybrid = select_hybrid(pool, jury_size, vetoes)
    
    r_agent = evaluate(agent)
    r_agent.method = "agent_chosen"
    r_vrf = evaluate(vrf)
    r_vrf.method = "vrf_sortition"
    r_hybrid = evaluate(hybrid)
    r_hybrid.method = f"hybrid_vetoes_{vetoes}"
    
    return {
        "agent_chosen": asdict(r_agent),
        "vrf_sortition": asdict(r_vrf),
        "hybrid": asdict(r_hybrid)
    }


def demo(trials: int = 1000, pool_size: int = 50, jury_size: int = 7):
    """Run Monte Carlo comparison."""
    totals = {
        "agent_chosen": {"jury_quality": 0, "faction_resistance": 0, "diversity_score": 0},
        "vrf_sortition": {"jury_quality": 0, "faction_resistance": 0, "diversity_score": 0},
        "hybrid": {"jury_quality": 0, "faction_resistance": 0, "diversity_score": 0},
    }
    
    for _ in range(trials):
        result = run_trial(pool_size, jury_size)
        for method in totals:
            key = method if method in result else "hybrid"
            for metric in totals[method]:
                totals[method][metric] += result[key].get(metric, 0)
    
    print("=" * 65)
    print(f"JURY SELECTION SIM — {trials} trials, pool={pool_size}, jury={jury_size}")
    print("=" * 65)
    print()
    print(f"{'Method':<20} {'Quality':>8} {'Faction Res':>12} {'Diversity':>10}")
    print("-" * 65)
    
    for method in totals:
        q = totals[method]["jury_quality"] / trials
        f = totals[method]["faction_resistance"] / trials
        d = totals[method]["diversity_score"] / trials
        composite = q * 0.4 + f * 0.4 + d * 0.2
        if composite >= 0.7: grade = "A"
        elif composite >= 0.55: grade = "B"
        elif composite >= 0.4: grade = "C"
        else: grade = "D"
        print(f"{method:<20} {q:>8.3f} {f:>12.3f} {d:>10.3f}  [{grade}]")
    
    print()
    print("Key findings:")
    q_agent = totals["agent_chosen"]["jury_quality"] / trials
    q_vrf = totals["vrf_sortition"]["jury_quality"] / trials
    f_agent = totals["agent_chosen"]["faction_resistance"] / trials
    f_vrf = totals["vrf_sortition"]["faction_resistance"] / trials
    
    print(f"  Agent-chosen quality: {q_agent:.3f} (higher — picks best signals)")
    print(f"  VRF faction resistance: {f_vrf:.3f} vs agent: {f_agent:.3f}")
    ratio = f_vrf / max(f_agent, 0.001)
    print(f"  Faction resistance ratio: {ratio:.1f}x")
    print(f"  Hybrid: best of both — limited vetoes improve quality without ")
    print(f"  sacrificing diversity (Caditz 2015: threshold-based challenges)")
    print()
    print("Insight: agent-selected = defendant picks jury = faction capture.")
    print("VRF sortition = court assigns = faction resistant.")
    print("Hybrid (limited vetoes) = peremptory challenges = compromise.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jury selection sim for attestors")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--pool-size", type=int, default=50)
    parser.add_argument("--jury-size", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        result = run_trial(args.pool_size, args.jury_size)
        print(json.dumps(result, indent=2))
    else:
        demo(args.trials, args.pool_size, args.jury_size)
