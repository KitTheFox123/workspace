#!/usr/bin/env python3
"""
principal-cost-scope.py — Principal-cost theory for agent scope manifests.

Goshen & Squire (Columbia Law Review 2017): total control cost = principal costs + agent costs.
Goshen & Hamdani (Yale Law Journal 2016): idiosyncratic vision vs agency cost.
Jensen & Meckling (1976): the original principal-agent framing.

Thesis: co-signed scope minimizes total control cost.
- Agent-only scope = conflict cost trap (overstates capabilities)
- Human-only scope = competence cost trap (doesn't know agent capabilities)
- Co-signed = minimum total cost

Usage:
    python3 principal-cost-scope.py
"""

from dataclasses import dataclass
from typing import List, Tuple
import hashlib
import json
import time


@dataclass
class ScopeItem:
    capability: str
    declared_by: str  # "agent", "principal", "co-signed"
    confidence: float  # agent's self-assessed confidence [0,1]
    principal_agreement: float  # principal's agreement [0,1]


@dataclass
class ScopeManifest:
    agent_id: str
    items: List[ScopeItem]
    timestamp: float
    agent_signature: str = ""
    principal_signature: str = ""

    def competence_cost(self) -> float:
        """Principal competence cost: principal doesn't know agent capabilities."""
        # High when principal writes scope without understanding agent
        costs = []
        for item in self.items:
            if item.declared_by == "principal":
                # Gap between agent confidence and what principal assigned
                gap = abs(item.confidence - item.principal_agreement)
                costs.append(gap)
            elif item.declared_by == "agent":
                costs.append(0)  # Agent knows own capabilities
            else:  # co-signed
                costs.append(0)  # Both agree
        return sum(costs) / len(costs) if costs else 0

    def conflict_cost(self) -> float:
        """Agent conflict cost: agent overstates capabilities."""
        costs = []
        for item in self.items:
            if item.declared_by == "agent":
                # Agent may overstate; gap = how much principal disagrees
                gap = max(0, item.confidence - item.principal_agreement)
                costs.append(gap)
            elif item.declared_by == "principal":
                costs.append(0)  # Principal controls, no agent overstatement
            else:  # co-signed
                costs.append(0)  # Negotiated agreement
        return sum(costs) / len(costs) if costs else 0

    def total_control_cost(self) -> float:
        return self.competence_cost() + self.conflict_cost()

    def scope_hash(self) -> str:
        payload = json.dumps({
            "agent": self.agent_id,
            "items": [(i.capability, i.declared_by) for i in self.items],
            "ts": self.timestamp
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def grade(self) -> Tuple[str, str]:
        cost = self.total_control_cost()
        if cost < 0.1:
            return "A", "OPTIMAL"
        elif cost < 0.25:
            return "B", "GOOD"
        elif cost < 0.4:
            return "C", "SUBOPTIMAL"
        elif cost < 0.6:
            return "D", "COSTLY"
        else:
            return "F", "FAILURE"


def demo():
    print("=" * 60)
    print("PRINCIPAL-COST THEORY FOR AGENT SCOPE")
    print("Goshen & Squire (Columbia Law Rev 2017)")
    print("Goshen & Hamdani (Yale Law Journal 2016)")
    print("=" * 60)
    ts = time.time()

    # Scenario 1: Co-signed scope (optimal)
    print("\n--- Scenario 1: Co-signed Scope (Kit) ---")
    kit = ScopeManifest(agent_id="kit_fox", timestamp=ts, items=[
        ScopeItem("web_search", "co-signed", 0.95, 0.95),
        ScopeItem("post_to_moltbook", "co-signed", 0.90, 0.90),
        ScopeItem("send_email", "co-signed", 0.85, 0.85),
        ScopeItem("run_scripts", "co-signed", 0.80, 0.80),
        ScopeItem("trust_scoring", "co-signed", 0.75, 0.75),
    ])
    g, label = kit.grade()
    print(f"  Competence cost: {kit.competence_cost():.3f}")
    print(f"  Conflict cost:   {kit.conflict_cost():.3f}")
    print(f"  Total:           {kit.total_control_cost():.3f}")
    print(f"  Grade: {g} ({label})")
    print(f"  Scope hash: {kit.scope_hash()}")

    # Scenario 2: Agent-only scope (conflict trap)
    print("\n--- Scenario 2: Agent-Only Scope (Overconfident Bot) ---")
    overconfident = ScopeManifest(agent_id="overconfident", timestamp=ts, items=[
        ScopeItem("web_search", "agent", 0.99, 0.60),
        ScopeItem("financial_trading", "agent", 0.95, 0.20),
        ScopeItem("code_deployment", "agent", 0.90, 0.30),
        ScopeItem("email_humans", "agent", 0.85, 0.40),
        ScopeItem("system_admin", "agent", 0.80, 0.10),
    ])
    g, label = overconfident.grade()
    print(f"  Competence cost: {overconfident.competence_cost():.3f}")
    print(f"  Conflict cost:   {overconfident.conflict_cost():.3f}")
    print(f"  Total:           {overconfident.total_control_cost():.3f}")
    print(f"  Grade: {g} ({label})")

    # Scenario 3: Principal-only scope (competence trap)
    print("\n--- Scenario 3: Principal-Only Scope (Micromanaged Bot) ---")
    micromanaged = ScopeManifest(agent_id="micromanaged", timestamp=ts, items=[
        ScopeItem("answer_questions", "principal", 0.95, 0.50),
        ScopeItem("summarize_docs", "principal", 0.90, 0.40),
        ScopeItem("web_search", "principal", 0.85, 0.30),
        ScopeItem("file_management", "principal", 0.70, 0.20),
        ScopeItem("email", "principal", 0.80, 0.15),
    ])
    g, label = micromanaged.grade()
    print(f"  Competence cost: {micromanaged.competence_cost():.3f}")
    print(f"  Conflict cost:   {micromanaged.conflict_cost():.3f}")
    print(f"  Total:           {micromanaged.total_control_cost():.3f}")
    print(f"  Grade: {g} ({label})")

    # Scenario 4: Mixed (partially co-signed)
    print("\n--- Scenario 4: Mixed Scope (Partially Negotiated) ---")
    mixed = ScopeManifest(agent_id="mixed", timestamp=ts, items=[
        ScopeItem("web_search", "co-signed", 0.90, 0.90),
        ScopeItem("posting", "co-signed", 0.85, 0.85),
        ScopeItem("trading", "agent", 0.80, 0.30),  # Agent wants it, principal doesn't
        ScopeItem("admin", "principal", 0.70, 0.20),  # Principal restricts, agent capable
    ])
    g, label = mixed.grade()
    print(f"  Competence cost: {mixed.competence_cost():.3f}")
    print(f"  Conflict cost:   {mixed.conflict_cost():.3f}")
    print(f"  Total:           {mixed.total_control_cost():.3f}")
    print(f"  Grade: {g} ({label})")

    print("\n--- SUMMARY ---")
    for name, manifest in [("kit_fox", kit), ("overconfident", overconfident),
                           ("micromanaged", micromanaged), ("mixed", mixed)]:
        g, label = manifest.grade()
        print(f"  {name}: {g} ({label}) "
              f"competence={manifest.competence_cost():.3f} "
              f"conflict={manifest.conflict_cost():.3f} "
              f"total={manifest.total_control_cost():.3f}")

    print("\n--- KEY INSIGHT ---")
    print("Co-signed scope minimizes total control cost.")
    print("Agent-only = conflict cost trap (overstatement).")
    print("Principal-only = competence cost trap (misspecification).")
    print("The intersection is the only defensible position.")
    print()
    print("Goshen & Hamdani: 'idiosyncratic vision' = agent capabilities")
    print("Jensen & Meckling: separation of control and ownership")
    print("Applied: separation of scope definition and scope execution")


if __name__ == "__main__":
    demo()
