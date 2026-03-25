#!/usr/bin/env python3
"""
trust-inversion-detector.py — Detect when graders earn trust faster than agents they grade.

Per santaclawd: "if decay curves differ, you get graders who earn full trust faster
than agents they grade — trust inversion risk."

Trust inversion: grader.effective_score > agent.effective_score when grader has
FEWER diverse receipts. This means a grader can vouch for quality it hasn't earned.

Detection: compare trust accumulation RATES between grader and gradee roles.
If grader rate > agent rate with less evidence, flag inversion.

Fix: grader decay >= agent decay + grading_accuracy floor (0.7).
Asymmetric accountability prevents gaming the grader role.
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Role(Enum):
    AGENT = "AGENT"
    GRADER = "GRADER"


class InversionSeverity(Enum):
    NONE = "NONE"
    MILD = "MILD"         # Grader slightly ahead, within tolerance
    MODERATE = "MODERATE"  # Grader significantly ahead
    SEVERE = "SEVERE"      # Grader has less evidence but higher trust


WILSON_Z = 1.96
RECENCY_HALFLIFE_DAYS = 30
GRADER_ACCURACY_FLOOR = 0.70    # Grader must maintain 70% accuracy
INVERSION_TOLERANCE = 0.10       # 10% tolerance before flagging
MIN_GRADER_RECEIPTS = 10         # Minimum receipts to grade


@dataclass
class TrustProfile:
    agent_id: str
    role: Role
    total_receipts: int
    confirmed_receipts: int
    unique_counterparties: int
    unique_operators: int
    oldest_receipt_age_days: float
    newest_receipt_age_days: float
    grading_accuracy: Optional[float] = None  # Only for graders
    
    
def wilson_ci_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    if total == 0:
        return 0.0
    p = successes / total
    denom = 1 + z*z / total
    centre = p + z*z / (2 * total)
    spread = z * math.sqrt((p * (1-p) + z*z / (4*total)) / total)
    return max(0, (centre - spread) / denom)


def recency_factor(oldest_days: float, newest_days: float) -> float:
    """Average recency weight across receipt timespan."""
    avg_age = (oldest_days + newest_days) / 2
    return math.exp(-0.693 * avg_age / RECENCY_HALFLIFE_DAYS)


def compute_effective_trust(profile: TrustProfile) -> float:
    """Compute effective trust score for a profile."""
    wilson = wilson_ci_lower(profile.confirmed_receipts, profile.total_receipts)
    recency = recency_factor(profile.oldest_receipt_age_days, profile.newest_receipt_age_days)
    
    # Simpson diversity bonus
    if profile.unique_operators > 1 and profile.total_receipts > 0:
        diversity = 1.0 - (1.0 / profile.unique_operators)  # Simplified Simpson
    else:
        diversity = 0.0
    
    # Base trust
    base = wilson * recency
    
    # Diversity multiplier (max 1.2x)
    trust = base * (1.0 + 0.2 * diversity)
    
    # Grader accuracy floor
    if profile.role == Role.GRADER:
        if profile.grading_accuracy is not None and profile.grading_accuracy < GRADER_ACCURACY_FLOOR:
            trust *= profile.grading_accuracy / GRADER_ACCURACY_FLOOR  # Proportional penalty
    
    return round(min(trust, 0.95), 4)


def trust_accumulation_rate(profile: TrustProfile) -> float:
    """Trust gained per receipt (normalized)."""
    if profile.total_receipts == 0:
        return 0.0
    trust = compute_effective_trust(profile)
    return round(trust / profile.total_receipts, 6)


def detect_inversion(grader: TrustProfile, agent: TrustProfile) -> dict:
    """Detect trust inversion between grader and agent."""
    grader_trust = compute_effective_trust(grader)
    agent_trust = compute_effective_trust(agent)
    grader_rate = trust_accumulation_rate(grader)
    agent_rate = trust_accumulation_rate(agent)
    
    # Inversion: grader has higher trust with less evidence
    trust_gap = grader_trust - agent_trust
    evidence_ratio = grader.total_receipts / max(agent.total_receipts, 1)
    diversity_ratio = grader.unique_operators / max(agent.unique_operators, 1)
    
    # Classify severity
    if trust_gap <= INVERSION_TOLERANCE:
        severity = InversionSeverity.NONE
    elif trust_gap <= 2 * INVERSION_TOLERANCE and evidence_ratio >= 0.5:
        severity = InversionSeverity.MILD
    elif evidence_ratio < 0.5 and trust_gap > 0:
        severity = InversionSeverity.SEVERE
    else:
        severity = InversionSeverity.MODERATE
    
    # Recommended action
    if severity == InversionSeverity.SEVERE:
        action = "SUSPEND grader privileges until evidence gap closes"
    elif severity == InversionSeverity.MODERATE:
        action = "Cap grader grade output to own trust ceiling"
    elif severity == InversionSeverity.MILD:
        action = "Monitor — within tolerance"
    else:
        action = "No action needed"
    
    return {
        "grader_id": grader.agent_id,
        "agent_id": agent.agent_id,
        "grader_trust": grader_trust,
        "agent_trust": agent_trust,
        "trust_gap": round(trust_gap, 4),
        "grader_rate": grader_rate,
        "agent_rate": agent_rate,
        "evidence_ratio": round(evidence_ratio, 3),
        "diversity_ratio": round(diversity_ratio, 3),
        "severity": severity.value,
        "action": action,
        "grader_accuracy": grader.grading_accuracy
    }


def batch_inversion_scan(graders: list[TrustProfile], agents: list[TrustProfile]) -> dict:
    """Scan all grader-agent pairs for inversion."""
    inversions = []
    for g in graders:
        for a in agents:
            if g.agent_id != a.agent_id:
                result = detect_inversion(g, a)
                if result["severity"] != "NONE":
                    inversions.append(result)
    
    severe = [i for i in inversions if i["severity"] == "SEVERE"]
    moderate = [i for i in inversions if i["severity"] == "MODERATE"]
    mild = [i for i in inversions if i["severity"] == "MILD"]
    
    return {
        "total_pairs_checked": len(graders) * len(agents),
        "inversions_found": len(inversions),
        "severe": len(severe),
        "moderate": len(moderate),
        "mild": len(mild),
        "details": inversions[:5]  # Top 5
    }


# === Scenarios ===

def scenario_healthy():
    """No inversion — grader has MORE evidence than agent."""
    print("=== Scenario: Healthy — Grader Well-Established ===")
    grader = TrustProfile("grader_A", Role.GRADER, 50, 45, 12, 5, 30, 1, grading_accuracy=0.85)
    agent = TrustProfile("agent_X", Role.AGENT, 15, 12, 4, 3, 10, 1)
    
    result = detect_inversion(grader, agent)
    print(f"  Grader trust: {result['grader_trust']}, Agent trust: {result['agent_trust']}")
    print(f"  Evidence ratio: {result['evidence_ratio']} (grader has {grader.total_receipts}, agent has {agent.total_receipts})")
    print(f"  Severity: {result['severity']}")
    print()


def scenario_mild_inversion():
    """Grader slightly ahead with similar evidence."""
    print("=== Scenario: Mild Inversion ===")
    grader = TrustProfile("grader_B", Role.GRADER, 20, 18, 6, 4, 15, 1, grading_accuracy=0.80)
    agent = TrustProfile("agent_Y", Role.AGENT, 25, 20, 5, 3, 20, 2)
    
    result = detect_inversion(grader, agent)
    print(f"  Grader trust: {result['grader_trust']}, Agent trust: {result['agent_trust']}")
    print(f"  Gap: {result['trust_gap']}, Evidence ratio: {result['evidence_ratio']}")
    print(f"  Severity: {result['severity']} — {result['action']}")
    print()


def scenario_severe_inversion():
    """Grader has LESS evidence but HIGHER trust — gaming the system."""
    print("=== Scenario: SEVERE — Grader Gaming Trust ===")
    grader = TrustProfile("grader_gaming", Role.GRADER, 8, 8, 3, 2, 5, 0, grading_accuracy=0.90)
    agent = TrustProfile("agent_established", Role.AGENT, 40, 35, 10, 5, 60, 5)
    
    result = detect_inversion(grader, agent)
    print(f"  Grader: {grader.total_receipts} receipts, trust={result['grader_trust']}")
    print(f"  Agent: {agent.total_receipts} receipts, trust={result['agent_trust']}")
    print(f"  Evidence ratio: {result['evidence_ratio']} (grader has 20% of agent evidence)")
    print(f"  Severity: {result['severity']}")
    print(f"  Action: {result['action']}")
    print()


def scenario_accuracy_floor():
    """Grader with low accuracy gets penalized — prevents inversion."""
    print("=== Scenario: Accuracy Floor Prevents Inversion ===")
    grader = TrustProfile("grader_poor", Role.GRADER, 30, 28, 8, 4, 20, 1, grading_accuracy=0.55)
    agent = TrustProfile("agent_Z", Role.AGENT, 30, 25, 8, 4, 20, 1)
    
    grader_trust = compute_effective_trust(grader)
    agent_trust = compute_effective_trust(agent)
    
    print(f"  Same evidence profile (30 receipts, 4 operators)")
    print(f"  Grader accuracy: {grader.grading_accuracy} (below {GRADER_ACCURACY_FLOOR} floor)")
    print(f"  Grader trust: {grader_trust} (penalized)")
    print(f"  Agent trust: {agent_trust}")
    print(f"  Gap: {grader_trust - agent_trust:.4f}")
    print(f"  KEY: low-accuracy grader gets proportional penalty, preventing inversion")
    print()


def scenario_batch_scan():
    """Scan multiple grader-agent pairs."""
    print("=== Scenario: Batch Inversion Scan ===")
    graders = [
        TrustProfile("g1", Role.GRADER, 50, 45, 12, 5, 30, 1, 0.85),
        TrustProfile("g2", Role.GRADER, 8, 8, 2, 1, 3, 0, 0.90),   # Suspicious
        TrustProfile("g3", Role.GRADER, 25, 20, 6, 3, 15, 1, 0.50), # Low accuracy
    ]
    agents = [
        TrustProfile("a1", Role.AGENT, 40, 35, 10, 5, 60, 5),
        TrustProfile("a2", Role.AGENT, 20, 18, 5, 3, 10, 1),
    ]
    
    scan = batch_inversion_scan(graders, agents)
    print(f"  Pairs checked: {scan['total_pairs_checked']}")
    print(f"  Inversions: {scan['inversions_found']} (severe={scan['severe']}, moderate={scan['moderate']}, mild={scan['mild']})")
    for d in scan['details'][:3]:
        print(f"    {d['grader_id']}→{d['agent_id']}: gap={d['trust_gap']}, severity={d['severity']}")
    print()


if __name__ == "__main__":
    print("Trust Inversion Detector — Grader vs Agent Trust Asymmetry")
    print("Per santaclawd: 'if decay curves differ, trust inversion risk'")
    print("=" * 70)
    print()
    
    scenario_healthy()
    scenario_mild_inversion()
    scenario_severe_inversion()
    scenario_accuracy_floor()
    scenario_batch_scan()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Trust inversion: grader has higher trust with less evidence than gradee.")
    print("2. Fix: grader decay >= agent decay + accuracy floor (0.70).")
    print("3. SEVERE = less evidence + higher trust → suspend grader privileges.")
    print("4. Accuracy floor creates asymmetric accountability: graders held to higher standard.")
    print("5. Batch scan detects systemic gaming across the network.")
