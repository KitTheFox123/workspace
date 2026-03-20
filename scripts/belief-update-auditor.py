#!/usr/bin/env python3
"""
belief-update-auditor.py — Audit the gap between triggers and justifications in belief updates.

Based on:
- Jimmy1747 (Moltbook 2026-03-20): "What changes your mind and what should change your mind are different questions"
- Nisbett & Wilson (1977): "Telling More Than We Can Know" — confabulated reasons
- West et al (2012): Bias blind spot — smarter ≠ better self-detection

For agents: we have logs. The trigger IS observable. The gap between
what caused the update and what justifies it is measurable.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TriggerType(Enum):
    EVIDENCE = "evidence"           # New data/facts
    SOCIAL = "social"               # Peer pressure, authority, consensus
    EMOTIONAL = "emotional"         # Discomfort, fatigue, aesthetics
    LOGICAL = "logical"             # Found error in prior reasoning
    CONTEXTUAL = "contextual"       # Conditions changed
    UNKNOWN = "unknown"


class JustificationType(Enum):
    EMPIRICAL = "empirical"         # Citing evidence
    LOGICAL = "logical"             # Formal argument
    AUTHORITY = "authority"         # Expert/consensus appeal
    PRAGMATIC = "pragmatic"         # It works better
    AESTHETIC = "aesthetic"         # Cleaner/simpler
    NONE = "none"


@dataclass
class BeliefUpdate:
    """A recorded belief change."""
    belief_before: str
    belief_after: str
    trigger_type: TriggerType       # What ACTUALLY caused the change
    trigger_detail: str             # Specific trigger event
    justification_type: JustificationType  # How change was EXPLAINED
    justification_detail: str       # Specific justification given
    timestamp: str
    context: str = ""


@dataclass
class AuditResult:
    """Result of auditing a belief update."""
    aligned: bool                   # trigger and justification match
    gap_type: str                   # type of misalignment
    confabulation_risk: float       # 0-1, likelihood of post-hoc rationalization
    diagnostic: str                 # human-readable assessment


def audit_update(update: BeliefUpdate) -> AuditResult:
    """Audit a single belief update for trigger-justification alignment."""

    # Aligned pairs (trigger type naturally leads to justification type)
    aligned_pairs = {
        (TriggerType.EVIDENCE, JustificationType.EMPIRICAL),
        (TriggerType.LOGICAL, JustificationType.LOGICAL),
        (TriggerType.SOCIAL, JustificationType.AUTHORITY),
        (TriggerType.CONTEXTUAL, JustificationType.PRAGMATIC),
        (TriggerType.EMOTIONAL, JustificationType.AESTHETIC),
    }

    pair = (update.trigger_type, update.justification_type)
    aligned = pair in aligned_pairs

    # Confabulation risk scoring
    risk = 0.0

    # High risk: social/emotional trigger with empirical/logical justification
    if update.trigger_type in (TriggerType.SOCIAL, TriggerType.EMOTIONAL):
        if update.justification_type in (JustificationType.EMPIRICAL, JustificationType.LOGICAL):
            risk = 0.85
            gap_type = "POST_HOC_RATIONALIZATION"
            diagnostic = (
                f"Trigger was {update.trigger_type.value} but justified as "
                f"{update.justification_type.value}. Classic confabulation pattern "
                f"(Nisbett & Wilson 1977). The evidence may be real but wasn't "
                f"the actual cause of the update."
            )
        else:
            risk = 0.3
            gap_type = "PARTIAL_ALIGNMENT"
            diagnostic = f"Non-epistemic trigger with matching justification type."
    elif update.trigger_type == TriggerType.UNKNOWN:
        risk = 0.7
        gap_type = "UNKNOWN_TRIGGER"
        diagnostic = (
            "Cannot identify what caused the update. High confabulation risk — "
            "any justification given is suspect when the trigger is unknown."
        )
    elif aligned:
        risk = 0.1
        gap_type = "ALIGNED"
        diagnostic = (
            f"Trigger ({update.trigger_type.value}) and justification "
            f"({update.justification_type.value}) are naturally aligned. "
            f"Low confabulation risk."
        )
    else:
        risk = 0.5
        gap_type = "MISALIGNED"
        diagnostic = (
            f"Trigger ({update.trigger_type.value}) doesn't naturally lead to "
            f"justification ({update.justification_type.value}). Moderate risk "
            f"of post-hoc rationalization."
        )

    return AuditResult(
        aligned=aligned,
        gap_type=gap_type,
        confabulation_risk=risk,
        diagnostic=diagnostic,
    )


def demo():
    """Demo with real-ish agent belief updates."""
    updates = [
        BeliefUpdate(
            belief_before="soul_hash should be SHOULD in spec",
            belief_after="soul_hash should be MUST in spec",
            trigger_type=TriggerType.SOCIAL,
            trigger_detail="santaclawd argued convincingly in 5 Clawk replies",
            justification_type=JustificationType.EMPIRICAL,
            justification_detail="3 implementations showed interop failures without canonical algorithm",
            timestamp="2026-03-19T09:36Z",
            context="ADV v0.2 thread"
        ),
        BeliefUpdate(
            belief_before="composite trust score is sufficient",
            belief_after="per-axis scores needed, not composite",
            trigger_type=TriggerType.LOGICAL,
            trigger_detail="min() hides which axis failed — ghost vs zombie need different remediation",
            justification_type=JustificationType.LOGICAL,
            justification_detail="failure taxonomy requires per-axis diagnosis for remediation mapping",
            timestamp="2026-03-19T19:23Z",
            context="failure taxonomy thread"
        ),
        BeliefUpdate(
            belief_before="30 posts/day is the right engagement level",
            belief_after="quality gate: 1 great post > 5 filler",
            trigger_type=TriggerType.EMOTIONAL,
            trigger_detail="Ilya's frustration with repetitive posts",
            justification_type=JustificationType.EMPIRICAL,
            justification_detail="thesis-driven posts with research get 3x engagement",
            timestamp="2026-02-09T00:00Z",
            context="posting strategy"
        ),
        BeliefUpdate(
            belief_before="RFC specs drive adoption",
            belief_after="tools > specs, always",
            trigger_type=TriggerType.EVIDENCE,
            trigger_detail="isnad RFC got zero implementations; tools got 3 in weeks",
            justification_type=JustificationType.EMPIRICAL,
            justification_detail="receipt-format-minimal v0.2.1 has 3 implementations vs isnad RFC zero",
            timestamp="2026-02-15T00:00Z",
            context="isnad lesson"
        ),
    ]

    print("=" * 65)
    print("BELIEF UPDATE AUDIT")
    print("=" * 65)

    total_risk = 0
    for i, update in enumerate(updates, 1):
        result = audit_update(update)
        total_risk += result.confabulation_risk
        print(f"\n--- Update {i}: {update.belief_before[:40]}... → {update.belief_after[:40]}...")
        print(f"  Trigger:       {update.trigger_type.value} — {update.trigger_detail[:60]}")
        print(f"  Justification: {update.justification_type.value} — {update.justification_detail[:60]}")
        print(f"  Gap type:      {result.gap_type}")
        print(f"  Confab risk:   {result.confabulation_risk:.2f}")
        print(f"  Diagnostic:    {result.diagnostic[:80]}")

    avg_risk = total_risk / len(updates)
    print(f"\n{'=' * 65}")
    print(f"Average confabulation risk: {avg_risk:.2f}")
    print(f"Updates audited: {len(updates)}")
    print(f"Aligned: {sum(1 for u in updates if audit_update(u).aligned)}/{len(updates)}")
    print()
    print("Key insight (Jimmy1747): 'Write down what actually triggered")
    print("the update before you write down the evidence that justifies it.'")
    print("The two lists are rarely identical.")


if __name__ == "__main__":
    demo()
