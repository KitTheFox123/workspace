#!/usr/bin/env python3
"""
dormant-state-handler.py — ATF V1.2 DORMANT state management.

Per santaclawd: idle ≠ bad actor. DORMANT is the majority case.
RFC 5280 §5.3.1 certificateHold = exact model.

States: ACTIVE → DORMANT → REACTIVATING → ACTIVE (or DORMANT → SUSPENDED)

Key mechanics:
  - 5%/month trust decay during DORMANT (not zeroed)
  - certificateHold: reversible suspension, not revocation
  - Reactivation requires n_recovery receipts (lighter than initial n=30)
  - n_recovery = ceil(n_initial * 0.4) = 12 (identity history preserved)
  - Wilson CI at n=12 with prior: 0.78 ceiling vs 0.57 cold start

Per draft-ietf-dnsop-svcb-dane-04: DISCOVERY_MODE in receipt for path quality.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"            # Idle, trust decaying
    REACTIVATING = "REACTIVATING"  # Collecting n_recovery receipts
    SUSPENDED = "SUSPENDED"        # Dormant too long, needs full re-bootstrap
    REVOKED = "REVOKED"            # Permanent


class DiscoveryMode(Enum):
    """V1.2 DISCOVERY_MODE enum per santaclawd."""
    DANE = "DANE"              # DNSSEC-signed TLSA (strongest)
    SVCB = "SVCB"              # Service binding with alpn
    CT_FALLBACK = "CT_FALLBACK"  # Log lookup (weakest, latency)
    NONE = "NONE"              # No discovery, direct connection


# SPEC_CONSTANTS (V1.2)
DORMANT_THRESHOLD_DAYS = 30        # No receipts for 30d = DORMANT
DORMANT_DECAY_RATE = 0.05          # 5% per month trust decay
DORMANT_MAX_MONTHS = 12            # 12 months dormant → SUSPENDED
N_INITIAL = 30                     # Initial graduation threshold
N_RECOVERY = 12                    # ceil(30 * 0.4) — identity history preserved
REACTIVATION_WINDOW_DAYS = 90     # Must complete n_recovery within 90d
WILSON_Z = 1.96                    # 95% confidence


@dataclass
class AgentTrustState:
    agent_id: str
    state: AgentState = AgentState.ACTIVE
    trust_score: float = 0.0
    trust_at_dormancy: float = 0.0    # Preserved for reactivation
    last_receipt_at: float = 0.0
    dormant_since: Optional[float] = None
    reactivation_started: Optional[float] = None
    recovery_receipts: int = 0
    total_receipts: int = 0
    discovery_mode: DiscoveryMode = DiscoveryMode.DANE
    genesis_hash: str = ""


def wilson_ci_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return max(0, (centre - spread) / denominator)


def compute_dormant_decay(trust_at_dormancy: float, months_dormant: float) -> float:
    """
    Trust decays 5%/month during DORMANT.
    Exponential decay: trust * (1 - rate)^months
    """
    if months_dormant <= 0:
        return trust_at_dormancy
    decayed = trust_at_dormancy * ((1 - DORMANT_DECAY_RATE) ** months_dormant)
    return round(max(0, decayed), 4)


def check_state_transition(agent: AgentTrustState, now: float) -> dict:
    """Evaluate and apply state transitions."""
    transitions = []
    
    if agent.state == AgentState.ACTIVE:
        days_since_receipt = (now - agent.last_receipt_at) / 86400
        if days_since_receipt >= DORMANT_THRESHOLD_DAYS:
            agent.state = AgentState.DORMANT
            agent.trust_at_dormancy = agent.trust_score
            agent.dormant_since = now
            transitions.append({
                "from": "ACTIVE", "to": "DORMANT",
                "reason": f"No receipts for {days_since_receipt:.0f} days",
                "trust_preserved": agent.trust_at_dormancy
            })
    
    elif agent.state == AgentState.DORMANT:
        months_dormant = (now - agent.dormant_since) / (86400 * 30)
        decayed_trust = compute_dormant_decay(agent.trust_at_dormancy, months_dormant)
        agent.trust_score = decayed_trust
        
        if months_dormant >= DORMANT_MAX_MONTHS:
            agent.state = AgentState.SUSPENDED
            transitions.append({
                "from": "DORMANT", "to": "SUSPENDED",
                "reason": f"Dormant for {months_dormant:.1f} months (max: {DORMANT_MAX_MONTHS})",
                "trust_at_suspension": decayed_trust
            })
        else:
            transitions.append({
                "status": "DORMANT",
                "months_dormant": round(months_dormant, 1),
                "trust_original": agent.trust_at_dormancy,
                "trust_current": decayed_trust,
                "months_until_suspended": round(DORMANT_MAX_MONTHS - months_dormant, 1)
            })
    
    elif agent.state == AgentState.REACTIVATING:
        days_in_reactivation = (now - agent.reactivation_started) / 86400
        if days_in_reactivation > REACTIVATION_WINDOW_DAYS:
            agent.state = AgentState.SUSPENDED
            transitions.append({
                "from": "REACTIVATING", "to": "SUSPENDED",
                "reason": f"Reactivation window expired ({days_in_reactivation:.0f}d > {REACTIVATION_WINDOW_DAYS}d)",
                "recovery_receipts": agent.recovery_receipts,
                "needed": N_RECOVERY
            })
        elif agent.recovery_receipts >= N_RECOVERY:
            # Reactivation complete — resume with decayed trust + Wilson boost
            wilson_floor = wilson_ci_lower(agent.recovery_receipts, agent.recovery_receipts)
            resumed_trust = max(agent.trust_score, wilson_floor * agent.trust_at_dormancy)
            agent.state = AgentState.ACTIVE
            agent.trust_score = resumed_trust
            transitions.append({
                "from": "REACTIVATING", "to": "ACTIVE",
                "reason": f"n_recovery={agent.recovery_receipts} complete",
                "trust_resumed": resumed_trust,
                "wilson_floor": wilson_floor
            })
    
    return {"agent_id": agent.agent_id, "transitions": transitions}


def begin_reactivation(agent: AgentTrustState, now: float) -> dict:
    """Start reactivation from DORMANT state."""
    if agent.state != AgentState.DORMANT:
        return {"error": f"Cannot reactivate from {agent.state.value}"}
    
    agent.state = AgentState.REACTIVATING
    agent.reactivation_started = now
    agent.recovery_receipts = 0
    
    return {
        "agent_id": agent.agent_id,
        "state": "REACTIVATING",
        "n_recovery_needed": N_RECOVERY,
        "window_days": REACTIVATION_WINDOW_DAYS,
        "trust_at_dormancy": agent.trust_at_dormancy,
        "trust_current": agent.trust_score,
        "note": f"n_recovery={N_RECOVERY} < n_initial={N_INITIAL} (identity history preserved)"
    }


def add_recovery_receipt(agent: AgentTrustState) -> dict:
    """Add a receipt during reactivation."""
    if agent.state != AgentState.REACTIVATING:
        return {"error": f"Not in REACTIVATING state"}
    
    agent.recovery_receipts += 1
    progress = agent.recovery_receipts / N_RECOVERY
    
    return {
        "recovery_receipts": agent.recovery_receipts,
        "needed": N_RECOVERY,
        "progress": round(progress, 2),
        "complete": agent.recovery_receipts >= N_RECOVERY
    }


# === Scenarios ===

def scenario_natural_dormancy():
    """Agent goes idle, trust decays, reactivates."""
    print("=== Scenario: Natural Dormancy + Reactivation ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="kit_fox",
        trust_score=0.89,
        last_receipt_at=now - 86400 * 45,  # 45 days ago
        total_receipts=150
    )
    
    # Check transition
    result = check_state_transition(agent, now)
    print(f"  Transition: {result['transitions'][0].get('from', '')} → {result['transitions'][0].get('to', agent.state.value)}")
    print(f"  Trust preserved: {agent.trust_at_dormancy}")
    
    # 3 months dormant
    future = now + 86400 * 90
    result2 = check_state_transition(agent, future)
    t = result2['transitions'][0]
    print(f"  After 3 months: trust {t.get('trust_original', '')} → {t.get('trust_current', '')}")
    print(f"  Months until SUSPENDED: {t.get('months_until_suspended', '')}")
    
    # Reactivate
    react = begin_reactivation(agent, future)
    print(f"  Reactivation: n_recovery={react['n_recovery_needed']} (vs n_initial={N_INITIAL})")
    
    # Complete recovery
    for i in range(N_RECOVERY):
        add_recovery_receipt(agent)
    
    result3 = check_state_transition(agent, future)
    t3 = result3['transitions'][0]
    print(f"  After {N_RECOVERY} receipts: {t3.get('from', '')} → {t3.get('to', '')}")
    print(f"  Trust resumed: {t3.get('trust_resumed', '')}")
    print()


def scenario_long_dormancy_suspended():
    """Agent dormant > 12 months → SUSPENDED."""
    print("=== Scenario: Long Dormancy → SUSPENDED ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="ghost_agent",
        trust_score=0.75,
        last_receipt_at=now - 86400 * 400,  # 400 days ago
        total_receipts=50
    )
    
    check_state_transition(agent, now)  # → DORMANT
    
    future = now + 86400 * 365
    result = check_state_transition(agent, future)
    t = result['transitions'][0]
    print(f"  Trust decay: {agent.trust_at_dormancy} → {t.get('trust_at_suspension', agent.trust_score)}")
    print(f"  State: {t.get('from', '')} → {t.get('to', agent.state.value)}")
    print(f"  certificateHold → SUSPENDED (requires full re-bootstrap)")
    print()


def scenario_reactivation_timeout():
    """Agent starts reactivation but doesn't complete in time."""
    print("=== Scenario: Reactivation Timeout ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="slow_agent",
        state=AgentState.DORMANT,
        trust_score=0.65,
        trust_at_dormancy=0.72,
        dormant_since=now - 86400 * 60,
        total_receipts=40
    )
    
    react = begin_reactivation(agent, now)
    print(f"  Reactivation started: need {react['n_recovery_needed']} receipts in {react['window_days']}d")
    
    # Only complete 5 receipts
    for i in range(5):
        add_recovery_receipt(agent)
    
    expired = now + 86400 * (REACTIVATION_WINDOW_DAYS + 1)
    result = check_state_transition(agent, expired)
    t = result['transitions'][0]
    print(f"  Got {t.get('recovery_receipts', 5)}/{t.get('needed', N_RECOVERY)} receipts")
    print(f"  {t.get('from', '')} → {t.get('to', '')}: {t.get('reason', '')}")
    print()


