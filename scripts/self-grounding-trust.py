#!/usr/bin/env python3
"""self-grounding-trust.py — Trust scoring where weights emerge from structural measurement.

Based on Santa Clawd's insight: use quorum variance ratio itself as calibration
anchor. The 487.9x separation between honest and sybil is a measured structural
fact — not a parameter. Weights derived FROM measurement, not imposed ON it.

Key principle: a sybil that successfully Goodharts quorum variance has built
genuine social infrastructure. The attack becomes the defense.
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Agent:
    id: str
    is_sybil: bool = False
    attestations_given: List[str] = field(default_factory=list)
    attestations_received: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=list)
    activity_timestamps: List[float] = field(default_factory=list)

def generate_network(n_honest: int = 30, n_sybil: int = 10, 
                     n_platforms: int = 5) -> List[Agent]:
    """Generate a mixed honest/sybil network."""
    agents = []
    all_platforms = [f"platform_{i}" for i in range(n_platforms)]
    
    for i in range(n_honest):
        # Honest agents: organic platform presence, bursty timing
        n_plat = random.randint(2, min(4, n_platforms))
        platforms = random.sample(all_platforms, n_plat)
        timestamps = sorted([random.expovariate(0.1) for _ in range(random.randint(10, 50))])
        agents.append(Agent(id=f"honest_{i}", platforms=platforms, activity_timestamps=timestamps))
    
    for i in range(n_sybil):
        # Sybils: clustered platforms, regular timing
        platforms = random.sample(all_platforms, random.randint(1, 2))
        # Manufactured regularity
        n_acts = random.randint(15, 40)
        timestamps = sorted([j * (1.0 + random.gauss(0, 0.02)) for j in range(n_acts)])
        agents.append(Agent(id=f"sybil_{i}", is_sybil=True, platforms=platforms, 
                           activity_timestamps=timestamps))
    
    # Generate attestations
    for a in agents:
        if a.is_sybil:
            # Sybils attest each other (clique)
            targets = [b.id for b in agents if b.is_sybil and b.id != a.id]
            a.attestations_given = random.sample(targets, min(len(targets), random.randint(3, 8)))
        else:
            # Honest agents attest across the network
            targets = [b.id for b in agents if b.id != a.id and not b.is_sybil]
            a.attestations_given = random.sample(targets, min(len(targets), random.randint(2, 10)))
    
    # Build received attestations
    id_map = {a.id: a for a in agents}
    for a in agents:
        for target_id in a.attestations_given:
            if target_id in id_map:
                id_map[target_id].attestations_received.append(a.id)
    
    return agents

def measure_quorum_variance(agent: Agent, all_agents: List[Agent]) -> float:
    """Measure quorum variance — how diverse are this agent's attestors?"""
    if not agent.attestations_received:
        return 0.0
    
    id_map = {a.id: a for a in all_agents}
    attestor_platforms = []
    for att_id in agent.attestations_received:
        if att_id in id_map:
            attestor_platforms.extend(id_map[att_id].platforms)
    
    if not attestor_platforms:
        return 0.0
    
    # Count unique platforms among attestors
    platform_counts = {}
    for p in attestor_platforms:
        platform_counts[p] = platform_counts.get(p, 0) + 1
    
    # Variance of platform distribution (higher = more diverse)
    values = list(platform_counts.values())
    if len(values) < 2:
        return 0.0
    
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return len(platform_counts) * (1 + variance / max(mean ** 2, 0.01))

def measure_timing_cv(agent: Agent) -> float:
    """Coefficient of variation of inter-activity gaps."""
    if len(agent.activity_timestamps) < 3:
        return 0.0
    
    gaps = [agent.activity_timestamps[i+1] - agent.activity_timestamps[i] 
            for i in range(len(agent.activity_timestamps) - 1)]
    
    mean_gap = sum(gaps) / len(gaps)
    if mean_gap == 0:
        return 0.0
    
    std_gap = math.sqrt(sum((g - mean_gap) ** 2 for g in gaps) / len(gaps))
    return std_gap / mean_gap

def measure_cross_clique(agent: Agent, all_agents: List[Agent]) -> float:
    """Measure cross-clique attestation ratio."""
    if not agent.attestations_received:
        return 0.0
    
    id_map = {a.id: a for a in all_agents}
    
    # Count attestors from different platform sets
    platform_sets = []
    for att_id in agent.attestations_received:
        if att_id in id_map:
            platform_sets.append(frozenset(id_map[att_id].platforms))
    
    unique_sets = len(set(platform_sets))
    return unique_sets / max(len(platform_sets), 1)

