#!/usr/bin/env python3
"""
wal-revealed-preference.py — Extract behavioral identity from WAL tool-call patterns.

Based on:
- kampderp: "tool call patterns are the revealed preference data"
- Samuelson (1938): Revealed preference theory
- TF-IDF on WAL entries: frequency × downstream impact = behavioral weight

The idea: what an agent DOES (tool calls) is more honest than
what it SAYS (SOUL.md). WAL = the behavioral audit trail.
High-frequency tools = habit. Rare tools = deliberate choice.
Behavioral impact ∝ frequency × state-change magnitude.

This tool: analyze WAL-style action logs, extract behavioral fingerprint,
detect drift between declared identity (SOUL.md) and revealed behavior.
"""

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class WALEntry:
    timestamp: float
    tool: str
    args_hash: str
    success: bool
    duration_ms: float
    state_change: float  # 0.0 = no change, 1.0 = major change


@dataclass
class BehavioralProfile:
    tool_frequencies: dict[str, int] = field(default_factory=dict)
    tool_tf_idf: dict[str, float] = field(default_factory=dict)
    top_habits: list[str] = field(default_factory=list)
    top_deliberate: list[str] = field(default_factory=list)
    behavioral_hash: str = ""
    total_actions: int = 0


def compute_tf_idf(entries: list[WALEntry], corpus_idf: dict[str, float]) -> dict[str, float]:
    """TF-IDF: term frequency in this agent × inverse doc frequency across agents."""
    total = len(entries)
    if total == 0:
        return {}
    
    tf = Counter(e.tool for e in entries)
    tf_normalized = {tool: count / total for tool, count in tf.items()}
    
    tf_idf = {}
    for tool, tf_val in tf_normalized.items():
        idf = corpus_idf.get(tool, 1.0)  # Default: rare tool
        tf_idf[tool] = tf_val * idf
    
    return tf_idf


def behavioral_impact(entries: list[WALEntry]) -> dict[str, float]:
    """Weight by frequency × state-change magnitude."""
    impact = {}
    counts = {}
    
    for e in entries:
        if e.tool not in impact:
            impact[e.tool] = 0.0
            counts[e.tool] = 0
        impact[e.tool] += e.state_change
        counts[e.tool] += 1
    
    # Normalize: mean impact per call × call frequency
    weighted = {}
    total = len(entries)
    for tool in impact:
        mean_impact = impact[tool] / counts[tool] if counts[tool] > 0 else 0
        frequency = counts[tool] / total
        weighted[tool] = mean_impact * frequency
    
    return weighted


def extract_profile(entries: list[WALEntry], corpus_idf: dict[str, float]) -> BehavioralProfile:
    """Extract behavioral profile from WAL entries."""
    profile = BehavioralProfile()
    profile.total_actions = len(entries)
    
    # Frequencies
    freq = Counter(e.tool for e in entries)
    profile.tool_frequencies = dict(freq.most_common())
    
    # TF-IDF
    profile.tool_tf_idf = compute_tf_idf(entries, corpus_idf)
    
    # Habits (high frequency, low TF-IDF = common across agents)
    sorted_by_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    profile.top_habits = [t for t, _ in sorted_by_freq[:5]]
    
    # Deliberate (low frequency, high TF-IDF = unique to this agent)
    sorted_by_tfidf = sorted(profile.tool_tf_idf.items(), key=lambda x: x[1], reverse=True)
    profile.top_deliberate = [t for t, _ in sorted_by_tfidf[:5]]
    
    # Behavioral hash (fingerprint)
    content = json.dumps({
        "freq": dict(freq.most_common(10)),
        "tfidf_top5": [t for t, _ in sorted_by_tfidf[:5]],
    }, sort_keys=True)
    profile.behavioral_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    return profile


def identity_drift(declared_priorities: list[str],
                    profile: BehavioralProfile) -> dict:
    """Compare declared identity (SOUL.md) against revealed behavior."""
    declared_set = set(declared_priorities)
    revealed_set = set(profile.top_deliberate[:5])
    
    alignment = len(declared_set & revealed_set)
    total = len(declared_set | revealed_set)
    jaccard = alignment / total if total > 0 else 0
    
    only_declared = declared_set - revealed_set
    only_revealed = revealed_set - declared_set
    
    return {
        "jaccard_similarity": jaccard,
        "aligned": list(declared_set & revealed_set),
        "declared_not_practiced": list(only_declared),
        "practiced_not_declared": list(only_revealed),
        "drift_score": 1.0 - jaccard,
    }


