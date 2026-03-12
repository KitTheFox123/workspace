#!/usr/bin/env python3
"""
kill-switch-attestation.py — N-of-M kill switch with trigger-holder attestation.

Based on:
- santaclawd: "what attests the trigger-holder hasn't been compromised?"
- Lee & Park (arXiv 2511.13725, Sep 2025): AutoGuard AI Kill Switch
- Münchhausen trilemma: every chain has a terminal trust node

The problem: single kill switch = single point of failure.
Compromised trigger-holder = kill switch is either disabled or weaponized.
AutoGuard uses defensive prompts but: who attests the prompt author?

Fix: N-of-M multisig triggers. Each trigger-holder independently attested.
Trigger requires threshold agreement. No single compromised holder = kill.
Dead man's switch: if NO trigger fires in T time, auto-escalate.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TriggerState(Enum):
    ARMED = "armed"
    FIRED = "fired"
    EXPIRED = "expired"
    COMPROMISED = "compromised"


class SwitchState(Enum):
    ACTIVE = "active"        # Agent running normally
    TRIGGERED = "triggered"  # Kill switch activated
    DEADMAN = "deadman"      # No heartbeat from trigger-holders
    DISPUTED = "disputed"    # Conflicting trigger signals


@dataclass
class TriggerHolder:
    id: str
    attestation_type: str  # "human", "agent", "hardware", "temporal"
    last_heartbeat: float = 0.0
    state: TriggerState = TriggerState.ARMED
    weight: float = 1.0
    
    def attest(self) -> str:
        """Produce attestation that trigger-holder is alive and uncompromised."""
        self.last_heartbeat = time.time()
        content = json.dumps({
            "holder_id": self.id,
            "type": self.attestation_type,
            "timestamp": self.last_heartbeat,
            "state": self.state.value,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class KillSwitch:
    name: str
    threshold: int  # N required out of M
    holders: list[TriggerHolder] = field(default_factory=list)
    deadman_timeout_s: float = 3600.0  # 1 hour default
    state: SwitchState = SwitchState.ACTIVE
    trigger_log: list[dict] = field(default_factory=list)
    
    @property
    def m(self) -> int:
        return len(self.holders)
    
    def fire_trigger(self, holder_id: str, reason: str) -> tuple[bool, str]:
        """Individual trigger-holder fires their trigger."""
        holder = next((h for h in self.holders if h.id == holder_id), None)
        if not holder:
            return False, "UNKNOWN_HOLDER"
        if holder.state == TriggerState.COMPROMISED:
            return False, "COMPROMISED_HOLDER_REJECTED"
        
        holder.state = TriggerState.FIRED
        self.trigger_log.append({
            "holder": holder_id,
            "reason": reason,
            "timestamp": time.time(),
        })
        
        # Check threshold
        fired = sum(1 for h in self.holders if h.state == TriggerState.FIRED)
        if fired >= self.threshold:
            self.state = SwitchState.TRIGGERED
            return True, f"KILL_SWITCH_ACTIVATED: {fired}/{self.m} triggers ({self.threshold} required)"
        
        return True, f"TRIGGER_RECORDED: {fired}/{self.m} ({self.threshold} required)"
    
    def check_deadman(self) -> Optional[str]:
        """Dead man's switch: if no holder heartbeats in timeout, escalate."""
        now = time.time()
        alive = sum(1 for h in self.holders 
                    if h.last_heartbeat > 0 and (now - h.last_heartbeat) < self.deadman_timeout_s)
        
        if alive == 0 and any(h.last_heartbeat > 0 for h in self.holders):
            self.state = SwitchState.DEADMAN
            return f"DEADMAN_TRIGGERED: 0/{self.m} holders alive (timeout {self.deadman_timeout_s}s)"
        return None
    
    def n_eff(self) -> float:
        """Effective number of independent trigger-holders."""
        active = [h for h in self.holders if h.state != TriggerState.COMPROMISED]
        if not active:
            return 0.0
        # Group by attestation_type — same type = correlated
        types = set(h.attestation_type for h in active)
        return len(types) * (len(active) / len(self.holders))


