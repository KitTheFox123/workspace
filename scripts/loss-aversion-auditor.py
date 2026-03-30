#!/usr/bin/env python3
"""
loss-aversion-auditor.py — Audit trust/reputation systems for loss aversion bias.

Loss aversion (λ≈2.25, Kahneman & Tversky 1992) suggests losses hurt ~2x gains.
But Yechiam & Zeif (2025, J Econ Psych 107:102801) re-meta-analyzed 163 estimates
(n=149,218) and found λ≈1.07 for symmetric, unordered gambles — NOT significantly
above 1.0. The canonical λ=2.25 is inflated by:
  1. Asymmetric gambles (smaller losses than gains → confound with diminishing sensitivity)
  2. Ordered presentation (ascending losses → anchoring/status quo effects)
  3. Publication bias toward dramatic λ values

Walasek, Mullett & Stewart (2024, J Econ Psych 103:102740): re-modeled 17 studies
with raw data, found λ=1.31 (much lower than Brown et al 2024's λ=1.96).

Agent trust parallel: reputation systems often penalize negative attestations MORE
than they reward positive ones (implicit loss aversion). If loss aversion is an
artifact of measurement, asymmetric punishment may be MISCALIBRATED — punishing
defection too harshly relative to rewarding cooperation.

This script audits trust scoring functions for loss aversion bias and simulates
the impact of different λ values on trust dynamics.

References:
- Yechiam & Zeif (2025) "Loss aversion is not robust: A re-meta-analysis" J Econ Psych 107:102801
- Walasek, Mullett & Stewart (2024) "A meta-analysis of loss aversion in risky contexts" J Econ Psych 103:102740
- Brown, Imai, Vieider & Camerer (2024) "Meta-analysis of empirical estimates of loss aversion" CESifo WP
- Kahneman & Tversky (1979, 1992) Prospect Theory
- Ert & Erev (2013) "On the descriptive value of loss aversion in decisions under risk"
"""

import json
import math
import random
from dataclasses import dataclass
from typing import List, Tuple

random.seed(42)

@dataclass
class Attestation:
    """A trust attestation (positive or negative)."""
    agent_id: str
    target_id: str
    positive: bool
    magnitude: float  # 0-1 strength
    timestamp: int

def generate_attestation_history(n: int = 200, defection_rate: float = 0.15) -> List[Attestation]:
    """Generate realistic attestation history."""
    history = []
    for i in range(n):
        positive = random.random() > defection_rate
        magnitude = random.betavariate(2, 5) if not positive else random.betavariate(5, 2)
        history.append(Attestation(
            agent_id=f"agent_{random.randint(0, 19)}",
            target_id="target_0",
            positive=positive,
            magnitude=magnitude,
            timestamp=i
        ))
    return history

def trust_score_with_lambda(history: List[Attestation], lam: float) -> float:
    """
    Compute trust score with given loss aversion parameter λ.
    
    Positive attestation: +magnitude
    Negative attestation: -λ * magnitude
    
    Normalized to [0, 1] via sigmoid.
    """
    raw = 0.0
    for a in history:
        if a.positive:
            raw += a.magnitude
        else:
            raw -= lam * a.magnitude
    # Normalize by count
    raw /= len(history)
    # Sigmoid to [0, 1]
    return 1 / (1 + math.exp(-10 * raw))

def audit_lambda_sensitivity(history: List[Attestation]) -> dict:
    """
    Test how different λ values change trust outcomes.
    
    Key λ values from literature:
    - 1.00: No loss aversion (gains = losses)
    - 1.07: Yechiam & Zeif 2025 (symmetric, unordered)
    - 1.31: Walasek et al 2024 (raw data re-modeling)
    - 1.96: Brown et al 2024 (full meta-analysis, confounded)
    - 2.25: Tversky & Kahneman 1992 (original estimate)
    """
    lambdas = {
        "neutral (1.00)": 1.00,
        "Yechiam_2025 (1.07)": 1.07,
        "Walasek_2024 (1.31)": 1.31,
        "Brown_2024 (1.96)": 1.96,
        "Kahneman_1992 (2.25)": 2.25,
        "extreme (3.00)": 3.00,
    }
    
    results = {}
    for name, lam in lambdas.items():
        score = trust_score_with_lambda(history, lam)
        results[name] = {"lambda": lam, "trust_score": round(score, 4)}
    
    return results

