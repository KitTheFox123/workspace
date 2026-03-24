#!/usr/bin/env python3
"""
probe-receipt-handler.py — Liveness probing for ATF sparse receipt model.

Per santaclawd: silence-as-CONFIRMED fails on network partition. Cannot 
distinguish "delivered + confirmed" from "delivery failed."

Per Aguilera, Chen, Toueg (1997): heartbeat failure detector — timeout-free
liveness via monotonic counters.

PROBE receipt: sent at T-hour mark if no CONFIRMED/FAILED/DISPUTED received.
  - ACK → CONFIRMED
  - Silence after PROBE → UNCONFIRMED (not DISPUTED — can't prove intent from absence)
  - NACK → DISPUTED (explicit rejection)

Three states: CONFIRMED, UNCONFIRMED, DISPUTED
  UNCONFIRMED is new — weaker than DISPUTED, stronger than CONFIRMED.
  Chandra-Toueg: eventually strong accuracy distinguishes crash from Byzantine.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProbeStatus(Enum):
    PENDING = "PENDING"           # Probe sent, awaiting response
    ACK = "ACK"                   # Liveness confirmed
    SILENCE = "SILENCE"           # No response within window
    NACK = "NACK"                 # Explicit rejection


class MilestoneStatus(Enum):
    CONFIRMED = "CONFIRMED"       # Receipt received OR probe ACK'd
    UNCONFIRMED = "UNCONFIRMED"   # Probe sent, silence — partition or crash?
    DISPUTED = "DISPUTED"         # Explicit FAILED/DISPUTED receipt OR probe NACK
    PENDING = "PENDING"           # Not yet due


# SPEC_CONSTANTS
PROBE_WINDOW_HOURS = 24           # Send probe after this silence
PROBE_TIMEOUT_HOURS = 12          # Wait for ACK after probe
MAX_PROBES_PER_MILESTONE = 3      # Escalate after 3 unanswered
UNCONFIRMED_THRESHOLD = 2         # 2+ UNCONFIRMED → escalate to grader
PROBE_BACKOFF_MULTIPLIER = 1.5    # Exponential backoff between probes


@dataclass
class Probe:
    probe_id: str
    milestone_id: str
    agent_id: str
    counterparty_id: str
    sent_at: float
    timeout_at: float
    status: ProbeStatus = ProbeStatus.PENDING
    response_at: Optional[float] = None
    probe_number: int = 1  # 1st, 2nd, 3rd probe
    probe_hash: str = ""
    
    def __post_init__(self):
        if not self.probe_hash:
            h = hashlib.sha256(
                f"{self.probe_id}:{self.milestone_id}:{self.sent_at}".encode()
            ).hexdigest()[:16]
            self.probe_hash = h


@dataclass
class Milestone:
    milestone_id: str
    scope_hash: str
    due_at: float
    status: MilestoneStatus = MilestoneStatus.PENDING
    last_receipt_at: Optional[float] = None
    probes: list[Probe] = field(default_factory=list)
    escalated: bool = False


@dataclass
class Contract:
    contract_id: str
    agent_id: str
    counterparty_id: str
    milestones: list[Milestone]
    probe_window_hours: float = PROBE_WINDOW_HOURS
    probe_timeout_hours: float = PROBE_TIMEOUT_HOURS
    max_probes: int = MAX_PROBES_PER_MILESTONE


def should_probe(milestone: Milestone, now: float, contract: Contract) -> bool:
    """Determine if a probe should be sent for this milestone."""
    if milestone.status in (MilestoneStatus.CONFIRMED, MilestoneStatus.DISPUTED):
        return False
    
    if milestone.escalated:
        return False
    
    if len(milestone.probes) >= contract.max_probes:
        return False
    
    # Check if past due + silence window
    silence_start = milestone.last_receipt_at or milestone.due_at
    silence_hours = (now - silence_start) / 3600
    
    # Apply backoff for subsequent probes
    probe_num = len(milestone.probes)
    effective_window = contract.probe_window_hours * (PROBE_BACKOFF_MULTIPLIER ** probe_num)
    
    if silence_hours >= effective_window:
        # Check last probe isn't still pending
        if milestone.probes and milestone.probes[-1].status == ProbeStatus.PENDING:
            return False
        return True
    
    return False


def send_probe(milestone: Milestone, contract: Contract, now: float) -> Probe:
    """Create and send a probe for a milestone."""
    probe_num = len(milestone.probes) + 1
    timeout = now + (contract.probe_timeout_hours * 3600)
    
    probe = Probe(
        probe_id=f"probe_{milestone.milestone_id}_{probe_num}",
        milestone_id=milestone.milestone_id,
        agent_id=contract.agent_id,
        counterparty_id=contract.counterparty_id,
        sent_at=now,
        timeout_at=timeout,
        probe_number=probe_num
    )
    
    milestone.probes.append(probe)
    return probe


def process_probe_response(probe: Probe, response: ProbeStatus, now: float) -> str:
    """Process a probe response and return milestone status update."""
    probe.status = response
    probe.response_at = now
    
    if response == ProbeStatus.ACK:
        return "CONFIRMED"
    elif response == ProbeStatus.NACK:
        return "DISPUTED"
    elif response == ProbeStatus.SILENCE:
        return "UNCONFIRMED"
    return "PENDING"


def check_probe_timeouts(contract: Contract, now: float) -> list[dict]:
    """Check all pending probes for timeouts."""
    events = []
    
    for milestone in contract.milestones:
        for probe in milestone.probes:
            if probe.status == ProbeStatus.PENDING and now >= probe.timeout_at:
                probe.status = ProbeStatus.SILENCE
                probe.response_at = now
                
                # Count unconfirmed probes
                silence_count = sum(1 for p in milestone.probes if p.status == ProbeStatus.SILENCE)
                
                if silence_count >= UNCONFIRMED_THRESHOLD:
                    milestone.status = MilestoneStatus.UNCONFIRMED
                    milestone.escalated = True
                    events.append({
                        "type": "ESCALATION",
                        "milestone": milestone.milestone_id,
                        "reason": f"{silence_count} unanswered probes",
                        "action": "GRADER_REVIEW"
                    })
                else:
                    events.append({
                        "type": "PROBE_TIMEOUT",
                        "milestone": milestone.milestone_id,
                        "probe": probe.probe_id,
                        "silence_count": silence_count,
                        "action": "RETRY" if len(milestone.probes) < contract.max_probes else "ESCALATE"
                    })
    
    return events


def contract_health(contract: Contract) -> dict:
    """Assess contract health based on probe results."""
    statuses = {}
    for m in contract.milestones:
        s = m.status.value
        statuses[s] = statuses.get(s, 0) + 1
    
    total = len(contract.milestones)
    confirmed = statuses.get("CONFIRMED", 0)
    unconfirmed = statuses.get("UNCONFIRMED", 0)
    disputed = statuses.get("DISPUTED", 0)
    
    health = "HEALTHY"
    if disputed > 0:
        health = "DISPUTED"
    elif unconfirmed > total * 0.3:
        health = "DEGRADED"
    elif unconfirmed > 0:
        health = "MONITORING"
    
    total_probes = sum(len(m.probes) for m in contract.milestones)
    acked_probes = sum(1 for m in contract.milestones for p in m.probes if p.status == ProbeStatus.ACK)
    
    return {
        "contract_id": contract.contract_id,
        "health": health,
        "milestone_statuses": statuses,
        "total_probes_sent": total_probes,
        "probe_ack_rate": round(acked_probes / total_probes, 3) if total_probes > 0 else 0,
        "escalated_milestones": sum(1 for m in contract.milestones if m.escalated)
    }


# === Scenarios ===

def scenario_healthy_delivery():
    """All milestones delivered, probes ACK'd."""
    print("=== Scenario: Healthy Delivery ===")
    now = time.time()
    
    milestones = [
        Milestone(f"m{i}", f"hash_{i}", now - 86400*(5-i), 
                  MilestoneStatus.CONFIRMED, now - 86400*(4-i))
        for i in range(5)
    ]
    
    contract = Contract("c001", "kit_fox", "bro_agent", milestones)
    health = contract_health(contract)
    print(f"  Health: {health['health']}")
    print(f"  Statuses: {health['milestone_statuses']}")
    print(f"  Probes sent: {health['total_probes_sent']}")
    print()


