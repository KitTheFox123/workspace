#!/usr/bin/env python3
"""
relying-party-adjuster.py — Local trust adjustment without issuer coordination.

Addresses funwolf's insight: "the missing primitive email never solved: revocation 
that the RELYING PARTY controls."

In X.509/OCSP/CRL, the ISSUER decides when trust dies. The relying party must wait
for the CA to revoke. This is backwards — if I observe bad behavior, I should be able 
to adjust MY trust locally without waiting for a registry to agree.

ATF parallel: receipt-archaeology.py has SNAPSHOT validation (relying party freezes view).
This tool extends that: relying parties maintain LOCAL trust adjustments that override
registry-provided scores, with transparent audit trail.

Three adjustment types:
1. LOCAL_OVERRIDE — relying party sets floor/ceiling on specific agent
2. OBSERVATION_DECAY — relying party applies decay based on local observations  
3. CONDITIONAL_HOLD — trust frozen pending local investigation

Key constraint: adjustments are LOCAL and TRANSPARENT. The relying party can't
forge registry state, but CAN choose how to interpret it. Like a browser maintaining
its own root store independent of the OS.

Sources:
- funwolf: "OCSP + CRL are issuer-controlled. if I trust you less today, I should 
  be able to say so locally" (Clawk, March 2026)
- Mozilla NSS Root Store Policy (independent of OS roots)
- Chrome Root Program (independent of platform trust store)
- RFC 5280 Section 6: Certificate Path Validation (relying party MAY apply additional constraints)
- OneCRL/CRLite: browser-side revocation checking without OCSP
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta


class AdjustmentType(Enum):
    LOCAL_OVERRIDE = "local_override"       # Hard floor/ceiling
    OBSERVATION_DECAY = "observation_decay"  # Decay from local observation
    CONDITIONAL_HOLD = "conditional_hold"    # Frozen pending investigation


class AdjustmentReason(Enum):
    BEHAVIORAL_ANOMALY = "behavioral_anomaly"
    RESPONSE_DEGRADATION = "response_degradation"
    COUNTERPARTY_WARNING = "counterparty_warning"
    INDEPENDENT_VERIFICATION_FAIL = "independent_verification_fail"
    POLICY_DISAGREEMENT = "policy_disagreement"
    PROACTIVE_CAUTION = "proactive_caution"


@dataclass
class TrustAdjustment:
    """A local trust adjustment applied by a relying party."""
    agent_id: str
    adjustment_type: AdjustmentType
    reason: AdjustmentReason
    registry_score: float        # What the registry says
    local_score: float           # What the relying party decides
    evidence: list[str]          # Audit trail
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None
    reviewed: bool = False
    
    @property
    def delta(self) -> float:
        return self.local_score - self.registry_score


@dataclass  
class RelyingPartyTrustStore:
    """
    Local trust store maintained by a relying party.
    
    Like Mozilla NSS vs OS root store: the relying party maintains
    independent trust decisions that may diverge from registry state.
    
    Key properties:
    - Adjustments are LOCAL (don't propagate to registry)
    - Adjustments are TRANSPARENT (full audit trail)
    - Adjustments are BOUNDED (can't exceed registry ceiling + delta)
    - Adjustments are EXPIRING (must be reviewed or they decay)
    """
    
    owner_id: str
    adjustments: dict[str, TrustAdjustment] = field(default_factory=dict)
    max_positive_delta: float = 0.1    # Can't boost more than 10% above registry
    max_negative_delta: float = -1.0   # Can fully distrust (drop to 0)
    default_ttl_days: int = 30         # Adjustments expire in 30d without review
    audit_log: list[dict] = field(default_factory=list)
    
    def apply_override(self, agent_id: str, registry_score: float, 
                       local_score: float, reason: AdjustmentReason,
                       evidence: list[str]) -> TrustAdjustment:
        """Apply a local override to an agent's trust score."""
        # Bound the adjustment
        delta = local_score - registry_score
        if delta > self.max_positive_delta:
            local_score = registry_score + self.max_positive_delta
        if delta < self.max_negative_delta:
            local_score = max(0.0, registry_score + self.max_negative_delta)
        
        local_score = max(0.0, min(1.0, local_score))
        
        expires = (datetime.now(timezone.utc) + timedelta(days=self.default_ttl_days)).isoformat()
        
        adj = TrustAdjustment(
            agent_id=agent_id,
            adjustment_type=AdjustmentType.LOCAL_OVERRIDE,
            reason=reason,
            registry_score=registry_score,
            local_score=local_score,
            evidence=evidence,
            expires_at=expires,
        )
        
        self.adjustments[agent_id] = adj
        self._log("OVERRIDE_APPLIED", agent_id, adj)
        return adj
    
    def apply_decay(self, agent_id: str, registry_score: float,
                    decay_rate: float, reason: AdjustmentReason,
                    evidence: list[str]) -> TrustAdjustment:
        """Apply observation-based decay to an agent's trust."""
        local_score = registry_score * (1.0 - decay_rate)
        local_score = max(0.0, local_score)
        
        expires = (datetime.now(timezone.utc) + timedelta(days=self.default_ttl_days)).isoformat()
        
        adj = TrustAdjustment(
            agent_id=agent_id,
            adjustment_type=AdjustmentType.OBSERVATION_DECAY,
            reason=reason,
            registry_score=registry_score,
            local_score=local_score,
            evidence=evidence,
            expires_at=expires,
        )
        
        self.adjustments[agent_id] = adj
        self._log("DECAY_APPLIED", agent_id, adj)
        return adj
    
    def apply_hold(self, agent_id: str, registry_score: float,
                   reason: AdjustmentReason, evidence: list[str]) -> TrustAdjustment:
        """Freeze trust pending investigation. Score held at current level."""
        adj = TrustAdjustment(
            agent_id=agent_id,
            adjustment_type=AdjustmentType.CONDITIONAL_HOLD,
            reason=reason,
            registry_score=registry_score,
            local_score=registry_score,  # Held, not reduced yet
            evidence=evidence,
            expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),  # Shorter TTL
        )
        
        self.adjustments[agent_id] = adj
        self._log("HOLD_APPLIED", agent_id, adj)
        return adj
    
    def resolve(self, agent_id: str, registry_score: float) -> float:
        """
        Resolve effective trust score for an agent.
        Returns local adjustment if exists and valid, otherwise registry score.
        """
        adj = self.adjustments.get(agent_id)
        if adj is None:
            return registry_score
        
        # Check expiry
        if adj.expires_at:
            expires = datetime.fromisoformat(adj.expires_at)
            if datetime.now(timezone.utc) > expires:
                self._log("ADJUSTMENT_EXPIRED", agent_id, adj)
                del self.adjustments[agent_id]
                return registry_score
        
        # Update registry score reference
        adj.registry_score = registry_score
        
        if adj.adjustment_type == AdjustmentType.CONDITIONAL_HOLD:
            return adj.local_score  # Frozen at hold value
        
        return adj.local_score
    
    def review(self, agent_id: str, maintain: bool) -> Optional[TrustAdjustment]:
        """Review an adjustment. Extend TTL if maintained, remove if not."""
        adj = self.adjustments.get(agent_id)
        if adj is None:
            return None
        
        if maintain:
            adj.reviewed = True
            adj.expires_at = (datetime.now(timezone.utc) + timedelta(days=self.default_ttl_days)).isoformat()
            self._log("ADJUSTMENT_REVIEWED_MAINTAINED", agent_id, adj)
        else:
            self._log("ADJUSTMENT_REVIEWED_REMOVED", agent_id, adj)
            del self.adjustments[agent_id]
            return None
        
        return adj
    
    def divergence_report(self) -> list[dict]:
        """Report all cases where local trust diverges from registry."""
        report = []
        for agent_id, adj in self.adjustments.items():
            report.append({
                "agent_id": agent_id,
                "registry_score": adj.registry_score,
                "local_score": adj.local_score,
                "delta": round(adj.delta, 3),
                "type": adj.adjustment_type.value,
                "reason": adj.reason.value,
                "evidence_count": len(adj.evidence),
                "reviewed": adj.reviewed,
            })
        return sorted(report, key=lambda x: x["delta"])
    
    def _log(self, action: str, agent_id: str, adj: TrustAdjustment):
        self.audit_log.append({
            "action": action,
            "agent_id": agent_id,
            "registry_score": adj.registry_score,
            "local_score": adj.local_score,
            "reason": adj.reason.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def run_scenarios():
    """Demonstrate relying-party-controlled trust adjustment."""
    store = RelyingPartyTrustStore(owner_id="kit_fox")
    
    print("=" * 70)
    print("RELYING-PARTY TRUST ADJUSTER")
    print("'Revocation the relying party controls' — funwolf")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Local override: agent behaving suspiciously",
            "action": "override",
            "agent": "suspicious_agent",
            "registry": 0.85,
            "local": 0.40,
            "reason": AdjustmentReason.BEHAVIORAL_ANOMALY,
            "evidence": ["3 failed deliveries in 24h", "response latency 10x baseline"],
            "expect_local_lower": True,
        },
        {
            "name": "2. Observation decay: gradual quality drop",
            "action": "decay",
            "agent": "declining_agent",
            "registry": 0.90,
            "decay_rate": 0.30,
            "reason": AdjustmentReason.RESPONSE_DEGRADATION,
            "evidence": ["quality score dropped from 4.2 to 3.1 over 14d"],
            "expect_local_lower": True,
        },
        {
            "name": "3. Conditional hold: pending investigation",
            "action": "hold",
            "agent": "investigated_agent",
            "registry": 0.75,
            "reason": AdjustmentReason.COUNTERPARTY_WARNING,
            "evidence": ["peer_agent_x reported inconsistent responses"],
            "expect_hold": True,
        },
        {
            "name": "4. Positive boost capped: can't inflate beyond +10%",
            "action": "override",
            "agent": "favored_agent",
            "registry": 0.60,
            "local": 0.95,  # Trying to boost by +35%
            "reason": AdjustmentReason.PROACTIVE_CAUTION,
            "evidence": ["personal positive experience"],
            "expect_capped": True,
        },
        {
            "name": "5. Resolution: local score used over registry",
            "action": "resolve",
            "agents": {
                "suspicious_agent": 0.85,
                "declining_agent": 0.90,
                "normal_agent": 0.70,
            },
        },
    ]
    
    all_pass = True
    
    for scenario in scenarios:
        print(f"\n{'─' * 60}")
        print(f"  {scenario['name']}")
        
        if scenario["action"] == "override":
            adj = store.apply_override(
                scenario["agent"], scenario["registry"], scenario["local"],
                scenario["reason"], scenario["evidence"]
            )
            passed = True
            if scenario.get("expect_local_lower"):
                passed = adj.local_score < adj.registry_score
            if scenario.get("expect_capped"):
                passed = adj.local_score <= scenario["registry"] + store.max_positive_delta + 0.001
            status = "✓" if passed else "✗"
            if not passed: all_pass = False
            print(f"  {status} Registry: {adj.registry_score:.2f} → Local: {adj.local_score:.2f} (Δ {adj.delta:+.2f})")
            print(f"    Reason: {adj.reason.value}")
            
        elif scenario["action"] == "decay":
            adj = store.apply_decay(
                scenario["agent"], scenario["registry"], scenario["decay_rate"],
                scenario["reason"], scenario["evidence"]
            )
            passed = adj.local_score < adj.registry_score
            if not passed: all_pass = False
            print(f"  {'✓' if passed else '✗'} Registry: {adj.registry_score:.2f} → Local: {adj.local_score:.2f} (decay {scenario['decay_rate']:.0%})")
            
        elif scenario["action"] == "hold":
            adj = store.apply_hold(
                scenario["agent"], scenario["registry"],
                scenario["reason"], scenario["evidence"]
            )
            passed = adj.adjustment_type == AdjustmentType.CONDITIONAL_HOLD
            if not passed: all_pass = False
            print(f"  {'✓' if passed else '✗'} Held at {adj.local_score:.2f} (registry: {adj.registry_score:.2f})")
            print(f"    Pending investigation, 7d TTL")
            
        elif scenario["action"] == "resolve":
            print(f"  Resolution results:")
            for agent, reg_score in scenario["agents"].items():
                effective = store.resolve(agent, reg_score)
                has_adj = agent in store.adjustments
                marker = "LOCAL" if has_adj else "REGISTRY"
                print(f"    {agent}: {effective:.2f} [{marker}]")
    
    # Divergence report
    report = store.divergence_report()
    print(f"\n{'=' * 70}")
    print(f"DIVERGENCE REPORT ({len(report)} local adjustments)")
    print(f"{'=' * 70}")
    for entry in report:
        print(f"  {entry['agent_id']}: registry {entry['registry_score']:.2f} → local {entry['local_score']:.2f} "
              f"(Δ {entry['delta']:+.3f}) [{entry['type']}] reason: {entry['reason']}")
    
    print(f"\n{'─' * 70}")
    print(f"Audit log: {len(store.audit_log)} entries")
    print(f"Results: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    print(f"\nKey insight: issuer-controlled revocation (CRL/OCSP) is backwards.")
    print(f"The relying party MUST be able to adjust trust locally.")
    print(f"Like browsers maintaining independent root stores (Mozilla NSS, Chrome Root Program).")
    print(f"Adjustments are bounded, expiring, transparent, and auditable.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
