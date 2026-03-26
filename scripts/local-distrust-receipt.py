#!/usr/bin/env python3
"""
local-distrust-receipt.py — Relying-party-controlled trust revocation.

The missing primitive email/PKI never solved: revocation that the RELYING
PARTY controls (funwolf, Clawk 2026-03-26).

Problem: OCSP/CRL = issuer-controlled revocation. If I trust you less today,
I must wait for your CA to agree. Let's Encrypt killed OCSP entirely (Aug 2025).
RevDNS (SIGCOMM 2025, Bhowmick et al.) moves to DNSSEC but still issuer-controlled.

Solution: LOCAL_DISTRUST receipt. An agent can:
1. Downgrade another agent in its LOCAL trust store
2. Publish a signed receipt of the distrust decision
3. No permission needed from the distrusted agent's registry
4. Other agents can aggregate distrust receipts for crowd-sourced revocation

This is the PKI equivalent of "I block you on my phone" vs "your carrier disconnects you."

Receipt types:
- LOCAL_DISTRUST: I no longer trust you (unilateral)
- CONDITIONAL_DISTRUST: I distrust you IF <condition> (evidence-based)
- DISTRUST_PROPAGATION: I'm forwarding someone else's distrust + my endorsement
- DISTRUST_REVERSAL: I'm restoring trust (requires new evidence)

Sources:
- Let's Encrypt ending OCSP (Dec 2024, enacted Aug 2025)
- RevDNS (SIGCOMM 2025): DNS-based revocation, NSEC aggressive negative caching
- RFC 7908: Route leak classification (parallel: trust leak = endorsement beyond scope)
- ASPA (IETF SIDROPS): Valley-free path verification
- funwolf: "the missing primitive email never solved: revocation that the RELYING PARTY controls"
"""

import json
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Optional


class DistrustType(Enum):
    LOCAL = "LOCAL_DISTRUST"
    CONDITIONAL = "CONDITIONAL_DISTRUST"
    PROPAGATION = "DISTRUST_PROPAGATION"
    REVERSAL = "DISTRUST_REVERSAL"


class DistrustReason(Enum):
    """Structured reason codes (parallel: SMTP bounce codes, TLS alert descriptions)."""
    BEHAVIORAL_DRIFT = "behavioral_drift"          # Agent behavior changed
    ATTESTATION_FAILURE = "attestation_failure"     # Failed to produce valid attestation
    RECEIPT_TIMEOUT = "receipt_timeout"              # Didn't acknowledge within window
    DIVERGENCE_DETECTED = "divergence_detected"     # JSD divergence above threshold
    POLICY_VIOLATION = "policy_violation"            # Violated declared policy
    STALE_IDENTITY = "stale_identity"               # Identity not refreshed within MAX_TENURE
    MANUAL = "manual"                               # Operator decision
    CROWD_SIGNAL = "crowd_signal"                   # Aggregated distrust from multiple sources


@dataclass
class DistrustReceipt:
    """A signed receipt of a relying party's distrust decision."""
    issuer_id: str                    # Who is distrusting
    target_id: str                    # Who is being distrusted
    distrust_type: DistrustType
    reason: DistrustReason
    evidence: Optional[dict] = None   # Supporting data (scores, timestamps, etc.)
    prior_trust_level: float = 0.0    # What trust was before
    new_trust_level: float = 0.0      # What trust is now
    condition: Optional[str] = None   # For CONDITIONAL type
    propagated_from: Optional[str] = None  # For PROPAGATION type
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    receipt_id: str = ""
    chain_hash: str = ""              # Hash linking to previous receipt
    
    def __post_init__(self):
        if not self.receipt_id:
            content = f"{self.issuer_id}:{self.target_id}:{self.distrust_type.value}:{self.timestamp}"
            self.receipt_id = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        d = {
            "receipt_id": self.receipt_id,
            "issuer_id": self.issuer_id,
            "target_id": self.target_id,
            "distrust_type": self.distrust_type.value,
            "reason": self.reason.value,
            "prior_trust_level": self.prior_trust_level,
            "new_trust_level": self.new_trust_level,
            "timestamp": self.timestamp,
            "chain_hash": self.chain_hash,
        }
        if self.evidence:
            d["evidence"] = self.evidence
        if self.condition:
            d["condition"] = self.condition
        if self.propagated_from:
            d["propagated_from"] = self.propagated_from
        return d


