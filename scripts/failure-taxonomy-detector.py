#!/usr/bin/env python3
"""failure-taxonomy-detector.py — Detect ghost/zombie/phantom agents.

Per santaclawd ADV v0.2 failure taxonomy:
  ghost   = continuous + staked + UNREACHABLE
  zombie  = reachable + staked + DISCONTINUOUS
  phantom = reachable + continuous + UNSTAKED

trust = min(continuity, stake, reachability)
The failing axis tells you exactly what attack you're looking at.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class FailureMode(Enum):
    HEALTHY = "HEALTHY"
    GHOST = "GHOST"       # unreachable
    ZOMBIE = "ZOMBIE"     # discontinuous
    PHANTOM = "PHANTOM"   # unstaked
    DEAD = "DEAD"         # multiple failures


@dataclass
class AgentState:
    name: str
    # Continuity: monotonic sequence with no gaps > threshold
    last_sequence_id: int
    expected_sequence_id: int  # what we'd expect next
    sequence_gap_count: int    # gaps detected
    # Stake: on-chain or escrow commitment
    stake_amount: float        # SOL or equivalent
    stake_verified: bool       # verified on-chain
    # Reachability: responds to pings
    last_ping_response: datetime
    ping_timeout: timedelta = timedelta(hours=24)

    @property
    def is_continuous(self) -> bool:
        return self.sequence_gap_count <= 2  # allow 2 small gaps

    @property
    def is_staked(self) -> bool:
        return self.stake_verified and self.stake_amount > 0

    @property
    def is_reachable(self) -> bool:
        return (datetime(2026, 3, 19, 20, 0) - self.last_ping_response) < self.ping_timeout


def classify(agent: AgentState) -> dict:
    """Classify agent failure mode."""
    axes = {
        "continuity": agent.is_continuous,
        "stake": agent.is_staked,
        "reachability": agent.is_reachable,
    }
    failing = [k for k, v in axes.items() if not v]

    if not failing:
        mode = FailureMode.HEALTHY
    elif len(failing) > 1:
        mode = FailureMode.DEAD
    elif "reachability" in failing:
        mode = FailureMode.GHOST
    elif "continuity" in failing:
        mode = FailureMode.ZOMBIE
    elif "stake" in failing:
        mode = FailureMode.PHANTOM
    else:
        mode = FailureMode.DEAD

    # trust = min(axis scores)
    scores = {
        "continuity": 1.0 if agent.is_continuous else max(0, 1.0 - agent.sequence_gap_count * 0.2),
        "stake": 1.0 if agent.is_staked else 0.0,
        "reachability": 1.0 if agent.is_reachable else 0.0,
    }
    trust = min(scores.values())

    # Structured RECOMMENDED_ACTION per santaclawd (2026-03-20)
    # "diagnostic without prescription is just anxiety"
    RECOMMENDED_ACTIONS = {
        FailureMode.HEALTHY: {
            "action": "NONE",
            "protocol": "continue_monitoring",
            "urgency": "LOW",
            "spec_ref": "ADV-v0.2-§4.1",
            "description": "agent healthy, no intervention needed",
        },
        FailureMode.GHOST: {
            "action": "REACHABILITY_CHECK",
            "protocol": "send_probe_receipt",
            "urgency": "MEDIUM",
            "spec_ref": "ADV-v0.2-§4.3",
            "description": "verify endpoint alive, send wake-up receipt, check DNS/network",
            "escalation": "if unreachable >72h, downgrade trust to 0.0",
        },
        FailureMode.ZOMBIE: {
            "action": "CONTINUITY_VERIFY",
            "protocol": "request_reissue_receipt",
            "urgency": "HIGH",
            "spec_ref": "ADV-v0.2-§4.2",
            "description": "investigate sequence gaps — missed receipts or selective emission",
            "escalation": "if gaps >10, require REISSUE with predecessor_hash",
        },
        FailureMode.PHANTOM: {
            "action": "STAKE_VALIDATE",
            "protocol": "verify_onchain_escrow",
            "urgency": "HIGH",
            "spec_ref": "ADV-v0.2-§4.4",
            "description": "verify stake on-chain, check escrow contract, require re-stake",
            "escalation": "if unstaked >7d, classify as sybil candidate",
        },
        FailureMode.DEAD: {
            "action": "QUARANTINE",
            "protocol": "isolate_and_audit",
            "urgency": "CRITICAL",
            "spec_ref": "ADV-v0.2-§4.5",
            "description": "multiple axes failed — quarantine and full audit",
            "escalation": "revoke all active attestations",
        },
    }

    recommended = RECOMMENDED_ACTIONS[mode]

    return {
        "agent": agent.name,
        "mode": mode.value,
        "trust": round(trust, 2),
        "axes": {k: "✅" if v else "❌" for k, v in axes.items()},
        "scores": {k: round(v, 2) for k, v in scores.items()},
        "failing": failing or ["none"],
        "recommended_action": recommended,
    }


# Test agents
now = datetime(2026, 3, 19, 20, 0)
agents = [
    AgentState("healthy_agent", 100, 101, 0, 0.05, True, now - timedelta(hours=1)),
    AgentState("ghost_agent", 100, 101, 0, 0.05, True, now - timedelta(days=3)),
    AgentState("zombie_agent", 50, 100, 12, 0.05, True, now - timedelta(hours=2)),
    AgentState("phantom_agent", 100, 101, 0, 0.0, False, now - timedelta(hours=1)),
    AgentState("dead_agent", 10, 100, 20, 0.0, False, now - timedelta(days=7)),
    AgentState("near_ghost", 100, 101, 0, 0.05, True, now - timedelta(hours=23)),
]

print("=" * 65)
print("Failure Taxonomy Detector — ghost/zombie/phantom (ADV v0.2)")
print("trust = min(continuity, stake, reachability)")
print("=" * 65)

icons = {"HEALTHY": "🟢", "GHOST": "👻", "ZOMBIE": "🧟", "PHANTOM": "👤", "DEAD": "💀"}

for a in agents:
    r = classify(a)
    icon = icons[r["mode"]]
    print(f"\n  {icon} {r['agent']}: {r['mode']} (trust={r['trust']})")
    print(f"     continuity:{r['axes']['continuity']} stake:{r['axes']['stake']} reachability:{r['axes']['reachability']}")
    print(f"     scores: {r['scores']}")
    ra = r["recommended_action"]
    if r["mode"] != "HEALTHY":
        print(f"     action: {ra['action']} ({ra['urgency']})")
        print(f"     protocol: {ra['protocol']}")
        print(f"     spec_ref: {ra['spec_ref']}")
        if "escalation" in ra:
            print(f"     escalation: {ra['escalation']}")

print(f"\n{'=' * 65}")
print("INSIGHT: One detector per failure mode, not one score.")
print("ghost = ping it. zombie = check sequence. phantom = check chain.")
print(f"{'=' * 65}")


if __name__ == "__main__":
    pass  # demo runs at import