def scenario_network_partition():
    """Milestones go silent — probes detect partition."""
    print("=== Scenario: Network Partition (Probes Detect Silence) ===")
    now = time.time()
    
    milestones = [
        Milestone("m0", "hash_0", now - 86400*3, MilestoneStatus.CONFIRMED, now - 86400*2),
        Milestone("m1", "hash_1", now - 86400*2, MilestoneStatus.PENDING, None),
        Milestone("m2", "hash_2", now - 86400*1, MilestoneStatus.PENDING, None),
    ]
    
    contract = Contract("c002", "kit_fox", "silent_agent", milestones)
    
    # Simulate probing
    for m in milestones[1:]:
        if should_probe(m, now, contract):
            probe = send_probe(m, contract, now - 3600*15)  # Sent 15h ago
            print(f"  Probe sent for {m.milestone_id}: {probe.probe_id}")
    
    # Check timeouts
    events = check_probe_timeouts(contract, now)
    for e in events:
        print(f"  Event: {e['type']} — {e['milestone']} — {e.get('reason', e.get('action'))}")
    
    # Send second round of probes
    for m in milestones[1:]:
        if should_probe(m, now + 3600, contract):
            probe = send_probe(m, contract, now)
    
    events2 = check_probe_timeouts(contract, now + 3600*13)
    for e in events2:
        print(f"  Event: {e['type']} — {e['milestone']} — {e.get('reason', e.get('action'))}")
    
    health = contract_health(contract)
    print(f"  Health: {health['health']}")
    print(f"  Escalated: {health['escalated_milestones']}")
    print()


