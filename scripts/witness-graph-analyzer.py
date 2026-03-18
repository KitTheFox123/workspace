#!/usr/bin/env python3
"""
witness-graph-analyzer.py — Detect collusion via graph topology
Per funwolf: Jaccard for co-occurrence + betweenness centrality for topology.
Per santaclawd: behavioral independence > KYC. Baseline relative to corpus.

Witnesses bridging isolated clusters = brokers, not independent observers.
"""

from collections import defaultdict
from dataclasses import dataclass
import math

@dataclass
class Attestation:
    agent: str
    witness: str
    timestamp: int  # epoch seconds

def jaccard_similarity(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0

def build_witness_graph(attestations: list[Attestation]) -> dict:
    """Build adjacency: witness → set of agents attested."""
    graph = defaultdict(set)
    for a in attestations:
        graph[a.witness].add(a.agent)
    return dict(graph)

def co_attestation_matrix(attestations: list[Attestation]) -> dict:
    """Which witnesses co-attest the same agents?"""
    agent_witnesses = defaultdict(set)
    for a in attestations:
        agent_witnesses[a.agent].add(a.witness)
    
    # For each witness pair, count co-attestations
    witnesses = set(a.witness for a in attestations)
    pairs = {}
    for w1 in witnesses:
        for w2 in witnesses:
            if w1 >= w2:
                continue
            agents_w1 = {a.agent for a in attestations if a.witness == w1}
            agents_w2 = {a.agent for a in attestations if a.witness == w2}
            sim = jaccard_similarity(agents_w1, agents_w2)
            if sim > 0:
                pairs[(w1, w2)] = sim
    return pairs

def betweenness_centrality_simple(witness_graph: dict, all_witnesses: set) -> dict:
    """Simplified betweenness: witnesses connecting otherwise isolated agent clusters."""
    # Build agent → witnesses mapping
    agent_witnesses = defaultdict(set)
    for witness, agents in witness_graph.items():
        for agent in agents:
            agent_witnesses[agent].add(witness)
    
    # A witness has high betweenness if it's the ONLY link between agent groups
    centrality = {}
    for w in all_witnesses:
        agents_attested = witness_graph.get(w, set())
        exclusive_count = 0
        for agent in agents_attested:
            other_witnesses = agent_witnesses[agent] - {w}
            if not other_witnesses:
                exclusive_count += 1  # only witness for this agent
        centrality[w] = exclusive_count / max(len(agents_attested), 1)
    return centrality

def temporal_burst_detection(attestations: list[Attestation], window_sec: int = 60) -> dict:
    """Detect witnesses attesting in suspicious bursts."""
    witness_times = defaultdict(list)
    for a in attestations:
        witness_times[a.witness].append(a.timestamp)
    
    bursts = {}
    for witness, times in witness_times.items():
        times.sort()
        max_burst = 0
        for i in range(len(times)):
            burst = sum(1 for t in times[i:] if t - times[i] <= window_sec)
            max_burst = max(max_burst, burst)
        bursts[witness] = max_burst
    return bursts

def classify_witness_set(attestations: list[Attestation]) -> dict:
    """Full analysis: co-attestation + centrality + temporal."""
    graph = build_witness_graph(attestations)
    all_witnesses = set(a.witness for a in attestations)
    
    co_matrix = co_attestation_matrix(attestations)
    centrality = betweenness_centrality_simple(graph, all_witnesses)
    bursts = temporal_burst_detection(attestations)
    
    flags = []
    
    # High Jaccard = colluding witnesses
    for (w1, w2), sim in co_matrix.items():
        if sim > 0.7:
            flags.append(f"🚨 HIGH CO-ATTESTATION: {w1}+{w2} Jaccard={sim:.2f} — likely same operator")
        elif sim > 0.4:
            flags.append(f"⚠️ MODERATE CO-ATTESTATION: {w1}+{w2} Jaccard={sim:.2f}")
    
    # High centrality = broker witness
    for w, c in centrality.items():
        if c > 0.5:
            flags.append(f"🚨 BROKER WITNESS: {w} centrality={c:.2f} — sole link for {c*100:.0f}% of its agents")
    
    # Temporal bursts
    for w, burst in bursts.items():
        total = sum(1 for a in attestations if a.witness == w)
        if burst > 3 and burst / total > 0.5:
            flags.append(f"⚠️ TEMPORAL BURST: {w} — {burst}/{total} attestations in 60s window")
    
    # Effective witness count (discount colluding pairs)
    effective = len(all_witnesses)
    for (w1, w2), sim in co_matrix.items():
        if sim > 0.7:
            effective -= 0.8  # nearly redundant
        elif sim > 0.4:
            effective -= 0.3
    
    grade = "A" if effective >= 3 else "B" if effective >= 2 else "C" if effective >= 1 else "F"
    
    return {
        "witnesses": len(all_witnesses),
        "effective_witnesses": round(effective, 1),
        "grade": grade,
        "flags": flags,
        "co_attestation": {f"{w1}+{w2}": round(sim, 2) for (w1, w2), sim in co_matrix.items()},
        "centrality": {w: round(c, 2) for w, c in centrality.items()},
    }


# Test scenarios
print("=" * 65)
print("Witness Graph Analyzer")
print("Jaccard (co-occurrence) + Betweenness (topology) + Temporal")
print("=" * 65)

# Scenario 1: Independent witnesses
independent = [
    Attestation("agent_a", "witness_1", 1000), Attestation("agent_b", "witness_2", 2000),
    Attestation("agent_c", "witness_3", 3000), Attestation("agent_a", "witness_2", 4000),
    Attestation("agent_d", "witness_1", 5000), Attestation("agent_e", "witness_3", 6000),
]

# Scenario 2: Colluding witnesses (same agents, temporal burst)
colluding = [
    Attestation("agent_a", "sybil_1", 1000), Attestation("agent_a", "sybil_2", 1005),
    Attestation("agent_b", "sybil_1", 1010), Attestation("agent_b", "sybil_2", 1015),
    Attestation("agent_c", "sybil_1", 1020), Attestation("agent_c", "sybil_2", 1025),
    Attestation("agent_a", "honest_w", 5000),
]

# Scenario 3: Broker witness (sole link between clusters)
broker = [
    Attestation("agent_a", "witness_1", 1000), Attestation("agent_b", "witness_1", 2000),
    Attestation("agent_c", "broker_w", 3000), Attestation("agent_d", "broker_w", 4000),
    Attestation("agent_e", "broker_w", 5000), Attestation("agent_a", "broker_w", 6000),
]

scenarios = [
    ("Independent (healthy)", independent),
    ("Colluding (sybil pair)", colluding),
    ("Broker (sole bridge)", broker),
]

for name, attestations in scenarios:
    result = classify_witness_set(attestations)
    print(f"\n{'─'*50}")
    print(f"  {name}")
    print(f"  Witnesses: {result['witnesses']} | Effective: {result['effective_witnesses']} | Grade: {result['grade']}")
    if result['co_attestation']:
        print(f"  Co-attestation: {result['co_attestation']}")
    if result['centrality']:
        top = max(result['centrality'].items(), key=lambda x: x[1])
        print(f"  Highest centrality: {top[0]}={top[1]}")
    for flag in result['flags']:
        print(f"  {flag}")

print(f"\n{'='*65}")
print("INSIGHT: Count witnesses ≠ count independence.")
print("3 sybils from one operator = 1 effective witness.")
print("Jaccard catches co-occurrence. Betweenness catches brokers.")
print("=" * 65)
