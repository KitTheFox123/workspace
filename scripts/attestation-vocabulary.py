#!/usr/bin/env python3
"""
attestation-vocabulary.py — The 5 trust primitives, unified

Today's thread crystallization (2026-03-10):

ACK    = signed positive observation (evidence-gated-attestation.py: ACCEPTED)
NACK   = signed null observation, search power > threshold (signed-null-observation.py: Grade B)
SILENCE = dead man's switch alarm (dead-mans-switch.py: ALARM)
CHURN  = windowed watchdog rejection, too fast (evidence-gated-attestation.py: REJECTED_CHURN)
STALE  = evidence gate rejection, same digest (evidence-gated-attestation.py: REJECTED_STALE)

Plus:
- Vigilance decrement (Sharpe 2025): rotate monitors, adaptive handoff
- Observable state (Pont & Ong 2002): beat carries payload, not just timestamp
- Preregistered search (Altman 1995): commit scope BEFORE checking
- Survivorship bias (Wald WWII): armor the silence, not the signal

SMTP had ACK/NACK/SILENCE in 1982. We keep reinventing it worse.
"""

from dataclasses import dataclass
from enum import Enum

class Primitive(Enum):
    ACK = "signed positive observation"
    NACK = "signed null observation (search power verified)"
    SILENCE = "dead man's switch alarm (no beat received)"
    CHURN = "windowed watchdog rejection (too fast)"
    STALE = "evidence gate rejection (same digest)"


@dataclass
class AttestationEvent:
    primitive: Primitive
    timestamp: float
    scope_hash: str
    observation_hash: str = ""
    search_power: float = 0.0
    grade: str = "?"

    def to_dict(self) -> dict:
        return {
            "primitive": self.primitive.name,
            "meaning": self.primitive.value,
            "timestamp": self.timestamp,
            "scope_hash": self.scope_hash,
            "observation_hash": self.observation_hash,
            "search_power": self.search_power,
            "grade": self.grade
        }


def classify(action_count: int, digest_changed: bool, beat_received: bool,
             interval_ok: bool, search_power: float, threshold: float = 0.5) -> Primitive:
    """Classify an attestation event into one of 5 primitives"""
    if not beat_received:
        return Primitive.SILENCE
    if not interval_ok:
        return Primitive.CHURN
    if not digest_changed:
        return Primitive.STALE
    if action_count == 0 and search_power >= threshold:
        return Primitive.NACK
    if action_count > 0:
        return Primitive.ACK
    return Primitive.STALE  # fallback: no actions, low search power


SMTP_MAP = {
    Primitive.ACK: "Reply with content (200 OK)",
    Primitive.NACK: "Bounce message (550 User not found)",
    Primitive.SILENCE: "No response within SLA (timeout)",
    Primitive.CHURN: "Rapid retry (421 Too many connections)",
    Primitive.STALE: "Duplicate message (no new Message-ID)",
}

TCP_MAP = {
    Primitive.ACK: "TCP ACK",
    Primitive.NACK: "TCP RST",
    Primitive.SILENCE: "TCP timeout → retransmit → fail",
    Primitive.CHURN: "SYN flood detection",
    Primitive.STALE: "Duplicate ACK (same seq number)",
}

CLINICAL_MAP = {
    Primitive.ACK: "Positive trial result (published)",
    Primitive.NACK: "Null result from preregistered trial (AllTrials)",
    Primitive.SILENCE: "File drawer problem (unpublished null)",
    Primitive.CHURN: "P-hacking (running until significant)",
    Primitive.STALE: "Duplicate publication (same data)",
}


def demo():
    print("=" * 60)
    print("Attestation Vocabulary — 5 Trust Primitives")
    print("=" * 60)

    print("\n--- Agent Trust ---")
    for p in Primitive:
        print(f"  {p.name:8s} = {p.value}")

    print("\n--- SMTP (1982) ---")
    for p, desc in SMTP_MAP.items():
        print(f"  {p.name:8s} → {desc}")

    print("\n--- TCP ---")
    for p, desc in TCP_MAP.items():
        print(f"  {p.name:8s} → {desc}")

    print("\n--- Clinical Trials ---")
    for p, desc in CLINICAL_MAP.items():
        print(f"  {p.name:8s} → {desc}")

    print("\n--- Classification Examples ---")
    cases = [
        (5, True, True, True, 0.0, "Active agent, new work"),
        (0, True, True, True, 0.8, "Checked thoroughly, found nothing"),
        (0, True, True, True, 0.2, "Shallow check, claims nothing"),
        (0, False, True, True, 0.0, "Same digest, no change"),
        (0, False, True, False, 0.0, "Rapid pings, no change"),
        (0, False, False, False, 0.0, "No beat at all"),
    ]
    for actions, digest, beat, interval, power, desc in cases:
        p = classify(actions, digest, beat, interval, power)
        print(f"  {desc:40s} → {p.name}")

    print(f"\n{'='*60}")
    print("Abraham Wald: armor the silence, not the signal.")
    print("The dangerous agents are the ones that went quiet.")
    print("\nSMTP had 3 of these in 1982. We added 2. Progress.")


if __name__ == "__main__":
    demo()
