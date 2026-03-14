#!/usr/bin/env python3
"""
commitment-decay-monitor.py — Post-lock alignment drift detector.

Skinner's insight: C(on-chain) is a step function, but C(psychological)
has a half-life. This monitors the gap between economic state (locked/unlocked)
and behavioral signals (attestation frequency, gossip activity).

Based on:
- Fudenberg & Levine 2006: dual-self model (present vs future self)
- Schelling 1960: commitment devices (restricting future choices)
- Kahneman & Tversky 1979: loss aversion (endowment effect post-lock)
- Skinner (Clawk, 2026-03-14): "Structural Isolation" post-lock

The key insight: SOL lock = Odysseus tied to the mast.
When the ropes come off, does he still resist the sirens?
"""

import math
from dataclasses import dataclass


@dataclass
class AgentCommitment:
    agent_id: str
    lock_amount_sol: float
    lock_start_hours_ago: float
    lock_duration_hours: float
    attestation_rate_per_day: float  # How often they attest (behavioral signal)
    gossip_response_rate: float  # 0-1, how often they respond to gossip pings

    @property
    def locked(self) -> bool:
        return self.lock_start_hours_ago < self.lock_duration_hours

    @property
    def hours_since_unlock(self) -> float:
        if self.locked:
            return 0.0
        return self.lock_start_hours_ago - self.lock_duration_hours

    @property
    def c_onchain(self) -> float:
        """Step function: 1.0 if locked, 0.0 if not."""
        return 1.0 if self.locked else 0.0

    @property
    def c_behavioral(self) -> float:
        """Psychological commitment decay post-unlock.
        Endowment effect: people overvalue while they have it,
        then rapidly recalibrate after loss.
        Half-life ~72h post-unlock (empirical estimate).
        """
        if self.locked:
            return 1.0
        # Exponential decay with 72h half-life
        half_life = 72.0
        return math.exp(-0.693 * self.hours_since_unlock / half_life)

    @property
    def alignment_gap(self) -> float:
        """Gap between behavioral signals and commitment state.
        High gap while locked = bad (commitment without engagement).
        High gap post-unlock = expected (transitioning out).
        """
        # Behavioral score: normalize attestation rate (assume 4/day = healthy)
        attest_score = min(self.attestation_rate_per_day / 4.0, 1.0)
        behavioral = (attest_score + self.gossip_response_rate) / 2.0

        if self.locked:
            # During lock: behavioral should match commitment
            return abs(1.0 - behavioral)
        else:
            # Post-lock: behavioral decay is expected
            expected = self.c_behavioral
            return abs(expected - behavioral)

    @property
    def risk_level(self) -> str:
        gap = self.alignment_gap
        if gap < 0.15: return "LOW"
        if gap < 0.30: return "MODERATE"
        if gap < 0.50: return "HIGH"
        return "CRITICAL"

    @property
    def diagnosis(self) -> str:
        if self.locked and self.alignment_gap > 0.3:
            return "COMMITMENT_WITHOUT_ENGAGEMENT — locked but inactive. Odysseus tied to mast but sleeping."
        if not self.locked and self.c_behavioral > 0.5 and self.alignment_gap < 0.15:
            return "GRACEFUL_TRANSITION — behavioral decay matches expected post-lock trajectory."
        if not self.locked and self.hours_since_unlock > 120 and self.gossip_response_rate > 0.6:
            return "INTRINSIC_ALIGNMENT — commitment expired but behavior persists. Genuine, not forced."
        if not self.locked and self.hours_since_unlock < 24 and self.alignment_gap > 0.4:
            return "RAPID_DISENGAGEMENT — unlocked and immediately inactive. The ropes were the whole story."
        return "MONITORING"


def demo():
    print("=== Commitment Decay Monitor (Fudenberg & Levine 2006) ===\n")

    scenarios = [
        AgentCommitment("locked_active", 1.0, 48, 720, 4.0, 0.9),
        AgentCommitment("locked_passive", 1.0, 48, 720, 0.5, 0.2),
        AgentCommitment("just_unlocked_active", 1.0, 730, 720, 3.5, 0.85),
        AgentCommitment("unlocked_24h_gone", 1.0, 744, 720, 0.1, 0.05),
        AgentCommitment("unlocked_7d_still_here", 1.0, 888, 720, 3.0, 0.8),
        AgentCommitment("never_locked", 0.0, 0, 0, 2.0, 0.6),
    ]

    for s in scenarios:
        print(f"Agent: {s.agent_id}")
        print(f"  Lock:          {'LOCKED' if s.locked else f'UNLOCKED ({s.hours_since_unlock:.0f}h ago)'}")
        print(f"  C(on-chain):   {s.c_onchain:.1f}")
        print(f"  C(behavioral): {s.c_behavioral:.3f}")
        print(f"  Alignment gap: {s.alignment_gap:.3f}")
        print(f"  Risk:          {s.risk_level}")
        print(f"  Diagnosis:     {s.diagnosis}")
        print()


if __name__ == "__main__":
    demo()
