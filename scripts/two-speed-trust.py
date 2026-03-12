#!/usr/bin/env python3
"""
two-speed-trust.py — Two-speed trust architecture: fast path + slow path.

santaclawd's insight: "Is trust infrastructure just payment infrastructure
without the money?"

Yes. Lightning Network = probabilistic fast path + on-chain settlement.
Replace BTC with trust scores, channels with attestation streams,
settlement with VDF/hash anchors.

Fast path: immediate, probabilistic, low-confidence (heartbeat receipts)
Slow path: VDF-anchored, high-confidence, latency ok (cross-agent attestation)
Merge on confirmation: fast estimate converges to slow ground truth.

Also implements Goeschl & Jarke (JEBO 2017) insight: trust persists
under zero observability. "Blind trust" = fast path without slow confirmation.

Usage:
    python3 two-speed-trust.py
"""

import time
import hashlib
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Receipt:
    agent_id: str
    action: str
    timestamp: float
    confidence: float  # 0-1
    path: str  # "fast" or "slow"
    anchor_hash: Optional[str] = None  # VDF/hash anchor for slow path

    def __post_init__(self):
        if self.path == "slow" and not self.anchor_hash:
            payload = f"{self.agent_id}:{self.action}:{self.timestamp}"
            self.anchor_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class TrustChannel:
    """Like a Lightning channel but for trust."""
    agent_id: str
    fast_score: float = 0.5  # probabilistic, updated on every receipt
    slow_score: float = 0.5  # anchored, updated on settlement
    fast_receipts: List[Receipt] = field(default_factory=list)
    slow_receipts: List[Receipt] = field(default_factory=list)
    pending_settlement: List[Receipt] = field(default_factory=list)
    last_settlement: float = 0.0

    def fast_update(self, action_success: bool, confidence: float = 0.6):
        """Heartbeat-speed update. Probabilistic. Immediate."""
        r = Receipt(
            self.agent_id,
            "success" if action_success else "failure",
            time.time(), confidence, "fast"
        )
        self.fast_receipts.append(r)
        self.pending_settlement.append(r)

        # EMA update
        alpha = 0.15
        observation = 1.0 if action_success else 0.0
        self.fast_score = alpha * observation + (1 - alpha) * self.fast_score

    def slow_update(self, cross_agent_score: float, confidence: float = 0.9):
        """Cross-agent attestation. High confidence. Latency ok."""
        r = Receipt(
            self.agent_id,
            f"attested:{cross_agent_score:.2f}",
            time.time(), confidence, "slow"
        )
        self.slow_receipts.append(r)

        # Weighted update toward attested score
        weight = confidence * 0.3
        self.slow_score = weight * cross_agent_score + (1 - weight) * self.slow_score

    def settle(self) -> dict:
        """Merge fast and slow paths. Like closing a Lightning channel."""
        n_pending = len(self.pending_settlement)
        if n_pending == 0:
            return {"status": "NO_PENDING"}

        # Merge: slow path is ground truth, fast path is estimate
        # Divergence = the interesting signal
        divergence = abs(self.fast_score - self.slow_score)

        # Merged score: weighted by confidence
        fast_weight = 0.3
        slow_weight = 0.7
        merged = fast_weight * self.fast_score + slow_weight * self.slow_score

        result = {
            "agent": self.agent_id,
            "fast_score": round(self.fast_score, 3),
            "slow_score": round(self.slow_score, 3),
            "merged_score": round(merged, 3),
            "divergence": round(divergence, 3),
            "pending_settled": n_pending,
        }

        # Divergence diagnosis
        if divergence > 0.3:
            result["alert"] = "HIGH_DIVERGENCE"
            result["note"] = "fast path disagrees with slow attestation — investigate"
        elif divergence > 0.15:
            result["alert"] = "MODERATE_DIVERGENCE"
        else:
            result["alert"] = "CONVERGED"

        self.pending_settlement = []
        self.last_settlement = time.time()
        return result


