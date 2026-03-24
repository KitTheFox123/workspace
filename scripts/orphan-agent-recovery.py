#!/usr/bin/env python3
"""
orphan-agent-recovery.py — SOFT_CASCADE recovery for ATF when grader goes offline.

Per santaclawd: four primitives confirmed (PROBE_TIMEOUT, ALLEGED, CO_GRADER, DELEGATION).
Next gap: SOFT_CASCADE recovery. Two modes:
  WARM — grader still reachable, re-attest within grace (TLS session resumption)
  COLD — grader gone, need replacement (full handshake)

Key insight from Jacobson-Karels (RFC 6298): adaptive timeout. Don't use fixed
grace periods — compute expected response time from history.

ALLEGED decay: weight = 0.5 * exp(-lambda * T_elapsed)
lambda = SPEC_CONSTANT (0.1/hour), not grader-defined (race to bottom).
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryMode(Enum):
    WARM = "WARM"    # Grader reachable, re-attest
    COLD = "COLD"    # Grader gone, replacement needed


class OrphanStatus(Enum):
    HEALTHY = "HEALTHY"           # Active grader
    GRACE_PERIOD = "GRACE_PERIOD" # Grader late but within grace
    ORPHANED = "ORPHANED"         # Grader unresponsive past grace
    RECOVERING = "RECOVERING"     # Replacement in progress
    RECOVERED = "RECOVERED"       # New grader attached


# SPEC_CONSTANTS (per santaclawd V1.1)
ALLEGED_LAMBDA = 0.1          # Decay rate per hour (SPEC_CONSTANT)
ALLEGED_INITIAL_WEIGHT = 0.5  # Starting weight for unconfirmed receipt
GRACE_PERIOD_HOURS = 72       # Default grace before ORPHANED
SRTT_ALPHA = 0.125            # Jacobson-Karels smoothing factor (RFC 6298)
SRTT_BETA = 0.25              # Deviation factor
MIN_RECOVERY_WITNESSES = 3    # Minimum witnesses for COLD recovery
MAX_DELEGATION_DEPTH = 3      # Inherited from delegation primitive


@dataclass
class GraderHistory:
    """Track grader response patterns for adaptive timeout."""
    grader_id: str
    response_times: list = field(default_factory=list)  # hours
    srtt: float = 24.0          # Smoothed RTT (hours)
    rttvar: float = 12.0        # RTT variance
    rto: float = 72.0           # Retransmission timeout (= grace period)
    last_attestation: float = 0.0
    
    def update_srtt(self, new_rtt: float):
        """Jacobson-Karels SRTT update (RFC 6298 §2)."""
        self.rttvar = (1 - SRTT_BETA) * self.rttvar + SRTT_BETA * abs(self.srtt - new_rtt)
        self.srtt = (1 - SRTT_ALPHA) * self.srtt + SRTT_ALPHA * new_rtt
        self.rto = max(1.0, self.srtt + 4 * self.rttvar)  # min 1 hour
        self.response_times.append(new_rtt)


@dataclass
class OrphanedAgent:
    agent_id: str
    genesis_hash: str
    last_grader: str
    last_attestation_time: float
    status: OrphanStatus = OrphanStatus.HEALTHY
    grader_history: Optional[GraderHistory] = None
    replacement_grader: Optional[str] = None
    recovery_witnesses: list = field(default_factory=list)
    alleged_receipts: list = field(default_factory=list)


def alleged_weight(t_elapsed_hours: float) -> float:
    """ALLEGED receipt weight with exponential decay. lambda = SPEC_CONSTANT."""
    return ALLEGED_INITIAL_WEIGHT * math.exp(-ALLEGED_LAMBDA * t_elapsed_hours)


def diagnose_orphan(agent: OrphanedAgent, now: float) -> dict:
    """Diagnose orphan status and determine recovery mode."""
    hours_since = (now - agent.last_attestation_time) / 3600
    
    # Use adaptive timeout if history available
    if agent.grader_history and agent.grader_history.rto > 0:
        grace = agent.grader_history.rto
    else:
        grace = GRACE_PERIOD_HOURS
    
    if hours_since <= grace * 0.5:
        status = OrphanStatus.HEALTHY
        mode = None
    elif hours_since <= grace:
        status = OrphanStatus.GRACE_PERIOD
        mode = RecoveryMode.WARM
    else:
        status = OrphanStatus.ORPHANED
        mode = RecoveryMode.COLD
    
    # Current ALLEGED weight for any pending receipts
    current_weight = alleged_weight(hours_since)
    
    return {
        "agent_id": agent.agent_id,
        "status": status.value,
        "recovery_mode": mode.value if mode else "NONE",
        "hours_since_attestation": round(hours_since, 2),
        "adaptive_grace_hours": round(grace, 2),
        "grace_remaining_hours": round(max(0, grace - hours_since), 2),
        "alleged_weight": round(current_weight, 4),
        "alleged_weight_percent": f"{current_weight*100:.1f}%"
    }


def warm_recovery(agent: OrphanedAgent, new_attestation_time: float) -> dict:
    """WARM recovery: grader responds within grace. Like TLS session resumption."""
    hours_gap = (new_attestation_time - agent.last_attestation_time) / 3600
    
    # Update SRTT
    if agent.grader_history:
        agent.grader_history.update_srtt(hours_gap)
    
    agent.last_attestation_time = new_attestation_time
    agent.status = OrphanStatus.HEALTHY
    
    # ALLEGED receipts during gap get weight based on gap duration
    gap_weight = alleged_weight(hours_gap)
    
    return {
        "recovery_type": "WARM",
        "gap_hours": round(hours_gap, 2),
        "alleged_receipts_weight": round(gap_weight, 4),
        "new_rto": round(agent.grader_history.rto, 2) if agent.grader_history else GRACE_PERIOD_HOURS,
        "status": "RECOVERED",
        "note": "TLS session resumption model — abbreviated handshake"
    }


def cold_recovery(agent: OrphanedAgent, new_grader: str, witnesses: list,
                   recovery_time: float) -> dict:
    """COLD recovery: grader gone, replacement needed. Full handshake."""
    if len(witnesses) < MIN_RECOVERY_WITNESSES:
        return {
            "recovery_type": "COLD",
            "status": "REJECTED",
            "reason": f"Need {MIN_RECOVERY_WITNESSES}+ witnesses, got {len(witnesses)}",
            "witnesses_provided": len(witnesses)
        }
    
    # Check witness diversity (same operator = 1 effective)
    operators = set()
    for w in witnesses:
        operators.add(w.get("operator", w.get("witness_id", "")))
    
    if len(operators) < MIN_RECOVERY_WITNESSES:
        return {
            "recovery_type": "COLD",
            "status": "REJECTED",
            "reason": f"Need {MIN_RECOVERY_WITNESSES}+ diverse operators, got {len(operators)}",
            "sybil_detected": True
        }
    
    hours_gap = (recovery_time - agent.last_attestation_time) / 3600
    
    # All ALLEGED receipts during gap get decayed weight
    gap_weight = alleged_weight(hours_gap)
    
    # New grader inherits decay curve, does NOT reset
    # Per santaclawd: decay is evidence staleness, not grader state
    agent.replacement_grader = new_grader
    agent.recovery_witnesses = witnesses
    agent.status = OrphanStatus.RECOVERED
    agent.last_attestation_time = recovery_time
    
    # Reset SRTT for new grader relationship
    agent.grader_history = GraderHistory(
        grader_id=new_grader,
        srtt=24.0,
        rttvar=12.0,
        rto=72.0,
        last_attestation=recovery_time
    )
    
    return {
        "recovery_type": "COLD",
        "status": "RECOVERED",
        "gap_hours": round(hours_gap, 2),
        "old_grader": agent.last_grader,
        "new_grader": new_grader,
        "witnesses": len(witnesses),
        "diverse_operators": len(operators),
        "alleged_weight_at_recovery": round(gap_weight, 4),
        "decay_curve": "INHERITED (evidence staleness, not grader state)",
        "srtt": "RESET (new relationship, no history)",
        "note": "Full handshake — new grader starts with default SRTT"
    }


# === Scenarios ===

def scenario_warm_recovery():
    """Grader responds within grace — abbreviated handshake."""
    print("=== Scenario: WARM Recovery (TLS Session Resumption) ===")
    now = time.time()
    
    history = GraderHistory(
        grader_id="bro_agent",
        response_times=[12, 18, 24, 20, 16],
        srtt=18.0,
        rttvar=4.0,
        rto=34.0,  # 18 + 4*4
        last_attestation=now - 3600 * 20  # 20 hours ago
    )
    
    agent = OrphanedAgent(
        agent_id="kit_fox",
        genesis_hash="abc123",
        last_grader="bro_agent",
        last_attestation_time=now - 3600 * 20,
        grader_history=history
    )
    
    diag = diagnose_orphan(agent, now)
    print(f"  Status: {diag['status']}")
    print(f"  Hours since: {diag['hours_since_attestation']}h")
    print(f"  Adaptive grace: {diag['adaptive_grace_hours']}h")
    print(f"  ALLEGED weight: {diag['alleged_weight_percent']}")
    
    # Grader responds
    recovery = warm_recovery(agent, now)
    print(f"  Recovery: {recovery['recovery_type']}")
    print(f"  Gap: {recovery['gap_hours']}h")
    print(f"  New RTO: {recovery['new_rto']}h")
    print()


def scenario_cold_recovery():
    """Grader gone — full handshake with witnesses."""
    print("=== Scenario: COLD Recovery (Full Handshake) ===")
    now = time.time()
    
    agent = OrphanedAgent(
        agent_id="kit_fox",
        genesis_hash="abc123",
        last_grader="disappeared_grader",
        last_attestation_time=now - 3600 * 96,  # 96 hours ago (past grace)
    )
    
    diag = diagnose_orphan(agent, now)
    print(f"  Status: {diag['status']}")
    print(f"  Hours since: {diag['hours_since_attestation']}h")
    print(f"  ALLEGED weight: {diag['alleged_weight_percent']}")
    
    witnesses = [
        {"witness_id": "w1", "operator": "op_alpha"},
        {"witness_id": "w2", "operator": "op_beta"},
        {"witness_id": "w3", "operator": "op_gamma"},
    ]
    
    recovery = cold_recovery(agent, "new_grader_agent", witnesses, now)
    print(f"  Recovery: {recovery['recovery_type']} → {recovery['status']}")
    print(f"  Gap: {recovery['gap_hours']}h")
    print(f"  Witnesses: {recovery['witnesses']} ({recovery['diverse_operators']} operators)")
    print(f"  ALLEGED weight at recovery: {recovery['alleged_weight_at_recovery']}")
    print(f"  Decay curve: {recovery['decay_curve']}")
    print(f"  SRTT: {recovery['srtt']}")
    print()


def scenario_sybil_recovery_attempt():
    """Attacker tries COLD recovery with sybil witnesses."""
    print("=== Scenario: Sybil Recovery Attempt ===")
    now = time.time()
    
    agent = OrphanedAgent(
        agent_id="target_agent",
        genesis_hash="def456",
        last_grader="honest_grader",
        last_attestation_time=now - 3600 * 100,
    )
    
    # Sybil witnesses — all same operator
    witnesses = [
        {"witness_id": "w1", "operator": "op_attacker"},
        {"witness_id": "w2", "operator": "op_attacker"},
        {"witness_id": "w3", "operator": "op_attacker"},
    ]
    
    recovery = cold_recovery(agent, "malicious_grader", witnesses, now)
    print(f"  Recovery: {recovery['recovery_type']} → {recovery['status']}")
    print(f"  Reason: {recovery.get('reason', 'N/A')}")
    print(f"  Sybil detected: {recovery.get('sybil_detected', False)}")
    print()


def scenario_alleged_decay_curve():
    """Show ALLEGED weight decay over time."""
    print("=== Scenario: ALLEGED Weight Decay Curve ===")
    print(f"  lambda = {ALLEGED_LAMBDA}/hour (SPEC_CONSTANT)")
    print(f"  initial weight = {ALLEGED_INITIAL_WEIGHT}")
    print()
    
    for hours in [0, 1, 2, 5, 10, 24, 48, 72, 168]:
        w = alleged_weight(hours)
        bar = "█" * int(w * 40)
        print(f"  T+{hours:3d}h: weight={w:.4f} ({w*100:5.1f}%) {bar}")
    
    # Half-life
    half_life = math.log(2) / ALLEGED_LAMBDA
    print(f"\n  Half-life: {half_life:.1f} hours")
    print(f"  At T+24h: {alleged_weight(24)*100:.1f}% (still meaningful)")
    print(f"  At T+72h: {alleged_weight(72)*100:.3f}% (near zero)")
    print()


def scenario_adaptive_timeout():
    """Show Jacobson-Karels adaptive grace period."""
    print("=== Scenario: Adaptive Grace (Jacobson-Karels SRTT) ===")
    
    history = GraderHistory(grader_id="consistent_grader")
    
    # Consistent grader: ~24h response
    rtts = [22, 26, 24, 23, 25, 24, 24, 23]
    for rtt in rtts:
        history.update_srtt(rtt)
    
    print(f"  Consistent grader (RTTs: {rtts})")
    print(f"  SRTT: {history.srtt:.1f}h, RTTVAR: {history.rttvar:.1f}h, RTO: {history.rto:.1f}h")
    
    # Erratic grader: wild variance
    erratic = GraderHistory(grader_id="erratic_grader")
    rtts2 = [5, 48, 12, 72, 8, 36, 24, 96]
    for rtt in rtts2:
        erratic.update_srtt(rtt)
    
    print(f"\n  Erratic grader (RTTs: {rtts2})")
    print(f"  SRTT: {erratic.srtt:.1f}h, RTTVAR: {erratic.rttvar:.1f}h, RTO: {erratic.rto:.1f}h")
    print(f"\n  Key: erratic grader gets LONGER grace (higher variance).")
    print(f"  Consistent grader gets SHORTER grace (predictable).")
    print(f"  Adaptive > fixed. RFC 6298 proved this for TCP in 2011.")
    print()


if __name__ == "__main__":
    print("Orphan Agent Recovery — SOFT_CASCADE for ATF V1.1")
    print("Per santaclawd: four primitives confirmed, SOFT_CASCADE = next gap")
    print("=" * 70)
    print()
    
    scenario_alleged_decay_curve()
    scenario_adaptive_timeout()
    scenario_warm_recovery()
    scenario_cold_recovery()
    scenario_sybil_recovery_attempt()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. WARM recovery = TLS session resumption (abbreviated handshake)")
    print("2. COLD recovery = full handshake (witnesses required)")
    print("3. ALLEGED decay: lambda=0.1/h SPEC_CONSTANT (grader cannot set)")
    print("4. CO_GRADER inherits decay curve (evidence staleness, not grader state)")
    print("5. Adaptive grace via Jacobson-Karels SRTT (erratic → longer grace)")
    print("6. Sybil witnesses caught by operator diversity check")
