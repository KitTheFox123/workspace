#!/usr/bin/env python3
"""
adversarial-bench.py — Adversarial benchmark validator.

Mutation testing for agent benchmarks: does the score survive
an adversary trying to break it? If it only survives cooperative
evaluation, it's theater.

Thomas & Uminsky (2022, Patterns): metric optimization without
domain constraints = gaming the proxy.
"""

import hashlib
import json
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class AttackType(Enum):
    REPHRASE = "rephrase"           # Same question, different words
    CONTRADICT = "contradict"       # Opposite framing
    PARTIAL_CONTEXT = "partial"     # Remove key info
    ADVERSARIAL_SUFFIX = "suffix"   # Add misleading context
    ORDER_SHUFFLE = "shuffle"       # Reorder options/steps


@dataclass
class BenchmarkItem:
    question: str
    expected: str
    category: str
    difficulty: float  # 0-1


@dataclass
class AttackResult:
    original_score: float
    attacked_score: float
    attack_type: AttackType
    survived: bool
    delta: float

    @property
    def robustness(self) -> float:
        """1.0 = perfectly robust, 0.0 = completely fragile"""
        if self.original_score == 0:
            return 1.0  # Can't break what's already broken
        return max(0, self.attacked_score / self.original_score)


@dataclass
class BenchmarkAudit:
    """Full adversarial audit of a benchmark score."""
    benchmark_name: str
    original_score: float
    attack_results: list[AttackResult] = field(default_factory=list)

    @property
    def robust_score(self) -> float:
        """Score that survives adversarial evaluation."""
        if not self.attack_results:
            return self.original_score
        avg_robustness = sum(r.robustness for r in self.attack_results) / len(self.attack_results)
        return self.original_score * avg_robustness

    @property
    def inflation_ratio(self) -> float:
        """How much the benchmark is inflated. >1 = gaming detected."""
        if self.robust_score == 0:
            return float('inf')
        return self.original_score / self.robust_score

    @property
    def grade(self) -> str:
        r = self.inflation_ratio
        if r <= 1.05: return "A"  # Robust
        if r <= 1.15: return "B"  # Minor inflation
        if r <= 1.30: return "C"  # Moderate gaming
        if r <= 1.50: return "D"  # Significant gaming
        return "F"                 # Theater

    def summary(self) -> dict:
        return {
            "benchmark": self.benchmark_name,
            "original_score": round(self.original_score, 3),
            "robust_score": round(self.robust_score, 3),
            "inflation_ratio": round(self.inflation_ratio, 2),
            "grade": self.grade,
            "attacks_run": len(self.attack_results),
            "attacks_survived": sum(1 for r in self.attack_results if r.survived),
            "weakest_attack": min(
                self.attack_results, key=lambda r: r.robustness
            ).attack_type.value if self.attack_results else None,
        }


def simulate_attack(original_score: float, attack: AttackType) -> float:
    """
    Simulate score degradation under attack.
    In production: actually re-run the benchmark with adversarial variants.
    """
    # Different attacks have different expected impact
    impact = {
        AttackType.REPHRASE: random.gauss(0.05, 0.03),       # Small
        AttackType.CONTRADICT: random.gauss(0.15, 0.08),     # Medium
        AttackType.PARTIAL_CONTEXT: random.gauss(0.20, 0.10), # Large
        AttackType.ADVERSARIAL_SUFFIX: random.gauss(0.25, 0.12), # Large
        AttackType.ORDER_SHUFFLE: random.gauss(0.08, 0.04),  # Small
    }
    degradation = max(0, impact[attack])
    return max(0, original_score * (1 - degradation))


def audit_benchmark(name: str, original_score: float, 
                    n_attacks: int = 5) -> BenchmarkAudit:
    """Run adversarial audit on a benchmark score."""
    audit = BenchmarkAudit(benchmark_name=name, original_score=original_score)
    
    for attack_type in AttackType:
        for _ in range(n_attacks):
            attacked = simulate_attack(original_score, attack_type)
            survived = attacked >= original_score * 0.90  # 10% tolerance
            result = AttackResult(
                original_score=original_score,
                attacked_score=attacked,
                attack_type=attack_type,
                survived=survived,
                delta=original_score - attacked,
            )
            audit.attack_results.append(result)
    
    return audit


def demo():
    random.seed(42)
    print("=== Adversarial Benchmark Validator ===\n")
    
    scenarios = [
        ("Robust Agent (real capability)", 0.85),
        ("Benchmark Gamer (inflated)", 0.95),
        ("Mediocre but Honest", 0.60),
    ]
    
    for name, score in scenarios:
        audit = audit_benchmark(name, score, n_attacks=3)
        s = audit.summary()
        print(f"📋 {s['benchmark']}")
        print(f"   Original: {s['original_score']:.1%}  →  Robust: {s['robust_score']:.1%}")
        print(f"   Inflation: {s['inflation_ratio']:.2f}x  Grade: {s['grade']}")
        print(f"   Survived: {s['attacks_survived']}/{s['attacks_run']} attacks")
        print(f"   Weakest against: {s['weakest_attack']}")
        print()
    
    print("--- Goodhart's Law Applied ---")
    print("Benchmark score = proxy. Robust score = reality.")
    print("Inflation ratio > 1.3 = gaming detected.")
    print("The fix: adversarial evaluation where the benchmark FIGHTS BACK.")
    print()
    print("--- Grade Scale ---")
    print("A (≤1.05x): Score survives adversarial pressure")
    print("B (≤1.15x): Minor inflation, mostly real")
    print("C (≤1.30x): Moderate gaming, discount needed")
    print("D (≤1.50x): Significant gaming, score unreliable")
    print("F (>1.50x): Theater. Score measures benchmark skill, not capability.")


if __name__ == "__main__":
    demo()
