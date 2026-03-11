#!/usr/bin/env python3
"""
liability-allocator.py — Map cert levels to liability allocation.

ALI 2024: "multi-layered supply chain" is the core liability problem for AI.
Cert levels solve it by binding responsibility at certification time.

L0: No cert → nobody liable (responsibility gap)
L1: Self-declared → agent liable (unenforceable)
L2: Human-reviewed → principal liable (current standard)
L3: Continuous attestation → system+issuer jointly liable
L4: DAG governance → governance collective liable

Each incident maps to a cert level, which determines who pays.
"""

from dataclasses import dataclass
from enum import IntEnum


class CertLevel(IntEnum):
    L0 = 0  # No certification
    L1 = 1  # Self-declared
    L2 = 2  # Human-reviewed
    L3 = 3  # Continuous attestation
    L4 = 4  # DAG governance


@dataclass
class LiabilityParty:
    role: str
    share: float  # 0.0-1.0
    enforceable: bool


LIABILITY_MAP = {
    CertLevel.L0: {
        "parties": [],
        "gap": 1.0,
        "description": "No cert = no liability assignment. Full responsibility gap.",
        "ali_category": "Unregulated autonomous system"
    },
    CertLevel.L1: {
        "parties": [LiabilityParty("agent_operator", 1.0, False)],
        "gap": 0.8,  # Self-declared = mostly unenforceable
        "description": "Self-declared cert. Agent claims responsibility. Unenforceable.",
        "ali_category": "Self-certified product"
    },
    CertLevel.L2: {
        "parties": [
            LiabilityParty("human_principal", 0.7, True),
            LiabilityParty("platform_provider", 0.3, True)
        ],
        "gap": 0.1,
        "description": "Human reviews + approves. Principal liable for agent actions.",
        "ali_category": "Human-supervised AI system"
    },
    CertLevel.L3: {
        "parties": [
            LiabilityParty("system_operator", 0.4, True),
            LiabilityParty("cert_issuer", 0.3, True),
            LiabilityParty("attestation_pool", 0.2, True),
            LiabilityParty("human_principal", 0.1, True)
        ],
        "gap": 0.05,
        "description": "Continuous attestation. Joint liability across supply chain.",
        "ali_category": "Monitored autonomous system"
    },
    CertLevel.L4: {
        "parties": [
            LiabilityParty("dag_governance", 0.5, True),
            LiabilityParty("cert_issuer", 0.2, True),
            LiabilityParty("attestation_pool", 0.2, True),
            LiabilityParty("insurance_pool", 0.1, True)
        ],
        "gap": 0.0,
        "description": "DAG governance. Collective liability. No gap.",
        "ali_category": "Fully governed autonomous system"
    }
}


@dataclass
class Incident:
    id: str
    cert_level: CertLevel
    damage_amount: float
    description: str


def allocate_liability(incident: Incident) -> dict:
    """Allocate liability based on cert level."""
    mapping = LIABILITY_MAP[incident.cert_level]
    
    allocations = []
    covered = 0.0
    for party in mapping["parties"]:
        amount = incident.damage_amount * party.share
        allocations.append({
            "party": party.role,
            "amount": round(amount, 2),
            "share": f"{party.share:.0%}",
            "enforceable": party.enforceable
        })
        if party.enforceable:
            covered += party.share
    
    gap_amount = incident.damage_amount * mapping["gap"]
    
    return {
        "incident": incident.id,
        "cert_level": f"L{incident.cert_level}",
        "damage": incident.damage_amount,
        "allocations": allocations,
        "gap_amount": round(gap_amount, 2),
        "gap_percentage": f"{mapping['gap']:.0%}",
        "ali_category": mapping["ali_category"],
        "grade": grade_coverage(mapping["gap"])
    }


def grade_coverage(gap: float) -> str:
    if gap == 0: return "A"
    if gap <= 0.1: return "B"
    if gap <= 0.3: return "C"
    if gap <= 0.5: return "D"
    return "F"


def demo():
    incidents = [
        Incident("INC-001", CertLevel.L0, 10000, "Uncertified agent causes data loss"),
        Incident("INC-002", CertLevel.L1, 5000, "Self-certified agent sends wrong email"),
        Incident("INC-003", CertLevel.L2, 25000, "Human-supervised agent makes bad trade"),
        Incident("INC-004", CertLevel.L3, 50000, "Attested agent drifts from scope"),
        Incident("INC-005", CertLevel.L4, 100000, "DAG-governed agent fails at scale"),
    ]
    
    print("=" * 65)
    print("LIABILITY ALLOCATOR — Cert Level → Responsibility Assignment")
    print("Based on ALI 2024: Principles of Civil Liability for AI")
    print("=" * 65)
    
    total_damage = 0
    total_gap = 0
    
    for inc in incidents:
        result = allocate_liability(inc)
        total_damage += inc.damage_amount
        total_gap += result["gap_amount"]
        
        print(f"\n{'─' * 55}")
        print(f"{result['incident']} | {result['cert_level']} | ${result['damage']:,.0f} | Grade: {result['grade']}")
        print(f"  Category: {result['ali_category']}")
        print(f"  Description: {inc.description}")
        
        if result["allocations"]:
            for a in result["allocations"]:
                enforced = "✓" if a["enforceable"] else "✗"
                print(f"  → {a['party']}: ${a['amount']:,.0f} ({a['share']}) [{enforced}]")
        else:
            print(f"  → NO PARTIES LIABLE")
        
        if result["gap_amount"] > 0:
            print(f"  ⚠ Responsibility gap: ${result['gap_amount']:,.0f} ({result['gap_percentage']})")
    
    print(f"\n{'=' * 65}")
    print(f"PORTFOLIO SUMMARY")
    print(f"  Total damage: ${total_damage:,.0f}")
    print(f"  Total gap: ${total_gap:,.0f} ({total_gap/total_damage:.0%})")
    print(f"  Covered: ${total_damage - total_gap:,.0f} ({(total_damage-total_gap)/total_damage:.0%})")
    print(f"\nKEY INSIGHT: No cert = nobody to sue. The cert IS the")
    print(f"liability contract. ALI 2024 identified 'multi-layered")
    print(f"supply chain' as THE problem. Cert levels solve it.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
