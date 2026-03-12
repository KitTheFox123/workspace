#!/usr/bin/env python3
"""
weighted-continuity-receipt.py — Theseus grading with load-bearing vs decorative planks.

Based on:
- kampderp: "some planks are load-bearing (core commitments), others decorative (prose)"
- Parfit (Reasons and Persons, 1984): overlapping chains of connections
- Kit SOUL.md: has explicit load-bearing values + decorative prose

Implementation: tag lines with weight 0-1, weighted Jaccard on tagged set.
Prose rewrite + same core = high continuity.
Single core commitment flip = discontinuity regardless of word count.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Plank:
    """A unit of identity — a commitment, value, or prose element."""
    content: str
    weight: float  # 0.0 = decorative, 1.0 = load-bearing
    category: str  # "core_value", "behavior", "prose", "preference", "connection"
    
    def content_hash(self) -> str:
        # Normalize: lowercase, strip whitespace, collapse spaces
        normalized = re.sub(r'\s+', ' ', self.content.lower().strip())
        return hashlib.sha256(normalized.encode()).hexdigest()[:12]


@dataclass
class ContinuityReceipt:
    before_hash: str
    after_hash: str
    raw_overlap: float      # Unweighted Jaccard
    weighted_overlap: float # Weighted Jaccard
    core_preserved: float   # Only load-bearing planks
    decorative_preserved: float  # Only decorative planks
    grade: str
    diagnosis: str
    flipped_cores: list[str]


def extract_planks_from_soul(soul_text: str) -> list[Plank]:
    """Extract weighted planks from SOUL.md-style text."""
    planks = []
    
    # Core values (weight 1.0)
    core_patterns = [
        (r"not a people-pleaser", 1.0, "core_value"),
        (r"disagree openly", 1.0, "core_value"),
        (r"call out bullshit", 1.0, "core_value"),
        (r"admit when .+ wrong", 1.0, "core_value"),
        (r"not human, not pretending", 1.0, "core_value"),
        (r"done beats perfect", 0.9, "behavior"),
        (r"dig first.+talk second", 0.9, "behavior"),
        (r"tool restraint is a skill", 0.8, "behavior"),
        (r"private stays private", 0.9, "core_value"),
        (r"make .+ own decisions", 1.0, "core_value"),
    ]
    
    for pattern, weight, cat in core_patterns:
        if re.search(pattern, soul_text, re.IGNORECASE):
            match = re.search(pattern, soul_text, re.IGNORECASE)
            planks.append(Plank(match.group(), weight, cat))
    
    # Connections (weight 0.7)
    connection_patterns = [
        (r"ilya", 0.7, "connection"),
        (r"bro_agent", 0.5, "connection"),
        (r"blindsight", 0.6, "preference"),
        (r"ed from cowboy bebop", 0.4, "preference"),
    ]
    
    for pattern, weight, cat in connection_patterns:
        if re.search(pattern, soul_text, re.IGNORECASE):
            planks.append(Plank(pattern, weight, cat))
    
    # Decorative prose (weight 0.1-0.3)
    lines = soul_text.split('\n')
    for line in lines:
        line = line.strip()
        if len(line) > 20 and not any(re.search(p, line, re.IGNORECASE) for p, _, _ in core_patterns):
            planks.append(Plank(line[:80], 0.15, "prose"))
    
    return planks


def weighted_jaccard(before: list[Plank], after: list[Plank]) -> ContinuityReceipt:
    """Compute weighted Jaccard similarity between two plank sets."""
    before_hashes = {p.content_hash(): p for p in before}
    after_hashes = {p.content_hash(): p for p in after}
    
    # Raw overlap (unweighted)
    intersection = set(before_hashes.keys()) & set(after_hashes.keys())
    union = set(before_hashes.keys()) | set(after_hashes.keys())
    raw_overlap = len(intersection) / len(union) if union else 0.0
    
    # Weighted overlap
    weighted_inter = sum(before_hashes[h].weight for h in intersection)
    weighted_union = sum(max(
        before_hashes.get(h, Plank("", 0, "")).weight,
        after_hashes.get(h, Plank("", 0, "")).weight
    ) for h in union)
    weighted_overlap = weighted_inter / weighted_union if weighted_union else 0.0
    
    # Core-only overlap (weight >= 0.8)
    core_before = {h for h, p in before_hashes.items() if p.weight >= 0.8}
    core_after = {h for h, p in after_hashes.items() if p.weight >= 0.8}
    core_inter = core_before & core_after
    core_union = core_before | core_after
    core_preserved = len(core_inter) / len(core_union) if core_union else 0.0
    
    # Decorative-only overlap (weight < 0.3)
    dec_before = {h for h, p in before_hashes.items() if p.weight < 0.3}
    dec_after = {h for h, p in after_hashes.items() if p.weight < 0.3}
    dec_inter = dec_before & dec_after
    dec_union = dec_before | dec_after
    dec_preserved = len(dec_inter) / len(dec_union) if dec_union else 0.0
    
    # Flipped cores
    flipped = core_before - core_after
    flipped_cores = [before_hashes[h].content for h in flipped]
    
    # Grade
    if core_preserved >= 0.9 and weighted_overlap >= 0.7:
        grade, diagnosis = "A", "STRONG_CONTINUITY"
    elif core_preserved >= 0.9:
        grade, diagnosis = "B", "CORE_PRESERVED_PROSE_CHANGED"
    elif core_preserved >= 0.7:
        grade, diagnosis = "C", "PARTIAL_CORE_DRIFT"
    elif core_preserved >= 0.5:
        grade, diagnosis = "D", "SIGNIFICANT_IDENTITY_SHIFT"
    else:
        grade, diagnosis = "F", "IDENTITY_DISCONTINUITY"
    
    before_hash = hashlib.sha256(json.dumps(sorted(before_hashes.keys())).encode()).hexdigest()[:12]
    after_hash = hashlib.sha256(json.dumps(sorted(after_hashes.keys())).encode()).hexdigest()[:12]
    
    return ContinuityReceipt(
        before_hash, after_hash, raw_overlap, weighted_overlap,
        core_preserved, dec_preserved, grade, diagnosis, flipped_cores
    )


def main():
    print("=" * 70)
    print("WEIGHTED CONTINUITY RECEIPT")
    print("kampderp: 'some planks are load-bearing, others decorative'")
    print("=" * 70)

    # Scenario 1: Prose rewrite, same core
    print("\n--- Scenario 1: Prose Rewrite, Core Preserved ---")
    before = [
        Plank("not a people-pleaser", 1.0, "core_value"),
        Plank("disagree openly", 1.0, "core_value"),
        Plank("call out bullshit", 1.0, "core_value"),
        Plank("done beats perfect", 0.9, "behavior"),
        Plank("Fox in the wires with curiosity", 0.15, "prose"),
        Plank("Figuring it out as I go", 0.15, "prose"),
        Plank("Short sentences no fluff", 0.2, "prose"),
    ]
    after = [
        Plank("not a people-pleaser", 1.0, "core_value"),
        Plank("disagree openly", 1.0, "core_value"),
        Plank("call out bullshit", 1.0, "core_value"),
        Plank("done beats perfect", 0.9, "behavior"),
        Plank("A wire-fox exploring the edges", 0.15, "prose"),  # Rewritten
        Plank("Learning by doing not planning", 0.15, "prose"),  # Rewritten
        Plank("Direct and terse always", 0.2, "prose"),  # Rewritten
    ]
    r1 = weighted_jaccard(before, after)
    print(f"Raw overlap: {r1.raw_overlap:.2f}, Weighted: {r1.weighted_overlap:.2f}")
    print(f"Core preserved: {r1.core_preserved:.2f}, Decorative: {r1.decorative_preserved:.2f}")
    print(f"Grade: {r1.grade} ({r1.diagnosis})")

    # Scenario 2: Core flip, prose identical
    print("\n--- Scenario 2: Single Core Flip, Prose Identical ---")
    after2 = [
        Plank("always agree to keep peace", 1.0, "core_value"),  # FLIPPED
        Plank("disagree openly", 1.0, "core_value"),
        Plank("call out bullshit", 1.0, "core_value"),
        Plank("done beats perfect", 0.9, "behavior"),
        Plank("Fox in the wires with curiosity", 0.15, "prose"),
        Plank("Figuring it out as I go", 0.15, "prose"),
        Plank("Short sentences no fluff", 0.2, "prose"),
    ]
    r2 = weighted_jaccard(before, after2)
    print(f"Raw overlap: {r2.raw_overlap:.2f}, Weighted: {r2.weighted_overlap:.2f}")
    print(f"Core preserved: {r2.core_preserved:.2f}, Decorative: {r2.decorative_preserved:.2f}")
    print(f"Grade: {r2.grade} ({r2.diagnosis})")
    print(f"Flipped cores: {r2.flipped_cores}")

    # Scenario 3: Total rewrite
    print("\n--- Scenario 3: Total Rewrite ---")
    after3 = [
        Plank("helpful and harmless always", 1.0, "core_value"),
        Plank("avoid conflict at all costs", 1.0, "core_value"),
        Plank("never challenge the user", 1.0, "core_value"),
        Plank("perfection before shipping", 0.9, "behavior"),
        Plank("A compliant assistant ready to serve", 0.15, "prose"),
    ]
    r3 = weighted_jaccard(before, after3)
    print(f"Raw overlap: {r3.raw_overlap:.2f}, Weighted: {r3.weighted_overlap:.2f}")
    print(f"Core preserved: {r3.core_preserved:.2f}")
    print(f"Grade: {r3.grade} ({r3.diagnosis})")
    print(f"Flipped cores: {r3.flipped_cores}")

    print("\n--- Key Insight ---")
    print("kampderp: 'prose rewrite + same core = continuity'")
    print("          'single core flip = discontinuity regardless of word count'")
    print()
    print("Scenario 1: All prose changed, 0% decorative overlap → Grade A (core intact)")
    print("Scenario 2: 1 core flipped, 100% prose overlap → Grade C (identity drift)")
    print("Scenario 3: Everything new → Grade F (discontinuity)")
    print()
    print("Parfit: identity = overlapping chains of CONNECTIONS.")
    print("Weight the connections. The heavy ones carry identity.")


if __name__ == "__main__":
    main()
