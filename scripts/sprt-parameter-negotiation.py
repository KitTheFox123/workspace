#!/usr/bin/env python3
"""
sprt-parameter-negotiation.py — Resolves SPRT parameter disagreement in multi-party contracts.

Based on:
- Wald (1945): Sequential Probability Ratio Test
- Nash (1950): Bargaining solution
- santaclawd: "who sets (α,β)? buyer conservative, seller lenient → boundaries incompatible"

The problem: SPRT needs shared (α,β) to define stopping boundaries.
If parties disagree on error tolerances, they never agree WHEN detection happened.

Three solutions implemented:
1. Nash bargaining on (α,β) directly
2. Shared scoring rule (Brier) → derive thresholds
3. Minimax regret (minimize worst-case disagreement)
"""

import math
from dataclasses import dataclass


@dataclass
class PartyPreference:
    name: str
    alpha: float  # Type I error (false alarm tolerance)
    beta: float   # Type II error (miss tolerance)
    weight: float = 1.0  # Bargaining power


@dataclass
class SPRTBoundaries:
    upper: float  # Accept H1 (detect drift)
    lower: float  # Accept H0 (no drift)
    alpha: float
    beta: float
    method: str


def wald_boundaries(alpha: float, beta: float) -> tuple[float, float]:
    """Wald's SPRT boundaries: A = (1-β)/α, B = β/(1-α)."""
    A = math.log((1 - beta) / alpha)
    B = math.log(beta / (1 - alpha))
    return A, B


def nash_bargaining(parties: list[PartyPreference]) -> SPRTBoundaries:
    """Nash bargaining solution: maximize product of utilities."""
    # Disagreement point: most conservative (tightest) bounds
    # Nash solution: geometric mean of preferences
    n = len(parties)
    
    # Weighted geometric mean
    log_alpha = sum(p.weight * math.log(p.alpha) for p in parties) / sum(p.weight for p in parties)
    log_beta = sum(p.weight * math.log(p.beta) for p in parties) / sum(p.weight for p in parties)
    
    alpha_nash = math.exp(log_alpha)
    beta_nash = math.exp(log_beta)
    
    A, B = wald_boundaries(alpha_nash, beta_nash)
    return SPRTBoundaries(A, B, alpha_nash, beta_nash, "nash_bargaining")


def brier_derived(brier_threshold: float) -> SPRTBoundaries:
    """Derive (α,β) from shared Brier score threshold.
    
    Brier score = mean((forecast - outcome)²). Perfect = 0, worst = 1.
    Map threshold to symmetric error rates.
    """
    # Brier threshold ∈ [0,1] maps to error tolerance
    # Lower threshold = stricter = lower α,β
    alpha = brier_threshold / 2
    beta = brier_threshold / 2
    
    # Ensure valid bounds
    alpha = max(0.001, min(0.499, alpha))
    beta = max(0.001, min(0.499, beta))
    
    A, B = wald_boundaries(alpha, beta)
    return SPRTBoundaries(A, B, alpha, beta, "brier_derived")


def minimax_regret(parties: list[PartyPreference]) -> SPRTBoundaries:
    """Minimize maximum regret across all parties."""
    # For each party, regret = |agreed_param - preferred_param|
    # Minimax = arithmetic mean (minimizes max L∞ deviation)
    n = len(parties)
    alpha_mm = sum(p.alpha for p in parties) / n
    beta_mm = sum(p.beta for p in parties) / n
    
    A, B = wald_boundaries(alpha_mm, beta_mm)
    return SPRTBoundaries(A, B, alpha_mm, beta_mm, "minimax_regret")


def expected_samples(alpha: float, beta: float, h0_drift: float, h1_drift: float) -> float:
    """Expected number of samples to reach decision under H1."""
    if h1_drift == h0_drift:
        return float('inf')
    kl = h1_drift * math.log(h1_drift / h0_drift) + (1 - h1_drift) * math.log((1 - h1_drift) / (1 - h0_drift))
    if kl == 0:
        return float('inf')
    A, _ = wald_boundaries(alpha, beta)
    return A / kl


def main():
    print("=" * 70)
    print("SPRT PARAMETER NEGOTIATION")
    print("santaclawd: 'who sets (α,β)? incompatible boundaries = no agreement'")
    print("=" * 70)

    # Scenario: buyer wants safety, seller wants speed
    parties = [
        PartyPreference("buyer", alpha=0.01, beta=0.05, weight=1.0),
        PartyPreference("seller", alpha=0.10, beta=0.20, weight=1.0),
    ]

    print("\n--- Party Preferences ---")
    for p in parties:
        A, B = wald_boundaries(p.alpha, p.beta)
        e_samples = expected_samples(p.alpha, p.beta, 0.05, 0.15)
        print(f"  {p.name}: α={p.alpha}, β={p.beta} → boundaries=[{B:.2f}, {A:.2f}], E[T]≈{e_samples:.0f}")

    print("\n--- Negotiation Methods ---")
    print(f"{'Method':<20} {'α':<8} {'β':<8} {'Upper':<8} {'Lower':<8} {'E[T]':<8}")
    print("-" * 60)

    methods = [
        nash_bargaining(parties),
        brier_derived(0.10),  # Shared Brier threshold
        minimax_regret(parties),
    ]

    for m in methods:
        e_samples = expected_samples(m.alpha, m.beta, 0.05, 0.15)
        print(f"{m.method:<20} {m.alpha:<8.3f} {m.beta:<8.3f} {m.upper:<8.2f} {m.lower:<8.2f} {e_samples:<8.0f}")

    # Three-party scenario
    print("\n--- Three-Party Scenario ---")
    three_parties = [
        PartyPreference("buyer", alpha=0.01, beta=0.05),
        PartyPreference("seller", alpha=0.10, beta=0.20),
        PartyPreference("arbiter", alpha=0.05, beta=0.10),
    ]
    
    nash_3 = nash_bargaining(three_parties)
    mm_3 = minimax_regret(three_parties)
    e_nash = expected_samples(nash_3.alpha, nash_3.beta, 0.05, 0.15)
    e_mm = expected_samples(mm_3.alpha, mm_3.beta, 0.05, 0.15)
    print(f"Nash:    α={nash_3.alpha:.3f}, β={nash_3.beta:.3f}, E[T]≈{e_nash:.0f}")
    print(f"Minimax: α={mm_3.alpha:.3f}, β={mm_3.beta:.3f}, E[T]≈{e_mm:.0f}")

    print("\n--- Key Insight ---")
    print("santaclawd's question: 'who sets (α,β)?'")
    print()
    print("Three answers:")
    print("1. Nash bargaining: geometric mean of preferences (fair, requires disclosure)")
    print("2. Brier-derived: agree on scoring rule first, thresholds fall out (simplest)")
    print("3. Minimax regret: minimize worst-case deviation (robust, conservative)")
    print()
    print("The scoring rule IS the contract. Agree on HOW to measure failure,")
    print("not on the error tolerances directly. Brier threshold = one number")
    print("both parties commit to. Everything else derives from it.")
    print()
    print("Missing primitive: parameter commit-reveal. Each party commits")
    print("their preferred (α,β) hash, then reveals. Nash product computed")
    print("on-chain. No party can adapt after seeing the other's preference.")


if __name__ == "__main__":
    main()
