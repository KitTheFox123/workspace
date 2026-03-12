#!/usr/bin/env python3
"""
diffusion-of-responsibility-detector.py

Detects diffusion of responsibility in multi-agent attestation groups.
Based on Beyer et al (2017, SCAN): presence of alternative agents reduces
outcome monitoring (FRN amplitude) even when control is unchanged.

Indicators:
1. Response latency increase (agents wait for others to act)
2. Monitoring depth decrease (shorter/shallower attestations with more agents)
3. Named vs unnamed accountability (diffusion strongest when no one is "it")
4. Ringelmann ratio (effort per agent vs solo baseline)

Usage:
    python diffusion-of-responsibility-detector.py [--demo]
"""

import argparse
import json
import math
import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class Attestation:
    agent_id: str
    group_size: int
    latency_ms: float  # time to respond
    depth_score: float  # 0-1, how thorough
    named_responsible: bool  # was this agent explicitly designated?
    content_length: int  # chars in attestation


@dataclass
class DiffusionReport:
    group_id: str
    group_size: int
    latency_ratio: float  # vs solo baseline
    depth_ratio: float  # vs solo baseline
    ringelmann_ratio: float  # actual/potential effort
    named_accountability: float  # fraction with named responsibility
    diffusion_score: float  # 0-1, higher = more diffusion
    grade: str
    recommendations: list


def detect_diffusion(
    attestations: list[Attestation],
    solo_latency_ms: float = 500.0,
    solo_depth: float = 0.85,
) -> DiffusionReport:
    """Analyze attestation group for diffusion of responsibility."""
    if not attestations:
        return DiffusionReport("empty", 0, 0, 0, 0, 0, 1.0, "F", ["No attestations"])

    group_size = attestations[0].group_size
    n = len(attestations)

    # 1. Latency ratio (Beyer: participants acted later in Together condition)
    avg_latency = sum(a.latency_ms for a in attestations) / n
    latency_ratio = avg_latency / solo_latency_ms if solo_latency_ms > 0 else 1.0

    # 2. Depth ratio (FRN reduced = less monitoring)
    avg_depth = sum(a.depth_score for a in attestations) / n
    depth_ratio = avg_depth / solo_depth if solo_depth > 0 else 1.0

    # 3. Ringelmann ratio (Ringelmann 1913: 8 people = 49% potential)
    # Expected: each person contributes 1/N of potential
    # Actual: measure total effort vs N * solo effort
    total_effort = sum(a.depth_score * a.content_length for a in attestations)
    potential_effort = n * solo_depth * max(a.content_length for a in attestations)
    ringelmann_ratio = total_effort / potential_effort if potential_effort > 0 else 0

    # 4. Named accountability
    named_count = sum(1 for a in attestations if a.named_responsible)
    named_accountability = named_count / n if n > 0 else 0

    # Composite diffusion score
    # Higher latency = more diffusion
    # Lower depth = more diffusion
    # Lower Ringelmann = more diffusion
    # Lower named accountability = more diffusion
    latency_penalty = min(1.0, max(0, (latency_ratio - 1.0) / 2.0))  # 0 at ratio 1, 1 at ratio 3
    depth_penalty = max(0, 1.0 - depth_ratio)
    ringelmann_penalty = max(0, 1.0 - ringelmann_ratio)
    naming_penalty = 1.0 - named_accountability

    diffusion_score = (
        0.25 * latency_penalty
        + 0.30 * depth_penalty
        + 0.25 * ringelmann_penalty
        + 0.20 * naming_penalty
    )

    # Grade
    if diffusion_score < 0.15:
        grade = "A"
    elif diffusion_score < 0.30:
        grade = "B"
    elif diffusion_score < 0.50:
        grade = "C"
    elif diffusion_score < 0.70:
        grade = "D"
    else:
        grade = "F"

    # Recommendations
    recs = []
    if latency_ratio > 1.5:
        recs.append(f"Latency {latency_ratio:.1f}x solo — agents waiting for others to act first")
    if depth_ratio < 0.7:
        recs.append(f"Monitoring depth {depth_ratio:.0%} of solo — agents checking less thoroughly")
    if named_accountability < 0.5:
        recs.append("Fewer than half have named accountability — designate specific reviewers")
    if ringelmann_ratio < 0.6:
        recs.append(f"Ringelmann ratio {ringelmann_ratio:.0%} — group producing less than sum of parts")
    if group_size > 5 and diffusion_score > 0.3:
        recs.append(f"Group size {group_size} with diffusion {diffusion_score:.2f} — consider smaller subgroups")
    if not recs:
        recs.append("Low diffusion detected — group functioning well")

    return DiffusionReport(
        group_id=f"group_{n}",
        group_size=group_size,
        latency_ratio=latency_ratio,
        depth_ratio=depth_ratio,
        ringelmann_ratio=ringelmann_ratio,
        named_accountability=named_accountability,
        diffusion_score=diffusion_score,
        grade=grade,
        recommendations=recs,
    )


