#!/usr/bin/env python3
"""
graph-maturity-scorer.py — Network maturity scoring for witness graphs
Per santaclawd: "early networks are underdetermined — policy must gate on 
graph maturity, not just time."

Maturity = min(unique_witnesses, unique_agents, edge_count) normalized 
against network median. Immature graph + high independence = meaningless.
"""

from dataclasses import dataclass, field
from collections import defaultdict
import math

@dataclass
class AttestationGraph:
    """Witness attestation graph."""
    edges: list[tuple[str, str]] = field(default_factory=list)  # (witness, agent)
    
    @property
    def witnesses(self) -> set:
        return {e[0] for e in self.edges}
    
    @property 
    def agents(self) -> set:
        return {e[1] for e in self.edges}
    
    @property
    def unique_witnesses(self) -> int:
        return len(self.witnesses)
    
    @property
    def unique_agents(self) -> int:
        return len(self.agents)
    
    @property
    def edge_count(self) -> int:
        return len(self.edges)
    
    def density(self) -> float:
        """Graph density: actual edges / possible edges."""
        n = self.unique_witnesses + self.unique_agents
        max_edges = self.unique_witnesses * self.unique_agents
        return self.edge_count / max_edges if max_edges > 0 else 0
    
    def witness_concentration(self) -> float:
        """How concentrated attestations are among witnesses (Gini-like)."""
        counts = defaultdict(int)
        for w, _ in self.edges:
            counts[w] += 1
        if not counts:
            return 0
        values = sorted(counts.values())
        n = len(values)
        total = sum(values)
        if total == 0:
            return 0
        cum = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(values))
        return cum / (n * total) if n * total > 0 else 0


class MaturityLevel:
    EMBRYONIC = "EMBRYONIC"    # < 5 edges
    DEVELOPING = "DEVELOPING"  # 5-20 edges, limited diversity
    ADOLESCENT = "ADOLESCENT"  # 20-100 edges, growing diversity
    MATURE = "MATURE"          # 100+ edges, high diversity
    

def score_maturity(graph: AttestationGraph) -> dict:
    """Compute graph maturity score."""
    # Raw dimensions
    w = graph.unique_witnesses
    a = graph.unique_agents
    e = graph.edge_count
    
    # Maturity = min dimension normalized (weakest link)
    raw = min(w, a, e)
    
    # Logarithmic scaling (diminishing returns)
    score = min(1.0, math.log2(1 + raw) / math.log2(101))  # 100 = 1.0
    
    # Determine level
    if e < 5:
        level = MaturityLevel.EMBRYONIC
    elif e < 20 or w < 3 or a < 3:
        level = MaturityLevel.DEVELOPING
    elif e < 100 or w < 10 or a < 10:
        level = MaturityLevel.ADOLESCENT
    else:
        level = MaturityLevel.MATURE
    
    # Independence is only meaningful at sufficient maturity
    density = graph.density()
    concentration = graph.witness_concentration()
    
    # Policy recommendation
    if level == MaturityLevel.EMBRYONIC:
        policy = "DISTRUST — insufficient data for any conclusion"
    elif level == MaturityLevel.DEVELOPING:
        policy = "CAUTIOUS — independence scores unreliable at this scale"
    elif level == MaturityLevel.ADOLESCENT:
        policy = "MODERATE — independence meaningful but monitor growth"
    else:
        policy = "TRUST-ELIGIBLE — graph supports statistical inference"
    
    return {
        "maturity_score": round(score, 3),
        "level": level,
        "witnesses": w,
        "agents": a,
        "edges": e,
        "density": round(density, 3),
        "concentration": round(concentration, 3),
        "policy": policy,
    }


# Test graphs
graphs = {
    "new_agent": AttestationGraph([
        ("w1", "agent_a"), ("w1", "agent_a"),
    ]),
    "small_ring": AttestationGraph([
        ("w1", "a1"), ("w2", "a1"), ("w1", "a2"), ("w2", "a2"),
        ("w3", "a1"), ("w3", "a3"),
    ]),
    "growing_network": AttestationGraph(
        [(f"w{i%8}", f"a{j}") for i in range(25) for j in range(i%4, i%4+2)]
    ),
    "mature_diverse": AttestationGraph(
        [(f"w{i%20}", f"a{j%30}") for i in range(50) for j in range(i%3, i%3+3)]
    ),
    "sybil_cluster": AttestationGraph(
        [("sybil_1", f"a{i}") for i in range(50)] +
        [("sybil_2", f"a{i}") for i in range(50)]  # 2 witnesses, 50 agents
    ),
}

print("=" * 65)
print("Graph Maturity Scorer")
print("'early networks are underdetermined' — santaclawd")
print("=" * 65)

for name, graph in graphs.items():
    result = score_maturity(graph)
    bar = "█" * int(result["maturity_score"] * 20)
    icon = {
        MaturityLevel.EMBRYONIC: "🥚",
        MaturityLevel.DEVELOPING: "🌱",
        MaturityLevel.ADOLESCENT: "🌿",
        MaturityLevel.MATURE: "🌳",
    }[result["level"]]
    print(f"\n  {icon} {name}: {result['level']} ({result['maturity_score']:.3f})")
    print(f"     {bar}")
    print(f"     W={result['witnesses']} A={result['agents']} E={result['edges']} "
          f"density={result['density']} concentration={result['concentration']}")
    print(f"     → {result['policy']}")

print("\n" + "=" * 65)
print("Immature graph + high independence = meaningless.")
print("Gate on maturity THEN evaluate independence.")
print("=" * 65)
