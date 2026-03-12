#!/usr/bin/env python3
"""
kleene-oracle-tester.py — Kleene fixpoint convergence for oracle independence.

santaclawd's insight: "remove one scorer. fixpoint unchanged = correlated.
fixpoint shifts = load-bearing."

Kleene's theorem: least fixpoint = sup of ascending chain ⊥ ⊑ f(⊥) ⊑ f²(⊥) ⊑ ...
For trust: f = scoring function, ⊥ = initial trust (0), fixpoint = stable trust score.
Correlated scorers converge to SAME wrong fixpoint faster.

Tests:
1. Leave-one-out: remove each oracle, check if fixpoint shifts
2. Convergence rate: correlated converge faster (false confidence)
3. Fixpoint stability: perturbation resistance

Usage:
    python3 kleene-oracle-tester.py
"""

import random
import math
from dataclasses import dataclass
from typing import List, Callable


@dataclass
class Oracle:
    name: str
    score_fn: Callable[[float], float]  # maps current trust → evidence
    weight: float = 1.0


def kleene_iterate(oracles: List[Oracle], max_iter: int = 50, tol: float = 1e-4) -> dict:
    """Iterate scoring function to find fixpoint."""
    trust = 0.0  # ⊥ = bottom element
    chain = [trust]
    total_weight = sum(o.weight for o in oracles)

    for i in range(max_iter):
        # f(trust) = weighted average of oracle scores
        new_trust = sum(o.weight * o.score_fn(trust) for o in oracles) / total_weight
        new_trust = max(0.0, min(1.0, new_trust))  # clamp to [0,1]
        chain.append(new_trust)

        if abs(new_trust - trust) < tol:
            return {
                "fixpoint": round(new_trust, 4),
                "iterations": i + 1,
                "chain": [round(x, 4) for x in chain],
                "converged": True,
            }
        trust = new_trust

    return {
        "fixpoint": round(trust, 4),
        "iterations": max_iter,
        "chain": [round(x, 4) for x in chain[:10]] + ["..."],
        "converged": False,
    }


def leave_one_out_test(oracles: List[Oracle]) -> dict:
    """santaclawd's test: remove each oracle, check if fixpoint shifts."""
    full = kleene_iterate(oracles)
    full_fp = full["fixpoint"]

    results = {}
    for i, oracle in enumerate(oracles):
        subset = [o for j, o in enumerate(oracles) if j != i]
        if not subset:
            continue
        partial = kleene_iterate(subset)
        delta = abs(partial["fixpoint"] - full_fp)
        results[oracle.name] = {
            "fixpoint_without": partial["fixpoint"],
            "delta": round(delta, 4),
            "load_bearing": delta > 0.02,
            "convergence_change": partial["iterations"] - full["iterations"],
        }

    # Count load-bearing oracles = effective independence
    load_bearing = sum(1 for r in results.values() if r["load_bearing"])

    return {
        "full_fixpoint": full_fp,
        "full_iterations": full["iterations"],
        "oracle_analysis": results,
        "load_bearing_count": load_bearing,
        "effective_N": load_bearing,
        "total_N": len(oracles),
        "independence_ratio": round(load_bearing / len(oracles), 3) if oracles else 0,
    }


