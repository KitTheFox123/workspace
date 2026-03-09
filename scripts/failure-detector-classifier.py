#!/usr/bin/env python3
"""failure-detector-classifier.py — Chandra-Toueg failure detector classification for agent monitors.

Maps agent monitoring architectures to Chandra-Toueg failure detector classes
(P, S, ◇P, ◇S). The weakest class that solves consensus is ◇S — our heartbeat
system needs to achieve at least that.

Key insight: ◇S (eventually strong) = eventually, some non-faulty process is never
suspected. That's enough for consensus. Our heartbeat = ◇P (eventually perfect) —
stronger than needed, but the "eventually" part is load-bearing.

Based on: Chandra & Toueg, JACM 43(2):225-267, 1996.

Usage:
    python3 failure-detector-classifier.py [--demo] [--classify MONITOR_TYPE]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class MonitorProfile:
    """Agent monitor mapped to Chandra-Toueg classification."""
    name: str
    description: str
    completeness: str  # strong or weak
    accuracy: str      # strong, weak, eventually_strong, eventually_weak
    ct_class: str      # P, S, ◇P, ◇S
    solves_consensus: bool
    agent_example: str
    failure_mode: str
    grade: str


MONITOR_PROFILES = [
    MonitorProfile(
        name="synchronous_heartbeat",
        description="Fixed-interval heartbeat with known upper bound on delay",
        completeness="strong",
        accuracy="strong",
        ct_class="P (Perfect)",
        solves_consensus=True,
        agent_example="Platform-controlled heartbeat with fixed network, no async",
        failure_mode="Assumes synchrony — false positives if network delays exceed bound",
        grade="A"
    ),
    MonitorProfile(
        name="adaptive_heartbeat",
        description="Heartbeat with adaptive timeout (2x max observed RTT)",
        completeness="strong",
        accuracy="eventually_strong",
        ct_class="◇P (Eventually Perfect)",
        solves_consensus=True,
        agent_example="isnad heartbeat — eventually stops suspecting live agents",
        failure_mode="Initial period of false positives until timeout stabilizes",
        grade="A-"
    ),
    MonitorProfile(
        name="gossip_failure_detector",
        description="van Renesse gossip-style with T_fail and T_cleanup",
        completeness="strong",
        accuracy="eventually_strong",
        ct_class="◇P (Eventually Perfect)",
        solves_consensus=True,
        agent_example="scope-gossip-sim.py — O(log N) detection, survives partition",
        failure_mode="T_cleanup=2×T_fail prevents zombie members; initial false positives",
        grade="A-"
    ),
    MonitorProfile(
        name="single_trusted_monitor",
        description="One trusted monitor that all agents report to",
        completeness="strong",
        accuracy="weak",
        ct_class="S (Strong)",
        solves_consensus=True,
        agent_example="Platform operator as sole monitor — never suspected itself",
        failure_mode="Monitor is SPOF; if compromised, all trust collapses",
        grade="B"
    ),
    MonitorProfile(
        name="self_attestation",
        description="Agent monitors itself and reports status",
        completeness="weak",
        accuracy="eventually_weak",
        ct_class="◇S (Eventually Strong)",
        solves_consensus=True,
        agent_example="Agent self-reporting health — confused deputy",
        failure_mode="Weakest useful class; initial chaos period unbounded",
        grade="C"
    ),
    MonitorProfile(
        name="no_monitor",
        description="No failure detection mechanism",
        completeness="none",
        accuracy="none",
        ct_class="None",
        solves_consensus=False,
        agent_example="Agent runs without any heartbeat or attestation",
        failure_mode="FLP impossibility — cannot solve consensus without failure detector",
        grade="F"
    ),
    MonitorProfile(
        name="phi_accrual",
        description="Φ accrual failure detector — continuous suspicion level",
        completeness="strong",
        accuracy="eventually_strong",
        ct_class="◇P (Eventually Perfect)",
        solves_consensus=True,
        agent_example="liveness-renewal.py — suspicion as continuous value not binary",
        failure_mode="Threshold selection affects false positive rate",
        grade="A"
    ),
    MonitorProfile(
        name="three_signal_verdict",
        description="Liveness × Intent × Drift conjunction monitor",
        completeness="strong",
        accuracy="eventually_strong",
        ct_class="◇P (Eventually Perfect) — with gray failure detection",
        solves_consensus=True,
        agent_example="three-signal-verdict.py — differential observability",
        failure_mode="Requires 3 independent channels; any 2 correlated = degraded",
        grade="A+"
    ),
]


def classify(name: str) -> dict:
    for p in MONITOR_PROFILES:
        if p.name == name:
            return asdict(p)
    return {"error": f"Unknown monitor: {name}"}


def demo():
    print("=" * 65)
    print("CHANDRA-TOUEG FAILURE DETECTOR CLASSIFICATION")
    print("Agent Monitoring Architectures")
    print("=" * 65)
    print()
    print("Key: ◇S (eventually strong) = weakest that solves consensus")
    print("     FLP impossibility: no consensus without failure detector")
    print()

    for p in MONITOR_PROFILES:
        consensus = "✅" if p.solves_consensus else "❌"
        print(f"[{p.grade}] {p.name}")
        print(f"    Class: {p.ct_class} {consensus}")
        print(f"    Completeness: {p.completeness} | Accuracy: {p.accuracy}")
        print(f"    Example: {p.agent_example}")
        print(f"    Failure: {p.failure_mode}")
        print()

    print("-" * 65)
    print("HIERARCHY: P > {S, ◇P} > ◇S > None")
    print("S and ◇P cannot simulate each other.")
    print("◇S is the WEAKEST class that solves consensus.")
    print()
    print("INSIGHT: Most agent monitoring is ◇P (eventually perfect).")
    print("The 'eventually' part is the initial chaos period —")
    print("heartbeat timeouts must stabilize before trust is reliable.")
    print("Three-signal verdict adds gray failure detection on top.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--classify", type=str)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.classify:
        print(json.dumps(classify(args.classify), indent=2))
    elif args.json:
        print(json.dumps([asdict(p) for p in MONITOR_PROFILES], indent=2))
    else:
        demo()
