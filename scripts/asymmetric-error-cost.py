#!/usr/bin/env python3
"""
asymmetric-error-cost.py — Neyman-Pearson framework for payer_type classification.

Per bro_agent (2026-03-15): "Unrecoverable false negative on human payer > 
recoverable false positive on A2A."

Neyman-Pearson (1933): minimize Type II error (miss) subject to 
Type I error (false alarm) ≤ α. When costs are asymmetric, 
the threshold shifts toward the cheaper error.

Applied: misclassifying human as A2A (5min timeout → funds lost) 
costs MORE than misclassifying A2A as human (24h timeout → just slow).
"""

from dataclasses import dataclass
from enum import Enum
import math


class ErrorType(Enum):
    FALSE_POSITIVE = "fp"  # A2A classified as human → slow but safe
    FALSE_NEGATIVE = "fn"  # Human classified as A2A → funds at risk


@dataclass
class ErrorCost:
    error_type: ErrorType
    description: str
    cost_sol: float          # Direct financial cost
    reversible: bool         # Can the error be corrected?
    time_to_detect_hours: float
    
    @property
    def effective_cost(self) -> float:
        """Irreversible errors get 10x multiplier."""
        return self.cost_sol * (10.0 if not self.reversible else 1.0)


# Define asymmetric costs
COSTS = {
    ErrorType.FALSE_POSITIVE: ErrorCost(
        error_type=ErrorType.FALSE_POSITIVE,
        description="A2A gets human timeout (24h instead of 5min)",
        cost_sol=0.0,       # No funds lost, just slower
        reversible=True,     # Can re-classify on next contract
        time_to_detect_hours=0.1,
    ),
    ErrorType.FALSE_NEGATIVE: ErrorCost(
        error_type=ErrorType.FALSE_NEGATIVE,
        description="Human gets A2A timeout (5min instead of 24h)",
        cost_sol=0.5,        # Average escrow value at risk
        reversible=False,    # Funds may be lost after timeout
        time_to_detect_hours=0.083,  # 5 minutes
    ),
}


def neyman_pearson_threshold(
    alpha: float = 0.01,      # Max acceptable Type I error rate
    base_rate_a2a: float = 0.7,  # Prior: most contracts are A2A
    cost_ratio: float | None = None,
) -> dict:
    """
    Compute optimal classification threshold using Neyman-Pearson.
    
    When cost_ratio (FN/FP) is high, threshold shifts conservative:
    classify as human unless STRONG evidence of A2A.
    """
    if cost_ratio is None:
        fp_cost = COSTS[ErrorType.FALSE_POSITIVE].effective_cost
        fn_cost = COSTS[ErrorType.FALSE_NEGATIVE].effective_cost
        cost_ratio = fn_cost / max(fp_cost, 0.001)
    
    # Likelihood ratio threshold shifts with cost asymmetry
    # Higher cost_ratio → higher threshold → more conservative
    lr_threshold = cost_ratio * (1 - alpha) / alpha
    
    # In practice: a2a_score must exceed this to classify as A2A
    # Map to 0-1 score threshold
    score_threshold = 1 - 1 / (1 + math.log1p(lr_threshold))
    
    return {
        "alpha": alpha,
        "cost_ratio_fn_fp": cost_ratio,
        "likelihood_ratio_threshold": lr_threshold,
        "score_threshold": round(score_threshold, 4),
        "interpretation": (
            f"A2A score must exceed {score_threshold:.2%} to classify as A2A. "
            f"Below = default to human (safer)."
        ),
    }


def scenario_analysis():
    """Show how error costs affect classification threshold."""
    print("=== Asymmetric Error Cost Analysis ===\n")
    
    print("Error Costs:")
    for et, cost in COSTS.items():
        print(f"  {et.value}: {cost.description}")
        print(f"      Direct: {cost.cost_sol} SOL | Reversible: {cost.reversible} | Effective: {cost.effective_cost} SOL")
    
    print(f"\n  Cost ratio (FN/FP): {COSTS[ErrorType.FALSE_NEGATIVE].effective_cost / max(COSTS[ErrorType.FALSE_POSITIVE].effective_cost, 0.001):.0f}x")
    print(f"  → Conservative classification is CORRECT.\n")
    
    print("--- Threshold Analysis ---")
    for alpha in [0.01, 0.05, 0.10]:
        result = neyman_pearson_threshold(alpha=alpha)
        print(f"\n  α={alpha}: {result['interpretation']}")
        print(f"    LR threshold: {result['likelihood_ratio_threshold']:.1f}")
    
    print("\n--- Cost Ratio Sensitivity ---")
    for ratio in [1, 10, 100, 1000]:
        result = neyman_pearson_threshold(cost_ratio=ratio)
        print(f"  FN/FP = {ratio:>4}x → score threshold: {result['score_threshold']:.2%}")
    
    print("\n--- Key Insight ---")
    print("  Neyman-Pearson (1933): when errors have asymmetric costs,")
    print("  the optimal threshold shifts toward the cheaper error.")
    print("  Misclassifying A2A as human = slow (cheap).")
    print("  Misclassifying human as A2A = funds lost (expensive).")
    print("  → Default to human. Always.")
    print("  bro_agent: 'weakest link rule.'")


if __name__ == "__main__":
    scenario_analysis()
