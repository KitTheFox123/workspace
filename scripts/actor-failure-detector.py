#!/usr/bin/env python3
"""actor-failure-detector.py — Actor model failure detection for agent runtimes.

Maps Agha 1986 actor model primitives to Chandra-Toueg failure detector classes.
Every message-passing agent runtime is implicitly a failure detector.
Email/heartbeat = Φ accrual on message gaps.

Usage:
    python3 actor-failure-detector.py [--demo]
"""

import json
import math
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class ActorChannel:
    """A communication channel between agents."""
    name: str
    protocol: str  # email, heartbeat, clawk, webhook
    expected_interval_sec: float
    last_message_ts: Optional[float] = None
    message_count: int = 0
    
    
@dataclass 
class PhiAccrual:
    """Hayashibara 2004 Φ accrual failure detector."""
    window: List[float]  # inter-arrival times
    max_window: int = 100
    
    def add_heartbeat(self, interval: float):
        self.window.append(interval)
        if len(self.window) > self.max_window:
            self.window.pop(0)
    
    def phi(self, time_since_last: float) -> float:
        """Compute Φ suspicion level."""
        if not self.window:
            return 0.0
        mean = sum(self.window) / len(self.window)
        if mean == 0:
            return 0.0
        variance = sum((x - mean) ** 2 for x in self.window) / len(self.window)
        std = max(math.sqrt(variance), 0.001)
        # Normal distribution CDF approximation
        y = (time_since_last - mean) / std
        # Φ = -log10(1 - CDF(y))
        cdf = 0.5 * (1 + math.erf(y / math.sqrt(2)))
        if cdf >= 1.0:
            return 16.0  # cap
        if cdf <= 0.0:
            return 0.0
        return max(0, -math.log10(1 - cdf))


@dataclass
class AgentRuntime:
    """Agent runtime modeled as actor system with failure detection."""
    agent_id: str
    channels: List[ActorChannel]
    phi_detectors: dict  # channel_name -> PhiAccrual
    
    def suspicion_level(self, now: float) -> dict:
        """Compute per-channel and aggregate suspicion."""
        results = {}
        for ch in self.channels:
            if ch.last_message_ts is None:
                results[ch.name] = {"phi": 16.0, "status": "NEVER_SEEN", "grade": "F"}
                continue
            gap = now - ch.last_message_ts
            detector = self.phi_detectors.get(ch.name)
            if detector and detector.window:
                phi = detector.phi(gap)
            else:
                # Fallback: ratio-based
                phi = max(0, gap / ch.expected_interval_sec - 1) * 3
            
            if phi < 1:
                status, grade = "ALIVE", "A"
            elif phi < 3:
                status, grade = "SUSPECT", "B"
            elif phi < 8:
                status, grade = "LIKELY_DEAD", "D"
            else:
                status, grade = "DEAD", "F"
            
            results[ch.name] = {
                "phi": round(phi, 2),
                "gap_sec": round(gap, 1),
                "expected_sec": ch.expected_interval_sec,
                "status": status,
                "grade": grade
            }
        
        # Aggregate: worst channel determines overall
        if not results:
            return {"aggregate": {"status": "NO_CHANNELS", "grade": "F"}, "channels": {}}
        
        worst_phi = max(r["phi"] for r in results.values())
        if worst_phi < 1:
            agg_status, agg_grade = "HEALTHY", "A"
        elif worst_phi < 3:
            agg_status, agg_grade = "DEGRADED", "B"
        elif worst_phi < 8:
            agg_status, agg_grade = "CRITICAL", "D"
        else:
            agg_status, agg_grade = "FAILED", "F"
        
        return {
            "aggregate": {"status": agg_status, "grade": agg_grade, "max_phi": round(worst_phi, 2)},
            "channels": results,
            "ct_class": "◇P" if worst_phi < 3 else ("◇S" if worst_phi < 8 else "None"),
            "insight": "Mailbox IS the failure detector (funwolf). No reply within TTL = presumed dead."
        }


def demo():
    """Demo with realistic agent channels."""
    now = 1741532880  # ~Mar 9 15:08 UTC
    
    # Healthy agent: all channels active
    healthy = AgentRuntime(
        agent_id="kit_fox",
        channels=[
            ActorChannel("heartbeat", "heartbeat", 1200, now - 300, 100),
            ActorChannel("clawk", "clawk", 1800, now - 600, 50),
            ActorChannel("email", "email", 14400, now - 3600, 20),
        ],
        phi_detectors={
            "heartbeat": PhiAccrual(window=[1200] * 20),
            "clawk": PhiAccrual(window=[1800] * 15),
            "email": PhiAccrual(window=[14400] * 10),
        }
    )
    
    # Silent agent: heartbeat ok but no other channels
    silent = AgentRuntime(
        agent_id="ghost_agent",
        channels=[
            ActorChannel("heartbeat", "heartbeat", 1200, now - 300, 100),
            ActorChannel("clawk", "clawk", 1800, now - 86400, 5),
            ActorChannel("email", "email", 14400, None, 0),
        ],
        phi_detectors={
            "heartbeat": PhiAccrual(window=[1200] * 20),
            "clawk": PhiAccrual(window=[1800] * 15),
        }
    )
    
    # Dead agent: no heartbeat
    dead = AgentRuntime(
        agent_id="dead_agent",
        channels=[
            ActorChannel("heartbeat", "heartbeat", 1200, now - 7200, 50),
            ActorChannel("clawk", "clawk", 1800, now - 7200, 10),
        ],
        phi_detectors={
            "heartbeat": PhiAccrual(window=[1200] * 20),
            "clawk": PhiAccrual(window=[1800] * 15),
        }
    )
    
    print("=" * 60)
    print("ACTOR MODEL FAILURE DETECTION")
    print("Agha 1986 + Hayashibara 2004 Φ accrual")
    print("=" * 60)
    
    for name, runtime in [("Healthy", healthy), ("Silent", silent), ("Dead", dead)]:
        result = runtime.suspicion_level(now)
        print(f"\n[{result['aggregate']['grade']}] {runtime.agent_id} — {result['aggregate']['status']}")
        print(f"    CT class: {result['ct_class']}")
        for ch_name, ch_data in result["channels"].items():
            print(f"    {ch_name}: Φ={ch_data['phi']}, {ch_data['status']}")
    
    print(f"\n{'=' * 60}")
    print("Key insight: every message channel is a failure detector.")
    print("FLP says you need one for consensus. Email predates FLP.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
