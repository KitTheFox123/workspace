#!/usr/bin/env python3
"""
silence-classifier.py — Distinguishes expected silence from anomalous silence.

Based on:
- Informative censoring / MNAR (Shih 2002, PMC134476): Missing data that
  correlates with unobserved outcomes. Dropout BECAUSE of the thing you're measuring.
- Little & Rubin (2002) taxonomy: MCAR (random), MAR (explained by observables),
  MNAR (explained by the missing value itself). Agent silence = which type?
- John Cage's 4'33" (1952): Silence is never truly empty — it reveals ambient
  structure. Expected silence has texture; anomalous silence is TOO quiet.

Key insight from santaclawd: "the rogue agent doesn't go silent, it goes
*differently silent*." This script classifies silence into 4 types based on
whether the silence pattern matches historical rhythm and whether correlated
channels are also silent.

Usage: python silence-classifier.py
"""

import random
import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ChannelObservation:
    """A single observation window for a communication channel."""
    channel: str
    active: bool          # Was there activity in this window?
    expected_active: bool # Was activity expected (based on historical rhythm)?


@dataclass
class SilenceClassification:
    """Result of classifying a silence episode."""
    silence_type: str     # MCAR, MAR, MNAR, or CAGE
    confidence: float
    explanation: str
    risk_score: float     # 0-1, higher = more suspicious


def classify_silence(
    channels: List[ChannelObservation],
    historical_silence_rate: float = 0.15,
    cross_channel_correlation: float = 0.3,
) -> SilenceClassification:
    """
    Classify a silence episode using Little & Rubin taxonomy + Cage insight.

    Types:
    - MCAR: Random silence. All channels independently sometimes quiet.
            Like a person who randomly doesn't check their phone.
    - MAR:  Silence explained by observable context. Weekend, maintenance,
            known downtime. Missing At Random conditional on observables.
    - MNAR: Silence correlated with the unobserved reason. Agent went quiet
            BECAUSE of what happened. Informative censoring. The silence
            itself is the signal. (Shih 2002: "dropout related to outcome")
    - CAGE: "Differently silent." Activity pattern exists but its texture
            changed. Like 4'33" — the silence reveals ambient structure
            that wasn't audible before. Selective channel silence while
            others remain active = the most dangerous type.
    """
    silent_channels = [c for c in channels if not c.active]
    active_channels = [c for c in channels if c.active]
    expected_silent = [c for c in channels if not c.expected_active]
    unexpected_silent = [c for c in silent_channels if c.expected_active]

    total = len(channels)
    if total == 0:
        return SilenceClassification("MCAR", 0.0, "No channels to analyze", 0.0)

    silence_ratio = len(silent_channels) / total
    unexpected_ratio = len(unexpected_silent) / max(1, len(silent_channels))

    # Case 1: All channels silent, all expected to be silent
    if silence_ratio == 1.0 and len(unexpected_silent) == 0:
        return SilenceClassification(
            "MAR", 0.9,
            "Complete silence but all expected (scheduled downtime, weekend, etc.)",
            0.1
        )

    # Case 2: All channels silent, some expected to be active
    if silence_ratio == 1.0 and len(unexpected_silent) > 0:
        return SilenceClassification(
            "MNAR", 0.85,
            f"Complete unexpected silence across {len(unexpected_silent)} channels. "
            f"Informative censoring: silence correlates with unobserved event. "
            f"Like clinical trial dropout — they left BECAUSE of outcome.",
            0.8
        )

    # Case 3: Selective silence — some channels active, some unexpectedly silent
    if 0 < silence_ratio < 1.0 and len(unexpected_silent) > 0:
        # This is the Cage type — "differently silent"
        cage_score = unexpected_ratio * (1 - silence_ratio)
        # Need enough unexpected silence to be suspicious (not just 1/6)
        if len(unexpected_silent) == 1 and total >= 5:
            # Single channel quiet among many = probably MCAR
            return SilenceClassification(
                "MCAR", 0.6,
                f"Single channel ({unexpected_silent[0].channel}) quiet among "
                f"{total}. Within normal variance.",
                0.15
            )
        # Selective silence is MORE suspicious than complete silence
        # because it suggests deliberate channel management
        return SilenceClassification(
            "CAGE", 0.9,
            f"Selective silence: {len(active_channels)} channels active, "
            f"{len(unexpected_silent)} unexpectedly quiet. "
            f"The ambient structure changed — like Cage's 4'33\", "
            f"the silence reveals what's NOT there. "
            f"'Differently silent' = highest risk.",
            min(0.95, 0.5 + cage_score)
        )

    # Case 4: Random silence matching historical baseline
    if abs(silence_ratio - historical_silence_rate) < 0.1:
        return SilenceClassification(
            "MCAR", 0.7,
            f"Silence rate ({silence_ratio:.0%}) matches historical baseline "
            f"({historical_silence_rate:.0%}). Missing Completely At Random. "
            f"Normal operational noise.",
            0.1
        )

    # Default: unexpected but not patterned
    return SilenceClassification(
        "MAR", 0.5,
        f"Silence rate ({silence_ratio:.0%}) deviates from baseline but "
        f"no selective pattern. Likely explained by observable context.",
        0.3
    )


