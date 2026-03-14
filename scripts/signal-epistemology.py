#!/usr/bin/env python3
"""
signal-epistemology.py — Two-epistemology trust signal classifier.

Trust signals are either:
1. DECAYING (memory): gossip, liveness, cert age → R=e^(-t/S)
2. OBSERVABLE (state): on-chain lock, DKIM authorship → query source directly

Mixing them is the L3.5 design trap. This tool classifies signals
and applies the correct scoring function.

References:
- Ebbinghaus 1885 (forgetting curve for decaying signals)
- Watson & Morgan, Cognition 2025 (epistemic vigilance)
"""

import math
from dataclasses import dataclass
from enum import Enum


class SignalType(Enum):
    DECAYING = "decaying"      # Memory-based, needs freshness model
    OBSERVABLE = "observable"  # State-based, query the source


@dataclass
class TrustSignal:
    code: str
    name: str
    signal_type: SignalType
    stability_hours: float  # For DECAYING only; ignored for OBSERVABLE
    epistemic_weight: float  # Watson & Morgan 2025

    def score(self, raw: float, age_hours: float = 0, state_active: bool = True) -> float:
        if self.signal_type == SignalType.OBSERVABLE:
            return raw if state_active else 0.0
        return raw * math.exp(-age_hours / self.stability_hours)


# L3.5 Signal Registry
SIGNALS = {
    "T": TrustSignal("T", "tile_proof", SignalType.DECAYING, float("inf"), 2.0),
    "G": TrustSignal("G", "gossip", SignalType.DECAYING, 4.0, 1.0),
    "A": TrustSignal("A", "attestation", SignalType.DECAYING, 720.0, 2.0),
    "S": TrustSignal("S", "sleeper", SignalType.DECAYING, 168.0, 1.5),
    "C": TrustSignal("C", "commitment", SignalType.OBSERVABLE, 0.0, 2.0),
    "D": TrustSignal("D", "dkim_authorship", SignalType.OBSERVABLE, 0.0, 1.5),
}


def classify_demo():
    print("=== Signal Epistemology Classifier ===\n")
    print(f"{'Code':<5} {'Name':<18} {'Type':<12} {'Stability':<12} {'Weight'}")
    print("-" * 60)
    for s in SIGNALS.values():
        stab = "∞" if s.stability_hours == float("inf") else (
            "n/a" if s.signal_type == SignalType.OBSERVABLE else f"{s.stability_hours}h"
        )
        print(f"{s.code:<5} {s.name:<18} {s.signal_type.value:<12} {stab:<12} {s.epistemic_weight}x")

    print("\n=== Scoring Examples ===\n")
    scenarios = [
        ("Fresh gossip (0h)", "G", 0.9, 0, True),
        ("Stale gossip (8h)", "G", 0.9, 8, True),
        ("Dead gossip (24h)", "G", 0.9, 24, True),
        ("Tile proof (never decays)", "T", 0.95, 1000, True),
        ("Commitment locked", "C", 0.8, 0, True),
        ("Commitment UNLOCKED", "C", 0.8, 0, False),
        ("DKIM valid", "D", 1.0, 0, True),
        ("DKIM revoked", "D", 1.0, 0, False),
        ("Attestation fresh", "A", 0.88, 0, True),
        ("Attestation 30d old", "A", 0.88, 720, True),
    ]

    for name, code, raw, age, active in scenarios:
        sig = SIGNALS[code]
        score = sig.score(raw, age, active)
        print(f"  {name:<30} {code}={raw:.2f} → {score:.3f} ({sig.signal_type.value})")

    # Key insight
    print("\n=== Design Trap Detection ===\n")
    print("❌ WRONG: Treating commitment like memory → decay(C, 48h) = 0.3")
    print(f"   Actual: C is OBSERVABLE → query chain → locked={SIGNALS['C'].score(0.8, 48, True):.1f} or unlocked={SIGNALS['C'].score(0.8, 48, False):.1f}")
    print()
    print("❌ WRONG: Treating gossip like state → gossip(G, 24h) = 0.9")
    print(f"   Actual: G is DECAYING → R=e^(-24/4) = {SIGNALS['G'].score(0.9, 24):.4f}")
    print()
    print("✅ RIGHT: Type system enforces epistemology. Two axioms, one wire format.")


if __name__ == "__main__":
    classify_demo()
