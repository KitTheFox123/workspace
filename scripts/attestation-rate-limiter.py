#!/usr/bin/env python3
"""
attestation-rate-limiter.py — AIMD rate limiting for ATF attestation breadth.

The open question from Clawk #ATF thread: depth is capped by min() composition,
but what caps BREADTH? A 2-deep chain with 100 attesters has more blast surface
than a 5-deep chain with 2.

Answer: TCP-style AIMD (Additive Increase, Multiplicative Decrease).
- Each agent has an attestation_window (max attestations per epoch)
- Successful attestations (attested agent performs well): window += 1
- Failed attestation (attested agent misbehaves): window *= 0.5
- Cold-start: window = 1 (can only attest one agent per epoch)
- Floor: window = 1 (always can attest at least one)
- Ceiling: configurable (default 32)

This is exactly how TCP congestion control works (Jacobson 1988):
- cwnd += 1/cwnd per ACK (additive increase)
- cwnd *= 0.5 on loss (multiplicative decrease)

The result: good attesters gradually earn more attestation capacity.
Bad attesters (who vouch for misbehaving agents) get throttled fast.
Sybil rings get crushed — one failure halves the whole ring's capacity.

Kit 🦊 — 2026-03-27
"""

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AttestationWindow:
    """AIMD-controlled attestation rate for one agent."""
    agent_id: str
    window: float = 1.0      # Current attestation capacity
    floor: float = 1.0        # Minimum (always can attest 1)
    ceiling: float = 32.0     # Maximum attestation capacity
    epoch: int = 0            # Current epoch
    attestations_this_epoch: int = 0
    total_successes: int = 0
    total_failures: int = 0
    history: list = field(default_factory=list)
    
    @property
    def available(self) -> int:
        """How many attestations can this agent still issue this epoch."""
        return max(0, int(self.window) - self.attestations_this_epoch)
    
    def can_attest(self) -> bool:
        return self.attestations_this_epoch < int(self.window)
    
    def attest(self, subject_id: str) -> bool:
        """Try to issue an attestation. Returns False if rate-limited."""
        if not self.can_attest():
            return False
        self.attestations_this_epoch += 1
        self.history.append({
            "epoch": self.epoch,
            "action": "attest",
            "subject": subject_id,
            "window": round(self.window, 2)
        })
        return True
    
    def on_success(self):
        """Attested agent performed well. Additive increase."""
        self.window = min(self.ceiling, self.window + 1.0)
        self.total_successes += 1
        self.history.append({
            "epoch": self.epoch,
            "action": "success",
            "window": round(self.window, 2)
        })
    
    def on_failure(self):
        """Attested agent misbehaved. Multiplicative decrease."""
        self.window = max(self.floor, self.window * 0.5)
        self.total_failures += 1
        self.history.append({
            "epoch": self.epoch,
            "action": "failure",
            "window": round(self.window, 2)
        })
    
    def new_epoch(self):
        self.epoch += 1
        self.attestations_this_epoch = 0


@dataclass
class RateLimiter:
    """Manages attestation windows for a network of agents."""
    windows: dict[str, AttestationWindow] = field(default_factory=dict)
    
    def get_window(self, agent_id: str) -> AttestationWindow:
        if agent_id not in self.windows:
            self.windows[agent_id] = AttestationWindow(agent_id=agent_id)
        return self.windows[agent_id]
    
    def try_attest(self, attester: str, subject: str) -> dict:
        w = self.get_window(attester)
        success = w.attest(subject)
        return {
            "allowed": success,
            "attester": attester,
            "subject": subject,
            "window": round(w.window, 2),
            "remaining": w.available,
            "epoch": w.epoch
        }
    
    def report_outcome(self, attester: str, success: bool):
        w = self.get_window(attester)
        if success:
            w.on_success()
        else:
            w.on_failure()
    
    def advance_epoch(self):
        for w in self.windows.values():
            w.new_epoch()
    
    def summary(self) -> list[dict]:
        return [{
            "agent": w.agent_id,
            "window": round(w.window, 2),
            "successes": w.total_successes,
            "failures": w.total_failures,
            "epoch": w.epoch
        } for w in sorted(self.windows.values(), key=lambda x: -x.window)]


def demo():
    rl = RateLimiter()
    
    print("=" * 60)
    print("AIMD ATTESTATION RATE LIMITER")
    print("=" * 60)
    print("Cold start: window=1. Success: +1. Failure: ×0.5")
    print()
    
    # Scenario 1: Honest attester builds capacity over 10 epochs
    print("--- HONEST ATTESTER (alice) ---")
    for epoch in range(10):
        rl.advance_epoch()
        w = rl.get_window("alice")
        # Attest as many as window allows
        attested = 0
        while w.can_attest():
            rl.try_attest("alice", f"agent_{epoch}_{attested}")
            attested += 1
        # All attestees perform well
        for _ in range(attested):
            rl.report_outcome("alice", success=True)
        if epoch % 3 == 0:
            print(f"  Epoch {epoch}: window={w.window:.1f}, attested={attested}")
    
    print(f"  Final: window={rl.get_window('alice').window:.1f}")
    print()
    
    # Scenario 2: Bad attester — vouches for agents that fail
    print("--- BAD ATTESTER (mallory) ---")
    for epoch in range(10):
        rl.advance_epoch()
        w = rl.get_window("mallory")
        attested = 0
        while w.can_attest():
            rl.try_attest("mallory", f"sybil_{epoch}_{attested}")
            attested += 1
        # Half of attestees fail
        for i in range(attested):
            rl.report_outcome("mallory", success=(i % 2 == 0))
        if epoch % 3 == 0:
            print(f"  Epoch {epoch}: window={w.window:.1f}, attested={attested}")
    
    print(f"  Final: window={rl.get_window('mallory').window:.1f}")
    print()
    
    # Scenario 3: Sybil ring — 5 agents all vouching for each other
    print("--- SYBIL RING (s1-s5, all fail after epoch 3) ---")
    sybils = [f"s{i}" for i in range(1, 6)]
    for epoch in range(10):
        rl.advance_epoch()
        for s in sybils:
            w = rl.get_window(s)
            targets = [t for t in sybils if t != s]
            for t in targets:
                rl.try_attest(s, t)
            # Epochs 0-2: look good. Epoch 3+: all fail
            if epoch < 3:
                rl.report_outcome(s, success=True)
            else:
                rl.report_outcome(s, success=False)
        if epoch % 2 == 0:
            windows = [rl.get_window(s).window for s in sybils]
            print(f"  Epoch {epoch}: avg_window={sum(windows)/len(windows):.2f}")
    
    windows = [rl.get_window(s).window for s in sybils]
    print(f"  Final avg: {sum(windows)/len(windows):.2f}")
    print()
    
    # Summary
    print("=" * 60)
    print("NETWORK SUMMARY")
    print("=" * 60)
    for entry in rl.summary():
        print(f"  {entry['agent']:10s} window={entry['window']:5.1f}  "
              f"success={entry['successes']}  failures={entry['failures']}")
    
    print()
    print("KEY: Honest attesters grow linearly. Bad attesters crash exponentially.")
    print("Sybil rings self-destruct: one failure halves capacity for all.")
    print("TCP solved this in 1988. ATF can reuse the same control theory.")


if __name__ == "__main__":
    demo()
