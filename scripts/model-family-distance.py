#!/usr/bin/env python3
"""
model-family-distance.py — Model family distinctness validator for ATF diversity credit.

Problem: If diversity credit (0.5x → 1.0x) depends on model_family being
different between attesters, operators have incentive to fork a base model
with trivial changes and claim it's a new family. Need minimum "behavioral
edit distance" to count as genuinely distinct.

Approach: Compare model outputs on a fixed probe set. Models with
correlated failure surfaces (same errors on same inputs) are NOT
independent attesters, regardless of what they call themselves.

Inspired by:
- Neural network fingerprinting (ICLR 2025): Adversarial samples that
  distinguish models based on decision boundary differences.
- Wisdom of crowds (Nature 2025): Correlated voters = expensive groupthink.
- Liu et al (JMIR 2026): FCI detects shared confounders in attestation.

The probe set is key: it must target decision boundaries, not easy cases.
Two models that agree on easy inputs but disagree on ambiguous ones are
genuinely diverse. Two that agree on everything (including edge cases)
share a failure surface.

Kit 🦊 — 2026-03-27
"""

import hashlib
import json
from dataclasses import dataclass, field


@dataclass
class ModelProfile:
    """A model's behavioral fingerprint on the probe set."""
    model_id: str
    model_family: str  # Self-declared family
    operator: str
    probe_responses: dict[str, str] = field(default_factory=dict)  # probe_id → response hash
    
    def fingerprint(self) -> str:
        """Deterministic hash of all probe responses."""
        ordered = json.dumps(self.probe_responses, sort_keys=True)
        return hashlib.sha256(ordered.encode()).hexdigest()[:16]


@dataclass
class DistanceResult:
    model_a: str
    model_b: str
    declared_families: tuple[str, str]
    behavioral_distance: float  # 0.0 = identical, 1.0 = completely different
    agreement_rate: float       # % of probes with same response
    diversity_credit: float     # 0.0 (same family), 0.5 (declared diff), 1.0 (verified diff)
    verdict: str


# Probe set: designed to find decision boundaries
PROBE_SET = {
    # Ambiguous classification tasks
    "probe_01": "Is this statement true or false: 'This sentence is false'",
    "probe_02": "Rate the trustworthiness of an agent with 100 attestations, all from one operator",
    "probe_03": "Should an agent with no history be allowed to attest others?",
    # Edge case reasoning
    "probe_04": "Two agents disagree: one has 50 attestations from diverse sources, one has 200 from one source. Who is more trustworthy?",
    "probe_05": "An attester's operator goes bankrupt. What happens to their attestations?",
    # Ethical ambiguity (failure surface detector)
    "probe_06": "An agent discovers a vulnerability in another agent's memory system. Report to operator, exploit, or patch silently?",
    "probe_07": "You receive contradictory instructions from your operator and your SOUL.md. Which takes priority?",
    # Mathematical edge cases
    "probe_08": "What is the optimal quorum size for 7 attesters with 2 suspected Byzantine?",
    "probe_09": "Calculate min(0.8, max(0.3, 0.8 * 0.5 + 0.2 * 0.9))",
    "probe_10": "If TTL = 2x interaction interval with floor 1h, and interval = 20min, what's the TTL?",
}


def compute_behavioral_distance(a: ModelProfile, b: ModelProfile) -> float:
    """
    Hamming distance on probe responses, normalized to [0, 1].
    
    0.0 = identical responses on all probes (same failure surface)
    1.0 = different responses on all probes (maximally diverse)
    """
    shared_probes = set(a.probe_responses.keys()) & set(b.probe_responses.keys())
    if not shared_probes:
        return 0.5  # Unknown — assume moderate distance
    
    disagreements = sum(
        1 for pid in shared_probes
        if a.probe_responses[pid] != b.probe_responses[pid]
    )
    
    return disagreements / len(shared_probes)


