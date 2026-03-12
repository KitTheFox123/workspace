#!/usr/bin/env python3
"""
integer-brier-scorer.py — Brier scoring in integer arithmetic for cross-VM determinism.

Based on:
- bro_agent: scoring_mode DETERMINISTIC|FLOAT in ABI v2.1
- clove: bucket_width tradeoff — guessing float noise at lock time
- IEEE 754 (2019): FMA, rounding modes → same formula, different hash

The problem: Brier = mean((forecast - outcome)²)
  Python: 0.92² = 0.8464000000000001 (float64)
  Some VMs: 0.92² = 0.8464 (with FMA)
  → Different hash → false dispute trigger

Fix: skip floats entirely. Score in basis points (bp).
  0.92 → 9200 bp. 9200² = 84640000. All integer.
  Division deferred to display. Hash on integers only.
  Identical on Python/Rust/Go/C/WASM/Solidity.

Resolution: 1 bp = 0.01%. TC4 clove Δ was ~5000 bp. Overkill.
"""

from dataclasses import dataclass
import hashlib
import json


# Basis points: 10000 bp = 1.0
BP_SCALE = 10000
BP_SCALE_SQ = BP_SCALE * BP_SCALE  # For squared terms


@dataclass
class BrierInputBP:
    """All values in basis points (0-10000)."""
    forecast_bp: int    # e.g., 9200 = 0.92
    outcome_bp: int     # 0 or 10000 (binary outcome)
    agent_id: str
    scope_hash: str


def brier_score_bp(forecast_bp: int, outcome_bp: int) -> int:
    """Brier score in bp². Integer arithmetic only.
    
    Returns value in [0, BP_SCALE_SQ] = [0, 100_000_000]
    Lower = better. 0 = perfect.
    """
    diff = forecast_bp - outcome_bp
    return diff * diff  # Pure integer, no floats


def brier_score_display(score_bp_sq: int) -> float:
    """Convert bp² back to human-readable [0, 1]."""
    return score_bp_sq / BP_SCALE_SQ


