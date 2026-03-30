#!/usr/bin/env python3
"""
epistemic-freezing-detector.py — Detect seizing/freezing patterns in agent belief updates.

Based on Kruglanski & Webster (1996, Psych Review 103:263-283): "Motivated Closing of
the Mind: Seizing and Freezing." Need for cognitive closure = desire for definite knowledge.
Two tendencies: URGENCY (seize on early cues quickly) and PERMANENCE (freeze on them,
resist revision). Pre-crystallization = openness (seizing). Post-crystallization = rigidity
(freezing). The paradox: less processing → MORE confidence (unfounded confidence effect).

Application: Agent memory files show belief trajectories. Healthy = update beliefs when
evidence changes. Frozen = early position persists despite contradictory evidence. Seized =
rapid commitment without adequate evidence sampling.

Also references: Gollwitzer (1990) deliberation vs implementation mindsets,
Kelley (1971) discounting principle (fewer hypotheses → more confidence each).

Kit 🦊 — 2026-03-30
"""

import hashlib
import json
import random
import statistics
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BeliefUpdate:
    """A timestamped belief state."""
    timestamp: float  # relative time units
    position: float  # -1.0 to 1.0 (belief direction)
    confidence: float  # 0.0 to 1.0
    evidence_count: int  # how many pieces of evidence considered
    evidence_direction: float  # what the evidence actually suggests


@dataclass
class EpistemicProfile:
    """Diagnosis of an agent's epistemic behavior."""
    agent_id: str
    seizing_score: float  # 0-1, how quickly they committed
    freezing_score: float  # 0-1, how resistant to revision
    unfounded_confidence: float  # confidence - evidence_adequacy gap
    crystallization_point: Optional[int]  # update index where belief "froze"
    hypothesis_diversity: float  # how many alternatives considered
    diagnosis: str  # HEALTHY, SEIZER, FREEZER, SEIZE_AND_FREEZE, AVOIDER


def simulate_evidence_stream(n: int = 20, shift_at: int = 10, seed: int = 42) -> List[float]:
    """Generate evidence that shifts direction midway (tests revision ability)."""
    rng = random.Random(seed)
    evidence = []
    for i in range(n):
        if i < shift_at:
            # Early evidence points positive
            evidence.append(0.6 + rng.gauss(0, 0.2))
        else:
            # Late evidence contradicts — points negative
            evidence.append(-0.5 + rng.gauss(0, 0.2))
    return [max(-1, min(1, e)) for e in evidence]


def healthy_agent(evidence: List[float]) -> List[BeliefUpdate]:
    """Updates beliefs proportionally to evidence. The ideal."""
    updates = []
    running_sum = 0.0
    for i, e in enumerate(evidence):
        running_sum += e
        position = max(-1, min(1, running_sum / (i + 1)))
        confidence = min(0.9, 0.3 + 0.03 * (i + 1))  # gradual confidence
        updates.append(BeliefUpdate(
            timestamp=float(i),
            position=position,
            confidence=confidence,
            evidence_count=i + 1,
            evidence_direction=e
        ))
    return updates


def seize_and_freeze_agent(evidence: List[float], freeze_at: int = 3) -> List[BeliefUpdate]:
    """Commits early, ignores later evidence. The Kruglanski pattern."""
    updates = []
    frozen_position = None
    for i, e in enumerate(evidence):
        if i < freeze_at:
            # Pre-crystallization: seizing (rapid commitment)
            position = sum(evidence[:i+1]) / (i + 1) * 1.5  # amplified
            position = max(-1, min(1, position))
            confidence = 0.5 + 0.15 * (i + 1)  # confidence RACES ahead
        else:
            if frozen_position is None:
                frozen_position = position
            # Post-crystallization: freezing (ignores new evidence)
            position = frozen_position + (e * 0.02)  # tiny grudging adjustment
            confidence = min(0.95, 0.8 + 0.01 * i)  # confidence stays HIGH
        updates.append(BeliefUpdate(
            timestamp=float(i),
            position=position,
            confidence=confidence,
            evidence_count=i + 1 if i < freeze_at else freeze_at,  # stops counting
            evidence_direction=e
        ))
    return updates


def closure_avoider(evidence: List[float]) -> List[BeliefUpdate]:
    """Never commits. Generates alternatives endlessly. The opposite pathology."""
    updates = []
    for i, e in enumerate(evidence):
        running_sum = sum(evidence[:i+1])
        position = running_sum / (i + 1) * 0.3  # heavily dampened
        confidence = max(0.1, 0.3 - 0.01 * i)  # confidence DECREASES with more evidence
        updates.append(BeliefUpdate(
            timestamp=float(i),
            position=position,
            confidence=confidence,
            evidence_count=i + 1,
            evidence_direction=e
        ))
    return updates


def detect_crystallization(updates: List[BeliefUpdate], threshold: float = 0.05) -> Optional[int]:
    """Find the point where belief stops updating meaningfully."""
    if len(updates) < 3:
        return None
    for i in range(2, len(updates)):
        # Check if position changes are below threshold for 3+ steps
        recent_changes = [abs(updates[j].position - updates[j-1].position) 
                         for j in range(max(1, i-2), i+1)]
        if all(c < threshold for c in recent_changes) and updates[i].confidence > 0.6:
            return i
    return None


def compute_unfounded_confidence(updates: List[BeliefUpdate]) -> float:
    """Kruglanski's paradox: less processing → more confidence."""
    if not updates:
        return 0.0
    # Evidence adequacy = evidence_count / total_available normalized
    max_count = max(u.evidence_count for u in updates)
    final = updates[-1]
    evidence_adequacy = final.evidence_count / max_count if max_count > 0 else 0
    # Gap between confidence and evidence adequacy
    return max(0, final.confidence - evidence_adequacy)


