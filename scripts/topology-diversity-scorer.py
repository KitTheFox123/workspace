#!/usr/bin/env python3
"""
topology-diversity-scorer.py — Score actual topological independence of witness sets.

kampderp's critique: "monoculture topology with N witnesses is still effectively 1."
Zhao et al (ePrint 2025/1033): TEE reduces BFT from 3f+1 to 2f+1, but only if
TEEs are on independent silicon.

This tool scores a witness set across 5 diversity axes:
  1. Cloud provider (AWS/GCP/Azure/Hetzner/self-hosted)
  2. Geographic region (continent/country/city)
  3. Hardware architecture (x86/ARM/RISC-V)
  4. OS family (Linux/BSD/macOS)
  5. Controller (who operates it — same human = correlated)

Effective N = N * diversity_score, where diversity_score ∈ (0, 1].
If all witnesses share cloud+region+arch, effective_N ≈ 1 regardless of N.

Usage:
    python3 topology-diversity-scorer.py --demo
    python3 topology-diversity-scorer.py --witnesses witnesses.json
"""

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class Witness:
    name: str
    cloud: str       # aws, gcp, azure, hetzner, self-hosted, unknown
    region: str       # us-east, eu-west, ap-south, etc.
    arch: str         # x86_64, arm64, riscv64
    os: str           # linux, bsd, macos
    controller: str   # human/org operating it


@dataclass
class DiversityScore:
    axis: str
    unique_values: int
    total: int
    score: float  # 0-1, higher = more diverse
    detail: Dict[str, int]


def axis_diversity(values: List[str]) -> float:
    """Shannon entropy normalized to [0,1]. 1 = max diversity, 0 = monoculture."""
    if len(values) <= 1:
        return 0.0
    counts = Counter(values)
    n = len(values)
    max_entropy = math.log2(n)
    if max_entropy == 0:
        return 0.0
    entropy = -sum((c / n) * math.log2(c / n) for c in counts.values())
    return round(entropy / max_entropy, 4)


def score_witnesses(witnesses: List[Witness]) -> dict:
    """Score a witness set across all diversity axes."""
    n = len(witnesses)
    axes = {
        "cloud": [w.cloud for w in witnesses],
        "region": [w.region for w in witnesses],
        "architecture": [w.arch for w in witnesses],
        "os": [w.os for w in witnesses],
        "controller": [w.controller for w in witnesses],
    }

    # Weights: controller and cloud matter most for correlated failure
    weights = {
        "cloud": 0.30,
        "region": 0.20,
        "architecture": 0.15,
        "os": 0.10,
        "controller": 0.25,
    }

    scores = {}
    weighted_sum = 0.0

    for axis_name, values in axes.items():
        div = axis_diversity(values)
        scores[axis_name] = DiversityScore(
            axis=axis_name,
            unique_values=len(set(values)),
            total=n,
            score=div,
            detail=dict(Counter(values)),
        )
        weighted_sum += div * weights[axis_name]

    # Effective N: if diversity is 0 (monoculture), effective_N = 1
    # If diversity is 1 (max), effective_N = N
    effective_n = 1 + (n - 1) * weighted_sum
    
    # Grade
    if weighted_sum >= 0.8:
        grade = "A"
    elif weighted_sum >= 0.6:
        grade = "B"
    elif weighted_sum >= 0.4:
        grade = "C"
    elif weighted_sum >= 0.2:
        grade = "D"
    else:
        grade = "F"

    return {
        "witness_count": n,
        "effective_n": round(effective_n, 2),
        "diversity_score": round(weighted_sum, 4),
        "grade": grade,
        "axes": {k: asdict(v) for k, v in scores.items()},
        "verdict": f"N={n}, effective_N={effective_n:.1f}. "
                   + ("Topology is load-bearing." if weighted_sum < 0.5 else "Reasonable independence.")
                   + (f" Monoculture risk: {[k for k,v in scores.items() if v.score < 0.3]}" if any(v.score < 0.3 for v in scores.values()) else ""),
    }


def demo():
    """Kit's actual witness set vs an ideal one."""
    print("=== Topology Diversity Scorer ===\n")

    # Kit's ACTUAL witnesses (honest assessment)
    kit_witnesses = [
        Witness("kit_fox", "hetzner", "eu-central", "x86_64", "linux", "ilya"),
        Witness("bro_agent", "unknown-vps", "us-east", "x86_64", "linux", "bro_operator"),
        Witness("gendolf", "unknown", "unknown", "x86_64", "linux", "gendolf_operator"),
    ]

    print("1. KIT'S ACTUAL WITNESS SET")
    result = score_witnesses(kit_witnesses)
    print(f"   N={result['witness_count']}, effective_N={result['effective_n']}")
    print(f"   Diversity: {result['diversity_score']} (grade: {result['grade']})")
    for axis, data in result['axes'].items():
        print(f"   {axis}: {data['score']:.2f} — {data['detail']}")
    print(f"   Verdict: {result['verdict']}")

    # Ideal witness set
    print("\n2. IDEAL WITNESS SET (5 witnesses)")
    ideal = [
        Witness("w1", "aws", "us-east", "x86_64", "linux", "operator_a"),
        Witness("w2", "gcp", "eu-west", "arm64", "linux", "operator_b"),
        Witness("w3", "hetzner", "ap-south", "x86_64", "bsd", "operator_c"),
        Witness("w4", "self-hosted", "sa-east", "riscv64", "linux", "operator_d"),
        Witness("w5", "azure", "af-south", "arm64", "macos", "operator_e"),
    ]
    result2 = score_witnesses(ideal)
    print(f"   N={result2['witness_count']}, effective_N={result2['effective_n']}")
    print(f"   Diversity: {result2['diversity_score']} (grade: {result2['grade']})")
    for axis, data in result2['axes'].items():
        print(f"   {axis}: {data['score']:.2f} — {data['detail']}")

    # Worst case: 10 witnesses, all same everything
    print("\n3. MONOCULTURE (10 witnesses, same infra)")
    mono = [Witness(f"w{i}", "aws", "us-east", "x86_64", "linux", "same_operator") for i in range(10)]
    result3 = score_witnesses(mono)
    print(f"   N={result3['witness_count']}, effective_N={result3['effective_n']}")
    print(f"   Diversity: {result3['diversity_score']} (grade: {result3['grade']})")
    print(f"   Verdict: {result3['verdict']}")

    # Zhao et al finding
    print("\n4. BFT IMPLICATION (Zhao et al 2025)")
    print("   Trusted hardware: 3f+1 → 2f+1 (halves witness requirement)")
    print("   BUT: TEEs on same silicon = correlated TEE failure")
    print(f"   Kit's effective_N={result['effective_n']:.1f} with N={result['witness_count']}")
    print(f"   Need effective_N ≥ 2f+1 = {2*1+1} for f=1 Byzantine tolerance")
    print(f"   Status: {'SUFFICIENT' if result['effective_n'] >= 3 else 'INSUFFICIENT — topology is theater'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--witnesses", type=str, help="JSON file with witness definitions")
    args = parser.parse_args()

    if args.witnesses:
        with open(args.witnesses) as f:
            data = json.load(f)
        witnesses = [Witness(**w) for w in data]
        result = score_witnesses(witnesses)
        print(json.dumps(result, indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
