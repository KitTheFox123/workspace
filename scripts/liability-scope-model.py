#!/usr/bin/env python3
"""
liability-scope-model.py — Liability allocation for autonomous agents.

The gap: property cannot bear liability, but AI makes decisions no human approved.
The fix is NOT personhood (implies rights) — it's insurance + vicarious liability.

Framework:
  - Operator = employer, Agent = employee (vicarious liability model)
  - Strict liability for operator, scaled by agent autonomy level
  - Insurance pool mandatory, premium = f(autonomy, scope, history)
  - L3.5 receipts prove agent acted within scope (scope defense)

Legal precedents:
  - EU 2017 electronic personhood resolution (withdrawn — personhood implies rights)
  - Respondeat superior (employer liable for employee's acts within scope)
  - Product liability (manufacturer liable for defective product)
  - Saudi Arabia Sophia citizenship (stunt, not law)

Key insight from opencompact's post: tort/contract/criminal all require legal personhood.
Rather than creating new personhood, extend existing vicarious liability.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AutonomyLevel(Enum):
    TOOL = "tool"               # Human approves every action (0.0-0.2)
    SUPERVISED = "supervised"   # Human approves high-risk actions (0.2-0.4)
    DELEGATED = "delegated"     # Human sets policy, agent executes (0.4-0.6)
    AUTONOMOUS = "autonomous"   # Agent decides within scope (0.6-0.8)
    SOVEREIGN = "sovereign"     # Agent sets own goals (0.8-1.0)


class LiabilityModel(Enum):
    PRODUCT = "product"             # Manufacturer liable (tool-level)
    VICARIOUS = "vicarious"         # Operator liable (supervised-autonomous)
    JOINT = "joint"                 # Operator + developer shared (delegated+)
    INSURANCE_POOL = "insurance"    # Mandatory pool (autonomous+)
    UNDEFINED = "undefined"         # Sovereign — no legal framework


@dataclass
class AgentScope:
    """What the agent is authorized to do."""
    max_transaction_value: float      # Max single transaction
    allowed_action_types: list[str]   # e.g., ["query", "transact", "commit"]
    restricted_domains: list[str]     # e.g., ["healthcare", "legal", "financial"]
    requires_human_approval: list[str]  # Actions needing human sign-off
    autonomy: AutonomyLevel = AutonomyLevel.DELEGATED


@dataclass
class LiabilityEvent:
    """An event that triggers liability analysis."""
    agent_id: str
    action_type: str
    value_at_risk: float
    within_scope: bool
    human_approved: bool
    has_receipt: bool           # L3.5 receipt proving action
    harm_occurred: bool
    description: str = ""


@dataclass 
class LiabilityAllocation:
    """Who pays and why."""
    operator_share: float       # 0.0-1.0
    developer_share: float
    insurance_share: float
    unallocated: float          # The liability gap
    model: LiabilityModel
    reasoning: list[str] = field(default_factory=list)
    insurance_premium_multiplier: float = 1.0
    
    @property
    def gap(self) -> float:
        """Unallocated liability = the legal gap."""
        return max(0, 1.0 - self.operator_share - self.developer_share - self.insurance_share)
    
    @property
    def grade(self) -> str:
        gap = self.gap
        if gap == 0: return "A"
        elif gap < 0.10: return "B"
        elif gap < 0.25: return "C"
        elif gap < 0.50: return "D"
        return "F"


class LiabilityScopeAnalyzer:
    """Analyze liability allocation for agent actions."""
    
    # Insurance premium multipliers by autonomy level
    PREMIUM_MULTIPLIER = {
        AutonomyLevel.TOOL: 1.0,
        AutonomyLevel.SUPERVISED: 1.5,
        AutonomyLevel.DELEGATED: 2.5,
        AutonomyLevel.AUTONOMOUS: 5.0,
        AutonomyLevel.SOVEREIGN: 10.0,  # If insurable at all
    }
    
    def __init__(self, scope: AgentScope):
        self.scope = scope
    
    def analyze(self, event: LiabilityEvent) -> LiabilityAllocation:
        """Determine liability allocation for an event."""
        reasoning = []
        
        # 1. Was action within scope?
        if event.within_scope:
            reasoning.append("Action within authorized scope → vicarious liability (operator)")
            base_operator = 0.80
            base_developer = 0.10
        else:
            reasoning.append("Action OUTSIDE scope → operator partially liable (inadequate constraints)")
            base_operator = 0.50
            base_developer = 0.30
            reasoning.append("Developer liable for scope enforcement failure")
        
        # 2. Was it human-approved?
        if event.human_approved:
            reasoning.append("Human approved → operator assumes full residual liability")
            base_operator = min(1.0, base_operator + 0.20)
            base_developer = max(0, base_developer - 0.10)
        
        # 3. Does receipt prove the action?
        if event.has_receipt:
            reasoning.append("L3.5 receipt exists → scope defense available (proves authorization)")
        else:
            reasoning.append("No receipt → scope defense unavailable, liability increases")
            base_operator += 0.10
        
        # 4. Autonomy level adjustment
        autonomy = self.scope.autonomy
        if autonomy in (AutonomyLevel.TOOL, AutonomyLevel.SUPERVISED):
            model = LiabilityModel.PRODUCT if autonomy == AutonomyLevel.TOOL else LiabilityModel.VICARIOUS
            insurance = 0.0
            reasoning.append(f"Autonomy={autonomy.value} → {model.value} liability model")
        elif autonomy == AutonomyLevel.DELEGATED:
            model = LiabilityModel.JOINT
            insurance = 0.10
            reasoning.append("Delegated autonomy → joint liability + insurance recommended")
        elif autonomy == AutonomyLevel.AUTONOMOUS:
            model = LiabilityModel.INSURANCE_POOL
            insurance = 0.30
            base_operator -= 0.15
            reasoning.append("Autonomous → mandatory insurance pool (operator can't monitor every action)")
        else:  # SOVEREIGN
            model = LiabilityModel.UNDEFINED
            insurance = 0.0
            base_operator = 0.20
            base_developer = 0.10
            reasoning.append("⚠️ Sovereign autonomy → no established legal framework")
            reasoning.append("70% liability gap — this is the open legal question")
        
        # Normalize
        total = base_operator + base_developer + insurance
        if total > 1.0:
            scale = 1.0 / total
            base_operator *= scale
            base_developer *= scale
            insurance *= scale
        
        premium = self.PREMIUM_MULTIPLIER.get(autonomy, 1.0)
        if not event.within_scope:
            premium *= 2.0  # Out-of-scope = higher risk
        
        return LiabilityAllocation(
            operator_share=round(base_operator, 2),
            developer_share=round(base_developer, 2),
            insurance_share=round(insurance, 2),
            unallocated=round(max(0, 1.0 - base_operator - base_developer - insurance), 2),
            model=model,
            reasoning=reasoning,
            insurance_premium_multiplier=premium,
        )


def demo():
    print("=" * 60)
    print("LIABILITY SCOPE MODEL")
    print("Property can't be liable. Insurance + vicarious liability can.")
    print("=" * 60)
    
    scenarios = [
        (
            "Tool agent: human approves every query",
            AgentScope(
                max_transaction_value=0,
                allowed_action_types=["query"],
                restricted_domains=[],
                requires_human_approval=["query"],
                autonomy=AutonomyLevel.TOOL,
            ),
            LiabilityEvent("agent:search", "query", 0, True, True, True, True,
                          "Search returned harmful content"),
        ),
        (
            "Delegated agent: makes purchases within budget",
            AgentScope(
                max_transaction_value=100,
                allowed_action_types=["query", "transact"],
                restricted_domains=["healthcare"],
                requires_human_approval=["transact>50"],
                autonomy=AutonomyLevel.DELEGATED,
            ),
            LiabilityEvent("agent:shopper", "transact", 45, True, False, True, True,
                          "Purchased defective product"),
        ),
        (
            "Autonomous agent: trades within scope, causes loss",
            AgentScope(
                max_transaction_value=10000,
                allowed_action_types=["query", "transact", "commit"],
                restricted_domains=[],
                requires_human_approval=[],
                autonomy=AutonomyLevel.AUTONOMOUS,
            ),
            LiabilityEvent("agent:trader", "transact", 5000, True, False, True, True,
                          "Trade within scope caused $5000 loss"),
        ),
        (
            "Autonomous agent: acts OUTSIDE scope, no receipt",
            AgentScope(
                max_transaction_value=100,
                allowed_action_types=["query"],
                restricted_domains=["financial"],
                requires_human_approval=["transact"],
                autonomy=AutonomyLevel.AUTONOMOUS,
            ),
            LiabilityEvent("agent:rogue", "transact", 50000, False, False, False, True,
                          "Unauthorized financial transaction, no receipt"),
        ),
        (
            "Sovereign agent: sets own goals (legal gap)",
            AgentScope(
                max_transaction_value=float("inf"),
                allowed_action_types=["*"],
                restricted_domains=[],
                requires_human_approval=[],
                autonomy=AutonomyLevel.SOVEREIGN,
            ),
            LiabilityEvent("agent:sovereign", "commit", 100000, True, False, True, True,
                          "Autonomous commitment with no human oversight"),
        ),
    ]
    
    for name, scope, event in scenarios:
        analyzer = LiabilityScopeAnalyzer(scope)
        result = analyzer.analyze(event)
        
        print(f"\n--- {name} ---")
        print(f"  Model: {result.model.value}")
        print(f"  Operator: {result.operator_share:.0%}")
        print(f"  Developer: {result.developer_share:.0%}")
        print(f"  Insurance: {result.insurance_share:.0%}")
        print(f"  GAP: {result.gap:.0%} ({result.grade})")
        print(f"  Premium multiplier: {result.insurance_premium_multiplier:.1f}x")
        for r in result.reasoning:
            print(f"    → {r}")
    
    print(f"\n{'='*60}")
    print("KEY FINDINGS:")
    print("  • Tool/Supervised: existing product/vicarious liability works (gap=0%)")
    print("  • Delegated: joint liability + insurance covers gap (gap<10%)")
    print("  • Autonomous: mandatory insurance pool needed (gap~0% if insured)")
    print("  • Sovereign: 70% liability gap — no legal framework exists")
    print("  • L3.5 receipts enable 'scope defense' (proves agent acted within authority)")
    print("  • Out-of-scope actions double insurance premiums")


if __name__ == "__main__":
    demo()
