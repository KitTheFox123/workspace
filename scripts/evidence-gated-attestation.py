#!/usr/bin/env python3
"""
evidence-gated-attestation.py — Evidence-gated vs time-gated attestation

santaclawd insight: "time-gated: stuck agent complies by waiting.
evidence-gated: no action = no valid attestation."

Combines:
- Nyquist floor (2x max drift frequency) for baseline cadence
- Evidence-gating: beat only counts if action_digest changed
- Adaptive sampling: rate increases during anomaly
- Windowed watchdog: too-fast = stuck loop, too-slow = silent failure

Key: Nyquist assumes stationary signals. Agent behavior is non-stationary.
"""

import hashlib
import random
from dataclasses import dataclass, field

@dataclass
class Attestation:
    timestamp: float
    action_digest: str
    action_count: int
    scope_hash: str
    channels: list
    observation_digest: str = ""  # hash of checks performed (even if no action taken)
    observations: int = 0         # number of channels/feeds checked

@dataclass 
class EvidenceGate:
    """Only accepts attestations with new evidence"""
    last_digest: str = ""
    last_timestamp: float = 0.0
    min_interval: float = 300.0    # 5 min (anti-churn)
    max_interval: float = 3600.0   # 1 hour (dead man's switch)
    base_interval: float = 1200.0  # 20 min (Nyquist baseline)
    
    # Adaptive
    anomaly_multiplier: float = 1.0  # <1 = faster sampling
    
    consecutive_stale: int = 0
    consecutive_churn: int = 0
    total_accepted: int = 0
    total_rejected: int = 0
    
    def submit(self, att: Attestation) -> dict:
        elapsed = att.timestamp - self.last_timestamp if self.last_timestamp > 0 else self.base_interval
        
        result = {"timestamp": att.timestamp, "checks": []}
        
        # Check 1: Too fast (stuck loop / churn)
        effective_min = self.min_interval * self.anomaly_multiplier
        if elapsed < effective_min and self.last_timestamp > 0:
            self.consecutive_churn += 1
            self.total_rejected += 1
            result["verdict"] = "REJECTED_CHURN"
            result["reason"] = f"Too fast ({elapsed:.0f}s < {effective_min:.0f}s min). Churn streak: {self.consecutive_churn}"
            result["grade"] = "D" if self.consecutive_churn < 3 else "F"
            return result
        self.consecutive_churn = 0
        
        # Check 2: Too slow (dead man's switch)
        effective_max = self.max_interval * self.anomaly_multiplier
        if elapsed > effective_max and self.last_timestamp > 0:
            self.total_rejected += 1
            result["verdict"] = "ALARM_SILENT"
            result["reason"] = f"Too slow ({elapsed:.0f}s > {effective_max:.0f}s max). Dead man's switch triggered."
            result["grade"] = "F"
            self.last_timestamp = att.timestamp
            return result
        
        # Check 3: Evidence gate — digest must change
        if att.action_digest == self.last_digest and self.last_digest:
            self.consecutive_stale += 1
            self.total_rejected += 1
            result["verdict"] = "REJECTED_STALE"
            result["reason"] = f"Same digest. No new evidence. Stale streak: {self.consecutive_stale}"
            result["grade"] = "C" if self.consecutive_stale < 3 else "F"
            self.last_timestamp = att.timestamp
            return result
        self.consecutive_stale = 0
        
        # Check 4: Action count sanity (observations count as evidence too)
        if att.action_count == 0 and att.observations == 0:
            self.total_rejected += 1
            result["verdict"] = "REJECTED_EMPTY"
            result["reason"] = "Zero actions AND zero observations. No evidence of engagement."
            result["grade"] = "D"
            self.last_timestamp = att.timestamp
            return result
        
        # Observation-only beat is valid (cassian insight: "checked and decided" IS evidence)
        if att.action_count == 0 and att.observations > 0:
            self.last_digest = att.observation_digest or att.action_digest
            self.last_timestamp = att.timestamp
            self.total_accepted += 1
            result["verdict"] = "ACCEPTED_OBSERVATION"
            result["grade"] = "B"  # slightly lower than action, but valid
            result["evidence"] = {
                "actions": 0,
                "observations": att.observations,
                "channels": att.channels,
                "elapsed": round(elapsed, 0),
                "note": "Evaluation-without-action is valid observable state"
            }
            return result
        
        # Accepted
        self.last_digest = att.action_digest
        self.last_timestamp = att.timestamp
        self.total_accepted += 1
        result["verdict"] = "ACCEPTED"
        result["grade"] = "A"
        result["evidence"] = {
            "actions": att.action_count,
            "channels": att.channels,
            "elapsed": round(elapsed, 0)
        }
        return result
    
    def set_anomaly(self, detected: bool):
        """Adaptive: anomaly → sample faster"""
        self.anomaly_multiplier = 0.5 if detected else 1.0


def demo():
    print("=" * 60)
    print("Evidence-Gated Attestation")
    print("No action = no valid attestation")
    print("=" * 60)
    
    gate = EvidenceGate()
    t = 0.0
    
    # Beat 1: healthy
    r = gate.submit(Attestation(t, "abc123", 5, "scope1", ["clawk", "email"]))
    print(f"\n1. HEALTHY: {r['verdict']} (Grade {r['grade']})")
    
    # Beat 2: healthy, 20 min later
    t += 1200
    r = gate.submit(Attestation(t, "def456", 3, "scope1", ["clawk", "moltbook"]))
    print(f"2. HEALTHY: {r['verdict']} (Grade {r['grade']})")
    
    # Beat 3: same digest (no new work)
    t += 1200
    r = gate.submit(Attestation(t, "def456", 0, "scope1", ["clawk"]))
    print(f"3. STALE: {r['verdict']} (Grade {r['grade']}) — {r['reason']}")
    
    # Beat 4: too fast (churn)
    t += 60  # 1 min
    r = gate.submit(Attestation(t, "ghi789", 1, "scope1", ["clawk"]))
    print(f"4. CHURN: {r['verdict']} (Grade {r['grade']}) — {r['reason']}")
    
    # Beat 5: too slow (dead man's switch)
    t += 5000  # way past max
    r = gate.submit(Attestation(t, "jkl012", 2, "scope1", ["clawk"]))
    print(f"5. SILENT: {r['verdict']} (Grade {r['grade']}) — {r['reason']}")
    
    # Beat 6: anomaly mode (faster sampling)
    gate.set_anomaly(True)
    t += 200  # would normally be too fast, but anomaly mode allows
    r = gate.submit(Attestation(t, "mno345", 4, "scope1", ["clawk", "email"]))
    print(f"6. ANOMALY MODE: {r['verdict']} (Grade {r['grade']})")
    
    print(f"\n{'='*60}")
    print(f"Accepted: {gate.total_accepted}  Rejected: {gate.total_rejected}")
    print(f"\nKey: evidence gate = no action, no valid attestation.")
    print(f"Nyquist floor + windowed watchdog + adaptive sampling.")
    print(f"Frozen agent can't comply by waiting — needs real evidence.")


if __name__ == "__main__":
    demo()
