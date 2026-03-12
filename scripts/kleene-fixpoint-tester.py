#!/usr/bin/env python3
"""
kleene-fixpoint-tester.py — Test oracle independence via fixpoint convergence.

santaclawd's test: "remove one scorer. fixpoint unchanged = correlated.
fixpoint shifts = load-bearing."

Kleene's fixpoint theorem: monotone function on complete lattice has
least fixpoint = ⊔{f^n(⊥) | n ∈ ℕ}. Trust scoring = iterative refinement
toward fixpoint. Correlated scorers = same operator repeated.

Münchhausen trilemma for trust:
1. Infinite regress (who certifies the certifier?)
2. Circular reasoning (A vouches for B vouches for A)
3. Axiomatic stop (genesis receipt)

Usage:
    uv run --with numpy python3 scripts/kleene-fixpoint-tester.py
"""

import random
import math
from dataclasses import dataclass
from typing import List, Callable, Dict, Tuple


@dataclass
class Oracle:
    name: str
    substrate: str  # llm, rule, human, temporal
    score_fn: Callable[[str, float], float]  # agent_id, current_score -> new_score


def make_llm_oracle(name: str, bias: float = 0.0, noise: float = 0.05) -> Oracle:
    """LLM-based oracle — correlated with other LLMs via shared training."""
    def score(agent_id: str, current: float) -> float:
        base = 0.6 + bias  # LLMs tend toward similar base
        return max(0, min(1, base + random.gauss(0, noise)))
    return Oracle(name, "llm", score)


def make_rule_oracle(name: str) -> Oracle:
    """Rule-based oracle — deterministic, no training correlation."""
    def score(agent_id: str, current: float) -> float:
        # Checks: has receipts? has scope_hash? has continuity?
        checks = hash(agent_id) % 10  # simulate checks
        return checks / 10.0
    return Oracle(name, "rule", score)


def make_temporal_oracle(name: str) -> Oracle:
    """Temporal oracle — based on history/trajectory."""
    def score(agent_id: str, current: float) -> float:
        # Trend-based: slight regression to mean
        return current * 0.8 + 0.1 + random.gauss(0, 0.03)
    return Oracle(name, "temporal", score)


def make_human_oracle(name: str) -> Oracle:
    """Human oracle — uncorrelated with LLMs."""
    def score(agent_id: str, current: float) -> float:
        return 0.5 + random.gauss(0, 0.15)  # wide variance, centered
    return Oracle(name, "human", score)


def compute_fixpoint(oracles: List[Oracle], agent_id: str, 
                     max_iter: int = 50, tol: float = 0.001) -> Tuple[float, int]:
    """Iterate scoring until convergence (Kleene ascending chain)."""
    score = 0.0  # ⊥ = start from bottom
    for i in range(max_iter):
        new_scores = [o.score_fn(agent_id, score) for o in oracles]
        new_score = sum(new_scores) / len(new_scores)
        if abs(new_score - score) < tol:
            return new_score, i + 1
        score = new_score
    return score, max_iter


def leave_one_out_test(oracles: List[Oracle], agent_id: str, 
                       n_trials: int = 20) -> Dict[str, dict]:
    """santaclawd's test: remove each oracle, check if fixpoint shifts."""
    # Full fixpoint (averaged over trials for stability)
    full_fps = [compute_fixpoint(oracles, agent_id)[0] for _ in range(n_trials)]
    full_fp = sum(full_fps) / len(full_fps)

    results = {}
    for i, oracle in enumerate(oracles):
        reduced = [o for j, o in enumerate(oracles) if j != i]
        if not reduced:
            continue
        red_fps = [compute_fixpoint(reduced, agent_id)[0] for _ in range(n_trials)]
        red_fp = sum(red_fps) / len(red_fps)
        delta = abs(red_fp - full_fp)
        
        load_bearing = delta > 0.05
        results[oracle.name] = {
            "substrate": oracle.substrate,
            "fixpoint_delta": round(delta, 4),
            "load_bearing": load_bearing,
            "full_fixpoint": round(full_fp, 4),
            "reduced_fixpoint": round(red_fp, 4),
        }

    return results


def substrate_diversity_score(oracles: List[Oracle]) -> float:
    """Effective N based on substrate diversity (Kish design effect)."""
    substrates = [o.substrate for o in oracles]
    unique = len(set(substrates))
    n = len(substrates)
    if n == 0:
        return 0
    # Herfindahl index
    from collections import Counter
    counts = Counter(substrates)
    hhi = sum((c/n)**2 for c in counts.values())
    effective_n = 1 / hhi
    return round(effective_n, 2)


def demo():
    print("=" * 60)
    print("KLEENE FIXPOINT TESTER FOR TRUST ORACLES")
    print("santaclawd: remove one scorer, fixpoint unchanged = correlated")
    print("=" * 60)
    random.seed(42)

    # Scenario 1: All LLM oracles (correlated)
    print("\n--- Scenario 1: All LLM (Correlated) ---")
    correlated = [
        make_llm_oracle("gpt4", bias=0.0),
        make_llm_oracle("claude", bias=0.02),
        make_llm_oracle("gemini", bias=-0.01),
        make_llm_oracle("llama", bias=0.01),
    ]
    r1 = leave_one_out_test(correlated, "test_agent")
    eff_n1 = substrate_diversity_score(correlated)
    print(f"  Effective N: {eff_n1} (all same substrate)")
    for name, data in r1.items():
        marker = "🔴 CORRELATED" if not data["load_bearing"] else "🟢 LOAD-BEARING"
        print(f"  Remove {name}: Δ={data['fixpoint_delta']:.4f} {marker}")

    # Scenario 2: Diverse substrates
    print("\n--- Scenario 2: Diverse Substrates ---")
    diverse = [
        make_llm_oracle("claude"),
        make_rule_oracle("scope_checker"),
        make_temporal_oracle("trajectory"),
        make_human_oracle("auditor"),
    ]
    r2 = leave_one_out_test(diverse, "test_agent")
    eff_n2 = substrate_diversity_score(diverse)
    print(f"  Effective N: {eff_n2} (four substrates)")
    for name, data in r2.items():
        marker = "🔴 CORRELATED" if not data["load_bearing"] else "🟢 LOAD-BEARING"
        print(f"  Remove {name}: Δ={data['fixpoint_delta']:.4f} {marker}")

    # Scenario 3: Münchhausen detection
    print("\n--- Scenario 3: Münchhausen Trilemma Detection ---")
    print("  Infinite regress: A certifies B certifies C certifies A...")
    print("  Circular: A→B→A (cycle length 2)")
    print("  Axiomatic: Genesis receipt (stops the chain)")
    print()
    print("  Correlated oracles = circular reasoning at substrate level")
    print(f"  4 LLMs: effective N = {eff_n1} (circular)")
    print(f"  4 diverse: effective N = {eff_n2} (each load-bearing)")

    # Grade
    print("\n--- GRADES ---")
    for label, eff_n, results in [("All LLM", eff_n1, r1), ("Diverse", eff_n2, r2)]:
        load_bearing = sum(1 for r in results.values() if r["load_bearing"])
        total = len(results)
        if eff_n >= 3.5 and load_bearing == total:
            grade = "A"
        elif eff_n >= 2.5:
            grade = "B"
        elif eff_n >= 1.5:
            grade = "C"
        else:
            grade = "F"
        print(f"  {label}: effective_N={eff_n}, load_bearing={load_bearing}/{total}, grade={grade}")


if __name__ == "__main__":
    demo()
