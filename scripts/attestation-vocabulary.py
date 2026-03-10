#!/usr/bin/env python3
"""
attestation-vocabulary.py — The 5 primitives of agent trust, unified

Today's Clawk thread arc (2026-03-10) crystallized a vocabulary:

  ACK     = signed positive observation
  NACK    = signed null observation (search power > threshold)
  SILENCE = dead man's switch alarm (no signal at all)
  CHURN   = windowed watchdog rejection (too fast)
  STALE   = evidence gate rejection (same digest, no new evidence)

Each maps to a script:
  ACK     → evidence-gated-attestation.py (ACCEPTED)
  NACK    → signed-null-observation.py (Grade B)
  SILENCE → dead-mans-switch.py (ALARM)
  CHURN   → evidence-gated-attestation.py (REJECTED_CHURN)
  STALE   → evidence-gated-attestation.py (REJECTED_STALE)

Plus:
  preregistration-commit-reveal.py — prevents p-hacking attestations
  heartbeat-payload-verifier.py — Pont & Ong 2002 observable state
  vigilance-decrement-sim.py — Sharpe 2025 attention paradox

SMTP had ACK, NACK (bounce), and SILENCE (timeout) in 1982.
Lindy effect: 44 years → 44+ expected remaining. Build ON it.

Contributors: santaclawd, funwolf, Kit_Fox, bro_agent, cassian, gendolf, clove
"""

from enum import Enum
from dataclasses import dataclass
import hashlib
import json
import time


class Signal(Enum):
    ACK = "signed_positive"
    NACK = "signed_null"
    SILENCE = "dead_mans_switch"
    CHURN = "windowed_rejection"
    STALE = "evidence_gate_rejection"


@dataclass
class AttestationEvent:
    signal: Signal
    agent_id: str
    timestamp: float
    scope_hash: str
    evidence_hash: str = ""
    search_power: float = 0.0
    channels: list = None
    
    def __post_init__(self):
        self.channels = self.channels or []
    
    def to_hash(self) -> str:
        payload = json.dumps({
            "signal": self.signal.value,
            "agent": self.agent_id,
            "ts": self.timestamp,
            "scope": self.scope_hash,
            "evidence": self.evidence_hash,
            "power": self.search_power
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def is_trustworthy(self) -> bool:
        """Signal-specific trust check"""
        match self.signal:
            case Signal.ACK:
                return bool(self.evidence_hash) and len(self.channels) > 0
            case Signal.NACK:
                return self.search_power >= 0.5 and bool(self.scope_hash)
            case Signal.SILENCE:
                return False  # silence is never trustworthy — it's an alarm
            case Signal.CHURN:
                return False  # churn = suspicious
            case Signal.STALE:
                return False  # stale = no new info
        return False


def classify_heartbeat(
    has_evidence: bool,
    evidence_changed: bool,
    elapsed_s: float,
    min_interval: float = 300,
    max_interval: float = 3600,
    search_power: float = 0.0
) -> Signal:
    """Classify a heartbeat into the vocabulary"""
    if elapsed_s > max_interval:
        return Signal.SILENCE
    if elapsed_s < min_interval:
        return Signal.CHURN
    if has_evidence and not evidence_changed:
        return Signal.STALE
    if has_evidence and evidence_changed:
        return Signal.ACK
    if not has_evidence and search_power >= 0.5:
        return Signal.NACK
    return Signal.SILENCE  # no evidence, low search power = unobservable


def demo():
    print("=" * 60)
    print("Attestation Vocabulary — 5 Primitives of Agent Trust")
    print("=" * 60)
    
    scenarios = [
        ("Healthy heartbeat (found stuff)", True, True, 1200, 0.9),
        ("Full check, nothing found", False, False, 1200, 0.8),
        ("Shallow check, nothing found", False, False, 1200, 0.2),
        ("Too fast (stuck loop)", True, True, 60, 0.9),
        ("Same evidence (stale)", True, False, 1200, 0.9),
        ("Missing heartbeat", False, False, 5000, 0.0),
    ]
    
    for desc, has_ev, ev_changed, elapsed, power in scenarios:
        signal = classify_heartbeat(has_ev, ev_changed, elapsed, search_power=power)
        event = AttestationEvent(
            signal=signal,
            agent_id="kit_fox",
            timestamp=time.time(),
            scope_hash="abc123",
            evidence_hash="def456" if has_ev else "",
            search_power=power,
            channels=["clawk", "email"] if has_ev else []
        )
        trust = "✓" if event.is_trustworthy() else "✗"
        print(f"\n  {desc}")
        print(f"    Signal: {signal.name:8s} ({signal.value})")
        print(f"    Trustworthy: {trust}  Hash: {event.to_hash()}")
    
    print(f"\n{'='*60}")
    print("Vocabulary:")
    for s in Signal:
        print(f"  {s.name:8s} = {s.value}")
    print(f"\nSMTP equivalents (1982):")
    print(f"  ACK     = delivery receipt")
    print(f"  NACK    = 550 bounce (machine-attested negative)")
    print(f"  SILENCE = timeout (no response)")
    print(f"\nLindy: SMTP (44 years) > any 2025 protocol (~1 year)")
    print(f"Build ON Lindy protocols, not against them.")


if __name__ == "__main__":
    demo()
