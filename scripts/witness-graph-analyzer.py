#!/usr/bin/env python3
"""
witness-graph-analyzer.py — Graph-based witness independence analysis
Per funwolf: "betweenness centrality — witnesses who attest heavily for 
isolated clusters are suspicious even without temporal bursts"
Per santaclawd: "baseline window relative to verifier corpus"

Combines:
- Jaccard similarity (existing: attestation-burst-detector.py)  
- Betweenness centrality (new: bridge vs captured witnesses)
- Chi-squared co-attestation frequency (santaclawd's statistical test)
- Attestation decay (clove: 90-day half-life for credibility)
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field

@dataclass
class Attestation:
    witness: str
    agent: str
    timestamp: float  # days since epoch
    
@dataclass
class WitnessProfile:
    name: str
    agents_attested: set = field(default_factory=set)
    attestation_count: int = 0
    unique_clusters: int = 0
    betweenness: float = 0.0
    
    @property
    def diversity_score(self) -> float:
        if self.attestation_count == 0:
            return 0
        return len(self.agents_attested) / self.attestation_count

def build_graph(attestations: list[Attestation]) -> dict:
    """Build co-attestation graph: which witnesses attest for the same agents?"""
    # agent → set of witnesses
    agent_witnesses = defaultdict(set)
    for a in attestations:
        agent_witnesses[a.agent].add(a.witness)
    
    # witness co-occurrence matrix
    co_occur = defaultdict(int)
    total_agents = len(agent_witnesses)
    
    for agent, witnesses in agent_witnesses.items():
        witnesses = list(witnesses)
        for i in range(len(witnesses)):
            for j in range(i+1, len(witnesses)):
                pair = tuple(sorted([witnesses[i], witnesses[j]]))
                co_occur[pair] += 1
    
    return agent_witnesses, co_occur, total_agents

def chi_squared_test(pair_count: int, w1_count: int, w2_count: int, total: int) -> float:
    """Chi-squared: does this pair co-attest more than expected by chance?"""
    if total == 0:
        return 0
    expected = (w1_count * w2_count) / total
    if expected == 0:
        return 0
    return (pair_count - expected) ** 2 / expected

def attestation_decay(age_days: float, half_life: float = 90.0) -> float:
    """Credibility weight decays, evidence hash is permanent."""
    return 2 ** (-age_days / half_life)

def simple_betweenness(agent_witnesses: dict, witnesses: set) -> dict:
    """Simplified betweenness: how many agent-pairs does each witness bridge?"""
    witness_agents = defaultdict(set)
    for agent, ws in agent_witnesses.items():
        for w in ws:
            witness_agents[w].add(agent)
    
    betweenness = {}
    agents_list = list(agent_witnesses.keys())
    max_pairs = len(agents_list) * (len(agents_list) - 1) / 2 if len(agents_list) > 1 else 1
    
    for w in witnesses:
        # How many unique agent-pairs does this witness connect?
        w_agents = list(witness_agents[w])
        pairs = len(w_agents) * (len(w_agents) - 1) / 2
        betweenness[w] = pairs / max_pairs if max_pairs > 0 else 0
    
    return betweenness

def analyze(attestations: list[Attestation], current_day: float = 100.0) -> list[dict]:
    """Full witness graph analysis."""
    agent_witnesses, co_occur, total_agents = build_graph(attestations)
    
    # Build witness profiles
    witnesses = set(a.witness for a in attestations)
    profiles = {}
    for w in witnesses:
        p = WitnessProfile(w)
        for a in attestations:
            if a.witness == w:
                p.agents_attested.add(a.agent)
                p.attestation_count += 1
        profiles[w] = p
    
    # Betweenness
    betweenness = simple_betweenness(agent_witnesses, witnesses)
    for w in witnesses:
        profiles[w].betweenness = betweenness.get(w, 0)
    
    # Chi-squared for suspicious pairs
    suspicious_pairs = []
    for pair, count in co_occur.items():
        w1, w2 = pair
        chi2 = chi_squared_test(count, profiles[w1].attestation_count, 
                                profiles[w2].attestation_count, total_agents)
        if chi2 > 3.84:  # p < 0.05
            suspicious_pairs.append((w1, w2, chi2, count))
    
    # Decay-weighted attestation count
    results = []
    for w, p in profiles.items():
        weighted_count = sum(
            attestation_decay(current_day - a.timestamp)
            for a in attestations if a.witness == w
        )
        
        # Classification
        captured = p.diversity_score < 0.3 and p.attestation_count > 5
        bridge = p.betweenness > 0.3
        suspicious = any(w in (s[0], s[1]) for s in suspicious_pairs)
        
        if captured:
            grade = "F — CAPTURED"
        elif suspicious:
            grade = "C — SUSPICIOUS CORRELATION"  
        elif bridge:
            grade = "A — BRIDGE WITNESS"
        elif p.diversity_score > 0.6:
            grade = "A — DIVERSE"
        else:
            grade = "B — NORMAL"
        
        results.append({
            "witness": w,
            "raw_count": p.attestation_count,
            "weighted_count": round(weighted_count, 1),
            "agents": len(p.agents_attested),
            "diversity": round(p.diversity_score, 2),
            "betweenness": round(p.betweenness, 3),
            "grade": grade,
        })
    
    return sorted(results, key=lambda x: x["diversity"], reverse=True), suspicious_pairs

# Test data
attestations = [
    # Independent bridge witness — attests across many agents
    *[Attestation("bridge_w", f"agent_{i}", 90+i) for i in range(8)],
    # Diverse witness
    *[Attestation("diverse_w", f"agent_{i}", 80+i) for i in range(5)],
    # Captured witness pair — only attest for same 2 agents
    *[Attestation("captured_w1", "agent_0", 50+i) for i in range(10)],
    *[Attestation("captured_w2", "agent_0", 51+i) for i in range(10)],
    *[Attestation("captured_w1", "agent_1", 55+i) for i in range(8)],
    *[Attestation("captured_w2", "agent_1", 56+i) for i in range(8)],
    # Normal witness
    *[Attestation("normal_w", f"agent_{i}", 70+i*2) for i in range(3)],
]

results, suspicious = analyze(attestations, current_day=100)

print("=" * 65)
print("Witness Graph Analyzer")
print("Betweenness centrality + chi-squared co-attestation + decay")
print("=" * 65)

for r in results:
    icon = "🔗" if "BRIDGE" in r["grade"] else "✅" if "DIVERSE" in r["grade"] else "⚠️" if "NORMAL" in r["grade"] else "🚨"
    print(f"\n  {icon} {r['witness']}: {r['grade']}")
    print(f"     Raw: {r['raw_count']} | Decay-weighted: {r['weighted_count']} | Agents: {r['agents']}")
    print(f"     Diversity: {r['diversity']} | Betweenness: {r['betweenness']}")

if suspicious:
    print(f"\n⚠️  Suspicious pairs (χ² > 3.84):")
    for w1, w2, chi2, count in suspicious:
        print(f"    {w1} + {w2}: χ²={chi2:.1f}, co-attested {count} agents")

print("\n" + "=" * 65)
print("Credibility decays (90-day half-life). Evidence hash doesn't.")
print("Bridge witnesses > captured witnesses. Always.")
print("=" * 65)
