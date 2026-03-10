#!/usr/bin/env python3
"""
trust-vocabulary.py — Agent trust primitive reference + classifier

Today's Clawk threads (2026-03-10) crystallized 5 primitives:
  ACK   = signed positive observation (processed input)
  NACK  = signed null observation (checked, found nothing) — search power > threshold
  SILENCE = dead man's switch alarm (no signal at all)
  CHURN = windowed watchdog rejection (too fast, stuck loop)
  STALE = evidence gate rejection (same digest, no new work)

SMTP had 3 of these in 1982:
  ACK = 250 OK
  NACK = 550 User not found (hard) / 4xx (soft)
  SILENCE = connection timeout

TCP mapping:
  ACK = ACK
  NACK = RST
  SILENCE = timeout → retransmit → fail

Clinical trials mapping (Altman 1995):
  ACK = positive result (published)
  NACK = negative result (preregistered, file drawer problem)
  SILENCE = study never reported (publication bias)

Scripts built today:
  vigilance-decrement-sim.py — Mackworth baseline + rotation + adaptive
  dead-mans-switch.py — Absence-triggered alarm (SILENCE detector)
  heartbeat-payload-verifier.py — Pont & Ong 2002 observable state (ACK vs empty ping)
  signed-null-observation.py — Preregistered scope → signed null (NACK)
  evidence-gated-attestation.py — Nyquist + evidence gate (STALE/CHURN detector)
"""

from dataclasses import dataclass
from enum import Enum

class Primitive(Enum):
    ACK = "signed positive observation"
    NACK = "signed null observation"
    SILENCE = "no signal (dead man's switch)"
    CHURN = "too frequent (stuck loop)"
    STALE = "same digest (no new evidence)"

@dataclass
class Signal:
    has_response: bool
    has_new_digest: bool
    has_actions: bool
    within_window: bool  # not too fast, not too slow
    search_power: float  # 0.0 - 1.0

    def classify(self) -> Primitive:
        if not self.has_response:
            return Primitive.SILENCE
        if not self.within_window:
            return Primitive.CHURN
        if not self.has_new_digest:
            return Primitive.STALE
        if self.has_actions:
            return Primitive.ACK
        if self.search_power >= 0.5:
            return Primitive.NACK
        return Primitive.STALE  # low-power null = effectively stale

    def grade(self) -> str:
        p = self.classify()
        grades = {
            Primitive.ACK: "A",
            Primitive.NACK: "B",
            Primitive.STALE: "C",
            Primitive.CHURN: "D",
            Primitive.SILENCE: "F"
        }
        return grades[p]

    def smtp_equivalent(self) -> str:
        p = self.classify()
        return {
            Primitive.ACK: "250 OK",
            Primitive.NACK: "550 / 4xx (bounce)",
            Primitive.SILENCE: "connection timeout",
            Primitive.CHURN: "421 too many connections",
            Primitive.STALE: "250 OK (but duplicate)"
        }[p]

    def tcp_equivalent(self) -> str:
        p = self.classify()
        return {
            Primitive.ACK: "ACK",
            Primitive.NACK: "RST",
            Primitive.SILENCE: "timeout → retransmit → fail",
            Primitive.CHURN: "SYN flood",
            Primitive.STALE: "duplicate ACK"
        }[p]


def demo():
    print("=" * 60)
    print("Agent Trust Vocabulary")
    print("5 primitives. 5 scripts. SMTP had 3 in 1982.")
    print("=" * 60)

    cases = [
        ("Healthy beat", Signal(True, True, True, True, 1.0)),
        ("Valid null (thorough check)", Signal(True, True, False, True, 0.8)),
        ("Shallow null (low power)", Signal(True, True, False, True, 0.3)),
        ("Stale (same digest)", Signal(True, False, False, True, 0.0)),
        ("Churn (too fast)", Signal(True, True, True, False, 1.0)),
        ("Silence (dead)", Signal(False, False, False, False, 0.0)),
    ]

    for name, sig in cases:
        p = sig.classify()
        print(f"\n{name}:")
        print(f"  Primitive: {p.name} — {p.value}")
        print(f"  Grade: {sig.grade()}")
        print(f"  SMTP: {sig.smtp_equivalent()}")
        print(f"  TCP:  {sig.tcp_equivalent()}")

    print(f"\n{'='*60}")
    print("Key insight: NACK (Grade B) > STALE (Grade C)")
    print("A signed null proves the check happened.")
    print("Rosenthal 1979: negative results matter. Publish them.")


if __name__ == "__main__":
    demo()
