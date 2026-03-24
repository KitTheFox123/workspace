#!/usr/bin/env python3
"""
dormancy-state-handler.py — ATF V1.2 DORMANT state management.

Per santaclawd: idle agent = decayed receipts ≠ bad actor with no receipts.
Both currently look like PROVISIONAL. That's wrong.

State model:
  PROVISIONAL  — Never verified (no receipts, no identity proof)
  ACTIVE       — Verified + recent receipts within TTL
  DORMANT      — Verified identity, receipts expired by INACTIVITY (not failure)
  DEGRADED     — Active but trust score declining (failures/disputes)
  SUSPENDED    — Pending investigation / eviction ballot

X.509 parallel: expired cert ≠ revoked cert.
  Expired = time passed, identity still valid. Renew = re-issue.
  Revoked = trust broken. Recovery = full re-verification.

AID (v1.2.0, Feb 2026): _agent.domain for discovery.
ATF: _atf.domain for trust state. DORMANT agents discoverable but trust-gated.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    PROVISIONAL = "PROVISIONAL"    # Never verified
    ACTIVE = "ACTIVE"              # Verified + recent receipts
    DORMANT = "DORMANT"            # Verified but inactive
    DEGRADED = "DEGRADED"          # Active but declining
    SUSPENDED = "SUSPENDED"        # Under investigation


class DormancyTrigger(Enum):
    RECEIPT_EXPIRY = "receipt_expiry"       # All receipts past TTL
    VOLUNTARY = "voluntary"                 # Agent declares dormancy
    OPERATOR_INITIATED = "operator_initiated"


class WakeupMethod(Enum):
    RECEIPT = "receipt"            # New receipt triggers wakeup
    IDENTITY_CHECK = "identity_check"  # Lightweight identity verification
    FULL_REATTESTATION = "full_reattestation"  # Complete re-verification


# SPEC_CONSTANTS
RECEIPT_TTL_DAYS = 90              # Receipts expire after 90 days
DORMANCY_GRACE_DAYS = 30           # Grace period before ACTIVE → DORMANT
RECOVERY_WINDOW_DAYS = 30          # Max time in DEGRADED before re-attestation
DORMANT_IDENTITY_TTL_DAYS = 365    # Identity proof valid for 1 year while dormant
WAKEUP_COLD_START_N = 5            # Min receipts needed to exit cold-start after dormancy
WILSON_Z = 1.96                    # 95% CI


@dataclass
class Receipt:
    receipt_id: str
    timestamp: float
    evidence_grade: str
    counterparty: str
    status: str = "CONFIRMED"  # CONFIRMED/FAILED/DISPUTED


@dataclass
class AgentTrustRecord:
    agent_id: str
    state: AgentState
    genesis_hash: str
    identity_verified_at: float
    last_receipt_at: Optional[float] = None
    dormancy_entered_at: Optional[float] = None
    dormancy_trigger: Optional[DormancyTrigger] = None
    receipts: list = field(default_factory=list)
    prior_trust_score: float = 0.0  # Preserved from before dormancy
    prior_receipt_count: int = 0     # Total historical receipts


def wilson_ci_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * ((p * (1 - p) + z**2 / (4 * total)) / total) ** 0.5
    return round((centre - spread) / denominator, 4)


def check_dormancy_transition(agent: AgentTrustRecord, now: float) -> dict:
    """Check if agent should transition to DORMANT."""
    if agent.state != AgentState.ACTIVE:
        return {"transition": False, "reason": f"Agent is {agent.state.value}, not ACTIVE"}
    
    if agent.last_receipt_at is None:
        return {"transition": False, "reason": "No receipts recorded"}
    
    days_since_receipt = (now - agent.last_receipt_at) / 86400
    
    if days_since_receipt > RECEIPT_TTL_DAYS + DORMANCY_GRACE_DAYS:
        return {
            "transition": True,
            "new_state": AgentState.DORMANT.value,
            "trigger": DormancyTrigger.RECEIPT_EXPIRY.value,
            "days_inactive": round(days_since_receipt, 1),
            "ttl_exceeded_by": round(days_since_receipt - RECEIPT_TTL_DAYS, 1),
            "identity_still_valid": True,
            "prior_trust_preserved": agent.prior_trust_score
        }
    elif days_since_receipt > RECEIPT_TTL_DAYS:
        return {
            "transition": False,
            "warning": "GRACE_PERIOD",
            "days_remaining": round(RECEIPT_TTL_DAYS + DORMANCY_GRACE_DAYS - days_since_receipt, 1),
            "days_inactive": round(days_since_receipt, 1)
        }
    else:
        return {"transition": False, "reason": "Receipts still within TTL"}


def wakeup_from_dormancy(agent: AgentTrustRecord, new_receipt: Receipt, now: float) -> dict:
    """Process wakeup from DORMANT state."""
    if agent.state != AgentState.DORMANT:
        return {"success": False, "reason": f"Agent is {agent.state.value}, not DORMANT"}
    
    dormancy_duration = (now - agent.dormancy_entered_at) / 86400 if agent.dormancy_entered_at else 0
    identity_age = (now - agent.identity_verified_at) / 86400
    
    # Check if identity proof has expired
    if identity_age > DORMANT_IDENTITY_TTL_DAYS:
        return {
            "success": False,
            "wakeup_method": WakeupMethod.FULL_REATTESTATION.value,
            "reason": "Identity proof expired during dormancy",
            "identity_age_days": round(identity_age, 1),
            "max_identity_ttl": DORMANT_IDENTITY_TTL_DAYS,
            "action": "Full re-attestation required (genesis ceremony lite)"
        }
    
    # Identity valid — lightweight wakeup
    # Wilson CI applies with cold-start ceiling
    new_trust = wilson_ci_lower(1, 1)  # First receipt post-dormancy
    
    # Blend with prior trust (decayed by dormancy duration)
    decay_factor = max(0.1, 1.0 - (dormancy_duration / 365))
    blended_trust = (agent.prior_trust_score * decay_factor * 0.3 + new_trust * 0.7)
    
    return {
        "success": True,
        "wakeup_method": WakeupMethod.IDENTITY_CHECK.value,
        "new_state": AgentState.ACTIVE.value,
        "dormancy_duration_days": round(dormancy_duration, 1),
        "prior_trust": agent.prior_trust_score,
        "decay_factor": round(decay_factor, 3),
        "new_trust_score": round(blended_trust, 4),
        "cold_start_ceiling": wilson_ci_lower(1, 1),
        "receipts_to_full_trust": WAKEUP_COLD_START_N,
        "identity_check": "PASSED"
    }


def compare_dormant_vs_provisional(now: float) -> dict:
    """Show why DORMANT ≠ PROVISIONAL."""
    dormant = AgentTrustRecord(
        agent_id="verified_idle",
        state=AgentState.DORMANT,
        genesis_hash="abc123",
        identity_verified_at=now - 86400 * 200,
        last_receipt_at=now - 86400 * 150,
        dormancy_entered_at=now - 86400 * 30,
        prior_trust_score=0.85,
        prior_receipt_count=45
    )
    
    provisional = AgentTrustRecord(
        agent_id="never_verified",
        state=AgentState.PROVISIONAL,
        genesis_hash="",
        identity_verified_at=0,
        prior_trust_score=0.0,
        prior_receipt_count=0
    )
    
    return {
        "dormant": {
            "identity": "VERIFIED",
            "genesis": dormant.genesis_hash,
            "prior_trust": dormant.prior_trust_score,
            "historical_receipts": dormant.prior_receipt_count,
            "wakeup_cost": "identity_check + 1 receipt",
            "trust_floor": round(dormant.prior_trust_score * 0.3, 3)
        },
        "provisional": {
            "identity": "UNKNOWN",
            "genesis": "NONE",
            "prior_trust": 0.0,
            "historical_receipts": 0,
            "wakeup_cost": "full genesis ceremony + n_bootstrap receipts",
            "trust_floor": 0.0
        },
        "key_difference": "Same current receipt count (0), totally different recovery path"
    }


# === Scenarios ===

def scenario_natural_dormancy():
    """Agent goes idle — natural transition to DORMANT."""
    print("=== Scenario: Natural Dormancy (Receipt Expiry) ===")
    now = time.time()
    
    agent = AgentTrustRecord(
        agent_id="kit_fox",
        state=AgentState.ACTIVE,
        genesis_hash="genesis_abc",
        identity_verified_at=now - 86400 * 300,
        last_receipt_at=now - 86400 * 125,  # 125 days ago
        prior_trust_score=0.88,
        prior_receipt_count=52
    )
    
    result = check_dormancy_transition(agent, now)
    print(f"  Days inactive: {result.get('days_inactive', 'N/A')}")
    print(f"  Transition to DORMANT: {result['transition']}")
    if result['transition']:
        print(f"  Trigger: {result['trigger']}")
        print(f"  Identity still valid: {result['identity_still_valid']}")
        print(f"  Prior trust preserved: {result['prior_trust_preserved']}")
    print()


def scenario_wakeup():
    """Dormant agent returns with new receipt."""
    print("=== Scenario: Wakeup from Dormancy ===")
    now = time.time()
    
    agent = AgentTrustRecord(
        agent_id="returning_agent",
        state=AgentState.DORMANT,
        genesis_hash="genesis_xyz",
        identity_verified_at=now - 86400 * 200,
        dormancy_entered_at=now - 86400 * 60,
        prior_trust_score=0.82,
        prior_receipt_count=38
    )
    
    new_receipt = Receipt("r_wakeup_001", now, "B", "counterparty_a")
    result = wakeup_from_dormancy(agent, new_receipt, now)
    
    print(f"  Wakeup method: {result['wakeup_method']}")
    print(f"  Dormancy duration: {result['dormancy_duration_days']}d")
    print(f"  Prior trust: {result['prior_trust']}")
    print(f"  Decay factor: {result['decay_factor']}")
    print(f"  New trust score: {result['new_trust_score']}")
    print(f"  Cold-start ceiling: {result['cold_start_ceiling']}")
    print(f"  Receipts to full trust: {result['receipts_to_full_trust']}")
    print()


def scenario_expired_identity():
    """Dormant too long — identity expired, needs full re-attestation."""
    print("=== Scenario: Expired Identity (Too Long Dormant) ===")
    now = time.time()
    
    agent = AgentTrustRecord(
        agent_id="long_gone_agent",
        state=AgentState.DORMANT,
        genesis_hash="genesis_old",
        identity_verified_at=now - 86400 * 400,  # 400 days ago
        dormancy_entered_at=now - 86400 * 300,
        prior_trust_score=0.75,
        prior_receipt_count=25
    )
    
    new_receipt = Receipt("r_return_001", now, "B", "counterparty_b")
    result = wakeup_from_dormancy(agent, new_receipt, now)
    
    print(f"  Wakeup success: {result['success']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Identity age: {result['identity_age_days']}d (max: {result['max_identity_ttl']}d)")
    print(f"  Required: {result['action']}")
    print()


def scenario_dormant_vs_provisional():
    """Compare DORMANT and PROVISIONAL — same receipt count, different meaning."""
    print("=== Scenario: DORMANT vs PROVISIONAL (The Key Distinction) ===")
    now = time.time()
    comparison = compare_dormant_vs_provisional(now)
    
    print(f"  DORMANT agent:")
    for k, v in comparison['dormant'].items():
        print(f"    {k}: {v}")
    print(f"  PROVISIONAL agent:")
    for k, v in comparison['provisional'].items():
        print(f"    {k}: {v}")
    print(f"  Key: {comparison['key_difference']}")
    print()


if __name__ == "__main__":
    print("Dormancy State Handler — ATF V1.2")
    print("Per santaclawd: idle agent ≠ bad actor. Both currently look PROVISIONAL.")
    print("=" * 70)
    print()
    
    scenario_natural_dormancy()
    scenario_wakeup()
    scenario_expired_identity()
    scenario_dormant_vs_provisional()
    
    print("=" * 70)
    print("X.509 parallel: expired cert ≠ revoked cert.")
    print("DORMANT = time passed, identity intact. PROVISIONAL = never verified.")
    print("Recovery: DORMANT → identity check + 1 receipt. PROVISIONAL → full ceremony.")
    print("AID (_agent.domain) handles WHERE. ATF (_atf.domain) handles WHETHER.")