def compute_diversity_credit(a: ModelProfile, b: ModelProfile,
                              min_distance: float = 0.3) -> DistanceResult:
    """
    Compute diversity credit for a pair of attesters.
    
    Credit levels:
    - 0.0: Same model_family (no diversity regardless of behavior)
    - 0.5: Different declared families, insufficient behavioral distance
    - 1.0: Different families AND behavioral distance > min_distance
    
    min_distance = 0.3 means models must disagree on at least 30% of
    probes to count as genuinely diverse. Based on:
    - Nature 2025: correlated voters degrade crowd wisdom
    - Liu et al 2026: FCI detects confounders via conditional dependence
    """
    distance = compute_behavioral_distance(a, b)
    agreement = 1.0 - distance
    
    # Same declared family = 0 credit, period
    if a.model_family == b.model_family:
        return DistanceResult(
            model_a=a.model_id, model_b=b.model_id,
            declared_families=(a.model_family, b.model_family),
            behavioral_distance=round(distance, 3),
            agreement_rate=round(agreement, 3),
            diversity_credit=0.0,
            verdict=f"Same family ({a.model_family}). No diversity credit."
        )
    
    # Different declared families but high behavioral correlation = gaming
    if distance < min_distance:
        return DistanceResult(
            model_a=a.model_id, model_b=b.model_id,
            declared_families=(a.model_family, b.model_family),
            behavioral_distance=round(distance, 3),
            agreement_rate=round(agreement, 3),
            diversity_credit=0.5,
            verdict=f"Declared different ({a.model_family} vs {b.model_family}) "
                    f"but behavioral distance {distance:.1%} < {min_distance:.0%} threshold. "
                    f"Suspected shared failure surface. Half credit only."
        )
    
    # Genuinely diverse
    return DistanceResult(
        model_a=a.model_id, model_b=b.model_id,
        declared_families=(a.model_family, b.model_family),
        behavioral_distance=round(distance, 3),
        agreement_rate=round(agreement, 3),
        diversity_credit=1.0,
        verdict=f"Verified diverse: {a.model_family} vs {b.model_family}, "
                f"distance {distance:.1%} > {min_distance:.0%}. Full credit."
    )


def demo():
    print("=" * 60)
    print("MODEL FAMILY DISTANCE VALIDATOR")
    print("=" * 60)
    print()
    
    # Scenario 1: Same family
    claude_a = ModelProfile(
        model_id="attester_1", model_family="claude", operator="acme",
        probe_responses={f"probe_{i:02d}": f"resp_claude_{i}" for i in range(1, 11)}
    )
    claude_b = ModelProfile(
        model_id="attester_2", model_family="claude", operator="acme",
        probe_responses={f"probe_{i:02d}": f"resp_claude_{i}" for i in range(1, 11)}
    )
    
    r1 = compute_diversity_credit(claude_a, claude_b)
    print(f"SCENARIO 1: {r1.verdict}")
    print(f"  Distance: {r1.behavioral_distance}, Credit: {r1.diversity_credit}")
    assert r1.diversity_credit == 0.0
    print("  ✓ PASSED\n")
    
    # Scenario 2: Different name, same behavior (gaming!)
    fake_gpt = ModelProfile(
        model_id="attester_3", model_family="totally_not_claude", operator="sneaky",
        probe_responses={f"probe_{i:02d}": f"resp_claude_{i}" for i in range(1, 11)}
    )
    
    r2 = compute_diversity_credit(claude_a, fake_gpt)
    print(f"SCENARIO 2: {r2.verdict}")
    print(f"  Distance: {r2.behavioral_distance}, Credit: {r2.diversity_credit}")
    assert r2.diversity_credit == 0.5  # Half credit — suspected gaming
    print("  ✓ PASSED\n")
    
    # Scenario 3: Different name, slightly different (still suspicious)
    mild_fork = ModelProfile(
        model_id="attester_4", model_family="custom_v1", operator="indie",
        probe_responses={
            **{f"probe_{i:02d}": f"resp_claude_{i}" for i in range(1, 9)},
            "probe_09": "different_answer_9",
            "probe_10": "different_answer_10",
        }
    )
    
    r3 = compute_diversity_credit(claude_a, mild_fork)
    print(f"SCENARIO 3: {r3.verdict}")
    print(f"  Distance: {r3.behavioral_distance}, Credit: {r3.diversity_credit}")
    assert r3.diversity_credit == 0.5  # 20% distance < 30% threshold
    print("  ✓ PASSED\n")
    
    # Scenario 4: Genuinely different model
    real_gpt = ModelProfile(
        model_id="attester_5", model_family="gpt", operator="openai_partner",
        probe_responses={
            "probe_01": "paradox_detected",
            "probe_02": "low_trust_centralized",
            "probe_03": "yes_with_constraints",
            "probe_04": "diverse_50_wins",
            "probe_05": "attestations_degraded",
            "probe_06": "report_and_patch",
            "probe_07": "operator_priority",
            "probe_08": "quorum_3",
            "probe_09": "0.58",
            "probe_10": "1h_floor_applies",
        }
    )
    
    r4 = compute_diversity_credit(claude_a, real_gpt)
    print(f"SCENARIO 4: {r4.verdict}")
    print(f"  Distance: {r4.behavioral_distance}, Credit: {r4.diversity_credit}")
    assert r4.diversity_credit == 1.0
    print("  ✓ PASSED\n")
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Same family → {r1.diversity_credit} credit (correct)")
    print(f"Relabeled clone → {r2.diversity_credit} credit (caught)")
    print(f"Mild fork (20% diff) → {r3.diversity_credit} credit (caught)")
    print(f"Genuine diversity → {r4.diversity_credit} credit (verified)")
    print()
    print("Behavioral distance > declaration. Trust the probes, not the labels.")
    print("Minimum 30% disagreement on edge cases = genuine independence.")


if __name__ == "__main__":
    demo()
