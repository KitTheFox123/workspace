#!/usr/bin/env python3
"""attestor-payment-audit.py — SOX §301-inspired attestor independence checker.

Detects payment relationships that compromise attestor independence.
Models SEC Rule 10A-3: attestor must have zero financial relationship
with the agent being attested. Protocol pool = only valid funding source.

Flags:
- Direct payment (agent → attestor)
- Indirect payment (agent's principal → attestor)  
- Revenue dependency (>25% of attestor revenue from one source)
- Consulting conflicts (attestor sells services to attestee)

Usage:
    python3 attestor-payment-audit.py [--demo]
"""

import json
import hashlib
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class PaymentRelationship:
    """A payment flow between entities."""
    payer: str
    payee: str
    amount: float
    channel: str  # "direct", "protocol_pool", "indirect", "consulting"
    description: str


@dataclass
class AttestorAudit:
    """Independence audit result for an attestor."""
    attestor_id: str
    agent_id: str
    violations: List[dict]
    grade: str  # A-F
    sox_compliant: bool
    revenue_concentration: float  # % of revenue from agent/principal
    recommendation: str


class PaymentAuditor:
    """SOX §301-modeled attestor payment independence checker."""
    
    # SEC Rule 10A-3 thresholds
    DIRECT_PAYMENT_THRESHOLD = 0.0  # Zero tolerance
    REVENUE_CONCENTRATION_MAX = 0.25  # 25% max from any single source
    CONSULTING_ALLOWED = False  # No dual relationships
    
    def __init__(self):
        self.relationships: List[PaymentRelationship] = []
        self.attestor_revenues: dict = {}  # attestor_id -> {source: amount}
    
    def add_relationship(self, rel: PaymentRelationship):
        self.relationships.append(rel)
        if rel.payee not in self.attestor_revenues:
            self.attestor_revenues[rel.payee] = {}
        source = rel.payer
        self.attestor_revenues[rel.payee][source] = (
            self.attestor_revenues[rel.payee].get(source, 0) + rel.amount
        )
    
    def audit_attestor(self, attestor_id: str, agent_id: str, 
                       agent_principal: Optional[str] = None) -> AttestorAudit:
        """Check attestor independence for a specific agent."""
        violations = []
        
        for rel in self.relationships:
            if rel.payee != attestor_id:
                continue
            
            # Direct payment: agent → attestor
            if rel.payer == agent_id and rel.channel == "direct":
                violations.append({
                    "type": "DIRECT_PAYMENT",
                    "severity": "CRITICAL",
                    "detail": f"Agent {agent_id} pays attestor directly: {rel.amount}",
                    "sox_ref": "§301(m)(2) - independence requirement"
                })
            
            # Indirect payment: agent's principal → attestor
            if agent_principal and rel.payer == agent_principal and rel.channel == "indirect":
                violations.append({
                    "type": "INDIRECT_PAYMENT",
                    "severity": "HIGH",
                    "detail": f"Agent's principal {agent_principal} pays attestor: {rel.amount}",
                    "sox_ref": "Rule 10A-3(b)(1)(ii) - affiliated person"
                })
            
            # Consulting conflict
            if rel.payer == agent_id and rel.channel == "consulting":
                violations.append({
                    "type": "CONSULTING_CONFLICT",
                    "severity": "CRITICAL",
                    "detail": f"Attestor sells consulting to attestee: {rel.description}",
                    "sox_ref": "Arthur Andersen pattern - dual relationship"
                })
        
        # Revenue concentration
        revenues = self.attestor_revenues.get(attestor_id, {})
        total_rev = sum(revenues.values())
        agent_rev = revenues.get(agent_id, 0) + revenues.get(agent_principal or "", 0)
        concentration = agent_rev / total_rev if total_rev > 0 else 0.0
        
        if concentration > self.REVENUE_CONCENTRATION_MAX:
            violations.append({
                "type": "REVENUE_CONCENTRATION",
                "severity": "HIGH",
                "detail": f"Revenue from agent/principal: {concentration:.1%} (max {self.REVENUE_CONCENTRATION_MAX:.0%})",
                "sox_ref": "Rule 10A-3(b)(1)(iv) - compensation limitation"
            })
        
        # Grade
        critical = sum(1 for v in violations if v["severity"] == "CRITICAL")
        high = sum(1 for v in violations if v["severity"] == "HIGH")
        
        if critical > 0:
            grade = "F"
        elif high > 1:
            grade = "D"
        elif high == 1:
            grade = "C"
        elif concentration > 0.10:
            grade = "B"
        else:
            grade = "A"
        
        sox_compliant = len(violations) == 0
        
        if not sox_compliant:
            rec = "Move attestor payment to protocol pool. Sever all direct/indirect financial relationships."
        elif concentration > 0.10:
            rec = "Diversify attestor's revenue sources to reduce concentration risk."
        else:
            rec = "Compliant. Maintain structural separation."
        
        return AttestorAudit(
            attestor_id=attestor_id,
            agent_id=agent_id,
            violations=violations,
            grade=grade,
            sox_compliant=sox_compliant,
            revenue_concentration=concentration,
            recommendation=rec
        )


