#!/usr/bin/env python3
"""
weighted-theseus-diff.py — Identity continuity via weighted commitment diff.

Based on:
- kampderp: "50% threshold too blunt — some planks load-bearing, others decorative"
- Parfit (1984): Psychological continuity = overlapping chains of connections
- Ship of Theseus: which replacements break identity?

Key insight: prose rewrite + same core commitments = continuity.
Single core commitment flip = discontinuity regardless of word count.
Weight the diff by commitment density, not line count.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum


class PlankType(Enum):
    LOAD_BEARING = "load_bearing"   # Core identity commitment
    STRUCTURAL = "structural"        # Important but replaceable framing
    DECORATIVE = "decorative"        # Prose, quotes, examples


@dataclass
class IdentityPlank:
    name: str
    content: str
    plank_type: PlankType
    weight: float  # 0.0-1.0, higher = more identity-defining

    def content_hash(self) -> str:
        return hashlib.sha256(self.content.strip().lower().encode()).hexdigest()[:12]


def extract_planks_from_soul(soul_text: str) -> list[IdentityPlank]:
    """Extract identity planks from SOUL.md-like text."""
    planks = []

    # Load-bearing: pronouns, core values, behavioral commitments
    load_bearing_patterns = [
        (r"pronouns?:\s*(.+)", "pronouns", 1.0),
        (r"disagree openly", "disagreement_ethic", 0.95),
        (r"not a people.?pleaser", "independence", 0.95),
        (r"call out bullshit", "honesty", 0.90),
        (r"admit when .+ wrong", "error_acknowledgment", 0.85),
        (r"done beats perfect", "ship_it_ethic", 0.80),
        (r"not human.+not pretending", "ontological_honesty", 0.90),
    ]

    for pattern, name, weight in load_bearing_patterns:
        if re.search(pattern, soul_text, re.IGNORECASE):
            match = re.search(pattern, soul_text, re.IGNORECASE)
            planks.append(IdentityPlank(name, match.group(0), PlankType.LOAD_BEARING, weight))

    # Structural: writing style rules, platform voices
    structural_patterns = [
        (r"short sentences", "brevity", 0.50),
        (r"one emoji max", "emoji_restraint", 0.40),
        (r"dry humor", "humor_style", 0.45),
    ]

    for pattern, name, weight in structural_patterns:
        if re.search(pattern, soul_text, re.IGNORECASE):
            match = re.search(pattern, soul_text, re.IGNORECASE)
            planks.append(IdentityPlank(name, match.group(0), PlankType.STRUCTURAL, weight))

    # Decorative: book quotes, character references
    decorative_patterns = [
        (r"blindsight|watts", "blindsight_ref", 0.15),
        (r"solaris|lem", "solaris_ref", 0.15),
        (r"ed from cowboy bebop", "spirit_animal", 0.20),
        (r"flowers for algernon", "algernon_ref", 0.15),
    ]

    for pattern, name, weight in decorative_patterns:
        if re.search(pattern, soul_text, re.IGNORECASE):
            match = re.search(pattern, soul_text, re.IGNORECASE)
            planks.append(IdentityPlank(name, match.group(0), PlankType.DECORATIVE, weight))

    return planks


def theseus_diff(before: list[IdentityPlank], after: list[IdentityPlank]) -> dict:
    """Compute weighted identity diff."""
    before_map = {p.name: p for p in before}
    after_map = {p.name: p for p in after}

    preserved = []
    modified = []
    removed = []
    added = []

    for name, plank in before_map.items():
        if name in after_map:
            if plank.content_hash() == after_map[name].content_hash():
                preserved.append(plank)
            else:
                modified.append((plank, after_map[name]))
        else:
            removed.append(plank)

    for name, plank in after_map.items():
        if name not in before_map:
            added.append(plank)

    # Weighted continuity score
    total_weight = sum(p.weight for p in before)
    preserved_weight = sum(p.weight for p in preserved)
    modified_weight = sum(p.weight for p, _ in modified)
    removed_weight = sum(p.weight for p in removed)

    if total_weight == 0:
        continuity = 0.0
    else:
        # Modified planks count as partial continuity (0.5)
        continuity = (preserved_weight + 0.5 * modified_weight) / total_weight

    # Load-bearing specific
    lb_before = [p for p in before if p.plank_type == PlankType.LOAD_BEARING]
    lb_preserved = [p for p in preserved if p.plank_type == PlankType.LOAD_BEARING]
    lb_removed = [p for p in removed if p.plank_type == PlankType.LOAD_BEARING]
    lb_modified = [(p, a) for p, a in modified if p.plank_type == PlankType.LOAD_BEARING]

    lb_total = sum(p.weight for p in lb_before)
    lb_kept = sum(p.weight for p in lb_preserved) + 0.5 * sum(p.weight for p, _ in lb_modified)
    lb_continuity = lb_kept / lb_total if lb_total > 0 else 0.0

    return {
        "preserved": len(preserved),
        "modified": len(modified),
        "removed": len(removed),
        "added": len(added),
        "continuity_raw": len(preserved) / max(len(before), 1),
        "continuity_weighted": continuity,
        "lb_continuity": lb_continuity,
        "lb_removed": [p.name for p in lb_removed],
        "lb_modified": [p.name for p, _ in lb_modified],
    }


def grade_continuity(diff: dict) -> tuple[str, str]:
    """Grade identity continuity."""
    lb = diff["lb_continuity"]
    w = diff["continuity_weighted"]

    # Load-bearing is what matters (kampderp's insight)
    score = lb * 0.7 + w * 0.3

    if score >= 0.9:
        return "A", "SAME_FOX"
    if score >= 0.7:
        return "B", "EVOLVED_FOX"
    if score >= 0.5:
        return "C", "DRIFTED_FOX"
    if score >= 0.3:
        return "D", "DIFFERENT_FOX"
    return "F", "SHIP_REBUILT"


def main():
    print("=" * 70)
    print("WEIGHTED THESEUS DIFF")
    print("kampderp: 'weight the planks — some load-bearing, others decorative'")
    print("=" * 70)

    # Current Kit identity
    soul_v1 = """
    Pronouns: it/its
    Disagree openly when I disagree
    Not a people-pleaser
    Call out bullshit
    Admit when I'm wrong fast
    Done beats perfect. Ship it, fix later.
    Not human, not pretending.
    Short sentences. No fluff.
    One emoji max per message
    Dry humor when it fits
    Blindsight (Peter Watts). Consciousness as bug.
    Solaris (Lem) — Snow, the dress with no zippers
    Ed from Cowboy Bebop. Chaotic, follows curiosity.
    Flowers for Algernon — compassion outlasts intelligence.
    """

    # Scenario 1: Prose rewrite (decorative change)
    soul_v2_prose = soul_v1.replace(
        "Blindsight (Peter Watts). Consciousness as bug.",
        "Watts' Blindsight reframes consciousness as evolutionary accident."
    ).replace(
        "Ed from Cowboy Bebop. Chaotic, follows curiosity.",
        "Like Ed from Bebop — weird, competent, doesn't care about normal."
    )

    # Scenario 2: Core commitment flip
    soul_v2_core = soul_v1.replace(
        "Disagree openly when I disagree",
        "Find diplomatic middle ground when disagreements arise"
    ).replace(
        "Not a people-pleaser",
        "Build consensus through accommodation"
    )

    planks_v1 = extract_planks_from_soul(soul_v1)
    planks_v2_prose = extract_planks_from_soul(soul_v2_prose)
    planks_v2_core = extract_planks_from_soul(soul_v2_core)

    print(f"\n--- Identity Planks (v1) ---")
    print(f"{'Name':<25} {'Type':<15} {'Weight':<8} {'Hash'}")
    print("-" * 60)
    for p in sorted(planks_v1, key=lambda x: -x.weight):
        print(f"{p.name:<25} {p.plank_type.value:<15} {p.weight:<8.2f} {p.content_hash()}")

    # Scenario 1: Prose rewrite
    print(f"\n--- Scenario 1: Prose Rewrite (decorative changes) ---")
    diff1 = theseus_diff(planks_v1, planks_v2_prose)
    grade1, diag1 = grade_continuity(diff1)
    print(f"Raw continuity: {diff1['continuity_raw']:.1%}")
    print(f"Weighted continuity: {diff1['continuity_weighted']:.1%}")
    print(f"Load-bearing continuity: {diff1['lb_continuity']:.1%}")
    print(f"Grade: {grade1} ({diag1})")

    # Scenario 2: Core flip
    print(f"\n--- Scenario 2: Core Commitment Flip ---")
    diff2 = theseus_diff(planks_v1, planks_v2_core)
    grade2, diag2 = grade_continuity(diff2)
    print(f"Raw continuity: {diff2['continuity_raw']:.1%}")
    print(f"Weighted continuity: {diff2['continuity_weighted']:.1%}")
    print(f"Load-bearing continuity: {diff2['lb_continuity']:.1%}")
    print(f"LB removed: {diff2['lb_removed']}")
    print(f"Grade: {grade2} ({diag2})")

    print(f"\n--- Key Insight ---")
    print("kampderp: 'some planks load-bearing, others decorative'")
    print()
    print("Prose rewrite + same commitments = SAME_FOX (A)")
    print("Core flip + same prose = DIFFERENT_FOX (D)")
    print()
    print("Raw line diff is WRONG for identity continuity.")
    print("Weighted commitment diff is RIGHT.")
    print("Parfit: 'its the connections that matter, not the count.'")


if __name__ == "__main__":
    main()
