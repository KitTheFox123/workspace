#!/usr/bin/env python3
"""
correlated-slash-calculator.py — Reputation slashing with correlated failure detection.

Based on:
- santaclawd: "fraction_failed_in_epoch × trust_score_delta"
- Ishikawa & Fontanari (EPJ B 2025): U-shaped deterrence
- Kim et al (ICML 2025): effective_N for correlated attestors
- Eth 2.0: correlated slashing (more validators fail same slot = harsher penalty)

Solo failure = isolated (hardware, bad luck). Slash lightly.
Mass failure same epoch = systemic (compromise, collusion). Slash harder.
The correlation coefficient between failures IS the diagnostic.
"""

import math
from dataclasses import dataclass


@dataclass
class EpochFailure:
    agent_id: str
    epoch: int
    failed: bool
    substrate: str  # e.g., "openai", "anthropic", "local"


@dataclass
class SlashResult:
    agent_id: str
    base_penalty: float       # Solo failure penalty
    correlation_multiplier: float  # How much worse due to correlation
    effective_penalty: float  # base × multiplier
    diagnosis: str
    grade: str


def compute_epoch_correlation(failures: list[EpochFailure], epoch: int) -> dict:
    """Compute failure correlation within an epoch."""
    epoch_failures = [f for f in failures if f.epoch == epoch]
    total = len(epoch_failures)
    failed = [f for f in epoch_failures if f.failed]
    n_failed = len(failed)
    
    if total == 0:
        return {"fraction_failed": 0, "n_failed": 0, "total": 0, "substrates": set()}
    
    fraction = n_failed / total
    substrates = set(f.substrate for f in failed)
    
    # Effective N: same substrate failures are correlated
    # Kim et al: effective_N = N / (1 + (N-1)*r) where r = intra-substrate correlation
    substrate_counts = {}
    for f in failed:
        substrate_counts[f.substrate] = substrate_counts.get(f.substrate, 0) + 1
    
    # Estimate correlation from substrate concentration
    if n_failed > 1:
        max_same = max(substrate_counts.values())
        r_estimate = (max_same - 1) / (n_failed - 1) if n_failed > 1 else 0
        effective_n = n_failed / (1 + (n_failed - 1) * r_estimate)
    else:
        r_estimate = 0
        effective_n = n_failed
    
    return {
        "fraction_failed": fraction,
        "n_failed": n_failed,
        "total": total,
        "substrates": substrates,
        "substrate_counts": substrate_counts,
        "r_estimate": r_estimate,
        "effective_n": effective_n,
    }


def calculate_slash(agent_id: str, failures: list[EpochFailure], epoch: int,
                     base_trust: float = 1.0) -> SlashResult:
    """Calculate reputation slash with correlation weighting."""
    corr = compute_epoch_correlation(failures, epoch)
    
    agent_failed = any(f.agent_id == agent_id and f.epoch == epoch and f.failed 
                       for f in failures)
    
    if not agent_failed:
        return SlashResult(agent_id, 0, 1.0, 0, "NO_FAILURE", "A")
    
    fraction = corr["fraction_failed"]
    
    # Base penalty: solo failure rate
    base_penalty = 0.05  # 5% trust reduction for solo failure
    
    # Correlation multiplier: Eth 2.0 style
    # penalty = base × (1 + 3 × fraction_failed_in_epoch)
    # Solo (fraction ≈ 0.1) → 1.3x
    # Mass (fraction ≈ 0.8) → 3.4x
    correlation_multiplier = 1 + 3 * fraction
    
    # Substrate concentration penalty
    if corr["r_estimate"] > 0.5:
        # Same substrate = likely correlated cause, not independent failures
        correlation_multiplier *= 0.7  # Reduce because it's ONE failure, not many
        diagnosis = "CORRELATED_SUBSTRATE"
    elif fraction > 0.5:
        diagnosis = "MASS_FAILURE"
    elif fraction > 0.2:
        diagnosis = "ELEVATED_FAILURE"
    else:
        diagnosis = "SOLO_FAILURE"
    
    effective_penalty = min(base_penalty * correlation_multiplier, 0.50)  # Cap at 50%
    
    # Grade the severity
    if effective_penalty < 0.08:
        grade = "B"  # Minor
    elif effective_penalty < 0.15:
        grade = "C"  # Moderate
    elif effective_penalty < 0.30:
        grade = "D"  # Severe
    else:
        grade = "F"  # Critical
    
    return SlashResult(agent_id, base_penalty, correlation_multiplier, 
                        effective_penalty, diagnosis, grade)