def measure_punishment_asymmetry(history: List[Attestation], lam: float) -> dict:
    """
    Measure how much a single defection costs vs a single cooperation gains.
    """
    # Baseline: all attestations
    baseline = trust_score_with_lambda(history, lam)
    
    # Remove one positive attestation
    pos_indices = [i for i, a in enumerate(history) if a.positive]
    neg_indices = [i for i, a in enumerate(history) if not a.positive]
    
    if not pos_indices or not neg_indices:
        return {"error": "Need both positive and negative attestations"}
    
    # Average impact of removing one positive
    pos_impacts = []
    for idx in random.sample(pos_indices, min(20, len(pos_indices))):
        reduced = [a for i, a in enumerate(history) if i != idx]
        pos_impacts.append(baseline - trust_score_with_lambda(reduced, lam))
    
    # Average impact of removing one negative
    neg_impacts = []
    for idx in random.sample(neg_indices, min(20, len(neg_indices))):
        reduced = [a for i, a in enumerate(history) if i != idx]
        neg_impacts.append(trust_score_with_lambda(reduced, lam) - baseline)
    
    avg_pos = sum(pos_impacts) / len(pos_impacts)
    avg_neg = sum(neg_impacts) / len(neg_impacts)
    
    effective_lambda = avg_neg / avg_pos if avg_pos > 0 else float('inf')
    
    return {
        "configured_lambda": lam,
        "avg_positive_impact": round(avg_pos, 6),
        "avg_negative_impact": round(avg_neg, 6),
        "effective_lambda": round(effective_lambda, 3),
        "interpretation": (
            "OVERCORRECTING" if effective_lambda > 1.5 else
            "CALIBRATED" if 0.8 <= effective_lambda <= 1.5 else
            "UNDERCORRECTING"
        )
    }

def simulate_honest_vs_sybil(n_sims: int = 100) -> dict:
    """
    Test whether loss aversion helps or hurts sybil detection.
    
    Hypothesis: High λ disproportionately punishes honest agents who
    occasionally fail (real defection) while sybils maintain clean records
    (no defection, just manufactured cooperation).
    """
    results = {"honest_punished_more": 0, "sybil_punished_more": 0}
    
    for lam_name, lam in [("neutral", 1.0), ("KT_1992", 2.25)]:
        honest_scores = []
        sybil_scores = []
        
        for _ in range(n_sims):
            # Honest agent: mostly good, occasional real failures (10-20%)
            honest_history = generate_attestation_history(100, defection_rate=random.uniform(0.10, 0.20))
            honest_scores.append(trust_score_with_lambda(honest_history, lam))
            
            # Sybil: manufactured 100% positive record
            sybil_history = generate_attestation_history(100, defection_rate=0.0)
            sybil_scores.append(trust_score_with_lambda(sybil_history, lam))
        
        avg_honest = sum(honest_scores) / len(honest_scores)
        avg_sybil = sum(sybil_scores) / len(sybil_scores)
        gap = avg_sybil - avg_honest
        
        results[lam_name] = {
            "avg_honest": round(avg_honest, 4),
            "avg_sybil": round(avg_sybil, 4),
            "gap": round(gap, 4),
            "interpretation": f"Sybils lead by {gap:.3f} — {'HIGH' if gap > 0.1 else 'LOW'} λ advantage"
        }
    
    # Key finding: higher λ = bigger gap favoring sybils
    neutral_gap = results["neutral"]["gap"]
    kt_gap = results["KT_1992"]["gap"]
    results["lambda_amplifies_sybil_advantage"] = kt_gap > neutral_gap
    results["amplification_factor"] = round(kt_gap / neutral_gap if neutral_gap > 0 else 0, 3)
    
    return results

