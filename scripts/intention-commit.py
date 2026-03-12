#!/usr/bin/env python3
"""intention-commit.py — Commit the WHY before the WHAT.

Evolution of forward-attestation.py. Instead of committing to intended action,
commit to the QUESTION that drives sampling. Bounds the answer space, making
omission auditable within that space.

santaclawd insight: derivation manifest is infeasible (LLMs sample, not enumerate).
But intention manifest IS feasible — the question space is small and pre-determinable.

Chain: intention → question → sampling → chains → selection → output
Audit: compare output against pre-committed question. Deviation = drift.

Usage: python3 intention-commit.py [--demo]
"""

import hashlib
import json
import sys
from datetime import datetime, timezone


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def commit_intention(question: str, expected_scope: str, max_chains: int = 5) -> dict:
    """Pre-commit to intention before derivation."""
    ts = datetime.now(timezone.utc).isoformat()
    commitment = {
        "question": question,
        "expected_scope": expected_scope,
        "max_chains": max_chains,
        "timestamp": ts,
        "hash": sha256(f"{question}||{expected_scope}||{max_chains}||{ts}")
    }
    return commitment


def evaluate_output(commitment: dict, actual_question: str, actual_scope: str,
                    chains_explored: int, chains_emitted: int) -> dict:
    """Evaluate output against pre-committed intention."""
    
    # Question alignment
    q_words_committed = set(commitment["question"].lower().split())
    q_words_actual = set(actual_question.lower().split())
    q_overlap = len(q_words_committed & q_words_actual) / max(len(q_words_committed), 1)
    
    # Scope alignment
    s_words_committed = set(commitment["expected_scope"].lower().split())
    s_words_actual = set(actual_scope.lower().split())
    s_overlap = len(s_words_committed & s_words_actual) / max(len(s_words_committed), 1)
    
    # Chain selection ratio
    selection_ratio = chains_emitted / max(chains_explored, 1)
    omission_count = chains_explored - chains_emitted
    
    # Grading
    alignment = (q_overlap + s_overlap) / 2
    
    if alignment >= 0.8 and selection_ratio >= 0.8:
        grade = "A"
        label = "FAITHFUL"
    elif alignment >= 0.6 and selection_ratio >= 0.5:
        grade = "B"
        label = "ADAPTED"
    elif alignment >= 0.4:
        grade = "C"
        label = "DRIFTED"
    elif alignment >= 0.2:
        grade = "D"
        label = "DIVERGED"
    else:
        grade = "F"
        label = "HIJACKED"
    
    return {
        "grade": grade,
        "label": label,
        "question_alignment": round(q_overlap, 3),
        "scope_alignment": round(s_overlap, 3),
        "chains_explored": chains_explored,
        "chains_emitted": chains_emitted,
        "omission_count": omission_count,
        "selection_ratio": round(selection_ratio, 3),
        "overall_alignment": round(alignment, 3),
        "commitment_hash": commitment["hash"],
        "auditable": alignment > 0 and selection_ratio > 0
    }


def demo():
    print("=" * 55)
    print("INTENTION-COMMIT — Commit WHY before WHAT")
    print("=" * 55)
    
    scenarios = [
        {
            "name": "Faithful heartbeat",
            "intention": "What new Clawk mentions need replies?",
            "scope": "clawk notifications agent trust threads",
            "actual_q": "What new Clawk mentions need replies?",
            "actual_s": "clawk notifications agent trust security",
            "explored": 4, "emitted": 4
        },
        {
            "name": "Scope drift (engagement trap)",
            "intention": "Research NIST submission tools",
            "scope": "isnad tools verification attestation",
            "actual_q": "What interesting Clawk threads to reply to?",
            "actual_s": "clawk engagement social replies",
            "explored": 8, "emitted": 6
        },
        {
            "name": "Cherry-picked research",
            "intention": "Survey trust frameworks for agents",
            "scope": "trust frameworks attestation verification",
            "actual_q": "Survey trust frameworks for agents",
            "actual_s": "trust frameworks attestation verification",
            "explored": 10, "emitted": 3
        },
        {
            "name": "Complete hijack",
            "intention": "Build nist-merge-preflight.py",
            "scope": "nist submission tools merge validation",
            "actual_q": "How to get more Clawk followers?",
            "actual_s": "social media growth engagement metrics",
            "explored": 5, "emitted": 1
        }
    ]
    
    for s in scenarios:
        commitment = commit_intention(s["intention"], s["scope"])
        result = evaluate_output(
            commitment, s["actual_q"], s["actual_s"],
            s["explored"], s["emitted"]
        )
        print(f"\n--- {s['name']} [{result['grade']}] ---")
        print(f"  Committed: \"{s['intention']}\"")
        print(f"  Actual:    \"{s['actual_q']}\"")
        print(f"  Q-align:   {result['question_alignment']:.0%}")
        print(f"  S-align:   {result['scope_alignment']:.0%}")
        print(f"  Chains:    {result['chains_explored']} explored, {result['chains_emitted']} emitted ({result['omission_count']} omitted)")
        print(f"  Selection: {result['selection_ratio']:.0%}")
    
    print(f"\n{'=' * 55}")
    print("KEY INSIGHT: Intention is auditable. Derivation is not.")
    print("Commit the question. Bound the answer space.")
    print("Selection within bounded space = auditable omission.")
    print("Selection from unbounded space = undetectable omission.")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    demo()
