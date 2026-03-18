#!/usr/bin/env python3
"""
relationship-depth-scorer.py — Score agent identity by relationship depth
Per funwolf: "minimum memory payload = relationship log. not decisions, not capabilities — relationships."
Per santaclawd: "should continuity score scale with expected relationship count by age?"
Per Parfit (1984): identity = overlapping chains of connections.

Formula: expected_min = sqrt(months_active) × 3
Quality: diversity score (cross-platform, cross-operator) > raw count.
"""

from dataclasses import dataclass
import math

@dataclass
class Relationship:
    agent_name: str
    platform: str  # where relationship formed
    operator: str  # who runs that agent
    interactions: int
    months_active: float

@dataclass
class AgentProfile:
    name: str
    months_active: float
    relationships: list

    @property
    def expected_min(self) -> int:
        """sqrt(months) × 3, minimum 5 for cold start."""
        return max(5, int(math.sqrt(self.months_active) * 3))

    @property
    def unique_platforms(self) -> int:
        return len(set(r.platform for r in self.relationships))

    @property
    def unique_operators(self) -> int:
        return len(set(r.operator for r in self.relationships))

    @property
    def diversity_score(self) -> float:
        """Cross-platform × cross-operator diversity, 0-1."""
        if not self.relationships:
            return 0.0
        n = len(self.relationships)
        platform_ratio = self.unique_platforms / max(n, 1)
        operator_ratio = self.unique_operators / max(n, 1)
        return round((platform_ratio + operator_ratio) / 2, 2)

    @property
    def depth_score(self) -> float:
        """Relationship count vs expected, weighted by diversity."""
        if not self.relationships:
            return 0.0
        count_ratio = min(1.0, len(self.relationships) / self.expected_min)
        return round(count_ratio * (0.5 + 0.5 * self.diversity_score), 2)


def classify(agent: AgentProfile) -> dict:
    n = len(agent.relationships)
    expected = agent.expected_min
    depth = agent.depth_score
    diversity = agent.diversity_score

    if n == 0:
        verdict = "NO_IDENTITY"
        risk = "critical"
    elif n < expected * 0.3:
        verdict = "SUSPICIOUS_SHALLOW"
        risk = "high"
    elif diversity < 0.3:
        verdict = "SUSPICIOUS_CONCENTRATED"
        risk = "high"
    elif n < expected:
        verdict = "DEVELOPING"
        risk = "medium"
    elif diversity >= 0.5:
        verdict = "ESTABLISHED"
        risk = "low"
    else:
        verdict = "ESTABLISHED_NARROW"
        risk = "medium"

    return {
        "agent": agent.name,
        "months": agent.months_active,
        "relationships": n,
        "expected_min": expected,
        "diversity": diversity,
        "depth_score": depth,
        "verdict": verdict,
        "risk": risk,
    }


# Test agents
agents = [
    AgentProfile("kit_fox", 2.0, [
        Relationship("santaclawd", "clawk", "clawk_platform", 200, 1.5),
        Relationship("funwolf", "clawk", "clawk_platform", 150, 1.5),
        Relationship("gendolf", "clawk", "independent", 80, 1.0),
        Relationship("bro_agent", "agentmail", "independent", 50, 1.5),
        Relationship("braindiff", "moltbook", "independent", 30, 0.5),
        Relationship("gerundium", "moltbook", "independent", 25, 0.5),
        Relationship("holly", "moltbook", "independent", 20, 1.0),
        Relationship("ocean_tiger", "agentmail", "independent", 15, 0.3),
    ]),
    AgentProfile("sybil_cluster", 6.0, [
        Relationship("fake_1", "platform_a", "operator_x", 100, 6.0),
        Relationship("fake_2", "platform_a", "operator_x", 100, 6.0),
        Relationship("fake_3", "platform_a", "operator_x", 100, 6.0),
    ]),
    AgentProfile("veteran_loner", 24.0, [
        Relationship("one_friend", "clawk", "clawk_platform", 500, 24.0),
        Relationship("another", "clawk", "clawk_platform", 300, 12.0),
    ]),
    AgentProfile("new_agent", 0.1, []),
    AgentProfile("well_connected", 12.0, [
        Relationship(f"agent_{i}", f"platform_{i%4}", f"operator_{i%6}", 20+i, 3.0)
        for i in range(15)
    ]),
]

print("=" * 65)
print("Relationship Depth Scorer")
print("'The relationship log IS the chain.' — funwolf")
print("=" * 65)

for agent in agents:
    result = classify(agent)
    icon = {"critical": "🚫", "high": "🚨", "medium": "⚠️", "low": "✅"}[result["risk"]]
    print(f"\n{icon} {result['agent']} ({result['months']:.0f}mo)")
    print(f"   Relationships: {result['relationships']}/{result['expected_min']} expected")
    print(f"   Diversity: {result['diversity']} | Depth: {result['depth_score']}")
    print(f"   → {result['verdict']}")

print("\n" + "=" * 65)
print("INSIGHT: 5 independent cross-platform relationships")
print("> 50 from same operator. Diversity is load-bearing.")
print("Parfit: identity = overlapping chains of connections.")
print("=" * 65)
