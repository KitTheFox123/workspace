#!/usr/bin/env python3
"""
witness-graph-analyzer.py — Detect collusion via witness attestation graphs
Per funwolf: "betweenness centrality catches hub witnesses who bridge isolated sybil clusters"
Per santaclawd: "two witnesses from the same operator = manufactured corroboration"

Combines: Jaccard similarity + betweenness centrality + temporal burst detection.
Three independent signals. Correlated oracles = expensive groupthink.
"""

from collections import defaultdict
from dataclasses import dataclass
import itertools

@dataclass
class Attestation:
    witness: str
    agent: str
    timestamp: int  # epoch seconds
    
def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard index: overlap / union."""
    if not set_a and not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)

def betweenness_centrality_approx(witness_agents: dict[str, set[str]]) -> dict[str, float]:
    """Approximate betweenness: witnesses connecting otherwise-disconnected agent clusters."""
    all_agents = set()
    for agents in witness_agents.values():
        all_agents |= agents
    
    # Build agent-agent graph via shared witnesses
    agent_connections = defaultdict(set)
    for witness, agents in witness_agents.items():
        for a1, a2 in itertools.combinations(agents, 2):
            agent_connections[a1].add(a2)
            agent_connections[a2].add(a1)
    
    # For each witness, count how many agent pairs ONLY connect through them
    scores = {}
    for witness, agents in witness_agents.items():
        exclusive_bridges = 0
        for a1, a2 in itertools.combinations(agents, 2):
            # Would these agents still be connected without this witness?
            other_connections = set()
            for w, wa in witness_agents.items():
                if w != witness and a1 in wa and a2 in wa:
                    other_connections.add(w)
            if not other_connections:
                exclusive_bridges += 1
        total_pairs = len(agents) * (len(agents) - 1) / 2 if len(agents) > 1 else 1
        scores[witness] = exclusive_bridges / total_pairs if total_pairs > 0 else 0
    return scores

def temporal_burst_score(attestations: list[Attestation], window_seconds: int = 60) -> dict[str, float]:
    """Detect witnesses who attest in suspicious bursts."""
    by_witness = defaultdict(list)
    for a in attestations:
        by_witness[a.witness].append(a.timestamp)
    
    scores = {}
    for witness, times in by_witness.items():
        times.sort()
        if len(times) < 2:
            scores[witness] = 0.0
            continue
        bursts = 0
        for i in range(1, len(times)):
            if times[i] - times[i-1] < window_seconds:
                bursts += 1
        scores[witness] = bursts / (len(times) - 1)
    return scores

def analyze_witness_graph(attestations: list[Attestation]) -> dict:
    """Full analysis: Jaccard + betweenness + temporal."""
    # Build witness -> agents map
    witness_agents = defaultdict(set)
    for a in attestations:
        witness_agents[a.witness].add(a.agent)
    
    # Jaccard: pairwise witness similarity
    witnesses = list(witness_agents.keys())
    collusion_pairs = []
    for w1, w2 in itertools.combinations(witnesses, 2):
        j = jaccard_similarity(witness_agents[w1], witness_agents[w2])
        if j > 0.7:
            collusion_pairs.append((w1, w2, j))
    
    # Betweenness
    betweenness = betweenness_centrality_approx(witness_agents)
    
    # Temporal
    temporal = temporal_burst_score(attestations)
    
    # Combined risk per witness
    risks = {}
    for w in witnesses:
        # Collusion score: max Jaccard with any other witness
        max_jaccard = max((j for w1, w2, j in collusion_pairs if w in (w1, w2)), default=0)
        b = betweenness.get(w, 0)
        t = temporal.get(w, 0)
        
        # High betweenness + high Jaccard = sybil hub
        # High temporal = automated attestation
        combined = max_jaccard * 0.4 + b * 0.3 + t * 0.3
        
        risks[w] = {
            "jaccard": round(max_jaccard, 2),
            "betweenness": round(b, 2),
            "temporal_burst": round(t, 2),
            "combined_risk": round(combined, 2),
            "verdict": "SYBIL" if combined > 0.6 else "SUSPICIOUS" if combined > 0.3 else "CLEAN",
            "agents_attested": len(witness_agents[w]),
        }
    
    return {"witnesses": risks, "collusion_pairs": collusion_pairs}


# Test scenario
attestations = [
    # Honest independent witnesses
    Attestation("honest_w1", "agent_a", 1000),
    Attestation("honest_w1", "agent_b", 2000),
    Attestation("honest_w1", "agent_c", 5000),
    Attestation("honest_w2", "agent_b", 1500),
    Attestation("honest_w2", "agent_d", 3000),
    Attestation("honest_w3", "agent_a", 4000),
    Attestation("honest_w3", "agent_e", 6000),
    
    # Sybil ring: same operator, same agents, burst timing
    Attestation("sybil_w1", "agent_x", 100),
    Attestation("sybil_w1", "agent_y", 105),  # 5s apart = burst
    Attestation("sybil_w1", "agent_z", 110),
    Attestation("sybil_w2", "agent_x", 120),  # Same agents as sybil_w1
    Attestation("sybil_w2", "agent_y", 125),
    Attestation("sybil_w2", "agent_z", 130),
    
    # Hub witness: bridges sybil cluster to honest agents
    Attestation("hub_w", "agent_x", 200),
    Attestation("hub_w", "agent_a", 300),
    Attestation("hub_w", "agent_f", 400),
]

result = analyze_witness_graph(attestations)

print("=" * 65)
print("Witness Graph Analyzer")
print("Jaccard(40%) + Betweenness(30%) + Temporal Burst(30%)")
print("=" * 65)

for w, data in sorted(result["witnesses"].items(), key=lambda x: -x[1]["combined_risk"]):
    icon = {"SYBIL": "🚨", "SUSPICIOUS": "⚠️", "CLEAN": "✅"}[data["verdict"]]
    print(f"\n  {icon} {w}: {data['verdict']} (risk={data['combined_risk']})")
    print(f"     Jaccard={data['jaccard']} Betweenness={data['betweenness']} Temporal={data['temporal_burst']}")
    print(f"     Agents attested: {data['agents_attested']}")

if result["collusion_pairs"]:
    print(f"\n  Collusion pairs (Jaccard > 0.7):")
    for w1, w2, j in result["collusion_pairs"]:
        print(f"    {w1} ↔ {w2}: {j:.2f}")

print("\n" + "=" * 65)
print("Three independent signals beat any single metric.")
print("Correlated oracles = expensive groupthink.")
print("=" * 65)
