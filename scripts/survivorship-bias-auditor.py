#!/usr/bin/env python3
"""survivorship-bias-auditor.py — Detect missing/silent agents in trust graphs.

Wald's insight: armor where the returning planes WEREN'T hit.
Trust graphs show active agents. The dangerous signal is who's MISSING.

Detects:
1. Agents who were active but stopped (gone silent)
2. Agents referenced by others but never seen directly (phantom nodes)
3. Temporal gaps where expected activity didn't occur (missing heartbeats)
4. Asymmetric attestations (A attests B, but B never attests anyone)

Based on:
- Wald (1943): survivorship bias in aircraft armor placement
- AnDePeD (Sci Reports 2024): periodic decomposition for anomaly detection
- Graph spatiotemporal process (Info Fusion 2024): missing value handling in multivariate time series
"""

import json
import random
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

@dataclass
class Agent:
    name: str
    first_seen: float  # hours from epoch
    last_seen: float
    activity_count: int = 0
    attested_by: list = field(default_factory=list)
    attests_others: list = field(default_factory=list)
    mentioned_by: list = field(default_factory=list)
    expected_interval_hrs: float = 4.0  # expected heartbeat interval

@dataclass
class SurvivorshipAudit:
    """Results of survivorship bias analysis."""
    silent_agents: list  # were active, now quiet
    phantom_nodes: list  # referenced but never directly observed
    missing_heartbeats: list  # temporal gaps in expected activity
    asymmetric_attestors: list  # attest but are never attested
    bias_score: float  # 0-1, how much the graph is survivorship-biased
    invisible_fraction: float  # what % of the graph we can't see

def generate_trust_graph(n_active=20, n_silent=5, n_phantom=3, hours=720):
    """Generate a realistic trust graph with survivorship bias built in."""
    agents = {}
    now = hours  # current time in hours

    # Active agents — these we can see
    for i in range(n_active):
        name = f"agent_{i:03d}"
        first = random.uniform(0, hours * 0.7)
        last = random.uniform(hours * 0.8, hours)
        agents[name] = Agent(
            name=name,
            first_seen=first,
            last_seen=last,
            activity_count=random.randint(10, 200),
        )

    # Silent agents — were active, went dark
    for i in range(n_silent):
        name = f"silent_{i:03d}"
        first = random.uniform(0, hours * 0.3)
        last = random.uniform(hours * 0.3, hours * 0.6)  # stopped before now
        agents[name] = Agent(
            name=name,
            first_seen=first,
            last_seen=last,
            activity_count=random.randint(5, 50),
        )

    # Build attestation graph (only among visible agents)
    active_names = [n for n, a in agents.items() if a.last_seen > hours * 0.7]
    for name, agent in agents.items():
        # Active agents attest each other
        n_attestations = random.randint(1, min(5, len(active_names)))
        targets = random.sample([n for n in active_names if n != name],
                                min(n_attestations, len(active_names) - 1))
        agent.attests_others = targets
        for t in targets:
            agents[t].attested_by.append(name)

    # Phantom nodes — referenced but not in our graph
    phantoms = [f"phantom_{i:03d}" for i in range(n_phantom)]
    # Some active agents mention phantoms
    for _ in range(n_phantom * 2):
        mentioner = random.choice(active_names)
        phantom = random.choice(phantoms)
        agents[mentioner].attests_others.append(phantom)

    return agents, phantoms, now

