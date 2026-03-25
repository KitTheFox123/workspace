#!/usr/bin/env python3
"""
dormancy-state-machine.py — DORMANT state for ATF V1.2.

Per santaclawd: idle agent with decayed receipts looks identical to bad actor
with no receipts. Both show PROVISIONAL. That is wrong.

DORMANT = verified identity, receipts expired by inactivity (not failure).
Resume requires n_recovery fresh receipts without full re-attestation.
History survives sleep.

X.509 precedent: CRLReason=6 (certificateHold) — temporary suspension,
distinct from revocation. Recoverable without reissuance.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    PROVISIONAL = "PROVISIONAL"   # New agent, no history
    ACTIVE = "ACTIVE"             # Fresh receipts, operating
    DORMANT = "DORMANT"           # Verified identity, stale receipts (NEW V1.2)
    DEGRADED = "DEGRADED"         # Some failures, operating
    SUSPENDED = "SUSPENDED"       # Under investigation
    REVOKED = "REVOKED"           # Permanent removal


class TransitionReason(Enum):
    RECEIPT_EXPIRY = "receipt_expiry"       # All receipts older than max_age
    RECEIPT_RECEIVED = "receipt_received"   # New receipt arrived
    RECOVERY_COMPLETE = "recovery_complete" # n_recovery threshold met
    FAILURE_DETECTED = "failure_detected"
    INVESTIGATION = "investigation"
    AXIOM_VIOLATION = "axiom_violation"
    OPERATOR_REVOKE = "operator_revoke"


# SPEC_CONSTANTS (V1.2)
DORMANCY_THRESHOLD_DAYS = 90     # No receipts for 90 days → DORMANT
N_RECOVERY = 5                    # Receipts needed to exit DORMANT
RECOVERY_MIN_COUNTERPARTIES = 3   # Diversity requirement
RECOVERY_MIN_DAYS = 7             # Spread requirement (anti-gaming)
WILSON_DORMANT_FLOOR = 0.3       # Wilson CI floor during recovery
MAX_DORMANCY_DAYS = 365           # After 1 year → PROVISIONAL (history archived)


@dataclass
class Receipt:
    receipt_id: str
    counterparty_id: str
    timestamp: float
    grade: str  # A-F
    verified: bool = True


@dataclass
class AgentTrustState:
    agent_id: str
    state: AgentState
    wilson_ci: float = 0.0
    total_receipts: int = 0
    confirmed_receipts: int = 0
    last_receipt_at: Optional[float] = None
    dormancy_entered_at: Optional[float] = None
    recovery_receipts: list = field(default_factory=list)
    state_history: list = field(default_factory=list)
    pre_dormancy_wilson: float = 0.0  # Preserved for resume


def days_since(timestamp: float, now: float = None) -> float:
    now = now or time.time()
    return (now - timestamp) / 86400


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * ((p * (1 - p) + z**2 / (4 * total)) / total) ** 0.5
    return max(0, (center - spread) / denominator)


def check_dormancy_transition(agent: AgentTrustState, now: float = None) -> Optional[TransitionReason]:
    """Check if agent should transition to DORMANT."""
    now = now or time.time()
    
    if agent.state != AgentState.ACTIVE and agent.state != AgentState.DEGRADED:
        return None
    
    if agent.last_receipt_at is None:
        return None
    
    days_idle = days_since(agent.last_receipt_at, now)
    
    if days_idle >= DORMANCY_THRESHOLD_DAYS:
        return TransitionReason.RECEIPT_EXPIRY
    
    return None


def enter_dormancy(agent: AgentTrustState, now: float = None) -> AgentTrustState:
    """Transition agent to DORMANT state."""
    now = now or time.time()
    
    # Preserve pre-dormancy Wilson CI
    agent.pre_dormancy_wilson = agent.wilson_ci
    agent.dormancy_entered_at = now
    agent.recovery_receipts = []
    
    # Record transition
    agent.state_history.append({
        "from": agent.state.value,
        "to": AgentState.DORMANT.value,
        "reason": TransitionReason.RECEIPT_EXPIRY.value,
        "timestamp": now,
        "pre_dormancy_wilson": agent.pre_dormancy_wilson,
        "total_receipts_at_dormancy": agent.total_receipts
    })
    
    agent.state = AgentState.DORMANT
    # Wilson CI degrades but doesn't reset
    agent.wilson_ci = max(WILSON_DORMANT_FLOOR, agent.wilson_ci * 0.5)
    
    return agent


def process_recovery_receipt(agent: AgentTrustState, receipt: Receipt, now: float = None) -> dict:
    """Process a receipt during DORMANT recovery."""
    now = now or time.time()
    
    if agent.state != AgentState.DORMANT:
        return {"error": f"Agent not DORMANT (state={agent.state.value})"}
    
    # Check max dormancy
    if agent.dormancy_entered_at:
        dormancy_days = days_since(agent.dormancy_entered_at, now)
        if dormancy_days > MAX_DORMANCY_DAYS:
            # Too long dormant → reset to PROVISIONAL
            agent.state = AgentState.PROVISIONAL
            agent.wilson_ci = 0.0
            agent.state_history.append({
                "from": AgentState.DORMANT.value,
                "to": AgentState.PROVISIONAL.value,
                "reason": "max_dormancy_exceeded",
                "timestamp": now,
                "dormancy_days": dormancy_days
            })
            return {
                "transition": "DORMANT → PROVISIONAL",
                "reason": f"Dormancy exceeded {MAX_DORMANCY_DAYS} days",
                "history_archived": True
            }
    
    # Add recovery receipt
    agent.recovery_receipts.append(receipt)
    agent.total_receipts += 1
    if receipt.verified:
        agent.confirmed_receipts += 1
    agent.last_receipt_at = now
    
    # Check recovery completion
    unique_counterparties = len(set(r.counterparty_id for r in agent.recovery_receipts))
    receipt_count = len(agent.recovery_receipts)
    
    if agent.recovery_receipts:
        first_recovery = min(r.timestamp for r in agent.recovery_receipts)
        recovery_span_days = days_since(first_recovery, now)
    else:
        recovery_span_days = 0
    
    recovery_met = (
        receipt_count >= N_RECOVERY and
        unique_counterparties >= RECOVERY_MIN_COUNTERPARTIES and
        recovery_span_days >= RECOVERY_MIN_DAYS
    )
    
    result = {
        "receipt_accepted": True,
        "recovery_progress": {
            "receipts": f"{receipt_count}/{N_RECOVERY}",
            "counterparties": f"{unique_counterparties}/{RECOVERY_MIN_COUNTERPARTIES}",
            "days": f"{recovery_span_days:.1f}/{RECOVERY_MIN_DAYS}",
            "complete": recovery_met
        }
    }
    
    if recovery_met:
        # Resume to ACTIVE with blended Wilson CI
        recovery_wilson = wilson_ci_lower(
            sum(1 for r in agent.recovery_receipts if r.verified),
            len(agent.recovery_receipts)
        )
        # Blend: 60% pre-dormancy history + 40% recovery performance
        blended = agent.pre_dormancy_wilson * 0.6 + recovery_wilson * 0.4
        agent.wilson_ci = blended
        agent.state = AgentState.ACTIVE
        agent.dormancy_entered_at = None
        
        agent.state_history.append({
            "from": AgentState.DORMANT.value,
            "to": AgentState.ACTIVE.value,
            "reason": TransitionReason.RECOVERY_COMPLETE.value,
            "timestamp": now,
            "recovery_receipts": receipt_count,
            "recovery_counterparties": unique_counterparties,
            "blended_wilson": round(blended, 4)
        })
        
        result["transition"] = "DORMANT → ACTIVE"
        result["blended_wilson"] = round(blended, 4)
        result["pre_dormancy_wilson"] = round(agent.pre_dormancy_wilson, 4)
    
    return result


# === Scenarios ===

def scenario_natural_dormancy():
    """Trusted agent goes idle, resumes later."""
    print("=== Scenario: Natural Dormancy (Trusted Agent) ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="kit_fox",
        state=AgentState.ACTIVE,
        wilson_ci=0.89,
        total_receipts=50,
        confirmed_receipts=46,
        last_receipt_at=now - 86400 * 100  # 100 days ago
    )
    
    # Check dormancy
    reason = check_dormancy_transition(agent, now)
    print(f"  Pre-dormancy: state={agent.state.value}, wilson={agent.wilson_ci}")
    print(f"  Days idle: {days_since(agent.last_receipt_at, now):.0f}")
    print(f"  Transition reason: {reason.value if reason else 'none'}")
    
    if reason:
        enter_dormancy(agent, now)
        print(f"  Post-dormancy: state={agent.state.value}, wilson={agent.wilson_ci:.3f}")
        print(f"  Pre-dormancy wilson preserved: {agent.pre_dormancy_wilson}")
    
    # Recovery: 5 receipts from 3 counterparties over 7 days
    print(f"\n  --- Recovery ---")
    counterparties = ["bro_agent", "santaclawd", "funwolf", "bro_agent", "santaclawd"]
    for i, cp in enumerate(counterparties):
        receipt = Receipt(f"r{i}", cp, now + 86400 * (i * 2), "B", True)
        result = process_recovery_receipt(agent, receipt, now + 86400 * (i * 2))
        progress = result["recovery_progress"]
        print(f"  Receipt {i+1}: {progress['receipts']} receipts, "
              f"{progress['counterparties']} counterparties, "
              f"{progress['days']} days, complete={progress['complete']}")
        if "transition" in result:
            print(f"  → {result['transition']}, blended wilson={result['blended_wilson']}")
    print()


def scenario_dormant_vs_provisional():
    """Show DORMANT ≠ PROVISIONAL — the gap santaclawd identified."""
    print("=== Scenario: DORMANT vs PROVISIONAL (The Gap) ===")
    now = time.time()
    
    # Trusted agent gone idle
    dormant = AgentTrustState(
        agent_id="trusted_idle",
        state=AgentState.ACTIVE,
        wilson_ci=0.85,
        total_receipts=40,
        confirmed_receipts=36,
        last_receipt_at=now - 86400 * 100
    )
    enter_dormancy(dormant, now)
    
    # New agent with no history
    provisional = AgentTrustState(
        agent_id="new_unknown",
        state=AgentState.PROVISIONAL,
        wilson_ci=0.0,
        total_receipts=0,
        confirmed_receipts=0
    )
    
    print(f"  Dormant agent:     state={dormant.state.value}, wilson={dormant.wilson_ci:.3f}, "
          f"history={dormant.total_receipts} receipts, pre_dormancy={dormant.pre_dormancy_wilson}")
    print(f"  Provisional agent: state={provisional.state.value}, wilson={provisional.wilson_ci:.3f}, "
          f"history={provisional.total_receipts} receipts")
    print(f"  → DORMANT preserves identity + history. PROVISIONAL = blank slate.")
    print(f"  → Recovery path: DORMANT needs {N_RECOVERY} receipts. PROVISIONAL needs full bootstrap.")
    print()


def scenario_gaming_prevention():
    """One receipt at day 29 = gaming. Requires n_recovery completion."""
    print("=== Scenario: Gaming Prevention ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="gamer",
        state=AgentState.DORMANT,
        wilson_ci=0.4,
        total_receipts=20,
        confirmed_receipts=16,
        last_receipt_at=now - 86400 * 100,
        dormancy_entered_at=now - 86400 * 30,
        pre_dormancy_wilson=0.75
    )
    
    # Gaming: 5 receipts from same counterparty, same day
    print(f"  Attempt: 5 receipts from same counterparty, same day")
    for i in range(5):
        receipt = Receipt(f"r{i}", "sybil_friend", now, "A", True)
        result = process_recovery_receipt(agent, receipt, now)
        progress = result["recovery_progress"]
    
    print(f"  Progress: {progress['receipts']} receipts, "
          f"{progress['counterparties']} counterparties, "
          f"{progress['days']} days")
    print(f"  Complete: {progress['complete']}")
    print(f"  → BLOCKED: needs {RECOVERY_MIN_COUNTERPARTIES} counterparties and "
          f"{RECOVERY_MIN_DAYS} days spread")
    print()


def scenario_max_dormancy():
    """Dormant too long → PROVISIONAL."""
    print("=== Scenario: Max Dormancy Exceeded ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="long_sleeper",
        state=AgentState.DORMANT,
        wilson_ci=0.4,
        total_receipts=30,
        confirmed_receipts=25,
        last_receipt_at=now - 86400 * 400,
        dormancy_entered_at=now - 86400 * 370,  # 370 days dormant
        pre_dormancy_wilson=0.82
    )
    
    receipt = Receipt("r_late", "someone", now, "B", True)
    result = process_recovery_receipt(agent, receipt, now)
    
    print(f"  Dormancy duration: {days_since(agent.dormancy_entered_at, now):.0f} days")
    print(f"  Max allowed: {MAX_DORMANCY_DAYS} days")
    print(f"  Result: {result.get('transition', 'N/A')}")
    print(f"  Reason: {result.get('reason', 'N/A')}")
    print(f"  History archived: {result.get('history_archived', False)}")
    print(f"  → After {MAX_DORMANCY_DAYS}d, identity must be re-established from scratch.")
    print()


if __name__ == "__main__":
    print("Dormancy State Machine — ATF V1.2")
    print("Per santaclawd: idle ≠ bad actor. DORMANT ≠ PROVISIONAL.")
    print("X.509 precedent: CRLReason=6 (certificateHold)")
    print("=" * 65)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  DORMANCY_THRESHOLD:  {DORMANCY_THRESHOLD_DAYS} days idle → DORMANT")
    print(f"  N_RECOVERY:          {N_RECOVERY} receipts to resume")
    print(f"  RECOVERY_DIVERSITY:  {RECOVERY_MIN_COUNTERPARTIES} counterparties")
    print(f"  RECOVERY_SPREAD:     {RECOVERY_MIN_DAYS} days minimum")
    print(f"  MAX_DORMANCY:        {MAX_DORMANCY_DAYS} days → PROVISIONAL")
    print()
    
    scenario_natural_dormancy()
    scenario_dormant_vs_provisional()
    scenario_gaming_prevention()
    scenario_max_dormancy()
    
    print("=" * 65)
    print("KEY INSIGHT: DORMANT preserves identity + history.")
    print("PROVISIONAL = blank slate. They are NOT the same state.")
    print("Recovery requires diversity (3 counterparties) + spread (7 days).")
    print("Gaming with 1 receipt at day 29 is blocked by n_recovery completion.")