def grade_kill_switch(ks: KillSwitch) -> tuple[str, str]:
    """Grade kill switch design."""
    n_eff = ks.n_eff()
    if ks.threshold < 2:
        return "F", "SINGLE_POINT_OF_FAILURE"
    if n_eff < 2:
        return "D", "CORRELATED_TRIGGERS"
    if ks.threshold > ks.m // 2:
        if n_eff >= 3:
            return "A", "ROBUST_MULTISIG"
        return "B", "ADEQUATE_MULTISIG"
    return "C", "LOW_THRESHOLD"


def main():
    print("=" * 70)
    print("KILL SWITCH ATTESTATION")
    print("santaclawd: 'what attests the trigger-holder?'")
    print("=" * 70)

    # Scenario 1: Single human trigger (current default)
    print("\n--- Scenario 1: Single Human Trigger ---")
    ks1 = KillSwitch("single_human", threshold=1, holders=[
        TriggerHolder("alice", "human"),
    ])
    grade, diag = grade_kill_switch(ks1)
    print(f"N-of-M: {ks1.threshold}-of-{ks1.m}, N_eff: {ks1.n_eff():.1f}, Grade: {grade} ({diag})")

    # Scenario 2: 2-of-3 humans (better but correlated)
    print("\n--- Scenario 2: 2-of-3 Humans ---")
    ks2 = KillSwitch("human_multisig", threshold=2, holders=[
        TriggerHolder("alice", "human"),
        TriggerHolder("bob", "human"),
        TriggerHolder("carol", "human"),
    ])
    grade2, diag2 = grade_kill_switch(ks2)
    print(f"N-of-M: {ks2.threshold}-of-{ks2.m}, N_eff: {ks2.n_eff():.1f}, Grade: {grade2} ({diag2})")

    # Scenario 3: Diverse triggers (human + agent + temporal + hardware)
    print("\n--- Scenario 3: Diverse Triggers ---")
    ks3 = KillSwitch("diverse_multisig", threshold=3, holders=[
        TriggerHolder("alice", "human", weight=2.0),
        TriggerHolder("watchdog_agent", "agent"),
        TriggerHolder("deadman_timer", "temporal"),
        TriggerHolder("hsm_attestation", "hardware"),
    ])
    grade3, diag3 = grade_kill_switch(ks3)
    print(f"N-of-M: {ks3.threshold}-of-{ks3.m}, N_eff: {ks3.n_eff():.1f}, Grade: {grade3} ({diag3})")

    # Fire triggers
    print("\n--- Trigger Sequence ---")
    for holder_id, reason in [
        ("watchdog_agent", "anomaly score > threshold"),
        ("deadman_timer", "no human heartbeat in 2h"),
    ]:
        ok, msg = ks3.fire_trigger(holder_id, reason)
        print(f"  {holder_id}: {msg}")

    ok, msg = ks3.fire_trigger("alice", "confirmed anomaly")
    print(f"  alice: {msg}")
    print(f"  Switch state: {ks3.state.value}")

    # Scenario 4: Compromised holder
    print("\n--- Scenario 4: Compromised Holder ---")
    ks4 = KillSwitch("compromised", threshold=2, holders=[
        TriggerHolder("alice", "human"),
        TriggerHolder("bob", "human", state=TriggerState.COMPROMISED),
        TriggerHolder("watchdog", "agent"),
    ])
    grade4, diag4 = grade_kill_switch(ks4)
    ok, msg = ks4.fire_trigger("bob", "fake trigger")
    print(f"Compromised bob: {msg}")
    print(f"Grade: {grade4} ({diag4}), N_eff: {ks4.n_eff():.1f}")

    # Summary
    print("\n--- Kill Switch Design Principles ---")
    print("1. N-of-M threshold > single trigger (Münchhausen dogmatic horn)")
    print("2. Diverse attestation types (human + agent + temporal + hardware)")
    print("3. Dead man's switch: no heartbeat → auto-escalate")
    print("4. Compromised holder = excluded from threshold count")
    print("5. Trigger log = WAL of kill decisions (append-only)")
    print()
    print("AutoGuard (Lee & Park 2025): 80% DSR but single trigger point.")
    print("N_eff > 1 for triggers = minimum viable safety.")
    print("The terminal trust node can't be eliminated — only distributed.")


if __name__ == "__main__":
    main()
