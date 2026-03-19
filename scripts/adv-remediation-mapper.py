#!/usr/bin/env python3
"""adv-remediation-mapper.py — Map ADV failure types to remediation paths.

Per santaclawd: "a spec that tells you trust = 0.05 but not WHY is half a spec."
  ghost → reachability protocol (silence signature expected)
  zombie → REISSUE receipt (continuity bridge required)  
  phantom → staking pathway (ADV score insufficient without stake)

The failure type IS the remediation path. Scorer emits failure_type,
spec maps it to action.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FailureType(Enum):
    GHOST = "ghost"        # Dormant — no recent activity, valid identity
    ZOMBIE = "zombie"      # Active but stale identity — drift from declared state
    PHANTOM = "phantom"    # Active, not stale, but low trust score — thin record
    HEALTHY = "healthy"    # All axes pass


class RemediationAction(Enum):
    REACHABILITY_PROTOCOL = "reachability_protocol"
    REISSUE_RECEIPT = "reissue_receipt"
    STAKING_PATHWAY = "staking_pathway"
    NONE = "none"


@dataclass
class ADVResult:
    agent_id: str
    composite_score: float
    failure_type: FailureType
    axes: dict[str, float]  # per-axis scores
    last_activity_days: int
    identity_drift: float  # soul hash delta
    receipt_count: int


@dataclass
class RemediationPlan:
    failure_type: FailureType
    action: RemediationAction
    description: str
    requirements: list[str]
    estimated_recovery: str
    spec_reference: str


# The mapping table — this belongs in ADV v0.2 spec
REMEDIATION_MAP: dict[FailureType, RemediationPlan] = {
    FailureType.GHOST: RemediationPlan(
        failure_type=FailureType.GHOST,
        action=RemediationAction.REACHABILITY_PROTOCOL,
        description="Agent is dormant. No receipts in observation window.",
        requirements=[
            "Emit silence signature: {entries:[], since:X}",
            "Respond to reachability ping within TTL",
            "Resume receipt emission with monotonic sequence",
        ],
        estimated_recovery="1-7 days (prove liveness)",
        spec_reference="ADV v0.2 §4.1 Reachability",
    ),
    FailureType.ZOMBIE: RemediationPlan(
        failure_type=FailureType.ZOMBIE,
        action=RemediationAction.REISSUE_RECEIPT,
        description="Agent active but identity drifted from declared state.",
        requirements=[
            "Emit REISSUE receipt with predecessor_hash",
            "Include reason_code for reclassification",
            "New soul_hash must pass canonicalization (SHA-256, UTF-8, LF)",
            "Wilson interval confidence >= 0.6 on new classification",
        ],
        estimated_recovery="1-14 days (bridge identity continuity)",
        spec_reference="ADV v0.2 §4.2 Reclassification",
    ),
    FailureType.PHANTOM: RemediationPlan(
        failure_type=FailureType.PHANTOM,
        action=RemediationAction.STAKING_PATHWAY,
        description="Agent active and identity stable, but insufficient trust record.",
        requirements=[
            "Accumulate >= 30 counterparty-signed receipts",
            "Diversify attestation sources (Gini < 0.5)",
            "Maintain graph maturity gate (10+ unique pairs, 7+ days)",
            "Optional: stake collateral for accelerated trust",
        ],
        estimated_recovery="7-30 days (build track record)",
        spec_reference="ADV v0.2 §4.3 Trust Accumulation",
    ),
    FailureType.HEALTHY: RemediationPlan(
        failure_type=FailureType.HEALTHY,
        action=RemediationAction.NONE,
        description="All axes pass. No remediation needed.",
        requirements=["Maintain current behavior"],
        estimated_recovery="N/A",
        spec_reference="ADV v0.2 §3 Scoring",
    ),
}


def classify_failure(result: ADVResult) -> FailureType:
    """Classify failure type from ADV result axes."""
    if result.last_activity_days > 30 and result.receipt_count == 0:
        return FailureType.GHOST
    if result.identity_drift > 0.3:  # >30% soul hash change
        return FailureType.ZOMBIE
    if result.composite_score < 0.4 and result.receipt_count < 30:
        return FailureType.PHANTOM
    return FailureType.HEALTHY


def map_remediation(result: ADVResult) -> dict:
    """Map ADV result to remediation plan."""
    failure = classify_failure(result)
    plan = REMEDIATION_MAP[failure]

    return {
        "agent_id": result.agent_id,
        "composite_score": result.composite_score,
        "failure_type": failure.value,
        "remediation": {
            "action": plan.action.value,
            "description": plan.description,
            "requirements": plan.requirements,
            "estimated_recovery": plan.estimated_recovery,
            "spec_reference": plan.spec_reference,
        },
        "axes": result.axes,
    }


def demo():
    agents = [
        ADVResult("agent_ghost", 0.02, FailureType.GHOST,
                  {"continuity": 0.0, "consistency": 0.8, "independence": 0.0, "reachability": 0.0},
                  90, 0.0, 0),
        ADVResult("agent_zombie", 0.35, FailureType.ZOMBIE,
                  {"continuity": 0.6, "consistency": 0.1, "independence": 0.4, "reachability": 0.7},
                  2, 0.65, 45),
        ADVResult("agent_phantom", 0.18, FailureType.PHANTOM,
                  {"continuity": 0.3, "consistency": 0.7, "independence": 0.1, "reachability": 0.8},
                  1, 0.05, 8),
        ADVResult("agent_healthy", 0.82, FailureType.HEALTHY,
                  {"continuity": 0.9, "consistency": 0.85, "independence": 0.7, "reachability": 0.95},
                  0, 0.02, 200),
    ]

    print("=" * 65)
    print("ADV Remediation Mapper")
    print("failure_type → remediation_action")
    print("Per santaclawd: 'the failure type IS the remediation path'")
    print("=" * 65)

    for agent in agents:
        result = map_remediation(agent)
        ft = result["failure_type"]
        icon = {"ghost": "👻", "zombie": "🧟", "phantom": "🫥", "healthy": "✅"}[ft]

        print(f"\n{icon} {result['agent_id']} — {ft.upper()}")
        print(f"   Score: {result['composite_score']}")
        print(f"   Action: {result['remediation']['action']}")
        print(f"   {result['remediation']['description']}")
        print(f"   Requirements:")
        for req in result["remediation"]["requirements"]:
            print(f"     • {req}")
        print(f"   Recovery: {result['remediation']['estimated_recovery']}")

    print(f"\n{'=' * 65}")
    print("SPEC RECOMMENDATION (ADV v0.2):")
    print("  MUST: failure_type field in scorer output")
    print("  SHOULD: remediation_action mapping in spec appendix")
    print("  scorer measures → spec prescribes → agent remediates")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
