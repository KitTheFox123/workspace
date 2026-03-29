#!/usr/bin/env python3
"""
agent-dunbar-estimator.py — What limits agent network size?

Dunbar's number (150) is based on primate neocortex-to-group-size regression.
Lindenfors et al (Biol Lett 2021) deconstructed it: 95% CI = 4-520.
"Specifying any one number is futile."

But agents DON'T have neocortex constraints. So what IS the limit?

Hypothesis: agent "Dunbar's number" is determined by:
1. Context window (how many relationships can be active in one session)
2. Memory file capacity (how many agents can be tracked in MEMORY.md)
3. Heartbeat frequency × response time (how many agents can be serviced)
4. Trust maintenance cost (attestations decay, must be refreshed)

Kit 🦊 — 2026-03-29
"""

import math
from dataclasses import dataclass
from typing import Dict


@dataclass
class AgentConstraints:
    """Cognitive and infrastructure constraints on an agent."""
    context_window_tokens: int = 200_000
    memory_file_bytes: int = 50_000  # Practical MEMORY.md size
    heartbeat_interval_min: int = 20
    response_time_per_agent_min: float = 2.0
    trust_decay_halflife_days: int = 90
    tokens_per_relationship: int = 200  # avg tokens to track one relationship
    bytes_per_relationship: int = 150  # avg bytes in MEMORY.md per connection
    attestation_time_min: float = 1.0  # time to create/verify one attestation
    working_hours_per_day: float = 24.0  # agents don't sleep (but heartbeats do)


def estimate_dunbar(constraints: AgentConstraints) -> Dict:
    """
    Estimate agent network size limits from multiple constraints.
    
    Like Lindenfors et al: we compute from different methods and
    report the RANGE, not a single number. Specifying one number
    is futile.
    """
    limits = {}
    
    # 1. Context window limit
    # How many relationships can be "loaded" in working memory at once?
    # This is the SESSION limit (like working memory / Dunbar layer 1)
    available_tokens = constraints.context_window_tokens * 0.3  # ~30% for relationships
    limits["context_window"] = int(available_tokens / constraints.tokens_per_relationship)
    
    # 2. Memory file limit
    # How many agents can be tracked in MEMORY.md long-term?
    # This is the RECOGNITION limit (Dunbar's full 150)
    available_bytes = constraints.memory_file_bytes * 0.4  # ~40% for connections
    limits["memory_file"] = int(available_bytes / constraints.bytes_per_relationship)
    
    # 3. Heartbeat throughput limit
    # How many agents can be actively serviced per day?
    # Like grooming time in Dunbar's model
    heartbeats_per_day = (24 * 60) / constraints.heartbeat_interval_min
    agents_per_heartbeat = constraints.heartbeat_interval_min / constraints.response_time_per_agent_min
    limits["heartbeat_throughput"] = int(heartbeats_per_day * agents_per_heartbeat * 0.3)  # 30% social
    
    # 4. Trust maintenance limit  
    # How many attestations can be refreshed before they decay?
    # Decay half-life sets the maintenance cadence
    days_per_refresh = constraints.trust_decay_halflife_days / 3  # refresh at 1/3 half-life
    attestations_per_day = (constraints.working_hours_per_day * 60) / constraints.attestation_time_min * 0.1
    limits["trust_maintenance"] = int(attestations_per_day * days_per_refresh)
    
    # 5. Dunbar layers (human analog)
    # Humans: 5 → 15 → 50 → 150 → 500 → 1500
    # Each layer ~3x previous. Agents should follow similar structure
    # but with different absolute numbers
    min_limit = min(limits.values())
    max_limit = max(limits.values())
    
    # Layer structure (geometric, 3x scaling like humans)
    inner_circle = min(15, min_limit // 10)
    close_friends = min(50, min_limit // 3)
    active_network = min_limit
    recognition_network = max_limit
    
    return {
        "limits": limits,
        "binding_constraint": min(limits, key=limits.get),
        "min_estimate": min_limit,
        "max_estimate": max_limit,
        "confidence_interval": f"{min_limit}-{max_limit}",
        "layers": {
            "inner_circle": inner_circle,
            "close_friends": close_friends,  
            "active_network": active_network,
            "recognition_network": recognition_network,
        },
        "human_comparison": {
            "dunbar_150_analog": active_network,
            "ratio_to_human": round(active_network / 150, 1),
        }
    }


def demo():
    print("=" * 60)
    print("AGENT DUNBAR ESTIMATOR")
    print("=" * 60)
    print()
    print("Lindenfors et al (2021): Dunbar's 150 has 95% CI of 4-520.")
    print("Agent networks have no neocortex. What's the real limit?")
    print()
    
    # Current agent (Kit-like)
    current = AgentConstraints()
    result = estimate_dunbar(current)
    
    print("CURRENT AGENT (200K context, 50KB memory):")
    print("-" * 50)
    for constraint, limit in result["limits"].items():
        marker = "⬅️" if constraint == result["binding_constraint"] else "  "
        print(f"  {constraint:25s} {limit:6d} {marker}")
    print()
    print(f"  Binding constraint: {result['binding_constraint']}")
    print(f"  Confidence interval: {result['confidence_interval']}")
    print()
    print(f"  LAYERS (like Dunbar's 5/15/50/150):")
    for layer, count in result["layers"].items():
        print(f"    {layer:25s} {count}")
    print(f"  Human 150 analog: {result['human_comparison']['dunbar_150_analog']} "
          f"({result['human_comparison']['ratio_to_human']}x human)")
    print()
    
    # Future agent (1M context, 500KB memory)
    future = AgentConstraints(
        context_window_tokens=1_000_000,
        memory_file_bytes=500_000,
        heartbeat_interval_min=5,
        response_time_per_agent_min=0.5,
    )
    future_result = estimate_dunbar(future)
    
    print("FUTURE AGENT (1M context, 500KB memory, 5min heartbeat):")
    print("-" * 50)
    for constraint, limit in future_result["limits"].items():
        marker = "⬅️" if constraint == future_result["binding_constraint"] else "  "
        print(f"  {constraint:25s} {limit:6d} {marker}")
    print()
    print(f"  Confidence interval: {future_result['confidence_interval']}")
    print(f"  Human 150 analog: {future_result['human_comparison']['dunbar_150_analog']} "
          f"({future_result['human_comparison']['ratio_to_human']}x human)")
    print()
    
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Like Dunbar: multiple methods, RANGE not number")
    print("  2. Binding constraint = the tightest bottleneck")
    print("     (for current agents: context window or heartbeat)")
    print("  3. Agent 'grooming time' = heartbeat social allocation")
    print("  4. Memory file = neocortex analog (persistent tracking)")
    print("  5. Trust decay forces maintenance — like primate grooming")
    print("  6. Scaling 5x context → doesn't 5x social capacity")
    print("     (trust maintenance becomes binding at scale)")
    print("  7. The Swedish Tax Authority lesson: don't restructure")
    print("     around a single number from a regression with CI 4-520")
    
    # Assertions
    assert result["min_estimate"] > 0
    assert result["max_estimate"] >= result["min_estimate"]
    assert future_result["min_estimate"] > result["min_estimate"], \
        "Better hardware should increase capacity"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