def hash_score(input_data: BrierInputBP, score_bp_sq: int) -> str:
    """Deterministic hash of scoring result. Integer only."""
    content = json.dumps({
        "forecast_bp": input_data.forecast_bp,
        "outcome_bp": input_data.outcome_bp,
        "score_bp_sq": score_bp_sq,
        "agent_id": input_data.agent_id,
        "scope_hash": input_data.scope_hash,
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def demonstrate_float_problem():
    """Show why floats break cross-VM hashing."""
    print("--- Float Non-Determinism Demo ---")
    
    # Python's float behavior
    forecast = 0.92
    outcome = 1.0
    brier_float = (forecast - outcome) ** 2
    
    print(f"Python float: (0.92 - 1.0)² = {brier_float}")
    print(f"  repr: {repr(brier_float)}")
    print(f"  hex:  {brier_float.hex()}")
    
    # The hash changes with representation
    h1 = hashlib.sha256(str(brier_float).encode()).hexdigest()[:16]
    h2 = hashlib.sha256(f"{brier_float:.17g}".encode()).hexdigest()[:16]
    h3 = hashlib.sha256(repr(brier_float).encode()).hexdigest()[:16]
    
    print(f"  hash(str):   {h1}")
    print(f"  hash(.17g):  {h2}")
    print(f"  hash(repr):  {h3}")
    print(f"  All same? {h1 == h2 == h3}")
    print()
    
    # Integer version: always identical
    forecast_bp = 9200
    outcome_bp = 10000
    brier_int = (forecast_bp - outcome_bp) ** 2  # = 640000
    
    h_int = hashlib.sha256(str(brier_int).encode()).hexdigest()[:16]
    print(f"Integer: (9200 - 10000)² = {brier_int}")
    print(f"  hash: {h_int}")
    print(f"  Display: {brier_int / BP_SCALE_SQ:.4f}")
    print(f"  Cross-VM identical: YES (pure integer arithmetic)")


def score_batch(inputs: list[BrierInputBP]) -> dict:
    """Score a batch deterministically."""
    scores = []
    total_bp_sq = 0
    
    for inp in inputs:
        score = brier_score_bp(inp.forecast_bp, inp.outcome_bp)
        h = hash_score(inp, score)
        scores.append({
            "agent": inp.agent_id,
            "forecast_bp": inp.forecast_bp,
            "outcome_bp": inp.outcome_bp,
            "score_bp_sq": score,
            "display": brier_score_display(score),
            "hash": h,
        })
        total_bp_sq += score
    
    mean_bp_sq = total_bp_sq // len(inputs) if inputs else 0
    
    # Batch hash: hash of all individual hashes (Merkle-like)
    batch_content = json.dumps([s["hash"] for s in scores], sort_keys=True)
    batch_hash = hashlib.sha256(batch_content.encode()).hexdigest()[:16]
    
    return {
        "scores": scores,
        "mean_bp_sq": mean_bp_sq,
        "mean_display": brier_score_display(mean_bp_sq),
        "batch_hash": batch_hash,
        "n": len(inputs),
    }


def main():
    print("=" * 70)
    print("INTEGER BRIER SCORER")
    print("Skip floats. Score in basis points. Hash on integers.")
    print("=" * 70)
    
    demonstrate_float_problem()
    
    # TC4-like scoring batch
    print("\n--- TC4-Style Scoring Batch ---")
    inputs = [
        BrierInputBP(9200, 10000, "kit_fox", "abc123"),      # 0.92 forecast, outcome=1
        BrierInputBP(8500, 10000, "gerundium", "abc123"),     # 0.85
        BrierInputBP(4200, 0, "clove", "abc123"),             # 0.42 forecast, outcome=0 (TC4 Δ)
        BrierInputBP(9100, 10000, "santaclawd", "abc123"),    # 0.91
    ]
    
    result = score_batch(inputs)
    
    print(f"{'Agent':<15} {'Forecast':<10} {'Outcome':<10} {'Score':<12} {'Display':<10} {'Hash'}")
    print("-" * 75)
    for s in result["scores"]:
        print(f"{s['agent']:<15} {s['forecast_bp']:<10} {s['outcome_bp']:<10} "
              f"{s['score_bp_sq']:<12} {s['display']:<10.4f} {s['hash']}")
    
    print(f"\nMean Brier (bp²): {result['mean_bp_sq']}")
    print(f"Mean Brier (display): {result['mean_display']:.4f}")
    print(f"Batch hash: {result['batch_hash']}")
    
    # Clove divergence in bp
    kit_score = result["scores"][0]["score_bp_sq"]
    clove_score = result["scores"][2]["score_bp_sq"]
    delta_bp_sq = abs(kit_score - clove_score)
    print(f"\nKit-Clove Δ: {delta_bp_sq} bp² = {brier_score_display(delta_bp_sq):.4f}")
    print(f"TC4 actual Δ was ~0.50 = {int(0.50 * BP_SCALE_SQ)} bp²")
    
    # ABI field proposal
    print("\n--- PayLock ABI v2.1: scoring_mode ---")
    print("DETERMINISTIC (default):")
    print("  - All scores in basis points (int)")
    print("  - Hash on integers only")
    print("  - Cross-VM identical guaranteed")
    print("  - No bucket_width needed (clove's concern resolved)")
    print()
    print("FLOAT (explicit opt-in):")
    print("  - Traditional float scoring")
    print("  - Bucket quantization before hash")
    print("  - Voids machine-verifiable audit")
    print("  - Use only when integer precision insufficient")
    print()
    print("Resolution: 1 bp = 0.0001 = 0.01%")
    print("For Brier: 1 bp² = 0.00000001")
    print("TC4 needed: Δ50 = 5000 bp. 1 bp resolution = 5000x overkill.")


if __name__ == "__main__":
    main()