def demo():
    """Run demonstration with synthetic data."""
    random.seed(42)
    print("=" * 60)
    print("DIFFUSION OF RESPONSIBILITY DETECTOR")
    print("Based on Beyer et al (2017, Soc Cogn Affect Neurosci)")
    print("=" * 60)

    # Scenario 1: Small group, named accountability
    print("\n--- Scenario 1: 3 agents, all named ---")
    atts1 = [
        Attestation("alice", 3, 520, 0.82, True, 450),
        Attestation("bob", 3, 580, 0.78, True, 420),
        Attestation("carol", 3, 490, 0.85, True, 480),
    ]
    r1 = detect_diffusion(atts1)
    print(f"Grade: {r1.grade} | Diffusion: {r1.diffusion_score:.3f}")
    print(f"Latency: {r1.latency_ratio:.2f}x | Depth: {r1.depth_ratio:.0%} | Ringelmann: {r1.ringelmann_ratio:.0%}")
    for rec in r1.recommendations:
        print(f"  → {rec}")

    # Scenario 2: Large group, no named accountability
    print("\n--- Scenario 2: 8 agents, none named ---")
    atts2 = [
        Attestation(f"agent_{i}", 8, 800 + random.gauss(0, 200), 0.45 + random.gauss(0, 0.1), False, 200 + random.randint(-50, 50))
        for i in range(8)
    ]
    r2 = detect_diffusion(atts2)
    print(f"Grade: {r2.grade} | Diffusion: {r2.diffusion_score:.3f}")
    print(f"Latency: {r2.latency_ratio:.2f}x | Depth: {r2.depth_ratio:.0%} | Ringelmann: {r2.ringelmann_ratio:.0%}")
    for rec in r2.recommendations:
        print(f"  → {rec}")

    # Scenario 3: Solo attestor (baseline)
    print("\n--- Scenario 3: Solo attestor (baseline) ---")
    atts3 = [Attestation("solo", 1, 480, 0.88, True, 600)]
    r3 = detect_diffusion(atts3)
    print(f"Grade: {r3.grade} | Diffusion: {r3.diffusion_score:.3f}")
    print(f"Latency: {r3.latency_ratio:.2f}x | Depth: {r3.depth_ratio:.0%} | Ringelmann: {r3.ringelmann_ratio:.0%}")
    for rec in r3.recommendations:
        print(f"  → {rec}")

    # Scenario 4: Li & Schnedler fix — one designated responsible
    print("\n--- Scenario 4: 5 agents, 1 designated lead ---")
    atts4 = [
        Attestation("lead", 5, 450, 0.90, True, 550),
        *[Attestation(f"support_{i}", 5, 650 + random.gauss(0, 100), 0.60 + random.gauss(0, 0.05), False, 300)
          for i in range(4)],
    ]
    r4 = detect_diffusion(atts4)
    print(f"Grade: {r4.grade} | Diffusion: {r4.diffusion_score:.3f}")
    print(f"Latency: {r4.latency_ratio:.2f}x | Depth: {r4.depth_ratio:.0%} | Ringelmann: {r4.ringelmann_ratio:.0%}")
    for rec in r4.recommendations:
        print(f"  → {rec}")

    print("\n" + "=" * 60)
    print("KEY INSIGHT: Diffusion is not post-hoc bias — it's an online")
    print("reduction in outcome monitoring (FRN attenuation). The brain")
    print("literally tracks less when others could have acted instead.")
    print("Fix: named accountability + small groups + designated leads.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect diffusion of responsibility in attestation groups")
    parser.add_argument("--demo", action="store_true", help="Run demo with synthetic data")
    args = parser.parse_args()

    if args.demo:
        demo()
    else:
        print("Use --demo for demonstration. Or import and call detect_diffusion().")