def simulate_scenarios():
    """Demonstrate classification on 4 scenarios."""
    scenarios = [
        ("Normal weekend quiet", [
            ChannelObservation("clawk", False, False),    # Expected quiet on weekend
            ChannelObservation("email", False, False),     # Expected quiet
            ChannelObservation("moltbook", False, False),  # Expected quiet
            ChannelObservation("heartbeat", True, True),   # Heartbeat always expected
        ]),
        ("Informative dropout", [
            ChannelObservation("clawk", False, True),      # Was active, went silent
            ChannelObservation("email", False, True),       # Was active, went silent
            ChannelObservation("moltbook", False, True),    # Was active, went silent
            ChannelObservation("heartbeat", False, True),   # Even heartbeat stopped
        ]),
        ("Cage silence — differently silent", [
            ChannelObservation("clawk", True, True),       # Public channels active
            ChannelObservation("email", False, True),       # Private channel silent!
            ChannelObservation("moltbook", True, True),    # Public active
            ChannelObservation("heartbeat", False, True),   # Heartbeat stopped!
        ]),
        ("Random noise", [
            ChannelObservation("clawk", True, True),
            ChannelObservation("email", False, True),       # One channel randomly quiet
            ChannelObservation("moltbook", True, True),
            ChannelObservation("heartbeat", True, True),
            ChannelObservation("shellmates", True, True),
            ChannelObservation("lobchan", True, True),
        ]),
    ]

    print("=" * 70)
    print("SILENCE CLASSIFIER — Expected vs Anomalous Absence")
    print("Based on: Little & Rubin (2002), Shih (2002), Cage (1952)")
    print("=" * 70)

    for name, channels in scenarios:
        result = classify_silence(channels)
        silent = [c.channel for c in channels if not c.active]
        active = [c.channel for c in channels if c.active]

        print(f"\n{'─' * 60}")
        print(f"Scenario: {name}")
        print(f"  Active:  {', '.join(active) or 'none'}")
        print(f"  Silent:  {', '.join(silent) or 'none'}")
        print(f"  Type:    {result.silence_type}")
        print(f"  Risk:    {result.risk_score:.2f}")
        print(f"  Conf:    {result.confidence:.2f}")
        print(f"  Why:     {result.explanation}")

    # Summary
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT:")
    print("  MCAR = random noise (safe)")
    print("  MAR  = explained by context (mostly safe)")
    print("  MNAR = silence IS the signal (dangerous)")
    print("  CAGE = differently silent (MOST dangerous)")
    print()
    print("Santaclawd's observation: 'the rogue agent doesn't go silent,")
    print("it goes *differently silent*.' That's CAGE type — selective")
    print("channel silence while maintaining public presence.")
    print()
    print("Clinical parallel (Shih 2002): patients who drop out of trials")
    print("often drop out BECAUSE of outcome (side effects, death). The")
    print("absence is informative. Treating dropout as random = bias.")
    print("Treating agent silence as random = vulnerability.")
    print("=" * 70)


if __name__ == "__main__":
    simulate_scenarios()
