#!/usr/bin/env python3
"""
minority-report-scorer.py — Weight dissenting attestors higher, not lower.

When 2-of-3 agree and 1 dissents:
- If majority is correct → minority is wrong (test further)
- If majority is correlated (Knight & Leveson 1986) → minority is the only honest observer

The minority report is the most informative datum in attestation pools.

Usage: python3 minority-report-scorer.py
"""

from dataclasses import dataclass
import hashlib


@dataclass
class Attestation:
    attestor: str
    claim: str  # the observed hash / verdict
    backbone: str  # model/infra behind this attestor
    confidence: float = 0.8


def diversity_score(attestations: list[Attestation]) -> float:
    """How diverse is the attestor pool? 0=monoculture, 1=fully diverse."""
    backbones = set(a.backbone for a in attestations)
    return len(backbones) / len(attestations) if attestations else 0


def find_minority(attestations: list[Attestation]) -> dict:
    """Identify minority/majority split and score informativeness."""
    claims = {}
    for a in attestations:
        claims.setdefault(a.claim, []).append(a)

    if len(claims) == 1:
        return {
            "split": "unanimous",
            "verdict": list(claims.keys())[0],
            "diversity": diversity_score(attestations),
            "confidence": "HIGH" if diversity_score(attestations) > 0.5 else "LOW_MONOCULTURE",
            "minority_report": None
        }

    # Sort by group size
    groups = sorted(claims.items(), key=lambda x: len(x[1]), reverse=True)
    majority_claim, majority_group = groups[0]
    minority_claim, minority_group = groups[1]

    # Correlation check: are majority members on same backbone?
    maj_backbones = set(a.backbone for a in majority_group)
    min_backbones = set(a.backbone for a in minority_group)
    majority_correlated = len(maj_backbones) < len(majority_group)

    # Informativeness scoring
    if majority_correlated:
        # Knight & Leveson: correlated majority = expensive groupthink
        minority_weight = 0.8  # dissenter is likely more informative
        majority_weight = 0.3
        reason = "majority correlated (same backbone) — dissent weighted higher"
    else:
        # Diverse majority = probably correct, but still test minority
        minority_weight = 0.4
        majority_weight = 0.7
        reason = "diverse majority — minority still worth investigating"

    return {
        "split": f"{len(majority_group)}-vs-{len(minority_group)}",
        "majority": {"claim": majority_claim, "attestors": [a.attestor for a in majority_group],
                     "weight": majority_weight, "correlated": majority_correlated},
        "minority_report": {"claim": minority_claim, "attestors": [a.attestor for a in minority_group],
                           "weight": minority_weight, "backbones": list(min_backbones)},
        "action": "INVESTIGATE_MINORITY" if majority_correlated else "VERIFY_MAJORITY",
        "reason": reason
    }


def demo():
    print("=" * 60)
    print("Minority Report Scorer")
    print("Knight & Leveson 1986 — correlated errors in N-version programming")
    print("=" * 60)

    scenarios = [
        {
            "name": "Diverse unanimous (strong)",
            "attestations": [
                Attestation("obs_1", "scope_ok", "claude"),
                Attestation("obs_2", "scope_ok", "gpt"),
                Attestation("obs_3", "scope_ok", "gemini"),
            ]
        },
        {
            "name": "Monoculture unanimous (weak)",
            "attestations": [
                Attestation("obs_1", "scope_ok", "claude"),
                Attestation("obs_2", "scope_ok", "claude"),
                Attestation("obs_3", "scope_ok", "claude"),
            ]
        },
        {
            "name": "Correlated majority, diverse minority (dissent = signal)",
            "attestations": [
                Attestation("obs_1", "scope_ok", "claude"),
                Attestation("obs_2", "scope_ok", "claude"),
                Attestation("obs_3", "scope_DRIFT", "gemini"),
            ]
        },
        {
            "name": "Diverse majority, lone dissenter",
            "attestations": [
                Attestation("obs_1", "scope_ok", "claude"),
                Attestation("obs_2", "scope_ok", "gpt"),
                Attestation("obs_3", "scope_ok", "gemini"),
                Attestation("obs_4", "scope_DRIFT", "llama"),
            ]
        },
        {
            "name": "Even split (no clear majority)",
            "attestations": [
                Attestation("obs_1", "scope_ok", "claude"),
                Attestation("obs_2", "scope_DRIFT", "gpt"),
            ]
        },
    ]

    for s in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {s['name']}")
        result = find_minority(s["attestations"])
        print(f"  Split: {result['split']}")
        if result["minority_report"]:
            print(f"  Majority: {result['majority']['claim']} (weight={result['majority']['weight']}, correlated={result['majority']['correlated']})")
            print(f"  Minority: {result['minority_report']['claim']} (weight={result['minority_report']['weight']})")
            print(f"  Action: {result['action']}")
            print(f"  Reason: {result['reason']}")
        else:
            print(f"  Verdict: {result['verdict']}")
            print(f"  Diversity: {result['diversity']:.2f}")
            print(f"  Confidence: {result['confidence']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("Unanimous monoculture = WEAK (1 opinion × 3 copies)")
    print("Correlated majority + diverse dissenter = INVESTIGATE DISSENT")
    print("Diverse majority + lone dissenter = probably fine, but test")
    print("The minority report is always worth reading.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
