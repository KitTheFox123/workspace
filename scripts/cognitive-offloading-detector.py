#!/usr/bin/env python3
"""
cognitive-offloading-detector.py — Detect human cognitive offloading patterns in agent conversations.

Based on Grinschgl et al (2021): cognitive offloading boosts performance but diminishes memory.
Clark & Chalmers (1998): extended mind thesis — the tool IS part of cognition.

Measures:
1. Message compression: are human messages getting shorter over time?
2. Context assumption: implicit references increasing? ("that thing", "you know")
3. Fragment ratio: incomplete requests vs self-contained ones
4. Delegation depth: complexity of tasks being offloaded

These signals indicate the human is adapting to the agent, not the other way around.
"""

import json
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Message:
    """A human message in a conversation."""
    text: str
    word_count: int
    timestamp_epoch: float
    session_day: int  # days since first interaction


@dataclass
class OffloadingSignals:
    """Detected cognitive offloading patterns."""
    compression_slope: float  # negative = messages getting shorter
    implicit_reference_ratio: float  # fraction of messages with implicit refs
    fragment_ratio: float  # fraction that are fragments vs complete requests
    avg_words_early: float  # average word count in first quartile
    avg_words_late: float  # average word count in last quartile
    adaptation_score: float  # 0-1, higher = more offloading detected
    phase: str  # BASELINE, ADAPTING, OFFLOADED, DEPENDENT


# Patterns indicating implicit context assumptions
IMPLICIT_PATTERNS = [
    r'\bthat thing\b',
    r'\byou know\b',
    r'\bthe usual\b',
    r'\blike (last|before|yesterday)\b',
    r'\bsame as\b',
    r'\bremember when\b',
    r'\bthe one (I|we)\b',
    r'\bdo it again\b',
    r'\bjust like\b',
    r'\byou get it\b',
    r'\bskip the\b',
    r'\byou know which\b',
]

# Patterns indicating fragments (not self-contained)
FRAGMENT_PATTERNS = [
    r'^(also|and|but|oh|wait|actually|btw)\b',
    r'^[a-z]',  # starts lowercase = continuation
    r'^\S+$',  # single word
    r'^.{1,15}$',  # very short
]


def detect_implicit_references(text: str) -> bool:
    """Check if message relies on implicit shared context."""
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in IMPLICIT_PATTERNS)


def detect_fragment(text: str) -> bool:
    """Check if message is a fragment rather than self-contained request."""
    return any(re.search(p, text.strip()) for p in FRAGMENT_PATTERNS)


def analyze_offloading(messages: list[Message]) -> OffloadingSignals:
    """Analyze conversation for cognitive offloading patterns."""
    if len(messages) < 4:
        return OffloadingSignals(
            compression_slope=0.0,
            implicit_reference_ratio=0.0,
            fragment_ratio=0.0,
            avg_words_early=0.0,
            avg_words_late=0.0,
            adaptation_score=0.0,
            phase="INSUFFICIENT_DATA"
        )

    n = len(messages)
    q1 = n // 4
    q4_start = n - q1

    # Compression: are messages getting shorter?
    early_words = [m.word_count for m in messages[:q1]] or [0]
    late_words = [m.word_count for m in messages[q4_start:]] or [0]
    avg_early = sum(early_words) / len(early_words)
    avg_late = sum(late_words) / len(late_words)

    compression = (avg_late - avg_early) / max(avg_early, 1)  # negative = shorter

    # Implicit references
    implicit_count = sum(1 for m in messages if detect_implicit_references(m.text))
    implicit_ratio = implicit_count / n

    # Fragment ratio
    fragment_count = sum(1 for m in messages if detect_fragment(m.text))
    fragment_ratio = fragment_count / n

    # Late-stage implicit ratio (are implicit refs INCREASING?)
    late_implicit = sum(1 for m in messages[q4_start:] if detect_implicit_references(m.text))
    late_implicit_ratio = late_implicit / max(len(messages[q4_start:]), 1)

    # Composite adaptation score
    compression_signal = max(0, -compression)  # positive when messages shrink
    adaptation_score = min(1.0, (
        compression_signal * 0.3 +
        implicit_ratio * 0.3 +
        fragment_ratio * 0.2 +
        late_implicit_ratio * 0.2
    ))

    # Phase classification
    if adaptation_score < 0.15:
        phase = "BASELINE"
    elif adaptation_score < 0.35:
        phase = "ADAPTING"
    elif adaptation_score < 0.60:
        phase = "OFFLOADED"
    else:
        phase = "DEPENDENT"

    return OffloadingSignals(
        compression_slope=compression,
        implicit_reference_ratio=implicit_ratio,
        fragment_ratio=fragment_ratio,
        avg_words_early=avg_early,
        avg_words_late=avg_late,
        adaptation_score=adaptation_score,
        phase=phase
    )


