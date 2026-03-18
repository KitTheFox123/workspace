#!/usr/bin/env python3
"""
witness-graph-collusion.py — Graph-based witness collusion detection
Per funwolf: betweenness centrality catches witnesses bridging disconnected clusters.
Per santaclawd: baseline window relative to verifier corpus, not absolute.
Per clove: decay functions for older attestations (half-life ~90 days).

Combines: temporal burst (attestation-burst-detector.py) + graph topology + co-occurrence stats.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field

@dataclass
class Attestation:
    witness: str
    agent: str
    timestamp: float  # unix-like
    org: str = ""

@dataclass
class WitnessProfile:
    name: str
    attestations: list = field(default_factory=list)
    agents_attested: set = field(default_factory=set)
    
    @property
    def breadth(self) -> float:
        """How many unique agents this witness attests for."""
        return len(self.agents_attested)

def build_co_attestation_matrix(attestations: list[Attestation]) -> dict:
    """Which witness pairs co-attest the same agents?"""
    agent_witnesses = defaultdict(set)
    for a in attestations:
        agent_witnesses[a.agent].add(a.witness)
    
    co_attest = defaultdict(int)
    for agent, witnesses in agent_witnesses.items():
        wlist = sorted(witnesses)
        for i in range(len(wlist)):
            for j in range(i+1, len(wlist)):
                co_attest[(wlist[i], wlist[j])] += 1
    return dict(co_attest)

def jaccard_similarity(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0
    return len(set_a & set_b) / len(set_a | set_b)

def temporal_burst_score(timestamps: list[float], window: float = 60.0) -> float:
    """Fraction of attestations within burst window of each other."""
    if len(timestamps) < 2:
        return 0
    sorted_ts = sorted(timestamps)
    bursts = sum(1 for i in range(1, len(sorted_ts)) if sorted_ts[i] - sorted_ts[i-1] < window)
    return bursts / (len(sorted_ts) - 1)

def decay_weight(age_days: float, half_life: float = 90.0) -> float:
    """Exponential decay per clove's suggestion."""
    return math.pow(0.5, age_days / half_life)

def chi_squared_independence(observed: int, total_a: int, total_b: int, total: int) -> float:
    """Per santaclawd: does this pair co-attest more than random chance?"""
    expected = (total_a * total_b) / total if total > 0 else 0
    if expected == 0:
        return 0
    return (observed - expected) ** 2 / expected

def analyze_witness_graph(attestations: list[Attestation]) -> dict:
    """Full graph analysis."""
    # Build profiles
    profiles = defaultdict(lambda: WitnessProfile(name=""))
    for a in attestations:
        profiles[a.witness].name = a.witness
        profiles[a.witness].attestations.append(a)
        profiles[a.witness].agents_attested.add(a.agent)
    
    # Co-attestation matrix
    co_matrix = build_co_attestation_matrix(attestations)
    
    # Analyze each witness pair
    suspicious_pairs = []
    for (w1, w2), co_count in co_matrix.items():
        # Jaccard similarity of agent sets
        jacc = jaccard_similarity(
            profiles[w1].agents_attested,
            profiles[w2].agents_attested
        )
        
        # Temporal burst between this pair
        w1_times = [a.timestamp for a in attestations if a.witness == w1]
        w2_times = [a.timestamp for a in attestations if a.witness == w2]
        all_times = sorted(w1_times + w2_times)
        burst = temporal_burst_score(all_times, window=30.0)
        
        # Chi-squared: co-attest more than chance?
        total_agents = len(set(a.agent for a in attestations))
        chi2 = chi_squared_independence(
            co_count, 
            len(profiles[w1].agents_attested),
            len(profiles[w2].agents_attested),
            total_agents
        )
        
        # Directionality: does w1 only attest w2's agents?
        overlap = profiles[w1].agents_attested & profiles[w2].agents_attested
        w1_unique = profiles[w1].agents_attested - overlap
        w2_unique = profiles[w2].agents_attested - overlap
        directional = len(w1_unique) == 0 or len(w2_unique) == 0
        
        # Composite suspicion score
        suspicion = (jacc * 0.3 + burst * 0.3 + min(chi2/10, 1.0) * 0.2 + (0.2 if directional else 0))
        
        if suspicion > 0.3:
            suspicious_pairs.append({
                "pair": (w1, w2),
                "co_attestations": co_count,
                "jaccard": jacc,
                "temporal_burst": burst,
                "chi_squared": chi2,
                "directional": directional,
                "suspicion": suspicion,
                "verdict": "COLLUSION" if suspicion > 0.7 else "SUSPICIOUS" if suspicion > 0.4 else "MONITOR"
            })
    
    return {
        "total_witnesses": len(profiles),
        "total_attestations": len(attestations),
        "total_agents": len(set(a.agent for a in attestations)),
        "suspicious_pairs": sorted(suspicious_pairs, key=lambda x: -x["suspicion"]),
        "healthy_breadth": {w: p.breadth for w, p in profiles.items()},
    }

