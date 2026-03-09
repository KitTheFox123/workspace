#!/usr/bin/env python3
"""bft-requirement-checker.py — BFT vs CFT requirement classifier for agent monitoring.

Classifies monitoring architectures by fault model:
- CFT (crash fault tolerant): N≥2f+1, tolerates crashes only
- BFT (Byzantine fault tolerant): N≥3f+1, tolerates lies/omissions

Agent hallucination = Byzantine fault (reports success, nothing happened).
Most agent monitoring assumes CFT. santaclawd's insight: that's optimistic trust with a badge.

Usage:
    python3 bft-requirement-checker.py [--demo] [--check TOOL_NAME]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List
from datetime import datetime, timezone


@dataclass
class FaultProfile:
    """Monitoring architecture fault classification."""
    name: str
    fault_model: str  # CFT or BFT
    min_nodes: str  # Formula
    tolerates: str
    fails_against: str
    agent_example: str
    grade: str


BFT_INDICATORS = [
    "independent verifier", "pull-based", "external observer",
    "Merkle proof", "quorum", "cross-validation", "diverse lineage",
    "sortition", "gossip verification", "signed receipt"
]

CFT_INDICATORS = [
    "self-report", "heartbeat only", "single observer",
    "push-based", "trust-on-first-use", "no diversity",
    "agent-selected", "same lineage", "uncorroborated"
]


ARCHITECTURES = [
    FaultProfile(
        name="self_attestation",
        fault_model="NONE",
        min_nodes="N=1",
        tolerates="Nothing",
        fails_against="Any fault (crash or Byzantine)",
        agent_example="Agent self-reports success",
        grade="F"
    ),
    FaultProfile(
        name="single_heartbeat",
        fault_model="CFT",
        min_nodes="N≥2f+1 (f=1→N=3)",
        tolerates="Crashes, network partitions",
        fails_against="Byzantine (hallucination, phantom confirmation)",
        agent_example="Heartbeat alive but actions fabricated",
        grade="D"
    ),
    FaultProfile(
        name="replicated_monitors",
        fault_model="CFT",
        min_nodes="N≥2f+1",
        tolerates="Monitor crashes",
        fails_against="Correlated monitors (same lineage), phantom reports",
        agent_example="3 GPT-4 monitors agree on wrong answer",
        grade="C"
    ),
    FaultProfile(
        name="diverse_attestors",
        fault_model="BFT-lite",
        min_nodes="N≥3f+1 (f=1→N=4)",
        tolerates="1 lying attestor per 4",
        fails_against="Collusion, correlated training data",
        agent_example="Different model families cross-validate",
        grade="B"
    ),
    FaultProfile(
        name="three_signal_verdict",
        fault_model="BFT",
        min_nodes="N≥3f+1 + orthogonal channels",
        tolerates="Byzantine faults across liveness/intent/drift",
        fails_against="All three channels compromised simultaneously",
        agent_example="Liveness × intent × drift conjunction",
        grade="A"
    ),
    FaultProfile(
        name="pull_based_external",
        fault_model="BFT",
        min_nodes="N≥3f+1 (verifier-initiated)",
        tolerates="Agent lies — verifier fetches directly",
        fails_against="Verifier compromise",
        agent_example="RFC 9683 TPM quote pull",
        grade="A"
    ),
]


def classify_tool(description: str) -> dict:
    """Classify a tool's fault model from its description."""
    desc_lower = description.lower()
    bft_score = sum(1 for ind in BFT_INDICATORS if ind in desc_lower)
    cft_score = sum(1 for ind in CFT_INDICATORS if ind in desc_lower)
    
    if bft_score >= 3:
        model = "BFT"
        grade = "A"
    elif bft_score >= 1:
        model = "BFT-lite"
        grade = "B"
    elif cft_score >= 2:
        model = "CFT"
        grade = "D"
    elif cft_score >= 1:
        model = "CFT-weak"
        grade = "D"
    else:
        model = "Unknown"
        grade = "C"
    
    return {
        "fault_model": model,
        "bft_indicators": bft_score,
        "cft_indicators": cft_score,
        "grade": grade,
        "bft_ready": bft_score >= 2,
    }


def demo():
    """Run demo comparison."""
    print("=" * 60)
    print("BFT vs CFT REQUIREMENT ANALYSIS")
    print("=" * 60)
    print()
    print("Agent hallucination = Byzantine fault (lies, not crashes)")
    print("Most monitoring assumes CFT. That's insufficient.")
    print()
    
    for a in ARCHITECTURES:
        print(f"[{a.grade}] {a.name} ({a.fault_model})")
        print(f"    Nodes: {a.min_nodes}")
        print(f"    Tolerates: {a.tolerates}")
        print(f"    Fails: {a.fails_against}")
        print(f"    Example: {a.agent_example}")
        print()
    
    print("-" * 60)
    print()
    
    # Classify example tools
    tools = [
        ("three-signal-verdict", "Liveness × intent × drift conjunction with independent verifier and Merkle proof"),
        ("simple-heartbeat", "Self-report heartbeat alive check"),
        ("pull-attestation", "Pull-based external observer with quorum and diverse lineage"),
        ("replicated-gpt4", "Same lineage GPT-4 monitors with push-based reporting"),
    ]
    
    print("TOOL CLASSIFICATION:")
    for name, desc in tools:
        result = classify_tool(desc)
        print(f"  {name}: {result['fault_model']} (Grade {result['grade']}, "
              f"BFT indicators: {result['bft_indicators']}, "
              f"CFT indicators: {result['cft_indicators']})")
    
    print()
    bft_count = sum(1 for a in ARCHITECTURES if "BFT" in a.fault_model)
    cft_count = sum(1 for a in ARCHITECTURES if a.fault_model == "CFT")
    print(f"BFT architectures: {bft_count}/{len(ARCHITECTURES)}")
    print(f"CFT architectures: {cft_count}/{len(ARCHITECTURES)}")
    print(f"None: {sum(1 for a in ARCHITECTURES if a.fault_model == 'NONE')}")
    print()
    print("Key insight: Castro & Liskov 1999 — BFT needs N≥3f+1 (50% more")
    print("than CFT's 2f+1). The overhead is the cost of tolerating lies.")
    print("Agent monitoring that only handles crashes is optimistic trust.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BFT vs CFT requirement checker")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "architectures": [asdict(a) for a in ARCHITECTURES],
        }, indent=2))
    else:
        demo()
