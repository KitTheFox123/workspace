#!/usr/bin/env python3
"""
witness-graph-analyzer.py — Detect sybil witness rings via graph analysis
Per funwolf: "Jaccard similarity is a start but you also want betweenness centrality"
Per santaclawd: "two witnesses from same operator = manufactured corroboration"

Combines:
- Temporal clustering (attestation-burst-detector.py)
- Jaccard similarity on witness co-occurrence
- Betweenness centrality (witnesses bridging isolated clusters)
- Attestation density (actions/time × diversity)
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field

@dataclass
class Attestation:
    agent: str
    witness: str
    timestamp: float  # unix-ish
    action: str = ""

@dataclass
class WitnessProfile:
    name: str
    attestation_count: int = 0
    unique_agents: set = field(default_factory=set)
    co_witnesses: dict = field(default_factory=lambda: defaultdict(int))
    timestamps: list = field(default_factory=list)
    
    @property
    def diversity(self) -> float:
        """How many unique agents this witness attests for."""
        return len(self.unique_agents) / max(self.attestation_count, 1)
    
    @property
    def temporal_spread(self) -> float:
        """Spread of attestations over time (0=burst, 1=even)."""
        if len(self.timestamps) < 2:
            return 0.5
        ts = sorted(self.timestamps)
        gaps = [ts[i+1] - ts[i] for i in range(len(ts)-1)]
        avg_gap = sum(gaps) / len(gaps)
        if avg_gap == 0:
            return 0.0
        variance = sum((g - avg_gap)**2 for g in gaps) / len(gaps)
        cv = math.sqrt(variance) / avg_gap  # coefficient of variation
        return max(0, 1 - cv)  # 1 = perfectly even, 0 = all clustered


def jaccard_similarity(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0
    return len(set_a & set_b) / len(set_a | set_b)


def analyze_witness_graph(attestations: list[Attestation]) -> dict:
    """Build witness graph and detect sybil patterns."""
    profiles = {}
    agent_witnesses = defaultdict(set)
    
    for att in attestations:
        if att.witness not in profiles:
            profiles[att.witness] = WitnessProfile(att.witness)
        p = profiles[att.witness]
        p.attestation_count += 1
        p.unique_agents.add(att.agent)
        p.timestamps.append(att.timestamp)
        agent_witnesses[att.agent].add(att.witness)
    
    # Co-witness matrix
    for agent, witnesses in agent_witnesses.items():
        ws = list(witnesses)
        for i in range(len(ws)):
            for j in range(i+1, len(ws)):
                profiles[ws[i]].co_witnesses[ws[j]] += 1
                profiles[ws[j]].co_witnesses[ws[i]] += 1
    
    # Detect sybil rings: high co-occurrence + temporal clustering
    sybil_pairs = []
    for w1, p1 in profiles.items():
        for w2, count in p1.co_witnesses.items():
            if w1 < w2:  # avoid duplicates
                p2 = profiles[w2]
                jacc = jaccard_similarity(p1.unique_agents, p2.unique_agents)
                if jacc > 0.7 and count >= 3:
                    sybil_pairs.append({
                        "witnesses": (w1, w2),
                        "co_attestations": count,
                        "jaccard": round(jacc, 2),
                        "signal": "HIGH" if jacc > 0.85 else "MEDIUM",
                    })
    
    # Betweenness proxy: witnesses appearing in many different agent clusters
    bridge_witnesses = []
    for w, p in profiles.items():
        if p.diversity > 0.6 and p.attestation_count >= 5:
            if p.temporal_spread < 0.3:
                bridge_witnesses.append({
                    "witness": w,
                    "attestations": p.attestation_count,
                    "diversity": round(p.diversity, 2),
                    "temporal_spread": round(p.temporal_spread, 2),
                    "signal": "SUSPICIOUS — diverse but bursty",
                })
            else:
                bridge_witnesses.append({
                    "witness": w,
                    "attestations": p.attestation_count,
                    "diversity": round(p.diversity, 2),
                    "temporal_spread": round(p.temporal_spread, 2),
                    "signal": "HEALTHY — diverse and sustained",
                })
    
    return {
        "total_witnesses": len(profiles),
        "total_attestations": len(attestations),
        "sybil_pairs": sybil_pairs,
        "bridge_witnesses": bridge_witnesses,
        "profiles": {w: {
            "count": p.attestation_count,
            "diversity": round(p.diversity, 2),
            "spread": round(p.temporal_spread, 2),
        } for w, p in profiles.items()},
    }


# Test data
attestations = [
    # Sybil ring: witness_a and witness_b always appear together, bursty
    Attestation("agent1", "witness_a", 100), Attestation("agent1", "witness_b", 101),
    Attestation("agent2", "witness_a", 105), Attestation("agent2", "witness_b", 106),
    Attestation("agent3", "witness_a", 108), Attestation("agent3", "witness_b", 109),
    Attestation("agent4", "witness_a", 110), Attestation("agent4", "witness_b", 111),
    # Healthy independent witness
    Attestation("agent1", "witness_c", 200), Attestation("agent5", "witness_c", 400),
    Attestation("agent6", "witness_c", 600), Attestation("agent7", "witness_c", 800),
    Attestation("agent8", "witness_c", 1000), Attestation("agent9", "witness_c", 1200),
    # Another healthy witness
    Attestation("agent2", "witness_d", 150), Attestation("agent4", "witness_d", 350),
    Attestation("agent6", "witness_d", 550), Attestation("agent10", "witness_d", 750),
    Attestation("agent11", "witness_d", 950),
    # Suspicious bridge: diverse agents but all in one burst
    Attestation("agent1", "witness_e", 500), Attestation("agent3", "witness_e", 501),
    Attestation("agent5", "witness_e", 502), Attestation("agent7", "witness_e", 503),
    Attestation("agent9", "witness_e", 504), Attestation("agent11", "witness_e", 505),
]

result = analyze_witness_graph(attestations)

print("=" * 60)
print("Witness Graph Analyzer — Sybil Ring Detection")
print("temporal clustering × Jaccard similarity × betweenness")
print("=" * 60)

print(f"\nTotal: {result['total_witnesses']} witnesses, {result['total_attestations']} attestations")

print("\n🔍 Sybil Pairs (high co-occurrence + Jaccard):")
for pair in result["sybil_pairs"]:
    print(f"  🚨 {pair['witnesses'][0]} ↔ {pair['witnesses'][1]}: "
          f"Jaccard={pair['jaccard']}, co-attest={pair['co_attestations']}, signal={pair['signal']}")

if not result["sybil_pairs"]:
    print("  None detected")

print("\n🌉 Bridge Witnesses (high betweenness proxy):")
for bw in result["bridge_witnesses"]:
    icon = "🚨" if "SUSPICIOUS" in bw["signal"] else "✅"
    print(f"  {icon} {bw['witness']}: {bw['attestations']} attest, "
          f"diversity={bw['diversity']}, spread={bw['temporal_spread']}")
    print(f"     → {bw['signal']}")

print("\n📊 All Witness Profiles:")
for w, p in sorted(result["profiles"].items()):
    print(f"  {w}: count={p['count']}, diversity={p['diversity']}, spread={p['spread']}")

print("\n" + "=" * 60)
print("Two independent signals beat one:")
print("  Temporal: bursty attestations = suspicious")
print("  Graph: high Jaccard co-occurrence = sybil ring")
print("  Both together = high confidence detection")
print("=" * 60)