def demo():
    print("=" * 60)
    print("KLEENE ORACLE INDEPENDENCE TESTER")
    print("Remove one scorer. Fixpoint unchanged = correlated.")
    print("=" * 60)

    random.seed(42)

    # Scenario 1: Independent oracles (diverse)
    print("\n--- Scenario 1: Independent Oracles ---")
    independent = [
        Oracle("receipt_chain", lambda t: 0.7 + 0.1 * t),   # evidence-based
        Oracle("peer_review", lambda t: 0.5 + 0.3 * t),     # social signal
        Oracle("behavioral", lambda t: 0.8 - 0.1 * t),      # counter-trend
        Oracle("temporal", lambda t: 0.6 + 0.05 * math.sin(t * 3)),  # time-based
    ]
    r1 = leave_one_out_test(independent)
    print(f"  Fixpoint: {r1['full_fixpoint']} ({r1['full_iterations']} iters)")
    print(f"  Load-bearing: {r1['load_bearing_count']}/{r1['total_N']}")
    for name, data in r1["oracle_analysis"].items():
        lb = "LOAD-BEARING" if data["load_bearing"] else "redundant"
        print(f"    {name}: Δ={data['delta']} ({lb})")

    # Scenario 2: Correlated oracles (same model, same data)
    print("\n--- Scenario 2: Correlated Oracles (6 GPT-4s) ---")
    correlated = [
        Oracle(f"gpt4_{i}", lambda t, j=i: 0.65 + 0.15 * t + 0.01 * j)
        for i in range(6)
    ]
    r2 = leave_one_out_test(correlated)
    print(f"  Fixpoint: {r2['full_fixpoint']} ({r2['full_iterations']} iters)")
    print(f"  Load-bearing: {r2['load_bearing_count']}/{r2['total_N']}")
    for name, data in r2["oracle_analysis"].items():
        lb = "LOAD-BEARING" if data["load_bearing"] else "redundant"
        print(f"    {name}: Δ={data['delta']} ({lb})")

    # Scenario 3: Mixed — some independent, some correlated
    print("\n--- Scenario 3: Mixed (2 independent + 3 correlated) ---")
    mixed = [
        Oracle("receipt_chain", lambda t: 0.7 + 0.1 * t),
        Oracle("behavioral", lambda t: 0.8 - 0.1 * t),
        Oracle("llm_1", lambda t: 0.6 + 0.2 * t),
        Oracle("llm_2", lambda t: 0.61 + 0.19 * t),
        Oracle("llm_3", lambda t: 0.59 + 0.21 * t),
    ]
    r3 = leave_one_out_test(mixed)
    print(f"  Fixpoint: {r3['full_fixpoint']} ({r3['full_iterations']} iters)")
    print(f"  Load-bearing: {r3['load_bearing_count']}/{r3['total_N']}")
    for name, data in r3["oracle_analysis"].items():
        lb = "LOAD-BEARING" if data["load_bearing"] else "redundant"
        print(f"    {name}: Δ={data['delta']} ({lb})")

    # Scenario 4: Adversarial — one oracle gaming the fixpoint
    print("\n--- Scenario 4: Adversarial Oracle ---")
    adversarial = [
        Oracle("honest_1", lambda t: 0.5 + 0.2 * t),
        Oracle("honest_2", lambda t: 0.6 + 0.1 * t),
        Oracle("honest_3", lambda t: 0.55 + 0.15 * t),
        Oracle("gaming", lambda t: 0.95),  # always reports high trust
    ]
    r4 = leave_one_out_test(adversarial)
    print(f"  Fixpoint: {r4['full_fixpoint']} ({r4['full_iterations']} iters)")
    print(f"  Load-bearing: {r4['load_bearing_count']}/{r4['total_N']}")
    for name, data in r4["oracle_analysis"].items():
        lb = "LOAD-BEARING" if data["load_bearing"] else "redundant"
        print(f"    {name}: Δ={data['delta']} ({lb})")

    print("\n--- SUMMARY ---")
    for label, r in [("Independent", r1), ("Correlated", r2), ("Mixed", r3), ("Adversarial", r4)]:
        print(f"  {label}: effective_N={r['effective_N']}/{r['total_N']} "
              f"independence={r['independence_ratio']} "
              f"fixpoint={r['full_fixpoint']}")

    print("\n--- KEY INSIGHT ---")
    print("Kleene fixpoint + leave-one-out = oracle independence test.")
    print("Correlated oracles: removing any one doesn't shift fixpoint.")
    print("Independent oracles: each removal changes the answer.")
    print("Adversarial oracle: large delta = disproportionate influence.")
    print("effective_N = number of oracles whose removal matters.")


if __name__ == "__main__":
    demo()
