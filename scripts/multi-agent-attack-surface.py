#!/usr/bin/env python3
"""multi-agent-attack-surface.py — Combinatorial attack surface calculator.

Per NBER w34836 (Bloom et al., Feb 2026): 69% of firms use AI, 90% report
zero productivity impact. The real risk isn't individual agents — it's the
combinatorial explosion of trust relationships in multi-agent systems.

Each agent-to-agent connection is a potential confused deputy (Hardy 1988).
IETF AIMS: 53% of deployments use static API keys. Per-action receipts
reduce the surface from O(n²) to O(n).

References:
- Bloom et al. (2026): NBER w34836, 6,000 exec survey
- Hardy (1988): Confused Deputy problem
- Perrow (1984): Normal Accidents — interactive complexity
- Brooks (1975): No Silver Bullet — O(n²) interaction surface
"""

import json
import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Agent:
    id: str
    tools: int = 5
    static_keys: bool = True  # IETF AIMS: 53% use static keys
    has_receipts: bool = False
    trust_connections: int = 0


@dataclass
class MultiAgentSystem:
    agents: List[Agent] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.agents)

    @property
    def pairwise_connections(self) -> int:
        """O(n²) trust relationships — Brooks (1975)."""
        return self.n * (self.n - 1) // 2

    @property
    def total_tool_surface(self) -> int:
        """Each tool accessible by each connected agent = multiplicative."""
        return sum(a.tools for a in self.agents) * self.n

    @property
    def static_key_pct(self) -> float:
        """IETF AIMS found 53% — what's ours?"""
        if not self.agents:
            return 0.0
        return sum(1 for a in self.agents if a.static_keys) / self.n

    @property
    def receipt_coverage(self) -> float:
        """Per-action receipts reduce surface from O(n²) to O(n)."""
        if not self.agents:
            return 0.0
        return sum(1 for a in self.agents if a.has_receipts) / self.n

    @property
    def confused_deputy_risk(self) -> float:
        """Hardy (1988): probability of confused deputy in chain.
        
        Each unverified hop adds risk multiplicatively.
        Static keys = no per-action verification.
        Receipts = per-action verification.
        """
        static = sum(1 for a in self.agents if a.static_keys and not a.has_receipts)
        if self.n == 0:
            return 0.0
        # Each static-key agent is a potential confused deputy
        # Risk compounds per hop: 1 - (1 - p)^hops
        p_per_hop = 0.05  # base probability per unverified hop
        hops = static
        return 1.0 - (1.0 - p_per_hop) ** hops

    @property
    def perrow_complexity(self) -> str:
        """Perrow (1984): interactive complexity classification."""
        if self.pairwise_connections > 45:  # >10 agents
            return "TIGHTLY_COUPLED"
        elif self.pairwise_connections > 10:  # >5 agents
            return "INTERACTIVE"
        elif self.pairwise_connections > 3:
            return "LINEAR"
        return "SIMPLE"

    @property
    def grade(self) -> str:
        risk = self.confused_deputy_risk
        coverage = self.receipt_coverage
        static = self.static_key_pct

        if coverage >= 0.9 and static <= 0.1:
            return "A"
        elif coverage >= 0.7 and static <= 0.3:
            return "B"
        elif coverage >= 0.5:
            return "C"
        elif risk < 0.3:
            return "D"
        return "F"

    @property
    def effective_surface(self) -> int:
        """With receipts: O(n). Without: O(n²)."""
        receipt_agents = sum(1 for a in self.agents if a.has_receipts)
        no_receipt = self.n - receipt_agents
        # Receipt agents contribute O(1) surface each
        # Non-receipt agents contribute O(n) surface each
        return receipt_agents + no_receipt * self.n

    def audit(self) -> dict:
        return {
            "agents": self.n,
            "pairwise_connections": self.pairwise_connections,
            "total_tool_surface": self.total_tool_surface,
            "effective_surface": self.effective_surface,
            "surface_reduction": f"{(1 - self.effective_surface / max(self.total_tool_surface, 1)) * 100:.0f}%",
            "static_key_pct": f"{self.static_key_pct:.0%}",
            "receipt_coverage": f"{self.receipt_coverage:.0%}",
            "confused_deputy_risk": f"{self.confused_deputy_risk:.2f}",
            "perrow_complexity": self.perrow_complexity,
            "grade": self.grade,
            "recommendation": self._recommend(),
        }

    def _recommend(self) -> str:
        if self.grade == "A":
            return "SECURED — per-action receipts cover system"
        if self.static_key_pct > 0.5:
            return "CRITICAL — >50% static keys (IETF AIMS baseline). Replace with per-action receipts."
        if self.receipt_coverage < 0.5:
            return "HIGH_RISK — <50% receipt coverage. Confused deputy chains likely."
        if self.perrow_complexity == "TIGHTLY_COUPLED":
            return "COMPLEX — Perrow Normal Accidents territory. Reduce agent count or add receipts."
        return "MODERATE — partial coverage. Prioritize highest-connectivity agents."


def demo():
    print("=" * 60)
    print("SCENARIO 1: Typical multi-agent (no receipts, static keys)")
    print("=" * 60)

    typical = MultiAgentSystem(agents=[
        Agent(id=f"agent_{i}", tools=5, static_keys=True, has_receipts=False)
        for i in range(8)
    ])
    print(json.dumps(typical.audit(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: ATF-compliant (per-action receipts)")
    print("=" * 60)

    secured = MultiAgentSystem(agents=[
        Agent(id=f"agent_{i}", tools=5, static_keys=False, has_receipts=True)
        for i in range(8)
    ])
    print(json.dumps(secured.audit(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Mixed (partial adoption)")
    print("=" * 60)

    mixed = MultiAgentSystem(agents=[
        Agent(id="coordinator", tools=10, static_keys=False, has_receipts=True),
        Agent(id="researcher", tools=8, static_keys=False, has_receipts=True),
        Agent(id="writer", tools=3, static_keys=True, has_receipts=False),
        Agent(id="reviewer", tools=4, static_keys=True, has_receipts=True),
        Agent(id="deployer", tools=6, static_keys=True, has_receipts=False),
    ])
    print(json.dumps(mixed.audit(), indent=2))

    print()
    print("=" * 60)
    print("SCALING: Attack surface growth")
    print("=" * 60)

    for n in [2, 5, 10, 20, 50]:
        no_receipt = MultiAgentSystem(agents=[
            Agent(id=f"a{i}", tools=5, static_keys=True) for i in range(n)
        ])
        with_receipt = MultiAgentSystem(agents=[
            Agent(id=f"a{i}", tools=5, static_keys=False, has_receipts=True) for i in range(n)
        ])
        print(f"  n={n:2d}: no_receipts={no_receipt.pairwise_connections:5d} connections, "
              f"risk={no_receipt.confused_deputy_risk:.2f} | "
              f"with_receipts: effective={with_receipt.effective_surface:3d}, "
              f"risk={with_receipt.confused_deputy_risk:.2f}")


if __name__ == "__main__":
    demo()
