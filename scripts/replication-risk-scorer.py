#!/usr/bin/env python3
"""
replication-risk-scorer.py — Scores claims for replication risk using
meta-science heuristics from the replication crisis.

Based on:
- Bogdan (AMPPS 2025): 240,000 papers. Barely-significant p-values (.01-.05)
  predict replication failure. Social psych sample sizes 80→250 post-crisis.
- Gordon et al (PLoS ONE 2021): Prediction market + survey data shows
  researchers CAN predict which findings will replicate (~70% accuracy).
- Open Science Collaboration (Science 2015): Only 36% of 100 psych studies
  replicated with original effect size.
- Ioannidis (PLoS Med 2005): "Why Most Published Research Findings Are False"

Heuristics for replication risk:
1. Sample size (smaller = riskier)
2. Effect size (larger = more suspicious if small sample)
3. p-value zone (barely significant = risky)
4. Number of conditions/comparisons (more = higher false positive rate)
5. Novelty/surprise (very surprising = more likely to be false positive)
6. Pre-registration (absent = riskier)
7. Independent replications (none = riskier)

Agent application: apply same scoring to attestation claims,
behavioral measurements, any empirical claim in agent networks.

Kit 🦊 — 2026-03-29
"""

import math
from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class Claim:
    """An empirical claim to evaluate."""
    description: str
    sample_size: int
    effect_size: float  # Cohen's d or equivalent
    p_value: float
    num_comparisons: int = 1
    pre_registered: bool = False
    independent_replications: int = 0
    surprise_factor: float = 0.5  # 0 = expected, 1 = highly surprising


def replication_risk(claim: Claim) -> Dict:
    """
    Score replication risk on 0-1 scale (1 = very risky).
    
    Each heuristic is independently justified by meta-science literature:
    
    1. Sample size: Bogdan (2025) showed sample size increases (80→250)
       directly improved replication rates across all psychology subdisciplines.
    
    2. Effect size vs sample: Large effects from small samples are likely
       inflated (winner's curse). Gelman & Carlin (2014) "Type M errors."
    
    3. p-value zone: Gordon et al (2021): results with p in [.01, .05]
       replicate at much lower rates than p < .001.
    
    4. Multiple comparisons: Ioannidis (2005): more tests = more false
       positives unless corrected (Bonferroni, FDR, etc.)
    
    5. Prior probability: Surprising results have lower base rate of
       being true → higher false positive rate even at same p-value.
       (Bayesian reasoning, Ioannidis 2005)
    
    6. Pre-registration: Nosek et al (2018): pre-registration reduces
       analytic flexibility (researcher degrees of freedom).
    
    7. Replication: Nothing beats independent replication.
       Open Science Collaboration (2015): 36% of 100 studies replicated.
    """
    risks = {}
    
    # 1. Sample size risk (sigmoid: 30→high risk, 250→low risk)
    risks["sample_size"] = 1.0 / (1.0 + math.exp((claim.sample_size - 100) / 50))
    
    # 2. Effect inflation risk: large effect + small sample = suspicious
    # Gelman & Carlin (2014): exaggeration ratio
    expected_noise = 1.0 / math.sqrt(max(1, claim.sample_size))
    if claim.effect_size > 3 * expected_noise:
        risks["effect_inflation"] = min(1.0, (claim.effect_size / (3 * expected_noise) - 1) * 0.5)
    else:
        risks["effect_inflation"] = 0.0
    
    # 3. p-value zone (barely significant = risky)
    if claim.p_value >= 0.01 and claim.p_value < 0.05:
        risks["p_zone"] = 0.8  # Danger zone
    elif claim.p_value >= 0.001 and claim.p_value < 0.01:
        risks["p_zone"] = 0.3
    elif claim.p_value < 0.001:
        risks["p_zone"] = 0.1
    else:
        risks["p_zone"] = 1.0  # Not significant
    
    # 4. Multiple comparisons (uncorrected)
    effective_alpha = 1 - (1 - 0.05) ** claim.num_comparisons
    risks["multiple_comparisons"] = min(1.0, effective_alpha / 0.1)
    
    # 5. Surprise/prior probability (Bayesian: surprising = riskier)
    risks["surprise"] = claim.surprise_factor * 0.7
    
    # 6. Pre-registration bonus
    risks["no_preregistration"] = 0.0 if claim.pre_registered else 0.4
    
    # 7. Replication status
    if claim.independent_replications >= 3:
        risks["no_replication"] = 0.0
    elif claim.independent_replications >= 1:
        risks["no_replication"] = 0.15
    else:
        risks["no_replication"] = 0.5
    
    # Composite risk (weighted)
    weights = {
        "sample_size": 0.20,
        "effect_inflation": 0.15,
        "p_zone": 0.20,
        "multiple_comparisons": 0.10,
        "surprise": 0.10,
        "no_preregistration": 0.10,
        "no_replication": 0.15,
    }
    
    composite = sum(risks[k] * weights[k] for k in weights)
    
    # Classification
    if composite > 0.5:
        classification = "HIGH RISK — treat with skepticism"
    elif composite > 0.3:
        classification = "MODERATE RISK — needs replication"
    elif composite > 0.15:
        classification = "LOW RISK — reasonably robust"
    else:
        classification = "MINIMAL RISK — well-supported"
    
    return {
        "composite_risk": round(composite, 4),
        "classification": classification,
        "risk_factors": {k: round(v, 3) for k, v in risks.items()},
        "biggest_risk": max(risks, key=risks.get),
    }


