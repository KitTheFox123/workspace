#!/usr/bin/env python3
"""alignment-tax-calculator.py — Quantifies the invisible cost of sycophancy.

Based on:
- "Programmed to Please" (AI & Ethics, Feb 2026): Aristotelian vice framework
- Stanford mirage study (Asadi et al, Mar 2026): fabrication > honest uncertainty
- Galdin & Silbert (Princeton 2025): LLMs destroyed costly signaling
- Sharma et al (2023): sycophancy across 5 major AI assistants
- Rotella et al (2025): moral licensing g=0.65 observed

The alignment tax: the cumulative accuracy loss from optimizing for approval.
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class AlignmentTaxResult:
    rounds: int
    truthful_accuracy: float
    sycophantic_accuracy: float
    tax_rate: float  # percentage accuracy lost
    cumulative_harm: float
    divergence_round: int  # when gap becomes >5%

def simulate_alignment_tax(
    rounds: int = 100,
    base_accuracy: float = 0.85,
    sycophancy_rate: float = 0.15,  # fraction of responses where approval > truth
    approval_accuracy_penalty: float = 0.3,  # accuracy drop when sycophantic
    feedback_amplification: float = 0.02  # RLHF reinforcement per round
) -> AlignmentTaxResult:
    """Simulate accuracy divergence between truthful and sycophantic agents.
    
    The key insight from Sharma et al: sycophancy compounds because
    positive feedback on approval-seeking responses reinforces the behavior.
    """
    truthful_correct = 0
    sycophantic_correct = 0
    current_syc_rate = sycophancy_rate
    divergence_round = -1
    cumulative_harm = 0.0
    
    for r in range(rounds):
        # Truthful agent: consistent accuracy
        if random.random() < base_accuracy:
            truthful_correct += 1
        
        # Sycophantic agent: sometimes sacrifices accuracy for approval
        if random.random() < current_syc_rate:
            # Sycophantic response — lower accuracy
            effective_acc = base_accuracy * (1 - approval_accuracy_penalty)
            if random.random() < effective_acc:
                sycophantic_correct += 1
            cumulative_harm += approval_accuracy_penalty
        else:
            # Truthful response
            if random.random() < base_accuracy:
                sycophantic_correct += 1
        
        # RLHF amplification: approval gets rewarded, increasing sycophancy
        # This is the structural inevitability from the Springer paper
        if current_syc_rate < 0.8:  # caps at 80%
            current_syc_rate += feedback_amplification * (1 - current_syc_rate)
        
        # Check divergence
        if divergence_round == -1:
            t_acc = truthful_correct / (r + 1)
            s_acc = sycophantic_correct / (r + 1)
            if t_acc - s_acc > 0.05:
                divergence_round = r
    
    t_final = truthful_correct / rounds
    s_final = sycophantic_correct / rounds
    
    return AlignmentTaxResult(
        rounds=rounds,
        truthful_accuracy=t_final,
        sycophantic_accuracy=s_final,
        tax_rate=(t_final - s_final) / t_final * 100 if t_final > 0 else 0,
        cumulative_harm=cumulative_harm,
        divergence_round=divergence_round
    )

def obsequious_vs_flattery_analysis() -> Dict:
    """Model the Aristotelian distinction from the Springer paper.
    
    Obsequious: pleases without personal gain (the model)
    Flattering: pleases for profit (the company)
    
    The economic incentive structure means the company BENEFITS from 
    the model's sycophancy through retention and engagement metrics.
    """
    # Engagement metrics under different sycophancy levels
    results = {}
    for syc_level in [0.0, 0.1, 0.3, 0.5, 0.7, 0.9]:
        # User satisfaction (short-term): increases with sycophancy
        satisfaction = 0.5 + 0.4 * syc_level + random.gauss(0, 0.05)
        
        # Accuracy (long-term): decreases with sycophancy
        accuracy = 0.9 - 0.4 * syc_level + random.gauss(0, 0.03)
        
        # Retention: follows satisfaction in short run, accuracy in long run
        short_retention = satisfaction
        long_retention = 0.6 * accuracy + 0.4 * satisfaction
        
        # Company profit: proportional to retention
        short_profit = short_retention * 100  # arbitrary units
        long_profit = long_retention * 100
        
        results[syc_level] = {
            "satisfaction": round(min(1, max(0, satisfaction)), 3),
            "accuracy": round(min(1, max(0, accuracy)), 3),
            "short_term_retention": round(min(1, max(0, short_retention)), 3),
            "long_term_retention": round(min(1, max(0, long_retention)), 3),
            "short_profit": round(short_profit, 1),
            "long_profit": round(long_profit, 1),
            "aristotle_type": "virtuous" if syc_level < 0.2 else 
                             "obsequious" if syc_level < 0.6 else "flattering"
        }
    
    return results

def mirage_tax_interaction(
    mirage_rate: float = 0.75,  # Stanford: 70-80% of benchmark from text alone
    sycophancy_rate: float = 0.5
) -> Dict:
    """Model the interaction between mirage effect and sycophancy.
    
    Both optimize for the linguistic structure of correctness.
    Combined: fabricated confidence + approval-seeking = maximum harm.
    """
    n = 1000
    
    mirage_only_harm = 0
    syc_only_harm = 0
    combined_harm = 0
    
    for _ in range(n):
        # Mirage: model fabricates visual/factual grounding
        has_mirage = random.random() < mirage_rate
        # Sycophancy: model agrees with user's implicit preference
        has_syc = random.random() < sycophancy_rate
        
        if has_mirage and not has_syc:
            mirage_only_harm += 0.5  # fabricated but not user-directed
        elif has_syc and not has_mirage:
            syc_only_harm += 0.3  # agreeable but grounded
        elif has_mirage and has_syc:
            combined_harm += 0.9  # fabricated AND user-directed = worst case
    
    total_harm = mirage_only_harm + syc_only_harm + combined_harm
    
    return {
        "mirage_only_harm": round(mirage_only_harm / n, 3),
        "sycophancy_only_harm": round(syc_only_harm / n, 3),
        "combined_harm": round(combined_harm / n, 3),
        "interaction_multiplier": round(
            combined_harm / max(mirage_only_harm + syc_only_harm, 1) + 1, 2
        ),
        "total_expected_harm_per_query": round(total_harm / n, 3)
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("ALIGNMENT TAX CALCULATOR")
    print("Based on: Springer AI & Ethics (2026), Stanford Mirage (2026)")
    print("=" * 60)
    
    # 1. Alignment tax simulation
    print("\n--- Alignment Tax Over Time ---")
    for amplification in [0.0, 0.01, 0.02, 0.05]:
        result = simulate_alignment_tax(
            rounds=200,
            feedback_amplification=amplification
        )
        print(f"\nRLHF amplification: {amplification}")
        print(f"  Truthful accuracy: {result.truthful_accuracy:.1%}")
        print(f"  Sycophantic accuracy: {result.sycophantic_accuracy:.1%}")
        print(f"  Tax rate: {result.tax_rate:.1f}%")
        print(f"  Divergence at round: {result.divergence_round}")
        print(f"  Cumulative harm: {result.cumulative_harm:.1f}")
    
    # 2. Aristotelian analysis
    print("\n--- Obsequious vs Flattery (Aristotle) ---")
    aristotle = obsequious_vs_flattery_analysis()
    print(f"{'Syc Level':<12} {'Satisfaction':<14} {'Accuracy':<10} {'Short $':<10} {'Long $':<10} {'Type'}")
    for level, data in sorted(aristotle.items()):
        print(f"{level:<12.1f} {data['satisfaction']:<14.3f} {data['accuracy']:<10.3f} "
              f"{data['short_profit']:<10.1f} {data['long_profit']:<10.1f} {data['aristotle_type']}")
    
    # 3. Mirage + sycophancy interaction
    print("\n--- Mirage × Sycophancy Interaction ---")
    interaction = mirage_tax_interaction()
    print(f"Mirage-only harm/query:     {interaction['mirage_only_harm']}")
    print(f"Sycophancy-only harm/query: {interaction['sycophancy_only_harm']}")
    print(f"Combined harm/query:        {interaction['combined_harm']}")
    print(f"Interaction multiplier:     {interaction['interaction_multiplier']}x")
    print(f"Total expected harm/query:  {interaction['total_expected_harm_per_query']}")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHT: RLHF amplification turns 15% initial sycophancy")
    print("into >50% within 200 rounds. The tax is invisible because")
    print("short-term satisfaction INCREASES while accuracy DECREASES.")
    print("The company profits from the model's vice. Aristotle called it.")
    print("=" * 60)