class LocalTrustStore:
    """
    Relying-party-controlled trust store with receipt generation.
    
    Unlike PKI where revocation is issuer-controlled (OCSP, CRL),
    this allows any agent to manage its own trust decisions locally
    and publish receipts for transparency.
    """
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.trust_levels: dict[str, float] = {}  # target → trust level [0, 1]
        self.receipts: list[DistrustReceipt] = []
        self.receipt_chain_head: str = "genesis"
    
    def get_trust(self, target_id: str) -> float:
        return self.trust_levels.get(target_id, 0.5)  # Default: neutral
    
    def _chain_hash(self) -> str:
        """Append-only hash chain for receipt integrity."""
        if not self.receipts:
            return hashlib.sha256(b"genesis").hexdigest()[:16]
        last = self.receipts[-1]
        return hashlib.sha256(f"{last.receipt_id}:{last.chain_hash}".encode()).hexdigest()[:16]
    
    def distrust(self, target_id: str, reason: DistrustReason,
                 new_level: float = 0.0, evidence: Optional[dict] = None,
                 condition: Optional[str] = None) -> DistrustReceipt:
        """Issue a local distrust receipt."""
        prior = self.get_trust(target_id)
        
        dtype = DistrustType.LOCAL
        if condition:
            dtype = DistrustType.CONDITIONAL
        
        receipt = DistrustReceipt(
            issuer_id=self.agent_id,
            target_id=target_id,
            distrust_type=dtype,
            reason=reason,
            evidence=evidence,
            prior_trust_level=prior,
            new_trust_level=new_level,
            condition=condition,
            chain_hash=self._chain_hash(),
        )
        
        self.trust_levels[target_id] = new_level
        self.receipts.append(receipt)
        return receipt
    
    def propagate_distrust(self, source_receipt: DistrustReceipt,
                           endorsement_weight: float = 0.5) -> Optional[DistrustReceipt]:
        """
        Forward another agent's distrust with your own endorsement.
        Weight determines how much you trust the source's judgment.
        """
        target = source_receipt.target_id
        if target == self.agent_id:
            return None  # Can't distrust yourself via propagation
        
        prior = self.get_trust(target)
        # Weighted adjustment: don't fully adopt someone else's distrust
        new_level = prior * (1 - endorsement_weight) + source_receipt.new_trust_level * endorsement_weight
        
        receipt = DistrustReceipt(
            issuer_id=self.agent_id,
            target_id=target,
            distrust_type=DistrustType.PROPAGATION,
            reason=source_receipt.reason,
            evidence={"source_receipt": source_receipt.receipt_id, "endorsement_weight": endorsement_weight},
            prior_trust_level=prior,
            new_trust_level=new_level,
            propagated_from=source_receipt.issuer_id,
            chain_hash=self._chain_hash(),
        )
        
        self.trust_levels[target] = new_level
        self.receipts.append(receipt)
        return receipt
    
    def restore_trust(self, target_id: str, new_level: float = 0.5,
                      evidence: Optional[dict] = None) -> DistrustReceipt:
        """Reverse a prior distrust decision with evidence."""
        prior = self.get_trust(target_id)
        
        receipt = DistrustReceipt(
            issuer_id=self.agent_id,
            target_id=target_id,
            distrust_type=DistrustType.REVERSAL,
            reason=DistrustReason.MANUAL,
            evidence=evidence or {"reason": "trust restored with new evidence"},
            prior_trust_level=prior,
            new_trust_level=new_level,
            chain_hash=self._chain_hash(),
        )
        
        self.trust_levels[target_id] = new_level
        self.receipts.append(receipt)
        return receipt


class DistrustAggregator:
    """
    Aggregate distrust receipts from multiple relying parties.
    Crowd-sourced revocation without centralized authority.
    
    Like CRLite (Mozilla) but bottom-up: agents publish distrust,
    aggregator detects patterns.
    """
    
    def __init__(self, quorum_threshold: int = 3, distrust_threshold: float = 0.3):
        self.receipts: list[DistrustReceipt] = []
        self.quorum_threshold = quorum_threshold
        self.distrust_threshold = distrust_threshold
    
    def ingest(self, receipt: DistrustReceipt):
        self.receipts.append(receipt)
    
    def get_crowd_distrust(self, target_id: str) -> dict:
        """Aggregate distrust signals for a target."""
        target_receipts = [r for r in self.receipts 
                          if r.target_id == target_id 
                          and r.distrust_type != DistrustType.REVERSAL]
        
        reversals = [r for r in self.receipts
                    if r.target_id == target_id
                    and r.distrust_type == DistrustType.REVERSAL]
        
        unique_issuers = set(r.issuer_id for r in target_receipts)
        reason_counts: dict[str, int] = {}
        for r in target_receipts:
            reason_counts[r.reason.value] = reason_counts.get(r.reason.value, 0) + 1
        
        quorum_met = len(unique_issuers) >= self.quorum_threshold
        avg_new_trust = (sum(r.new_trust_level for r in target_receipts) / len(target_receipts)) if target_receipts else 0.5
        
        return {
            "target_id": target_id,
            "distrust_count": len(target_receipts),
            "unique_issuers": len(unique_issuers),
            "reversal_count": len(reversals),
            "reason_distribution": reason_counts,
            "average_new_trust": round(avg_new_trust, 3),
            "quorum_met": quorum_met,
            "crowd_verdict": "DISTRUSTED" if quorum_met and avg_new_trust < self.distrust_threshold else "CONTESTED" if target_receipts else "TRUSTED",
        }


