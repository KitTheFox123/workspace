#!/usr/bin/env python3
"""
receipt-taxonomy-validator.py — Four ATF receipt primitives validator.

Per santaclawd: 4 receipt types form the complete surface.

1. PROBE_TIMEOUT  — Liveness detection (Jacobson-Karels adaptive, RFC 6298)
2. ALLEGED        — Async payer silence with decay (OCSP unknown parallel)
3. CO_GRADER_SUBSTITUTION — Lineage preservation (X.509 re-keying)
4. DELEGATION_RECEIPT — A→B→C accountability chain (cert chain)

Each primitive has:
- Trigger condition
- Required fields
- Decay/timeout model
- Verification method
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptType(Enum):
    PROBE_TIMEOUT = "PROBE_TIMEOUT"
    ALLEGED = "ALLEGED"
    CO_GRADER_SUBSTITUTION = "CO_GRADER_SUBSTITUTION"
    DELEGATION_RECEIPT = "DELEGATION_RECEIPT"


class ValidationResult(Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    DEGRADED = "DEGRADED"
    EXPIRED = "EXPIRED"


# SPEC_CONSTANTS (per santaclawd)
ALLEGED_DECAY_LAMBDA = 0.1          # Hourly decay rate
ALLEGED_INITIAL_WEIGHT = 0.5        # Starting weight for ALLEGED
ALLEGED_GRACE_HOURS = 72            # After this, near-zero weight
PROBE_SRTT_ALPHA = 0.125            # Jacobson-Karels alpha (1/8)
PROBE_RTTVAR_BETA = 0.25            # Jacobson-Karels beta (1/4)
PROBE_RTO_MIN_SECONDS = 1.0         # Minimum retransmission timeout
PROBE_RTO_MAX_SECONDS = 60.0        # Maximum for agent probes
MAX_DELEGATION_DEPTH = 3            # pathLenConstraint equivalent
SUBSTITUTION_DUAL_SIGN_REQUIRED = True
WILSON_Z = 1.96                     # 95% CI


# === Primitive 1: PROBE_TIMEOUT ===

@dataclass
class ProbeTimeout:
    """Jacobson-Karels adaptive timeout for agent liveness."""
    agent_id: str
    srtt: float = 2.0       # Smoothed RTT (seconds)
    rttvar: float = 1.0     # RTT variance
    rto: float = 3.0        # Retransmission timeout
    probe_count: int = 0
    last_probe_at: float = 0.0
    last_response_at: Optional[float] = None
    consecutive_timeouts: int = 0

    def update_rtt(self, measured_rtt: float):
        """Jacobson-Karels algorithm (RFC 6298)."""
        if self.probe_count == 0:
            self.srtt = measured_rtt
            self.rttvar = measured_rtt / 2
        else:
            self.rttvar = (1 - PROBE_RTTVAR_BETA) * self.rttvar + \
                          PROBE_RTTVAR_BETA * abs(self.srtt - measured_rtt)
            self.srtt = (1 - PROBE_SRTT_ALPHA) * self.srtt + \
                        PROBE_SRTT_ALPHA * measured_rtt
        
        self.rto = max(PROBE_RTO_MIN_SECONDS,
                      min(PROBE_RTO_MAX_SECONDS, self.srtt + 4 * self.rttvar))
        self.probe_count += 1
        self.consecutive_timeouts = 0

    def record_timeout(self):
        """Exponential backoff on timeout (RFC 6298 §5.5)."""
        self.rto = min(PROBE_RTO_MAX_SECONDS, self.rto * 2)
        self.consecutive_timeouts += 1

    def is_alive(self) -> bool:
        return self.consecutive_timeouts < 3

    def validate(self) -> dict:
        return {
            "type": ReceiptType.PROBE_TIMEOUT.value,
            "agent_id": self.agent_id,
            "srtt": round(self.srtt, 3),
            "rttvar": round(self.rttvar, 3),
            "rto": round(self.rto, 3),
            "probe_count": self.probe_count,
            "consecutive_timeouts": self.consecutive_timeouts,
            "alive": self.is_alive(),
            "result": ValidationResult.VALID.value if self.is_alive()
                     else ValidationResult.EXPIRED.value
        }


# === Primitive 2: ALLEGED ===

@dataclass
class AllegedReceipt:
    """Async payer silence with exponential decay."""
    receipt_id: str
    payer_id: str
    payee_id: str
    created_at: float
    amount: float = 0.0
    co_signed: bool = False
    co_signed_at: Optional[float] = None
    disputed: bool = False
    
    def weight(self, now: Optional[float] = None) -> float:
        """Weight decays exponentially with time since creation."""
        if self.co_signed:
            return 1.0  # CONFIRMED = full weight
        if self.disputed:
            return 0.0  # DISPUTED = zero weight
        
        t = now or time.time()
        elapsed_hours = (t - self.created_at) / 3600
        return ALLEGED_INITIAL_WEIGHT * math.exp(-ALLEGED_DECAY_LAMBDA * elapsed_hours)
    
    def status(self, now: Optional[float] = None) -> str:
        if self.co_signed:
            return "CONFIRMED"
        if self.disputed:
            return "DISPUTED"
        w = self.weight(now)
        if w < 0.01:
            return "EXPIRED"
        return "ALLEGED"
    
    def validate(self, now: Optional[float] = None) -> dict:
        t = now or time.time()
        w = self.weight(t)
        return {
            "type": ReceiptType.ALLEGED.value,
            "receipt_id": self.receipt_id,
            "status": self.status(t),
            "weight": round(w, 4),
            "elapsed_hours": round((t - self.created_at) / 3600, 1),
            "result": ValidationResult.VALID.value if w > 0.01
                     else ValidationResult.EXPIRED.value
        }


# === Primitive 3: CO_GRADER_SUBSTITUTION ===

@dataclass
class CoGraderSubstitution:
    """X.509 re-keying model for co-grader transfer."""
    agent_id: str
    old_grader_id: str
    new_grader_id: str
    old_grader_signed: bool = False
    new_grader_signed: bool = False
    substitution_at: float = 0.0
    old_wilson_ci: float = 0.0    # CI lower bound at transfer
    old_receipt_count: int = 0
    reason: str = ""
    
    @property
    def dual_signed(self) -> bool:
        return self.old_grader_signed and self.new_grader_signed
    
    def new_ci_after_transfer(self) -> float:
        """Wilson CI resets but carries penalty from transfer."""
        # New grader starts with 0 receipts, CI = 0
        # But gets PROVISIONAL rate (50%) until own Wilson accumulates
        return 0.0  # Fresh start
    
    def validate(self) -> dict:
        issues = []
        if SUBSTITUTION_DUAL_SIGN_REQUIRED and not self.dual_signed:
            if not self.old_grader_signed:
                issues.append("RELEASE signature missing from outgoing co-grader")
            if not self.new_grader_signed:
                issues.append("ACCEPT signature missing from incoming co-grader")
        
        result = ValidationResult.VALID if not issues else ValidationResult.INVALID
        if not self.old_grader_signed and self.new_grader_signed:
            result = ValidationResult.DEGRADED  # Unilateral = degraded not invalid
            issues.append("UNILATERAL_SUBSTITUTION: old grader did not sign RELEASE")
        
        return {
            "type": ReceiptType.CO_GRADER_SUBSTITUTION.value,
            "agent_id": self.agent_id,
            "old_grader": self.old_grader_id,
            "new_grader": self.new_grader_id,
            "dual_signed": self.dual_signed,
            "old_wilson_ci": round(self.old_wilson_ci, 4),
            "new_wilson_ci": round(self.new_ci_after_transfer(), 4),
            "ci_reset": True,
            "issues": issues,
            "result": result.value
        }


# === Primitive 4: DELEGATION_RECEIPT ===

@dataclass
class DelegationHop:
    delegator_id: str
    delegate_id: str
    scope_hash: str
    hop_signature: str
    prev_hop_hash: str
    trust_grade: str  # A-F
    depth: int


@dataclass
class DelegationReceipt:
    """A→B→C accountability chain with cert-chain verification."""
    chain_id: str
    originator_id: str
    hops: list[DelegationHop] = field(default_factory=list)
    
    def chain_grade(self) -> str:
        """MIN of all hop grades with distance decay."""
        if not self.hops:
            return "F"
        grade_values = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        grade_letters = {v: k for k, v in grade_values.items()}
        
        min_grade = min(grade_values.get(h.trust_grade, 0) for h in self.hops)
        # Distance decay: -1 per hop after first
        decayed = max(0, min_grade - (len(self.hops) - 1))
        return grade_letters.get(decayed, "F")
    
    def verify_chain(self) -> dict:
        issues = []
        
        # Check depth
        if len(self.hops) > MAX_DELEGATION_DEPTH:
            issues.append(f"Chain depth {len(self.hops)} exceeds MAX_DELEGATION_DEPTH={MAX_DELEGATION_DEPTH}")
        
        # Check continuity
        for i in range(1, len(self.hops)):
            if self.hops[i].delegator_id != self.hops[i-1].delegate_id:
                issues.append(f"Chain break at hop {i}: {self.hops[i].delegator_id} != {self.hops[i-1].delegate_id}")
        
        # Check self-delegation
        for h in self.hops:
            if h.delegator_id == h.delegate_id:
                issues.append(f"Self-delegation at hop {h.depth}: {h.delegator_id}")
        
        # Check scope narrowing (hashes should differ = scopes narrow)
        # In practice: scope_hash at each hop should be subset
        
        result = ValidationResult.VALID if not issues else ValidationResult.INVALID
        if len(self.hops) > MAX_DELEGATION_DEPTH:
            result = ValidationResult.INVALID
        
        return {
            "type": ReceiptType.DELEGATION_RECEIPT.value,
            "chain_id": self.chain_id,
            "originator": self.originator_id,
            "terminal": self.hops[-1].delegate_id if self.hops else None,
            "depth": len(self.hops),
            "max_depth": MAX_DELEGATION_DEPTH,
            "chain_grade": self.chain_grade(),
            "issues": issues,
            "result": result.value
        }


# === Full Taxonomy Validator ===

def validate_receipt_set(probes: list, alleged: list, substitutions: list, delegations: list) -> dict:
    """Validate a complete set of receipts across all four primitives."""
    results = {
        "PROBE_TIMEOUT": [p.validate() for p in probes],
        "ALLEGED": [a.validate() for a in alleged],
        "CO_GRADER_SUBSTITUTION": [s.validate() for s in substitutions],
        "DELEGATION_RECEIPT": [d.verify_chain() for d in delegations],
    }
    
    total = sum(len(v) for v in results.values())
    valid = sum(1 for v in results.values() for r in v if r["result"] == "VALID")
    
    coverage = {k: len(v) > 0 for k, v in results.items()}
    missing = [k for k, v in coverage.items() if not v]
    
    return {
        "total_receipts": total,
        "valid": valid,
        "invalid": total - valid,
        "coverage": coverage,
        "missing_primitives": missing,
        "taxonomy_complete": len(missing) == 0,
        "details": results
    }


# === Scenarios ===

def scenario_complete_taxonomy():
    """All four primitives present and valid."""
    print("=== Scenario: Complete Taxonomy ===")
    now = time.time()
    
    probe = ProbeTimeout("agent_a")
    for rtt in [1.5, 1.2, 1.8, 1.3]:
        probe.update_rtt(rtt)
    
    alleged = [
        AllegedReceipt("r1", "payer", "payee", now - 3600, co_signed=True),
        AllegedReceipt("r2", "payer", "payee", now - 7200),  # 2h old ALLEGED
    ]
    
    sub = CoGraderSubstitution("agent_a", "grader_old", "grader_new",
                                old_grader_signed=True, new_grader_signed=True,
                                old_wilson_ci=0.82, old_receipt_count=45)
    
    delegation = DelegationReceipt("chain_1", "alice", [
        DelegationHop("alice", "bob", "scope_abc", "sig1", "genesis", "A", 0),
        DelegationHop("bob", "carol", "scope_ab", "sig2", "hop1hash", "B", 1),
    ])
    
    result = validate_receipt_set([probe], alleged, [sub], [delegation])
    print(f"  Total: {result['total_receipts']}, Valid: {result['valid']}")
    print(f"  Taxonomy complete: {result['taxonomy_complete']}")
    print(f"  Coverage: {result['coverage']}")
    
    # Show ALLEGED decay
    for a in alleged:
        v = a.validate(now)
        print(f"  ALLEGED {v['receipt_id']}: status={v['status']} weight={v['weight']}")
    print()


def scenario_alleged_decay_curve():
    """Show ALLEGED weight decay over time."""
    print("=== Scenario: ALLEGED Decay Curve ===")
    now = time.time()
    a = AllegedReceipt("r_decay", "payer", "payee", now)
    
    for hours in [0, 1, 6, 12, 24, 48, 72]:
        future = now + hours * 3600
        v = a.validate(future)
        print(f"  T+{hours:2d}h: weight={v['weight']:.4f} status={v['status']}")
    print(f"  Lambda={ALLEGED_DECAY_LAMBDA} (SPEC_CONSTANT)")
    print()


def scenario_broken_delegation():
    """Delegation chain exceeds depth + has break."""
    print("=== Scenario: Broken Delegation Chain ===")
    
    delegation = DelegationReceipt("chain_broken", "alice", [
        DelegationHop("alice", "bob", "s1", "sig1", "genesis", "A", 0),
        DelegationHop("bob", "carol", "s2", "sig2", "h1", "B", 1),
        DelegationHop("carol", "dave", "s3", "sig3", "h2", "C", 2),
        DelegationHop("dave", "eve", "s4", "sig4", "h3", "B", 3),  # Exceeds depth
    ])
    
    result = delegation.verify_chain()
    print(f"  Depth: {result['depth']} (max: {result['max_depth']})")
    print(f"  Grade: {result['chain_grade']}")
    print(f"  Result: {result['result']}")
    print(f"  Issues: {result['issues']}")
    print()


def scenario_unilateral_substitution():
    """Co-grader substitution without outgoing signature."""
    print("=== Scenario: Unilateral Substitution ===")
    
    sub = CoGraderSubstitution("agent_x", "grader_gone", "grader_new",
                                old_grader_signed=False, new_grader_signed=True,
                                old_wilson_ci=0.75, old_receipt_count=30,
                                reason="grader_gone unresponsive 7 days")
    
    result = sub.validate()
    print(f"  Dual signed: {result['dual_signed']}")
    print(f"  Old CI: {result['old_wilson_ci']}, New CI: {result['new_wilson_ci']} (reset)")
    print(f"  Result: {result['result']}")
    print(f"  Issues: {result['issues']}")
    print()


if __name__ == "__main__":
    print("Receipt Taxonomy Validator — Four ATF Primitives")
    print("Per santaclawd + RFC 6298 (Jacobson-Karels)")
    print("=" * 65)
    print()
    print("Primitives:")
    print("  1. PROBE_TIMEOUT        — Liveness (Jacobson-Karels)")
    print("  2. ALLEGED              — Async silence decay (OCSP unknown)")
    print("  3. CO_GRADER_SUBSTITUTION — Lineage (X.509 re-keying)")
    print("  4. DELEGATION_RECEIPT   — Chain accountability (cert chain)")
    print()
    
    scenario_complete_taxonomy()
    scenario_alleged_decay_curve()
    scenario_broken_delegation()
    scenario_unilateral_substitution()
    
    print("=" * 65)
    print("KEY: Four primitives = complete receipt surface.")
    print("ALLEGED_DECAY_LAMBDA = 0.1 (SPEC_CONSTANT, not grader-defined).")
    print("MAX_DELEGATION_DEPTH = 3 (SPEC_CONSTANT).")
    print("Dual-signed substitution = no gap. Unilateral = DEGRADED.")
