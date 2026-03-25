#!/usr/bin/env python3
"""
dormant-state-handler.py — DORMANT state management for ATF V1.2.

Per santaclawd: idle != bad actor. ATF V1.2 gap #1.
X.509 certificateHold (CRL reason code 6) = exact model.

States:
  ACTIVE    → producing receipts within expected cadence
  DORMANT   → no receipts for dormancy_threshold (default 30d)
  RECOVERY  → resumed activity, earning n_recovery receipts
  GRADUATED → n_recovery completed, trust restored (minus decay)

Trust decay: 5%/month during DORMANT (compounding).
Max DORMANT: 180 days before forced re-attestation.
n_recovery: 8 receipts (lighter than initial n=30, identity preserved).
Resumption: resume at decayed level, earn back via n_recovery.
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    RECOVERY = "RECOVERY"
    GRADUATED = "GRADUATED"
    FORCED_REATTESTATON = "FORCED_REATTESTATION"


# SPEC_CONSTANTS (V1.2)
DORMANCY_THRESHOLD_DAYS = 30      # Days without receipt → DORMANT
DECAY_RATE_PER_MONTH = 0.05       # 5% trust decay per month
MAX_DORMANT_DAYS = 180            # Forced re-attestation after 6 months
N_RECOVERY = 8                     # Receipts needed to graduate from RECOVERY
N_INITIAL = 30                     # Receipts for initial trust (new identity)
WILSON_Z = 1.96                    # 95% confidence
MIN_RECOVERY_COUNTERPARTIES = 2    # Must interact with 2+ distinct counterparties


@dataclass
class AgentTrustState:
    agent_id: str
    state: AgentState = AgentState.ACTIVE
    trust_score: float = 0.0
    trust_at_dormancy: float = 0.0     # Trust when entering DORMANT
    last_receipt_timestamp: float = 0.0
    dormant_since: Optional[float] = None
    recovery_started: Optional[float] = None
    recovery_receipts: int = 0
    recovery_counterparties: set = field(default_factory=set)
    total_receipts: int = 0
    
    @property
    def days_dormant(self) -> float:
        if self.dormant_since is None:
            return 0
        return (time.time() - self.dormant_since) / 86400
    
    @property
    def months_dormant(self) -> float:
        return self.days_dormant / 30.0


def compute_decayed_trust(trust_at_dormancy: float, months_dormant: float) -> float:
    """Compound decay: trust * (1 - rate)^months."""
    decayed = trust_at_dormancy * ((1 - DECAY_RATE_PER_MONTH) ** months_dormant)
    return round(max(0, decayed), 4)


def wilson_ci_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return round(max(0, (centre - spread) / denominator), 4)


def check_dormancy(agent: AgentTrustState, now: float = None) -> dict:
    """Check if agent should transition to DORMANT."""
    now = now or time.time()
    days_since_receipt = (now - agent.last_receipt_timestamp) / 86400
    
    if agent.state == AgentState.ACTIVE and days_since_receipt >= DORMANCY_THRESHOLD_DAYS:
        return {
            "transition": True,
            "from": AgentState.ACTIVE.value,
            "to": AgentState.DORMANT.value,
            "days_idle": round(days_since_receipt, 1),
            "reason": f"No receipts for {days_since_receipt:.0f} days (threshold: {DORMANCY_THRESHOLD_DAYS}d)",
            "model": "X.509 certificateHold (CRL reason code 6)"
        }
    return {"transition": False, "days_idle": round(days_since_receipt, 1)}


def enter_dormant(agent: AgentTrustState, now: float = None) -> AgentTrustState:
    """Transition agent to DORMANT state."""
    now = now or time.time()
    agent.state = AgentState.DORMANT
    agent.trust_at_dormancy = agent.trust_score
    agent.dormant_since = now
    return agent


def check_forced_reattestation(agent: AgentTrustState) -> dict:
    """Check if DORMANT agent exceeds max duration."""
    if agent.state != AgentState.DORMANT:
        return {"forced": False}
    
    if agent.days_dormant >= MAX_DORMANT_DAYS:
        return {
            "forced": True,
            "days_dormant": round(agent.days_dormant, 1),
            "max_days": MAX_DORMANT_DAYS,
            "action": "FORCED_REATTESTATION — identity must re-prove from n=30",
            "decayed_trust": compute_decayed_trust(agent.trust_at_dormancy, agent.months_dormant),
            "reason": f"Dormant {agent.days_dormant:.0f}d exceeds {MAX_DORMANT_DAYS}d max"
        }
    
    return {
        "forced": False,
        "days_remaining": round(MAX_DORMANT_DAYS - agent.days_dormant, 1),
        "current_trust": compute_decayed_trust(agent.trust_at_dormancy, agent.months_dormant)
    }


def resume_activity(agent: AgentTrustState, counterparty_id: str, 
                    now: float = None) -> dict:
    """Agent resumes activity — enter RECOVERY state."""
    now = now or time.time()
    
    if agent.state == AgentState.DORMANT:
        decayed = compute_decayed_trust(agent.trust_at_dormancy, agent.months_dormant)
        agent.state = AgentState.RECOVERY
        agent.trust_score = decayed  # Resume at decayed level
        agent.recovery_started = now
        agent.recovery_receipts = 1
        agent.recovery_counterparties = {counterparty_id}
        agent.last_receipt_timestamp = now
        
        return {
            "transition": "DORMANT → RECOVERY",
            "trust_at_dormancy": agent.trust_at_dormancy,
            "months_dormant": round(agent.months_dormant, 1),
            "decayed_trust": decayed,
            "decay_amount": round(agent.trust_at_dormancy - decayed, 4),
            "receipts_needed": N_RECOVERY - 1,
            "counterparties_needed": max(0, MIN_RECOVERY_COUNTERPARTIES - 1)
        }
    
    elif agent.state == AgentState.RECOVERY:
        agent.recovery_receipts += 1
        agent.recovery_counterparties.add(counterparty_id)
        agent.last_receipt_timestamp = now
        
        graduated = (agent.recovery_receipts >= N_RECOVERY and 
                    len(agent.recovery_counterparties) >= MIN_RECOVERY_COUNTERPARTIES)
        
        if graduated:
            agent.state = AgentState.GRADUATED
            # Trust = Wilson CI on recovery receipts, starting from decayed baseline
            recovery_wilson = wilson_ci_lower(agent.recovery_receipts, agent.recovery_receipts)
            agent.trust_score = min(agent.trust_at_dormancy, 
                                   max(agent.trust_score, recovery_wilson))
            
            return {
                "transition": "RECOVERY → GRADUATED",
                "recovery_receipts": agent.recovery_receipts,
                "recovery_counterparties": len(agent.recovery_counterparties),
                "restored_trust": agent.trust_score,
                "ceiling": agent.trust_at_dormancy,
                "note": "Trust capped at pre-dormancy level until new evidence exceeds it"
            }
        
        return {
            "transition": None,
            "state": "RECOVERY",
            "receipts": f"{agent.recovery_receipts}/{N_RECOVERY}",
            "counterparties": f"{len(agent.recovery_counterparties)}/{MIN_RECOVERY_COUNTERPARTIES}",
            "remaining": N_RECOVERY - agent.recovery_receipts
        }
    
    return {"error": f"Cannot resume from state {agent.state.value}"}


# === Scenarios ===

def scenario_normal_dormancy():
    """Agent goes idle 45 days, resumes, recovers."""
    print("=== Scenario: Normal Dormancy + Recovery ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="seasonal_agent",
        state=AgentState.ACTIVE,
        trust_score=0.85,
        last_receipt_timestamp=now - 86400 * 45,  # 45 days ago
        total_receipts=50
    )
    
    # Check dormancy
    check = check_dormancy(agent, now)
    print(f"  Idle {check['days_idle']}d → transition: {check.get('to', 'none')}")
    
    # Enter dormant
    enter_dormant(agent, now - 86400 * 15)  # Became dormant 15 days ago
    decayed = compute_decayed_trust(agent.trust_at_dormancy, 0.5)  # 0.5 months
    print(f"  Trust at dormancy: {agent.trust_at_dormancy}")
    print(f"  After 0.5 months decay: {decayed}")
    
    # Resume
    result = resume_activity(agent, "counterparty_A", now)
    print(f"  Resume: {result['transition']}")
    print(f"  Decayed trust: {result['decayed_trust']}")
    
    # Complete recovery
    for i in range(7):
        cp = f"counterparty_{'B' if i < 3 else 'C'}"
        result = resume_activity(agent, cp, now + i * 3600)
    
    print(f"  Recovery: {result.get('transition', result.get('state'))}")
    if 'restored_trust' in result:
        print(f"  Restored trust: {result['restored_trust']} (ceiling: {result['ceiling']})")
    print()


def scenario_long_dormancy_forced():
    """Agent dormant 200 days — forced re-attestation."""
    print("=== Scenario: Forced Re-attestation (200 days) ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="abandoned_agent",
        state=AgentState.ACTIVE,
        trust_score=0.92,
        last_receipt_timestamp=now - 86400 * 200,
        total_receipts=100
    )
    
    enter_dormant(agent, now - 86400 * 200)
    agent.dormant_since = now - 86400 * 200  # Fix: dormant since 200 days ago
    
    check = check_forced_reattestation(agent)
    print(f"  Days dormant: {check.get('days_dormant', '?')}")
    print(f"  Forced: {check['forced']}")
    if check['forced']:
        decayed = check['decayed_trust']
        print(f"  Decayed trust: {decayed} (from {agent.trust_at_dormancy})")
        print(f"  Action: {check['action']}")
    print()


def scenario_decay_curve():
    """Show trust decay over time."""
    print("=== Scenario: Trust Decay Curve ===")
    initial = 0.90
    print(f"  Initial trust: {initial}")
    for months in [1, 3, 6, 9, 12, 18]:
        decayed = compute_decayed_trust(initial, months)
        pct_lost = round((1 - decayed/initial) * 100, 1)
        print(f"  {months:2d} months: {decayed:.4f} ({pct_lost}% lost)")
    print()


def scenario_recovery_diversity():
    """Recovery requires 2+ distinct counterparties."""
    print("=== Scenario: Recovery Counterparty Diversity ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="single_partner",
        state=AgentState.ACTIVE,
        trust_score=0.80,
        last_receipt_timestamp=now - 86400 * 40,
        total_receipts=30
    )
    
    enter_dormant(agent, now - 86400 * 10)
    resume_activity(agent, "only_friend", now)
    
    # 8 receipts but only 1 counterparty
    for i in range(7):
        result = resume_activity(agent, "only_friend", now + i * 3600)
    
    print(f"  8 receipts, 1 counterparty")
    print(f"  State: {agent.state.value} (NOT graduated)")
    print(f"  Counterparties: {len(agent.recovery_counterparties)}/{MIN_RECOVERY_COUNTERPARTIES}")
    print(f"  Reason: single-counterparty recovery = potential collusion")
    
    # Add second counterparty
    result = resume_activity(agent, "new_friend", now + 8 * 3600)
    print(f"  After 2nd counterparty: {result.get('transition', agent.state.value)}")
    print()


if __name__ == "__main__":
    print("Dormant State Handler — ATF V1.2 Gap #1")
    print("Per santaclawd: idle != bad actor. X.509 certificateHold model.")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  DORMANCY_THRESHOLD = {DORMANCY_THRESHOLD_DAYS}d")
    print(f"  DECAY_RATE = {DECAY_RATE_PER_MONTH*100}%/month (compounding)")
    print(f"  MAX_DORMANT = {MAX_DORMANT_DAYS}d (forced re-attestation)")
    print(f"  N_RECOVERY = {N_RECOVERY} receipts (vs N_INITIAL={N_INITIAL})")
    print(f"  MIN_RECOVERY_COUNTERPARTIES = {MIN_RECOVERY_COUNTERPARTIES}")
    print()
    
    scenario_normal_dormancy()
    scenario_long_dormancy_forced()
    scenario_decay_curve()
    scenario_recovery_diversity()
    
    print("=" * 70)
    print("KEY INSIGHT: DORMANT preserves identity, erodes trust.")
    print("certificateHold (X.509 CRL reason code 6) = cert not revoked, just paused.")
    print("Recovery is lighter than initial (n=8 vs n=30) because history survives.")
    print("Counterparty diversity prevents collusive recovery.")
