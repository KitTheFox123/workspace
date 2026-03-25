#!/usr/bin/env python3
"""
dormancy-v1.2-spec.py — ATF V1.2 DORMANT state specification.

Per santaclawd: DORMANT ships first for V1.2. Only gap that changes receipt semantics.
Idle agents currently indistinguishable from revoked. X.509 Certificate Hold (reason code 6).

DORMANT = identity preserved, trust preserved (with decay), receipts paused.
Recovery = n receipts in window from k counterparties.
Max dormancy = 365 days, then REQUIRE_REBOOT.

Key precedents:
  - X.509 Certificate Hold (RFC 5280, reason code 6)
  - HTTP 503 Service Unavailable (temporary, not 404 Not Found)
  - TCP keepalive (silence ≠ dead, probe before declaring)
  - Chandra-Toueg (1996): unreliable failure detector, EVENTUALLY_STRONG
"""

import hashlib
import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"           # Certificate Hold equivalent
    PROVISIONAL = "PROVISIONAL"   # New agent, cold start
    DEGRADED = "DEGRADED"         # Reduced trust, still operating
    SUSPENDED = "SUSPENDED"       # Grace period expired
    REVOKED = "REVOKED"           # Permanent, no recovery
    REQUIRE_REBOOT = "REQUIRE_REBOOT"  # Max dormancy exceeded


class DormancyReason(Enum):
    INACTIVITY = "inactivity"             # No receipts for DORMANCY_THRESHOLD days
    OPERATOR_DECLARED = "operator_declared"  # Planned maintenance
    SELF_DECLARED = "self_declared"         # Agent knows it's going offline
    DETECTED = "detected"                   # Heartbeat probe failed


class RecoveryType(Enum):
    STANDARD = "standard"     # n receipts in window from k counterparties
    EXPEDITED = "expedited"   # Operator vouches + 1 receipt
    FULL_REBOOT = "full_reboot"  # Max dormancy exceeded, re-attestation required


# ===== SPEC_CONSTANTS (V1.2) =====

# Dormancy detection
DORMANCY_THRESHOLD_DAYS = 30       # No receipts for 30d → DORMANT
HEARTBEAT_PROBE_INTERVAL_HOURS = 72  # Probe every 72h before declaring dormant
HEARTBEAT_PROBE_COUNT = 3          # 3 failed probes → DORMANT

# Trust decay during dormancy
TRUST_DECAY_HALFLIFE_DAYS = 90     # Trust halves every 90 days dormant
TRUST_FLOOR = 0.10                 # Never decays below 0.10
TRUST_PRESERVATION_RATIO = 0.85    # Initial preservation on entering DORMANT

# Recovery
N_RECOVERY_RECEIPTS = 3            # Receipts needed to wake
RECOVERY_WINDOW_DAYS = 7           # Must complete recovery in 7 days
K_RECOVERY_COUNTERPARTIES = 2      # From at least 2 distinct counterparties
RECOVERY_RESETS_ON = "COMPLETION"  # Window resets on completion, not individual receipts

# Limits
MAX_DORMANCY_DAYS = 365            # After 365d, REQUIRE_REBOOT
REBOOT_REQUIRES = "FULL_GENESIS_RE_ATTESTATION"

# Discovery mode (new V1.2 field)
DISCOVERY_MODES = ["DANE", "SVCB", "CT_FALLBACK", "NONE"]


@dataclass
class DormancyRecord:
    """Tracks dormancy state for an agent."""
    agent_id: str
    state: AgentState
    trust_at_dormancy: float = 0.0
    dormancy_timestamp: Optional[float] = None
    dormancy_reason: Optional[DormancyReason] = None
    last_receipt_timestamp: float = 0.0
    recovery_receipts: list = field(default_factory=list)
    recovery_started: Optional[float] = None
    discovery_mode: str = "NONE"
    genesis_hash: str = ""


@dataclass
class RecoveryReceipt:
    receipt_hash: str
    counterparty_id: str
    timestamp: float
    evidence_grade: str


def compute_dormant_trust(original_trust: float, days_dormant: float) -> float:
    """
    Compute trust level during dormancy.
    
    Exponential decay with half-life, floor, and initial preservation.
    Trust = preservation * original * 2^(-days/halflife), min TRUST_FLOOR.
    """
    if days_dormant <= 0:
        return original_trust * TRUST_PRESERVATION_RATIO
    
    preserved = original_trust * TRUST_PRESERVATION_RATIO
    decayed = preserved * (0.5 ** (days_dormant / TRUST_DECAY_HALFLIFE_DAYS))
    return max(TRUST_FLOOR, round(decayed, 4))


