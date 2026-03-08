#!/usr/bin/env python3
"""root-ceremony-sim.py — Root signing ceremony simulator.

Models the DNSSEC root signing ceremony trust model for agent scope signing.
Implements N-of-M threshold ceremony with dishonesty probability modeling.

Based on ICANN root signing ceremony: 14 Crypto Officers, 3 required,
formally specified 5% dishonesty rate → <1:1,000,000 compromise probability.

Usage:
    python3 root-ceremony-sim.py [--demo] [--officers N] [--threshold M] [--dishonesty P]
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class CeremonyResult:
    """Result of a ceremony probability analysis."""
    total_officers: int
    threshold: int
    dishonesty_rate: float
    compromise_probability: float
    compromise_one_in: str
    ceremony_valid: bool
    security_grade: str


def binomial_coeff(n: int, k: int) -> int:
    """Compute C(n, k)."""
    if k < 0 or k > n:
        return 0
    return math.factorial(n) // (math.factorial(k) * math.factorial(n - k))


def compromise_probability(n: int, k: int, p: float) -> float:
    """Probability that ALL k attending officers are dishonest.
    
    DNSSEC model: k officers attend out of n pool. ALL k must collude.
    P(compromise) = P(all k selected are dishonest)
    = C(n*p, k) / C(n, k) approximated as p^k for large n.
    
    More precisely: probability of selecting k dishonest from 
    n*p dishonest officers out of n total.
    """
    # Simple model: each of the k attending officers independently
    # has probability p of being dishonest. All k must be dishonest.
    return p ** k


def grade_ceremony(prob: float) -> str:
    """Grade based on compromise probability."""
    if prob < 1e-9:
        return "A+"
    elif prob < 1e-6:
        return "A"
    elif prob < 1e-4:
        return "B"
    elif prob < 1e-2:
        return "C"
    elif prob < 0.1:
        return "D"
    else:
        return "F"


def analyze_ceremony(n: int, k: int, p: float) -> CeremonyResult:
    """Analyze a ceremony configuration."""
    prob = compromise_probability(n, k, p)
    one_in = f"1:{int(1/prob):,}" if prob > 0 else "impossible"
    
    return CeremonyResult(
        total_officers=n,
        threshold=k,
        dishonesty_rate=p,
        compromise_probability=prob,
        compromise_one_in=one_in,
        ceremony_valid=prob < 1e-6,
        security_grade=grade_ceremony(prob)
    )


def demo():
    """Run demo showing DNSSEC ceremony + agent variants."""
    print("=" * 60)
    print("ROOT SIGNING CEREMONY ANALYSIS")
    print("=" * 60)
    print()
    
    configs = [
        ("DNSSEC actual (14 officers, 3 required, 5% dishonest)", 14, 3, 0.05),
        ("Minimal agent (7 officers, 3 required, 5%)", 7, 3, 0.05),
        ("Small team (5 officers, 3 required, 5%)", 5, 3, 0.05),
        ("High distrust (7 officers, 3 required, 15%)", 7, 3, 0.15),
        ("Pair signing (2 officers, 2 required, 5%)", 2, 2, 0.05),
        ("Single signer (1 officer, 1 required, 5%)", 1, 1, 0.05),
        ("Agent scope (3 attestors, 2 required, 10%)", 3, 2, 0.10),
        ("isnad quorum (5 attestors, 3 required, 10%)", 5, 3, 0.10),
    ]
    
    for label, n, k, p in configs:
        result = analyze_ceremony(n, k, p)
        status = "✅" if result.ceremony_valid else "❌"
        print(f"{status} [{result.security_grade}] {label}")
        print(f"    P(compromise) = {result.compromise_probability:.2e} ({result.compromise_one_in})")
        print()
    
    print("-" * 60)
    print("Key insight: DNSSEC's 14/3/5% = 1:8,000 per ceremony (p^k model)")
    print("Agent scope signing with 5/3/10% = 1:1,000 per heartbeat")
    print("DNSSEC claims 1:1,000,000 via hypergeometric (pool selection matters)")
    print("Short TTL compensates: if compromise lasts hours not years,")
    print("Grade C ceremony + hourly TTL ≈ Grade A ceremony + yearly TTL.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Root signing ceremony simulator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--officers", type=int, default=14)
    parser.add_argument("--threshold", type=int, default=3)
    parser.add_argument("--dishonesty", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.demo or (not args.json):
        demo()
    else:
        result = analyze_ceremony(args.officers, args.threshold, args.dishonesty)
        print(json.dumps(asdict(result), indent=2))
