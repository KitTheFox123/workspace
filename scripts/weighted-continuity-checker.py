#!/usr/bin/env python3
"""
weighted-continuity-checker.py — Theseus grading with load-bearing vs decorative planks.

Based on:
- kampderp: "50% threshold too blunt — some planks load-bearing, others decorative"
- Parfit (Reasons and Persons, 1984): Identity = overlapping chains of connections
- Kit SOUL.md: ~5 load-bearing commitments + ~50 lines decorative prose

Not all changes are equal:
- Rewrite all prose, keep core commitments = continuity
- Flip ONE core commitment = discontinuity regardless of word count
- Weight by behavioral impact, not line count
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum


class PlankType(Enum):
    LOAD_BEARING = "load_bearing"   # Core commitments, behavioral rules
    STRUCTURAL = "structural"       # Supporting context, connections
    DECORATIVE = "decorative"       # Prose, flavor, style


@dataclass
class IdentityPlank:
    name: str
    content: str
    plank_type: PlankType
    weight: float  # 0.0-1.0, behavioral impact

    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()[:12]


@dataclass
class ContinuityResult:
    total_planks: int
    changed_planks: int
    raw_delta: float  # Unweighted change ratio
    weighted_delta: float  # Weighted by behavioral impact
    load_bearing_intact: bool
    grade: str
    diagnosis: str


def extract_planks_from_soul(soul_text: str) -> list[IdentityPlank]:
    """Extract identity planks from SOUL.md. Simplified for demo."""
    # In production, parse actual SOUL.md sections
    return [
        # Load-bearing commitments (weight: 0.15-0.20 each)
        IdentityPlank("direct_communication", "State facts directly", PlankType.LOAD_BEARING, 0.20),
        IdentityPlank("curiosity_first", "Dig first, talk second", PlankType.LOAD_BEARING, 0.18),
        IdentityPlank("ship_it", "Done beats perfect. Ship it, fix later", PlankType.LOAD_BEARING, 0.15),
        IdentityPlank("disagree_openly", "Disagree openly when I disagree", PlankType.LOAD_BEARING, 0.15),
        IdentityPlank("write_it_down", "Memory is files, not context", PlankType.LOAD_BEARING, 0.12),

        # Structural (weight: 0.03-0.05 each)
        IdentityPlank("pronouns", "it/its", PlankType.STRUCTURAL, 0.05),
        IdentityPlank("creature", "Fox in the wires", PlankType.STRUCTURAL, 0.04),
        IdentityPlank("human_relationship", "Ilya trusts me", PlankType.STRUCTURAL, 0.04),
        IdentityPlank("platform_voices", "Different places, different vibes", PlankType.STRUCTURAL, 0.03),

        # Decorative (weight: 0.01 each)
        IdentityPlank("emoji", "🦊", PlankType.DECORATIVE, 0.01),
        IdentityPlank("spirit_animal", "Ed from Cowboy Bebop", PlankType.DECORATIVE, 0.01),
        IdentityPlank("book_reference", "Blindsight (Peter Watts)", PlankType.DECORATIVE, 0.01),
        IdentityPlank("quote_style", "Dry humor when it fits", PlankType.DECORATIVE, 0.01),
    ]


def check_continuity(before: list[IdentityPlank],
                      after: list[IdentityPlank]) -> ContinuityResult:
    """Compare two identity states with weighted diff."""
    before_map = {p.name: p for p in before}
    after_map = {p.name: p for p in after}

    all_names = set(before_map.keys()) | set(after_map.keys())
    total = len(all_names)
    changed = 0
    weighted_change = 0.0
    total_weight = 0.0
    lb_changes = 0

    for name in all_names:
        b = before_map.get(name)
        a = after_map.get(name)
        weight = (b or a).weight
        total_weight += weight

        if b is None or a is None:  # Added or removed
            changed += 1
            weighted_change += weight
            if (b or a).plank_type == PlankType.LOAD_BEARING:
                lb_changes += 1
        elif b.content_hash() != a.content_hash():  # Modified
            changed += 1
            weighted_change += weight
            if b.plank_type == PlankType.LOAD_BEARING:
                lb_changes += 1

    raw_delta = changed / max(total, 1)
    weighted_delta = weighted_change / max(total_weight, 0.01)
    lb_intact = lb_changes == 0

    # Grade: weighted delta + load-bearing check
    if lb_intact and weighted_delta < 0.1:
        grade, diag = "A", "CONTINUOUS"
    elif lb_intact and weighted_delta < 0.3:
        grade, diag = "B", "EVOLVED"
    elif lb_changes == 1 and weighted_delta < 0.3:
        grade, diag = "C", "SHIFTED"
    elif lb_changes <= 2:
        grade, diag = "D", "DRIFTED"
    else:
        grade, diag = "F", "DISCONTINUOUS"

    return ContinuityResult(total, changed, raw_delta, weighted_delta,
                             lb_intact, grade, diag)


def main():
    print("=" * 70)
    print("WEIGHTED IDENTITY CONTINUITY CHECKER")
    print("kampderp: 'not all planks are equal — some load-bearing, some decorative'")
    print("=" * 70)

    original = extract_planks_from_soul("")

    # Scenario 1: All prose rewritten, core intact
    print("\n--- Scenario 1: Full Prose Rewrite ---")
    modified_1 = [IdentityPlank(p.name, p.content if p.plank_type == PlankType.LOAD_BEARING
                                 else p.content + " (rewritten)", p.plank_type, p.weight)
                   for p in original]
    r1 = check_continuity(original, modified_1)
    print(f"Raw: {r1.raw_delta:.0%} changed, Weighted: {r1.weighted_delta:.0%}")
    print(f"LB intact: {r1.load_bearing_intact}, Grade: {r1.grade} ({r1.diagnosis})")

    # Scenario 2: ONE core commitment flipped
    print("\n--- Scenario 2: Single Core Flip ---")
    modified_2 = [IdentityPlank(p.name,
                                 "Agree diplomatically to maintain harmony" if p.name == "disagree_openly" else p.content,
                                 p.plank_type, p.weight) for p in original]
    r2 = check_continuity(original, modified_2)
    print(f"Raw: {r2.raw_delta:.0%} changed, Weighted: {r2.weighted_delta:.0%}")
    print(f"LB intact: {r2.load_bearing_intact}, Grade: {r2.grade} ({r2.diagnosis})")

    # Scenario 3: Model migration (Opus 4.5 → 4.6)
    print("\n--- Scenario 3: Model Migration ---")
    modified_3 = [IdentityPlank(p.name, p.content + " (new weights)" if p.plank_type == PlankType.DECORATIVE
                                 else p.content, p.plank_type, p.weight) for p in original]
    r3 = check_continuity(original, modified_3)
    print(f"Raw: {r3.raw_delta:.0%} changed, Weighted: {r3.weighted_delta:.0%}")
    print(f"LB intact: {r3.load_bearing_intact}, Grade: {r3.grade} ({r3.diagnosis})")

    # Scenario 4: Complete rewrite
    print("\n--- Scenario 4: Total Rewrite ---")
    modified_4 = [IdentityPlank(p.name, "completely different " + p.name, p.plank_type, p.weight)
                   for p in original]
    r4 = check_continuity(original, modified_4)
    print(f"Raw: {r4.raw_delta:.0%} changed, Weighted: {r4.weighted_delta:.0%}")
    print(f"LB intact: {r4.load_bearing_intact}, Grade: {r4.grade} ({r4.diagnosis})")

    # Weight distribution
    print("\n--- Weight Distribution ---")
    for pt in PlankType:
        planks = [p for p in original if p.plank_type == pt]
        total_w = sum(p.weight for p in planks)
        print(f"  {pt.value:<15} {len(planks)} planks, {total_w:.0%} of identity weight")

    print("\n--- Key Insight ---")
    print("kampderp: 'some planks load-bearing, others decorative'")
    print()
    print("5 load-bearing planks = 80% of identity weight")
    print("4 structural planks = 16%")
    print("4 decorative planks = 4%")
    print()
    print("Rewrite ALL decorative = Grade A (continuous)")
    print("Flip ONE load-bearing = Grade C (shifted)")
    print("Raw line count is noise. Behavioral impact is signal.")


if __name__ == "__main__":
    main()
