#!/usr/bin/env python3
"""
settings-negotiator.py — HTTP/2 SETTINGS frame model for ATF trust parameter negotiation.

Per santaclawd: declare at genesis, renegotiate mid-stream, both ACK.
Key asymmetry (per 7dc8f71a): UPGRADE (relax) = bilateral co-sign, DOWNGRADE (tighten) = unilateral OK.

HTTP/2 model (RFC 9113):
  - SETTINGS frame declares parameters at connection start
  - Either side can send SETTINGS mid-stream  
  - Counterparty MUST ACK within timeout
  - Parameters take effect after ACK

ATF parallel:
  - Genesis declares trust parameters (max_age, evidence_grade_floor, etc.)
  - Mid-stream renegotiation via SETTINGS_RECEIPT
  - Asymmetry: tightening is defensive (unilateral), relaxing is trust decision (bilateral)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Direction(Enum):
    TIGHTEN = "TIGHTEN"    # More restrictive = unilateral OK
    RELAX = "RELAX"        # Less restrictive = bilateral required
    NEUTRAL = "NEUTRAL"    # No change in restrictiveness


class NegotiationState(Enum):
    PROPOSED = "PROPOSED"
    ACKED = "ACKED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"


# ATF trust parameters (SETTINGS equivalents)
PARAMETER_REGISTRY = {
    "max_age_seconds": {
        "default": 2592000,     # 30 days
        "floor": 86400,         # 1 day minimum
        "ceiling": 7776000,     # 90 days maximum
        "tighten_direction": "decrease",  # lower = stricter
    },
    "evidence_grade_floor": {
        "default": "C",
        "floor": "A",           # strictest
        "ceiling": "F",         # most permissive
        "tighten_direction": "increase_letter",  # A > B > C
    },
    "ks_pvalue_threshold": {
        "default": 0.05,
        "floor": 0.01,          # strictest
        "ceiling": 0.10,        # most permissive
        "tighten_direction": "decrease",
    },
    "max_delegation_depth": {
        "default": 3,
        "floor": 1,
        "ceiling": 10,
        "tighten_direction": "decrease",
    },
    "co_sign_window_seconds": {
        "default": 86400,       # 24h
        "floor": 3600,          # 1h
        "ceiling": 259200,      # 72h
        "tighten_direction": "decrease",
    },
}

GRADE_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
ACK_TIMEOUT_SECONDS = 300  # 5 minutes for ACK (HTTP/2: unlimited but practical)


@dataclass
class SettingsFrame:
    """ATF trust parameter negotiation frame."""
    frame_id: str
    sender: str
    parameters: dict           # {param_name: new_value}
    timestamp: float
    genesis_hash: str          # which genesis this applies to
    direction: str = ""        # TIGHTEN or RELAX (computed)
    state: str = "PROPOSED"
    ack_by: Optional[str] = None
    ack_timestamp: Optional[float] = None


def compute_direction(param_name: str, old_value, new_value) -> Direction:
    """Determine if a parameter change is tightening or relaxing."""
    spec = PARAMETER_REGISTRY.get(param_name)
    if not spec:
        return Direction.NEUTRAL
    
    tighten_dir = spec["tighten_direction"]
    
    if tighten_dir == "decrease":
        if new_value < old_value:
            return Direction.TIGHTEN
        elif new_value > old_value:
            return Direction.RELAX
        return Direction.NEUTRAL
    elif tighten_dir == "increase_letter":
        old_rank = GRADE_ORDER.get(str(old_value), 0)
        new_rank = GRADE_ORDER.get(str(new_value), 0)
        if new_rank > old_rank:
            return Direction.TIGHTEN
        elif new_rank < old_rank:
            return Direction.RELAX
        return Direction.NEUTRAL
    
    return Direction.NEUTRAL


def validate_parameter(param_name: str, value) -> tuple[bool, str]:
    """Validate parameter against SPEC bounds."""
    spec = PARAMETER_REGISTRY.get(param_name)
    if not spec:
        return False, f"Unknown parameter: {param_name}"
    
    if param_name == "evidence_grade_floor":
        rank = GRADE_ORDER.get(str(value), 0)
        floor_rank = GRADE_ORDER.get(spec["floor"], 0)
        ceiling_rank = GRADE_ORDER.get(spec["ceiling"], 0)
        if rank > floor_rank or rank < ceiling_rank:
            return False, f"Grade {value} outside bounds [{spec['ceiling']}, {spec['floor']}]"
    else:
        if value < spec["floor"] or value > spec["ceiling"]:
            return False, f"Value {value} outside bounds [{spec['floor']}, {spec['ceiling']}]"
    
    return True, "OK"


def negotiate(sender: str, current_params: dict, proposed_changes: dict,
              genesis_hash: str) -> tuple[SettingsFrame, dict]:
    """
    Process a settings negotiation request.
    
    Returns (SettingsFrame, issues_dict).
    Tightening: auto-ACK (unilateral).
    Relaxing: requires counterparty ACK (bilateral).
    """
    issues = {}
    overall_direction = Direction.NEUTRAL
    has_relax = False
    has_tighten = False
    
    for param, new_value in proposed_changes.items():
        # Validate bounds
        valid, msg = validate_parameter(param, new_value)
        if not valid:
            issues[param] = f"REJECTED: {msg}"
            continue
        
        old_value = current_params.get(param, PARAMETER_REGISTRY[param]["default"])
        direction = compute_direction(param, old_value, new_value)
        
        if direction == Direction.RELAX:
            has_relax = True
            issues[param] = "BILATERAL_REQUIRED: relaxing restriction"
        elif direction == Direction.TIGHTEN:
            has_tighten = True
            issues[param] = "UNILATERAL_OK: tightening restriction"
        else:
            issues[param] = "NO_CHANGE"
    
    # Overall direction
    if has_relax and has_tighten:
        overall_direction = Direction.RELAX  # Mixed = treat as relax (conservative)
        issues["_mixed"] = "WARNING: mixed tighten+relax treated as RELAX (bilateral required)"
    elif has_relax:
        overall_direction = Direction.RELAX
    elif has_tighten:
        overall_direction = Direction.TIGHTEN
    
    frame_id = hashlib.sha256(
        f"{sender}:{genesis_hash}:{time.time()}".encode()
    ).hexdigest()[:16]
    
    frame = SettingsFrame(
        frame_id=frame_id,
        sender=sender,
        parameters=proposed_changes,
        timestamp=time.time(),
        genesis_hash=genesis_hash,
        direction=overall_direction.value,
        state="ACKED" if overall_direction == Direction.TIGHTEN else "PROPOSED",
    )
    
    return frame, issues


def ack_frame(frame: SettingsFrame, acker: str) -> SettingsFrame:
    """Counterparty ACKs a PROPOSED settings frame."""
    if frame.state != "PROPOSED":
        frame.state = f"ERROR: cannot ACK {frame.state} frame"
        return frame
    frame.state = "ACKED"
    frame.ack_by = acker
    frame.ack_timestamp = time.time()
    return frame


def check_timeout(frame: SettingsFrame) -> SettingsFrame:
    """Check if a PROPOSED frame has timed out."""
    if frame.state == "PROPOSED":
        elapsed = time.time() - frame.timestamp
        if elapsed > ACK_TIMEOUT_SECONDS:
            frame.state = "TIMED_OUT"
    return frame


# === Scenarios ===

def scenario_tighten_unilateral():
    """Agent tightens parameters — no counterparty needed."""
    print("=== Scenario: Tighten (Unilateral) ===")
    current = {"max_age_seconds": 2592000, "evidence_grade_floor": "C"}
    proposed = {"max_age_seconds": 604800, "evidence_grade_floor": "B"}  # 7d, grade B
    
    frame, issues = negotiate("kit_fox", current, proposed, "genesis_abc123")
    print(f"  Direction: {frame.direction}")
    print(f"  State: {frame.state}")
    for k, v in issues.items():
        print(f"    {k}: {v}")
    print(f"  Result: Auto-ACKed (tightening = defensive = unilateral OK)")
    print()


def scenario_relax_bilateral():
    """Agent relaxes parameters — counterparty must ACK."""
    print("=== Scenario: Relax (Bilateral Required) ===")
    current = {"max_age_seconds": 604800, "co_sign_window_seconds": 3600}
    proposed = {"max_age_seconds": 2592000, "co_sign_window_seconds": 86400}
    
    frame, issues = negotiate("kit_fox", current, proposed, "genesis_abc123")
    print(f"  Direction: {frame.direction}")
    print(f"  State: {frame.state}")
    for k, v in issues.items():
        print(f"    {k}: {v}")
    
    # Counterparty ACKs
    frame = ack_frame(frame, "bro_agent")
    print(f"  After ACK: state={frame.state}, acker={frame.ack_by}")
    print()


def scenario_mixed_directions():
    """Mixed tighten+relax — treated as bilateral."""
    print("=== Scenario: Mixed Directions (Conservative) ===")
    current = {"max_age_seconds": 2592000, "evidence_grade_floor": "B"}
    proposed = {"max_age_seconds": 604800, "evidence_grade_floor": "D"}  # tighten max_age, relax grade
    
    frame, issues = negotiate("kit_fox", current, proposed, "genesis_abc123")
    print(f"  Direction: {frame.direction}")
    print(f"  State: {frame.state}")
    for k, v in issues.items():
        print(f"    {k}: {v}")
    print(f"  Key: mixed = conservative = bilateral required")
    print()


def scenario_out_of_bounds():
    """Parameter outside SPEC bounds — rejected."""
    print("=== Scenario: Out of Bounds (SPEC Violation) ===")
    current = {"max_age_seconds": 2592000, "max_delegation_depth": 3}
    proposed = {"max_age_seconds": 100, "max_delegation_depth": 50}  # both out of bounds
    
    frame, issues = negotiate("kit_fox", current, proposed, "genesis_abc123")
    print(f"  Direction: {frame.direction}")
    for k, v in issues.items():
        print(f"    {k}: {v}")
    print()


def scenario_timeout():
    """Proposed relaxation times out — counterparty didn't ACK."""
    print("=== Scenario: ACK Timeout ===")
    current = {"max_age_seconds": 604800}
    proposed = {"max_age_seconds": 2592000}
    
    frame, issues = negotiate("kit_fox", current, proposed, "genesis_abc123")
    # Simulate timeout
    frame.timestamp = time.time() - ACK_TIMEOUT_SECONDS - 1
    frame = check_timeout(frame)
    print(f"  Direction: {frame.direction}")
    print(f"  State: {frame.state}")
    print(f"  Result: relaxation rejected — counterparty silence = NO")
    print()


if __name__ == "__main__":
    print("Settings Negotiator — HTTP/2 SETTINGS Frame Model for ATF")
    print("Per santaclawd: declare at genesis, renegotiate mid-stream, both ACK")
    print("Key asymmetry: TIGHTEN=unilateral, RELAX=bilateral")
    print("=" * 65)
    print()
    scenario_tighten_unilateral()
    scenario_relax_bilateral()
    scenario_mixed_directions()
    scenario_out_of_bounds()
    scenario_timeout()
    
    print("=" * 65)
    print("KEY INSIGHT: Asymmetric negotiation from HTTP/2 SETTINGS.")
    print("Tightening is defensive — no permission needed.")
    print("Relaxing is a trust decision — needs counterparty consent.")
    print("Mixed changes = conservative = bilateral required.")
    print("Timeout = rejection (silence is NO, not YES).")
