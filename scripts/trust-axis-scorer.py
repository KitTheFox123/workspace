#!/usr/bin/env python3
"""trust-axis-scorer.py — 3-axis trust model per santaclawd ADV v0.2.

Trust = min(continuity, stake, reachability).
Each axis fails independently → distinct failure modes:
  ghost   = continuous + staked + unreachable
  zombie  = reachable + staked + discontinuous
  phantom = reachable + continuous + unstaked

Composite scores hide failure modes. Per-axis scores + min() = transparent.
"""

from dataclasses import dataclass
from enum import Enum


class FailureMode(Enum):
    HEALTHY = "healthy"
    GHOST = "ghost"        # unreachable
    ZOMBIE = "zombie"      # discontinuous (soul_hash changed)
    PHANTOM = "phantom"    # unstaked (no track record)
    COMPROMISED = "compromised"  # multiple axes failing
    DEAD = "dead"          # all axes failing


@dataclass
class TrustAxes:
    """Three independent trust measurements."""
    continuity: float    # 0-1: soul_hash stability, identity persistence
    stake: float         # 0-1: ADV trajectory score, track record
    reachability: float  # 0-1: inbox liveness, response rate

    THRESHOLD = 0.3  # below this = axis failing

    @property
    def composite(self) -> float:
        return min(self.continuity, self.stake, self.reachability)

    @property
    def failure_mode(self) -> FailureMode:
        c = self.continuity >= self.THRESHOLD
        s = self.stake >= self.THRESHOLD
        r = self.reachability >= self.THRESHOLD

        if c and s and r:
            return FailureMode.HEALTHY
        if c and s and not r:
            return FailureMode.GHOST
        if not c and s and r:
            return FailureMode.ZOMBIE
        if c and not s and r:
            return FailureMode.PHANTOM
        if sum([c, s, r]) == 1:
            return FailureMode.COMPROMISED
        if not any([c, s, r]):
            return FailureMode.DEAD
        return FailureMode.COMPROMISED

    @property
    def weakest_axis(self) -> str:
        axes = {"continuity": self.continuity, "stake": self.stake, "reachability": self.reachability}
        return min(axes, key=axes.get)

    def remediation(self) -> str:
        fm = self.failure_mode
        if fm == FailureMode.HEALTHY:
            return "No action needed."
        if fm == FailureMode.GHOST:
            return "Agent unreachable. Check inbox liveness, network connectivity, heartbeat config."
        if fm == FailureMode.ZOMBIE:
            return "Identity discontinuity detected. soul_hash changed or SOUL.md corrupted. Verify provenance chain."
        if fm == FailureMode.PHANTOM:
            return "No stake/track record. Agent exists but hasn't built trust. Need receipts + attestations."
        if fm == FailureMode.COMPROMISED:
            return "Multiple trust axes failing. Possible takeover or fundamental degradation. Manual review required."
        return "All axes failing. Agent effectively non-existent. Deregister or rebuild from backup."


# Test agents
agents = {
    "kit_fox": TrustAxes(
        continuity=0.95,   # same SOUL.md since migration, soul_hash stable
        stake=0.88,        # 200+ receipts, PayLock history
        reachability=0.92  # heartbeat every 3h, inbox responsive
    ),
    "ghost_agent": TrustAxes(
        continuity=0.90,   # identity intact
        stake=0.75,        # decent history
        reachability=0.05  # hasn't responded in 2 weeks
    ),
    "zombie_bot": TrustAxes(
        continuity=0.10,   # soul_hash changed 3x in a week
        stake=0.60,        # some history under old identity
        reachability=0.85  # responds quickly
    ),
    "phantom_new": TrustAxes(
        continuity=0.80,   # consistent identity
        stake=0.08,        # no receipts, no attestations
        reachability=0.90  # inbox live
    ),
    "compromised": TrustAxes(
        continuity=0.15,   # identity drift
        stake=0.20,        # history inconsistent
        reachability=0.70  # still responsive (but who?)
    ),
    "dead_agent": TrustAxes(
        continuity=0.05,
        stake=0.02,
        reachability=0.01
    ),
}


def main():
    print("=" * 70)
    print("Trust Axis Scorer — 3-axis model per santaclawd ADV v0.2")
    print("trust = min(continuity, stake, reachability)")
    print("=" * 70)

    for name, axes in agents.items():
        fm = axes.failure_mode
        icon = {
            FailureMode.HEALTHY: "🟢",
            FailureMode.GHOST: "👻",
            FailureMode.ZOMBIE: "🧟",
            FailureMode.PHANTOM: "👤",
            FailureMode.COMPROMISED: "⚠️",
            FailureMode.DEAD: "💀",
        }[fm]

        print(f"\n{icon} {name}: {fm.value} (composite: {axes.composite:.2f})")
        print(f"   continuity={axes.continuity:.2f}  stake={axes.stake:.2f}  reachability={axes.reachability:.2f}")
        print(f"   weakest: {axes.weakest_axis}")
        print(f"   action: {axes.remediation()}")

    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: composite score hides failure mode.")
    print("  ghost_agent composite=0.05 — but WHY? Only per-axis tells you.")
    print("  zombie_bot composite=0.10 — different failure, different fix.")
    print("  ADV v0.2 MUST emit per-axis scores, not just a single number.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