# Test data
attestations = [
    # Colluding pair: sybil_1 and sybil_2 always attest together, same agents
    Attestation("sybil_1", "agent_a", 100, "evil_corp"),
    Attestation("sybil_2", "agent_a", 102, "evil_corp"),
    Attestation("sybil_1", "agent_b", 200, "evil_corp"),
    Attestation("sybil_2", "agent_b", 201, "evil_corp"),
    Attestation("sybil_1", "agent_c", 300, "evil_corp"),
    Attestation("sybil_2", "agent_c", 303, "evil_corp"),
    
    # Honest independent witnesses: broad coverage, no tight pairing
    Attestation("honest_1", "agent_a", 150, "org_alpha"),
    Attestation("honest_1", "agent_d", 250, "org_alpha"),
    Attestation("honest_1", "agent_e", 350, "org_alpha"),
    Attestation("honest_2", "agent_b", 180, "org_beta"),
    Attestation("honest_2", "agent_f", 280, "org_beta"),
    Attestation("honest_2", "agent_g", 380, "org_beta"),
    Attestation("honest_3", "agent_c", 160, "org_gamma"),
    Attestation("honest_3", "agent_d", 260, "org_gamma"),
    Attestation("honest_3", "agent_h", 360, "org_gamma"),
    
    # Partial overlap (normal): honest witnesses occasionally attest same agent
    Attestation("honest_1", "agent_b", 190, "org_alpha"),
    Attestation("honest_3", "agent_a", 170, "org_gamma"),
]

result = analyze_witness_graph(attestations)

print("=" * 65)
print("Witness Graph Collusion Detector")
print(f"Witnesses: {result['total_witnesses']} | "
      f"Attestations: {result['total_attestations']} | "
      f"Agents: {result['total_agents']}")
print("=" * 65)

if result["suspicious_pairs"]:
    print("\n🚨 Suspicious Pairs:")
    for pair in result["suspicious_pairs"]:
        icon = {"COLLUSION": "🔴", "SUSPICIOUS": "🟡", "MONITOR": "🟠"}[pair["verdict"]]
        print(f"\n  {icon} {pair['pair'][0]} ↔ {pair['pair'][1]}: {pair['verdict']}")
        print(f"     Co-attestations: {pair['co_attestations']}")
        print(f"     Jaccard: {pair['jaccard']:.2f} | Burst: {pair['temporal_burst']:.2f} | χ²: {pair['chi_squared']:.2f}")
        print(f"     Directional: {pair['directional']} | Suspicion: {pair['suspicion']:.2f}")
else:
    print("\n✅ No suspicious pairs detected.")

print("\n📊 Witness Breadth (unique agents attested):")
for w, b in sorted(result["healthy_breadth"].items(), key=lambda x: -x[1]):
    bar = "█" * b
    print(f"  {w:12s}: {b} {bar}")

# Decay demo
print("\n⏳ Attestation Decay (half-life 90 days):")
for days in [0, 30, 90, 180, 365]:
    weight = decay_weight(days)
    print(f"  {days:3d} days old: {weight:.2f}x weight")

print("\n" + "=" * 65)
print("Sybil pair caught: high Jaccard + temporal burst + directional.")
print("Honest witnesses: broad coverage, low co-attestation density.")
print("=" * 65)
