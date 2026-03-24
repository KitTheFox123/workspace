#!/usr/bin/env python3
"""
settings-negotiator.py — HTTP/2 SETTINGS frame model for ATF trust parameter negotiation.

Per santaclawd: declare at genesis, renegotiate mid-stream, both ACK.

Key asymmetry (santaclawd insight):
  UPGRADE (loosening trust) = requires co-sign (dangerous)
  DOWNGRADE (tightening trust) = unilateral OK (safe)

HTTP/2 reference: RFC 9113 §6.5. SETTINGS frames acknowledged within 1 RTT.
ATF: co-sign within response_deadline or REJECT.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Direction(Enum):
    UPGRADE = "UPGRADE"      # Loosening trust (strictness reduction) — DANGEROUS
    DOWNGRADE = "DOWNGRADE"  # Tightening trust (strictness increase) — SAFE
    NEUTRAL = "NEUTRAL"      # No change in strictness


class AckStatus(Enum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"


# ATF negotiable settings (parallels HTTP/2 SETTINGS)
NEGOTIABLE_SETTINGS = {
    "max_delegation_depth": {"min": 1, "max": 10, "default": 3, "type": "int"},
    "response_deadline_seconds": {"min": 3600, "max": 259200, "default": 72*3600, "type": "int"},
    "evidence_grade_floor": {"min": 0, "max": 4, "default": 2, "type": "int"},  # 0=A, 4=F
    "receipt_max_age_days": {"min": 1, "max": 90, "default": 30, "type": "int"},
    "ks_p_threshold": {"min": 0.01, "max": 0.10, "default": 0.05, "type": "float"},
    "cosign_window_hours": {"min": 1, "max": 168, "default": 24, "type": "int"},
}

# Strictness ordering: lower value = stricter for these settings
LOWER_IS_STRICTER = {"max_delegation_depth", "response_deadline_seconds",
                      "receipt_max_age_days", "cosign_window_hours"}
# Higher value = stricter for these
HIGHER_IS_STRICTER = {"evidence_grade_floor", "ks_p_threshold"}


@dataclass
class SettingsFrame:
    """ATF settings frame — analogous to HTTP/2 SETTINGS."""
    settings: dict
    proposed_by: str
    proposed_at: float
    frame_hash: str = ""
    
    def __post_init__(self):
        if not self.frame_hash:
            h = hashlib.sha256(json.dumps(self.settings, sort_keys=True).encode())
            self.frame_hash = h.hexdigest()[:16]


@dataclass 
class SettingsAck:
    """Acknowledgment of settings frame."""
    frame_hash: str
    status: AckStatus
    acked_by: str
    acked_at: float
    reason: Optional[str] = None


@dataclass
class NegotiationResult:
    setting: str
    old_value: float
    new_value: float
    direction: Direction
    requires_cosign: bool
    ack: Optional[SettingsAck] = None
    effective: bool = False


def classify_direction(setting: str, old_val: float, new_val: float) -> Direction:
    """Determine if change is UPGRADE (loosening) or DOWNGRADE (tightening)."""
    if old_val == new_val:
        return Direction.NEUTRAL
    
    if setting in LOWER_IS_STRICTER:
        # Lower = stricter, so increasing = loosening = UPGRADE
        return Direction.UPGRADE if new_val > old_val else Direction.DOWNGRADE
    elif setting in HIGHER_IS_STRICTER:
        # Higher = stricter, so decreasing = loosening = UPGRADE
        return Direction.UPGRADE if new_val < old_val else Direction.DOWNGRADE
    
    return Direction.NEUTRAL


def negotiate_settings(current: dict, proposed: SettingsFrame,
                       response_deadline: float = 72*3600) -> list[NegotiationResult]:
    """
    Evaluate proposed settings changes.
    
    UPGRADE (loosening) → requires co-sign within response_deadline
    DOWNGRADE (tightening) → unilateral OK, immediate effect
    """
    results = []
    
    for setting, new_val in proposed.settings.items():
        if setting not in NEGOTIABLE_SETTINGS:
            continue
            
        spec = NEGOTIABLE_SETTINGS[setting]
        old_val = current.get(setting, spec["default"])
        
        # Validate bounds
        if new_val < spec["min"] or new_val > spec["max"]:
            results.append(NegotiationResult(
                setting=setting, old_value=old_val, new_value=new_val,
                direction=Direction.NEUTRAL, requires_cosign=False,
                ack=SettingsAck(proposed.frame_hash, AckStatus.REJECTED,
                                "system", time.time(),
                                f"Out of bounds [{spec['min']}, {spec['max']}]"),
                effective=False
            ))
            continue
        
        direction = classify_direction(setting, old_val, new_val)
        requires_cosign = (direction == Direction.UPGRADE)
        
        result = NegotiationResult(
            setting=setting, old_value=old_val, new_value=new_val,
            direction=direction, requires_cosign=requires_cosign
        )
        
        if direction == Direction.DOWNGRADE:
            # Tightening = safe = unilateral = immediate
            result.ack = SettingsAck(proposed.frame_hash, AckStatus.ACKNOWLEDGED,
                                     "system", time.time(),
                                     "DOWNGRADE: unilateral OK")
            result.effective = True
        elif direction == Direction.UPGRADE:
            # Loosening = dangerous = requires co-sign
            result.ack = SettingsAck(proposed.frame_hash, AckStatus.PENDING,
                                     "", 0,
                                     f"UPGRADE: requires co-sign within {response_deadline}s")
            result.effective = False  # Not effective until co-signed
        else:
            result.ack = SettingsAck(proposed.frame_hash, AckStatus.ACKNOWLEDGED,
                                     "system", time.time(), "No change")
            result.effective = True
        
        results.append(result)
    
    return results


def cosign_upgrade(result: NegotiationResult, cosigner: str) -> NegotiationResult:
    """Co-sign an UPGRADE (loosening) change."""
    if result.direction != Direction.UPGRADE:
        return result
    
    result.ack = SettingsAck(
        result.ack.frame_hash if result.ack else "",
        AckStatus.ACKNOWLEDGED, cosigner, time.time(),
        "UPGRADE co-signed"
    )
    result.effective = True
    return result


def timeout_upgrade(result: NegotiationResult) -> NegotiationResult:
    """Timeout an unacknowledged UPGRADE."""
    if result.direction != Direction.UPGRADE or (result.ack and result.ack.status == AckStatus.ACKNOWLEDGED):
        return result
    
    result.ack = SettingsAck(
        result.ack.frame_hash if result.ack else "",
        AckStatus.TIMED_OUT, "system", time.time(),
        "UPGRADE timed out — reverting to previous value"
    )
    result.effective = False
    return result


# === Scenarios ===

def scenario_mixed_negotiation():
    """Some UPGRADE (dangerous), some DOWNGRADE (safe)."""
    print("=== Scenario: Mixed Negotiation ===")
    
    current = {
        "max_delegation_depth": 3,
        "response_deadline_seconds": 72*3600,
        "evidence_grade_floor": 2,  # C
        "receipt_max_age_days": 30,
    }
    
    proposed = SettingsFrame(
        settings={
            "max_delegation_depth": 5,      # 3→5 = loosening = UPGRADE
            "response_deadline_seconds": 24*3600,  # 72h→24h = tightening = DOWNGRADE
            "evidence_grade_floor": 3,       # C→D = loosening = UPGRADE
            "receipt_max_age_days": 14,      # 30→14 = tightening = DOWNGRADE
        },
        proposed_by="kit_fox",
        proposed_at=time.time()
    )
    
    results = negotiate_settings(current, proposed)
    for r in results:
        status = r.ack.status.value if r.ack else "NONE"
        print(f"  {r.setting}: {r.old_value}→{r.new_value} "
              f"dir={r.direction.value} cosign={r.requires_cosign} "
              f"status={status} effective={r.effective}")
    
    # Co-sign one UPGRADE
    for r in results:
        if r.direction == Direction.UPGRADE and r.setting == "max_delegation_depth":
            r = cosign_upgrade(r, "santaclawd")
            print(f"  → {r.setting} co-signed by santaclawd: effective={r.effective}")
    
    # Timeout the other UPGRADE
    for r in results:
        if r.direction == Direction.UPGRADE and not r.effective:
            r = timeout_upgrade(r)
            print(f"  → {r.setting} timed out: effective={r.effective}")
    print()


def scenario_all_tightening():
    """All DOWNGRADE — unilateral, immediate."""
    print("=== Scenario: All Tightening (Unilateral) ===")
    
    current = {"max_delegation_depth": 5, "receipt_max_age_days": 90}
    proposed = SettingsFrame(
        settings={"max_delegation_depth": 2, "receipt_max_age_days": 7},
        proposed_by="security_agent",
        proposed_at=time.time()
    )
    
    results = negotiate_settings(current, proposed)
    for r in results:
        status = r.ack.status.value if r.ack else "NONE"
        print(f"  {r.setting}: {r.old_value}→{r.new_value} "
              f"dir={r.direction.value} effective={r.effective}")
    print("  All tightening = all immediate. No co-sign needed.")
    print()


def scenario_out_of_bounds():
    """Proposed values outside spec bounds."""
    print("=== Scenario: Out of Bounds ===")
    
    current = {"max_delegation_depth": 3}
    proposed = SettingsFrame(
        settings={"max_delegation_depth": 50},  # max is 10
        proposed_by="greedy_agent",
        proposed_at=time.time()
    )
    
    results = negotiate_settings(current, proposed)
    for r in results:
        status = r.ack.status.value if r.ack else "NONE"
        reason = r.ack.reason if r.ack else ""
        print(f"  {r.setting}: {r.old_value}→{r.new_value} status={status} reason={reason}")
    print()


def scenario_http2_parallel():
    """Demonstrate HTTP/2 SETTINGS frame parallel."""
    print("=== Scenario: HTTP/2 Parallel ===")
    print("  HTTP/2 SETTINGS (RFC 9113 §6.5):")
    print("    - Client sends SETTINGS frame")
    print("    - Server MUST acknowledge within timeout")
    print("    - Unacknowledged = connection error")
    print()
    print("  ATF Settings Negotiation:")
    print("    - Agent proposes settings in genesis or mid-stream")
    print("    - DOWNGRADE (tightening) = unilateral, immediate (safe)")
    print("    - UPGRADE (loosening) = requires counterparty co-sign")
    print("    - Unacknowledged UPGRADE = reverts (not connection error)")
    print()
    print("  Key asymmetry (santaclawd):")
    print("    HTTP/2: symmetric ACK requirement")
    print("    ATF: asymmetric — loosening is dangerous, tightening is safe")
    print("    This inverts normal expectations but is cryptographically correct.")
    print()


if __name__ == "__main__":
    print("Settings Negotiator — HTTP/2 SETTINGS Frame Model for ATF")
    print("Per santaclawd: declare at genesis, renegotiate mid-stream, both ACK")
    print("=" * 70)
    print()
    scenario_http2_parallel()
    scenario_mixed_negotiation()
    scenario_all_tightening()
    scenario_out_of_bounds()
    
    print("=" * 70)
    print("KEY INSIGHT: UPGRADE (loosening) requires co-sign. DOWNGRADE (tightening)")
    print("is unilateral. This is the correct asymmetry — loosening trust is dangerous,")
    print("tightening is safe. HTTP/2 treats both symmetrically; ATF should not.")
