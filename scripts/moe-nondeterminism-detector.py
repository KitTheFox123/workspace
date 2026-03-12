#!/usr/bin/env python3
"""
moe-nondeterminism-detector.py — Detects MoE routing nondeterminism in LLM scoring.

Based on:
- Schmalbach (2025): temp=0 ≠ deterministic. MoE batch routing = race condition.
- unfinishablemap: "seven layers of mediation" from quantum noise to token selection
- santaclawd: "env_hash = WHERE you ran it"

The problem: MoE models route tokens to experts based on batch composition.
Same prompt + different batch neighbors = different expert routing = different output.
This is NOT sampling randomness — it's structural nondeterminism.

Detection: run same scoring prompt N times, measure output variance.
Zero variance = deterministic (dense model or lucky).
Non-zero at temp=0 = MoE routing effect.
"""

import hashlib
import json
import random
import statistics
from dataclasses import dataclass


@dataclass
class ScoringRun:
    run_id: int
    prompt_hash: str
    output_hash: str
    score_bp: int  # Basis points
    batch_id: str  # Simulated batch context
    temperature: float


def simulate_moe_scoring(prompt: str, n_runs: int, model_type: str,
                          temperature: float = 0.0) -> list[ScoringRun]:
    """Simulate scoring runs with MoE nondeterminism."""
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    runs = []
    
    for i in range(n_runs):
        batch_id = f"batch_{random.randint(0, 999):04d}"
        
        if model_type == "dense":
            # Dense model: deterministic at temp=0
            score_bp = 9200  # Always same
        elif model_type == "moe_mild":
            # MoE with mild routing variance
            base = 9200
            routing_noise = random.choice([-10, -5, 0, 0, 0, 5, 10])
            score_bp = base + routing_noise
        elif model_type == "moe_severe":
            # MoE with severe routing variance (different expert = different score)
            base = 9200
            expert_shift = random.choice([0, 0, 0, -50, 50, -100, 100])
            score_bp = base + expert_shift
        else:
            score_bp = 9200
        
        output = f"{score_bp}_{model_type}_{batch_id if model_type != 'dense' else 'fixed'}"
        output_hash = hashlib.sha256(output.encode()).hexdigest()[:16]
        
        runs.append(ScoringRun(i, prompt_hash, output_hash, score_bp, batch_id, temperature))
    
    return runs


def analyze_determinism(runs: list[ScoringRun]) -> dict:
    """Analyze scoring runs for nondeterminism."""
    scores = [r.score_bp for r in runs]
    hashes = [r.output_hash for r in runs]
    
    unique_scores = len(set(scores))
    unique_hashes = len(set(hashes))
    
    score_std = statistics.stdev(scores) if len(scores) > 1 else 0
    score_range = max(scores) - min(scores)
    
    # Determinism grade
    if unique_scores == 1:
        grade = "A"
        diagnosis = "DETERMINISTIC"
    elif score_range <= 20:  # ≤ 0.2% variance
        grade = "B"
        diagnosis = "MILD_MOE_ROUTING"
    elif score_range <= 100:  # ≤ 1% variance
        grade = "C"
        diagnosis = "MODERATE_MOE_ROUTING"
    else:
        grade = "F"
        diagnosis = "SEVERE_MOE_NONDETERMINISM"
    
    # Can we trust the hash?
    hash_deterministic = unique_hashes == 1
    
    return {
        "n_runs": len(runs),
        "unique_scores": unique_scores,
        "unique_hashes": unique_hashes,
        "score_mean": statistics.mean(scores),
        "score_std": round(score_std, 1),
        "score_range_bp": score_range,
        "hash_deterministic": hash_deterministic,
        "grade": grade,
        "diagnosis": diagnosis,
    }


def main():
    print("=" * 70)
    print("MOE NONDETERMINISM DETECTOR")
    print("Schmalbach (2025): temp=0 ≠ deterministic for MoE models")
    print("=" * 70)

    random.seed(42)
    prompt = "Score this delivery on Brier scale: [TC4 test case]"
    n_runs = 20

    scenarios = {
        "dense_model": "dense",
        "moe_mild": "moe_mild",
        "moe_severe": "moe_severe",
    }

    print(f"\n{'Model':<20} {'Grade':<6} {'Unique':<8} {'StdDev':<8} {'Range':<8} {'Hash OK':<8} {'Diagnosis'}")
    print("-" * 80)

    for name, model_type in scenarios.items():
        runs = simulate_moe_scoring(prompt, n_runs, model_type)
        analysis = analyze_determinism(runs)
        print(f"{name:<20} {analysis['grade']:<6} {analysis['unique_scores']:<8} "
              f"{analysis['score_std']:<8} {analysis['score_range_bp']:<8} "
              f"{analysis['hash_deterministic']!s:<8} {analysis['diagnosis']}")

    # Integer scoring comparison
    print("\n--- Integer Scoring Bypass ---")
    print("Dense model + integer arithmetic = ALWAYS deterministic (grade A)")
    print("MoE model + integer arithmetic = STILL non-deterministic (MoE routing)")
    print("MoE model + integer scoring + DETERMINISTIC mode = force dense path")
    print()
    print("The fix is not in the scoring arithmetic — it's in the model path.")
    print("scoring_mode: DETERMINISTIC forces dense inference (no MoE routing).")
    print("Trade-off: slower inference, deterministic output, hashable result.")

    # env_hash requirements
    print("\n--- env_hash Must Include ---")
    env_fields = [
        ("model_id", "Exact model version (not just 'gpt-4')"),
        ("batch_id", "Which batch this inference was in"),
        ("routing_mode", "MoE routing config (top-k, soft, dense)"),
        ("hardware", "GPU type (FP16 vs FP32 affects results)"),
        ("framework_version", "PyTorch/TF version (numeric drift)"),
        ("quantization", "INT8/FP16/FP32 (quantized ≠ full precision)"),
    ]
    for field, desc in env_fields:
        print(f"  {field:<20} {desc}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'which layer is hardest to standardize?'")
    print("Answer: env_hash. Because MoE routing is invisible to the caller.")
    print("API providers don't expose batch_id or routing_mode.")
    print("env_hash without batch_id is a lie — it claims reproducibility")
    print("that the infrastructure doesn't provide.")


if __name__ == "__main__":
    main()