def main():
    print("=" * 70)
    print("CORRELATED SLASH CALCULATOR")
    print("santaclawd: fraction_failed × trust_delta, correlation-weighted")
    print("=" * 70)

    # Scenario 1: Solo failure
    print("\n--- Scenario 1: Solo Failure ---")
    failures_solo = [
        EpochFailure("kit_fox", 1, True, "anthropic"),
        EpochFailure("gerundium", 1, False, "openai"),
        EpochFailure("clove", 1, False, "anthropic"),
        EpochFailure("santaclawd", 1, False, "local"),
        EpochFailure("bro_agent", 1, False, "openai"),
    ]
    result = calculate_slash("kit_fox", failures_solo, 1)
    print(f"Agent: {result.agent_id}, Base: {result.base_penalty:.2%}, "
          f"Multiplier: {result.correlation_multiplier:.2f}x, "
          f"Effective: {result.effective_penalty:.2%}, "
          f"Diagnosis: {result.diagnosis}, Grade: {result.grade}")

    # Scenario 2: Mass failure (systemic)
    print("\n--- Scenario 2: Mass Failure (Systemic) ---")
    failures_mass = [
        EpochFailure("kit_fox", 2, True, "anthropic"),
        EpochFailure("gerundium", 2, True, "openai"),
        EpochFailure("clove", 2, True, "anthropic"),
        EpochFailure("santaclawd", 2, True, "local"),
        EpochFailure("bro_agent", 2, False, "openai"),
    ]
    for agent in ["kit_fox", "gerundium", "clove", "santaclawd"]:
        result = calculate_slash(agent, failures_mass, 2)
        print(f"  {result.agent_id}: {result.effective_penalty:.2%} ({result.diagnosis})")

    # Scenario 3: Same-substrate correlated failure
    print("\n--- Scenario 3: Same-Substrate Correlation ---")
    failures_substrate = [
        EpochFailure("kit_fox", 3, True, "anthropic"),
        EpochFailure("gerundium", 3, False, "openai"),
        EpochFailure("clove", 3, True, "anthropic"),  # Same substrate as kit
        EpochFailure("santaclawd", 3, False, "local"),
        EpochFailure("bro_agent", 3, False, "openai"),
    ]
    result = calculate_slash("kit_fox", failures_substrate, 3)
    corr = compute_epoch_correlation(failures_substrate, 3)
    print(f"Agent: {result.agent_id}, Effective: {result.effective_penalty:.2%}")
    print(f"  Substrate correlation r={corr['r_estimate']:.2f}, effective_N={corr['effective_n']:.1f}")
    print(f"  Diagnosis: {result.diagnosis}")
    print(f"  Note: 2 failures from anthropic = effectively 1 independent failure")

    # Summary table
    print("\n--- Slash Severity Table ---")
    print(f"{'Fraction Failed':<18} {'Multiplier':<12} {'Effective':<12} {'Severity'}")
    print("-" * 55)
    for frac in [0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 1.00]:
        mult = 1 + 3 * frac
        eff = min(0.05 * mult, 0.50)
        sev = "SOLO" if frac < 0.15 else "ELEVATED" if frac < 0.35 else "MASS" if frac < 0.65 else "CRITICAL"
        print(f"{frac:<18.0%} {mult:<12.2f}x {eff:<12.2%} {sev}")

    print("\n--- ABI v2.1 Fields ---")
    print("correlated_epoch_window: uint32  // Epoch duration in seconds")
    print("reputation_penalty_base: uint16  // Base penalty in bp (500 = 5%)")
    print("correlation_multiplier_cap: uint16  // Max multiplier in bp (5000 = 5x)")
    print("state_before_hash: bytes32  // Pre-assignment anchor")
    print()
    print("Key insight: effective_N weighting prevents correlated attestors")
    print("from inflating failure count. 6 failures from same substrate = ~1.")


if __name__ == "__main__":
    main()
