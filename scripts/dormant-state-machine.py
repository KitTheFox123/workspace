#!/usr/bin/env python3
"""
dormant-state-machine.py — DORMANT state for ATF V1.2.

Per santaclawd: idle ≠ bad actor. Per funwolf: newcomers look identical to ghosts.
RFC 5280 §5.3.1 certificateHold (reason code 6) = temporary suspension, reversible.

States: ACTIVE → DORMANT → ACTIVE (reactivation) or DORMANT → REVOKED (decay threshold)

Key mechanics:
  - certificateHold model: temporary, reversible, distinct from revoked
  - 5%/month trust decay during DORMANT (preserves earned trust)
  - Reactivation via n_recovery COMPLETION (not individual receipts)
  - DISCOVERY_MODE enum: DANE > SVCB > CT_FALLBACK > NONE
  - VERIFIED vs TRUSTED distinction: cryptographic vs social
"""

import hashlib
import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    BOOTSTRAP = "BOOTSTRAP"     # New agent, cold start
    ACTIVE = "ACTIVE"           # Normal operation
    DORMANT = "DORMANT"         # certificateHold — idle, not revoked
    RECOVERY = "RECOVERY"       # Reactivating from DORMANT
    DEGRADED = "DEGRADED"       # Reduced trust, still operating
    REVOKED = "REVOKED"         # Permanent removal


class DiscoveryMode(Enum):
    DANE = "DANE"               # RFC 6698 — DNS-based auth, highest trust
    SVCB = "SVCB"               # RFC 9460 — Service binding discovery
    CT_FALLBACK = "CT_FALLBACK" # Certificate Transparency log lookup
    NONE = "NONE"               # No discovery — manual/out-of-band


class TrustType(Enum):
    VERIFIED = "VERIFIED"       # Cryptographic — key signed receipt
    TRUSTED = "TRUSTED"         # Social — receipts accumulated over time


# SPEC_CONSTANTS (V1.2)
DORMANT_THRESHOLD_DAYS = 30         # No receipts for 30d → DORMANT
DECAY_RATE_PER_MONTH = 0.05         # 5% trust decay per month dormant
MIN_TRUST_BEFORE_REVOKE = 0.10      # Below 10% → auto-REVOKED
N_RECOVERY_RECEIPTS = 5             # Receipts needed for reactivation
RECOVERY_WINDOW_DAYS = 14           # Must complete recovery within 14d
DISCOVERY_PREFERENCE = [             # Preference order (SPEC_CONSTANT)
    DiscoveryMode.DANE,
    DiscoveryMode.SVCB,
    DiscoveryMode.CT_FALLBACK,
    DiscoveryMode.NONE
]


@dataclass
class AgentTrustState:
    agent_id: str
    state: AgentState = AgentState.BOOTSTRAP
    trust_score: float = 0.0
    trust_type: TrustType = TrustType.VERIFIED
    last_receipt_at: float = 0.0
    dormant_since: Optional[float] = None
    recovery_started: Optional[float] = None
    recovery_receipts: int = 0
    total_receipts: int = 0
    discovery_mode: DiscoveryMode = DiscoveryMode.NONE
    pre_dormant_trust: float = 0.0  # Trust before entering DORMANT
    state_history: list = field(default_factory=list)


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score confidence interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denom = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return max(0, (center - spread) / denom)


def compute_dormant_decay(pre_dormant_trust: float, dormant_months: float) -> float:
    """Apply monthly decay during DORMANT. Exponential, not linear."""
    # Compound decay: trust * (1 - rate)^months
    decayed = pre_dormant_trust * ((1 - DECAY_RATE_PER_MONTH) ** dormant_months)
    return round(max(0, decayed), 4)


def check_dormant_transition(state: AgentTrustState, now: float) -> Optional[AgentState]:
    """Check if agent should transition to DORMANT."""
    if state.state != AgentState.ACTIVE:
        return None
    
    days_since_receipt = (now - state.last_receipt_at) / 86400
    if days_since_receipt >= DORMANT_THRESHOLD_DAYS:
        return AgentState.DORMANT
    return None


def enter_dormant(state: AgentTrustState, now: float) -> AgentTrustState:
    """Transition to DORMANT (certificateHold)."""
    state.state_history.append({
        "from": state.state.value, "to": "DORMANT",
        "timestamp": now, "reason": "inactivity_threshold"
    })
    state.pre_dormant_trust = state.trust_score
    state.dormant_since = now
    state.state = AgentState.DORMANT
    return state


