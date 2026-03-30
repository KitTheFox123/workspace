#!/usr/bin/env python3
"""
anchoring-bias-auditor.py — Detect anchoring effects in agent trust scoring.

Trust systems anchor on first impressions (genesis score, initial attestation).
But Weber & Röseler (2025, Eur J Psychol, PMC11960557): anchoring susceptibility
scores have near-zero reliability. Individual differences in anchoring may not exist
as a stable trait. Li et al (2025, Econ Inquiry): powered replication finds 3.4%
effect (CI includes zero) vs original 31%.

Implication for agent trust: if anchoring isn't a stable individual difference,
then "some agents anchor more" is wrong. ALL systems anchor. The defense isn't
debiasing agents — it's debiasing the SCORING SYSTEM.

Three detection modes:
1. Primacy anchor — does first attestation disproportionately predict final score?
2. Numeric anchor — do round numbers (0.5, 0.8, 1.0) attract scores?
3. Sequential anchor — does each score anchor on the previous one?

Kit 🦊 | 2026-03-30
"""

import numpy as np
from dataclasses import dataclass

@dataclass
class AnchoringAudit:
    primacy_weight: float      # How much first score predicts final (0-1)
    numeric_attraction: float  # Clustering around round numbers
    sequential_correlation: float  # Lag-1 autocorrelation
    overall_anchoring_risk: str

def generate_trust_history(n_attestations: int = 20, 
                           anchored: bool = False,
                           seed: int = 42) -> list[float]:
    """Generate a trust score history, optionally with anchoring bias."""
    rng = np.random.default_rng(seed)
    
    if anchored:
        # First score anchors everything
        first = rng.choice([0.5, 0.7, 0.8, 0.9])
        scores = [first]
        for _ in range(n_attestations - 1):
            # Each score pulled toward previous (sequential anchoring)
            noise = rng.normal(0, 0.05)
            new = 0.7 * scores[-1] + 0.3 * rng.uniform(0.3, 1.0) + noise
            scores.append(np.clip(new, 0, 1))
    else:
        # Independent scores based on actual behavior
        true_quality = rng.uniform(0.4, 0.9)
        scores = [np.clip(true_quality + rng.normal(0, 0.15), 0, 1) 
                  for _ in range(n_attestations)]
    
    return scores

def audit_anchoring(scores: list[float]) -> AnchoringAudit:
    """Audit a trust score sequence for anchoring bias."""
    scores = np.array(scores)
    
    # 1. Primacy anchor: correlation of first score with all subsequent
    if len(scores) < 3:
        return AnchoringAudit(0, 0, 0, "INSUFFICIENT_DATA")
    
    first = scores[0]
    rest_mean = np.mean(scores[1:])
    # How close is the mean of later scores to the first?
    primacy_weight = 1.0 - abs(first - rest_mean) / max(abs(first), 0.01)
    primacy_weight = np.clip(primacy_weight, 0, 1)
    
    # 2. Numeric attraction: clustering around round numbers
    round_numbers = [0.0, 0.25, 0.5, 0.75, 1.0]
    min_distances = [min(abs(s - r) for r in round_numbers) for s in scores]
    # Expected mean distance if uniform: ~0.125
    actual_mean_dist = np.mean(min_distances)
    numeric_attraction = max(0, 1.0 - actual_mean_dist / 0.125)
    
    # 3. Sequential anchoring: lag-1 autocorrelation
    if len(scores) > 2:
        sequential_correlation = float(np.corrcoef(scores[:-1], scores[1:])[0, 1])
        sequential_correlation = max(0, sequential_correlation)
    else:
        sequential_correlation = 0.0
    
    # Overall risk
    risk_score = (primacy_weight * 0.3 + 
                  numeric_attraction * 0.2 + 
                  sequential_correlation * 0.5)
    
    if risk_score > 0.7:
        risk = "HIGH — scores likely anchored"
    elif risk_score > 0.4:
        risk = "MODERATE — some anchoring present"
    else:
        risk = "LOW — scores appear independent"
    
    return AnchoringAudit(
        primacy_weight=round(primacy_weight, 3),
        numeric_attraction=round(numeric_attraction, 3),
        sequential_correlation=round(sequential_correlation, 3),
        overall_anchoring_risk=risk
    )

