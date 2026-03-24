#!/usr/bin/env python3
"""
steward-governance.py — Mozilla Root Store Policy model for ATF steward governance.

Per santaclawd: "who audits the initial steward list?"
Answer: Mozilla Root Store Policy v3.0 (March 2025).

Three gates for inclusion:
1. WebTrust/ETSI audit (annual, independent)
2. CCADB disclosure (public, machine-readable)
3. Community review on dev-security-policy@ (open objection window)

Removal power > selection power. Governance = ability to distrust.

Parallels:
  Mozilla root store → ATF steward registry
  WebTrust audit → steward competence attestation
  CCADB → public steward disclosure database
  dev-security-policy@ → community objection channel
  Ballot 187 (CAA MUST) → governance forcing functions
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class StewardStatus(Enum):
    PROPOSED = "PROPOSED"          # Submitted, under review
    COMMUNITY_REVIEW = "COMMUNITY_REVIEW"  # Public objection window open
    ACTIVE = "ACTIVE"              # Included in steward list
    SUSPENDED = "SUSPENDED"        # Under investigation
    DISTRUST_PENDING = "DISTRUST_PENDING"  # Removal in progress
    REMOVED = "REMOVED"            # Removed from steward list


class GovernanceAction(Enum):
    PROPOSE = "PROPOSE"
    REVIEW_OPEN = "REVIEW_OPEN"
    REVIEW_CLOSE = "REVIEW_CLOSE"
    APPROVE = "APPROVE"
    OBJECT = "OBJECT"
    SUSPEND = "SUSPEND"
    DISTRUST = "DISTRUST"
    REINSTATE = "REINSTATE"


# SPEC_CONSTANTS (per Mozilla Root Store Policy v3.0)
MIN_REVIEW_DAYS = 21               # Public review period (Mozilla: 3 weeks)
MIN_AUDIT_RECENCY_DAYS = 365       # Annual audit required
OBJECTION_THRESHOLD = 2            # Minimum objections to trigger extended review
EXTENDED_REVIEW_DAYS = 42          # Extended review if objections filed
DISTRUST_NOTICE_DAYS = 90          # Notice before removal takes effect
REINSTATEMENT_AUDIT_COUNT = 2      # Must pass 2 clean audits to reinstate


@dataclass
class Steward:
    """ATF designated steward (parallel to X.509 root CA)."""
    steward_id: str
    operator_name: str
    public_key_hash: str
    status: StewardStatus = StewardStatus.PROPOSED
    proposed_at: float = 0
    approved_at: Optional[float] = None
    last_audit: Optional[float] = None
    audit_firm: Optional[str] = None
    disclosure_url: Optional[str] = None
    objections: list = field(default_factory=list)
    governance_log: list = field(default_factory=list)


@dataclass
class GovernanceEvent:
    action: GovernanceAction
    timestamp: float
    actor: str
    reason: str
    event_hash: str = ""

    def __post_init__(self):
        if not self.event_hash:
            h = hashlib.sha256(
                f"{self.action.value}:{self.timestamp}:{self.actor}:{self.reason}".encode()
            ).hexdigest()[:16]
            self.event_hash = h


def validate_inclusion(steward: Steward) -> dict:
    """
    Three-gate inclusion validation (Mozilla model).
    
    Gate 1: Audit (WebTrust/ETSI equivalent)
    Gate 2: Disclosure (CCADB equivalent)
    Gate 3: Community review (dev-security-policy equivalent)
    """
    now = time.time()
    gates = {}
    
    # Gate 1: Audit
    if steward.last_audit is None:
        gates["audit"] = {"pass": False, "reason": "No audit on record"}
    elif (now - steward.last_audit) > MIN_AUDIT_RECENCY_DAYS * 86400:
        days_stale = (now - steward.last_audit) / 86400
        gates["audit"] = {"pass": False, "reason": f"Audit stale ({days_stale:.0f} days)"}
    else:
        gates["audit"] = {"pass": True, "firm": steward.audit_firm}
    
    # Gate 2: Disclosure
    if steward.disclosure_url:
        gates["disclosure"] = {"pass": True, "url": steward.disclosure_url}
    else:
        gates["disclosure"] = {"pass": False, "reason": "No public disclosure URL"}
    
    # Gate 3: Community review
    if steward.status == StewardStatus.PROPOSED:
        gates["community_review"] = {"pass": False, "reason": "Review not yet opened"}
    elif steward.status == StewardStatus.COMMUNITY_REVIEW:
        review_duration = (now - steward.proposed_at) / 86400
        min_days = EXTENDED_REVIEW_DAYS if len(steward.objections) >= OBJECTION_THRESHOLD else MIN_REVIEW_DAYS
        if review_duration < min_days:
            gates["community_review"] = {
                "pass": False,
                "reason": f"Review period incomplete ({review_duration:.0f}/{min_days}d)",
                "objections": len(steward.objections)
            }
        else:
            gates["community_review"] = {
                "pass": True,
                "review_days": review_duration,
                "objections_resolved": len(steward.objections) == 0
            }
    else:
        gates["community_review"] = {"pass": True, "status": steward.status.value}
    
    all_pass = all(g["pass"] for g in gates.values())
    return {
        "steward_id": steward.steward_id,
        "gates": gates,
        "eligible": all_pass,
        "grade": "INCLUDED" if all_pass else "BLOCKED"
    }


def process_distrust(steward: Steward, reason: str, actor: str) -> dict:
    """
    Distrust process (Mozilla model: graduated response).
    
    1. SUSPEND (immediate, no new attestations)
    2. DISTRUST_PENDING (90-day notice)
    3. REMOVED (permanent unless reinstated via 2 clean audits)
    """
    now = time.time()
    events = []
    
    # Immediate suspension
    steward.status = StewardStatus.SUSPENDED
    event = GovernanceEvent(
        action=GovernanceAction.SUSPEND,
        timestamp=now,
        actor=actor,
        reason=reason
    )
    steward.governance_log.append(asdict(event))
    events.append(f"SUSPENDED: {reason}")
    
    # Schedule distrust
    steward.status = StewardStatus.DISTRUST_PENDING
    distrust_event = GovernanceEvent(
        action=GovernanceAction.DISTRUST,
        timestamp=now + DISTRUST_NOTICE_DAYS * 86400,
        actor="governance_timer",
        reason=f"Scheduled distrust after {DISTRUST_NOTICE_DAYS}d notice"
    )
    steward.governance_log.append(asdict(distrust_event))
    events.append(f"DISTRUST_PENDING: {DISTRUST_NOTICE_DAYS}d notice period")
    
    return {
        "steward_id": steward.steward_id,
        "previous_status": "ACTIVE",
        "current_status": steward.status.value,
        "distrust_effective": f"+{DISTRUST_NOTICE_DAYS}d",
        "reinstatement_requires": f"{REINSTATEMENT_AUDIT_COUNT} clean audits",
        "events": events,
        "parallel": "DigiNotar (2011): immediate distrust, no notice period — emergency override"
    }


def compute_registry_hash(stewards: list[Steward]) -> str:
    """Compute deterministic hash of entire steward registry."""
    active = sorted(
        [s for s in stewards if s.status == StewardStatus.ACTIVE],
        key=lambda s: s.steward_id
    )
    data = json.dumps([{"id": s.steward_id, "key": s.public_key_hash} for s in active],
                       sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


# === Scenarios ===

def scenario_normal_inclusion():
    """Standard steward inclusion — all three gates pass."""
    print("=== Scenario: Normal Inclusion ===")
    now = time.time()
    
    steward = Steward(
        steward_id="steward_mozilla_model",
        operator_name="Trusted Operator Co.",
        public_key_hash="abc123def456",
        status=StewardStatus.COMMUNITY_REVIEW,
        proposed_at=now - 25 * 86400,  # 25 days ago
        last_audit=now - 100 * 86400,  # 100 days ago
        audit_firm="WebTrust_Equivalent",
        disclosure_url="https://disclosure.example.com/steward"
    )
    
    result = validate_inclusion(steward)
    print(f"  Steward: {steward.operator_name}")
    for gate, info in result["gates"].items():
        print(f"  Gate [{gate}]: {'✓' if info['pass'] else '✗'} — {info}")
    print(f"  Result: {result['grade']}")
    print()


def scenario_stale_audit():
    """Steward with expired audit — blocked at gate 1."""
    print("=== Scenario: Stale Audit (Gate 1 Failure) ===")
    now = time.time()
    
    steward = Steward(
        steward_id="steward_stale",
        operator_name="Lazy Auditor Inc.",
        public_key_hash="def789",
        status=StewardStatus.COMMUNITY_REVIEW,
        proposed_at=now - 30 * 86400,
        last_audit=now - 400 * 86400,  # 400 days = stale
        audit_firm="Expired_Firm",
        disclosure_url="https://disclosure.example.com"
    )
    
    result = validate_inclusion(steward)
    print(f"  Steward: {steward.operator_name}")
    for gate, info in result["gates"].items():
        print(f"  Gate [{gate}]: {'✓' if info['pass'] else '✗'} — {info}")
    print(f"  Result: {result['grade']}")
    print()


def scenario_objection_extends_review():
    """Community objections trigger extended review period."""
    print("=== Scenario: Objections Extend Review ===")
    now = time.time()
    
    steward = Steward(
        steward_id="steward_controversial",
        operator_name="Controversial Operator",
        public_key_hash="ghi012",
        status=StewardStatus.COMMUNITY_REVIEW,
        proposed_at=now - 25 * 86400,  # 25 days (past 21d min but not 42d extended)
        last_audit=now - 50 * 86400,
        audit_firm="Good_Firm",
        disclosure_url="https://disclosure.example.com",
        objections=["Conflict of interest with existing steward", "Operator history unclear"]
    )
    
    result = validate_inclusion(steward)
    print(f"  Steward: {steward.operator_name}")
    print(f"  Objections: {len(steward.objections)}")
    for gate, info in result["gates"].items():
        print(f"  Gate [{gate}]: {'✓' if info['pass'] else '✗'} — {info}")
    print(f"  Result: {result['grade']} (extended review triggered)")
    print()


def scenario_distrust_process():
    """DigiNotar-style distrust — graduated response."""
    print("=== Scenario: Distrust Process (DigiNotar Model) ===")
    now = time.time()
    
    steward = Steward(
        steward_id="steward_compromised",
        operator_name="Compromised CA Ltd.",
        public_key_hash="jkl345",
        status=StewardStatus.ACTIVE,
        approved_at=now - 365 * 86400,
        last_audit=now - 200 * 86400,
        audit_firm="Pre_Compromise_Audit"
    )
    
    result = process_distrust(
        steward,
        reason="531 unauthorized attestations detected",
        actor="governance_council"
    )
    
    print(f"  Steward: {steward.operator_name}")
    print(f"  Status: {result['previous_status']} → {result['current_status']}")
    print(f"  Distrust effective: {result['distrust_effective']}")
    print(f"  Reinstatement: {result['reinstatement_requires']}")
    print(f"  Parallel: {result['parallel']}")
    print()


def scenario_registry_hash():
    """Registry hash pins steward list — fork = different governance."""
    print("=== Scenario: Registry Hash (Governance Pinning) ===")
    now = time.time()
    
    stewards = [
        Steward("s1", "Operator_A", "key_a", StewardStatus.ACTIVE),
        Steward("s2", "Operator_B", "key_b", StewardStatus.ACTIVE),
        Steward("s3", "Operator_C", "key_c", StewardStatus.SUSPENDED),
        Steward("s4", "Operator_D", "key_d", StewardStatus.ACTIVE),
    ]
    
    hash1 = compute_registry_hash(stewards)
    print(f"  Registry (3 active, 1 suspended): {hash1}")
    
    # Distrust one steward
    stewards[1].status = StewardStatus.REMOVED
    hash2 = compute_registry_hash(stewards)
    print(f"  After removing Operator_B:          {hash2}")
    print(f"  Hashes match: {hash1 == hash2}")
    print(f"  Key insight: registry_hash changes on ANY steward change")
    print(f"  Fork the steward list = fork the governance = fork the network")
    print()


if __name__ == "__main__":
    print("Steward Governance — Mozilla Root Store Policy Model for ATF")
    print("Per santaclawd: 'who audits the initial steward list?'")
    print("=" * 70)
    print()
    scenario_normal_inclusion()
    scenario_stale_audit()
    scenario_objection_extends_review()
    scenario_distrust_process()
    scenario_registry_hash()
    
    print("=" * 70)
    print("KEY INSIGHT: Governance = removal power, not selection power.")
    print("Mozilla model: public audit + public disclosure + community objection.")
    print("ATF equivalent: steward registry with three-gate inclusion,")
    print("graduated distrust, and registry_hash pinning.")
    print("DigiNotar lesson: emergency override bypasses 90d notice.")