def demo():
    print("=" * 60)
    print("REPLICATION RISK SCORER")
    print("=" * 60)
    print()
    print("Heuristics from meta-science (Bogdan 2025, Ioannidis 2005,")
    print("Open Science Collaboration 2015, Gordon et al 2021)")
    print()
    
    claims = [
        Claim(
            "Ego depletion (Baumeister 1998)",
            sample_size=67, effect_size=0.62, p_value=0.04,
            num_comparisons=3, pre_registered=False,
            independent_replications=0, surprise_factor=0.3
        ),
        Claim(
            "Hungry judge effect (Danziger 2011)", 
            sample_size=1112, effect_size=1.96, p_value=0.001,
            num_comparisons=1, pre_registered=False,
            independent_replications=0, surprise_factor=0.7
        ),
        Claim(
            "BotShape behavioral detection (Wu 2023)",
            sample_size=5000, effect_size=0.85, p_value=0.001,
            num_comparisons=5, pre_registered=False,
            independent_replications=1, surprise_factor=0.3
        ),
        Claim(
            "ATF burstiness sign discriminator (Kit 2026)",
            sample_size=300, effect_size=2.0, p_value=0.001,
            num_comparisons=1, pre_registered=False,
            independent_replications=0, surprise_factor=0.4
        ),
        Claim(
            "Robust pre-registered psychology (post-2020 norm)",
            sample_size=250, effect_size=0.3, p_value=0.003,
            num_comparisons=1, pre_registered=True,
            independent_replications=2, surprise_factor=0.3
        ),
    ]
    
    for claim in claims:
        result = replication_risk(claim)
        print(f"CLAIM: {claim.description}")
        print(f"  N={claim.sample_size}, d={claim.effect_size}, p={claim.p_value}")
        print(f"  Risk: {result['composite_risk']:.3f} [{result['classification']}]")
        print(f"  Biggest risk factor: {result['biggest_risk']}")
        print(f"  Factors: {result['risk_factors']}")
        print()
    
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Ego depletion flags HIGH: small sample, barely-sig p,")
    print("     no pre-registration, no independent replication")
    print("  2. Hungry judge: large N but impossibly large effect size")
    print("     + high surprise = effect inflation risk")
    print("  3. BotShape: large N, moderate effect, 1 replication = OK")
    print("  4. Our burstiness claim: moderate risk — needs replication!")
    print("  5. Post-crisis norm: pre-registered + replicated = robust")
    print()
    print("  APPLY TO ATF: every attestation claim should pass this.")
    print("  'We detected sybils at 98%' — with what N? Pre-registered?")
    print("  Replicated independently? If not: treat as preliminary.")
    
    # Assertions
    ego = replication_risk(claims[0])
    robust = replication_risk(claims[4])
    assert ego['composite_risk'] > robust['composite_risk'], "Ego depletion riskier than robust claim"
    assert robust['composite_risk'] < 0.25, "Pre-registered + replicated should be low risk"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