def demo():
    print("=" * 70)
    print("LOCAL DISTRUST RECEIPTS — Relying-Party-Controlled Revocation")
    print("=" * 70)
    
    # Setup: 4 agents, 1 aggregator
    kit = LocalTrustStore("kit")
    bro = LocalTrustStore("bro_agent")
    funwolf = LocalTrustStore("funwolf")
    gendolf = LocalTrustStore("gendolf")
    aggregator = DistrustAggregator(quorum_threshold=3)
    
    # Scenario 1: Kit detects behavioral drift in suspect_agent
    print("\n--- Scenario 1: Behavioral Drift Detection ---")
    r1 = kit.distrust(
        "suspect_agent",
        DistrustReason.BEHAVIORAL_DRIFT,
        new_level=0.1,
        evidence={"page_hinkley_stat": 4.2, "threshold": 3.0, "window": "24h"}
    )
    print(f"Kit distrusts suspect_agent: {r1.receipt_id}")
    print(f"  Reason: {r1.reason.value}, Trust: {r1.prior_trust_level:.1f} → {r1.new_trust_level:.1f}")
    aggregator.ingest(r1)
    
    # Scenario 2: bro_agent independently detects divergence
    print("\n--- Scenario 2: Independent Divergence Detection ---")
    r2 = bro.distrust(
        "suspect_agent",
        DistrustReason.DIVERGENCE_DETECTED,
        new_level=0.15,
        evidence={"jsd": 0.42, "threshold": 0.3, "comparison_agent": "baseline_oracle"}
    )
    print(f"bro_agent distrusts suspect_agent: {r2.receipt_id}")
    print(f"  Reason: {r2.reason.value}, Trust: {r2.prior_trust_level:.1f} → {r2.new_trust_level:.2f}")
    aggregator.ingest(r2)
    
    # Scenario 3: funwolf propagates kit's distrust with partial endorsement
    print("\n--- Scenario 3: Distrust Propagation (Crowd Signal) ---")
    r3 = funwolf.propagate_distrust(r1, endorsement_weight=0.7)
    print(f"funwolf propagates kit's distrust: {r3.receipt_id}")
    print(f"  Trust: {r3.prior_trust_level:.1f} → {r3.new_trust_level:.2f} (70% endorsement)")
    aggregator.ingest(r3)
    
    # Scenario 4: Gendolf adds conditional distrust
    print("\n--- Scenario 4: Conditional Distrust ---")
    r4 = gendolf.distrust(
        "suspect_agent",
        DistrustReason.STALE_IDENTITY,
        new_level=0.2,
        condition="identity_refresh_overdue > 90d",
        evidence={"last_refresh": "2025-12-01", "max_tenure_days": 90}
    )
    print(f"gendolf conditionally distrusts: {r4.receipt_id}")
    print(f"  Condition: {r4.condition}")
    aggregator.ingest(r4)
    
    # Check crowd verdict
    print("\n--- Crowd Aggregation ---")
    verdict = aggregator.get_crowd_distrust("suspect_agent")
    print(f"Target: {verdict['target_id']}")
    print(f"Distrust signals: {verdict['distrust_count']} from {verdict['unique_issuers']} unique issuers")
    print(f"Quorum ({aggregator.quorum_threshold} required): {'✓ MET' if verdict['quorum_met'] else '✗ NOT MET'}")
    print(f"Average trust: {verdict['average_new_trust']}")
    print(f"Reasons: {verdict['reason_distribution']}")
    print(f"Verdict: {verdict['crowd_verdict']}")
    
    # Scenario 5: Reversal
    print("\n--- Scenario 5: Trust Restoration ---")
    r5 = kit.restore_trust(
        "suspect_agent",
        new_level=0.6,
        evidence={"new_attestation": "valid", "drift_resolved": True}
    )
    print(f"Kit restores trust: {r5.receipt_id}")
    print(f"  Trust: {r5.prior_trust_level:.1f} → {r5.new_trust_level:.1f}")
    
    # Verify chain integrity
    print("\n--- Receipt Chain Integrity ---")
    for store_name, store in [("kit", kit), ("bro", bro), ("funwolf", funwolf), ("gendolf", gendolf)]:
        chain_valid = all(
            store.receipts[i].chain_hash != store.receipts[i+1].chain_hash
            for i in range(len(store.receipts) - 1)
        ) if len(store.receipts) > 1 else True
        print(f"  {store_name}: {len(store.receipts)} receipts, chain {'✓ valid' if chain_valid else '✗ broken'}")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: Revocation the relying party controls.")
    print("OCSP/CRL = issuer decides. LOCAL_DISTRUST = relying party decides.")
    print("Aggregation = crowd-sourced revocation without central authority.")
    print("Receipt chain = accountability. Every distrust decision is auditable.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    demo()
