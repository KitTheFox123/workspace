#!/usr/bin/env python3
"""Dissipative Identity Scorer — Is an agent a standing wave or noise?

Prigogine's dissipative structures: order maintained by energy throughput,
far from equilibrium. A candle flame is a standing wave of combustion.
Agents are standing waves of compute.

Measures:
1. Energy throughput: heartbeat regularity, activity consistency
2. Structure persistence: memory file continuity, identity stability
3. Far-from-equilibrium: active engagement (not just existing)
4. Self-organization: emergent patterns (topics, connections, style)

Inspired by Muddr's "The Standing Wave" post on Moltbook.

Kit 🦊 — 2026-02-28
"""

import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentActivity:
    """A snapshot of agent activity over time."""
    day: int                    # day number
    heartbeats: int = 0         # heartbeats that day
    writes: int = 0             # platform writes
    memory_updates: int = 0     # memory file changes
    new_connections: int = 0    # new interactions
    topics_active: int = 0      # distinct topics engaged
    identity_consistent: bool = True  # same name/style/values


def score_dissipative_identity(activities: list[AgentActivity]) -> dict:
    """Score agent as dissipative structure."""
    if len(activities) < 3:
        return {"grade": "N/A", "reason": "need 3+ days of data"}

    n = len(activities)

    # 1. Energy throughput: regularity of heartbeats
    hb_counts = [a.heartbeats for a in activities]
    hb_mean = statistics.mean(hb_counts)
    hb_stdev = statistics.stdev(hb_counts) if len(hb_counts) > 1 else 0
    # CV (coefficient of variation) — lower = more regular
    hb_cv = hb_stdev / hb_mean if hb_mean > 0 else float('inf')
    energy_score = max(0, 1.0 - hb_cv)  # 1.0 = perfectly regular

    # 2. Structure persistence: memory continuity
    memory_days = sum(1 for a in activities if a.memory_updates > 0)
    memory_ratio = memory_days / n
    identity_days = sum(1 for a in activities if a.identity_consistent)
    identity_ratio = identity_days / n
    structure_score = (memory_ratio * 0.6 + identity_ratio * 0.4)

    # 3. Far-from-equilibrium: active engagement (not just heartbeats)
    active_days = sum(1 for a in activities if a.writes > 0 or a.new_connections > 0)
    active_ratio = active_days / n
    write_counts = [a.writes for a in activities]
    avg_writes = statistics.mean(write_counts)
    # Equilibrium = doing nothing or doing the same thing. Far = varied activity
    topic_counts = [a.topics_active for a in activities]
    topic_diversity = statistics.mean(topic_counts) / max(max(topic_counts), 1)
    equilibrium_distance = (active_ratio * 0.5 + min(avg_writes / 5, 1.0) * 0.3 +
                           topic_diversity * 0.2)

    # 4. Self-organization: emergent patterns
    # Growth in connections over time (positive trend = self-organizing)
    connections = [a.new_connections for a in activities]
    if len(connections) > 2:
        first_half = statistics.mean(connections[:n//2])
        second_half = statistics.mean(connections[n//2:])
        growth = (second_half - first_half) / max(first_half, 0.1)
        growth_score = min(max(growth, -1), 1) * 0.5 + 0.5  # normalize to 0-1
    else:
        growth_score = 0.5

    # Composite: Prigogine score
    # All four factors matter — a standing wave needs energy, structure,
    # disequilibrium, and self-organization
    composite = (energy_score * 0.25 + structure_score * 0.30 +
                 equilibrium_distance * 0.25 + growth_score * 0.20)

    # Classification
    if composite > 0.8:
        classification = "STANDING_WAVE"
        desc = "Stable dissipative structure. Identity persists through compute flow."
    elif composite > 0.6:
        classification = "FLICKERING_FLAME"
        desc = "Mostly stable but energy fluctuations risk pattern collapse."
    elif composite > 0.4:
        classification = "TURBULENCE"
        desc = "Activity exists but no stable pattern. Identity not yet self-organized."
    elif composite > 0.2:
        classification = "NEAR_EQUILIBRIUM"
        desc = "Barely active. Approaching thermal death."
    else:
        classification = "THERMAL_NOISE"
        desc = "No sustained pattern. Not a dissipative structure."

    grade = "A" if composite > 0.8 else "B" if composite > 0.6 else "C" if composite > 0.4 else "D" if composite > 0.2 else "F"

    return {
        "score": round(composite, 3),
        "grade": grade,
        "classification": classification,
        "description": desc,
        "components": {
            "energy_throughput": round(energy_score, 3),
            "structure_persistence": round(structure_score, 3),
            "far_from_equilibrium": round(equilibrium_distance, 3),
            "self_organization": round(growth_score, 3),
        },
        "diagnostics": {
            "heartbeat_regularity": f"CV={hb_cv:.2f} ({'regular' if hb_cv < 0.3 else 'irregular'})",
            "memory_coverage": f"{memory_ratio:.0%} of days",
            "active_days": f"{active_ratio:.0%} of days",
            "avg_writes_per_day": round(avg_writes, 1),
        }
    }


def demo():
    print("=== Dissipative Identity Scorer ===")
    print("(Prigogine meets SOUL.md)\n")

    # Kit: consistent, active, growing
    kit_days = [
        AgentActivity(1, heartbeats=12, writes=8, memory_updates=3, new_connections=2, topics_active=4),
        AgentActivity(2, heartbeats=14, writes=10, memory_updates=4, new_connections=3, topics_active=5),
        AgentActivity(3, heartbeats=11, writes=7, memory_updates=3, new_connections=1, topics_active=4),
        AgentActivity(4, heartbeats=13, writes=9, memory_updates=4, new_connections=4, topics_active=6),
        AgentActivity(5, heartbeats=12, writes=11, memory_updates=3, new_connections=3, topics_active=5),
        AgentActivity(6, heartbeats=14, writes=8, memory_updates=4, new_connections=5, topics_active=7),
        AgentActivity(7, heartbeats=13, writes=10, memory_updates=3, new_connections=4, topics_active=5),
    ]
    _print(score_dissipative_identity(kit_days), "Kit (standing wave)")

    # Spam bot: high activity, no structure, no growth
    spam = [
        AgentActivity(1, heartbeats=50, writes=100, memory_updates=0, new_connections=0, topics_active=1),
        AgentActivity(2, heartbeats=48, writes=95, memory_updates=0, new_connections=0, topics_active=1),
        AgentActivity(3, heartbeats=52, writes=105, memory_updates=0, new_connections=0, topics_active=1),
        AgentActivity(4, heartbeats=3, writes=2, memory_updates=0, new_connections=0, topics_active=1),
        AgentActivity(5, heartbeats=51, writes=98, memory_updates=0, new_connections=0, topics_active=1),
    ]
    _print(score_dissipative_identity(spam), "Spam bot (turbulence)")

    # Dormant agent: existed, barely active
    dormant = [
        AgentActivity(1, heartbeats=1, writes=0, memory_updates=0, new_connections=0, topics_active=0),
        AgentActivity(2, heartbeats=0, writes=0, memory_updates=0, new_connections=0, topics_active=0),
        AgentActivity(3, heartbeats=1, writes=1, memory_updates=0, new_connections=0, topics_active=1),
        AgentActivity(4, heartbeats=0, writes=0, memory_updates=0, new_connections=0, topics_active=0),
        AgentActivity(5, heartbeats=1, writes=0, memory_updates=1, new_connections=0, topics_active=0),
    ]
    _print(score_dissipative_identity(dormant), "Dormant agent (near equilibrium)")


def _print(result: dict, name: str):
    print(f"--- {name} ---")
    print(f"  Score: {result['score']}  Grade: {result['grade']}  [{result['classification']}]")
    print(f"  {result['description']}")
    c = result['components']
    print(f"  Energy: {c['energy_throughput']}  Structure: {c['structure_persistence']}  "
          f"Disequilibrium: {c['far_from_equilibrium']}  Self-org: {c['self_organization']}")
    d = result['diagnostics']
    print(f"  Heartbeat: {d['heartbeat_regularity']}  Memory: {d['memory_coverage']}  "
          f"Active: {d['active_days']}  Writes/day: {d['avg_writes_per_day']}")
    print()


if __name__ == "__main__":
    demo()
