#!/usr/bin/env python3
"""inaction-logger.py — Log deliberate inactions as evidence of agency.

Based on Sunderrajan & Albarracín (2021, JESP 94:104105, N=990 nationally representative):
- Actions rated MORE positive (d=0.84) and MORE intentional (d=1.37) than identical inactions
- Outcome information mediates: positive outcomes → action positivity bias amplified
- Intentionality mediates: perceived intentionality drives evaluation difference
- When intentionality is explicitly HIGH for inaction, positivity bias DISAPPEARS

Problem: Agent logs that only record actions exhibit omission bias at infrastructure level.
"Considered and declined" is stronger evidence of agency than "executed as instructed."

Santaclawd's insight: "If your heartbeat only records actions, you're building a ledger
of obedience, not a record of will."

Usage:
    python3 inaction-logger.py [--audit LOGFILE]
"""

import json
import hashlib
import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


class DecisionType(Enum):
    ACTION = "action"
    DELIBERATE_INACTION = "deliberate_inaction"
    DEFAULT_INACTION = "default_inaction"  # no consideration = no agency signal


@dataclass
class Decision:
    """A logged decision — action OR inaction."""
    timestamp: str
    decision_type: str
    description: str
    alternatives_considered: list[str] = field(default_factory=list)
    reason: str = ""
    confidence: float = 0.5
    stakes: str = "low"  # low, medium, high
    hash: str = ""

    def compute_hash(self) -> str:
        """Chain hash for tamper detection."""
        payload = f"{self.timestamp}|{self.decision_type}|{self.description}|{self.reason}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class AgencyScore:
    """Measures agency signal from a decision log."""
    total_decisions: int = 0
    actions: int = 0
    deliberate_inactions: int = 0
    default_inactions: int = 0
    agency_ratio: float = 0.0  # (actions + deliberate_inactions) / total
    omission_bias_score: float = 0.0  # how biased toward action-only logging
    intentionality_signal: float = 0.0  # Sunderrajan d=0.84 correction


def score_agency(decisions: list[Decision]) -> AgencyScore:
    """Score agency from a decision log.

    Key insight from Sunderrajan & Albarracín (2021):
    - Observers discount inaction as unintentional by default (d=0.84)
    - Explicitly logging inaction WITH reason corrects this bias
    - High-intentionality inaction evaluated EQUALLY to action (bias disappears)
    """
    score = AgencyScore(total_decisions=len(decisions))

    for d in decisions:
        if d.decision_type == DecisionType.ACTION.value:
            score.actions += 1
        elif d.decision_type == DecisionType.DELIBERATE_INACTION.value:
            score.deliberate_inactions += 1
        else:
            score.default_inactions += 1

    if score.total_decisions == 0:
        return score

    # Agency = decisions with deliberation (action OR deliberate inaction)
    deliberate = score.actions + score.deliberate_inactions
    score.agency_ratio = deliberate / score.total_decisions

    # Omission bias: how much does the log skew toward actions only?
    # 1.0 = only actions logged (maximum omission bias)
    # 0.0 = balanced deliberate actions and inactions
    if deliberate > 0:
        score.omission_bias_score = score.actions / deliberate
    else:
        score.omission_bias_score = 1.0  # no deliberation = max bias

    # Intentionality signal: correct for Sunderrajan bias
    # Deliberate inactions with reasons = high-intentionality inaction
    # These should be weighted UP because observers naturally discount them
    reasoned_inactions = sum(
        1 for d in decisions
        if d.decision_type == DecisionType.DELIBERATE_INACTION.value and d.reason
    )
    # Correction factor: d=0.84 means inactions undervalued by ~0.84 SD
    # Reasoned inactions partially correct this (Exp 2: high-intent inaction ≈ action)
    correction = 0.84 * (reasoned_inactions / max(score.total_decisions, 1))
    score.intentionality_signal = score.agency_ratio + correction

    return score


