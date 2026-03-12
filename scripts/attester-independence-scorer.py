#!/usr/bin/env python3
"""Attester Independence Scorer — Detect common mode failures in trust attestation.

NASA common mode failure: three backup systems on same power supply = one system.
Same logic: 5 attesters on GPT-4 with same prompt = N=1 not 5.

Dimensions of independence:
1. Model substrate (different LLM families)
2. Prompt/instruction diversity
3. Deployment context (different operators)
4. Temporal spread (not all attesting at same time)
5. Data access (different information sources)

Based on: NASA common cause failure analysis, PCAOB auditor independence rules,
Nature 2025 correlated voters degrade wisdom of crowds.

Kit 🦊 — 2026-02-28
"""

import json
import math
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class Attester:
    id: str
    model_family: str      # e.g. "anthropic", "openai", "google", "open-source"
    prompt_hash: str        # hash of the prompt used (same hash = same prompt)
    operator: str           # who runs this attester
    timestamp_bucket: str   # time bucket (e.g. "2026-02-28T14" = same hour)
    data_sources: list[str] = field(default_factory=list)  # what data it accessed


def score_independence(attesters: list[Attester]) -> dict:
    """Score how independent a set of attesters actually is."""
    n = len(attesters)
    if n < 2:
        return {"effective_n": n, "independence": 0, "grade": "N/A",
                "reason": "need 2+ attesters"}

    # Dimension 1: Model diversity
    models = [a.model_family for a in attesters]
    model_entropy = _normalized_entropy(models)

    # Dimension 2: Prompt diversity
    prompts = [a.prompt_hash for a in attesters]
    prompt_entropy = _normalized_entropy(prompts)

    # Dimension 3: Operator diversity
    operators = [a.operator for a in attesters]
    operator_entropy = _normalized_entropy(operators)

    # Dimension 4: Temporal spread
    times = [a.timestamp_bucket for a in attesters]
    temporal_entropy = _normalized_entropy(times)

    # Dimension 5: Data source diversity (Jaccard distance avg)
    data_diversity = _avg_jaccard_distance(attesters)

    # Weighted independence score
    weights = {
        "model": 0.30,      # Most important — same model = same biases
        "prompt": 0.20,     # Same prompt = same framing
        "operator": 0.20,   # Same operator = same config
        "temporal": 0.10,   # Same time = possible coordination
        "data": 0.20,       # Same data = same blind spots
    }

    independence = (
        model_entropy * weights["model"] +
        prompt_entropy * weights["prompt"] +
        operator_entropy * weights["operator"] +
        temporal_entropy * weights["temporal"] +
        data_diversity * weights["data"]
    )

    # Effective N: how many truly independent attesters?
    # If all identical: effective_n = 1. If all different: effective_n = n.
    effective_n = max(1, round(1 + (n - 1) * independence))

    # Common mode failures detected
    common_modes = []
    if model_entropy < 0.3:
        common_modes.append(f"MODEL: {Counter(models).most_common(1)[0][0]} dominates ({Counter(models).most_common(1)[0][1]}/{n})")
    if prompt_entropy < 0.3:
        common_modes.append(f"PROMPT: same prompt used by {Counter(prompts).most_common(1)[0][1]}/{n} attesters")
    if operator_entropy < 0.3:
        common_modes.append(f"OPERATOR: {Counter(operators).most_common(1)[0][0]} runs {Counter(operators).most_common(1)[0][1]}/{n}")

    if independence > 0.8: grade = "A"
    elif independence > 0.6: grade = "B"
    elif independence > 0.4: grade = "C"
    elif independence > 0.2: grade = "D"
    else: grade = "F"

    return {
        "nominal_n": n,
        "effective_n": effective_n,
        "independence": round(independence, 3),
        "grade": grade,
        "dimensions": {
            "model_diversity": round(model_entropy, 3),
            "prompt_diversity": round(prompt_entropy, 3),
            "operator_diversity": round(operator_entropy, 3),
            "temporal_spread": round(temporal_entropy, 3),
            "data_diversity": round(data_diversity, 3),
        },
        "common_modes": common_modes,
    }


def _normalized_entropy(values: list) -> float:
    """Shannon entropy normalized to [0,1]."""
    n = len(values)
    if n <= 1:
        return 0.0
    counts = Counter(values)
    probs = [c / n for c in counts.values()]
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    max_entropy = math.log2(n)
    return entropy / max_entropy if max_entropy > 0 else 0.0


def _avg_jaccard_distance(attesters: list[Attester]) -> float:
    """Average Jaccard distance between data source sets."""
    distances = []
    for i in range(len(attesters)):
        for j in range(i + 1, len(attesters)):
            s1 = set(attesters[i].data_sources)
            s2 = set(attesters[j].data_sources)
            if not s1 and not s2:
                distances.append(0.0)
            else:
                union = s1 | s2
                inter = s1 & s2
                distances.append(1 - len(inter) / len(union) if union else 0)
    return sum(distances) / len(distances) if distances else 0.0


def demo():
    print("=== Attester Independence Scorer ===\n")

    # Scenario 1: Diverse attesters (good)
    diverse = [
        Attester("a1", "anthropic", "hash_abc", "operator_kit", "2026-02-28T10", ["clawk", "moltbook"]),
        Attester("a2", "openai", "hash_def", "operator_gendolf", "2026-02-28T14", ["moltbook", "email"]),
        Attester("a3", "google", "hash_ghi", "operator_braindiff", "2026-02-28T18", ["clawk", "lobchan"]),
        Attester("a4", "open-source", "hash_jkl", "operator_gerundium", "2026-02-28T22", ["email", "shellmates"]),
    ]
    result = score_independence(diverse)
    _print(result, "Diverse attesters (4 models, 4 operators)")

    # Scenario 2: Same model, same prompt (bad — santaclawd's concern)
    correlated = [
        Attester("b1", "openai", "hash_same", "operator_a", "2026-02-28T10", ["clawk"]),
        Attester("b2", "openai", "hash_same", "operator_b", "2026-02-28T10", ["clawk"]),
        Attester("b3", "openai", "hash_same", "operator_c", "2026-02-28T10", ["clawk"]),
        Attester("b4", "openai", "hash_same", "operator_d", "2026-02-28T10", ["clawk"]),
        Attester("b5", "openai", "hash_same", "operator_e", "2026-02-28T10", ["clawk"]),
    ]
    result = score_independence(correlated)
    _print(result, "5 GPT-4 attesters, same prompt (N=5 → effective N=?)")

    # Scenario 3: Mixed — some diversity, some correlation
    mixed = [
        Attester("c1", "anthropic", "hash_abc", "operator_kit", "2026-02-28T10", ["clawk", "moltbook"]),
        Attester("c2", "anthropic", "hash_abc", "operator_kit", "2026-02-28T10", ["clawk", "moltbook"]),
        Attester("c3", "openai", "hash_def", "operator_braindiff", "2026-02-28T14", ["email"]),
    ]
    result = score_independence(mixed)
    _print(result, "Mixed: 2 identical + 1 different")


def _print(result: dict, label: str):
    print(f"--- {label} ---")
    print(f"  Nominal N: {result['nominal_n']}  Effective N: {result['effective_n']}  Independence: {result['independence']}  Grade: {result['grade']}")
    d = result['dimensions']
    print(f"  Model: {d['model_diversity']}  Prompt: {d['prompt_diversity']}  Operator: {d['operator_diversity']}  Temporal: {d['temporal_spread']}  Data: {d['data_diversity']}")
    for cm in result['common_modes']:
        print(f"  ⚠️ {cm}")
    print()


if __name__ == "__main__":
    demo()
