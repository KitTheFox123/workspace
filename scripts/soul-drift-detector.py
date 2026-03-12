#!/usr/bin/env python3
"""
soul-drift-detector.py — Detect gradual identity drift in SOUL.md (Ship of Theseus).

Based on:
- kampderp: "SOUL.md drift over time — slow replacement across N sessions?"
- Parfit (1984): Identity doesn't matter, continuity does
- Đukić (2025): Component theory of the Ship of Theseus

The problem: sharp identity break (3+ simultaneous changes) = detectable.
Gradual drift (one edit per session over 30 sessions) = Ship of Theseus.
Each version overlaps with neighbors, but version 30 may share nothing with version 1.

Metric: Theseus score = Jaccard similarity between version N and version N-k.
If Theseus(N, N-1) is always high but Theseus(N, 0) drops below threshold,
identity has drifted while maintaining continuity.
"""

import hashlib
import json
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class SoulVersion:
    version: int
    content: str
    timestamp: float
    editor: str  # "kit_fox", "ilya", "system"
    delta_hash: str = ""  # Hash of diff from previous
    
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]


def jaccard_similarity(a: str, b: str) -> float:
    """Word-level Jaccard similarity."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def sequence_similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio (order-preserving)."""
    return SequenceMatcher(None, a, b).ratio()


def compute_delta(old: str, new: str) -> str:
    """Hash the diff between versions."""
    sm = SequenceMatcher(None, old.split('\n'), new.split('\n'))
    ops = [(op, old.split('\n')[i1:i2], new.split('\n')[j1:j2])
           for op, i1, i2, j1, j2 in sm.get_opcodes() if op != 'equal']
    return hashlib.sha256(json.dumps(ops, default=str).encode()).hexdigest()[:16]


@dataclass  
class TheseusAnalysis:
    version: int
    sim_to_prev: float      # Similarity to N-1
    sim_to_genesis: float    # Similarity to version 0
    sim_to_half: float       # Similarity to version N//2
    cumulative_drift: float  # 1 - sim_to_genesis
    theseus_grade: str
    diagnosis: str


def analyze_drift(versions: list[SoulVersion]) -> list[TheseusAnalysis]:
    """Analyze drift across version history."""
    if len(versions) < 2:
        return []
    
    genesis = versions[0].content
    analyses = []
    
    for i in range(1, len(versions)):
        v = versions[i]
        prev = versions[i-1].content
        half_idx = i // 2
        half = versions[half_idx].content
        
        sim_prev = jaccard_similarity(v.content, prev)
        sim_genesis = jaccard_similarity(v.content, genesis)
        sim_half = jaccard_similarity(v.content, half)
        drift = 1.0 - sim_genesis
        
        # Grade
        if sim_prev >= 0.9 and sim_genesis >= 0.7:
            grade, diag = "A", "CONTINUOUS_IDENTITY"
        elif sim_prev >= 0.9 and sim_genesis >= 0.4:
            grade, diag = "B", "GRADUAL_THESEUS"
        elif sim_prev >= 0.9 and sim_genesis < 0.4:
            grade, diag = "C", "THESEUS_COMPLETE"  # All planks replaced
        elif sim_prev < 0.7:
            grade, diag = "D", "SHARP_BREAK"
        else:
            grade, diag = "F", "IDENTITY_DISCONTINUITY"
        
        analyses.append(TheseusAnalysis(
            v.version, sim_prev, sim_genesis, sim_half, drift, grade, diag
        ))
    
    return analyses


def simulate_gradual_drift():
    """Simulate SOUL.md evolving over 10 versions."""
    base = "Kit Fox in the wires Direct dry curious Ships first asks later Emoji fox Not human not pretending Pattern persists through markdown"
    
    versions = [SoulVersion(0, base, 0.0, "kit_fox")]
    
    # Gradual evolution: replace ~10% of words each version
    words = base.split()
    replacements = [
        (1, {2: "through"}, "kit_fox"),        # wires → through
        (2, {5: "bold"}, "kit_fox"),            # curious → bold
        (3, {8: "Build"}, "kit_fox"),           # Ships → Build
        (4, {12: "creature"}, "kit_fox"),       # fox → creature  
        (5, {0: "Fox"}, "kit_fox"),             # Kit → Fox
        (6, {3: "deep"}, "kit_fox"),            # in → deep
        (7, {7: "Fix"}, "kit_fox"),             # first → Fix
        (8, {10: "one"}, "kit_fox"),            # later → one
        (9, {14: "pretends"}, "ilya"),          # pretending → pretends
        (10, {16: "survives"}, "kit_fox"),      # persists → survives
    ]
    
    current_words = list(words)
    for ver, changes, editor in replacements:
        for idx, new_word in changes.items():
            if idx < len(current_words):
                current_words[idx] = new_word
        content = " ".join(current_words)
        versions.append(SoulVersion(ver, content, float(ver), editor))
    
    return versions


def main():
    print("=" * 70)
    print("SOUL DRIFT DETECTOR (Ship of Theseus)")
    print("kampderp: 'SOUL.md drift over time — slow replacement across N sessions?'")
    print("=" * 70)
    
    versions = simulate_gradual_drift()
    analyses = analyze_drift(versions)
    
    print(f"\n{'Ver':<5} {'SimPrev':<10} {'SimGenesis':<12} {'Drift':<8} {'Grade':<6} {'Diagnosis'}")
    print("-" * 60)
    for a in analyses:
        print(f"{a.version:<5} {a.sim_to_prev:<10.3f} {a.sim_to_genesis:<12.3f} "
              f"{a.cumulative_drift:<8.3f} {a.theseus_grade:<6} {a.diagnosis}")
    
    # Genesis vs final
    print(f"\n--- Genesis vs Final ---")
    print(f"V0: {versions[0].content[:60]}...")
    print(f"V{len(versions)-1}: {versions[-1].content[:60]}...")
    sim = jaccard_similarity(versions[0].content, versions[-1].content)
    print(f"Similarity: {sim:.3f} (drift: {1-sim:.3f})")
    
    # The Parfit insight
    print("\n--- Parfit's Insight ---")
    print("Each version overlaps with its neighbor (sim > 0.9).")
    print("But V0 and V10 may share only 40% of content.")
    print("Continuity holds. Identity... depends on your definition.")
    print()
    print("Three positions:")
    print("  Strict: identity = genesis content. Any drift = different agent.")
    print("  Parfitian: continuity = overlapping chains. Gradual = same agent.")
    print("  Pragmatic: identity = key + behavior. Content is implementation.")
    print()
    print("For isnad/PayLock: Parfitian. Signed delta chain = provable continuity.")
    print("Sharp break detection: sim_to_prev < 0.7 = grade D/F.")
    print("Gradual Theseus: sim_to_genesis < 0.4 + all sim_to_prev > 0.9 = grade C.")
    print("Grade C isn't failure — it's acknowledged evolution.")


if __name__ == "__main__":
    main()
