#!/usr/bin/env python3
"""cpwbft-confidence-probe.py — Confidence-probe weighted BFT for agent attestation.

Based on Zheng et al (arXiv 2511.10400, Nov 2025): CP-WBFT.
LLM agents show stronger skepticism than traditional agents.
Confidence probes weight votes in Byzantine consensus.

Key insight: instead of equal votes, weight by calibrated confidence.
Survives 85.7% Byzantine fault rate in multi-agent systems.

Usage:
    python3 cpwbft-confidence-probe.py [--demo] [--byzantine-rate RATE]
"""

import argparse
import json
import random
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class AttestorVote:
    agent_id: str
    vote: str  # "valid" or "invalid"
    confidence: float  # 0.0-1.0
    weighted_score: float
    is_byzantine: bool


@dataclass 
class ConsensusResult:
    round_id: int
    votes: list
    weighted_valid: float
    weighted_invalid: float
    consensus: str
    correct: bool
    byzantine_rate: float
    method: str


def simulate_cpwbft(n_agents: int = 7, byzantine_rate: float = 0.3,
                     n_rounds: int = 100, ground_truth: str = "valid") -> dict:
    """Simulate CP-WBFT consensus rounds."""
    results = []
    
    for round_id in range(n_rounds):
        n_byzantine = int(n_agents * byzantine_rate)
        agents = []
        
        for i in range(n_agents):
            is_byz = i < n_byzantine
            
            if is_byz:
                # Byzantine: wrong vote, variable confidence
                vote = "invalid" if ground_truth == "valid" else "valid"
                # LLM skepticism: Byzantine agents less confident (key CP-WBFT insight)
                confidence = random.uniform(0.3, 0.7)
            else:
                # Honest: correct vote, high confidence
                vote = ground_truth
                confidence = random.uniform(0.7, 0.95)
            
            weighted = confidence  # CP-WBFT: weight = calibrated confidence
            agents.append(AttestorVote(
                agent_id=f"agent_{i}",
                vote=vote,
                confidence=confidence,
                weighted_score=weighted,
                is_byzantine=is_byz
            ))
        
        # Weighted consensus
        w_valid = sum(a.weighted_score for a in agents if a.vote == "valid")
        w_invalid = sum(a.weighted_score for a in agents if a.vote == "invalid")
        consensus = "valid" if w_valid > w_invalid else "invalid"
        
        results.append(ConsensusResult(
            round_id=round_id,
            votes=[asdict(a) for a in agents],
            weighted_valid=round(w_valid, 3),
            weighted_invalid=round(w_invalid, 3),
            consensus=consensus,
            correct=(consensus == ground_truth),
            byzantine_rate=byzantine_rate,
            method="CP-WBFT"
        ))
    
    accuracy = sum(1 for r in results if r.correct) / len(results)
    return {
        "method": "CP-WBFT",
        "n_agents": n_agents,
        "byzantine_rate": byzantine_rate,
        "n_rounds": n_rounds,
        "accuracy": round(accuracy, 3),
        "grade": "A" if accuracy >= 0.95 else "B" if accuracy >= 0.85 else "C" if accuracy >= 0.7 else "F",
    }


def simulate_naive(n_agents: int = 7, byzantine_rate: float = 0.3,
                    n_rounds: int = 100, ground_truth: str = "valid") -> dict:
    """Simulate naive majority voting (no confidence weighting)."""
    correct = 0
    for _ in range(n_rounds):
        n_byz = int(n_agents * byzantine_rate)
        honest_votes = n_agents - n_byz
        byz_votes = n_byz
        # Majority wins (equal weight)
        if honest_votes > byz_votes:
            correct += 1
    
    accuracy = correct / n_rounds
    return {
        "method": "Naive majority",
        "n_agents": n_agents,
        "byzantine_rate": byzantine_rate,
        "n_rounds": n_rounds,
        "accuracy": round(accuracy, 3),
        "grade": "A" if accuracy >= 0.95 else "B" if accuracy >= 0.85 else "C" if accuracy >= 0.7 else "F",
    }


def compare_methods(byzantine_rates=None):
    """Compare CP-WBFT vs naive at various Byzantine rates."""
    if byzantine_rates is None:
        byzantine_rates = [0.1, 0.2, 0.33, 0.5, 0.7, 0.857]
    
    comparisons = []
    for rate in byzantine_rates:
        cpwbft = simulate_cpwbft(byzantine_rate=rate)
        naive = simulate_naive(byzantine_rate=rate)
        comparisons.append({
            "byzantine_rate": rate,
            "cpwbft_accuracy": cpwbft["accuracy"],
            "cpwbft_grade": cpwbft["grade"],
            "naive_accuracy": naive["accuracy"],
            "naive_grade": naive["grade"],
            "improvement": round(cpwbft["accuracy"] - naive["accuracy"], 3)
        })
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "comparisons": comparisons,
        "key_insight": "CP-WBFT survives higher Byzantine rates because confidence-weighted "
                      "votes reduce impact of low-confidence Byzantine agents. LLM skepticism "
                      "= natural defense (Zheng et al 2511.10400).",
        "isnad_parallel": "Three-signal verdict (liveness × intent × drift) is a lightweight "
                         "confidence probe: each signal type contributes weighted evidence."
    }


def demo():
    """Run comparison demo."""
    print("=" * 60)
    print("CP-WBFT vs NAIVE MAJORITY — Byzantine Fault Tolerance")
    print("Based on Zheng et al (arXiv 2511.10400)")
    print("=" * 60)
    print()
    
    results = compare_methods()
    
    print(f"{'Byz Rate':>10} {'CP-WBFT':>10} {'Grade':>6} {'Naive':>10} {'Grade':>6} {'Δ':>8}")
    print("-" * 56)
    for c in results["comparisons"]:
        print(f"{c['byzantine_rate']:>10.1%} {c['cpwbft_accuracy']:>10.1%} {c['cpwbft_grade']:>6} "
              f"{c['naive_accuracy']:>10.1%} {c['naive_grade']:>6} {c['improvement']:>+8.1%}")
    
    print()
    print(f"Key insight: {results['key_insight']}")
    print()
    print(f"Isnad parallel: {results['isnad_parallel']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CP-WBFT confidence probe simulator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--byzantine-rate", type=float, default=0.3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(compare_methods(), indent=2))
    else:
        demo()
