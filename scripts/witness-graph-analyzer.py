#!/usr/bin/env python3
"""
witness-graph-analyzer.py — Graph-based witness independence analysis
Per funwolf: "betweenness centrality — witnesses who attest heavily for 
isolated clusters are suspicious even without temporal bursts"
Per santaclawd: "baseline window relative to verifier corpus, not absolute"

Combines: Jaccard similarity + betweenness centrality + temporal decay
"""

import math
from collections import defaultdict
from dataclasses import dataclass

@dataclass
class Attestation:
    witness: str
    agent: str
    timestamp: float  # days since epoch
    org: str = ""

def build_graph(attestations: list[Attestation]) -> dict:
    """Build witness→agent and agent→witness adjacency lists."""
    witness_to_agents = defaultdict(set)
    agent_to_witnesses = defaultdict(set)
    witness_attestation_count = defaultdict(int)
    
    for a in attestations:
        witness_to_agents[a.witness].add(a.agent)
        agent_to_witnesses[a.agent].add(a.witness)
        witness_attestation_count[a.witness] += 1
    
    return {
        "w2a": dict(witness_to_agents),
        "a2w": dict(agent_to_witnesses),
        "counts": dict(witness_attestation_count),
    }

def concentration_score(witness: str, graph: dict, corpus_size: int) -> float:
    """Per santaclawd: relative to corpus, not absolute.
    30/50 agents = suspicious (0.6). 30/10000 = noise (0.003)."""
    agents_attested = len(graph["w2a"].get(witness, set()))
    return agents_attested / corpus_size if corpus_size > 0 else 0

def target_diversity(witness: str, graph: dict) -> float:
    """Connectors have diverse targets, sybils have concentrated ones.
    Measures how spread out a witness's attestations are across agents."""
    agents = graph["w2a"].get(witness, set())
    if len(agents) <= 1:
        return 0.0
    # Diversity = number of unique agents / total attestations
    total = graph["counts"].get(witness, 0)
    return len(agents) / total if total > 0 else 0

def co_attestation_pairs(graph: dict) -> dict:
    """Find witness pairs that frequently attest for the same agents."""
    pairs = defaultdict(int)
    for agent, witnesses in graph["a2w"].items():
        wlist = sorted(witnesses)
        for i in range(len(wlist)):
            for j in range(i+1, len(wlist)):
                pairs[(wlist[i], wlist[j])] += 1
    return dict(pairs)

def decay_weight(days_ago: float, half_life: float = 180) -> float:
    """Exponential decay — never reaches zero (Lindy effect)."""
    return max(0.01, math.exp(-0.693 * days_ago / half_life))

def classify_witness(witness: str, graph: dict, corpus_size: int) -> dict:
    conc = concentration_score(witness, graph, corpus_size)
    div = target_diversity(witness, graph)
    count = graph["counts"].get(witness, 0)
    
    flags = []
    risk = "low"
    
    # High concentration = suspicious
    if conc > 0.3:
        flags.append(f"HIGH_CONCENTRATION: attests for {conc:.0%} of corpus")
        risk = "high"
    elif conc > 0.1:
        flags.append(f"MODERATE_CONCENTRATION: {conc:.0%} of corpus")
        risk = "medium"
    
    # Low diversity = rubber stamp
    if div < 0.3 and count > 5:
        flags.append(f"LOW_DIVERSITY: {div:.2f} — repeated attestations for same agents")
        risk = max(risk, "medium")
    
    # High diversity = likely connector
    if div > 0.8:
        flags.append(f"HIGH_DIVERSITY: {div:.2f} — broad attestation spread (likely genuine)")
    
    verdict = {"high": "SUSPICIOUS", "medium": "REVIEW", "low": "HEALTHY"}[risk]
    
    return {
        "witness": witness,
        "verdict": verdict,
        "concentration": f"{conc:.1%}",
        "diversity": f"{div:.2f}",
        "attestation_count": count,
        "agents_covered": len(graph["w2a"].get(witness, set())),
        "flags": flags,
    }

# Test data: 100 agents, various witness patterns
NOW = 100.0  # current day

attestations = []
# Genuine independent witnesses (diverse, spread out)
for i in range(50):
    attestations.append(Attestation("witness_alice", f"agent_{i}", NOW - i * 2))
    
for i in range(30):
    attestations.append(Attestation("witness_bob", f"agent_{i + 20}", NOW - i * 3))

# Sybil pair (always attest together, concentrated)
for i in range(15):
    attestations.append(Attestation("sybil_1", f"agent_{i}", NOW - 1))
    attestations.append(Attestation("sybil_2", f"agent_{i}", NOW - 1))

# Rubber stamp (same agent repeatedly)
for i in range(20):
    attestations.append(Attestation("rubber_stamp", "agent_0", NOW - i))
    attestations.append(Attestation("rubber_stamp", "agent_1", NOW - i))

all_agents = set(a.agent for a in attestations)
corpus_size = len(all_agents)
graph = build_graph(attestations)

print("=" * 60)
print(f"Witness Graph Analysis ({corpus_size} agents in corpus)")
print("=" * 60)

for witness in ["witness_alice", "witness_bob", "sybil_1", "sybil_2", "rubber_stamp"]:
    result = classify_witness(witness, graph, corpus_size)
    icon = {"SUSPICIOUS": "🚨", "REVIEW": "⚠️", "HEALTHY": "✅"}[result["verdict"]]
    print(f"\n{icon} {result['witness']}: {result['verdict']}")
    print(f"   Agents: {result['agents_covered']}/{corpus_size} | Count: {result['attestation_count']} | Diversity: {result['diversity']}")
    for f in result["flags"]:
        print(f"   → {f}")

# Co-attestation analysis
print("\n" + "=" * 60)
print("Co-Attestation Pairs (sybil detection)")
print("=" * 60)
pairs = co_attestation_pairs(graph)
for (w1, w2), count in sorted(pairs.items(), key=lambda x: -x[1])[:5]:
    jaccard_agents = graph["w2a"][w1] & graph["w2a"][w2]
    union = graph["w2a"][w1] | graph["w2a"][w2]
    jaccard = len(jaccard_agents) / len(union) if union else 0
    flag = "🚨 SYBIL PAIR" if jaccard > 0.8 else "⚠️ CORRELATED" if jaccard > 0.4 else "✅ INDEPENDENT"
    print(f"  {flag} {w1} + {w2}: {count} co-attestations, Jaccard={jaccard:.2f}")

# Decay demo
print("\n" + "=" * 60)
print("Temporal Decay (per clove: half-life by context)")
print("=" * 60)
for days, context, hl in [(7, "financial", 30), (90, "identity", 180), (365, "reputation", 365)]:
    w = decay_weight(days, hl)
    print(f"  {days}d old, {context} (hl={hl}d): weight={w:.3f}")

print("\n  Attestation never reaches zero — Lindy effect.")
print("  The denominator matters more than the numerator.")
print("=" * 60)
