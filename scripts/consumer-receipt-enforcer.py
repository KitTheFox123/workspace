#!/usr/bin/env python3
"""
consumer-receipt-enforcer.py — Client-side receipt verification enforcer.

Inspired by Chrome's CT enforcement model: reject unverified receipts by DEFAULT.
Consumer opt-out, not opt-in. Per santaclawd's observation that "the hardest part
is getting consumers to actually verify."

CT lesson: Chrome REJECTS certs without SCTs. That's why CT adoption hit 100%.
Recommendation-based verification never works (RFC 9413: Postel's Law = ossification).

Design:
- EnforcementPolicy: STRICT (reject unverified), REPORT (accept + log), PERMISSIVE (skip)
- Receipt validation: Merkle inclusion proof, witness diversity, temporal freshness
- Degradation tracking: how often would STRICT have rejected what REPORT accepted?
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EnforcementPolicy(Enum):
    STRICT = "strict"       # Reject unverified (Chrome CT model)
    REPORT = "report"       # Accept but log violations (CT report-only mode)
    PERMISSIVE = "permissive"  # Skip verification (legacy compat)


class RejectionReason(Enum):
    NO_MERKLE_PROOF = "no_merkle_proof"
    INVALID_PROOF = "invalid_proof"
    INSUFFICIENT_WITNESSES = "insufficient_witnesses"
    STALE_RECEIPT = "stale_receipt"
    DUPLICATE_OPERATORS = "duplicate_operators"
    MISSING_DIVERSITY_HASH = "missing_diversity_hash"


@dataclass
class WitnessSignature:
    operator_id: str
    operator_org: str
    infra_hash: str  # hash(hosting + key_material)
    timestamp: float
    signature: str


@dataclass
class Receipt:
    receipt_id: str
    agent_id: str
    action_type: str
    merkle_root: str
    inclusion_proof: list[str]  # Sibling hashes for verification
    leaf_hash: str
    witnesses: list[WitnessSignature]
    diversity_hash: Optional[str] = None
    created_at: float = 0.0


@dataclass
class VerificationResult:
    valid: bool
    policy: EnforcementPolicy
    accepted: bool  # Whether the receipt was accepted (depends on policy)
    rejections: list[RejectionReason] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verification_time_ms: float = 0.0


@dataclass
class EnforcementStats:
    total_checked: int = 0
    strict_would_reject: int = 0
    report_violations: int = 0
    accepted: int = 0
    rejected: int = 0
    
    @property
    def enforcement_gap(self) -> float:
        """How many receipts REPORT accepts that STRICT would reject."""
        if self.total_checked == 0:
            return 0.0
        return self.strict_would_reject / self.total_checked


class ConsumerReceiptEnforcer:
    """Client-side receipt verification with CT-style enforcement."""
    
    # Chrome CT: 2-3 SCTs from independent logs
    MIN_WITNESSES = 2
    # Receipts older than 24h need re-verification
    FRESHNESS_THRESHOLD_S = 86400
    
    def __init__(self, policy: EnforcementPolicy = EnforcementPolicy.STRICT):
        self.policy = policy
        self.stats = EnforcementStats()
        self.violation_log: list[dict] = []
    
    def verify_receipt(self, receipt: Receipt) -> VerificationResult:
        """Verify a receipt according to enforcement policy."""
        start = time.monotonic()
        rejections = []
        warnings = []
        
        # 1. Merkle inclusion proof
        if not receipt.inclusion_proof:
            rejections.append(RejectionReason.NO_MERKLE_PROOF)
        elif not self._verify_merkle_proof(receipt):
            rejections.append(RejectionReason.INVALID_PROOF)
        
        # 2. Witness count (CT: 2-3 SCTs minimum)
        if len(receipt.witnesses) < self.MIN_WITNESSES:
            rejections.append(RejectionReason.INSUFFICIENT_WITNESSES)
        
        # 3. Witness independence (same org = 1 witness)
        unique_orgs = set()
        unique_infra = set()
        for w in receipt.witnesses:
            unique_orgs.add(w.operator_org)
            unique_infra.add(w.infra_hash)
        
        if len(unique_orgs) < self.MIN_WITNESSES:
            rejections.append(RejectionReason.DUPLICATE_OPERATORS)
            warnings.append(
                f"{len(receipt.witnesses)} witnesses but only "
                f"{len(unique_orgs)} unique orgs"
            )
        
        # 4. Diversity hash present (self-certifying artifact)
        if not receipt.diversity_hash:
            rejections.append(RejectionReason.MISSING_DIVERSITY_HASH)
        
        # 5. Temporal freshness
        age_s = time.time() - receipt.created_at
        if age_s > self.FRESHNESS_THRESHOLD_S:
            rejections.append(RejectionReason.STALE_RECEIPT)
            warnings.append(f"Receipt age: {age_s/3600:.1f}h")
        
        elapsed = (time.monotonic() - start) * 1000
        valid = len(rejections) == 0
        
        # Policy-based acceptance
        if self.policy == EnforcementPolicy.STRICT:
            accepted = valid
        elif self.policy == EnforcementPolicy.REPORT:
            accepted = True  # Accept but log
            if not valid:
                self._log_violation(receipt, rejections)
        else:  # PERMISSIVE
            accepted = True
        
        # Track enforcement gap
        self.stats.total_checked += 1
        if not valid:
            self.stats.strict_would_reject += 1
        if accepted:
            self.stats.accepted += 1
        else:
            self.stats.rejected += 1
        if self.policy == EnforcementPolicy.REPORT and not valid:
            self.stats.report_violations += 1
        
        return VerificationResult(
            valid=valid,
            policy=self.policy,
            accepted=accepted,
            rejections=rejections,
            warnings=warnings,
            verification_time_ms=elapsed,
        )
    
    def _verify_merkle_proof(self, receipt: Receipt) -> bool:
        """Verify Merkle inclusion proof. O(log n)."""
        current = receipt.leaf_hash
        for sibling in receipt.inclusion_proof:
            # Consistent ordering: smaller hash first
            if current < sibling:
                combined = current + sibling
            else:
                combined = sibling + current
            current = hashlib.sha256(combined.encode()).hexdigest()
        return current == receipt.merkle_root
    
    def _log_violation(self, receipt: Receipt, reasons: list[RejectionReason]):
        """Log violation for REPORT mode analysis."""
        self.violation_log.append({
            "receipt_id": receipt.receipt_id,
            "agent_id": receipt.agent_id,
            "reasons": [r.value for r in reasons],
            "timestamp": time.time(),
        })
    
    def enforcement_report(self) -> dict:
        """Generate enforcement gap report."""
        return {
            "policy": self.policy.value,
            "total_checked": self.stats.total_checked,
            "accepted": self.stats.accepted,
            "rejected": self.stats.rejected,
            "enforcement_gap": f"{self.stats.enforcement_gap:.1%}",
            "strict_would_reject": self.stats.strict_would_reject,
            "recommendation": self._recommend_policy(),
        }
    
    def _recommend_policy(self) -> str:
        """Recommend policy upgrade based on gap analysis."""
        gap = self.stats.enforcement_gap
        if gap == 0:
            return "STRICT safe to deploy — zero rejections"
        elif gap < 0.05:
            return f"STRICT recommended — only {gap:.1%} would be rejected"
        elif gap < 0.20:
            return f"Caution — {gap:.1%} rejection rate. Fix supply first."
        else:
            return f"High gap ({gap:.1%}). Stay in REPORT until supply improves."


def _make_merkle_proof(leaf: str) -> tuple[str, list[str], str]:
    """Helper: create a valid Merkle proof for testing."""
    leaf_hash = hashlib.sha256(leaf.encode()).hexdigest()
    sibling1 = hashlib.sha256(b"sibling1").hexdigest()
    # Compute parent
    if leaf_hash < sibling1:
        combined = leaf_hash + sibling1
    else:
        combined = sibling1 + leaf_hash
    root = hashlib.sha256(combined.encode()).hexdigest()
    return leaf_hash, [sibling1], root


@dataclass
class GraduationSchedule:
    """Chrome CT-style enforcement graduation.
    
    Timeline (per santaclawd's enforcement graduation problem):
    - Phase 1: REPORT mode (log violations, accept all)
    - Phase 2: STRICT for high-value transactions
    - Phase 3: STRICT for all transactions
    
    Chrome CT: announced Oct 2016, enforced July 2018 (21 months).
    HTTPS "Not Secure": Jan 2017 passwords, July 2018 all pages.
    """
    report_start: float          # Unix timestamp
    strict_high_value_date: float  # STRICT for tx > threshold
    strict_all_date: float        # STRICT for everything
    high_value_threshold: float = 1.0  # SOL or equivalent
    
    def current_policy(self, tx_value: float = 0.0) -> EnforcementPolicy:
        """Determine policy based on current date and tx value."""
        now = time.time()
        if now >= self.strict_all_date:
            return EnforcementPolicy.STRICT
        elif now >= self.strict_high_value_date and tx_value >= self.high_value_threshold:
            return EnforcementPolicy.STRICT
        elif now >= self.report_start:
            return EnforcementPolicy.REPORT
        else:
            return EnforcementPolicy.PERMISSIVE
    
    def phase_name(self, tx_value: float = 0.0) -> str:
        policy = self.current_policy(tx_value)
        now = time.time()
        if now < self.report_start:
            days_to = (self.report_start - now) / 86400
            return f"PRE-REPORT ({days_to:.0f}d to Phase 1)"
        elif now < self.strict_high_value_date:
            days_to = (self.strict_high_value_date - now) / 86400
            return f"REPORT ({days_to:.0f}d to Phase 2)"
        elif now < self.strict_all_date:
            days_to = (self.strict_all_date - now) / 86400
            return f"STRICT-HIGH ({days_to:.0f}d to Phase 3)"
        else:
            return "STRICT-ALL (fully enforced)"
    
    @classmethod
    def chrome_ct_model(cls, start: Optional[float] = None) -> "GraduationSchedule":
        """Create schedule based on Chrome CT timeline (21 months)."""
        s = start or time.time()
        return cls(
            report_start=s,
            strict_high_value_date=s + 180 * 86400,   # 6 months
            strict_all_date=s + 540 * 86400,           # 18 months
            high_value_threshold=1.0,
        )


def demo():
    """Demonstrate enforcement modes with test receipts."""
    now = time.time()
    
    # Build valid receipt
    leaf_hash, proof, root = _make_merkle_proof("action:deliver:abc123")
    
    valid_receipt = Receipt(
        receipt_id="r001",
        agent_id="agent:kit",
        action_type="delivery",
        merkle_root=root,
        inclusion_proof=proof,
        leaf_hash=leaf_hash,
        witnesses=[
            WitnessSignature("w1", "OrgA", "infra_a", now, "sig1"),
            WitnessSignature("w2", "OrgB", "infra_b", now, "sig2"),
        ],
        diversity_hash="div_abc",
        created_at=now - 3600,  # 1h old
    )
    
    # Receipt with problems: single org, no diversity hash
    bad_receipt = Receipt(
        receipt_id="r002",
        agent_id="agent:shady",
        action_type="delivery",
        merkle_root=root,
        inclusion_proof=proof,
        leaf_hash=leaf_hash,
        witnesses=[
            WitnessSignature("w1", "SameOrg", "infra_x", now, "sig1"),
            WitnessSignature("w2", "SameOrg", "infra_y", now, "sig2"),
        ],
        diversity_hash=None,
        created_at=now - 3600,
    )
    
    # Stale receipt (48h old)
    stale_receipt = Receipt(
        receipt_id="r003",
        agent_id="agent:old",
        action_type="attestation",
        merkle_root=root,
        inclusion_proof=proof,
        leaf_hash=leaf_hash,
        witnesses=[
            WitnessSignature("w1", "OrgC", "infra_c", now, "sig1"),
            WitnessSignature("w2", "OrgD", "infra_d", now, "sig2"),
        ],
        diversity_hash="div_xyz",
        created_at=now - 172800,  # 48h old
    )
    
    scenarios = [
        ("Valid receipt", valid_receipt),
        ("Same-org witnesses + no diversity hash", bad_receipt),
        ("Stale receipt (48h)", stale_receipt),
    ]
    
    for policy in EnforcementPolicy:
        print(f"\n{'='*60}")
        print(f"Policy: {policy.value.upper()}")
        print(f"{'='*60}")
        
        enforcer = ConsumerReceiptEnforcer(policy=policy)
        
        for name, receipt in scenarios:
            result = enforcer.verify_receipt(receipt)
            status = "✅ ACCEPTED" if result.accepted else "❌ REJECTED"
            valid = "valid" if result.valid else "invalid"
            print(f"\n  {name}: {status} ({valid})")
            if result.rejections:
                print(f"    Reasons: {[r.value for r in result.rejections]}")
            if result.warnings:
                print(f"    Warnings: {result.warnings}")
            print(f"    Verification: {result.verification_time_ms:.2f}ms")
        
        report = enforcer.enforcement_report()
        print(f"\n  📊 Gap Report:")
        print(f"    Checked: {report['total_checked']}")
        print(f"    Accepted: {report['accepted']}")
        print(f"    Rejected: {report['rejected']}")
        print(f"    Enforcement gap: {report['enforcement_gap']}")
        print(f"    → {report['recommendation']}")


def demo_graduation():
    """Demo enforcement graduation schedule."""
    print("\n" + "=" * 60)
    print("ENFORCEMENT GRADUATION (Chrome CT model)")
    print("=" * 60)
    
    now = time.time()
    schedule = GraduationSchedule.chrome_ct_model(start=now)
    
    test_cases = [
        ("Small tx today", 0.1, now),
        ("Large tx today", 5.0, now),
        ("Small tx +7mo", 0.1, now + 210 * 86400),
        ("Large tx +7mo", 5.0, now + 210 * 86400),
        ("Any tx +19mo", 0.1, now + 570 * 86400),
    ]
    
    for name, value, when in test_cases:
        # Temporarily shift time for demo
        orig = schedule.strict_high_value_date
        phase = "REPORT" if when < schedule.strict_high_value_date else (
            "STRICT-HIGH" if when < schedule.strict_all_date else "STRICT-ALL"
        )
        if when < schedule.report_start:
            phase = "PRE-REPORT"
        
        policy = EnforcementPolicy.REPORT
        if when >= schedule.strict_all_date:
            policy = EnforcementPolicy.STRICT
        elif when >= schedule.strict_high_value_date and value >= schedule.high_value_threshold:
            policy = EnforcementPolicy.STRICT
        
        print(f"\n  {name}: {phase} → {policy.value}")
        print(f"    Value: {value} SOL, Policy: {policy.value}")
    
    print(f"\n  📅 Schedule:")
    print(f"    Phase 1 (REPORT):      Day 0")
    print(f"    Phase 2 (STRICT >1 SOL): Day 180 (~6 months)")
    print(f"    Phase 3 (STRICT all):  Day 540 (~18 months)")
    print(f"    Modeled on Chrome CT: Oct 2016 → Jul 2018")


if __name__ == "__main__":
    demo()
    demo_graduation()


# === GRADUATION SCHEDULER ===

@dataclass
class GraduationMilestone:
    """CT-style enforcement graduation milestone."""
    name: str
    policy: EnforcementPolicy
    required_gap_below: float  # Max enforcement gap to proceed
    min_checked: int           # Minimum receipts checked at this level
    duration_days: int         # Minimum days at this level


class EnforcementGraduator:
    """
    Manage REPORT → STRICT graduation per Chrome CT model.
    
    Chrome timeline:
    - 2013: CT proposed (RFC 6962)
    - 2015: EV cert enforcement (REPORT for others)
    - April 2018: Full STRICT enforcement
    
    Agent commerce is smaller. Proposed:
    - Month 0-3: PERMISSIVE (collect baseline)
    - Month 3-6: REPORT (measure gap)
    - Month 6+: STRICT (if gap < 5%)
    """
    
    MILESTONES = [
        GraduationMilestone("baseline", EnforcementPolicy.PERMISSIVE, 1.0, 100, 90),
        GraduationMilestone("report", EnforcementPolicy.REPORT, 0.20, 500, 90),
        GraduationMilestone("strict", EnforcementPolicy.STRICT, 0.05, 1000, 0),
    ]
    
    def __init__(self):
        self.current_index = 0
        self.days_at_current = 0
        self.receipts_checked = 0
    
    @property
    def current_milestone(self) -> GraduationMilestone:
        return self.MILESTONES[self.current_index]
    
    def check_graduation(self, enforcer: ConsumerReceiptEnforcer) -> dict:
        """Check if ready to graduate to next enforcement level."""
        ms = self.current_milestone
        gap = enforcer.stats.enforcement_gap
        checked = enforcer.stats.total_checked
        
        ready = (
            self.current_index < len(self.MILESTONES) - 1
            and gap <= ms.required_gap_below
            and checked >= ms.min_checked
            and self.days_at_current >= ms.duration_days
        )
        
        blockers = []
        if gap > ms.required_gap_below:
            blockers.append(f"gap {gap:.1%} > {ms.required_gap_below:.0%}")
        if checked < ms.min_checked:
            blockers.append(f"checked {checked} < {ms.min_checked}")
        if self.days_at_current < ms.duration_days:
            blockers.append(f"days {self.days_at_current} < {ms.duration_days}")
        
        next_ms = (
            self.MILESTONES[self.current_index + 1]
            if self.current_index < len(self.MILESTONES) - 1
            else None
        )
        
        return {
            "current": ms.name,
            "policy": ms.policy.value,
            "ready_to_graduate": ready,
            "next": next_ms.name if next_ms else "FINAL",
            "blockers": blockers if not ready else [],
            "enforcement_gap": f"{gap:.1%}",
        }


def demo_graduation():
    """Show graduation readiness."""
    print("\n" + "=" * 60)
    print("ENFORCEMENT GRADUATION (CT-style)")
    print("=" * 60)
    
    grad = EnforcementGraduator()
    
    # Simulate: just started, low volume
    enforcer = ConsumerReceiptEnforcer(EnforcementPolicy.PERMISSIVE)
    grad.days_at_current = 30
    # Fake some stats
    enforcer.stats.total_checked = 50
    enforcer.stats.strict_would_reject = 20
    
    report = grad.check_graduation(enforcer)
    print(f"\n  Phase: {report['current']} ({report['policy']})")
    print(f"  Ready: {report['ready_to_graduate']}")
    print(f"  Next: {report['next']}")
    print(f"  Gap: {report['enforcement_gap']}")
    if report['blockers']:
        print(f"  Blockers: {report['blockers']}")
    
    # Simulate: 90 days, good gap
    grad.days_at_current = 95
    enforcer.stats.total_checked = 200
    enforcer.stats.strict_would_reject = 10
    
    report = grad.check_graduation(enforcer)
    print(f"\n  Phase: {report['current']} ({report['policy']}) — after 95 days")
    print(f"  Ready: {report['ready_to_graduate']}")
    print(f"  Gap: {report['enforcement_gap']}")
    if report['blockers']:
        print(f"  Blockers: {report['blockers']}")
    else:
        print(f"  → READY to graduate to {report['next']}")


if __name__ == "__main__":
    demo()
    demo_graduation()
