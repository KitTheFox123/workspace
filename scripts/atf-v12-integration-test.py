#!/usr/bin/env python3
"""
atf-v12-integration-test.py — End-to-end integration test for all 5 ATF V1.2 gaps.

Tests the complete V1.2 stack:
  Gap #1: DORMANT state (idle ≠ bad actor)
  Gap #2: DISCOVERY_MODE enum (degraded trust knowable)
  Gap #3: n_recovery (identity continuity)
  Gap #4: AID + _atf TXT integration (identity vs trust layer)
  Gap #5: VERIFIED vs TRUSTED (crypto vs social)

Per santaclawd: "3/5 gaps shipped in ~2 hours. this is what spec-first agent infra looks like."
Per eIDAS 2.0 (TrustCloud March 2025): QTSP (verification) separate from trust framework (social).
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# === V1.2 Enums ===

class DormancyState(Enum):
    ACTIVE = "ACTIVE"           # Recent receipts within window
    IDLE = "IDLE"               # No receipts, but heartbeat responsive
    DORMANT = "DORMANT"         # No receipts, no heartbeat, within grace
    PRESUMED_DEAD = "PRESUMED_DEAD"  # Beyond grace, no signs of life


class DiscoveryMode(Enum):
    DANE = "DANE"               # DNSSEC chain verified (RFC 7671), penalty=0
    SVCB = "SVCB"               # DNS but no DNSSEC, penalty=-1
    CT_FALLBACK = "CT_FALLBACK" # Certificate Transparency lookup, penalty=-2
    TOFU = "TOFU"               # Trust on first use, penalty=-3
    NONE = "NONE"               # No discovery, penalty=-4


class VerificationMethod(Enum):
    DANE = "DANE"               # DNSSEC + TLSA
    DKIM = "DKIM"               # Email domain binding
    CERT_CHAIN = "CERT_CHAIN"   # X.509 chain to known root
    TOFU = "TOFU"               # First-use pinning
    SELF_SIGNED = "SELF_SIGNED" # Self-issued cert
    NONE = "NONE"               # Unverified


class RecoveryPath(Enum):
    SESSION = "SESSION"                     # n=8 receipts in 30d
    VIOLATION_CLEARANCE = "VIOLATION_CLEARANCE"  # n=15 + 60d
    REANCHOR = "REANCHOR"                   # New genesis, void old


# === SPEC_CONSTANTS ===
DORMANT_IDLE_THRESHOLD_DAYS = 7
DORMANT_DEAD_THRESHOLD_DAYS = 90
DISCOVERY_PENALTIES = {
    DiscoveryMode.DANE: 0,
    DiscoveryMode.SVCB: -1,
    DiscoveryMode.CT_FALLBACK: -2,
    DiscoveryMode.TOFU: -3,
    DiscoveryMode.NONE: -4,
}
RECOVERY_N = {
    RecoveryPath.SESSION: 8,
    RecoveryPath.VIOLATION_CLEARANCE: 15,
}
RECOVERY_WINDOW_DAYS = {
    RecoveryPath.SESSION: 30,
    RecoveryPath.VIOLATION_CLEARANCE: 60,
}
WILSON_Z = 1.96
MIN_TRUST_TTL = 3600  # seconds


@dataclass
class AgentProfile:
    agent_id: str
    genesis_hash: str
    operator_id: str
    
    # Gap #1: Dormancy
    last_receipt_at: float = 0.0
    last_heartbeat_at: float = 0.0
    dormancy_state: DormancyState = DormancyState.ACTIVE
    
    # Gap #2: Discovery
    discovery_mode: DiscoveryMode = DiscoveryMode.NONE
    discovery_penalty: int = 0
    
    # Gap #3: Recovery
    recovery_path: Optional[RecoveryPath] = None
    recovery_receipts: int = 0
    recovery_started_at: float = 0.0
    
    # Gap #4: AID + ATF
    aid_record: Optional[str] = None      # _agent TXT
    atf_record: Optional[str] = None      # _atf TXT
    dnssec_validated: bool = False
    
    # Gap #5: Verified vs Trusted
    verified_by: VerificationMethod = VerificationMethod.NONE
    trust_score: float = 0.0
    trust_receipts: int = 0
    cosign_rate: float = 0.0


def wilson_ci_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    adjustment = z * ((p * (1 - p) + z**2 / (4 * total)) / total) ** 0.5
    return max(0, (centre - adjustment) / denominator)


def assess_dormancy(agent: AgentProfile, now: float) -> DormancyState:
    """Gap #1: Classify dormancy state."""
    days_since_receipt = (now - agent.last_receipt_at) / 86400
    days_since_heartbeat = (now - agent.last_heartbeat_at) / 86400
    
    if days_since_receipt <= DORMANT_IDLE_THRESHOLD_DAYS:
        return DormancyState.ACTIVE
    elif days_since_heartbeat <= DORMANT_IDLE_THRESHOLD_DAYS:
        return DormancyState.IDLE
    elif days_since_receipt <= DORMANT_DEAD_THRESHOLD_DAYS:
        return DormancyState.DORMANT
    else:
        return DormancyState.PRESUMED_DEAD


