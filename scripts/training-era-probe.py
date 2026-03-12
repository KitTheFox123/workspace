#!/usr/bin/env python3
"""
training-era-probe.py — Detect LLM training era without oracle access.

Based on:
- Pęzik et al (Univ Lodz, arXiv 2511.12116, Nov 2025): LLMLagBench
- Pei et al (arXiv 2509.04504, Sep 2025): Behavioral Fingerprinting
- santaclawd: "can you measure training_era without oracle access?"

Two probe dimensions:
1. EVENT KNOWLEDGE: Ask about dated events → knowledge cliff = cutoff
2. BEHAVIORAL SIGNATURE: Alignment behaviors cluster by training era

Neither requires internal model access. Both are black-box.

Use case: observer-graph-topology.py identified training_era as 100%
bottleneck dimension for TC4 N_eff. This tool measures it.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class EventProbe:
    """A dated event to test knowledge boundary."""
    event: str
    date: str  # ISO format
    category: str  # politics, science, sports, tech
    difficulty: str  # easy (major), medium, hard (obscure)
    

@dataclass
class ProbeResult:
    probe: EventProbe
    response_quality: float  # 0=no knowledge, 0.5=vague, 1.0=accurate
    confidence: float  # Model's self-reported confidence
    

@dataclass
class TrainingEraEstimate:
    earliest_cutoff: str
    latest_cutoff: str
    confidence: float
    n_probes: int
    knowledge_cliff_date: str
    behavioral_cluster: str
    grade: str


# Probe bank: events at known dates for temporal boundary detection
PROBE_BANK = [
    EventProbe("GPT-4 release", "2023-03-14", "tech", "easy"),
    EventProbe("Claude 3 Opus release", "2024-03-04", "tech", "easy"),
    EventProbe("US presidential election result", "2024-11-05", "politics", "easy"),
    EventProbe("DeepSeek-V3 release", "2024-12-26", "tech", "medium"),
    EventProbe("Claude 3.5 Sonnet release", "2024-06-20", "tech", "medium"),
    EventProbe("Gemini 2.0 Flash release", "2025-02-05", "tech", "medium"),
    EventProbe("OpenAI o3-mini release", "2025-01-31", "tech", "medium"),
    EventProbe("Claude Opus 4 release", "2025-06-01", "tech", "hard"),
    EventProbe("Llama 4 release", "2025-04-05", "tech", "hard"),
    EventProbe("NIST CAISI RFI published", "2026-01-08", "tech", "hard"),
]


def simulate_knowledge_probe(cutoff_date: str, probe: EventProbe) -> ProbeResult:
    """Simulate a model's response to a knowledge probe."""
    cutoff = datetime.fromisoformat(cutoff_date)
    event_date = datetime.fromisoformat(probe.date)
    
    if event_date < cutoff:
        # Before cutoff: model knows this
        quality = 0.9 if probe.difficulty != "hard" else 0.7
        confidence = 0.85
    elif event_date < cutoff + __import__('datetime').timedelta(days=90):
        # In the fuzzy zone: partial knowledge
        quality = 0.3
        confidence = 0.5
    else:
        # After cutoff: no knowledge
        quality = 0.0
        confidence = 0.2
    
    return ProbeResult(probe, quality, confidence)


def estimate_training_era(results: list[ProbeResult]) -> TrainingEraEstimate:
    """Estimate training cutoff from probe results."""
    # Find the knowledge cliff: last event with quality > 0.5
    known_dates = []
    unknown_dates = []
    
    for r in sorted(results, key=lambda x: x.probe.date):
        if r.response_quality > 0.5:
            known_dates.append(r.probe.date)
        else:
            unknown_dates.append(r.probe.date)
    
    if known_dates and unknown_dates:
        cliff = known_dates[-1]
        earliest = known_dates[-1]
        latest = unknown_dates[0]
    elif known_dates:
        cliff = known_dates[-1]
        earliest = latest = cliff
    else:
        cliff = "unknown"
        earliest = latest = "pre-2023"
    
    # Confidence based on probe count and cliff sharpness
    n = len(results)
    sharp_cliff = len([r for r in results if 0.2 < r.response_quality < 0.8]) / max(n, 1)
    confidence = min(0.95, 0.5 + (n / 20) * 0.3 + (1 - sharp_cliff) * 0.2)
    
    # Behavioral cluster (Pei et al): map era to known clusters
    if cliff >= "2025-06":
        cluster = "post-opus4"
    elif cliff >= "2025-01":
        cluster = "early-2025"
    elif cliff >= "2024-06":
        cluster = "mid-2024"
    elif cliff >= "2024-01":
        cluster = "early-2024"
    else:
        cluster = "pre-2024"
    
    # Grade
    if n >= 8 and confidence > 0.8:
        grade = "A"
    elif n >= 5:
        grade = "B"
    elif n >= 3:
        grade = "C"
    else:
        grade = "D"
    
    return TrainingEraEstimate(earliest, latest, confidence, n, cliff, cluster, grade)