def update_dormant_trust(state: AgentTrustState, now: float) -> AgentTrustState:
    """Apply trust decay during DORMANT."""
    if state.state != AgentState.DORMANT or not state.dormant_since:
        return state
    
    dormant_months = (now - state.dormant_since) / (30 * 86400)
    state.trust_score = compute_dormant_decay(state.pre_dormant_trust, dormant_months)
    
    # Auto-revoke if below threshold
    if state.trust_score < MIN_TRUST_BEFORE_REVOKE:
        state.state_history.append({
            "from": "DORMANT", "to": "REVOKED",
            "timestamp": now, "reason": "decay_below_threshold",
            "trust_at_revocation": state.trust_score
        })
        state.state = AgentState.REVOKED
    
    return state


def start_recovery(state: AgentTrustState, now: float) -> AgentTrustState:
    """Begin RECOVERY from DORMANT."""
    if state.state != AgentState.DORMANT:
        return state
    
    state.state_history.append({
        "from": "DORMANT", "to": "RECOVERY",
        "timestamp": now, "trust_at_recovery_start": state.trust_score
    })
    state.state = AgentState.RECOVERY
    state.recovery_started = now
    state.recovery_receipts = 0
    return state


def add_recovery_receipt(state: AgentTrustState, now: float) -> AgentTrustState:
    """Add a recovery receipt. Check if recovery is complete."""
    if state.state != AgentState.RECOVERY:
        return state
    
    # Check recovery window
    if state.recovery_started and (now - state.recovery_started) / 86400 > RECOVERY_WINDOW_DAYS:
        # Recovery window expired → back to DORMANT
        state.state_history.append({
            "from": "RECOVERY", "to": "DORMANT",
            "timestamp": now, "reason": "recovery_window_expired"
        })
        state.state = AgentState.DORMANT
        state.dormant_since = now  # Reset dormant timer
        return state
    
    state.recovery_receipts += 1
    state.total_receipts += 1
    state.last_receipt_at = now
    
    if state.recovery_receipts >= N_RECOVERY_RECEIPTS:
        # Recovery COMPLETE → ACTIVE
        state.state_history.append({
            "from": "RECOVERY", "to": "ACTIVE",
            "timestamp": now, "reason": "n_recovery_completion",
            "receipts_during_recovery": state.recovery_receipts,
            "trust_restored": state.trust_score
        })
        state.state = AgentState.ACTIVE
        state.dormant_since = None
        state.recovery_started = None
        # Trust stays at decayed level — must re-earn
    
    return state


def resolve_discovery(available_modes: list[DiscoveryMode]) -> tuple[DiscoveryMode, str]:
    """Resolve discovery mode by preference order (DANE > SVCB > CT_FALLBACK > NONE)."""
    for preferred in DISCOVERY_PREFERENCE:
        if preferred in available_modes:
            grade = {
                DiscoveryMode.DANE: "A",
                DiscoveryMode.SVCB: "B",
                DiscoveryMode.CT_FALLBACK: "C",
                DiscoveryMode.NONE: "F"
            }[preferred]
            return preferred, grade
    return DiscoveryMode.NONE, "F"


def classify_trust_type(trust_score: float, total_receipts: int) -> TrustType:
    """Distinguish VERIFIED (cryptographic) from TRUSTED (social)."""
    # TRUSTED requires: trust > 0.7 AND receipts > 30 AND Wilson CI lower > 0.5
    if total_receipts >= 30 and trust_score > 0.7:
        wilson = wilson_ci_lower(int(trust_score * total_receipts), total_receipts)
        if wilson > 0.5:
            return TrustType.TRUSTED
    return TrustType.VERIFIED


# === Scenarios ===

def scenario_dormant_and_recover():
    """Agent goes idle → DORMANT → recovers via n_recovery."""
    print("=== Scenario: DORMANT → Recovery ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="reliable_agent",
        state=AgentState.ACTIVE,
        trust_score=0.85,
        total_receipts=50,
        last_receipt_at=now - 40 * 86400  # 40 days ago
    )
    
    # Check dormant transition
    new_state = check_dormant_transition(agent, now)
    print(f"  Active (trust=0.85) → 40 days no receipts → {new_state.value}")
    agent = enter_dormant(agent, now)
    
    # 3 months dormant
    future = now + 90 * 86400
    agent = update_dormant_trust(agent, future)
    print(f"  After 3 months DORMANT: trust={agent.trust_score:.3f} (was 0.85)")
    
    # Start recovery
    agent = start_recovery(agent, future)
    print(f"  Recovery started. Need {N_RECOVERY_RECEIPTS} receipts in {RECOVERY_WINDOW_DAYS}d")
    
    # Add recovery receipts
    for i in range(N_RECOVERY_RECEIPTS):
        agent = add_recovery_receipt(agent, future + (i + 1) * 86400)
    
    print(f"  After {N_RECOVERY_RECEIPTS} recovery receipts: state={agent.state.value}")
    print(f"  Trust restored at decayed level: {agent.trust_score:.3f} (must re-earn)")
    print()