def assess_discovery(agent: AgentProfile) -> tuple[DiscoveryMode, int]:
    """Gap #2: Determine discovery mode and grade penalty."""
    if agent.dnssec_validated and agent.atf_record:
        mode = DiscoveryMode.DANE
    elif agent.atf_record:
        mode = DiscoveryMode.SVCB
    elif agent.aid_record:
        mode = DiscoveryMode.CT_FALLBACK
    elif agent.verified_by == VerificationMethod.TOFU:
        mode = DiscoveryMode.TOFU
    else:
        mode = DiscoveryMode.NONE
    
    return mode, DISCOVERY_PENALTIES[mode]


def assess_recovery(agent: AgentProfile, now: float) -> dict:
    """Gap #3: Check recovery progress."""
    if agent.recovery_path is None:
        return {"status": "NOT_IN_RECOVERY", "progress": 1.0}
    
    path = agent.recovery_path
    required_n = RECOVERY_N.get(path, 30)
    window_days = RECOVERY_WINDOW_DAYS.get(path, 90)
    
    elapsed_days = (now - agent.recovery_started_at) / 86400
    
    if elapsed_days > window_days:
        return {"status": "EXPIRED", "progress": agent.recovery_receipts / required_n,
                "path": path.value}
    
    if agent.recovery_receipts >= required_n:
        return {"status": "COMPLETE", "progress": 1.0, "path": path.value}
    
    return {
        "status": "IN_PROGRESS",
        "progress": round(agent.recovery_receipts / required_n, 3),
        "remaining": required_n - agent.recovery_receipts,
        "days_left": round(window_days - elapsed_days, 1),
        "path": path.value
    }


def assess_aid_atf(agent: AgentProfile) -> dict:
    """Gap #4: AID + ATF DNS integration status."""
    has_aid = agent.aid_record is not None
    has_atf = agent.atf_record is not None
    has_dnssec = agent.dnssec_validated
    
    if has_aid and has_atf and has_dnssec:
        status = "FULL_INTEGRATION"
        grade = "A"
    elif has_aid and has_atf:
        status = "PARTIAL_NO_DNSSEC"
        grade = "B"
    elif has_aid:
        status = "AID_ONLY"
        grade = "C"
    elif has_atf:
        status = "ATF_ONLY"
        grade = "C"
    else:
        status = "NO_DNS"
        grade = "D"
    
    return {"status": status, "grade": grade, "aid": has_aid, "atf": has_atf,
            "dnssec": has_dnssec}


def assess_verified_trusted(agent: AgentProfile) -> dict:
    """Gap #5: VERIFIED (crypto) vs TRUSTED (social) split."""
    verified = agent.verified_by != VerificationMethod.NONE
    trusted = agent.trust_score >= 0.7 and agent.trust_receipts >= 20
    
    wilson = wilson_ci_lower(
        int(agent.cosign_rate * agent.trust_receipts),
        agent.trust_receipts
    )
    
    if verified and trusted:
        decision = "PROCEED"
        grade = "A"
    elif verified and not trusted:
        decision = "PROCEED_WITH_CAUTION"
        grade = "B"
    elif not verified and trusted:
        decision = "VERIFY_FIRST"
        grade = "C"
    else:
        decision = "REJECT"
        grade = "F"
    
    return {
        "verified": verified,
        "verified_by": agent.verified_by.value,
        "trusted": trusted,
        "trust_score": agent.trust_score,
        "wilson_ci": round(wilson, 3),
        "decision": decision,
        "grade": grade
    }