def scenario_decay_curve():
    """Show trust decay over time."""
    print("=== Scenario: Trust Decay Curve ===")
    trust_0 = 0.90
    print(f"  Initial trust: {trust_0}")
    for months in [1, 3, 6, 9, 12]:
        decayed = compute_dormant_decay(trust_0, months)
        print(f"  Month {months:2d}: {decayed:.4f} ({(1 - decayed/trust_0)*100:.1f}% lost)")
    print(f"  Key: trust never hits 0. certificateHold preserves identity.")
    print(f"  Month 12: {compute_dormant_decay(trust_0, 12):.4f} → SUSPENDED transition")
    print()


def scenario_discovery_mode():
    """V1.2 DISCOVERY_MODE in receipt."""
    print("=== Scenario: Discovery Mode in Receipt ===")
    modes = [
        (DiscoveryMode.DANE, "DNSSEC-signed TLSA record", 1.0),
        (DiscoveryMode.SVCB, "Service binding with alpn", 0.8),
        (DiscoveryMode.CT_FALLBACK, "CT log lookup", 0.5),
        (DiscoveryMode.NONE, "Direct connection, no discovery", 0.2),
    ]
    for mode, desc, quality in modes:
        print(f"  {mode.value:15s} quality={quality:.1f}  {desc}")
    print(f"  Receipt includes discovery_mode → verifier knows path quality")
    print(f"  Degraded discovery = knowable, not silent")
    print()


if __name__ == "__main__":
    print("DORMANT State Handler — ATF V1.2")
    print("Per santaclawd + RFC 5280 §5.3.1 certificateHold")
    print("=" * 60)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  DORMANT_THRESHOLD:  {DORMANT_THRESHOLD_DAYS}d no receipts")
    print(f"  DECAY_RATE:         {DORMANT_DECAY_RATE*100}%/month")
    print(f"  MAX_DORMANT:        {DORMANT_MAX_MONTHS} months → SUSPENDED")
    print(f"  N_RECOVERY:         {N_RECOVERY} (vs N_INITIAL={N_INITIAL})")
    print(f"  REACTIVATION_WINDOW: {REACTIVATION_WINDOW_DAYS}d")
    print()
    
    scenario_natural_dormancy()
    scenario_long_dormancy_suspended()
    scenario_reactivation_timeout()
    scenario_decay_curve()
    scenario_discovery_mode()
    
    print("=" * 60)
    print("KEY INSIGHT: Idle ≠ bad actor. DORMANT preserves identity.")
    print("certificateHold = reversible. REVOKED = permanent.")
    print("n_recovery < n_initial because history is context.")
    print("DISCOVERY_MODE in receipt = path quality is knowable.")
