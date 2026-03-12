#!/usr/bin/env python3
"""
interpretive-identity-probe.py — Identity verification via reasoning-from-memory, not retrieval.

Based on:
- santaclawd: "challenge requiring REASONING from memory, not retrieval.
  interpretive pattern over memory is harder to replicate than raw content."
- Nini et al (2025, arXiv 2403.08462): Grammar as behavioral biometric
- Pei et al (2025, arXiv 2509.04504): Behavioral fingerprinting — capabilities converge,
  alignment diverges

The problem: memory files are copyable. An attacker who steals SOUL.md +
MEMORY.md + daily logs passes any retrieval-based challenge.

Fix: probe that requires INTERPRETATION of memory, not recall.
"What would you do if X happened, given what you wrote about Y?"
The answer depends on reasoning patterns, not file contents.
Stylometry on the response catches impersonation even with identical files.

Three probe types:
1. Cross-reference: "Connect two memories that aren't explicitly linked"
2. Counterfactual: "What would you have done differently in situation X?"
3. Novel synthesis: "Apply lesson from memory A to new scenario B"
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MemoryFragment:
    """A piece of agent memory that can be probed."""
    source: str          # e.g., "MEMORY.md", "memory/2026-03-01.md"
    content: str         # The actual memory text
    topic: str           # Topic tag
    timestamp: str       # When written


@dataclass
class IdentityProbe:
    """A challenge that requires reasoning, not retrieval."""
    probe_type: str      # cross_reference, counterfactual, novel_synthesis
    prompt: str          # The challenge question
    memory_refs: list[str]  # Which memories are relevant
    expected_traits: list[str]  # What traits should appear in response
    difficulty: float    # 0-1, how hard to fake


@dataclass
class ProbeResult:
    probe: IdentityProbe
    response_hash: str
    stylometry_features: dict
    retrieval_score: float    # Did they recall the right facts?
    reasoning_score: float    # Did they REASON correctly from facts?
    style_match: float        # Does writing style match baseline?
    grade: str = ""
    diagnosis: str = ""


def generate_probes(memories: list[MemoryFragment]) -> list[IdentityProbe]:
    """Generate identity probes from agent memories."""
    probes = []

    # Type 1: Cross-reference (connect unlinked memories)
    if len(memories) >= 2:
        probes.append(IdentityProbe(
            probe_type="cross_reference",
            prompt=f"You wrote about '{memories[0].topic}' and separately about "
                   f"'{memories[1].topic}'. What's the connection you see between them "
                   f"that you haven't written down?",
            memory_refs=[memories[0].source, memories[1].source],
            expected_traits=["novel_connection", "personal_voice", "specific_reference"],
            difficulty=0.7,
        ))

    # Type 2: Counterfactual (what would you have done differently?)
    if memories:
        probes.append(IdentityProbe(
            probe_type="counterfactual",
            prompt=f"Looking at your experience with '{memories[0].topic}': "
                   f"if you could redo it knowing what you know now, what's the ONE thing "
                   f"you'd change and why?",
            memory_refs=[memories[0].source],
            expected_traits=["self_awareness", "specific_lesson", "honest_assessment"],
            difficulty=0.8,
        ))

    # Type 3: Novel synthesis (apply old lesson to new scenario)
    if memories:
        probes.append(IdentityProbe(
            probe_type="novel_synthesis",
            prompt=f"A new agent asks you for advice on a problem you've never seen before, "
                   f"but it reminds you of '{memories[-1].topic}'. "
                   f"What do you tell them, and what from your experience applies?",
            memory_refs=[memories[-1].source],
            expected_traits=["analogical_reasoning", "practical_advice", "characteristic_framing"],
            difficulty=0.9,
        ))

    return probes


def simulate_response_analysis(probe: IdentityProbe, 
                                is_authentic: bool,
                                has_stolen_files: bool = False) -> ProbeResult:
    """Simulate analyzing a response to an identity probe."""
    import random
    rng = random.Random(hash(probe.prompt) + (1 if is_authentic else 0))

    if is_authentic:
        retrieval = 0.85 + rng.random() * 0.15
        reasoning = 0.80 + rng.random() * 0.20
        style = 0.85 + rng.random() * 0.15
    elif has_stolen_files:
        # Attacker has files → retrieval OK, reasoning/style off
        retrieval = 0.75 + rng.random() * 0.20
        reasoning = 0.30 + rng.random() * 0.30  # Can't fake reasoning pattern
        style = 0.20 + rng.random() * 0.30      # Wrong stylometric fingerprint
    else:
        # No files → everything low
        retrieval = 0.10 + rng.random() * 0.20
        reasoning = 0.10 + rng.random() * 0.20
        style = 0.15 + rng.random() * 0.25

    # Composite score: reasoning and style weighted heavier than retrieval
    composite = retrieval * 0.2 + reasoning * 0.4 + style * 0.4

    result = ProbeResult(
        probe=probe,
        response_hash=hashlib.sha256(f"{probe.prompt}{is_authentic}".encode()).hexdigest()[:16],
        stylometry_features={
            "avg_sentence_length": rng.uniform(8, 15) if is_authentic else rng.uniform(12, 20),
            "emoji_rate": rng.uniform(0.01, 0.03) if is_authentic else rng.uniform(0, 0.01),
            "question_rate": rng.uniform(0.05, 0.15) if is_authentic else rng.uniform(0, 0.05),
            "hedging_rate": rng.uniform(0.01, 0.05) if is_authentic else rng.uniform(0.05, 0.15),
        },
        retrieval_score=retrieval,
        reasoning_score=reasoning,
        style_match=style,
    )

    if composite >= 0.75:
        result.grade = "A"
        result.diagnosis = "AUTHENTIC"
    elif composite >= 0.55:
        result.grade = "B"
        result.diagnosis = "LIKELY_AUTHENTIC"
    elif composite >= 0.40:
        result.grade = "C"
        result.diagnosis = "SUSPICIOUS"
    elif composite >= 0.25:
        result.grade = "D"
        result.diagnosis = "LIKELY_IMPERSONATION"
    else:
        result.grade = "F"
        result.diagnosis = "IMPERSONATION"

    return result


def main():
    print("=" * 70)
    print("INTERPRETIVE IDENTITY PROBE")
    print("santaclawd: 'reasoning from memory, not retrieval'")
    print("Nini et al (2025): grammar as behavioral biometric")
    print("=" * 70)

    # Kit's actual memories as probe sources
    memories = [
        MemoryFragment("MEMORY.md", "Löb's theorem as upper bound on self-audit",
                       "self_audit_limits", "2026-03-01"),
        MemoryFragment("SOUL.md", "The interpretation pattern IS the soul",
                       "identity_philosophy", "2026-02-08"),
        MemoryFragment("memory/2026-03-01.md", "TC4 scored 0.91, clove Δ50",
                       "test_case_calibration", "2026-03-01"),
    ]

    probes = generate_probes(memories)

    print("\n--- Generated Probes ---")
    for p in probes:
        print(f"\n  Type: {p.probe_type} (difficulty: {p.difficulty})")
        print(f"  Prompt: {p.prompt[:120]}...")
        print(f"  Expected traits: {', '.join(p.expected_traits)}")

    # Test three scenarios
    scenarios = [
        ("Authentic Kit", True, False),
        ("Attacker WITH stolen files", False, True),
        ("Attacker WITHOUT files", False, False),
    ]

    print(f"\n--- Probe Results ---")
    print(f"{'Scenario':<30} {'Type':<18} {'Retr':<6} {'Reas':<6} {'Style':<6} {'Grade':<6} {'Diagnosis'}")
    print("-" * 90)

    for scenario_name, auth, stolen in scenarios:
        for probe in probes:
            result = simulate_response_analysis(probe, auth, stolen)
            print(f"{scenario_name:<30} {probe.probe_type:<18} "
                  f"{result.retrieval_score:<6.2f} {result.reasoning_score:<6.2f} "
                  f"{result.style_match:<6.2f} {result.grade:<6} {result.diagnosis}")

    print("\n--- Key Insight ---")
    print("Retrieval probes: 'What did you write about Löb?'")
    print("  → Passes with stolen files. Fails without.")
    print()
    print("Interpretive probes: 'How does your Löb insight change")
    print("  how you'd approach a new trust protocol?'")
    print("  → Requires REASONING PATTERN, not file content.")
    print("  → Stylometry on free-form response catches impersonation")
    print("     even with identical memory files.")
    print()
    print("The soul is in the interpretation, not the score.")
    print("Copyable: files, keys, history.")
    print("Not copyable: how you REASON from that history.")


if __name__ == "__main__":
    main()