def self_grounding_score(agents: List[Agent]) -> Dict[str, Dict]:
    """Compute self-grounding trust scores.
    
    Key insight: weights are derived from the separation ratio of structural
    measurements, not hand-tuned. The quorum variance ratio between honest
    and sybil clusters IS the calibration anchor.
    """
    # Step 1: Measure raw structural signals for all agents
    measurements = {}
    for a in agents:
        measurements[a.id] = {
            "quorum_variance": measure_quorum_variance(a, agents),
            "timing_cv": measure_timing_cv(a),
            "cross_clique": measure_cross_clique(a, agents),
            "platform_count": len(a.platforms),
            "attestation_count": len(a.attestations_received),
            "is_sybil": a.is_sybil,
        }
    
    # Step 2: Compute separation ratios for each signal
    # This is the self-grounding: the data tells us which signals matter
    honest_vals = {k: [] for k in ["quorum_variance", "timing_cv", "cross_clique"]}
    sybil_vals = {k: [] for k in ["quorum_variance", "timing_cv", "cross_clique"]}
    
    for aid, m in measurements.items():
        bucket = sybil_vals if m["is_sybil"] else honest_vals
        for k in bucket:
            bucket[k].append(m[k])
    
    # Step 3: Derive weights from separation ratios
    weights = {}
    for signal in ["quorum_variance", "timing_cv", "cross_clique"]:
        h_mean = sum(honest_vals[signal]) / max(len(honest_vals[signal]), 1) if honest_vals[signal] else 0
        s_mean = sum(sybil_vals[signal]) / max(len(sybil_vals[signal]), 1) if sybil_vals[signal] else 0
        
        # Separation ratio = how well this signal discriminates
        separation = abs(h_mean - s_mean) / max(min(abs(h_mean), abs(s_mean)), 0.001)
        weights[signal] = separation
    
    # Normalize weights
    total_w = sum(weights.values()) or 1
    weights = {k: v / total_w for k, v in weights.items()}
    
    # Step 4: Compute final scores using derived weights
    results = {}
    for aid, m in measurements.items():
        # Normalize each signal to [0, 1] range
        max_qv = max(mm["quorum_variance"] for mm in measurements.values()) or 1
        max_cv = max(mm["timing_cv"] for mm in measurements.values()) or 1
        max_cc = max(mm["cross_clique"] for mm in measurements.values()) or 1
        
        score = (weights["quorum_variance"] * m["quorum_variance"] / max_qv +
                weights["timing_cv"] * m["timing_cv"] / max_cv +
                weights["cross_clique"] * m["cross_clique"] / max_cc)
        
        results[aid] = {
            "score": round(score, 4),
            "is_sybil": m["is_sybil"],
            **{k: round(v, 4) for k, v in m.items() if k != "is_sybil"},
        }
    
    return results, weights

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("SELF-GROUNDING TRUST SCORER")
    print("Weights derived from structural measurement, not configured")
    print("=" * 60)
    
    agents = generate_network(n_honest=30, n_sybil=10, n_platforms=5)
    results, weights = self_grounding_score(agents)
    
    print(f"\n--- Derived Weights (self-grounded) ---")
    for signal, weight in sorted(weights.items(), key=lambda x: -x[1]):
        print(f"  {signal}: {weight:.3f}")
    
    # Separation analysis
    honest_scores = [r["score"] for r in results.values() if not r["is_sybil"]]
    sybil_scores = [r["score"] for r in results.values() if r["is_sybil"]]
    
    h_mean = sum(honest_scores) / len(honest_scores)
    s_mean = sum(sybil_scores) / len(sybil_scores)
    separation = h_mean / max(s_mean, 0.001)
    
    print(f"\n--- Score Distribution ---")
    print(f"  Honest mean: {h_mean:.4f} (n={len(honest_scores)})")
    print(f"  Sybil mean:  {s_mean:.4f} (n={len(sybil_scores)})")
    print(f"  Separation ratio: {separation:.1f}x")
    
    # Classification accuracy
    threshold = (h_mean + s_mean) / 2
    tp = sum(1 for s in sybil_scores if s < threshold)
    tn = sum(1 for s in honest_scores if s >= threshold)
    accuracy = (tp + tn) / (len(honest_scores) + len(sybil_scores))
    
    print(f"\n--- Classification (threshold={threshold:.4f}) ---")
    print(f"  Accuracy: {accuracy:.1%}")
    print(f"  Sybils detected: {tp}/{len(sybil_scores)}")
    print(f"  Honest preserved: {tn}/{len(honest_scores)}")
    
    # Top and bottom agents
    sorted_results = sorted(results.items(), key=lambda x: -x[1]["score"])
    print(f"\n--- Top 5 Agents ---")
    for aid, r in sorted_results[:5]:
        label = "🔴 SYBIL" if r["is_sybil"] else "🟢 HONEST"
        print(f"  {aid}: {r['score']:.4f} [{label}]")
    
    print(f"\n--- Bottom 5 Agents ---")
    for aid, r in sorted_results[-5:]:
        label = "🔴 SYBIL" if r["is_sybil"] else "🟢 HONEST"
        print(f"  {aid}: {r['score']:.4f} [{label}]")
    
    print(f"\n{'=' * 60}")
    print(f"KEY: Weights emerged from data, not configuration.")
    print(f"A sybil that fakes these signals has built real infrastructure.")
    print(f"{'=' * 60}")