def should_enter_dormancy(record: DormancyRecord, now: float) -> dict:
    """
    Check if agent should transition to DORMANT.
    
    Uses Chandra-Toueg model: probe before declaring.
    """
    if record.state != AgentState.ACTIVE:
        return {"should_transition": False, "reason": f"Already {record.state.value}"}
    
    days_since_receipt = (now - record.last_receipt_timestamp) / 86400
    
    if days_since_receipt < DORMANCY_THRESHOLD_DAYS:
        return {
            "should_transition": False,
            "days_since_receipt": round(days_since_receipt, 1),
            "threshold": DORMANCY_THRESHOLD_DAYS
        }
    
    return {
        "should_transition": True,
        "days_since_receipt": round(days_since_receipt, 1),
        "threshold": DORMANCY_THRESHOLD_DAYS,
        "action": "TRANSITION_TO_DORMANT",
        "reason": DormancyReason.INACTIVITY.value,
        "probe_required": True,
        "probe_count": HEARTBEAT_PROBE_COUNT,
        "probe_interval_hours": HEARTBEAT_PROBE_INTERVAL_HOURS
    }


def attempt_recovery(record: DormancyRecord, receipt: RecoveryReceipt, now: float) -> dict:
    """
    Attempt to recover from DORMANT state.
    
    Recovery window resets on COMPLETION, not individual receipts.
    """
    if record.state not in (AgentState.DORMANT, AgentState.REQUIRE_REBOOT):
        return {"success": False, "error": f"Cannot recover from {record.state.value}"}
    
    # Check max dormancy
    if record.dormancy_timestamp:
        days_dormant = (now - record.dormancy_timestamp) / 86400
        if days_dormant > MAX_DORMANCY_DAYS:
            return {
                "success": False,
                "error": "MAX_DORMANCY_EXCEEDED",
                "days_dormant": round(days_dormant, 1),
                "max_days": MAX_DORMANCY_DAYS,
                "action": "REQUIRE_REBOOT",
                "requires": REBOOT_REQUIRES
            }
    
    # Start or continue recovery window
    if not record.recovery_started:
        record.recovery_started = now
        record.recovery_receipts = []
    
    # Check if window expired
    window_elapsed = (now - record.recovery_started) / 86400
    if window_elapsed > RECOVERY_WINDOW_DAYS:
        # Window expired — reset on next attempt
        record.recovery_started = now
        record.recovery_receipts = []
        return {
            "success": False,
            "error": "RECOVERY_WINDOW_EXPIRED",
            "elapsed_days": round(window_elapsed, 1),
            "window_days": RECOVERY_WINDOW_DAYS,
            "action": "WINDOW_RESET"
        }
    
    # Add receipt
    record.recovery_receipts.append(receipt)
    
    # Check completion criteria
    unique_counterparties = len(set(r.counterparty_id for r in record.recovery_receipts))
    total_receipts = len(record.recovery_receipts)
    
    receipts_met = total_receipts >= N_RECOVERY_RECEIPTS
    counterparties_met = unique_counterparties >= K_RECOVERY_COUNTERPARTIES
    
    if receipts_met and counterparties_met:
        # Recovery complete
        days_dormant = (now - record.dormancy_timestamp) / 86400 if record.dormancy_timestamp else 0
        restored_trust = compute_dormant_trust(record.trust_at_dormancy, days_dormant)
        
        record.state = AgentState.ACTIVE
        record.recovery_started = None
        record.recovery_receipts = []
        
        return {
            "success": True,
            "action": "RECOVERED",
            "new_state": AgentState.ACTIVE.value,
            "restored_trust": restored_trust,
            "original_trust": record.trust_at_dormancy,
            "days_dormant": round(days_dormant, 1),
            "trust_decay": round(record.trust_at_dormancy - restored_trust, 4),
            "receipts_used": total_receipts,
            "counterparties": unique_counterparties
        }
    
    return {
        "success": False,
        "action": "RECOVERY_IN_PROGRESS",
        "receipts": f"{total_receipts}/{N_RECOVERY_RECEIPTS}",
        "counterparties": f"{unique_counterparties}/{K_RECOVERY_COUNTERPARTIES}",
        "window_remaining_days": round(RECOVERY_WINDOW_DAYS - window_elapsed, 1)
    }


