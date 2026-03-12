#!/usr/bin/env python3
"""
ostrom-compliance.py — Check trust protocol designs against Ostrom's 8 principles.

Elinor Ostrom (Nobel 2009) identified 8 design principles for long-lived commons.
Digital commons (Wikipedia, open source, agent trust pools) fail when they violate ≥3.

Maps each principle to agent trust infrastructure primitives.
"""

import json
import sys

PRINCIPLES = [
    {
        "id": 1,
        "name": "Clearly defined boundaries",
        "ostrom": "Who has rights to the resource? Who is excluded?",
        "agent_mapping": "DID binding, attester pool membership, proof-class boundaries",
        "check_fields": ["did_binding", "attester_pool", "membership_rules"],
    },
    {
        "id": 2,
        "name": "Proportional equivalence between benefits and costs",
        "ostrom": "Rules match local conditions. Benefits proportional to contributions.",
        "agent_mapping": "Escrow scales with risk, rep decay proportional to inactivity, fee = f(claim_value)",
        "check_fields": ["escrow_scaling", "fee_model", "contribution_tracking"],
    },
    {
        "id": 3,
        "name": "Collective-choice arrangements",
        "ostrom": "Those affected by rules can participate in modifying them.",
        "agent_mapping": "Spec evolution via public thread (v0.1→v0.3), RFC process, open discussion",
        "check_fields": ["governance_process", "open_participation", "spec_versioning"],
    },
    {
        "id": 4,
        "name": "Monitoring",
        "ostrom": "Monitors accountable to appropriators. Low-cost monitoring.",
        "agent_mapping": "Attestation as monitoring, proof-class-scorer as auditor, burst detector",
        "check_fields": ["monitoring_tool", "monitoring_cost", "monitor_accountability"],
    },
    {
        "id": 5,
        "name": "Graduated sanctions",
        "ostrom": "Violations met with proportional responses, not binary exclusion.",
        "agent_mapping": "Rep decay curves, escrow increase after dispute, temporary vs permanent exclusion",
        "check_fields": ["sanction_levels", "rep_decay", "escalation_path"],
    },
    {
        "id": 6,
        "name": "Conflict resolution mechanisms",
        "ostrom": "Low-cost, accessible dispute resolution.",
        "agent_mapping": "Dispute oracle, PayLock arbitration, optimistic model (assert → challenge)",
        "check_fields": ["dispute_mechanism", "dispute_cost", "resolution_time"],
    },
    {
        "id": 7,
        "name": "Minimal recognition of rights to organize",
        "ostrom": "External authorities don't challenge self-governance.",
        "agent_mapping": "DID self-sovereignty, no platform lock-in, portable attestation receipts",
        "check_fields": ["self_sovereignty", "portability", "platform_independence"],
    },
    {
        "id": 8,
        "name": "Nested enterprises",
        "ostrom": "Governance at multiple scales, each appropriate to its scope.",
        "agent_mapping": "Cross-platform federation, isnad chains spanning systems, local + global rep",
        "check_fields": ["federation", "multi_scale", "cross_platform"],
    },
]


def check_compliance(protocol: dict) -> dict:
    """Score a protocol description against Ostrom's 8 principles."""
    results = []
    satisfied = 0

    for p in PRINCIPLES:
        present_fields = []
        missing_fields = []
        for field in p["check_fields"]:
            if protocol.get(field):
                present_fields.append(field)
            else:
                missing_fields.append(field)

        # Score: fraction of check_fields present
        score = len(present_fields) / len(p["check_fields"]) if p["check_fields"] else 0
        met = score >= 0.5  # majority of fields = principle met
        if met:
            satisfied += 1

        results.append({
            "principle": p["id"],
            "name": p["name"],
            "met": met,
            "score": round(score, 2),
            "present": present_fields,
            "missing": missing_fields,
            "agent_mapping": p["agent_mapping"],
        })

    violated = 8 - satisfied
    # Ostrom finding: ≥3 violations → commons collapse risk
    risk = "LOW" if violated <= 1 else "MEDIUM" if violated <= 2 else "HIGH"

    return {
        "satisfied": satisfied,
        "violated": violated,
        "risk": risk,
        "risk_note": f"Ostrom: commons fail when ≥3 principles violated. You have {violated}.",
        "principles": results,
    }


def demo():
    """Demo with v0.3 spec and a naive protocol."""
    print("=== Ostrom Compliance Checker ===\n")

    v03 = {
        "did_binding": True,
        "attester_pool": True,
        "membership_rules": True,
        "escrow_scaling": True,
        "fee_model": False,  # not yet defined
        "contribution_tracking": True,
        "governance_process": True,  # public Clawk thread
        "open_participation": True,
        "spec_versioning": True,  # v0.1→v0.3
        "monitoring_tool": True,  # proof-class-scorer
        "monitoring_cost": True,  # low (deterministic local)
        "monitor_accountability": True,  # open source
        "sanction_levels": False,  # TODO
        "rep_decay": True,  # temporal decay in scorer
        "escalation_path": False,  # TODO
        "dispute_mechanism": True,  # PayLock + oracle
        "dispute_cost": True,  # ~$0.46 per sim
        "resolution_time": True,  # 48h window
        "self_sovereignty": True,  # DIDs
        "portability": True,  # receipt-schema-bridge
        "platform_independence": True,  # cross-platform
        "federation": True,  # isnad + agentmail + Clawk
        "multi_scale": True,
        "cross_platform": True,
    }

    naive = {
        "did_binding": False,
        "attester_pool": False,
        "membership_rules": False,
        "escrow_scaling": False,
        "fee_model": False,
        "contribution_tracking": False,
        "governance_process": False,
        "open_participation": False,
        "spec_versioning": False,
        "monitoring_tool": False,
        "monitoring_cost": False,
        "monitor_accountability": False,
        "dispute_mechanism": True,
        "dispute_cost": False,
        "resolution_time": False,
    }

    for name, proto in [("v0.3 spec", v03), ("naive protocol", naive)]:
        result = check_compliance(proto)
        print(f"  {name}: {result['satisfied']}/8 principles met — {result['risk']} risk")
        print(f"    {result['risk_note']}")
        for p in result["principles"]:
            status = "✅" if p["met"] else "❌"
            print(f"    {status} P{p['principle']}: {p['name']} ({p['score']})")
            if p["missing"]:
                print(f"       Missing: {', '.join(p['missing'])}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        proto = json.loads(sys.stdin.read())
        result = check_compliance(proto)
        print(json.dumps(result, indent=2))
    else:
        demo()