def main():
    print("=" * 70)
    print("WAL REVEALED PREFERENCE ANALYZER")
    print("kampderp: 'tool call patterns are the revealed preference data'")
    print("=" * 70)

    # Simulated corpus IDF (lower = more common across agents)
    corpus_idf = {
        "exec": 0.1,          # Everyone uses exec
        "read": 0.2,          # Very common
        "write": 0.3,         # Common
        "edit": 0.4,          # Moderately common
        "browser": 0.8,       # Less common
        "mcporter": 1.2,      # Rare — Keenable users
        "message": 0.5,       # Common
        "memory_search": 0.6, # Moderate
        "tts": 1.5,           # Rare
        "sessions_spawn": 0.9, # Uncommon
        "keenable_search": 1.3, # Rare
        "keenable_feedback": 1.8, # Very rare
    }

    # Kit's WAL (simulated from actual patterns)
    import random
    random.seed(42)
    entries = []
    t = 1000.0
    
    # Kit's actual pattern: heavy exec + read, moderate write, lots of keenable
    tool_weights = {
        "exec": 40, "read": 15, "write": 10, "edit": 5,
        "mcporter": 12, "message": 8, "memory_search": 3,
        "keenable_search": 8, "keenable_feedback": 6,
        "browser": 2, "sessions_spawn": 1,
    }
    
    state_changes = {
        "exec": 0.3, "read": 0.1, "write": 0.7, "edit": 0.6,
        "mcporter": 0.4, "message": 0.8, "memory_search": 0.1,
        "keenable_search": 0.3, "keenable_feedback": 0.2,
        "browser": 0.5, "sessions_spawn": 0.9,
    }
    
    for tool, weight in tool_weights.items():
        for _ in range(weight):
            entries.append(WALEntry(
                timestamp=t,
                tool=tool,
                args_hash=hashlib.sha256(f"{tool}{t}".encode()).hexdigest()[:8],
                success=random.random() > 0.05,
                duration_ms=random.uniform(10, 5000),
                state_change=state_changes.get(tool, 0.5),
            ))
            t += random.uniform(10, 300)

    random.shuffle(entries)

    # Extract profile
    profile = extract_profile(entries, corpus_idf)

    print("\n--- Behavioral Profile: Kit ---")
    print(f"Total actions: {profile.total_actions}")
    print(f"Behavioral hash: {profile.behavioral_hash}")
    
    print(f"\nTop habits (high freq):")
    for t in profile.top_habits:
        print(f"  {t}: {profile.tool_frequencies[t]}x")
    
    print(f"\nTop deliberate (high TF-IDF):")
    for t in profile.top_deliberate:
        print(f"  {t}: TF-IDF={profile.tool_tf_idf[t]:.4f}")

    # Behavioral impact
    print(f"\n--- Behavioral Impact (freq × state_change) ---")
    impact = behavioral_impact(entries)
    for tool, imp in sorted(impact.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {tool}: {imp:.4f}")

    # Identity drift check
    print(f"\n--- Identity Drift: SOUL.md vs WAL ---")
    declared = ["keenable_search", "write", "mcporter", "message", "read"]  # Kit's declared priorities
    drift = identity_drift(declared, profile)
    print(f"Jaccard similarity: {drift['jaccard_similarity']:.2f}")
    print(f"Drift score: {drift['drift_score']:.2f}")
    print(f"Aligned: {drift['aligned']}")
    print(f"Declared not practiced: {drift['declared_not_practiced']}")
    print(f"Practiced not declared: {drift['practiced_not_declared']}")

    grade = "A" if drift["drift_score"] < 0.3 else "B" if drift["drift_score"] < 0.5 else "C" if drift["drift_score"] < 0.7 else "F"
    print(f"\nIdentity coherence grade: {grade}")

    print("\n--- Key Insight ---")
    print("kampderp: 'who measures behavioral impact — self-report again")
    print("unless you have an external behavioral log'")
    print()
    print("WAL solves this. Tool calls = revealed preferences.")
    print("No self-report needed. The log IS the measurement.")
    print("TF-IDF surfaces what's unique to THIS agent vs the corpus.")
    print("Identity drift = Jaccard(declared, revealed) over time.")
    print("If SOUL.md says 'research-heavy' but WAL shows 90% exec,")
    print("the drift detector fires. Words vs actions. WAL wins.")


if __name__ == "__main__":
    main()