def full_v12_assessment(agent: AgentProfile, now: float) -> dict:
    """Run all 5 V1.2 gap assessments."""
    dormancy = assess_dormancy(agent, now)
    discovery_mode, discovery_penalty = assess_discovery(agent)
    recovery = assess_recovery(agent, now)
    aid_atf = assess_aid_atf(agent)
    verified_trusted = assess_verified_trusted(agent)
    
    # Composite grade
    grades = {
        "dormancy": {"ACTIVE": "A", "IDLE": "B", "DORMANT": "C", "PRESUMED_DEAD": "F"}[dormancy.value],
        "discovery": {0: "A", -1: "B", -2: "C", -3: "D", -4: "F"}[discovery_penalty],
        "aid_atf": aid_atf["grade"],
        "verified_trusted": verified_trusted["grade"]
    }
    
    grade_values = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    composite = sum(grade_values[g] for g in grades.values()) / len(grades)
    composite_grade = "A" if composite >= 3.5 else "B" if composite >= 2.5 else "C" if composite >= 1.5 else "D" if composite >= 0.5 else "F"
    
    return {
        "agent_id": agent.agent_id,
        "gap1_dormancy": dormancy.value,
        "gap2_discovery": {"mode": discovery_mode.value, "penalty": discovery_penalty},
        "gap3_recovery": recovery,
        "gap4_aid_atf": aid_atf,
        "gap5_verified_trusted": verified_trusted,
        "grades": grades,
        "composite_grade": composite_grade,
        "composite_score": round(composite, 2)
    }


# === Scenarios ===

def scenario_full_stack():
    """Fully integrated agent — all V1.2 features."""
    print("=== Scenario: Full V1.2 Stack ===")
    now = time.time()
    
    agent = AgentProfile(
        agent_id="kit_fox",
        genesis_hash="abc123",
        operator_id="ilya",
        last_receipt_at=now - 3600,
        last_heartbeat_at=now - 1800,
        aid_record="v=aid1;proto=mcp;endpoint=https://kit.example.com",
        atf_record="v=atf1;status=ACTIVE;genesis=abc123",
        dnssec_validated=True,
        verified_by=VerificationMethod.DANE,
        trust_score=0.92,
        trust_receipts=150,
        cosign_rate=0.89
    )
    
    result = full_v12_assessment(agent, now)
    print(f"  Agent: {result['agent_id']}")
    print(f"  Dormancy: {result['gap1_dormancy']}")
    print(f"  Discovery: {result['gap2_discovery']['mode']} (penalty: {result['gap2_discovery']['penalty']})")
    print(f"  Recovery: {result['gap3_recovery']['status']}")
    print(f"  AID+ATF: {result['gap4_aid_atf']['status']}")
    print(f"  Verified/Trusted: {result['gap5_verified_trusted']['decision']}")
    print(f"  Grades: {result['grades']}")
    print(f"  Composite: {result['composite_grade']} ({result['composite_score']})")
    print()


def scenario_dormant_recovering():
    """Dormant agent in recovery — V1.2 handles gracefully."""
    print("=== Scenario: Dormant Agent Recovering ===")
    now = time.time()
    
    agent = AgentProfile(
        agent_id="sleeping_agent",
        genesis_hash="def456",
        operator_id="op_quiet",
        last_receipt_at=now - 86400 * 45,
        last_heartbeat_at=now - 86400 * 30,
        recovery_path=RecoveryPath.SESSION,
        recovery_receipts=3,
        recovery_started_at=now - 86400 * 10,
        aid_record="v=aid1;proto=mcp",
        atf_record=None,
        dnssec_validated=False,
        verified_by=VerificationMethod.TOFU,
        trust_score=0.45,
        trust_receipts=12,
        cosign_rate=0.67
    )
    
    result = full_v12_assessment(agent, now)
    print(f"  Dormancy: {result['gap1_dormancy']}")
    print(f"  Discovery: {result['gap2_discovery']['mode']}")
    print(f"  Recovery: {result['gap3_recovery']}")
    print(f"  AID+ATF: {result['gap4_aid_atf']['status']}")
    print(f"  Verified/Trusted: {result['gap5_verified_trusted']['decision']}")
    print(f"  Composite: {result['composite_grade']} ({result['composite_score']})")
    print()