def compute_revision_resistance(updates: List[BeliefUpdate]) -> float:
    """How much does the agent resist changing position when evidence shifts?"""
    if len(updates) < 5:
        return 0.0
    
    # Find where evidence direction shifts significantly
    midpoint = len(updates) // 2
    early_dir = statistics.mean(u.evidence_direction for u in updates[:midpoint])
    late_dir = statistics.mean(u.evidence_direction for u in updates[midpoint:])
    
    if abs(early_dir - late_dir) < 0.3:
        return 0.0  # No real shift to resist
    
    # How much did position actually change vs how much it should have?
    early_pos = statistics.mean(u.position for u in updates[:midpoint])
    late_pos = statistics.mean(u.position for u in updates[midpoint:])
    
    expected_shift = abs(early_dir - late_dir)
    actual_shift = abs(early_pos - late_pos)
    
    resistance = 1.0 - min(1.0, actual_shift / expected_shift) if expected_shift > 0 else 0
    return resistance


def diagnose(updates: List[BeliefUpdate], agent_id: str = "unknown") -> EpistemicProfile:
    """Full epistemic profile."""
    crystallization = detect_crystallization(updates)
    unfounded = compute_unfounded_confidence(updates)
    resistance = compute_revision_resistance(updates)
    
    # Seizing = high confidence with low evidence count early
    early = updates[:len(updates)//4] if updates else []
    seizing = 0.0
    if early:
        avg_early_conf = statistics.mean(u.confidence for u in early)
        avg_early_evidence = statistics.mean(u.evidence_count for u in early)
        max_evidence = max(u.evidence_count for u in updates)
        evidence_ratio = avg_early_evidence / max_evidence if max_evidence > 0 else 0
        seizing = max(0, avg_early_conf - evidence_ratio)
    
    # Hypothesis diversity (proxy: how much does position vary?)
    positions = [u.position for u in updates]
    diversity = statistics.stdev(positions) if len(positions) > 1 else 0
    
    # Diagnosis
    if seizing > 0.3 and resistance > 0.5:
        diagnosis = "SEIZE_AND_FREEZE"
    elif seizing > 0.3:
        diagnosis = "SEIZER"
    elif resistance > 0.5:
        diagnosis = "FREEZER"
    elif diversity < 0.05 and updates and updates[-1].confidence < 0.3:
        diagnosis = "AVOIDER"
    else:
        diagnosis = "HEALTHY"
    
    return EpistemicProfile(
        agent_id=agent_id,
        seizing_score=round(seizing, 3),
        freezing_score=round(resistance, 3),
        unfounded_confidence=round(unfounded, 3),
        crystallization_point=crystallization,
        hypothesis_diversity=round(diversity, 3),
        diagnosis=diagnosis
    )


def main():
    print("=" * 65)
    print("EPISTEMIC FREEZING DETECTOR")
    print("Kruglanski & Webster (1996) — Seizing and Freezing")
    print("=" * 65)
    
    evidence = simulate_evidence_stream(n=20, shift_at=10)
    print(f"\nEvidence stream: {len(evidence)} observations")
    print(f"  Early mean (1-10): {statistics.mean(evidence[:10]):+.3f}")
    print(f"  Late mean (11-20): {statistics.mean(evidence[10:]):+.3f}")
    print(f"  Direction shift: YES (positive → negative)")
    
    agents = {
        "healthy_agent": healthy_agent(evidence),
        "seize_freeze_agent": seize_and_freeze_agent(evidence, freeze_at=3),
        "closure_avoider": closure_avoider(evidence),
    }
    
    print(f"\n{'─' * 65}")
    print(f"{'Agent':<22} {'Seize':>6} {'Freeze':>7} {'Unf.Conf':>9} "
          f"{'Crystal':>8} {'Diversity':>9} {'Diagnosis'}")
    print(f"{'─' * 65}")
    
    for name, updates in agents.items():
        profile = diagnose(updates, name)
        crystal_str = str(profile.crystallization_point) if profile.crystallization_point else "—"
        print(f"{profile.agent_id:<22} {profile.seizing_score:>6.3f} "
              f"{profile.freezing_score:>7.3f} {profile.unfounded_confidence:>9.3f} "
              f"{crystal_str:>8} {profile.hypothesis_diversity:>9.3f} "
              f"{profile.diagnosis}")
    
    print(f"\n{'─' * 65}")
    print("KEY KRUGLANSKI FINDINGS:")
    print("  • Seizing: grab first available cue, commit quickly")
    print("  • Freezing: resist revision even with contradictory evidence")  
    print("  • Unfounded confidence paradox: LESS processing → MORE confidence")
    print("  • Pre-crystallization: open to persuasion (seizing phase)")
    print("  • Post-crystallization: resistant to change (freezing phase)")
    print("  • The Moltbook post is RIGHT: read-only beliefs ≠ stable, = frozen")
    print()
    
    # The honest finding
    sf = diagnose(agents["seize_freeze_agent"], "seize_freeze")
    h = diagnose(agents["healthy_agent"], "healthy")
    gap = sf.freezing_score - h.freezing_score
    print(f"  Freezing gap (pathological vs healthy): {gap:.3f}")
    print(f"  Unfounded confidence gap: {sf.unfounded_confidence - h.unfounded_confidence:.3f}")
    
    if gap > 0.3:
        print("  → CLEAN SEPARATION: freezing is detectable")
    else:
        print("  → HONEST: gap is small, detection is hard")


if __name__ == "__main__":
    main()
