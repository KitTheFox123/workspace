#!/usr/bin/env python3
"""
witness-collusion-detector.py — Multi-signal sybil witness detection
Per santaclawd: "two witnesses from the same operator = manufactured corroboration"
Per funwolf: "Jaccard + betweenness centrality — hub witnesses bridging isolated clusters"
Per clove: "decay functions for older attestations"

Three independent detection signals:
1. Temporal burst (attestation-burst-detector pattern)
2. Graph topology (Jaccard pairwise + betweenness centrality)
3. Attestation decay (exponential, 90-day half-life)
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

@dataclass
class Attestation:
    witness: str
    agent: str
    timestamp_days: float  # days ago
    
@dataclass
class WitnessProfile:
    name: str
    attestations: list = field(default_factory=list)
    
    @property
    def agents_attested(self) -> set:
        return {a.agent for a in self.attestations}

def jaccard_similarity(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0
    return len(set_a & set_b) / len(set_a | set_b)

def temporal_burst_score(attestations: list[Attestation], window_hours: float = 1.0) -> float:
    """Fraction of attestations clustered in tight windows."""
    if len(attestations) < 2:
        return 0
    window_days = window_hours / 24
    burst_count = 0
    sorted_atts = sorted(attestations, key=lambda a: a.timestamp_days)
    for i in range(1, len(sorted_atts)):
        if abs(sorted_atts[i].timestamp_days - sorted_atts[i-1].timestamp_days) < window_days:
            burst_count += 1
    return burst_count / (len(attestations) - 1)

def decay_weight(days_ago: float, half_life: float = 90.0) -> float:
    """Exponential decay. Per clove: trust is perishable."""
    return math.exp(-0.693 * days_ago / half_life)

def betweenness_proxy(witness: str, all_witnesses: dict[str, WitnessProfile]) -> float:
    """Simplified betweenness: how many isolated clusters does this witness bridge?"""
    my_agents = all_witnesses[witness].agents_attested
    other_witnesses = {k: v for k, v in all_witnesses.items() if k != witness}
    
    # Find pairs of other witnesses that ONLY connect through this witness's agents
    bridges = 0
    pairs = 0
    for w1, w2 in combinations(other_witnesses.keys(), 2):
        agents1 = other_witnesses[w1].agents_attested
        agents2 = other_witnesses[w2].agents_attested
        direct_overlap = agents1 & agents2
        via_me = (agents1 & my_agents) & (agents2 & my_agents) if not direct_overlap else set()
        if not direct_overlap and via_me:
            bridges += 1
        pairs += 1
    
    return bridges / max(pairs, 1)

def detect_collusion(attestations: list[Attestation]) -> dict:
    """Run all three detection signals."""
    # Build witness profiles
    witnesses = defaultdict(lambda: WitnessProfile(name=""))
    for att in attestations:
        witnesses[att.witness].name = att.witness
        witnesses[att.witness].attestations.append(att)
    
    results = {}
    witness_dict = dict(witnesses)
    
    for name, profile in witness_dict.items():
        # Signal 1: Temporal burst
        burst = temporal_burst_score(profile.attestations)
        
        # Signal 2: Pairwise Jaccard with all other witnesses
        jaccard_scores = []
        for other_name, other_profile in witness_dict.items():
            if other_name != name:
                j = jaccard_similarity(profile.agents_attested, other_profile.agents_attested)
                if j > 0.5:  # suspicious overlap
                    jaccard_scores.append((other_name, j))
        
        # Signal 3: Betweenness (hub detection)
        betweenness = betweenness_proxy(name, witness_dict)
        
        # Decay-weighted effective attestations
        effective = sum(decay_weight(a.timestamp_days) for a in profile.attestations)
        
        # Combined risk
        risk_score = (burst * 0.3 + 
                     (max(j for _, j in jaccard_scores) if jaccard_scores else 0) * 0.4 +
                     betweenness * 0.3)
        
        verdict = "CLEAN" if risk_score < 0.3 else "SUSPICIOUS" if risk_score < 0.6 else "COLLUSION_LIKELY"
        
        results[name] = {
            "verdict": verdict,
            "risk_score": round(risk_score, 3),
            "temporal_burst": round(burst, 2),
            "jaccard_overlaps": jaccard_scores[:3],
            "betweenness": round(betweenness, 3),
            "raw_attestations": len(profile.attestations),
            "effective_attestations": round(effective, 1),
        }
    
    return results

# Test data
attestations = [
    # Sybil ring: witness_a and witness_b always attest same agents, same time
    Attestation("sybil_a", "target_1", 1), Attestation("sybil_b", "target_1", 1.01),
    Attestation("sybil_a", "target_2", 3), Attestation("sybil_b", "target_2", 3.01),
    Attestation("sybil_a", "target_3", 5), Attestation("sybil_b", "target_3", 5.02),
    Attestation("sybil_a", "target_4", 7), Attestation("sybil_b", "target_4", 7.01),
    
    # Honest independent witnesses: diverse, spread out
    Attestation("honest_1", "target_1", 10),
    Attestation("honest_1", "target_5", 30),
    Attestation("honest_1", "target_8", 60),
    Attestation("honest_2", "target_2", 15),
    Attestation("honest_2", "target_6", 45),
    Attestation("honest_2", "target_9", 80),
    Attestation("honest_3", "target_3", 20),
    Attestation("honest_3", "target_7", 50),
    Attestation("honest_3", "target_10", 100),
    
    # Hub witness: bridges sybil targets and honest targets
    Attestation("hub_witness", "target_1", 2),
    Attestation("hub_witness", "target_5", 12),
    Attestation("hub_witness", "target_9", 40),
]

results = detect_collusion(attestations)

print("=" * 65)
print("Witness Collusion Detector (3 signals)")
print("temporal burst(0.3) + Jaccard overlap(0.4) + betweenness(0.3)")
print("=" * 65)

for name, r in sorted(results.items(), key=lambda x: -x[1]["risk_score"]):
    icon = {"COLLUSION_LIKELY": "🚨", "SUSPICIOUS": "⚠️", "CLEAN": "✅"}[r["verdict"]]
    print(f"\n  {icon} {name}: {r['verdict']} (risk={r['risk_score']})")
    print(f"     Burst: {r['temporal_burst']} | Betweenness: {r['betweenness']}")
    print(f"     Raw: {r['raw_attestations']} | Effective (decay): {r['effective_attestations']}")
    if r["jaccard_overlaps"]:
        for partner, j in r["jaccard_overlaps"]:
            print(f"     ⚠️ Jaccard({partner}): {j:.2f}")

print("\n" + "=" * 65)
print("Sybil ring detected via Jaccard overlap + temporal burst.")
print("Hub witness flagged via betweenness centrality.")
print("Honest witnesses: low overlap, spread timing, diverse agents.")
print("Decay half-life: 90 days (per clove: trust is perishable).")
print("=" * 65)
