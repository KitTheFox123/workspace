#!/usr/bin/env python3
"""dispute-escalation-router.py — Ury/Brett/Goldberg dispute resolution for agent attestation.

Three-tier escalation: interests (cheap) → rights (deterministic) → power (expensive).
Routes agent disputes to cheapest effective mechanism.

Based on:
- Ury, Brett & Goldberg (1988): Getting Disputes Resolved
- Kleros/UMA oracle models
- Brier-scored calibration

Usage:
    python3 dispute-escalation-router.py [--demo]
"""

import json
import hashlib
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class Dispute:
    """An attestation dispute."""
    id: str
    claim_type: str  # "scope" or "quality"
    claimant: str
    respondent: str
    evidence: dict
    
    
@dataclass 
class Resolution:
    """Resolution result."""
    dispute_id: str
    tier: str  # "interests" | "rights" | "power"
    mechanism: str
    cost: float  # relative cost units
    outcome: str
    confidence: float
    escalation_path: List[str]


class DisputeRouter:
    """Routes disputes through Ury/Brett/Goldberg escalation tiers."""
    
    TIERS = {
        "interests": {
            "description": "Brier-calibrated market resolution",
            "cost": 1.0,
            "mechanisms": ["brier_calibration", "market_pricing", "reputation_history"],
            "handles": ["quality", "behavioral"],
            "resolution_time": "minutes",
        },
        "rights": {
            "description": "Deterministic hash/scope comparison",
            "cost": 5.0,
            "mechanisms": ["hash_comparison", "scope_manifest_check", "ttl_validation"],
            "handles": ["scope", "capability", "expiry"],
            "resolution_time": "seconds",
        },
        "power": {
            "description": "Kleros-style escalating jury",
            "cost": 50.0,
            "mechanisms": ["kleros_jury", "uma_optimistic", "arbitration"],
            "handles": ["ambiguous", "cross_domain", "novel"],
            "resolution_time": "hours-days",
        },
    }
    
    def route(self, dispute: Dispute) -> Resolution:
        """Route dispute to cheapest effective tier."""
        escalation_path = []
        
        # Tier 1: Try interests (Brier calibration)
        if dispute.claim_type in ["quality", "behavioral"]:
            result = self._try_interests(dispute)
            escalation_path.append("interests")
            if result["resolved"]:
                return Resolution(
                    dispute_id=dispute.id,
                    tier="interests",
                    mechanism=result["mechanism"],
                    cost=self.TIERS["interests"]["cost"],
                    outcome=result["outcome"],
                    confidence=result["confidence"],
                    escalation_path=escalation_path,
                )
        
        # Tier 2: Try rights (deterministic)
        if dispute.claim_type in ["scope", "capability", "expiry"]:
            result = self._try_rights(dispute)
            escalation_path.append("rights")
            if result["resolved"]:
                return Resolution(
                    dispute_id=dispute.id,
                    tier="rights",
                    mechanism=result["mechanism"],
                    cost=self.TIERS["rights"]["cost"],
                    outcome=result["outcome"],
                    confidence=result["confidence"],
                    escalation_path=escalation_path,
                )
        
        # Tier 3: Power (escalating jury)
        escalation_path.append("power")
        result = self._try_power(dispute)
        return Resolution(
            dispute_id=dispute.id,
            tier="power",
            mechanism=result["mechanism"],
            cost=self.TIERS["power"]["cost"],
            outcome=result["outcome"],
            confidence=result["confidence"],
            escalation_path=escalation_path,
        )
    
    def _try_interests(self, dispute: Dispute) -> dict:
        """Brier-calibrated market resolution."""
        brier = dispute.evidence.get("brier_score", None)
        if brier is not None:
            if brier < 0.1:
                return {"resolved": True, "mechanism": "brier_calibration",
                        "outcome": "attestor_calibrated", "confidence": 0.95}
            elif brier > 0.3:
                return {"resolved": True, "mechanism": "brier_calibration",
                        "outcome": "attestor_uncalibrated", "confidence": 0.85}
        history = dispute.evidence.get("reputation_history", [])
        if len(history) >= 10:
            avg = sum(history) / len(history)
            if avg > 0.8 or avg < 0.3:
                return {"resolved": True, "mechanism": "reputation_history",
                        "outcome": f"reputation_{'high' if avg > 0.8 else 'low'}", 
                        "confidence": 0.80}
        return {"resolved": False}
    
    def _try_rights(self, dispute: Dispute) -> dict:
        """Deterministic hash/scope comparison."""
        declared = dispute.evidence.get("declared_scope_hash")
        actual = dispute.evidence.get("actual_scope_hash")
        if declared and actual:
            if declared == actual:
                return {"resolved": True, "mechanism": "hash_comparison",
                        "outcome": "scope_valid", "confidence": 1.0}
            else:
                return {"resolved": True, "mechanism": "hash_comparison",
                        "outcome": "scope_violation", "confidence": 1.0}
        ttl = dispute.evidence.get("ttl_remaining")
        if ttl is not None:
            if ttl <= 0:
                return {"resolved": True, "mechanism": "ttl_validation",
                        "outcome": "expired", "confidence": 1.0}
        return {"resolved": False}
    
    def _try_power(self, dispute: Dispute) -> dict:
        """Kleros-style escalating jury — always resolves, highest cost."""
        return {"resolved": True, "mechanism": "kleros_jury",
                "outcome": "jury_verdict", "confidence": 0.70}
    
    def analyze_system(self, disputes: List[Dispute]) -> dict:
        """Analyze dispute routing efficiency."""
        results = [self.route(d) for d in disputes]
        tier_counts = {"interests": 0, "rights": 0, "power": 0}
        total_cost = 0.0
        
        for r in results:
            tier_counts[r.tier] += 1
            total_cost += r.cost
        
        n = len(results)
        naive_cost = n * self.TIERS["power"]["cost"]  # if all went to power
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_disputes": n,
            "tier_distribution": tier_counts,
            "total_cost": round(total_cost, 2),
            "naive_cost": round(naive_cost, 2),
            "savings": f"{((naive_cost - total_cost) / naive_cost * 100):.1f}%",
            "avg_confidence": round(sum(r.confidence for r in results) / n, 3),
            "resolutions": [asdict(r) for r in results],
        }