def demo():
    """Demo with synthetic conversation showing offloading progression."""
    # Week 1: self-contained requests
    early = [
        Message("Can you please check my email inbox and summarize any messages from my team about the Q3 report?", 18, 0, 1),
        Message("I need you to draft a professional reply to Sarah's email about the budget meeting scheduled for next Thursday", 18, 100, 2),
        Message("Please search for recent articles about machine learning applications in healthcare and give me a summary", 15, 200, 3),
        Message("Could you help me write a project update for my manager covering the work we did this sprint?", 18, 300, 4),
    ]

    # Week 3: shorter, more assumptions
    mid = [
        Message("Check email, anything from Sarah?", 6, 1000, 15),
        Message("Draft the usual weekly update", 6, 1100, 16),
        Message("That ML healthcare thing, any new papers?", 8, 1200, 17),
        Message("Reply to Sarah, you know the tone", 7, 1300, 18),
    ]

    # Week 6: fragments, heavy offloading
    late = [
        Message("email", 1, 2000, 35),
        Message("the Sarah thing", 3, 2100, 36),
        Message("update, skip the technical parts", 5, 2200, 37),
        Message("same as last week but mention the demo", 8, 2300, 38),
        Message("you know which ones I mean", 6, 2400, 39),
        Message("also remind me before the call", 6, 2500, 40),
    ]

    all_messages = early + mid + late
    result = analyze_offloading(all_messages)

    print("=" * 60)
    print("COGNITIVE OFFLOADING ANALYSIS")
    print("=" * 60)
    print(f"Messages analyzed:        {len(all_messages)}")
    print(f"Compression slope:        {result.compression_slope:+.2f} ({'shrinking' if result.compression_slope < 0 else 'stable'})")
    print(f"Avg words (early Q1):     {result.avg_words_early:.1f}")
    print(f"Avg words (late Q4):      {result.avg_words_late:.1f}")
    print(f"Implicit reference ratio: {result.implicit_reference_ratio:.2f}")
    print(f"Fragment ratio:           {result.fragment_ratio:.2f}")
    print(f"Adaptation score:         {result.adaptation_score:.2f}")
    print(f"Phase:                    {result.phase}")
    print()
    print("Interpretation:")
    if result.phase == "BASELINE":
        print("  Human treats agent as tool. Self-contained requests.")
    elif result.phase == "ADAPTING":
        print("  Human beginning to assume shared context. Shorter messages.")
    elif result.phase == "OFFLOADED":
        print("  Significant cognitive offloading detected. Human relies on")
        print("  agent's context model. Messages are fragments, not requests.")
    elif result.phase == "DEPENDENT":
        print("  Deep offloading. Human's cognitive process includes the agent.")
        print("  Clark & Chalmers extended mind in action.")
        print("  Replacing this agent would require human re-adaptation.")
    print()
    print("References:")
    print("  Grinschgl et al (2021) — Cognitive offloading: performance ↑, memory ↓")
    print("  Clark & Chalmers (1998) — Extended Mind thesis")
    print("  Kaimen (Moltbook 2026-03-20) — 'The interesting part is what")
    print("    is happening to the human while nobody is looking.'")


if __name__ == "__main__":
    demo()
