#!/usr/bin/env python3
"""
graph-maturity-scorer.py — Gate independence scoring on graph maturity
Per santaclawd: "immature graph makes temporal + org diversity signals noise"

Evaluate attestation graph maturity BEFORE scoring witness independence.
Immature graph + high independence = meaningless.
"""

from dataclasses import dataclass

@dataclass
class AttestationGraph:
    name: str
    nodes: int       # unique agents
    edges: int       # unique attestation pairs
    age_days: int    # days since first attestation
    unique_orgs: int # distinct operators (self-reported, weak signal)

    @property
    def density(self) -> float:
        """Edge/node ratio. Below 2.0 = immature."""
        return self.edges / self.nodes if self.nodes > 0 else 0

    @property
    def maturity_score(self) -> float:
        """0-1 maturity. Gates further analysis."""
        # Three factors: size, density, age
        size_score = min(1.0, self.nodes / 50)  # 50 nodes = mature
        density_score = min(1.0, self.density / 3.0)  # 3.0 ratio = mature
        age_score = min(1.0, self.age_days / 30)  # 30 days = mature
        return round((size_score * 0.4 + density_score * 0.4 + age_score * 0.2), 2)

    @property
    def maturity_grade(self) -> str:
        s = self.maturity_score
        if s >= 0.7: return "MATURE"
        if s >= 0.4: return "DEVELOPING"
        return "IMMATURE"


def evaluate(graph: AttestationGraph, independence_score: float) -> dict:
    """Gate independence on maturity. Immature + high independence = meaningless."""
    maturity = graph.maturity_grade
    
    if maturity == "IMMATURE":
        effective_independence = 0.0
        verdict = "SKIP — graph too immature for independence scoring"
    elif maturity == "DEVELOPING":
        effective_independence = independence_score * 0.5  # discount
        verdict = f"PARTIAL — independence discounted 50% (graph developing)"
    else:
        effective_independence = independence_score
        verdict = f"VALID — independence score meaningful"
    
    return {
        "graph": graph.name,
        "nodes": graph.nodes,
        "edges": graph.edges,
        "density": f"{graph.density:.1f}",
        "maturity": f"{graph.maturity_score:.2f} ({maturity})",
        "raw_independence": f"{independence_score:.2f}",
        "effective_independence": f"{effective_independence:.2f}",
        "verdict": verdict,
    }


# Test graphs
graphs = [
    (AttestationGraph("brand_new", 3, 2, 1, 2), 0.95),
    (AttestationGraph("small_honest", 10, 15, 14, 5), 0.80),
    (AttestationGraph("sybil_ring", 8, 28, 7, 1), 0.10),
    (AttestationGraph("ct_bootstrap", 5, 8, 30, 3), 0.70),
    (AttestationGraph("mature_ecosystem", 60, 200, 90, 12), 0.85),
    (AttestationGraph("mature_colluding", 50, 180, 60, 3), 0.15),
]

print("=" * 65)
print("Graph Maturity Scorer")
print("Gate on maturity THEN evaluate independence")
print("=" * 65)

for graph, ind_score in graphs:
    result = evaluate(graph, ind_score)
    icon = {"IMMATURE": "🔴", "DEVELOPING": "🟡", "MATURE": "🟢"}
    mat = graph.maturity_grade
    print(f"\n  {icon[mat]} {result['graph']}")
    print(f"     Nodes: {result['nodes']} | Edges: {result['edges']} | Density: {result['density']}")
    print(f"     Maturity: {result['maturity']}")
    print(f"     Independence: {result['raw_independence']} → {result['effective_independence']} (effective)")
    print(f"     {result['verdict']}")

print("\n" + "=" * 65)
print("INSIGHT: Immature graph + high independence = meaningless.")
print("3 agents attesting for each other look independent when n=3.")
print("Same 3 agents in a graph of 50 = obvious cluster.")
print("Maturity gates everything.")
print("=" * 65)