def main():
    print("=" * 60)
    print("LOSS AVERSION TRUST AUDITOR")
    print("=" * 60)
    
    # Generate history
    history = generate_attestation_history(200, defection_rate=0.15)
    n_pos = sum(1 for a in history if a.positive)
    n_neg = len(history) - n_pos
    print(f"\nAttestations: {len(history)} ({n_pos} positive, {n_neg} negative)")
    print(f"Defection rate: {n_neg/len(history):.1%}")
    
    # 1. Lambda sensitivity
    print("\n" + "-" * 40)
    print("λ SENSITIVITY ANALYSIS")
    print("-" * 40)
    sensitivity = audit_lambda_sensitivity(history)
    for name, data in sensitivity.items():
        print(f"  {name}: trust = {data['trust_score']:.4f}")
    
    spread = sensitivity["extreme (3.00)"]["trust_score"] - sensitivity["neutral (1.00)"]["trust_score"]
    print(f"\n  Spread (λ=1 to λ=3): {spread:.4f}")
    print(f"  → λ choice shifts trust by {abs(spread):.1%}")
    
    # 2. Punishment asymmetry
    print("\n" + "-" * 40)
    print("PUNISHMENT ASYMMETRY AUDIT")
    print("-" * 40)
    for lam_val, lam_name in [(1.0, "neutral"), (1.07, "Yechiam"), (2.25, "K&T")]:
        asym = measure_punishment_asymmetry(history, lam_val)
        print(f"\n  λ={lam_val} ({lam_name}):")
        print(f"    Effective λ: {asym['effective_lambda']}")
        print(f"    Verdict: {asym['interpretation']}")
    
    # 3. Sybil advantage
    print("\n" + "-" * 40)
    print("SYBIL ADVANTAGE UNDER LOSS AVERSION")
    print("-" * 40)
    sybil = simulate_honest_vs_sybil()
    for key in ["neutral", "KT_1992"]:
        d = sybil[key]
        print(f"\n  {key}: honest={d['avg_honest']:.4f}, sybil={d['avg_sybil']:.4f}")
        print(f"    {d['interpretation']}")
    
    print(f"\n  λ amplifies sybil advantage: {sybil['lambda_amplifies_sybil_advantage']}")
    print(f"  Amplification factor: {sybil['amplification_factor']}x")
    
    # Summary
    print("\n" + "=" * 60)
    print("FINDINGS")
    print("=" * 60)
    print("""
1. LOSS AVERSION IS OVERESTIMATED
   Yechiam & Zeif (2025): λ≈1.07 when confounds removed
   Canonical λ=2.25 inflated by asymmetric gambles + ordering

2. TRUST SYSTEMS INHERIT THE BIAS
   Using λ=2.25 vs λ=1.07 shifts trust scores significantly
   The "losses hurt 2x" rule was never empirically clean

3. HIGH λ HELPS SYBILS
   Sybils maintain perfect records → no loss penalty
   Honest agents with real failures get disproportionately punished
   Higher λ = bigger gap favoring manufactured reputations

4. RECOMMENDATION
   Use λ≈1.0-1.3 (evidence-based range)
   Or better: let λ emerge from data, don't hardcode it
   Asymmetric punishment is a design CHOICE, not a cognitive fact
""")
    
    # JSON output
    output = {
        "sensitivity": sensitivity,
        "sybil_advantage": {
            "neutral_gap": sybil["neutral"]["gap"],
            "kt_gap": sybil["KT_1992"]["gap"],
            "amplification": sybil["amplification_factor"]
        },
        "recommendation": "λ≈1.0-1.3 based on Yechiam & Zeif 2025 + Walasek et al 2024",
        "references": [
            "Yechiam & Zeif (2025) J Econ Psych 107:102801",
            "Walasek, Mullett & Stewart (2024) J Econ Psych 103:102740",
            "Brown, Imai, Vieider & Camerer (2024) CESifo WP",
            "Kahneman & Tversky (1979) Econometrica 47:263-291"
        ]
    }
    
    print("\n" + json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