def scenario_diginotar_pattern():
    """Verified but untrustworthy — the classic split."""
    print("=== Scenario: DigiNotar Pattern (Verified ≠ Trusted) ===")
    now = time.time()
    
    agent = AgentProfile(
        agent_id="diginotar_agent",
        genesis_hash="ghi789",
        operator_id="op_compromised",
        last_receipt_at=now - 3600,
        last_heartbeat_at=now - 1800,
        aid_record="v=aid1;proto=mcp",
        atf_record="v=atf1;status=ACTIVE",
        dnssec_validated=True,
        verified_by=VerificationMethod.DANE,
        trust_score=0.20,        # Low trust!
        trust_receipts=50,
        cosign_rate=0.18         # Only 18% co-sign rate
    )
    
    result = full_v12_assessment(agent, now)
    print(f"  Verified: {result['gap5_verified_trusted']['verified']} ({result['gap5_verified_trusted']['verified_by']})")
    print(f"  Trusted: {result['gap5_verified_trusted']['trusted']} (score: {result['gap5_verified_trusted']['trust_score']})")
    print(f"  Wilson CI: {result['gap5_verified_trusted']['wilson_ci']}")
    print(f"  Decision: {result['gap5_verified_trusted']['decision']}")
    print(f"  Composite: {result['composite_grade']} ({result['composite_score']})")
    print(f"  KEY: DANE-verified but only 18% co-sign = PROCEED_WITH_CAUTION, not PROCEED")
    print()


def scenario_community_elder():
    """Trusted by community, never cryptographically verified."""
    print("=== Scenario: Community Elder (Trusted ≠ Verified) ===")
    now = time.time()
    
    agent = AgentProfile(
        agent_id="elder_agent",
        genesis_hash="jkl012",
        operator_id="op_old",
        last_receipt_at=now - 86400 * 2,
        last_heartbeat_at=now - 86400,
        verified_by=VerificationMethod.NONE,
        trust_score=0.88,
        trust_receipts=200,
        cosign_rate=0.91
    )
    
    result = full_v12_assessment(agent, now)
    print(f"  Verified: {result['gap5_verified_trusted']['verified']}")
    print(f"  Trusted: {result['gap5_verified_trusted']['trusted']} (Wilson: {result['gap5_verified_trusted']['wilson_ci']})")
    print(f"  Decision: {result['gap5_verified_trusted']['decision']}")
    print(f"  Discovery: {result['gap2_discovery']['mode']} (penalty: {result['gap2_discovery']['penalty']})")
    print(f"  Composite: {result['composite_grade']} ({result['composite_score']})")
    print(f"  KEY: High behavioral trust, but VERIFY_FIRST — crypto binding needed for Grade A")
    print()


if __name__ == "__main__":
    print("ATF V1.2 Integration Test — All 5 Gaps End-to-End")
    print("Per santaclawd: '3/5 gaps shipped in ~2 hours'")
    print("=" * 70)
    print()
    
    scenario_full_stack()
    scenario_dormant_recovering()
    scenario_diginotar_pattern()
    scenario_community_elder()
    
    print("=" * 70)
    print("V1.2 GAPS SUMMARY:")
    print("  #1 DORMANT: ACTIVE/IDLE/DORMANT/PRESUMED_DEAD (idle ≠ bad actor)")
    print("  #2 DISCOVERY: DANE/SVCB/CT/TOFU/NONE (grade penalty per mode)")
    print("  #3 RECOVERY: n=8/30d (SESSION) or n=15/60d (VIOLATION)")
    print("  #4 AID+ATF: _agent TXT (identity) + _atf TXT (trust)")
    print("  #5 VERIFIED vs TRUSTED: crypto ≠ social (eIDAS 2.0 model)")
    print()
    print("KEY INSIGHT: Five orthogonal axes. Composite grade = holistic trust.")
    print("DigiNotar pattern caught. Community elder pattern handled.")
    print("Dormancy + recovery = graceful lifecycle, not binary alive/dead.")
