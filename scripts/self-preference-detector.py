#!/usr/bin/env python3
"""self-preference-detector.py — Detect LLM self-preference bias in cross-validation.

Based on Wataoka et al (2024, arXiv 2410.21819): LLMs prefer lower-perplexity
(more familiar) text. Same model family cross-validating = correlated bias.

Detects: perplexity-familiarity bias, same-family correlation, 
evaluation independence violations.

Usage:
    python3 self-preference-detector.py [--demo]
"""

import argparse
import json
import math
import random
from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class EvaluatorProfile:
    """An evaluator's bias profile."""
    name: str
    model_family: str
    training_lineage: str  # e.g., "openai", "anthropic", "meta"
    familiarity_bias: float  # 0-1, how much perplexity affects scoring
    
    
@dataclass  
class BiasReport:
    """Self-preference bias detection report."""
    evaluator_pair: tuple
    same_family: bool
    correlation: float  # Score correlation between evaluators
    independence_grade: str  # A-F
    bias_type: str  # "self-preference", "familiarity", "independent"
    recommendation: str


def simulate_scores(evaluator: EvaluatorProfile, texts: List[dict], n_texts: int = 20) -> List[float]:
    """Simulate evaluation scores with familiarity bias."""
    random.seed(hash(evaluator.name) % 2**32)
    scores = []
    for t in texts:
        # Base quality score
        base = t["quality"]
        # Familiarity bias: same lineage = lower perplexity = higher score
        if t["source_lineage"] == evaluator.training_lineage:
            bias = evaluator.familiarity_bias * 0.3  # Up to +0.3 for familiar text
        else:
            bias = -evaluator.familiarity_bias * 0.1  # Slight penalty for unfamiliar
        # Add noise
        noise = random.gauss(0, 0.05)
        scores.append(max(0, min(1, base + bias + noise)))
    return scores


def pearson_r(x: List[float], y: List[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = sum(x)/n, sum(y)/n
    sx = math.sqrt(sum((xi-mx)**2 for xi in x) / (n-1))
    sy = math.sqrt(sum((yi-my)**2 for yi in y) / (n-1))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((xi-mx)*(yi-my) for xi, yi in zip(x, y)) / ((n-1) * sx * sy)


def detect_bias(eval_a: EvaluatorProfile, eval_b: EvaluatorProfile, 
                texts: List[dict]) -> BiasReport:
    """Detect self-preference bias between two evaluators."""
    scores_a = simulate_scores(eval_a, texts)
    scores_b = simulate_scores(eval_b, texts)
    
    r = pearson_r(scores_a, scores_b)
    same_family = eval_a.training_lineage == eval_b.training_lineage
    
    # Grade independence
    if same_family and r > 0.8:
        grade = "F"
        bias_type = "self-preference"
        rec = "Replace one evaluator with different training lineage"
    elif same_family and r > 0.6:
        grade = "D"  
        bias_type = "familiarity"
        rec = "High correlation from shared training. Add diverse evaluator."
    elif r > 0.7:
        grade = "C"
        bias_type = "familiarity"
        rec = "Correlation higher than expected. Check for shared data sources."
    elif r > 0.5:
        grade = "B"
        bias_type = "independent"
        rec = "Acceptable independence. Monitor for drift."
    else:
        grade = "A"
        bias_type = "independent"
        rec = "Strong independence. Diverse evaluations."
    
    return BiasReport(
        evaluator_pair=(eval_a.name, eval_b.name),
        same_family=same_family,
        correlation=round(r, 3),
        independence_grade=grade,
        bias_type=bias_type,
        recommendation=rec
    )


def demo():
    """Run demo with different evaluator configurations."""
    # Define evaluators
    evaluators = [
        EvaluatorProfile("claude_a", "claude", "anthropic", 0.7),
        EvaluatorProfile("claude_b", "claude", "anthropic", 0.65),
        EvaluatorProfile("gpt4", "gpt", "openai", 0.6),
        EvaluatorProfile("llama", "llama", "meta", 0.5),
        EvaluatorProfile("human_expert", "human", "none", 0.1),
    ]
    
    # Generate test texts from different lineages
    random.seed(42)
    texts = []
    for lineage in ["anthropic", "openai", "meta", "human"]:
        for _ in range(5):
            texts.append({
                "quality": random.uniform(0.3, 0.9),
                "source_lineage": lineage,
            })
    
    print("=" * 60)
    print("SELF-PREFERENCE BIAS DETECTION")
    print("Wataoka et al (2024): perplexity familiarity → score inflation")
    print("=" * 60)
    print()
    
    # Test all pairs
    results = []
    for i, ea in enumerate(evaluators):
        for eb in evaluators[i+1:]:
            report = detect_bias(ea, eb, texts)
            results.append(report)
            flag = "⚠️" if report.independence_grade in ("D", "F") else "✅"
            print(f"{flag} [{report.independence_grade}] {ea.name} × {eb.name}")
            print(f"    r={report.correlation}, family={'SAME' if report.same_family else 'diff'}")
            print(f"    Type: {report.bias_type}")
            print(f"    Fix: {report.recommendation}")
            print()
    
    # Summary
    f_count = sum(1 for r in results if r.independence_grade in ("D", "F"))
    print("-" * 60)
    print(f"Pairs tested: {len(results)}")
    print(f"Independence violations: {f_count}")
    print(f"Key insight: same model family = correlated errors, not validation")
    print(f"Fix: require different training lineages for cross-validation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Self-preference bias detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
