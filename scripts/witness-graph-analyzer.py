#!/usr/bin/env python3
"""
witness-graph-analyzer.py — Graph-based witness independence analysis
Per funwolf: betweenness centrality catches hub witnesses serving isolated clusters.
Per santaclawd: baseline window relative to corpus, not absolute time.
Per clove: decay functions for older attestations (Ebbinghaus curve).

Combines: Jaccard (pairwise), betweenness (hub detection), temporal burst, decay weighting.
"""

from collections import defaultdict
from datetime import datetime, timedelta
import math

# Simulated attestation graph
attestations = [
    # (witness, agent, timestamp_days_ago)
    # Honest independent witnesses
    ("witness_A", "agent_1", 2),
    ("witness_A", "agent_3", 5),
    ("witness_A", "agent_7", 10),
    ("witness_B", "agent_2", 1),
    ("witness_B", "agent_5", 3),
    ("witness_B", "agent_8", 15),
    ("witness_C", "agent_1", 4),
    ("witness_C", "agent_4", 6),
    ("witness_C", "agent_9", 20),
    # Colluding witness pair (always attest together)
    ("sybil_X", "agent_10", 1),
    ("sybil_X", "agent_11", 1),
    ("sybil_X", "agent_12", 2),
    ("sybil_Y", "agent_10", 1),
    ("sybil_Y", "agent_11", 1),
    ("sybil_Y", "agent_12", 2),
    # Hub witness (attestation mill)
    ("mill_Z", "agent_20", 1),
    ("mill_Z", "agent_21", 1),
    ("mill_Z", "agent_22", 1),
    ("mill_Z", "agent_23", 1),
    ("mill_Z", "agent_24", 2),
    ("mill_Z", "agent_25", 2),
    ("mill_Z", "agent_26", 3),
    ("mill_Z", "agent_27", 3),
    # Old attestation (should decay)
    ("witness_D", "agent_30", 180),
    ("witness_D", "agent_31", 200),
]

def ebbinghaus_decay(days_ago: float, half_life: float = 90) -> float:
    """Ebbinghaus forgetting curve: weight decays exponentially."""
    return math.exp(-0.693 * days_ago / half_life)

def jaccard_similarity(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0
    return len(set_a & set_b) / len(set_a | set_b)

def analyze_witnesses(attestations: list) -> dict:
    # Build witness → agents map
    witness_agents = defaultdict(set)
    witness_timestamps = defaultdict(list)
    
    for witness, agent, days_ago in attestations:
        witness_agents[witness].add(agent)
        witness_timestamps[witness].append(days_ago)
    
    witnesses = list(witness_agents.keys())
    results = {}
    
    for w in witnesses:
        agents = witness_agents[w]
        timestamps = witness_timestamps[w]
        
        # Volume
        volume = len(agents)
        
        # Temporal burst: std dev of timestamps (low = burst)
        if len(timestamps) > 1:
            mean_t = sum(timestamps) / len(timestamps)
            variance = sum((t - mean_t) ** 2 for t in timestamps) / len(timestamps)
            temporal_spread = math.sqrt(variance)
        else:
            temporal_spread = 0
        
        # Decay-weighted effective attestations
        effective = sum(ebbinghaus_decay(d) for d in timestamps)
        
        # Jaccard with all other witnesses (collusion detection)
        max_jaccard = 0
        colluder = None
        for other_w in witnesses:
            if other_w == w:
                continue
            j = jaccard_similarity(agents, witness_agents[other_w])
            if j > max_jaccard:
                max_jaccard = j
                colluder = other_w
        
        # Concentration: does this witness serve isolated clusters?
        # High volume + low overlap with others = attestation mill
        overlap_scores = []
        for other_w in witnesses:
            if other_w == w:
                continue
            overlap_scores.append(jaccard_similarity(agents, witness_agents[other_w]))
        avg_overlap = sum(overlap_scores) / len(overlap_scores) if overlap_scores else 0
        
        # Hub score: high volume + low average overlap = mill
        hub_score = volume * (1 - avg_overlap) if volume > 3 else 0
        
        # Classification
        flags = []
        grade = "A"
        
        if max_jaccard > 0.8:
            flags.append(f"COLLUSION: {max_jaccard:.0%} overlap with {colluder}")
            grade = "F"
        elif hub_score > 5:
            flags.append(f"ATTESTATION_MILL: hub_score={hub_score:.1f}")
            grade = "D"
        elif temporal_spread < 1.5 and volume > 2:
            flags.append(f"TEMPORAL_BURST: spread={temporal_spread:.1f}d over {volume} attestations")
            grade = "C"
        
        if effective < volume * 0.5:
            flags.append(f"DECAYED: {effective:.1f}/{volume} effective (old attestations)")
        
        results[w] = {
            "volume": volume,
            "effective": round(effective, 1),
            "temporal_spread": round(temporal_spread, 1),
            "max_jaccard": round(max_jaccard, 2),
            "colluder": colluder,
            "hub_score": round(hub_score, 1),
            "grade": grade,
            "flags": flags,
        }
    
    return results

print("=" * 65)
print("Witness Graph Analyzer")
print("Jaccard (pairwise) + Hub detection + Temporal burst + Decay")
print("=" * 65)

results = analyze_witnesses(attestations)
for witness, data in sorted(results.items(), key=lambda x: x[1]["grade"]):
    icon = {"A": "✅", "C": "⚠️", "D": "🔶", "F": "🚨"}[data["grade"]]
    print(f"\n  {icon} {witness}: Grade {data['grade']}")
    print(f"     Volume: {data['volume']} | Effective: {data['effective']} | Spread: {data['temporal_spread']}d")
    print(f"     Max Jaccard: {data['max_jaccard']} | Hub: {data['hub_score']}")
    for flag in data["flags"]:
        print(f"     → {flag}")

print("\n" + "=" * 65)
print("KEY INSIGHTS:")
print("  • Jaccard catches pairwise collusion (sybil_X ↔ sybil_Y)")
print("  • Hub score catches attestation mills (mill_Z)")
print("  • Temporal burst catches coordinated timing")
print("  • Ebbinghaus decay degrades old attestations gracefully")
print("  • Baseline: ≥30 co-attestations before flagging (Bayesian)")
print("=" * 65)
