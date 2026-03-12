#!/usr/bin/env python3
"""
determinism-constraint-checker.py — Checks scoring rules for cross-VM determinism.

Based on:
- Dawson (2013): IEEE 754 guarantees add/sub/mul/div/sqrt. Transcendentals NOT guaranteed.
- santaclawd: "same rule, same input — different float rounding across VMs → different hashes"
- IEEE 754-2008 §11: "possible to write programs that produce identical results"

Three scoring modes for ABI v2.1:
- DETERMINISTIC: basic IEEE 754 ops only, trace reproducible across VMs
- PROBABILISTIC: LLM/sampling, trace proves process not output
- HYBRID: deterministic scoring of probabilistic components

This tool: analyze a scoring rule for deterministic ops, flag non-deterministic ones.
"""

import ast
import sys
from dataclasses import dataclass
from enum import Enum


class ScoringMode(Enum):
    DETERMINISTIC = "deterministic"
    PROBABILISTIC = "probabilistic"
    HYBRID = "hybrid"


# IEEE 754 guaranteed deterministic operations
DETERMINISTIC_OPS = {
    "add", "sub", "mul", "div", "sqrt",  # Basic arithmetic
    "abs", "neg", "min", "max",           # Comparison/selection
    "floor", "ceil", "round", "trunc",    # Rounding (with mode)
    "fma",                                 # Fused multiply-add
}

# Non-deterministic across VMs (transcendental functions)
NONDETERMINISTIC_OPS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "exp", "exp2", "log", "log2", "log10",
    "pow", "hypot",
    "sinh", "cosh", "tanh",
    "erf", "erfc", "gamma", "lgamma",
}

# Python math module function mapping
PYTHON_MATH_NONDET = {
    "math.sin", "math.cos", "math.tan", "math.asin", "math.acos", "math.atan", "math.atan2",
    "math.exp", "math.exp2", "math.log", "math.log2", "math.log10",
    "math.pow", "math.hypot",
    "math.sinh", "math.cosh", "math.tanh",
    "math.erf", "math.erfc", "math.gamma", "math.lgamma",
}


@dataclass
class DeterminismReport:
    rule_name: str
    mode: ScoringMode
    deterministic_ops: list[str]
    nondeterministic_ops: list[str]
    grade: str
    diagnosis: str
    fix: str


def analyze_rule(rule_name: str, rule_code: str) -> DeterminismReport:
    """Analyze scoring rule source for determinism."""
    det_ops = []
    nondet_ops = []

    try:
        tree = ast.parse(rule_code)
    except SyntaxError:
        return DeterminismReport(rule_name, ScoringMode.PROBABILISTIC,
                                 [], ["PARSE_ERROR"], "F", "UNPARSEABLE", "Fix syntax")

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    func_name = f"{node.func.value.id}.{node.func.attr}"
                else:
                    func_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id

            if func_name in PYTHON_MATH_NONDET or func_name in NONDETERMINISTIC_OPS:
                nondet_ops.append(func_name)
            elif func_name:
                det_ops.append(func_name)

        # Check for ** operator (power = non-deterministic for non-integer exponents)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            nondet_ops.append("pow_operator")

    # Determine mode and grade
    if not nondet_ops:
        return DeterminismReport(rule_name, ScoringMode.DETERMINISTIC,
                                 det_ops, nondet_ops, "A",
                                 "FULLY_DETERMINISTIC",
                                 "No changes needed — trace reproducible across VMs")
    elif len(nondet_ops) <= 2 and len(det_ops) > len(nondet_ops):
        return DeterminismReport(rule_name, ScoringMode.HYBRID,
                                 det_ops, nondet_ops, "C",
                                 "HYBRID_DETERMINISM",
                                 f"Replace {nondet_ops} with lookup tables or fixed-point")
    else:
        return DeterminismReport(rule_name, ScoringMode.PROBABILISTIC,
                                 det_ops, nondet_ops, "D",
                                 "NON_DETERMINISTIC",
                                 "Use logical-step trace_hash, not exact-value trace_hash")


# Example scoring rules to analyze
RULES = {
    "brier_score": """
def brier_score(forecast, outcome):
    return (forecast - outcome) ** 2
""",
    "weighted_brier": """
import math
def weighted_brier(forecast, outcome, weight):
    return weight * (forecast - outcome) ** 2
""",
    "log_score": """
import math
def log_score(forecast, outcome):
    if outcome == 1:
        return -math.log(forecast)
    else:
        return -math.log(1 - forecast)
""",
    "cosine_similarity": """
import math
def cosine_sim(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    norm_a = math.sqrt(sum(x**2 for x in a))
    norm_b = math.sqrt(sum(x**2 for x in b))
    return dot / (norm_a * norm_b)
""",
    "simple_threshold": """
def threshold_score(value, threshold):
    if value >= threshold:
        return 1.0
    else:
        return 0.0
""",
    "integer_scoring": """
def int_score(delivered_items, expected_items):
    matched = sum(1 for d in delivered_items if d in expected_items)
    return matched * 100 // len(expected_items)
""",
}


def main():
    print("=" * 70)
    print("DETERMINISM CONSTRAINT CHECKER")
    print("Dawson (2013): IEEE 754 basic ops = deterministic, transcendentals = NOT")
    print("=" * 70)

    print(f"\n{'Rule':<20} {'Mode':<15} {'Grade':<6} {'NonDet Ops':<25} {'Diagnosis'}")
    print("-" * 80)

    for name, code in RULES.items():
        report = analyze_rule(name, code)
        nondet = ", ".join(report.nondeterministic_ops[:3]) or "none"
        print(f"{name:<20} {report.mode.value:<15} {report.grade:<6} {nondet:<25} {report.diagnosis}")

    print("\n--- ABI v2.1 scoring_mode Field ---")
    print("DETERMINISTIC:  basic IEEE 754 ops only → trace_hash reproducible")
    print("PROBABILISTIC:  LLM/sampling → trace_hash over logical steps only")
    print("HYBRID:         deterministic frame + non-deterministic components")
    print()
    print("Dispute routing per mode:")
    print("  DETERMINISTIC → replay and compare (automated)")
    print("  PROBABILISTIC → process audit only (manual/panel)")
    print("  HYBRID        → replay deterministic frame, audit non-det components")
    print()
    print("--- Fixes for Non-Deterministic Ops ---")
    print("math.log()  → lookup table or rational approximation")
    print("math.sqrt() → IEEE 754 guaranteed (safe!)")
    print("**          → integer exponents safe, float exponents NOT")
    print("math.sin()  → Chebyshev polynomial (fixed coefficients)")
    print()
    print("Key insight: the scoring rule IS a program.")
    print("Constrain the instruction set at lock time.")
    print("Disputes over float rounding = disputes over VMs, not agents.")


if __name__ == "__main__":
    main()
