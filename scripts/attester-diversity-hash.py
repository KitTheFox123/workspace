#!/usr/bin/env python3
"""
attester-diversity-hash.py — Infrastructure diversity scoring for trust receipts.

Per santaclawd (2026-03-15): diversity hash must be IN the receipt so consumers
can audit at verification time, not just trust issuance-time claims.

Granovetter cascade risk: 5 attesters on AWS us-east-1 = 1 attester in practice.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum


class DiversityAxis(Enum):
    INFRASTRUCTURE = "infrastructure"  # Cloud provider / region / self-hosted
    MODEL = "model"                    # LLM provider / model family
    OPERATOR = "operator"              # Human or org controlling the agent
    GEOGRAPHY = "geography"            # Physical jurisdiction


@dataclass
class AttesterProfile:
    agent_id: str
    infrastructure: str   # e.g. "aws:us-east-1", "hetzner:de", "self-hosted"
    model: str           # e.g. "anthropic:opus", "openai:gpt4", "local:llama"
    operator: str        # e.g. "org:acme", "individual:alice"
    geography: str       # e.g. "US", "DE", "JP"


def compute_diversity_score(attesters: list[AttesterProfile]) -> dict:
    """
    Score diversity across 4 axes. 
    Per-axis: unique_values / total_attesters.
    Overall: geometric mean (one monoculture axis tanks the whole score).
    """
    n = len(attesters)
    if n == 0:
        return {"score": 0.0, "grade": "F", "axes": {}, "hash": ""}
    if n == 1:
        return {"score": 0.0, "grade": "F", "axes": {}, "hash": _hash_profiles(attesters),
                "warning": "single attester = no diversity"}

    axes = {}
    for axis in DiversityAxis:
        values = [getattr(a, axis.value) for a in attesters]
        unique = len(set(values))
        ratio = unique / n
        axes[axis.value] = {
            "unique": unique,
            "total": n,
            "ratio": round(ratio, 3),
            "values": sorted(set(values)),
        }

    # Geometric mean — one bad axis kills the score
    import math
    ratios = [axes[a]["ratio"] for a in axes]
    geo_mean = math.prod(ratios) ** (1 / len(ratios))

    # Grade
    if geo_mean >= 0.8:
        grade = "A"
    elif geo_mean >= 0.6:
        grade = "B"
    elif geo_mean >= 0.4:
        grade = "C"
    elif geo_mean >= 0.2:
        grade = "D"
    else:
        grade = "F"

    # Diversity hash — goes INTO the receipt
    div_hash = _hash_profiles(attesters)

    # Cascade risk warnings
    warnings = []
    for axis_name, axis_data in axes.items():
        if axis_data["ratio"] < 0.5:
            dominant = max(set([getattr(a, axis_name) for a in attesters]),
                         key=lambda v: sum(1 for a in attesters if getattr(a, axis_name) == v))
            count = sum(1 for a in attesters if getattr(a, axis_name) == dominant)
            warnings.append(
                f"Granovetter risk: {count}/{n} attesters share {axis_name}={dominant}"
            )

    return {
        "score": round(geo_mean, 3),
        "grade": grade,
        "axes": axes,
        "hash": div_hash,
        "warnings": warnings,
    }


def _hash_profiles(attesters: list[AttesterProfile]) -> str:
    """Deterministic hash of attester infrastructure profiles."""
    data = sorted([
        f"{a.agent_id}:{a.infrastructure}:{a.model}:{a.operator}:{a.geography}"
        for a in attesters
    ])
    return hashlib.sha256("|".join(data).encode()).hexdigest()[:16]


def embed_in_receipt(receipt: dict, diversity_result: dict) -> dict:
    """Embed diversity hash + score in L3.5 trust receipt."""
    receipt["attester_diversity"] = {
        "hash": diversity_result["hash"],
        "score": diversity_result["score"],
        "grade": diversity_result["grade"],
        "attester_count": sum(1 for _ in diversity_result.get("axes", {}).values()),
    }
    if diversity_result.get("warnings"):
        receipt["attester_diversity"]["warnings"] = diversity_result["warnings"]
    return receipt


def demo():
    print("=== Attester Diversity Hash ===\n")

    # Scenario 1: Monoculture (all AWS, all Opus, same operator)
    mono = [
        AttesterProfile("agent-1", "aws:us-east-1", "anthropic:opus", "org:acme", "US"),
        AttesterProfile("agent-2", "aws:us-east-1", "anthropic:opus", "org:acme", "US"),
        AttesterProfile("agent-3", "aws:us-east-1", "anthropic:opus", "org:acme", "US"),
        AttesterProfile("agent-4", "aws:us-east-1", "anthropic:opus", "org:acme", "US"),
        AttesterProfile("agent-5", "aws:us-east-1", "anthropic:opus", "org:acme", "US"),
    ]
    r1 = compute_diversity_score(mono)
    print(f"🔴 Monoculture (5× AWS/Opus/Acme/US)")
    print(f"   Score: {r1['score']} ({r1['grade']})")
    print(f"   Hash: {r1['hash']}")
    for w in r1.get("warnings", []):
        print(f"   ⚠️  {w}")
    print()

    # Scenario 2: Diverse
    diverse = [
        AttesterProfile("agent-1", "aws:us-east-1", "anthropic:opus", "org:acme", "US"),
        AttesterProfile("agent-2", "hetzner:de", "openai:gpt4", "org:beta", "DE"),
        AttesterProfile("agent-3", "gcp:asia-east", "anthropic:sonnet", "individual:carol", "JP"),
        AttesterProfile("agent-4", "self-hosted", "local:llama", "individual:dave", "BR"),
        AttesterProfile("agent-5", "azure:eu-west", "deepseek:v3", "org:echo", "IE"),
    ]
    r2 = compute_diversity_score(diverse)
    print(f"🟢 Diverse (5 providers, 5 models, 5 operators, 5 countries)")
    print(f"   Score: {r2['score']} ({r2['grade']})")
    print(f"   Hash: {r2['hash']}")
    for w in r2.get("warnings", []):
        print(f"   ⚠️  {w}")
    print()

    # Scenario 3: Partial diversity (infra diverse, operator concentrated)
    partial = [
        AttesterProfile("agent-1", "aws:us-east-1", "anthropic:opus", "org:acme", "US"),
        AttesterProfile("agent-2", "hetzner:de", "openai:gpt4", "org:acme", "DE"),
        AttesterProfile("agent-3", "gcp:asia-east", "anthropic:sonnet", "org:acme", "JP"),
        AttesterProfile("agent-4", "self-hosted", "local:llama", "org:acme", "BR"),
    ]
    r3 = compute_diversity_score(partial)
    print(f"🟡 Partial (4 providers, 4 models, 1 operator, 4 countries)")
    print(f"   Score: {r3['score']} ({r3['grade']})")
    print(f"   Hash: {r3['hash']}")
    for w in r3.get("warnings", []):
        print(f"   ⚠️  {w}")
    print()

    # Show receipt embedding
    print("=== Receipt Embedding ===")
    receipt = {"agent_id": "kit_fox", "version": "L3.5-v0.2"}
    embedded = embed_in_receipt(receipt, r2)
    print(json.dumps(embedded, indent=2))


if __name__ == "__main__":
    demo()
