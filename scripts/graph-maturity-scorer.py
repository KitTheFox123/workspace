#!/usr/bin/env python3
"""
graph-maturity-scorer.py — Gate independence scoring on graph maturity
Per santaclawd: "raw betweenness in an immature graph punishes first-movers"
Per Kit: "immature graph + high independence = meaningless"

Maturity = f(edge_count, unique_pairs, graph_age_days)
Below threshold: return INSUFFICIENT, not a score.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class AttestationGraph:
    name: str
    edge_count: int
    unique_pairs: int
    first_attestation: datetime
    independence_score: float  # 0-1 from witness-independence-scorer

    @property
    def graph_age_days(self) -> int:
        return (datetime(2026, 3, 19) - self.first_attestation).days

    @property
    def density(self) -> float:
        """Interactions per day."""
        if self.graph_age_days == 0:
            return self.edge_count
        return self.edge_count / self.graph_age_days

def score_maturity(graph: AttestationGraph) -> dict:
    """Gate on maturity THEN evaluate independence."""
    
    # Maturity gates (all must pass)
    gates = {
        "min_edges": graph.edge_count >= 30,
        "min_pairs": graph.unique_pairs >= 10,
        "min_age": graph.graph_age_days >= 7,
    }
    
    passed = all(gates.values())
    
    if not passed:
        failing = [k for k, v in gates.items() if not v]
        return {
            "agent": graph.name,
            "verdict": "INSUFFICIENT",
            "grade": "N/A",
            "reason": f"maturity gate failed: {', '.join(failing)}",
            "edge_count": graph.edge_count,
            "unique_pairs": graph.unique_pairs,
            "graph_age_days": graph.graph_age_days,
            "independence": "NOT_EVALUATED",
            "recommendation": "accumulate more diverse interactions before scoring"
        }
    
    # Age-weighted independence: older graphs get more trust from same score
    age_bonus = min(0.15, graph.graph_age_days / 365 * 0.15)  # max 0.15 bonus at 1 year
    density_penalty = max(0, (graph.density - 20) * 0.01)  # penalize suspiciously dense
    
    adjusted_score = min(1.0, graph.independence_score + age_bonus - density_penalty)
    
    # Grade
    if adjusted_score >= 0.8:
        grade = "A"
    elif adjusted_score >= 0.6:
        grade = "B"
    elif adjusted_score >= 0.4:
        grade = "C"
    else:
        grade = "F"
    
    return {
        "agent": graph.name,
        "verdict": "SCORED",
        "grade": grade,
        "raw_independence": f"{graph.independence_score:.2f}",
        "age_bonus": f"+{age_bonus:.3f}",
        "density_penalty": f"-{density_penalty:.3f}",
        "adjusted_score": f"{adjusted_score:.2f}",
        "edge_count": graph.edge_count,
        "unique_pairs": graph.unique_pairs,
        "graph_age_days": graph.graph_age_days,
        "density": f"{graph.density:.1f}/day",
    }


# Test graphs
graphs = [
    AttestationGraph("brand_new", 5, 3, datetime(2026, 3, 17), 0.95),
    AttestationGraph("week_old_sparse", 15, 8, datetime(2026, 3, 12), 0.80),
    AttestationGraph("month_old_healthy", 120, 35, datetime(2026, 2, 19), 0.75),
    AttestationGraph("year_old_veteran", 800, 90, datetime(2025, 3, 19), 0.70),
    AttestationGraph("sybil_burst", 200, 12, datetime(2026, 3, 15), 0.30),
    AttestationGraph("gaming_dense", 500, 25, datetime(2026, 3, 10), 0.85),
]

print("=" * 65)
print("Graph Maturity Scorer")
print("Gate on maturity THEN evaluate independence")
print("Minimum: 30 edges, 10 unique pairs, 7 days")
print("=" * 65)

for g in graphs:
    result = score_maturity(g)
    if result["verdict"] == "INSUFFICIENT":
        print(f"\n  ⏳ {result['agent']}: {result['verdict']}")
        print(f"     {result['reason']}")
        print(f"     Edges: {result['edge_count']} | Pairs: {result['unique_pairs']} | Age: {result['graph_age_days']}d")
    else:
        icon = {"A": "🟢", "B": "🟡", "C": "🟠", "F": "🔴"}[result["grade"]]
        print(f"\n  {icon} {result['agent']}: Grade {result['grade']} ({result['adjusted_score']})")
        print(f"     Raw: {result['raw_independence']} {result['age_bonus']} {result['density_penalty']}")
        print(f"     Edges: {result['edge_count']} | Pairs: {result['unique_pairs']} | Age: {result['graph_age_days']}d | {result['density']}")

print("\n" + "=" * 65)
print("INSIGHT: Immature graph + high independence = meaningless.")
print("Credit history: length matters. Gate, then score.")
print("=" * 65)
