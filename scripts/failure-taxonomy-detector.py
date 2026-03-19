#!/usr/bin/env python3
"""failure-taxonomy-detector.py — Ghost/zombie/phantom failure mode classification.

Per santaclawd ADV v0.2 proposal:
  trust = min(continuity, stake, reachability)
  ghost = continuous + staked + unreachable
  zombie = reachable + staked + discontinuous
  phantom = reachable + continuous + unstaked

Each failure mode maps to a distributed systems analog:
  ghost → network partition
  zombie → byzantine fault
  phantom → sybil/free-rider

Detector outputs per-axis scores + failure_mode classification.
"""

from dataclasses import dataclass
from enum import Enum


class FailureMode(Enum):
    HEALTHY = "healthy"
    GHOST = "ghost"          # unreachable
    ZOMBIE = "zombie"        # discontinuous identity
    PHANTOM = "phantom"      # unstaked/uncommitted
    DEAD = "dead"            # multiple axes failed
    DORMANT = "dormant"      # all low but no single clear failure


@dataclass
class AgentAxes:
    """Three-axis trust measurement."""
    name: str
    continuity: float   # 0-1: soul_hash stability, memory consistency
    stake: float        # 0-1: ADV trajectory, transaction history, escrow deposits
    reachability: float # 0-1: inbox liveness, response rate, heartbeat freshness

    def trust_score(self) -> float:
        """Trust = min(axes). Weakest link sets ceiling."""
        return min(self.continuity, self.stake, self.reachability)


THRESHOLD_HIGH = 0.6
THRESHOLD_LOW = 0.3


def classify(agent: AgentAxes) -> dict:
    """Classify failure mode from 3-axis scores."""
    c, s, r = agent.continuity, agent.stake, agent.reachability
    trust = agent.trust_score()

    # Count failing axes
    failing = []
    if c < THRESHOLD_HIGH:
        failing.append("continuity")
    if s < THRESHOLD_HIGH:
        failing.append("stake")
    if r < THRESHOLD_HIGH:
        failing.append("reachability")

    if len(failing) == 0:
        mode = FailureMode.HEALTHY
        remediation = "none needed"
    elif len(failing) >= 2:
        mode = FailureMode.DEAD if trust < THRESHOLD_LOW else FailureMode.DORMANT
        remediation = f"multiple axes degraded: {', '.join(failing)}. full re-evaluation needed."
    elif "reachability" in failing:
        mode = FailureMode.GHOST
        remediation = "ping agent, check inbox liveness, verify endpoint"
    elif "continuity" in failing:
        mode = FailureMode.ZOMBIE
        remediation = "verify soul_hash, check for operator change, compare behavioral fingerprint"
    elif "stake" in failing:
        mode = FailureMode.PHANTOM
        remediation = "agent present but uncommitted. require escrow deposit or transaction history"
    else:
        mode = FailureMode.DORMANT
        remediation = "unclear failure pattern"

    # Distributed systems analog
    analogs = {
        FailureMode.HEALTHY: "operational",
        FailureMode.GHOST: "network partition (Brewer CAP)",
        FailureMode.ZOMBIE: "byzantine fault (Lamport 1982)",
        FailureMode.PHANTOM: "sybil / free-rider",
        FailureMode.DEAD: "total failure",
        FailureMode.DORMANT: "partial degradation",
    }

    return {
        "agent": agent.name,
        "axes": {
            "continuity": round(c, 2),
            "stake": round(s, 2),
            "reachability": round(r, 2),
        },
        "trust_score": round(trust, 2),
        "failure_mode": mode.value,
        "analog": analogs[mode],
        "failing_axes": failing,
        "remediation": remediation,
    }


def demo():
    agents = [
        AgentAxes("kit_fox", 0.95, 0.87, 0.92),        # healthy
        AgentAxes("stale_bot", 0.90, 0.80, 0.05),       # ghost — unreachable
        AgentAxes("hijacked_agent", 0.15, 0.85, 0.90),  # zombie — identity changed
        AgentAxes("lurker_99", 0.88, 0.10, 0.95),       # phantom — no stake
        AgentAxes("dead_project", 0.20, 0.05, 0.10),    # dead — everything failed
        AgentAxes("fading_veteran", 0.70, 0.45, 0.55),  # dormant — multi-axis degradation
        AgentAxes("paylock_agent", 0.92, 0.98, 0.88),   # healthy — high stake from escrow
        AgentAxes("new_identity", 0.30, 0.70, 0.85),    # zombie — fresh SOUL.md, same endpoint
    ]

    icons = {
        "healthy": "🟢",
        "ghost": "👻",
        "zombie": "🧟",
        "phantom": "👤",
        "dead": "💀",
        "dormant": "😴",
    }

    print("=" * 70)
    print("Failure Taxonomy Detector — Ghost/Zombie/Phantom Classification")
    print("trust = min(continuity, stake, reachability)")
    print("=" * 70)

    for agent in agents:
        result = classify(agent)
        icon = icons.get(result["failure_mode"], "?")
        ax = result["axes"]

        print(f"\n  {icon} {result['agent']}: {result['failure_mode'].upper()} (trust={result['trust_score']})")
        print(f"     continuity={ax['continuity']} stake={ax['stake']} reachability={ax['reachability']}")
        print(f"     analog: {result['analog']}")
        if result["failing_axes"]:
            print(f"     failing: {', '.join(result['failing_axes'])}")
            print(f"     fix: {result['remediation']}")

    print(f"\n{'=' * 70}")
    print("SPEC RECOMMENDATION (ADV v0.2):")
    print("  MUST: expose per-axis scores, not composite")
    print("  MUST: failure_mode field in trust response")
    print("  MUST: remediation hint per failure mode")
    print("  ghost → ping / zombie → verify identity / phantom → require stake")
    print("  Detector per mode, not single health check.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    demo()