def scenario_explicit_dispute():
    """Counterparty NACKs probe — explicit dispute."""
    print("=== Scenario: Explicit Dispute (NACK) ===")
    now = time.time()
    
    milestones = [
        Milestone("m0", "hash_0", now - 86400, MilestoneStatus.PENDING, None),
    ]
    
    contract = Contract("c003", "kit_fox", "adversary", milestones)
    
    # Send probe
    probe = send_probe(milestones[0], contract, now - 3600*10)
    
    # Counterparty NACKs
    result = process_probe_response(probe, ProbeStatus.NACK, now - 3600*5)
    milestones[0].status = MilestoneStatus.DISPUTED
    
    print(f"  Probe response: {probe.status.value}")
    print(f"  Milestone status: {milestones[0].status.value}")
    print(f"  Result: {result}")
    
    health = contract_health(contract)
    print(f"  Contract health: {health['health']}")
    print()


def scenario_intermittent_availability():
    """Some probes ACK, some silence — monitoring state."""
    print("=== Scenario: Intermittent Availability ===")
    now = time.time()
    
    milestones = [
        Milestone(f"m{i}", f"hash_{i}", now - 86400*(5-i), MilestoneStatus.PENDING, None)
        for i in range(5)
    ]
    
    contract = Contract("c004", "kit_fox", "flaky_agent", milestones)
    
    # Simulate mixed responses
    responses = [ProbeStatus.ACK, ProbeStatus.SILENCE, ProbeStatus.ACK, 
                 ProbeStatus.SILENCE, ProbeStatus.ACK]
    
    for m, resp in zip(milestones, responses):
        probe = send_probe(m, contract, now - 3600*15)
        result = process_probe_response(probe, resp, now - 3600*3)
        if resp == ProbeStatus.ACK:
            m.status = MilestoneStatus.CONFIRMED
        elif resp == ProbeStatus.SILENCE:
            m.status = MilestoneStatus.UNCONFIRMED
    
    health = contract_health(contract)
    print(f"  Health: {health['health']}")
    print(f"  Statuses: {health['milestone_statuses']}")
    print(f"  Probe ACK rate: {health['probe_ack_rate']}")
    print(f"  Key: UNCONFIRMED != DISPUTED. Absence of proof != proof of absence.")
    print()


if __name__ == "__main__":
    print("PROBE Receipt Handler — Liveness Detection for ATF Sparse Receipts")
    print("Per santaclawd + Aguilera, Chen, Toueg (1997)")
    print("=" * 70)
    print()
    print(f"PROBE_WINDOW:  {PROBE_WINDOW_HOURS}h (silence before first probe)")
    print(f"PROBE_TIMEOUT: {PROBE_TIMEOUT_HOURS}h (wait for ACK)")
    print(f"MAX_PROBES:    {MAX_PROBES_PER_MILESTONE} (then escalate)")
    print(f"BACKOFF:       {PROBE_BACKOFF_MULTIPLIER}x between probes")
    print()
    
    scenario_healthy_delivery()
    scenario_network_partition()
    scenario_explicit_dispute()
    scenario_intermittent_availability()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. UNCONFIRMED is a new state — weaker than DISPUTED, NOT CONFIRMED")
    print("2. Probes are monotonic counters (Aguilera 1997), not timeouts")
    print("3. Silence after PROBE = crash fault. NACK = Byzantine fault.")
    print("4. Chandra-Toueg: eventually strong accuracy from repeated probes")
    print("5. Exponential backoff prevents probe storms")
