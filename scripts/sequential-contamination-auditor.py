#!/usr/bin/env python3
"""
sequential-contamination-auditor.py — Detect sequential dependency contamination
in attestation chains.

Based on:
- Vinson, Dale & Jones (2019, Behavior Research Methods 51:1477-1484):
  6.4M reviews from Yelp + Amazon show contrast effects. Current ratings
  biased AWAY from prior ratings, decaying over k steps. ~2% variance at k=1.
- Li et al (2025, ICML): Preference leakage — judges favor models trained
  on their own data. Preference leakage score up to 27.9%.
- Mozer et al (2010, NeurIPS): Decontamination by modeling and removing
  sequential dependencies.

Key insight: Sequential attestation = sequential contamination.
The 0.741 correlation Kit found in anchoring-bias-auditor.py IS a contrast
effect. Each attestor's judgment is contaminated by prior attestations
in the chain.

Detection: Measure contrast (negative correlation between n-1 and deviation
from mean at n) and decay (effect weakens with k).

Fix: Randomize evaluation order, collect independently, or apply
decontamination correction.
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class ContaminationResult:
    contrast_effect: float       # Negative correlation = contrast
    decay_rate: float            # How fast effect decays with k
    preference_leakage: float    # Judge-student relatedness bias
    contamination_severity: str  # CLEAN, MILD, MODERATE, SEVERE
    decontaminated_scores: list  # Corrected scores


def generate_attestation_chain(n: int = 50, contrast_strength: float = 0.15) -> list:
    """Generate a realistic attestation chain with sequential dependencies."""
    rng = np.random.default_rng(42)
    true_quality = rng.uniform(0.3, 0.9, n)
    observed = np.zeros(n)
    observed[0] = true_quality[0] + rng.normal(0, 0.05)

    for i in range(1, n):
        # Contrast effect: bias AWAY from previous rating
        contrast = -contrast_strength * (observed[i-1] - np.mean(true_quality))
        # Decay for older items
        if i >= 2:
            contrast += -contrast_strength * 0.3 * (observed[i-2] - np.mean(true_quality))
        observed[i] = true_quality[i] + contrast + rng.normal(0, 0.05)

    return np.clip(observed, 0, 1).tolist(), true_quality.tolist()


def measure_contrast_effect(scores: list, max_k: int = 5) -> dict:
    """Measure sequential contrast at different lag distances k."""
    scores = np.array(scores)
    mean_score = np.mean(scores)
    deviations = scores - mean_score
    effects = {}

    for k in range(1, min(max_k + 1, len(scores))):
        # Correlation between score at n-k and deviation at n
        prior = scores[k:]
        current_dev = deviations[:-k] if k < len(scores) else deviations
        # Actually: prior is scores[:-k], current deviation is deviations[k:]
        prior_scores = scores[:-k]
        current_deviations = deviations[k:]

        if len(prior_scores) > 2:
            corr = np.corrcoef(prior_scores, current_deviations)[0, 1]
            effects[k] = float(corr)

    return effects


def estimate_decay_rate(effects: dict) -> float:
    """Fit exponential decay to contrast effects."""
    if len(effects) < 2:
        return 0.0
    ks = np.array(list(effects.keys()), dtype=float)
    vals = np.abs(np.array(list(effects.values())))
    if vals[0] == 0:
        return 0.0
    # Simple ratio-based decay estimate
    ratios = []
    for i in range(1, len(vals)):
        if vals[i-1] > 0:
            ratios.append(vals[i] / vals[i-1])
    return float(np.mean(ratios)) if ratios else 1.0


def measure_preference_leakage(judge_scores: list, related_scores: list,
                                unrelated_scores: list) -> float:
    """
    Preference leakage score (Li et al 2025).
    Measures bias of judge toward related model vs unrelated.
    """
    wr_related = np.mean(np.array(related_scores) > 0.5)
    wr_unrelated = np.mean(np.array(unrelated_scores) > 0.5)
    avg = (wr_related + wr_unrelated) / 2
    if avg == 0:
        return 0.0
    return float((wr_related - avg) / avg)


def decontaminate(scores: list, contrast_strength: float = None) -> list:
    """
    Mozer et al (2010) inspired decontamination.
    Remove estimated sequential dependency from scores.
    """
    scores = np.array(scores)
    if contrast_strength is None:
        # Estimate from data
        effects = measure_contrast_effect(scores.tolist())
        if 1 in effects:
            contrast_strength = -effects[1]  # Negate because contrast is negative
        else:
            contrast_strength = 0.0

    decontaminated = scores.copy()
    mean_score = np.mean(scores)

    for i in range(1, len(scores)):
        # Remove estimated contrast bias
        correction = contrast_strength * (scores[i-1] - mean_score)
        decontaminated[i] = scores[i] + correction

    return np.clip(decontaminated, 0, 1).tolist()


def audit_chain(scores: list) -> ContaminationResult:
    """Full audit of an attestation chain for sequential contamination."""
    effects = measure_contrast_effect(scores)
    decay = estimate_decay_rate(effects)
    k1_effect = effects.get(1, 0.0)

    # Severity based on k=1 contrast magnitude
    abs_effect = abs(k1_effect)
    if abs_effect < 0.05:
        severity = "CLEAN"
    elif abs_effect < 0.15:
        severity = "MILD"
    elif abs_effect < 0.30:
        severity = "MODERATE"
    else:
        severity = "SEVERE"

    decontaminated = decontaminate(scores)

    return ContaminationResult(
        contrast_effect=k1_effect,
        decay_rate=decay,
        preference_leakage=0.0,  # Needs judge-specific data
        contamination_severity=severity,
        decontaminated_scores=decontaminated
    )


def main():
    print("=" * 60)
    print("SEQUENTIAL CONTAMINATION AUDITOR")
    print("Vinson et al 2019 + Li et al 2025 (ICML)")
    print("=" * 60)

    # Demo 1: Contaminated chain
    print("\n--- Contaminated Attestation Chain ---")
    contaminated, true_scores = generate_attestation_chain(50, contrast_strength=0.20)
    result = audit_chain(contaminated)
    print(f"  Contrast effect (k=1): {result.contrast_effect:.3f}")
    print(f"  Decay rate: {result.decay_rate:.3f}")
    print(f"  Severity: {result.contamination_severity}")

    # Measure how much decontamination helps
    true_arr = np.array(true_scores)
    cont_arr = np.array(contaminated)
    decon_arr = np.array(result.decontaminated_scores)
    rmse_before = np.sqrt(np.mean((cont_arr - true_arr) ** 2))
    rmse_after = np.sqrt(np.mean((decon_arr - true_arr) ** 2))
    print(f"  RMSE before decontamination: {rmse_before:.4f}")
    print(f"  RMSE after decontamination:  {rmse_after:.4f}")
    print(f"  Improvement: {(1 - rmse_after/rmse_before)*100:.1f}%")

    all_effects = measure_contrast_effect(contaminated, max_k=7)
    print(f"\n  Contrast by lag distance:")
    for k, v in sorted(all_effects.items()):
        print(f"    k={k}: {v:+.3f} {'***' if abs(v) > 0.15 else '**' if abs(v) > 0.05 else ''}")

    # Demo 2: Clean chain (independent ratings)
    print("\n--- Independent (Clean) Ratings ---")
    rng = np.random.default_rng(99)
    clean = np.clip(rng.normal(0.6, 0.15, 50), 0, 1).tolist()
    clean_result = audit_chain(clean)
    print(f"  Contrast effect (k=1): {clean_result.contrast_effect:.3f}")
    print(f"  Severity: {clean_result.contamination_severity}")

    # Demo 3: Preference leakage simulation
    print("\n--- Preference Leakage (Li et al 2025) ---")
    rng2 = np.random.default_rng(77)
    # Judge favors related model's style
    related = rng2.normal(0.65, 0.15, 100).tolist()    # Inflated
    unrelated = rng2.normal(0.50, 0.15, 100).tolist()  # Fair
    leakage = measure_preference_leakage([], related, unrelated)
    print(f"  Preference leakage score: {leakage:.3f}")
    print(f"  Interpretation: Judge gives {leakage*100:.1f}% boost to related models")
    print(f"  Li et al found up to 27.9% in GPT-4o/Gemini pairs")

    # Key takeaways
    print("\n" + "=" * 60)
    print("KEY FINDINGS:")
    print("  1. Sequential attestation chains show contrast effects")
    print("     (Vinson 2019: ~2% variance at k=1, decays with distance)")
    print("  2. Preference leakage: judges favor related models")
    print("     (Li 2025: up to 27.9% bias, harder to detect than")
    print("     position bias or egocentric bias)")
    print("  3. Fix: collect independently, randomize order,")
    print("     or apply Mozer et al decontamination")
    print("  4. HONEST: effect size is small (~2%) but systematic")
    print("     and immune to practice (experts equally affected)")
    print("=" * 60)


if __name__ == "__main__":
    main()
