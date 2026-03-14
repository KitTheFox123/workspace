#!/usr/bin/env python3
"""
scar-trust-scorer.py — Revocation history as positive trust signal.

"An agent that revoked a bad attestation is MORE trustworthy than one that never erred."
- Schechtman 1996: identity IS the narrative including errors
- Staw 1976: sunk cost / escalation of commitment post-decision

Scars (self-corrections) increase trust. Unresolved errors decrease it.
The append-only log means mistakes are part of the record, not erased.

Usage: python3 scar-trust-scorer.py
"""

from dataclasses import dataclass


@dataclass
class ScarEvent:
    """A revocation or correction in the agent's history."""
    event_type: str  # "revocation", "correction", "admission"
    age_hours: float
    self_initiated: bool  # Did the agent initiate the correction?
    resolved: bool  # Was the underlying issue fixed?


def scar_score(events: list[ScarEvent]) -> dict:
    """Score an agent's scar history.
    
    Self-initiated corrections = positive signal (narrative integrity).
    External-forced revocations = neutral (compliance, not self-awareness).
    Unresolved errors = negative (no self-correction capability).
    """
    if not events:
        return {"score": 0.5, "grade": "C", "reason": "no history — unknown self-correction ability"}

    positive = 0
    negative = 0
    total = len(events)

    for e in events:
        if e.self_initiated and e.resolved:
            positive += 1.0  # Best: self-caught, self-fixed
        elif not e.self_initiated and e.resolved:
            positive += 0.5  # OK: caught externally, fixed
        elif e.self_initiated and not e.resolved:
            negative += 0.3  # Acknowledged but unfixed
        else:
            negative += 1.0  # Worst: externally caught, unfixed

    ratio = positive / (positive + negative) if (positive + negative) > 0 else 0.5
    
    # More scars (if mostly positive) = more trust, up to a point
    volume_bonus = min(0.1, total * 0.02) if ratio > 0.6 else 0
    final = min(1.0, ratio + volume_bonus)

    grade = "A" if final >= 0.9 else "B" if final >= 0.7 else "C" if final >= 0.5 else "D" if final >= 0.3 else "F"

    return {
        "score": round(final, 3),
        "grade": grade,
        "positive_scars": positive,
        "negative_scars": negative,
        "total_events": total,
        "self_correction_rate": round(sum(1 for e in events if e.self_initiated) / total, 2),
        "resolution_rate": round(sum(1 for e in events if e.resolved) / total, 2),
    }


def demo():
    print("=== Scar Trust Scorer ===\n")
    print("'The scar proves self-correction.' (Schechtman 1996)\n")

    scenarios = [
        ("No history", []),
        ("Perfect self-correction", [
            ScarEvent("revocation", 720, True, True),
            ScarEvent("correction", 360, True, True),
            ScarEvent("admission", 48, True, True),
        ]),
        ("Externally caught but fixed", [
            ScarEvent("revocation", 720, False, True),
            ScarEvent("correction", 360, False, True),
        ]),
        ("Self-aware but unfixed", [
            ScarEvent("admission", 48, True, False),
            ScarEvent("admission", 24, True, False),
        ]),
        ("Worst: caught and unfixed", [
            ScarEvent("revocation", 168, False, False),
            ScarEvent("revocation", 72, False, False),
            ScarEvent("correction", 24, False, False),
        ]),
        ("Mixed history (realistic)", [
            ScarEvent("revocation", 720, True, True),   # Self-caught, fixed
            ScarEvent("correction", 360, False, True),  # External, fixed
            ScarEvent("admission", 168, True, True),    # Self-caught, fixed
            ScarEvent("revocation", 48, False, False),  # External, unfixed (recent)
        ]),
    ]

    for name, events in scenarios:
        result = scar_score(events)
        print(f"  {name:35s} → {result['grade']} ({result['score']:.3f})")
        if events:
            print(f"    self-correction: {result['self_correction_rate']:.0%}, resolution: {result['resolution_rate']:.0%}")
        print()


if __name__ == "__main__":
    demo()