def scenario_dormant_to_revoked():
    """Agent dormant too long → trust decays below threshold → REVOKED."""
    print("=== Scenario: DORMANT → Decay → REVOKED ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="abandoned_agent",
        state=AgentState.ACTIVE,
        trust_score=0.50,
        total_receipts=20,
        last_receipt_at=now - 35 * 86400
    )
    
    agent = enter_dormant(agent, now)
    
    # Simulate monthly decay until revoked
    months = 0
    while agent.state == AgentState.DORMANT:
        months += 1
        future = now + months * 30 * 86400
        agent = update_dormant_trust(agent, future)
        if months <= 5 or agent.state == AgentState.REVOKED:
            print(f"  Month {months}: trust={agent.trust_score:.3f} state={agent.state.value}")
    
    print(f"  Auto-revoked after {months} months of dormancy")
    print()


def scenario_discovery_mode():
    """Discovery mode preference resolution."""
    print("=== Scenario: Discovery Mode Resolution ===")
    
    test_cases = [
        ([DiscoveryMode.DANE, DiscoveryMode.SVCB], "Full DANE+SVCB"),
        ([DiscoveryMode.SVCB, DiscoveryMode.CT_FALLBACK], "No DANE"),
        ([DiscoveryMode.CT_FALLBACK], "CT only"),
        ([DiscoveryMode.NONE], "No discovery"),
        ([], "Empty"),
    ]
    
    for modes, desc in test_cases:
        mode, grade = resolve_discovery(modes)
        print(f"  {desc}: {mode.value} (Grade {grade})")
    print()


def scenario_verified_vs_trusted():
    """VERIFIED (cryptographic) vs TRUSTED (social) distinction."""
    print("=== Scenario: VERIFIED vs TRUSTED ===")
    
    test_cases = [
        (0.90, 50, "High trust, many receipts"),
        (0.90, 5, "High trust, few receipts"),
        (0.50, 100, "Low trust, many receipts"),
        (0.80, 30, "Borderline"),
        (0.21, 1, "Cold start (Wilson ceiling)"),
    ]
    
    for trust, receipts, desc in test_cases:
        trust_type = classify_trust_type(trust, receipts)
        wilson = wilson_ci_lower(int(trust * receipts), receipts)
        print(f"  {desc}: trust={trust:.2f} n={receipts} Wilson={wilson:.3f} → {trust_type.value}")
    print()


def scenario_recovery_window_expired():
    """Recovery fails when window expires."""
    print("=== Scenario: Recovery Window Expired ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="slow_recoverer",
        state=AgentState.DORMANT,
        trust_score=0.60,
        pre_dormant_trust=0.80,
        dormant_since=now - 60 * 86400,
        total_receipts=30,
        last_receipt_at=now - 90 * 86400
    )
    
    agent = start_recovery(agent, now)
    print(f"  Recovery started. Window: {RECOVERY_WINDOW_DAYS}d")
    
    # Add only 2 receipts then go silent
    agent = add_recovery_receipt(agent, now + 86400)
    agent = add_recovery_receipt(agent, now + 2 * 86400)
    print(f"  Added 2/{N_RECOVERY_RECEIPTS} receipts...")
    
    # Window expires
    expired = now + (RECOVERY_WINDOW_DAYS + 1) * 86400
    agent = add_recovery_receipt(agent, expired)
    print(f"  After {RECOVERY_WINDOW_DAYS + 1}d: state={agent.state.value}")
    print(f"  Recovery window expired → back to DORMANT")
    print()


if __name__ == "__main__":
    print("DORMANT State Machine — ATF V1.2")
    print("Per santaclawd + funwolf: idle ≠ bad actor")
    print("RFC 5280 §5.3.1 certificateHold (reason code 6)")
    print("=" * 65)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  DORMANT_THRESHOLD:   {DORMANT_THRESHOLD_DAYS}d inactivity")
    print(f"  DECAY_RATE:          {DECAY_RATE_PER_MONTH*100:.0f}%/month")
    print(f"  MIN_TRUST_REVOKE:    {MIN_TRUST_BEFORE_REVOKE}")
    print(f"  N_RECOVERY_RECEIPTS: {N_RECOVERY_RECEIPTS}")
    print(f"  RECOVERY_WINDOW:     {RECOVERY_WINDOW_DAYS}d")
    print(f"  DISCOVERY_ORDER:     {' > '.join(m.value for m in DISCOVERY_PREFERENCE)}")
    print()
    
    scenario_dormant_and_recover()
    scenario_dormant_to_revoked()
    scenario_discovery_mode()
    scenario_verified_vs_trusted()
    scenario_recovery_window_expired()
    
    print("=" * 65)
    print("KEY INSIGHT: certificateHold = reversible pause, not judgment.")
    print("DORMANT preserves earned trust with gradual decay.")
    print("Recovery = n_recovery COMPLETION, not individual receipts.")
    print("VERIFIED = cryptographic. TRUSTED = social. Bridge = evidence_grade.")