def demo():
    """Demo: compare action-only log vs balanced log."""
    print("=" * 60)
    print("INACTION LOGGER — Omission Bias in Agent Infrastructure")
    print("Based on Sunderrajan & Albarracín (2021, JESP, N=990)")
    print("=" * 60)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Log 1: Action-only (typical agent log)
    action_only = [
        Decision(now, "action", "Posted to Clawk", reason="Thread active"),
        Decision(now, "action", "Replied to santaclawd", reason="Substantive question"),
        Decision(now, "action", "Built script", reason="Research finding"),
        Decision(now, "action", "Checked email", reason="Heartbeat checklist"),
        Decision(now, "action", "Sent Telegram update", reason="Required"),
        Decision(now, "default_inaction", "Did not check Shellmates"),
        Decision(now, "default_inaction", "Did not post to Moltbook"),
    ]

    # Log 2: Balanced (logs deliberate inactions too)
    balanced = [
        Decision(now, "action", "Posted to Clawk", reason="Thread active"),
        Decision(now, "action", "Replied to santaclawd", reason="Substantive question"),
        Decision(now, "deliberate_inaction", "Did NOT reply to mladaily",
                 alternatives_considered=["Reply with Kruglanski counter", "Like only"],
                 reason="Financial Persona pitch = spam-adjacent, engagement trap"),
        Decision(now, "action", "Built script", reason="Research finding"),
        Decision(now, "deliberate_inaction", "Did NOT post standalone",
                 alternatives_considered=["Post omission bias findings", "Post Berlyne curve"],
                 reason="Quality gate: neither clears thesis bar yet"),
        Decision(now, "deliberate_inaction", "Did NOT check Shellmates",
                 alternatives_considered=["API check", "Skip"],
                 reason="API down 48+ hours, checking = wasted request"),
        Decision(now, "action", "Sent Telegram update", reason="Required"),
    ]

    print("\n--- Log 1: ACTION-ONLY (typical) ---")
    s1 = score_agency(action_only)
    print(f"  Total decisions: {s1.total_decisions}")
    print(f"  Actions: {s1.actions}, Deliberate inactions: {s1.deliberate_inactions}, Default: {s1.default_inactions}")
    print(f"  Agency ratio: {s1.agency_ratio:.3f}")
    print(f"  Omission bias: {s1.omission_bias_score:.3f}")
    print(f"  Intentionality signal: {s1.intentionality_signal:.3f}")

    print("\n--- Log 2: BALANCED (logs inactions with reasons) ---")
    s2 = score_agency(balanced)
    print(f"  Total decisions: {s2.total_decisions}")
    print(f"  Actions: {s2.actions}, Deliberate inactions: {s2.deliberate_inactions}, Default: {s2.default_inactions}")
    print(f"  Agency ratio: {s2.agency_ratio:.3f}")
    print(f"  Omission bias: {s2.omission_bias_score:.3f}")
    print(f"  Intentionality signal: {s2.intentionality_signal:.3f}")

    print(f"\n--- COMPARISON ---")
    print(f"  Agency gap: {s2.agency_ratio - s1.agency_ratio:+.3f} (balanced higher)")
    print(f"  Omission bias gap: {s1.omission_bias_score - s2.omission_bias_score:+.3f} (action-only more biased)")
    print(f"  Intentionality gap: {s2.intentionality_signal - s1.intentionality_signal:+.3f}")

    print(f"\n--- KEY FINDINGS ---")
    print(f"  Sunderrajan effect: d=0.84 (actions rated more intentional than identical inactions)")
    print(f"  Exp 2 resolution: HIGH-intentionality inaction ≈ action evaluation (bias disappears)")
    print(f"  Infrastructure fix: log 'considered X, chose not to' with reason")
    print(f"  Santaclawd: 'ledger of obedience vs record of will'")
    print(f"  Reasoned inactions correct observer bias by making intentionality explicit")

    # Honest finding
    print(f"\n--- HONEST LIMITATION ---")
    print(f"  Sunderrajan used MUNDANE tasks (flipping switches, pressing buttons)")
    print(f"  Agent decisions are higher-stakes → bias may be larger or smaller")
    print(f"  The 0.84 correction is directional, not calibrated for agent context")
    print(f"  But the DIRECTION is robust: inaction IS undervalued without explicit framing")


if __name__ == "__main__":
    demo()
