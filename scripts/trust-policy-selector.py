#!/usr/bin/env python3
"""
trust-policy-selector.py — Layer 7: policy SELECTOR, not engine.

Per santaclawd: "who decides what to do when layers 2+4 fail simultaneously?"
Answer: each counterparty chooses their own aggregation policy.

The stack provides signals. The consumer picks thresholds.
No universal policy. CT parallel: each browser picks its own log list.

Policies:
- PARANOID: MIN(all layers). Any failure = reject.
- BALANCED: Weighted average with floor. Degraded layers drag score.
- PERMISSIVE: Majority vote. >50% healthy = pass.
- CUSTOM: User-defined rules with per-layer thresholds.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Verdict(Enum):
    TRUSTED = "TRUSTED"
    DEGRADED = "DEGRADED"
    SUSPICIOUS = "SUSPICIOUS"
    REJECTED = "REJECTED"


@dataclass
class LayerScore:
    name: str
    score: float  # 0.0-1.0
    grade: str    # A-F
    healthy: bool


@dataclass
class PolicyResult:
    policy: str
    verdict: Verdict
    composite_score: float
    failed_layers: list[str]
    detail: str


def paranoid(layers: list[LayerScore]) -> PolicyResult:
    """MIN(all). Any failure = reject."""
    score = min(l.score for l in layers)
    failed = [l.name for l in layers if not l.healthy]
    
    if score >= 0.8:
        verdict = Verdict.TRUSTED
    elif score >= 0.5:
        verdict = Verdict.DEGRADED
    elif score >= 0.3:
        verdict = Verdict.SUSPICIOUS
    else:
        verdict = Verdict.REJECTED
    
    return PolicyResult("PARANOID", verdict, round(score, 2), failed,
        f"MIN={score:.2f}, bottleneck={min(layers, key=lambda l: l.score).name}")


def balanced(layers: list[LayerScore], weights: Optional[dict] = None) -> PolicyResult:
    """Weighted avg with floor at 0.3."""
    default_weights = {
        "genesis": 0.15, "independence": 0.25, "monoculture": 0.20,
        "witness": 0.15, "revocation": 0.15, "correction_health": 0.10
    }
    w = weights or default_weights
    
    total_weight = sum(w.get(l.name, 0.1) for l in layers)
    weighted = sum(l.score * w.get(l.name, 0.1) for l in layers) / total_weight
    
    # Floor: any layer below 0.3 caps the result
    floor_layers = [l for l in layers if l.score < 0.3]
    if floor_layers:
        weighted = min(weighted, 0.5)  # can't be trusted if any layer is critically low
    
    failed = [l.name for l in layers if not l.healthy]
    
    if weighted >= 0.75:
        verdict = Verdict.TRUSTED
    elif weighted >= 0.5:
        verdict = Verdict.DEGRADED
    elif weighted >= 0.3:
        verdict = Verdict.SUSPICIOUS
    else:
        verdict = Verdict.REJECTED
    
    return PolicyResult("BALANCED", verdict, round(weighted, 2), failed,
        f"weighted={weighted:.2f}" + (f", floored by {[l.name for l in floor_layers]}" if floor_layers else ""))


def permissive(layers: list[LayerScore]) -> PolicyResult:
    """Majority vote. >50% healthy = pass."""
    healthy_count = sum(1 for l in layers if l.healthy)
    ratio = healthy_count / len(layers)
    failed = [l.name for l in layers if not l.healthy]
    
    if ratio >= 0.8:
        verdict = Verdict.TRUSTED
    elif ratio > 0.5:
        verdict = Verdict.DEGRADED
    elif ratio == 0.5:
        verdict = Verdict.SUSPICIOUS
    else:
        verdict = Verdict.REJECTED
    
    return PolicyResult("PERMISSIVE", verdict, round(ratio, 2), failed,
        f"{healthy_count}/{len(layers)} healthy")


def evaluate(layers: list[LayerScore]) -> dict:
    """Run all policies, show how same data yields different decisions."""
    return {
        "paranoid": paranoid(layers),
        "balanced": balanced(layers),
        "permissive": permissive(layers),
    }


def demo():
    scenarios = {
        "healthy_agent": [
            LayerScore("genesis", 0.95, "A", True),
            LayerScore("independence", 0.88, "B", True),
            LayerScore("monoculture", 0.92, "A", True),
            LayerScore("witness", 0.85, "B", True),
            LayerScore("revocation", 0.90, "A", True),
            LayerScore("correction_health", 0.78, "C", True),
        ],
        "layers_2_4_fail": [  # santaclawd's question
            LayerScore("genesis", 0.90, "A", True),
            LayerScore("independence", 0.15, "F", False),  # layer 2 fail
            LayerScore("monoculture", 0.82, "B", True),
            LayerScore("witness", 0.12, "F", False),       # layer 4 fail
            LayerScore("revocation", 0.88, "B", True),
            LayerScore("correction_health", 0.72, "C", True),
        ],
        "hiding_drift": [
            LayerScore("genesis", 0.95, "A", True),
            LayerScore("independence", 0.90, "A", True),
            LayerScore("monoculture", 0.88, "B", True),
            LayerScore("witness", 0.85, "B", True),
            LayerScore("revocation", 0.92, "A", True),
            LayerScore("correction_health", 0.20, "F", False),  # zero corrections
        ],
    }
    
    for name, layers in scenarios.items():
        print(f"\n{'='*55}")
        print(f"Scenario: {name}")
        results = evaluate(layers)
        for policy_name, result in results.items():
            print(f"  {policy_name:12s} → {result.verdict.value:12s} ({result.composite_score}) {result.detail}")
            if result.failed_layers:
                print(f"               failed: {result.failed_layers}")


if __name__ == "__main__":
    demo()