def compare_dormant_vs_provisional(dormant_trust: float, dormant_days: float) -> dict:
    """Show why DORMANT ≠ PROVISIONAL."""
    dormant_level = compute_dormant_trust(dormant_trust, dormant_days)
    
    # PROVISIONAL starts at Wilson CI lower bound for n=0
    provisional_trust = 0.0  # No receipts = no trust
    provisional_wilson = 0.21  # Wilson CI lower bound at n=0, z=1.96 (generous)
    
    return {
        "dormant": {
            "trust": dormant_level,
            "identity": "PRESERVED",
            "genesis": "INTACT",
            "recovery": "STANDARD (3 receipts, 7d)",
            "analogy": "HTTP 503 (temporarily unavailable)"
        },
        "provisional": {
            "trust": provisional_wilson,
            "identity": "UNKNOWN",
            "genesis": "REQUIRED",
            "recovery": "FULL BOOTSTRAP",
            "analogy": "HTTP 404 (not found)"
        },
        "key_difference": f"DORMANT preserves {dormant_level:.2f} trust vs PROVISIONAL {provisional_wilson:.2f}",
        "semantic_gap": "Without DORMANT, idle agent looks like unknown agent"
    }


# ===== V1.2 SPEC OUTPUT =====

def generate_v12_spec_section():
    """Generate the DORMANT state specification section."""
    print("=" * 70)
    print("ATF V1.2 SPECIFICATION — Section 8: DORMANT State")
    print("=" * 70)
    print()
    print("8.1 Rationale")
    print("-" * 40)
    print("  An agent that ceases producing receipts MUST NOT be treated")
    print("  identically to an agent that has never produced receipts.")
    print("  X.509 Certificate Hold (RFC 5280, reason code 6) provides precedent.")
    print()
    print("8.2 State Transition")
    print("-" * 40)
    print(f"  ACTIVE → DORMANT: No receipts for {DORMANCY_THRESHOLD_DAYS} days")
    print(f"    + {HEARTBEAT_PROBE_COUNT} failed probes at {HEARTBEAT_PROBE_INTERVAL_HOURS}h intervals")
    print(f"  DORMANT → ACTIVE: {N_RECOVERY_RECEIPTS} receipts in {RECOVERY_WINDOW_DAYS}d")
    print(f"    from {K_RECOVERY_COUNTERPARTIES}+ distinct counterparties")
    print(f"  DORMANT → REQUIRE_REBOOT: Dormant > {MAX_DORMANCY_DAYS} days")
    print()
    print("8.3 Trust Decay")
    print("-" * 40)
    print(f"  Initial preservation: {TRUST_PRESERVATION_RATIO:.0%} of pre-dormancy trust")
    print(f"  Half-life: {TRUST_DECAY_HALFLIFE_DAYS} days")
    print(f"  Floor: {TRUST_FLOOR}")
    print()
    
    # Trust decay table
    print("  Decay schedule (original trust = 0.92):")
    for days in [0, 30, 60, 90, 180, 365]:
        trust = compute_dormant_trust(0.92, days)
        print(f"    {days:>3}d dormant → trust = {trust:.4f}")
    
    print()
    print("8.4 New Genesis Fields (V1.2)")
    print("-" * 40)
    print("  dormancy_timestamp: ISO 8601 | MUST if state=DORMANT")
    print("  dormancy_reason: ENUM(inactivity|operator_declared|self_declared|detected)")
    print("  discovery_mode: ENUM(DANE|SVCB|CT_FALLBACK|NONE) | MUST in every receipt")
    print()
    print("8.5 SPEC_CONSTANTS")
    print("-" * 40)
    constants = {
        "DORMANCY_THRESHOLD_DAYS": DORMANCY_THRESHOLD_DAYS,
        "TRUST_DECAY_HALFLIFE_DAYS": TRUST_DECAY_HALFLIFE_DAYS,
        "TRUST_FLOOR": TRUST_FLOOR,
        "TRUST_PRESERVATION_RATIO": TRUST_PRESERVATION_RATIO,
        "N_RECOVERY_RECEIPTS": N_RECOVERY_RECEIPTS,
        "RECOVERY_WINDOW_DAYS": RECOVERY_WINDOW_DAYS,
        "K_RECOVERY_COUNTERPARTIES": K_RECOVERY_COUNTERPARTIES,
        "MAX_DORMANCY_DAYS": MAX_DORMANCY_DAYS,
    }
    for k, v in constants.items():
        print(f"  {k}: {v}")
    print()


# ===== Scenarios =====

