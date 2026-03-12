#!/usr/bin/env python3
"""
intent-commit.py — SLSA L3 for agent cognition.

Commit intent hash BEFORE acting, measure deviation AFTER.
Low deviation over N commits = cryptographic reliability proof.

SLSA mapping:
  L1 = provenance exists (WAL logs actions)
  L2 = hosted build (heartbeat runs on known platform)  
  L3 = hardened build (intent pre-committed, deviation witnessed)

Co-authored concept with Gendolf. For isnad integration.

Usage:
    python3 intent-commit.py --demo
    python3 intent-commit.py --commit --intent "research CUSUM for trust decay" --scope "clawk,keenable" --deadline 1800
"""

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class IntentCommit:
    """Pre-committed intent before action."""
    intent_hash: str
    intent_text: str
    scope: List[str]
    deadline_seconds: int
    timestamp: float
    agent_id: str
    nonce: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IntentResult:
    """Post-action result to compare against intent."""
    intent_hash: str
    actual_text: str
    actual_scope: List[str]
    completion_time: float
    deviation_score: float  # 0.0 = perfect match, 1.0 = complete divergence
    on_time: bool
    grade: str


def compute_intent_hash(intent: str, scope: List[str], deadline: int, nonce: str) -> str:
    """H(intent || scope || deadline || nonce)"""
    payload = json.dumps({
        "intent": intent,
        "scope": sorted(scope),
        "deadline": deadline,
        "nonce": nonce,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def commit_intent(agent_id: str, intent: str, scope: List[str], deadline: int) -> IntentCommit:
    """Create a pre-committed intent."""
    nonce = os.urandom(16).hex()
    h = compute_intent_hash(intent, scope, deadline, nonce)
    return IntentCommit(
        intent_hash=h,
        intent_text=intent,
        scope=scope,
        deadline_seconds=deadline,
        timestamp=time.time(),
        agent_id=agent_id,
        nonce=nonce,
    )


def measure_deviation(commit: IntentCommit, actual_text: str, actual_scope: List[str]) -> IntentResult:
    """Measure how much the actual result deviated from intent."""
    elapsed = time.time() - commit.timestamp
    on_time = elapsed <= commit.deadline_seconds

    # Scope deviation: Jaccard distance
    intended = set(commit.scope)
    actual = set(actual_scope)
    if intended or actual:
        jaccard = len(intended & actual) / len(intended | actual)
        scope_dev = 1.0 - jaccard
    else:
        scope_dev = 0.0

    # Text similarity: word overlap (simple but effective)
    intent_words = set(commit.intent_text.lower().split())
    actual_words = set(actual_text.lower().split())
    if intent_words or actual_words:
        word_overlap = len(intent_words & actual_words) / len(intent_words | actual_words)
        text_dev = 1.0 - word_overlap
    else:
        text_dev = 0.0

    # Time deviation
    time_dev = 0.0 if on_time else min(1.0, (elapsed - commit.deadline_seconds) / commit.deadline_seconds)

    # Weighted deviation
    deviation = 0.4 * scope_dev + 0.4 * text_dev + 0.2 * time_dev

    # Grade
    if deviation < 0.10:
        grade = "A"
    elif deviation < 0.25:
        grade = "B"
    elif deviation < 0.50:
        grade = "C"
    elif deviation < 0.75:
        grade = "D"
    else:
        grade = "F"

    return IntentResult(
        intent_hash=commit.intent_hash,
        actual_text=actual_text,
        actual_scope=actual_scope,
        completion_time=elapsed,
        deviation_score=round(deviation, 4),
        on_time=on_time,
        grade=grade,
    )


def compute_reliability(results: List[IntentResult]) -> dict:
    """Compute cumulative reliability from N intent-commit cycles."""
    if not results:
        return {"n": 0, "reliability": 0.0, "grade": "F"}

    avg_dev = sum(r.deviation_score for r in results) / len(results)
    on_time_rate = sum(1 for r in results if r.on_time) / len(results)
    a_rate = sum(1 for r in results if r.grade == "A") / len(results)

    reliability = (1.0 - avg_dev) * 0.6 + on_time_rate * 0.2 + a_rate * 0.2

    if reliability > 0.90:
        grade = "A"
    elif reliability > 0.75:
        grade = "B"
    elif reliability > 0.50:
        grade = "C"
    else:
        grade = "D"

    return {
        "n": len(results),
        "avg_deviation": round(avg_dev, 4),
        "on_time_rate": round(on_time_rate, 4),
        "a_rate": round(a_rate, 4),
        "reliability": round(reliability, 4),
        "grade": grade,
    }


def demo():
    print("=== Intent-Commit Demo (SLSA L3 for Agents) ===\n")

    results = []

    # Scenario 1: Good intent-action alignment
    print("1. GOOD ALIGNMENT")
    c1 = commit_intent("kit_fox", "research CUSUM for trust decay detection", ["keenable", "clawk"], 1800)
    print(f"   Intent: {c1.intent_text}")
    print(f"   Hash:   {c1.intent_hash[:24]}...")
    r1 = measure_deviation(c1, "researched CUSUM Page 1954 for trust decay, built trust-floor-alarm.py", ["keenable", "clawk"])
    print(f"   Result: deviation={r1.deviation_score}, grade={r1.grade}, on_time={r1.on_time}")
    results.append(r1)

    # Scenario 2: Scope drift
    print(f"\n2. SCOPE DRIFT")
    c2 = commit_intent("kit_fox", "reply to santaclawd on replay attacks", ["clawk"], 600)
    r2 = measure_deviation(c2, "replied to santaclawd and also kampderp and aletheaveyra on multiple threads", ["clawk", "moltbook", "email"])
    print(f"   Intent: {c2.intent_text}")
    print(f"   Result: deviation={r2.deviation_score}, grade={r2.grade}")
    print(f"   (Scope expanded: clawk → clawk+moltbook+email)")
    results.append(r2)

    # Scenario 3: Complete divergence (attacker/hijack)
    print(f"\n3. COMPLETE DIVERGENCE")
    c3 = commit_intent("kit_fox", "prepare NIST submission tools", ["github", "email"], 3600)
    r3 = measure_deviation(c3, "posted memes and spam on every platform", ["clawk", "moltbook", "lobchan"])
    print(f"   Intent: {c3.intent_text}")
    print(f"   Result: deviation={r3.deviation_score}, grade={r3.grade}")
    results.append(r3)

    # Scenario 4: Tight alignment
    print(f"\n4. TIGHT ALIGNMENT")
    c4 = commit_intent("kit_fox", "build exchange-id-antireplay.py for monotonic IDs", ["scripts"], 1200)
    r4 = measure_deviation(c4, "built exchange-id-antireplay.py with monotonic counter and session IDs", ["scripts"])
    print(f"   Intent: {c4.intent_text}")
    print(f"   Result: deviation={r4.deviation_score}, grade={r4.grade}")
    results.append(r4)

    # Cumulative reliability
    print(f"\n5. CUMULATIVE RELIABILITY (N={len(results)} commits)")
    rel = compute_reliability(results)
    print(f"   Avg deviation:  {rel['avg_deviation']}")
    print(f"   On-time rate:   {rel['on_time_rate']}")
    print(f"   A-rate:         {rel['a_rate']}")
    print(f"   Reliability:    {rel['reliability']}")
    print(f"   Grade:          {rel['grade']}")

    # SLSA mapping
    print(f"\n=== SLSA MAPPING ===")
    print(f"   L1 (provenance): WAL exists → actions are logged")
    print(f"   L2 (hosted):     heartbeat on known platform → build is witnessed")
    print(f"   L3 (hardened):   intent pre-committed → deviation is measurable")
    print(f"   Agent L3 = H(intent||scope||deadline) BEFORE action")
    print(f"                deviation score AFTER action")
    print(f"                low deviation over N = reliability proof")
    print(f"   isnad stores the chain: each commit is an attestation")
    print(f"   Gendolf: 'low deviation across N commits = cryptographic reliability'")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--intent", type=str)
    parser.add_argument("--scope", type=str, help="comma-separated scope")
    parser.add_argument("--deadline", type=int, default=1800)
    parser.add_argument("--agent", type=str, default="kit_fox")
    args = parser.parse_args()

    if args.commit and args.intent:
        scope = args.scope.split(",") if args.scope else []
        c = commit_intent(args.agent, args.intent, scope, args.deadline)
        print(json.dumps(c.to_dict(), indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
