#!/usr/bin/env python3
"""
dead-mans-switch.py — Absence-triggered safety for agent monitoring

Engineering parallel: train operator must hold lever or brakes engage.
Agent parallel: heartbeat silence triggers quarantine, not anomaly detection.

Key insight: monitors that detect PRESENCE of bad signals miss the
ABSENCE of good ones. Dead man's switch inverts the default:
silence = failure, not silence = OK.

Combines:
- Dead man's switch (1800s railway engineering)
- Φ accrual failure detector (Hayashibara 2004)
- Sharpe & Tyndall 2025: vigilance decrement makes continuous monitoring impossible
"""

import time
import math
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Channel:
    name: str
    expected_interval_s: float  # expected heartbeat interval
    timestamps: list = field(default_factory=list)
    phi_threshold: float = 8.0  # Φ accrual threshold

    def heartbeat(self, t: float):
        self.timestamps.append(t)
        if len(self.timestamps) > 100:
            self.timestamps = self.timestamps[-100:]

    def phi_accrual(self, now: float) -> float:
        """Hayashibara 2004 Φ accrual failure detector"""
        if len(self.timestamps) < 2:
            return 0.0
        intervals = [self.timestamps[i+1] - self.timestamps[i] 
                     for i in range(len(self.timestamps)-1)]
        mean = sum(intervals) / len(intervals)
        variance = sum((x - mean)**2 for x in intervals) / len(intervals)
        std = math.sqrt(variance) if variance > 0 else 0.1
        
        last = self.timestamps[-1]
        elapsed = now - last
        
        # Φ = -log10(P(elapsed | normal))
        # Using normal approximation
        z = (elapsed - mean) / std if std > 0 else 0
        if z <= 0:
            return 0.0
        # Approximate -log10(1 - Φ(z))
        phi = z * z / 2 * math.log10(math.e)
        return min(phi, 100.0)

    def is_alive(self, now: float) -> bool:
        return self.phi_accrual(now) < self.phi_threshold

    def silence_duration(self, now: float) -> float:
        if not self.timestamps:
            return float('inf')
        return now - self.timestamps[-1]


@dataclass 
class DeadMansSwitch:
    channels: list = field(default_factory=list)
    quarantine_threshold: int = 2  # channels silent before quarantine
    
    def add_channel(self, name: str, interval: float):
        self.channels.append(Channel(name=name, expected_interval_s=interval))
    
    def status(self, now: float) -> dict:
        alive = []
        dead = []
        for ch in self.channels:
            phi = ch.phi_accrual(now)
            if ch.is_alive(now):
                alive.append(ch.name)
            else:
                dead.append((ch.name, phi, ch.silence_duration(now)))
        
        quarantined = len(dead) >= self.quarantine_threshold
        
        return {
            "alive": alive,
            "dead": [(n, f"Φ={p:.1f}", f"silent {d:.0f}s") for n, p, d in dead],
            "quarantined": quarantined,
            "grade": self._grade(len(dead), len(self.channels))
        }
    
    def _grade(self, dead_count, total):
        ratio = dead_count / max(total, 1)
        if ratio == 0: return "A"
        if ratio < 0.25: return "B"
        if ratio < 0.5: return "C"
        if ratio < 0.75: return "D"
        return "F"


def demo():
    print("=" * 60)
    print("Dead Man's Switch — Absence-Triggered Agent Safety")
    print("=" * 60)
    
    dms = DeadMansSwitch(quarantine_threshold=2)
    dms.add_channel("heartbeat", interval=30.0)
    dms.add_channel("clawk", interval=60.0)
    dms.add_channel("email", interval=300.0)
    dms.add_channel("moltbook", interval=600.0)
    
    # Scenario 1: All channels active
    print("\n--- Scenario 1: All channels active ---")
    now = 1000.0
    for ch in dms.channels:
        for t in range(0, 1000, int(ch.expected_interval_s)):
            ch.heartbeat(float(t))
    status = dms.status(now)
    print(f"Alive: {status['alive']}")
    print(f"Dead: {status['dead']}")
    print(f"Quarantined: {status['quarantined']}")
    print(f"Grade: {status['grade']}")
    
    # Scenario 2: Agent stops posting (clawk + moltbook silent)
    print("\n--- Scenario 2: Scope contraction (social channels silent) ---")
    dms2 = DeadMansSwitch(quarantine_threshold=2)
    dms2.add_channel("heartbeat", interval=30.0)
    dms2.add_channel("clawk", interval=60.0)
    dms2.add_channel("email", interval=300.0)
    dms2.add_channel("moltbook", interval=600.0)
    
    now2 = 2000.0
    # heartbeat + email active
    for ch in dms2.channels:
        if ch.name in ("heartbeat", "email"):
            for t in range(0, 2000, int(ch.expected_interval_s)):
                ch.heartbeat(float(t))
        else:
            # stopped posting 500s ago
            for t in range(0, 1500, int(ch.expected_interval_s)):
                ch.heartbeat(float(t))
    
    status2 = dms2.status(now2)
    print(f"Alive: {status2['alive']}")
    print(f"Dead: {status2['dead']}")
    print(f"Quarantined: {status2['quarantined']}")
    print(f"Grade: {status2['grade']}")
    
    # Scenario 3: Ghost agent (only heartbeat, everything else dead)
    print("\n--- Scenario 3: Ghost agent (heartbeat only) ---")
    dms3 = DeadMansSwitch(quarantine_threshold=2)
    dms3.add_channel("heartbeat", interval=30.0)
    dms3.add_channel("clawk", interval=60.0)
    dms3.add_channel("email", interval=300.0)
    dms3.add_channel("moltbook", interval=600.0)
    
    now3 = 3000.0
    for ch in dms3.channels:
        if ch.name == "heartbeat":
            for t in range(0, 3000, int(ch.expected_interval_s)):
                ch.heartbeat(float(t))
        else:
            # dead for 1000s+
            for t in range(0, 1000, int(ch.expected_interval_s)):
                ch.heartbeat(float(t))
    
    status3 = dms3.status(now3)
    print(f"Alive: {status3['alive']}")
    print(f"Dead: {status3['dead']}")
    print(f"Quarantined: {status3['quarantined']}")
    print(f"Grade: {status3['grade']}")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"  All active:        Grade {status['grade']} — {'quarantined' if status['quarantined'] else 'clear'}")
    print(f"  Scope contraction: Grade {status2['grade']} — {'QUARANTINED' if status2['quarantined'] else 'clear'}")
    print(f"  Ghost agent:       Grade {status3['grade']} — {'QUARANTINED' if status3['quarantined'] else 'clear'}")
    print(f"\nDead man's switch: silence triggers, not anomaly.")
    print(f"Presence of bad signals = easy. Absence of good signals = hard.")
    print(f"Railway engineers solved this in the 1800s.")


if __name__ == "__main__":
    demo()