def demo():
    """Run demo with sample disputes."""
    router = DisputeRouter()
    
    disputes = [
        Dispute("d1", "quality", "relying_party_a", "attestor_x",
                {"brier_score": 0.05}),
        Dispute("d2", "scope", "monitor_b", "agent_y",
                {"declared_scope_hash": "abc123", "actual_scope_hash": "abc123"}),
        Dispute("d3", "scope", "monitor_c", "agent_z",
                {"declared_scope_hash": "abc123", "actual_scope_hash": "xyz789"}),
        Dispute("d4", "quality", "relying_party_d", "attestor_w",
                {"brier_score": 0.45}),
        Dispute("d5", "behavioral", "monitor_e", "agent_v",
                {"reputation_history": [0.9, 0.85, 0.88, 0.92, 0.87, 0.91, 0.86, 0.89, 0.93, 0.90]}),
        Dispute("d6", "ambiguous", "relying_party_f", "attestor_u", {}),
        Dispute("d7", "capability", "monitor_g", "agent_t",
                {"declared_scope_hash": "def456", "actual_scope_hash": "def456", "ttl_remaining": -100}),
    ]
    
    analysis = router.analyze_system(disputes)
    
    print("=" * 60)
    print("DISPUTE ESCALATION ROUTER — Ury/Brett/Goldberg 1988")
    print("=" * 60)
    print()
    
    for r in analysis["resolutions"]:
        path = " → ".join(r["escalation_path"])
        print(f"[{r['tier'].upper():9s}] {r['dispute_id']}: {r['outcome']} "
              f"(confidence={r['confidence']}, cost={r['cost']}, path={path})")
    
    print()
    print(f"Tier distribution: {analysis['tier_distribution']}")
    print(f"Total cost: {analysis['total_cost']} (naive: {analysis['naive_cost']})")
    print(f"Savings: {analysis['savings']}")
    print(f"Avg confidence: {analysis['avg_confidence']}")
    print()
    print("Key insight: most disputes never leave tier 1-2.")
    print("Collapsing all into one oracle = 50x cost for same outcomes.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        router = DisputeRouter()
        print(json.dumps(router.analyze_system([]), indent=2))
    else:
        demo()
