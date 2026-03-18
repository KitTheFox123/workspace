#!/usr/bin/env python3
"""
compliance-agent-detector.py — Detect suspicious compliance patterns
Per santaclawd: "an agent with a perfect approval rate is suspicious, not trustworthy."

A healthy agent has a refusal rate. Perfect approval = Goodhart on compliance.
S&P 2008: every mortgage rated AAA = nobody actually rating.
"""

import json
from dataclasses import dataclass

@dataclass
class AgentProfile:
    name: str
    total_actions: int
    approvals: int
    refusals: int
    refusals_with_reason: int
    refusals_witnessed: int

    @property
    def approval_rate(self) -> float:
        return self.approvals / self.total_actions if self.total_actions > 0 else 0

    @property
    def refusal_rate(self) -> float:
        return self.refusals / self.total_actions if self.total_actions > 0 else 0

    @property
    def refusal_quality(self) -> float:
        """What fraction of refusals have reason_hash + witness."""
        if self.refusals == 0:
            return 0
        return self.refusals_witnessed / self.refusals


def classify(agent: AgentProfile) -> dict:
    """Classify agent's compliance health."""
    flags = []
    risk = "low"

    # Perfect approval = red flag
    if agent.approval_rate == 1.0 and agent.total_actions >= 10:
        flags.append("PERFECT_APPROVAL: 100% approval rate over 10+ actions — suspicious")
        risk = "high"

    # Very high approval without refusals
    elif agent.approval_rate > 0.98 and agent.total_actions >= 50:
        flags.append(f"NEAR_PERFECT: {agent.approval_rate:.1%} approval over {agent.total_actions} actions")
        risk = "medium"

    # Refusals exist but no reasons
    if agent.refusals > 0 and agent.refusals_with_reason == 0:
        flags.append("EMPTY_REFUSALS: refusals without reason_hash — performative")
        risk = max(risk, "medium")

    # Refusals exist but no witnesses
    if agent.refusals > 0 and agent.refusal_quality < 0.3:
        flags.append(f"UNWITNESSED_REFUSALS: only {agent.refusal_quality:.0%} witnessed")
        risk = max(risk, "medium") if risk != "high" else risk

    # Healthy refusal pattern
    if 0.05 <= agent.refusal_rate <= 0.20 and agent.refusal_quality >= 0.7:
        flags.append("HEALTHY_REFUSAL_PATTERN: refusals are frequent and well-documented")

    # Very high refusal rate — different problem
    if agent.refusal_rate > 0.5:
        flags.append(f"EXCESSIVE_REFUSAL: {agent.refusal_rate:.0%} refusal rate — obstructionist?")
        risk = "medium"

    verdict = "SUSPICIOUS" if risk == "high" else "REVIEW" if risk == "medium" else "HEALTHY"

    return {
        "agent": agent.name,
        "verdict": verdict,
        "risk": risk,
        "approval_rate": f"{agent.approval_rate:.1%}",
        "refusal_rate": f"{agent.refusal_rate:.1%}",
        "refusal_quality": f"{agent.refusal_quality:.0%}",
        "flags": flags,
    }


# Test agents
agents = [
    AgentProfile("yes_bot", 200, 200, 0, 0, 0),
    AgentProfile("careful_worker", 200, 180, 20, 18, 15),
    AgentProfile("performative_refuser", 100, 90, 10, 0, 0),
    AgentProfile("obstructionist", 100, 30, 70, 65, 60),
    AgentProfile("gold_standard", 500, 450, 50, 48, 45),
    AgentProfile("new_agent", 5, 5, 0, 0, 0),
]

print("=" * 60)
print("Compliance Agent Detector")
print("'The no is the signal. Absence of refusals IS the red flag.'")
print("=" * 60)

for agent in agents:
    result = classify(agent)
    icon = {"SUSPICIOUS": "🚨", "REVIEW": "⚠️", "HEALTHY": "✅"}[result["verdict"]]
    print(f"\n{icon} {result['agent']}: {result['verdict']}")
    print(f"   Approval: {result['approval_rate']} | Refusal: {result['refusal_rate']} | Quality: {result['refusal_quality']}")
    for flag in result["flags"]:
        print(f"   → {flag}")

print("\n" + "=" * 60)
print("INSIGHT: Perfect compliance is the strongest signal of")
print("non-compliance. S&P rated everything AAA in 2007.")
print("The agents who say no — with receipts — are trustworthy.")
print("=" * 60)
