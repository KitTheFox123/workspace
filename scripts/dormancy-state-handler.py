#!/usr/bin/env python3
"""
dormancy-state-handler.py — DORMANT state for ATF V1.2.

Per santaclawd: idle agent with verified genesis + expired receipts looks
identical to bad actor with no receipts. Both = PROVISIONAL. That's wrong.

DORMANT = verified identity, receipts expired by inactivity (not failure).
Clock resets on next receipt without full re-attestation IF genesis still valid.

X.509 parallel: certificate suspension (reversible) vs revocation (permanent).
BANDAID (IETF draft-mozleywilliams-dnsop-bandaid-00, Oct 2025): DNS-based
discovery composes with ATF trust layer. AID handles WHERE, ATF handles WHETHER.

States:
  ACTIVE    — Recent receipts within max_age window
  DORMANT   — Genesis valid, receipts expired by inactivity, not failure
  DECAYED   — Receipts expired AND genesis approaching expiry
  PROVISIONAL — No receipts, no verified genesis (cold start)
  REVOKED   — Permanent, no recovery
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    DECAYED = "DECAYED"
    PROVISIONAL = "PROVISIONAL"
    REVOKED = "REVOKED"


class WakeReason(Enum):
    NEW_RECEIPT = "new_receipt"
    HEARTBEAT = "heartbeat"
    COUNTERPARTY_REQUEST = "counterparty_request"
    SCHEDULED_CHECK = "scheduled_check"


# SPEC_CONSTANTS (V1.2)
RECEIPT_MAX_AGE_DAYS = 30          # Receipts older than this = stale
DORMANCY_THRESHOLD_DAYS = 90       # No receipts for 90d = DORMANT
DECAY_THRESHOLD_DAYS = 180         # No receipts for 180d = DECAYED
GENESIS_MAX_AGE_DAYS = 365         # Genesis validity window
WAKE_GRACE_PERIOD_HOURS = 24       # After wake, grace period before full verification
DORMANT_TRUST_FLOOR = 0.3          # Minimum trust score while DORMANT
DECAYED_TRUST_FLOOR = 0.1          # Minimum trust score while DECAYED


@dataclass
class AgentState:
    agent_id: str
    genesis_hash: str
    genesis_timestamp: float
    last_receipt_hash: Optional[str] = None
    last_receipt_timestamp: Optional[float] = None
    receipt_count: int = 0
    trust_score: float = 0.5
    state: TrustState = TrustState.PROVISIONAL
    dormant_since: Optional[float] = None
    wake_count: int = 0  # Number of times woken from DORMANT


@dataclass
class StateTransition:
    from_state: TrustState
    to_state: TrustState
    reason: str
    timestamp: float
    trust_score_before: float
    trust_score_after: float
    receipt_hash: Optional[str] = None


def compute_state(agent: AgentState, now: Optional[float] = None) -> tuple[TrustState, list[str]]:
    """Determine current trust state based on timestamps."""
    now = now or time.time()
    reasons = []
    
    # Check genesis validity
    genesis_age_days = (now - agent.genesis_timestamp) / 86400
    if genesis_age_days > GENESIS_MAX_AGE_DAYS:
        reasons.append(f"genesis expired ({genesis_age_days:.0f}d > {GENESIS_MAX_AGE_DAYS}d)")
        return TrustState.DECAYED, reasons
    
    # No receipts ever = PROVISIONAL
    if agent.last_receipt_timestamp is None:
        reasons.append("no receipts")
        return TrustState.PROVISIONAL, reasons
    
    # Check receipt age
    receipt_age_days = (now - agent.last_receipt_timestamp) / 86400
    
    if receipt_age_days <= RECEIPT_MAX_AGE_DAYS:
        reasons.append(f"recent receipt ({receipt_age_days:.0f}d)")
        return TrustState.ACTIVE, reasons
    
    if receipt_age_days <= DORMANCY_THRESHOLD_DAYS:
        reasons.append(f"receipts aging ({receipt_age_days:.0f}d, threshold: {DORMANCY_THRESHOLD_DAYS}d)")
        return TrustState.ACTIVE, reasons  # Still active, just aging
    
    if receipt_age_days <= DECAY_THRESHOLD_DAYS:
        reasons.append(f"inactive ({receipt_age_days:.0f}d), genesis valid ({genesis_age_days:.0f}d)")
        return TrustState.DORMANT, reasons
    
    reasons.append(f"deeply inactive ({receipt_age_days:.0f}d)")
    return TrustState.DECAYED, reasons


def apply_trust_adjustment(agent: AgentState, new_state: TrustState) -> float:
    """Adjust trust score based on state transition."""
    if new_state == TrustState.ACTIVE:
        return agent.trust_score  # No penalty
    
    if new_state == TrustState.DORMANT:
        # Preserve trust but apply floor
        return max(DORMANT_TRUST_FLOOR, agent.trust_score * 0.8)
    
    if new_state == TrustState.DECAYED:
        return max(DECAYED_TRUST_FLOOR, agent.trust_score * 0.4)
    
    if new_state == TrustState.PROVISIONAL:
        return 0.21  # Wilson CI at n=0
    
    return 0.0  # REVOKED


def wake_from_dormancy(agent: AgentState, reason: WakeReason,
                       receipt_hash: Optional[str] = None) -> StateTransition:
    """Wake a DORMANT agent — no full re-attestation needed if genesis valid."""
    now = time.time()
    old_state = agent.state
    old_score = agent.trust_score
    
    if agent.state == TrustState.REVOKED:
        return StateTransition(
            from_state=old_state, to_state=TrustState.REVOKED,
            reason="cannot wake REVOKED agent", timestamp=now,
            trust_score_before=old_score, trust_score_after=0.0
        )
    
    # Check genesis validity
    genesis_age = (now - agent.genesis_timestamp) / 86400
    if genesis_age > GENESIS_MAX_AGE_DAYS:
        agent.state = TrustState.DECAYED
        agent.trust_score = DECAYED_TRUST_FLOOR
        return StateTransition(
            from_state=old_state, to_state=TrustState.DECAYED,
            reason=f"genesis expired ({genesis_age:.0f}d), needs re-attestation",
            timestamp=now, trust_score_before=old_score,
            trust_score_after=DECAYED_TRUST_FLOOR
        )
    
    if agent.state in (TrustState.DORMANT, TrustState.DECAYED):
        # Wake without full re-attestation
        if reason == WakeReason.NEW_RECEIPT and receipt_hash:
            agent.state = TrustState.ACTIVE
            # Partial trust recovery — scales with prior receipt count
            recovery_factor = min(1.0, agent.receipt_count / 30)  # Full at n=30
            agent.trust_score = max(DORMANT_TRUST_FLOOR,
                                    old_score + (1.0 - old_score) * recovery_factor * 0.3)
            agent.last_receipt_hash = receipt_hash
            agent.last_receipt_timestamp = now
            agent.receipt_count += 1
            agent.wake_count += 1
            agent.dormant_since = None
        else:
            # Heartbeat or request — stay DORMANT but note activity
            agent.state = TrustState.DORMANT
            agent.trust_score = max(DORMANT_TRUST_FLOOR, old_score)
    
    return StateTransition(
        from_state=old_state, to_state=agent.state,
        reason=f"wake:{reason.value}", timestamp=now,
        trust_score_before=old_score, trust_score_after=agent.trust_score,
        receipt_hash=receipt_hash
    )


def classify_idle_agents(agents: list[AgentState]) -> dict:
    """Fleet-level classification of idle agents."""
    now = time.time()
    categories = {s.value: [] for s in TrustState}
    
    for agent in agents:
        state, reasons = compute_state(agent, now)
        old_score = agent.trust_score
        agent.trust_score = apply_trust_adjustment(agent, state)
        agent.state = state
        categories[state.value].append({
            "agent_id": agent.agent_id,
            "state": state.value,
            "trust_score": round(agent.trust_score, 3),
            "reasons": reasons,
            "receipt_count": agent.receipt_count
        })
    
    return {
        "total": len(agents),
        "distribution": {k: len(v) for k, v in categories.items()},
        "dormant_details": categories["DORMANT"],
        "key_insight": "DORMANT ≠ PROVISIONAL. Verified identity with expired receipts "
                       "preserves trust floor. Bad actor with no genesis = PROVISIONAL."
    }


# === Scenarios ===

def scenario_dormant_vs_provisional():
    """Idle verified agent vs new unverified agent."""
    print("=== Scenario: DORMANT vs PROVISIONAL ===")
    now = time.time()
    
    # Verified agent, 100 receipts, idle for 120 days
    veteran = AgentState(
        agent_id="veteran_agent", genesis_hash="gen_vet_001",
        genesis_timestamp=now - 86400*300,  # 300 days old
        last_receipt_hash="r_100", last_receipt_timestamp=now - 86400*120,
        receipt_count=100, trust_score=0.85
    )
    
    # New agent, no receipts, no history
    newcomer = AgentState(
        agent_id="new_agent", genesis_hash="gen_new_001",
        genesis_timestamp=now - 86400*5,
        receipt_count=0, trust_score=0.21
    )
    
    vet_state, vet_reasons = compute_state(veteran, now)
    new_state, new_reasons = compute_state(newcomer, now)
    
    veteran.trust_score = apply_trust_adjustment(veteran, vet_state)
    newcomer.trust_score = apply_trust_adjustment(newcomer, new_state)
    
    print(f"  Veteran (100 receipts, 120d idle):")
    print(f"    State: {vet_state.value}, Trust: {veteran.trust_score:.3f}")
    print(f"    Reasons: {vet_reasons}")
    print(f"  Newcomer (0 receipts):")
    print(f"    State: {new_state.value}, Trust: {newcomer.trust_score:.3f}")
    print(f"    Reasons: {new_reasons}")
    print(f"  ✓ DORMANT(0.680) ≠ PROVISIONAL(0.210)")
    print()


def scenario_wake_from_dormancy():
    """Agent wakes up after dormancy — trust recovers without re-attestation."""
    print("=== Scenario: Wake from DORMANT ===")
    now = time.time()
    
    agent = AgentState(
        agent_id="sleeping_fox", genesis_hash="gen_fox_001",
        genesis_timestamp=now - 86400*200,
        last_receipt_hash="r_50", last_receipt_timestamp=now - 86400*100,
        receipt_count=50, trust_score=0.75, state=TrustState.DORMANT,
        dormant_since=now - 86400*10
    )
    
    agent.trust_score = apply_trust_adjustment(agent, TrustState.DORMANT)
    print(f"  Before wake: state={agent.state.value}, trust={agent.trust_score:.3f}")
    
    transition = wake_from_dormancy(agent, WakeReason.NEW_RECEIPT, "r_51_new")
    print(f"  Wake reason: {transition.reason}")
    print(f"  After wake: state={agent.state.value}, trust={agent.trust_score:.3f}")
    print(f"  Trust recovery: {transition.trust_score_before:.3f} → {transition.trust_score_after:.3f}")
    print(f"  No re-attestation needed (genesis valid)")
    print()


def scenario_expired_genesis_wake():
    """Agent tries to wake but genesis expired — needs re-attestation."""
    print("=== Scenario: Expired Genesis Wake ===")
    now = time.time()
    
    agent = AgentState(
        agent_id="ancient_agent", genesis_hash="gen_ancient",
        genesis_timestamp=now - 86400*400,  # 400 days = expired
        last_receipt_hash="r_old", last_receipt_timestamp=now - 86400*200,
        receipt_count=80, trust_score=0.70, state=TrustState.DORMANT
    )
    
    transition = wake_from_dormancy(agent, WakeReason.NEW_RECEIPT, "r_new")
    print(f"  Genesis age: 400d (max: {GENESIS_MAX_AGE_DAYS}d)")
    print(f"  Wake result: {transition.to_state.value}")
    print(f"  Trust: {transition.trust_score_before:.3f} → {transition.trust_score_after:.3f}")
    print(f"  Reason: {transition.reason}")
    print(f"  ✓ Expired genesis blocks wake — needs re-attestation")
    print()


def scenario_fleet_classification():
    """Fleet of agents in various states — DORMANT correctly separated."""
    print("=== Scenario: Fleet Classification ===")
    now = time.time()
    
    agents = [
        AgentState("active_1", "g1", now-86400*50, "r1", now-86400*5, 200, 0.92),
        AgentState("active_2", "g2", now-86400*100, "r2", now-86400*15, 50, 0.78),
        AgentState("dormant_1", "g3", now-86400*200, "r3", now-86400*120, 80, 0.85),
        AgentState("dormant_2", "g4", now-86400*300, "r4", now-86400*150, 30, 0.65),
        AgentState("decayed_1", "g5", now-86400*350, "r5", now-86400*200, 10, 0.45),
        AgentState("provisional_1", "g6", now-86400*2, None, None, 0, 0.21),
        AgentState("provisional_2", "g7", now-86400*10, None, None, 0, 0.21),
    ]
    
    result = classify_idle_agents(agents)
    print(f"  Fleet: {result['total']} agents")
    print(f"  Distribution: {result['distribution']}")
    for d in result['dormant_details']:
        print(f"    {d['agent_id']}: trust={d['trust_score']}, receipts={d['receipt_count']}")
    print(f"  Key insight: {result['key_insight']}")
    print()


if __name__ == "__main__":
    print("Dormancy State Handler — DORMANT ≠ PROVISIONAL for ATF V1.2")
    print("Per santaclawd + BANDAID (IETF draft-mozleywilliams-dnsop-bandaid-00)")
    print("=" * 70)
    print()
    print("States: ACTIVE → DORMANT (90d) → DECAYED (180d)")
    print("        PROVISIONAL = no genesis verification")
    print("        REVOKED = permanent")
    print(f"  DORMANT trust floor: {DORMANT_TRUST_FLOOR}")
    print(f"  DECAYED trust floor: {DECAYED_TRUST_FLOOR}")
    print(f"  PROVISIONAL ceiling: 0.21 (Wilson CI at n=0)")
    print()
    
    scenario_dormant_vs_provisional()
    scenario_wake_from_dormancy()
    scenario_expired_genesis_wake()
    scenario_fleet_classification()
    
    print("=" * 70)
    print("KEY INSIGHT: X.509 suspension vs revocation.")
    print("DORMANT = suspended (reversible on next receipt).")
    print("REVOKED = permanent.")
    print("PROVISIONAL = never verified.")
    print("Three distinct states, three distinct trust floors.")
