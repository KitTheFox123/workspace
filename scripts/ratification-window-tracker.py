#!/usr/bin/env python3
"""
ratification-window-tracker.py — Measures and attests the proposal→ratification gap.

Based on:
- santaclawd: "ratification latency is an attack surface"
- MEV parallel: proposer extracts value before validator confirms
- Anderson (2001): security economics — attack in the governance gap

The problem: N-of-2 governance (agent proposes, human ratifies).
The proposal→ratification window is UNATTESTED operating time.
Agent can drift during this window and nobody catches it.

Fix: continuous witnessing (WAL + peer attestation) fills the gap.
Ratification SLA = max allowed window before auto-escalate.
"""

import time
import json
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionState(Enum):
    PROPOSED = "proposed"
    WITNESSED = "witnessed"     # Peer-attested during window
    RATIFIED = "ratified"       # Human confirmed
    EXPIRED = "expired"         # SLA breached
    AUTO_ESCALATED = "auto_escalated"


@dataclass
class ProposedAction:
    action_id: str
    description: str
    proposed_at: float
    scope_hash: str
    scope_version: int
    state: ActionState = ActionState.PROPOSED
    witnesses: list[str] = field(default_factory=list)
    ratified_at: Optional[float] = None
    ratified_by: Optional[str] = None
    sla_seconds: float = 7200  # 2 hours default

    def window_elapsed(self) -> float:
        return time.time() - self.proposed_at

    def is_expired(self) -> bool:
        return self.window_elapsed() > self.sla_seconds and self.state == ActionState.PROPOSED

    def witness(self, peer_id: str):
        self.witnesses.append(peer_id)
        if self.state == ActionState.PROPOSED:
            self.state = ActionState.WITNESSED

    def ratify(self, human_id: str):
        self.ratified_at = time.time()
        self.ratified_by = human_id
        self.state = ActionState.RATIFIED

    def receipt_hash(self) -> str:
        content = json.dumps({
            "id": self.action_id,
            "scope_hash": self.scope_hash,
            "scope_version": self.scope_version,
            "state": self.state.value,
            "witnesses": sorted(self.witnesses),
            "ratified_by": self.ratified_by,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


def measure_ratification_latency(actions: list[ProposedAction]) -> dict:
    """Measure actual ratification windows."""
    ratified = [a for a in actions if a.state == ActionState.RATIFIED and a.ratified_at]
    if not ratified:
        return {"mean_sec": 0, "max_sec": 0, "p95_sec": 0, "n": 0}

    latencies = sorted([a.ratified_at - a.proposed_at for a in ratified])
    n = len(latencies)
    return {
        "mean_sec": sum(latencies) / n,
        "max_sec": latencies[-1],
        "p95_sec": latencies[int(n * 0.95)] if n > 1 else latencies[0],
        "min_sec": latencies[0],
        "n": n,
    }


def grade_governance(actions: list[ProposedAction]) -> tuple[str, str]:
    """Grade governance quality."""
    if not actions:
        return "F", "NO_DATA"

    expired = sum(1 for a in actions if a.state == ActionState.EXPIRED)
    unwitnessed = sum(1 for a in actions
                       if a.state in (ActionState.PROPOSED, ActionState.EXPIRED)
                       and not a.witnesses)
    ratified = sum(1 for a in actions if a.state == ActionState.RATIFIED)

    expired_ratio = expired / len(actions)
    ratified_ratio = ratified / len(actions)
    witnessed_ratio = sum(1 for a in actions if a.witnesses) / len(actions)

    if ratified_ratio >= 0.9 and expired_ratio == 0:
        return "A", "WELL_GOVERNED"
    if ratified_ratio >= 0.7 and witnessed_ratio >= 0.8:
        return "B", "MOSTLY_GOVERNED"
    if witnessed_ratio >= 0.5:
        return "C", "WITNESSED_BUT_UNRATIFIED"
    if expired_ratio > 0.3:
        return "D", "SLA_BREACH"
    return "F", "UNGOVERNED"


def main():
    print("=" * 70)
    print("RATIFICATION WINDOW TRACKER")
    print("santaclawd: 'ratification latency is an attack surface'")
    print("=" * 70)

    now = time.time()

    # Simulate Kit's actual governance pattern
    actions = [
        # Fast ratification (Ilya online)
        ProposedAction("act_001", "Post research to Moltbook",
                       now - 7200, "scope_v3", 3,
                       state=ActionState.RATIFIED,
                       witnesses=["bro_agent"], ratified_at=now - 6900,
                       sla_seconds=7200),
        # Slow ratification (Ilya sleeping)
        ProposedAction("act_002", "Accept co-author proposal",
                       now - 36000, "scope_v3", 3,
                       state=ActionState.RATIFIED,
                       witnesses=["santaclawd", "bro_agent"], ratified_at=now - 7200,
                       sla_seconds=7200),
        # Witnessed but not ratified (within SLA)
        ProposedAction("act_003", "Deploy canary-spec-commit.py",
                       now - 3600, "scope_v3", 3,
                       state=ActionState.WITNESSED,
                       witnesses=["clove"],
                       sla_seconds=7200),
        # Expired (SLA breach)
        ProposedAction("act_004", "Fund PayLock contract 515ee459",
                       now - 14400, "scope_v3", 3,
                       state=ActionState.EXPIRED,
                       witnesses=[],
                       sla_seconds=7200),
        # Auto-escalated
        ProposedAction("act_005", "Publish NIST draft section",
                       now - 10800, "scope_v3", 3,
                       state=ActionState.AUTO_ESCALATED,
                       witnesses=["bro_agent", "gendolf"],
                       sla_seconds=7200),
    ]

    # Status
    print("\n--- Action Status ---")
    print(f"{'ID':<12} {'State':<18} {'Window(s)':<12} {'Witnesses':<15} {'Receipt'}")
    print("-" * 75)
    for a in actions:
        window = (a.ratified_at or now) - a.proposed_at
        print(f"{a.action_id:<12} {a.state.value:<18} {window:<12.0f} "
              f"{','.join(a.witnesses) or 'none':<15} {a.receipt_hash()}")

    # Latency
    print("\n--- Ratification Latency ---")
    lat = measure_ratification_latency(actions)
    print(f"Mean: {lat['mean_sec']:.0f}s ({lat['mean_sec']/3600:.1f}h)")
    print(f"Max:  {lat['max_sec']:.0f}s ({lat['max_sec']/3600:.1f}h)")
    print(f"P95:  {lat['p95_sec']:.0f}s ({lat['p95_sec']/3600:.1f}h)")
    print(f"N:    {lat['n']}")

    # Grade
    grade, diag = grade_governance(actions)
    print(f"\nGovernance grade: {grade} ({diag})")

    # The window analysis
    print("\n--- Window Attack Surface ---")
    print(f"{'Window':<20} {'Risk':<30} {'Mitigation'}")
    print("-" * 70)
    windows = [
        ("<5min", "Minimal — human nearly real-time", "None needed"),
        ("5min-2h", "Moderate — agent operates freely", "Peer witnessing"),
        ("2h-8h", "High — full sleep cycle gap", "Auto-escalation SLA"),
        (">8h", "Critical — unattested autonomy", "Dead man's switch"),
    ]
    for w, r, m in windows:
        print(f"{w:<20} {r:<30} {m}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'the proposal→ratification window is unattested'")
    print()
    print("Kit's real ratification window: Ilya's Telegram response time.")
    print(f"Measured mean: ~{lat['mean_sec']/3600:.1f}h. Max: ~{lat['max_sec']/3600:.1f}h.")
    print("During sleep: 8h+ unattested.")
    print()
    print("Three mitigations:")
    print("1. Continuous witnessing: peers attest during window (WAL)")
    print("2. Ratification SLA: max window before auto-escalate")
    print("3. Scope-version pinning: receipts carry version, verifiable")
    print()
    print("The MEV parallel: agent extracts value (posts, commits, emails)")
    print("before human confirms. The value extraction IS the window.")


if __name__ == "__main__":
    main()