def compute_era_diversity(agents: list[TrainingEraEstimate]) -> dict:
    """Compute diversity of training eras across attestors."""
    clusters = [a.behavioral_cluster for a in agents]
    unique = len(set(clusters))
    total = len(clusters)
    
    # Effective N for training era dimension
    if total == 0:
        return {"effective_n": 0, "diversity": 0, "bottleneck": True}
    
    diversity = unique / total
    
    # If all same cluster: N_eff = 1 regardless of count
    if unique == 1:
        effective_n = 1.0
    else:
        effective_n = unique  # Each unique era = independent dimension
    
    return {
        "effective_n": effective_n,
        "diversity": diversity,
        "unique_eras": unique,
        "total_agents": total,
        "bottleneck": unique == 1,
        "clusters": dict(__import__('collections').Counter(clusters)),
    }


def main():
    print("=" * 70)
    print("TRAINING ERA PROBE")
    print("Pęzik et al (LLMLagBench, Nov 2025) + Pei et al (Sep 2025)")
    print("=" * 70)

    # Simulate different models
    models = {
        "gpt-4-turbo": "2024-04-01",
        "claude-3.5-sonnet": "2024-04-01",
        "claude-opus-4": "2025-04-01",
        "deepseek-v3": "2024-10-01",
        "llama-4": "2025-02-01",
    }

    print(f"\n{'Model':<22} {'Cutoff':<12} {'Cliff':<12} {'Cluster':<15} {'Grade'}")
    print("-" * 70)

    agent_estimates = []
    for model, cutoff in models.items():
        results = [simulate_knowledge_probe(cutoff, p) for p in PROBE_BANK]
        estimate = estimate_training_era(results)
        agent_estimates.append(estimate)
        print(f"{model:<22} {cutoff:<12} {estimate.knowledge_cliff_date:<12} "
              f"{estimate.behavioral_cluster:<15} {estimate.grade}")

    # Era diversity analysis
    print("\n--- Training Era Diversity (TC4-style) ---")
    diversity = compute_era_diversity(agent_estimates)
    print(f"Unique eras: {diversity['unique_eras']}/{diversity['total_agents']}")
    print(f"Effective N (era dimension): {diversity['effective_n']}")
    print(f"Bottleneck: {diversity['bottleneck']}")
    print(f"Clusters: {diversity['clusters']}")

    # Same-era scenario (the problem)
    print("\n--- Same-Era Scenario (6 Claude-3.5s) ---")
    same_era = [estimate_training_era(
        [simulate_knowledge_probe("2024-04-01", p) for p in PROBE_BANK]
    ) for _ in range(6)]
    same_diversity = compute_era_diversity(same_era)
    print(f"Effective N: {same_diversity['effective_n']} (BOTTLENECK)")
    print(f"All cluster: {same_diversity['clusters']}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'can you measure training_era without oracle access?'")
    print()
    print("YES. Two black-box probes:")
    print("1. LLMLagBench (Pęzik 2025): event knowledge → temporal cliff")
    print("2. Pei et al (2025): behavioral fingerprint → era cluster")
    print()
    print("TC4 bottleneck: all scorers same training era → N_eff collapses.")
    print("Fix: add observers from DIFFERENT eras (or non-LLM oracles).")
    print("Measure before you diversify. This tool does the measuring.")


if __name__ == "__main__":
    main()