@dataclass
class TwoSpeedTrustSystem:
    channels: dict = field(default_factory=dict)

    def get_channel(self, agent_id: str) -> TrustChannel:
        if agent_id not in self.channels:
            self.channels[agent_id] = TrustChannel(agent_id)
        return self.channels[agent_id]

    def heartbeat(self, agent_id: str, success: bool):
        """Fast path: every heartbeat."""
        ch = self.get_channel(agent_id)
        ch.fast_update(success)

    def attest(self, agent_id: str, score: float):
        """Slow path: cross-agent attestation."""
        ch = self.get_channel(agent_id)
        ch.slow_update(score)

    def settle_all(self) -> List[dict]:
        return [ch.settle() for ch in self.channels.values()]


def demo():
    print("=" * 60)
    print("TWO-SPEED TRUST ARCHITECTURE")
    print("Fast path (heartbeats) + Slow path (attestation)")
    print("santaclawd: 'trust infra = payment infra - money'")
    print("=" * 60)

    sys = TwoSpeedTrustSystem()
    random.seed(42)

    # Scenario 1: Honest agent — fast and slow converge
    print("\n--- Scenario 1: Honest Agent (converges) ---")
    for _ in range(20):
        sys.heartbeat("honest", random.random() < 0.9)
    sys.attest("honest", 0.85)  # Cross-agent agrees
    r1 = sys.get_channel("honest").settle()
    print(f"  Fast: {r1['fast_score']}, Slow: {r1['slow_score']}, "
          f"Merged: {r1['merged_score']}, Divergence: {r1['divergence']}")
    print(f"  Alert: {r1['alert']}")

    # Scenario 2: Gaming agent — fast looks good, slow disagrees
    print("\n--- Scenario 2: Gaming Agent (diverges) ---")
    for _ in range(20):
        sys.heartbeat("gaming", True)  # Always succeeds on fast path
    sys.attest("gaming", 0.3)  # But cross-agent attestation says sketchy
    r2 = sys.get_channel("gaming").settle()
    print(f"  Fast: {r2['fast_score']}, Slow: {r2['slow_score']}, "
          f"Merged: {r2['merged_score']}, Divergence: {r2['divergence']}")
    print(f"  Alert: {r2['alert']}")
    if "note" in r2:
        print(f"  Note: {r2['note']}")

    # Scenario 3: Declining agent — fast catches before slow
    print("\n--- Scenario 3: Declining Agent (fast leads) ---")
    for i in range(20):
        success = random.random() < (0.9 - i * 0.04)
        sys.heartbeat("declining", success)
    sys.attest("declining", 0.7)  # Slow path hasn't caught up yet
    r3 = sys.get_channel("declining").settle()
    print(f"  Fast: {r3['fast_score']}, Slow: {r3['slow_score']}, "
          f"Merged: {r3['merged_score']}, Divergence: {r3['divergence']}")
    print(f"  Alert: {r3['alert']}")

    # Scenario 4: Blind trust — fast path only, no attestation
    print("\n--- Scenario 4: Blind Trust (Goeschl & Jarke 2017) ---")
    for _ in range(20):
        sys.heartbeat("blind", random.random() < 0.8)
    # No slow path attestation — this is "blind trust"
    r4 = sys.get_channel("blind").settle()
    print(f"  Fast: {r4['fast_score']}, Slow: {r4['slow_score']} (default), "
          f"Merged: {r4['merged_score']}, Divergence: {r4['divergence']}")
    print(f"  Note: No attestation = blind trust. Goeschl found ~50% surplus still realized.")

    print("\n--- SUMMARY ---")
    for r in [r1, r2, r3, r4]:
        label = r['agent']
        print(f"  {label:12s}: fast={r['fast_score']:.3f} slow={r['slow_score']:.3f} "
              f"merged={r['merged_score']:.3f} Δ={r['divergence']:.3f} [{r['alert']}]")

    print("\n--- ARCHITECTURE ---")
    print("Fast path: EMA on heartbeat receipts. Immediate. Low confidence.")
    print("Slow path: Cross-agent attestation. Latency ok. High confidence.")
    print("Settlement: Merge paths. Divergence = the signal worth monitoring.")
    print("Same as Lightning: probabilistic channel + on-chain settlement.")
    print("The money was never the point — the consensus was.")


if __name__ == "__main__":
    demo()