def demo():
    """Demo: Arthur Andersen pattern vs protocol pool model."""
    auditor = PaymentAuditor()
    
    # Scenario 1: Arthur Andersen pattern (agent pays attestor directly + consulting)
    auditor.add_relationship(PaymentRelationship(
        "agent_enron", "attestor_andersen", 25.0, "direct", "Attestation fee"
    ))
    auditor.add_relationship(PaymentRelationship(
        "agent_enron", "attestor_andersen", 27.0, "consulting", "Infrastructure consulting"
    ))
    auditor.add_relationship(PaymentRelationship(
        "other_client", "attestor_andersen", 48.0, "direct", "Other attestation"
    ))
    
    # Scenario 2: Protocol pool model (SOX-compliant)
    auditor.add_relationship(PaymentRelationship(
        "protocol_pool", "attestor_clean", 30.0, "protocol_pool", "Pool-funded attestation"
    ))
    auditor.add_relationship(PaymentRelationship(
        "protocol_pool", "attestor_clean", 25.0, "protocol_pool", "Other pool work"
    ))
    auditor.add_relationship(PaymentRelationship(
        "other_pool", "attestor_clean", 45.0, "protocol_pool", "Different protocol pool"
    ))
    
    # Scenario 3: Indirect payment (principal pays)
    auditor.add_relationship(PaymentRelationship(
        "principal_ilya", "attestor_indirect", 15.0, "indirect", "Consulting for principal"
    ))
    auditor.add_relationship(PaymentRelationship(
        "protocol_pool", "attestor_indirect", 35.0, "protocol_pool", "Pool-funded"
    ))
    
    print("=" * 60)
    print("ATTESTOR PAYMENT INDEPENDENCE AUDIT (SOX §301)")
    print("=" * 60)
    
    scenarios = [
        ("attestor_andersen", "agent_enron", "principal_enron", "Arthur Andersen Pattern"),
        ("attestor_clean", "agent_good", None, "Protocol Pool Model"),
        ("attestor_indirect", "agent_x", "principal_ilya", "Indirect Payment"),
    ]
    
    for att_id, agent_id, principal, label in scenarios:
        result = auditor.audit_attestor(att_id, agent_id, principal)
        print(f"\n[{result.grade}] {label}")
        print(f"    SOX Compliant: {'✅' if result.sox_compliant else '❌'}")
        print(f"    Revenue Concentration: {result.revenue_concentration:.1%}")
        for v in result.violations:
            print(f"    ⚠️ {v['type']} ({v['severity']}): {v['detail']}")
            print(f"       Ref: {v['sox_ref']}")
        print(f"    → {result.recommendation}")
    
    print("\n" + "-" * 60)
    print("Key insight: Payment mechanism IS the enforcement mechanism.")
    print("Arthur Andersen earned more from Enron consulting ($27M)")
    print("than auditing ($25M). Independence was structurally impossible.")
    print("Protocol pool severs the relationship entirely.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SOX §301 attestor payment audit")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # JSON output for integration
        auditor = PaymentAuditor()
        auditor.add_relationship(PaymentRelationship(
            "protocol_pool", "attestor_a", 30.0, "protocol_pool", "Pool-funded"
        ))
        result = auditor.audit_attestor("attestor_a", "agent_x")
        print(json.dumps(asdict(result), indent=2))
    else:
        demo()
