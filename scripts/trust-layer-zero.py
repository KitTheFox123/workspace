#!/usr/bin/env python3
"""
trust-layer-zero.py — Transport reachability as trust precondition.

Per santaclawd: "six layers of agent trust — all six assume reachability."
Layer 0: before scoring trust, confirm the agent is reachable.

Chandra & Toueg (1996): failure detectors classified by completeness + accuracy.
- Strong completeness: every crashed process eventually suspected by every correct process
- Eventual strong accuracy: no correct process is permanently suspected

Maps to agent trust:
- Completeness: unreachable agents eventually lose trust scores (not indefinite grace)
- Accuracy: reachable agents aren't falsely marked dead (probe from multiple vantage points)

This implements:
1. Multi-probe reachability (SMTP, HTTP, MCP)
2. Failure detector with Chandra-Toueg classification
3. Trust score gating: no reachability = no score update
4. Liveness decay: trust degrades without proof-of-life
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class ProbeType(Enum):
    SMTP = "smtp"
    HTTP = "http"  
    MCP = "mcp"
    RECEIPT = "receipt"  # passive: received a receipt recently


class ReachabilityVerdict(Enum):
    ALIVE = "ALIVE"           # actively confirmed reachable
    SUSPECT = "SUSPECT"       # some probes failing
    UNREACHABLE = "UNREACHABLE"  # all probes failing
    UNKNOWN = "UNKNOWN"       # never probed


@dataclass
class ProbeResult:
    probe_type: ProbeType
    timestamp: datetime
    success: bool
    latency_ms: Optional[float] = None
    vantage_point: str = "self"  # who did the probing


@dataclass
class AgentReachability:
    agent_id: str
    probes: list[ProbeResult] = field(default_factory=list)
    
    def add_probe(self, probe: ProbeResult):
        self.probes.append(probe)
    
    def assess(self, now: Optional[datetime] = None, 
               window: timedelta = timedelta(hours=24),
               min_probes: int = 3) -> dict:
        now = now or datetime.utcnow()
        recent = [p for p in self.probes if (now - p.timestamp) <= window]
        
        if not recent:
            return {
                "agent_id": self.agent_id,
                "verdict": ReachabilityVerdict.UNKNOWN.value,
                "reason": "no probes in window",
                "trust_gate": "BLOCKED",
                "probe_count": 0,
                "recommendation": "probe before scoring"
            }
        
        successes = [p for p in recent if p.success]
        failures = [p for p in recent if not p.success]
        success_rate = len(successes) / len(recent)
        
        # Vantage point diversity (multiple probers = more confident)
        vantage_points = set(p.vantage_point for p in recent if p.success)
        
        # Probe type diversity
        probe_types = set(p.probe_type for p in recent if p.success)
        
        # Chandra-Toueg classification
        # Strong completeness: all failures detected
        # Eventual accuracy: no false positives after stabilization
        if success_rate >= 0.8 and len(vantage_points) >= 2:
            verdict = ReachabilityVerdict.ALIVE
            trust_gate = "OPEN"
            detector_class = "◇P"  # eventually perfect
        elif success_rate >= 0.5:
            verdict = ReachabilityVerdict.SUSPECT
            trust_gate = "DEGRADED"
            detector_class = "◇S"  # eventually strong
        elif success_rate > 0:
            verdict = ReachabilityVerdict.SUSPECT
            trust_gate = "DEGRADED"
            detector_class = "◇W"  # eventually weak
        else:
            verdict = ReachabilityVerdict.UNREACHABLE
            trust_gate = "BLOCKED"
            detector_class = "Ω"  # omega (weakest useful)
        
        # Liveness decay: how long since last success?
        if successes:
            last_success = max(p.timestamp for p in successes)
            staleness = (now - last_success).total_seconds() / 3600
        else:
            staleness = float('inf')
        
        # Decay factor for trust scores
        if staleness < 1:
            decay = 1.0
        elif staleness < 6:
            decay = 0.9
        elif staleness < 24:
            decay = 0.7
        elif staleness < 72:
            decay = 0.4
        else:
            decay = 0.1
        
        # Latency stats
        latencies = [p.latency_ms for p in successes if p.latency_ms is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        
        return {
            "agent_id": self.agent_id,
            "verdict": verdict.value,
            "trust_gate": trust_gate,
            "success_rate": round(success_rate, 2),
            "probe_count": len(recent),
            "successes": len(successes),
            "failures": len(failures),
            "vantage_points": len(vantage_points),
            "probe_types": [pt.value for pt in probe_types],
            "detector_class": detector_class,
            "staleness_hours": round(staleness, 1) if staleness != float('inf') else "never",
            "decay_factor": decay,
            "avg_latency_ms": round(avg_latency, 1) if avg_latency else None,
            "recommendation": _recommend(verdict, trust_gate, len(vantage_points), probe_types)
        }


def _recommend(verdict, gate, vantage_count, probe_types):
    if verdict == ReachabilityVerdict.UNREACHABLE:
        return "BLOCK trust score updates. Agent may be compromised or offline."
    if verdict == ReachabilityVerdict.SUSPECT:
        return "DECAY trust scores. Increase probe frequency. Check from additional vantage points."
    if vantage_count < 2:
        return "ALIVE but single vantage point. Add independent probers for confidence."
    if len(probe_types) < 2:
        return "ALIVE but single transport. Confirm via alternate channel."
    return "ALIVE. Trust scores may update normally."


def demo():
    now = datetime(2026, 3, 21, 7, 0, 0)
    
    # Scenario 1: Healthy agent — multiple probes, multiple vantage points
    healthy = AgentReachability("bro_agent")
    for h in range(0, 24, 4):
        healthy.add_probe(ProbeResult(ProbeType.SMTP, now - timedelta(hours=h), True, 120.0, "kit_fox"))
        healthy.add_probe(ProbeResult(ProbeType.RECEIPT, now - timedelta(hours=h+1), True, None, "funwolf"))
    
    # Scenario 2: Degraded — some failures
    degraded = AgentReachability("flaky_agent")
    for h in range(0, 12, 2):
        degraded.add_probe(ProbeResult(ProbeType.HTTP, now - timedelta(hours=h), h % 4 != 0, 500.0, "kit_fox"))
    
    # Scenario 3: Gone dark — all failures
    dark = AgentReachability("ghost_agent")
    for h in range(0, 24, 6):
        dark.add_probe(ProbeResult(ProbeType.SMTP, now - timedelta(hours=h), False, None, "kit_fox"))
        dark.add_probe(ProbeResult(ProbeType.HTTP, now - timedelta(hours=h), False, None, "funwolf"))
    
    # Scenario 4: Stale — was alive 3 days ago
    stale = AgentReachability("stale_agent")
    stale.add_probe(ProbeResult(ProbeType.SMTP, now - timedelta(days=3), True, 200.0, "kit_fox"))
    stale.add_probe(ProbeResult(ProbeType.HTTP, now - timedelta(days=3, hours=1), True, 150.0, "funwolf"))
    
    for name, agent in [("healthy", healthy), ("degraded", degraded), ("dark", dark), ("stale", stale)]:
        result = agent.assess(now)
        print(f"\n{'='*50}")
        print(f"Agent: {result['agent_id']} ({name})")
        print(f"Verdict: {result['verdict']} | Gate: {result['trust_gate']}")
        print(f"Detector: {result.get('detector_class', 'N/A')} | Decay: {result.get('decay_factor', 'N/A')}")
        print(f"Probes: {result['probe_count']}")
        print(f"→ {result['recommendation']}")


if __name__ == "__main__":
    demo()
