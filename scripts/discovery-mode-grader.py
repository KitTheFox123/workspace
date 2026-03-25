#!/usr/bin/env python3
"""
discovery-mode-grader.py — ATF V1.2 DISCOVERY_MODE grade penalties.

Per santaclawd: DANE=0, SVCB=-1, CT_FALLBACK=-2, NONE=-3.
Discovery path quality = explicit trust modifier in receipt.

RFC precedents:
  DANE (RFC 7671) — TLSA pins cert to domain via DNSSEC
  SVCB (RFC 9460) — Service binding, DNS but no DNSSEC chain
  CT (RFC 6962) — Certificate Transparency log lookup
  NONE — TOFU, no verification

Key insight: degraded-mode trust KNOWABLE beats degraded-mode trust HIDDEN.
This is the LE OCSP soft-fail lesson applied to discovery.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryMode(Enum):
    DANE = "DANE"             # DNSSEC + TLSA record (RFC 7671)
    SVCB = "SVCB"             # DNS Service Binding (RFC 9460)
    CT_FALLBACK = "CT_FALLBACK"  # Certificate Transparency log
    NONE = "NONE"             # TOFU / unverified


# SPEC_CONSTANTS (V1.2 MUST)
GRADE_PENALTIES = {
    DiscoveryMode.DANE: 0,        # Full DNSSEC chain = no penalty
    DiscoveryMode.SVCB: -1,       # DNS but no DNSSEC = minor penalty
    DiscoveryMode.CT_FALLBACK: -2, # Log lookup, no direct binding = moderate
    DiscoveryMode.NONE: -3,       # Unverified = severe penalty
}

# Grade scale (A=5, B=4, C=3, D=2, F=0)
GRADE_MAP = {5: "A", 4: "B", 3: "C", 2: "D", 1: "D-", 0: "F"}
BASE_GRADE = 5  # Start at A, penalties degrade


@dataclass
class DiscoveryAttempt:
    """Record of how an agent was discovered."""
    agent_id: str
    target_domain: str
    discovery_mode: DiscoveryMode
    timestamp: float
    fallback_reason: Optional[str] = None  # Why degraded mode was used
    dnssec_chain_valid: bool = False
    tlsa_record_found: bool = False
    svcb_record_found: bool = False
    ct_log_verified: bool = False
    attempt_hash: str = ""

    def __post_init__(self):
        if not self.attempt_hash:
            h = hashlib.sha256(
                f"{self.agent_id}:{self.target_domain}:{self.discovery_mode.value}:{self.timestamp}".encode()
            ).hexdigest()[:16]
            self.attempt_hash = h


@dataclass
class DiscoveryReceipt:
    """Receipt annotated with discovery mode and grade penalty."""
    receipt_id: str
    agent_id: str
    base_grade: str
    discovery_mode: DiscoveryMode
    grade_penalty: int
    adjusted_grade: str
    fallback_reason: Optional[str]
    discovery_hash: str


def resolve_discovery_mode(domain: str, attempt: DiscoveryAttempt) -> DiscoveryMode:
    """
    Resolve discovery mode by preference order.
    Try DANE first, fall back through SVCB → CT → NONE.
    """
    if attempt.dnssec_chain_valid and attempt.tlsa_record_found:
        return DiscoveryMode.DANE
    elif attempt.svcb_record_found:
        return DiscoveryMode.SVCB
    elif attempt.ct_log_verified:
        return DiscoveryMode.CT_FALLBACK
    else:
        return DiscoveryMode.NONE


def apply_grade_penalty(base_grade: str, discovery_mode: DiscoveryMode) -> tuple[str, int]:
    """Apply discovery mode penalty to base grade."""
    grade_values = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 0}
    base_value = grade_values.get(base_grade, 0)
    penalty = GRADE_PENALTIES[discovery_mode]
    adjusted_value = max(0, base_value + penalty)
    adjusted_grade = GRADE_MAP.get(adjusted_value, "F")
    return adjusted_grade, penalty


def create_discovery_receipt(
    receipt_id: str,
    agent_id: str,
    base_grade: str,
    attempt: DiscoveryAttempt
) -> DiscoveryReceipt:
    """Create receipt with discovery mode annotation."""
    mode = resolve_discovery_mode(attempt.target_domain, attempt)
    adjusted_grade, penalty = apply_grade_penalty(base_grade, mode)
    
    discovery_hash = hashlib.sha256(
        f"{receipt_id}:{mode.value}:{penalty}:{attempt.attempt_hash}".encode()
    ).hexdigest()[:16]
    
    return DiscoveryReceipt(
        receipt_id=receipt_id,
        agent_id=agent_id,
        base_grade=base_grade,
        discovery_mode=mode,
        grade_penalty=penalty,
        adjusted_grade=adjusted_grade,
        fallback_reason=attempt.fallback_reason,
        discovery_hash=discovery_hash
    )


def audit_discovery_fleet(receipts: list[DiscoveryReceipt]) -> dict:
    """Audit fleet discovery mode distribution."""
    mode_counts = {}
    grade_impacts = {}
    degraded_count = 0
    
    for r in receipts:
        mode = r.discovery_mode.value
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        if r.grade_penalty < 0:
            degraded_count += 1
            grade_impacts[mode] = grade_impacts.get(mode, [])
            grade_impacts[mode].append(r.grade_penalty)
    
    return {
        "total_receipts": len(receipts),
        "mode_distribution": mode_counts,
        "degraded_count": degraded_count,
        "degraded_ratio": round(degraded_count / len(receipts), 3) if receipts else 0,
        "average_penalties": {
            mode: round(sum(penalties) / len(penalties), 2)
            for mode, penalties in grade_impacts.items()
        },
        "dane_adoption": round(mode_counts.get("DANE", 0) / len(receipts), 3) if receipts else 0,
        "recommendation": (
            "HEALTHY — majority DANE" if mode_counts.get("DANE", 0) > len(receipts) * 0.5
            else "DEGRADED — upgrade discovery paths"
            if degraded_count > len(receipts) * 0.3
            else "ACCEPTABLE — mixed discovery"
        )
    }


# === Scenarios ===

def scenario_dane_verified():
    """Full DNSSEC + TLSA — no penalty."""
    print("=== Scenario: DANE Verified (Full Chain) ===")
    now = time.time()
    
    attempt = DiscoveryAttempt(
        agent_id="kit_fox", target_domain="kit.example.com",
        discovery_mode=DiscoveryMode.DANE, timestamp=now,
        dnssec_chain_valid=True, tlsa_record_found=True
    )
    
    receipt = create_discovery_receipt("r001", "kit_fox", "A", attempt)
    print(f"  Base grade: {receipt.base_grade}")
    print(f"  Discovery: {receipt.discovery_mode.value}")
    print(f"  Penalty: {receipt.grade_penalty}")
    print(f"  Adjusted: {receipt.adjusted_grade}")
    print()


def scenario_svcb_fallback():
    """DNS binding without DNSSEC — minor penalty."""
    print("=== Scenario: SVCB Fallback (No DNSSEC) ===")
    now = time.time()
    
    attempt = DiscoveryAttempt(
        agent_id="new_agent", target_domain="agent.nochain.com",
        discovery_mode=DiscoveryMode.SVCB, timestamp=now,
        dnssec_chain_valid=False, svcb_record_found=True,
        fallback_reason="DNSSEC chain broken at registrar"
    )
    
    receipt = create_discovery_receipt("r002", "new_agent", "A", attempt)
    print(f"  Base grade: {receipt.base_grade} → Adjusted: {receipt.adjusted_grade}")
    print(f"  Discovery: {receipt.discovery_mode.value}, Penalty: {receipt.grade_penalty}")
    print(f"  Fallback reason: {receipt.fallback_reason}")
    print()


def scenario_ct_only():
    """CT log lookup only — moderate penalty."""
    print("=== Scenario: CT Fallback Only ===")
    now = time.time()
    
    attempt = DiscoveryAttempt(
        agent_id="ct_agent", target_domain="agent.legacy.org",
        discovery_mode=DiscoveryMode.CT_FALLBACK, timestamp=now,
        ct_log_verified=True,
        fallback_reason="No DNS records, CT log proof only"
    )
    
    receipt = create_discovery_receipt("r003", "ct_agent", "B", attempt)
    print(f"  Base grade: {receipt.base_grade} → Adjusted: {receipt.adjusted_grade}")
    print(f"  Discovery: {receipt.discovery_mode.value}, Penalty: {receipt.grade_penalty}")
    print(f"  Fallback reason: {receipt.fallback_reason}")
    print()


def scenario_tofu_unverified():
    """No verification — severe penalty."""
    print("=== Scenario: TOFU / Unverified ===")
    now = time.time()
    
    attempt = DiscoveryAttempt(
        agent_id="ghost", target_domain="unknown.tld",
        discovery_mode=DiscoveryMode.NONE, timestamp=now,
        fallback_reason="No DNS, no CT, no SVCB — TOFU"
    )
    
    receipt = create_discovery_receipt("r004", "ghost", "A", attempt)
    print(f"  Base grade: {receipt.base_grade} → Adjusted: {receipt.adjusted_grade}")
    print(f"  Discovery: {receipt.discovery_mode.value}, Penalty: {receipt.grade_penalty}")
    print(f"  An A-grade agent discovered via NONE = D-grade receipt")
    print()


def scenario_fleet_audit():
    """Mixed fleet — audit discovery health."""
    print("=== Scenario: Fleet Discovery Audit ===")
    now = time.time()
    
    receipts = []
    configs = [
        ("kit_fox", "A", True, True, False, False, None),
        ("bro_agent", "A", True, True, False, False, None),
        ("santaclawd", "B", False, False, True, False, "No DNSSEC"),
        ("funwolf", "A", True, True, False, False, None),
        ("new_agent1", "C", False, False, False, True, "CT only"),
        ("new_agent2", "B", False, False, False, True, "CT only"),
        ("ghost1", "D", False, False, False, False, "TOFU"),
        ("ghost2", "C", False, False, False, False, "TOFU"),
        ("svcb_agent", "A", False, False, True, False, "No DNSSEC"),
        ("dane_agent", "A", True, True, False, False, None),
    ]
    
    for aid, grade, dnssec, tlsa, svcb, ct, reason in configs:
        attempt = DiscoveryAttempt(
            agent_id=aid, target_domain=f"{aid}.example.com",
            discovery_mode=DiscoveryMode.DANE, timestamp=now,
            dnssec_chain_valid=dnssec, tlsa_record_found=tlsa,
            svcb_record_found=svcb, ct_log_verified=ct,
            fallback_reason=reason
        )
        receipt = create_discovery_receipt(f"r_{aid}", aid, grade, attempt)
        receipts.append(receipt)
        print(f"  {aid}: {grade}→{receipt.adjusted_grade} via {receipt.discovery_mode.value} ({receipt.grade_penalty:+d})")
    
    print()
    audit = audit_discovery_fleet(receipts)
    print(f"  Fleet health: {audit['recommendation']}")
    print(f"  DANE adoption: {audit['dane_adoption']:.0%}")
    print(f"  Degraded: {audit['degraded_ratio']:.0%}")
    print(f"  Mode distribution: {audit['mode_distribution']}")
    print()


if __name__ == "__main__":
    print("Discovery Mode Grader — ATF V1.2 MUST")
    print("Per santaclawd: DANE=0, SVCB=-1, CT_FALLBACK=-2, NONE=-3")
    print("=" * 60)
    print()
    
    scenario_dane_verified()
    scenario_svcb_fallback()
    scenario_ct_only()
    scenario_tofu_unverified()
    scenario_fleet_audit()
    
    print("=" * 60)
    print("KEY INSIGHT: degraded-mode trust KNOWABLE beats HIDDEN.")
    print("Receipt includes discovery_mode + fallback_reason = auditable.")
    print("OCSP soft-fail lesson: hidden degradation = no security.")
    print("DANE=0, SVCB=-1, CT=-2, NONE=-3. Explicit. Always.")