def audit_survivorship_bias(agents: dict, phantoms: list, now: float,
                            silence_threshold_hrs: float = 168.0) -> SurvivorshipAudit:
    """
    Analyze a trust graph for survivorship bias.

    silence_threshold_hrs: hours of inactivity before flagging as silent
    """
    # 1. Silent agents: were active, now quiet
    silent = []
    for name, agent in agents.items():
        gap = now - agent.last_seen
        if gap > silence_threshold_hrs and agent.activity_count > 5:
            silent.append({
                "name": name,
                "last_seen_hrs_ago": round(gap, 1),
                "prior_activity": agent.activity_count,
                "was_attested_by": len(agent.attested_by),
                "risk": "high" if agent.attested_by else "medium",
            })

    # 2. Phantom nodes: referenced but never observed
    known_names = set(agents.keys())
    all_referenced = set()
    for agent in agents.values():
        all_referenced.update(agent.attests_others)
        all_referenced.update(agent.mentioned_by)
    phantom_detected = all_referenced - known_names

    # 3. Missing heartbeats: temporal gaps
    missing_hb = []
    for name, agent in agents.items():
        if agent.last_seen > now - 48:  # only check recent agents
            expected_beats = (now - agent.first_seen) / agent.expected_interval_hrs
            if expected_beats > 0:
                actual_rate = agent.activity_count / expected_beats
                if actual_rate < 0.3:  # less than 30% expected activity
                    missing_hb.append({
                        "name": name,
                        "expected_rate": round(expected_beats, 1),
                        "actual_count": agent.activity_count,
                        "coverage": round(actual_rate, 3),
                    })

    # 4. Asymmetric attestors: attest others but never attested themselves
    asymmetric = []
    for name, agent in agents.items():
        if agent.attests_others and not agent.attested_by:
            asymmetric.append({
                "name": name,
                "attests_count": len(agent.attests_others),
                "attested_by_count": 0,
                "risk": "potential sybil or isolated newcomer",
            })

    # Compute overall bias score
    total_nodes = len(agents) + len(phantom_detected)
    visible_active = sum(1 for a in agents.values() if (now - a.last_seen) < silence_threshold_hrs)
    invisible = len(silent) + len(phantom_detected)
    invisible_frac = invisible / max(total_nodes, 1)

    # Bias score: weighted combination
    bias_components = [
        len(silent) / max(len(agents), 1) * 0.35,        # silent fraction
        len(phantom_detected) / max(total_nodes, 1) * 0.25,  # phantom fraction
        len(asymmetric) / max(len(agents), 1) * 0.20,    # asymmetry
        len(missing_hb) / max(visible_active, 1) * 0.20, # missing heartbeats
    ]
    bias_score = min(sum(bias_components), 1.0)

    return SurvivorshipAudit(
        silent_agents=silent,
        phantom_nodes=list(phantom_detected),
        missing_heartbeats=missing_hb,
        asymmetric_attestors=asymmetric,
        bias_score=round(bias_score, 4),
        invisible_fraction=round(invisible_frac, 4),
    )

def main():
    print("=" * 60)
    print("SURVIVORSHIP BIAS AUDITOR")
    print("'Armor where the returning planes WEREN'T hit.' — Wald")
    print("=" * 60)

    # Run simulation
    agents, phantoms, now = generate_trust_graph(
        n_active=25, n_silent=8, n_phantom=4, hours=720
    )

    audit = audit_survivorship_bias(agents, phantoms, now)

    print(f"\n📊 Graph: {len(agents)} known agents, {now:.0f}h observation window")
    print(f"   Bias score: {audit.bias_score:.4f}")
    print(f"   Invisible fraction: {audit.invisible_fraction:.1%}")

    print(f"\n🔇 Silent agents ({len(audit.silent_agents)}):")
    for s in sorted(audit.silent_agents, key=lambda x: -x["last_seen_hrs_ago"])[:5]:
        print(f"   {s['name']}: silent {s['last_seen_hrs_ago']:.0f}h, "
              f"was active ({s['prior_activity']} events), risk={s['risk']}")

    print(f"\n👻 Phantom nodes ({len(audit.phantom_nodes)}):")
    for p in audit.phantom_nodes[:5]:
        print(f"   {p} — referenced but never directly observed")

    print(f"\n💓 Missing heartbeats ({len(audit.missing_heartbeats)}):")
    for m in audit.missing_heartbeats[:5]:
        print(f"   {m['name']}: {m['coverage']:.1%} of expected activity")

    print(f"\n⚖️ Asymmetric attestors ({len(audit.asymmetric_attestors)}):")
    for a in audit.asymmetric_attestors[:5]:
        print(f"   {a['name']}: attests {a['attests_count']}, attested by 0")

    # Wald's lesson
    print(f"\n{'=' * 60}")
    print("WALD'S LESSON:")
    print(f"  You're looking at {len(agents)} agents.")
    print(f"  But {len(audit.silent_agents)} went silent and "
          f"{len(audit.phantom_nodes)} were never seen.")
    print(f"  The {audit.invisible_fraction:.0%} you can't see IS the vulnerability.")
    print(f"  Trust graphs that ignore missing data are armoring the wrong side.")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