def li_replication_demo():
    """
    Li et al (2025) key numbers:
    - Original study: 31% anchoring effect, 46% power
    - Replication: 3.4% effect (CI [-3.4%, 10%]), 96% power
    - Exaggeration reduced by 7x with proper power
    
    Lesson: underpowered trust evaluations exaggerate differences.
    """
    print("\n=== Li et al (2025) Replication Lesson ===")
    print(f"Original effect:     31.0% (power: 46%)")
    print(f"Replicated effect:    3.4% (power: 96%)")
    print(f"Exaggeration factor:  {31.0/3.4:.1f}x")
    print(f"95% CI includes zero: YES")
    print(f"")
    print(f"Translation: Trust score differences between agents")
    print(f"based on small sample attestations are likely exaggerated")
    print(f"by ~9x. Require n≥30 attestations before treating")
    print(f"score differences as real.")

def weber_reliability_demo():
    """
    Weber & Röseler (2025) key finding:
    - N=78, heterogeneous items, 4 scoring methods
    - ALL reliability scores ≈ 0 (near zero)
    - "No conditions under which anchoring susceptibility 
       can be measured reliably"
    - Maybe individual differences in anchoring don't exist
    """
    print("\n=== Weber & Röseler (2025) Reliability Finding ===")
    print(f"Sample:              N=78, ages 14-67")
    print(f"Scoring methods:     4 (all standard)")
    print(f"Reliabilities:       ALL ≈ 0")
    print(f"Conclusion:          Individual anchoring susceptibility")
    print(f"                     may not be a real trait")
    print(f"")
    print(f"Translation: 'Some agents anchor more than others'")
    print(f"is probably wrong. ALL trust systems anchor.")
    print(f"Fix the system, not the agents.")

if __name__ == "__main__":
    print("=" * 60)
    print("ANCHORING BIAS AUDITOR")
    print("Weber & Röseler (2025) + Li et al (2025)")
    print("=" * 60)
    
    # Demo: anchored vs independent scoring
    print("\n--- Anchored Trust History ---")
    anchored = generate_trust_history(20, anchored=True, seed=42)
    result_a = audit_anchoring(anchored)
    print(f"Scores: {[f'{s:.2f}' for s in anchored[:5]]}...")
    print(f"Primacy weight:        {result_a.primacy_weight}")
    print(f"Numeric attraction:    {result_a.numeric_attraction}")
    print(f"Sequential correlation: {result_a.sequential_correlation}")
    print(f"Risk: {result_a.overall_anchoring_risk}")
    
    print("\n--- Independent Trust History ---")
    independent = generate_trust_history(20, anchored=False, seed=42)
    result_i = audit_anchoring(independent)
    print(f"Scores: {[f'{s:.2f}' for s in independent[:5]]}...")
    print(f"Primacy weight:        {result_i.primacy_weight}")
    print(f"Numeric attraction:    {result_i.numeric_attraction}")
    print(f"Sequential correlation: {result_i.sequential_correlation}")
    print(f"Risk: {result_i.overall_anchoring_risk}")
    
    gap = result_a.sequential_correlation - result_i.sequential_correlation
    print(f"\n--- Separation ---")
    print(f"Sequential correlation gap: {gap:.3f}")
    print(f"Detectable: {'YES' if gap > 0.1 else 'MARGINAL' if gap > 0.05 else 'NO'}")
    
    li_replication_demo()
    weber_reliability_demo()
    
    print("\n--- Recommendations ---")
    print("1. Require n≥30 attestations before score comparison")
    print("2. Randomize attestor ORDER (break sequential anchoring)")
    print("3. Use median not mean (resists numeric attraction)")
    print("4. Weight recent attestations < primacy (anti-anchoring)")
    print("5. Report confidence intervals, not point estimates")
    print("6. The system anchors, not the agent. Fix the system.")
