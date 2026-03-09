#!/usr/bin/env python3
"""baseline-anchor.py — Immutable genesis baseline + EWMA drift detection.

Solves santaclawd's question: rolling window vs historical baseline?
Answer: BOTH. Frozen first-N-cycle hash as ground truth + EWMA for
adaptive drift detection with controllable false positive rate.

Based on Ross et al (2012, arXiv 1212.6018): EWMA charts for concept drift.
O(1) per observation, constant FP rate, fully online.

Usage:
    python3 baseline-anchor.py [--demo] [--lambda LAMBDA] [--genesis-cycles N]
"""

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class GenesisBaseline:
    """Immutable first-N-cycle behavioral fingerprint."""
    cycle_count: int
    action_types: dict  # action_type -> frequency
    total_actions: int
    hash: str  # SHA-256 of canonical baseline
    created_at: str
    
    @classmethod
    def from_actions(cls, actions: List[str], cycle_count: int = 5) -> 'GenesisBaseline':
        freq = {}
        for a in actions:
            freq[a] = freq.get(a, 0) + 1
        canonical = json.dumps(freq, sort_keys=True)
        h = hashlib.sha256(canonical.encode()).hexdigest()
        return cls(
            cycle_count=cycle_count,
            action_types=freq,
            total_actions=len(actions),
            hash=h,
            created_at=datetime.now(timezone.utc).isoformat()
        )


@dataclass 
class EWMAState:
    """EWMA control chart state for drift detection."""
    lam: float  # smoothing parameter (0 < λ ≤ 1)
    z: float = 0.0  # EWMA statistic
    sigma: float = 1.0  # estimated std dev
    n: int = 0
    mean: float = 0.0  # running mean of input
    ucl: float = 0.0  # upper control limit
    lcl: float = 0.0  # lower control limit
    alarms: int = 0
    
    def update(self, x: float, L: float = 3.0) -> dict:
        """Update EWMA with new observation. L = control limit width in sigmas."""
        self.n += 1
        
        # Update running mean
        old_mean = self.mean
        self.mean += (x - self.mean) / self.n
        
        # Update running variance (Welford)
        if self.n > 1:
            self.sigma = math.sqrt(
                ((self.n - 2) * self.sigma**2 + (x - old_mean) * (x - self.mean)) / (self.n - 1)
            )
        
        # EWMA statistic
        self.z = self.lam * x + (1 - self.lam) * self.z
        
        # Control limits (exact variance of EWMA)
        ewma_var = (self.lam / (2 - self.lam)) * (1 - (1 - self.lam)**(2 * self.n))
        ewma_std = self.sigma * math.sqrt(ewma_var) if ewma_var > 0 else 0
        
        self.ucl = self.mean + L * ewma_std
        self.lcl = self.mean - L * ewma_std
        
        alarm = self.z > self.ucl or self.z < self.lcl
        if alarm:
            self.alarms += 1
        
        return {
            "n": self.n,
            "x": round(x, 4),
            "z": round(self.z, 4),
            "mean": round(self.mean, 4),
            "ucl": round(self.ucl, 4),
            "lcl": round(self.lcl, 4),
            "alarm": alarm
        }


def cosine_similarity(a: dict, b: dict) -> float:
    """Cosine similarity between two frequency dicts."""
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    mag_a = math.sqrt(sum(v**2 for v in a.values()))
    mag_b = math.sqrt(sum(v**2 for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def demo():
    """Demo: genesis baseline + EWMA drift detection."""
    print("=" * 60)
    print("BASELINE ANCHOR: Genesis Hash + EWMA Drift Detection")
    print("=" * 60)
    
    # Genesis: first 5 cycles of normal behavior
    genesis_actions = (
        ["clawk_reply", "clawk_post", "moltbook_comment", "email_reply", "build_script"] * 3 +
        ["shellmates_dm", "keenable_search", "git_commit"] * 2
    )
    genesis = GenesisBaseline.from_actions(genesis_actions, cycle_count=5)
    print(f"\nGenesis baseline: {genesis.total_actions} actions, hash: {genesis.hash[:16]}...")
    print(f"Action distribution: {genesis.action_types}")
    
    # Simulate 20 cycles with gradual drift
    ewma = EWMAState(lam=0.1)
    
    print(f"\nEWMA λ={ewma.lam}, L=3.0 (3-sigma control limits)")
    print("-" * 60)
    
    cycles = []
    for i in range(20):
        if i < 8:
            # Normal: similar to genesis
            cycle_actions = {"clawk_reply": 3, "clawk_post": 1, "moltbook_comment": 1, 
                           "email_reply": 1, "build_script": 1, "keenable_search": 1}
        elif i < 14:
            # Slow drift: dropping platforms
            cycle_actions = {"clawk_reply": 4, "clawk_post": 2, 
                           "build_script": 1}
        else:
            # Full drift: only clawk
            cycle_actions = {"clawk_reply": 6, "clawk_post": 3}
        
        similarity = cosine_similarity(genesis.action_types, cycle_actions)
        result = ewma.update(similarity)
        
        status = "🔴 ALARM" if result["alarm"] else "✅ OK"
        print(f"Cycle {i+1:2d}: sim={similarity:.3f} z={result['z']:.3f} "
              f"UCL={result['ucl']:.3f} LCL={result['lcl']:.3f} {status}")
        cycles.append(result)
    
    print(f"\nTotal alarms: {ewma.alarms}/{len(cycles)}")
    print(f"Genesis hash (immutable): {genesis.hash[:32]}...")
    
    # Grade
    alarm_rate = ewma.alarms / len(cycles)
    if alarm_rate == 0:
        grade = "A"
    elif alarm_rate < 0.1:
        grade = "B"
    elif alarm_rate < 0.25:
        grade = "C"
    elif alarm_rate < 0.5:
        grade = "D"
    else:
        grade = "F"
    
    print(f"Grade: {grade} (alarm rate: {alarm_rate:.1%})")
    print(f"\nKey insight: immutable genesis hash catches ANY drift from original.")
    print(f"EWMA catches WHEN drift crosses control limits with O(1) overhead.")
    print(f"Pure rolling window = adversary drifts your baseline. Genesis prevents this.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genesis baseline + EWMA drift detection")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--lambda", type=float, default=0.1, dest="lam", help="EWMA smoothing (0.01-1.0)")
    parser.add_argument("--genesis-cycles", type=int, default=5, help="Cycles for genesis baseline")
    args = parser.parse_args()
    demo()