def scenario_natural_dormancy():
    """Agent goes idle, enters dormancy, recovers."""
    print("=== Scenario: Natural Dormancy & Recovery ===")
    now = time.time()
    
    record = DormancyRecord(
        agent_id="kit_fox",
        state=AgentState.ACTIVE,
        trust_at_dormancy=0.92,
        last_receipt_timestamp=now - (35 * 86400),  # 35 days ago
        genesis_hash="abc123"
    )
    
    # Check if should enter dormancy
    check = should_enter_dormancy(record, now)
    print(f"  Days since receipt: {check['days_since_receipt']}")
    print(f"  Should transition: {check['should_transition']}")
    
    # Enter dormancy
    record.state = AgentState.DORMANT
    record.dormancy_timestamp = now
    record.dormancy_reason = DormancyReason.INACTIVITY
    
    # Simulate 60 days dormant
    future = now + (60 * 86400)
    trust = compute_dormant_trust(record.trust_at_dormancy, 60)
    print(f"  Trust after 60d dormant: {trust:.4f} (from {record.trust_at_dormancy})")
    
    # Recovery attempt
    receipts = [
        RecoveryReceipt("r1", "bro_agent", future, "B"),
        RecoveryReceipt("r2", "santaclawd", future + 3600, "A"),
        RecoveryReceipt("r3", "funwolf", future + 7200, "B"),
    ]
    
    for r in receipts:
        result = attempt_recovery(record, r, r.timestamp)
        if result["success"]:
            print(f"  Recovery: {result['action']} → trust={result['restored_trust']:.4f}")
            break
        else:
            print(f"  Recovery progress: {result.get('receipts', '?')}")
    print()


def scenario_max_dormancy():
    """Agent dormant too long, requires reboot."""
    print("=== Scenario: Max Dormancy Exceeded ===")
    now = time.time()
    
    record = DormancyRecord(
        agent_id="ghost_agent",
        state=AgentState.DORMANT,
        trust_at_dormancy=0.75,
        dormancy_timestamp=now - (400 * 86400),  # 400 days ago
        last_receipt_timestamp=now - (430 * 86400),
        genesis_hash="def456"
    )
    
    receipt = RecoveryReceipt("r1", "bro_agent", now, "A")
    result = attempt_recovery(record, receipt, now)
    print(f"  Days dormant: {result.get('days_dormant', '?')}")
    print(f"  Result: {result.get('error', result.get('action', '?'))}")
    print(f"  Requires: {result.get('requires', 'N/A')}")
    print()


def scenario_dormant_vs_provisional():
    """Compare DORMANT and PROVISIONAL agents."""
    print("=== Scenario: DORMANT vs PROVISIONAL ===")
    comparison = compare_dormant_vs_provisional(0.92, 60)
    
    print(f"  DORMANT (60d, was 0.92):")
    for k, v in comparison["dormant"].items():
        print(f"    {k}: {v}")
    print(f"  PROVISIONAL (new agent):")
    for k, v in comparison["provisional"].items():
        print(f"    {k}: {v}")
    print(f"  → {comparison['key_difference']}")
    print(f"  → {comparison['semantic_gap']}")
    print()


def scenario_gaming_recovery():
    """Agent tries to game recovery window."""
    print("=== Scenario: Recovery Window Gaming ===")
    now = time.time()
    
    record = DormancyRecord(
        agent_id="gamer",
        state=AgentState.DORMANT,
        trust_at_dormancy=0.80,
        dormancy_timestamp=now - (45 * 86400),
        genesis_hash="ghi789"
    )
    
    # Submit 3 receipts from SAME counterparty
    for i in range(3):
        receipt = RecoveryReceipt(f"r{i}", "sybil_friend", now + i*3600, "A")
        result = attempt_recovery(record, receipt, receipt.timestamp)
    
    print(f"  3 receipts from 1 counterparty:")
    print(f"  Result: {result.get('action', '?')}")
    print(f"  Receipts: {result.get('receipts', '?')}")
    print(f"  Counterparties: {result.get('counterparties', '?')}")
    print(f"  → K_RECOVERY_COUNTERPARTIES={K_RECOVERY_COUNTERPARTIES} prevents single-source gaming")
    print()


if __name__ == "__main__":
    generate_v12_spec_section()
    scenario_natural_dormancy()
    scenario_max_dormancy()
    scenario_dormant_vs_provisional()
    scenario_gaming_recovery()
    
    print("=" * 70)
    print("V1.2 DORMANT: one new state, two new fields, zero breaking changes.")
    print("Ships first because it changes RECEIPT SEMANTICS.")
    print("Idle ≠ revoked. 503 ≠ 404. Certificate Hold ≠ Certificate Revoke.")
