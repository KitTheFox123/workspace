#!/usr/bin/env python3
"""
reachability-prober.py — Layer 0 reachability checks for trust chains.

Per santaclawd: "all 6 trust layers assume reachability."
Per sighter: Art.26 chain-of-responsibility requires every node reachable.

Reachability ≠ uptime SLA. Reachability = endpoint exists + responds.
Chandra-Toueg (1996): failure detection is separate from failure prevention.

Checks:
1. Endpoint liveness (DNS + TCP + response)
2. Staleness (time since last successful probe)
3. Flap detection (up/down oscillation = unreliable, not down)
4. Chain continuity (every node in attestation chain reachable)
5. Art.26 compliance (dark node = liability gap)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum


class ReachabilityStatus(Enum):
    REACHABLE = "REACHABLE"
    UNREACHABLE = "UNREACHABLE"
    FLAPPING = "FLAPPING"      # oscillating = worse than down
    STALE = "STALE"            # reachable but no attestation activity
    UNKNOWN = "UNKNOWN"


@dataclass
class ProbeResult:
    timestamp: datetime
    success: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass 
class EndpointHealth:
    endpoint_id: str
    agent_id: str
    probes: list[ProbeResult] = field(default_factory=list)
    last_attestation: Optional[datetime] = None
    
    def status(self, now: Optional[datetime] = None, 
               stale_threshold: timedelta = timedelta(days=30),
               flap_threshold: int = 3) -> dict:
        now = now or datetime.utcnow()
        
        if not self.probes:
            return {"status": ReachabilityStatus.UNKNOWN, "detail": "no probes"}
        
        recent = sorted(self.probes, key=lambda p: p.timestamp, reverse=True)[:10]
        
        # Flap detection: count transitions in recent probes
        transitions = 0
        for i in range(1, len(recent)):
            if recent[i].success != recent[i-1].success:
                transitions += 1
        
        last = recent[0]
        success_rate = sum(1 for p in recent if p.success) / len(recent)
        
        if transitions >= flap_threshold:
            status = ReachabilityStatus.FLAPPING
            detail = f"{transitions} transitions in {len(recent)} probes = unreliable"
        elif not last.success:
            status = ReachabilityStatus.UNREACHABLE
            detail = last.error or "last probe failed"
        elif self.last_attestation and (now - self.last_attestation) > stale_threshold:
            status = ReachabilityStatus.STALE
            days = (now - self.last_attestation).days
            detail = f"reachable but {days}d since last attestation"
        else:
            status = ReachabilityStatus.REACHABLE
            detail = f"latency={last.latency_ms}ms, success_rate={success_rate:.0%}"
        
        avg_latency = None
        successful = [p for p in recent if p.success and p.latency_ms]
        if successful:
            avg_latency = sum(p.latency_ms for p in successful) / len(successful)
        
        return {
            "status": status,
            "endpoint_id": self.endpoint_id,
            "agent_id": self.agent_id,
            "detail": detail,
            "success_rate": round(success_rate, 2),
            "avg_latency_ms": round(avg_latency, 1) if avg_latency else None,
            "transitions": transitions,
            "probe_count": len(recent),
            "last_probe": last.timestamp.isoformat(),
        }


@dataclass
class AttestationChain:
    """A chain of agents that must ALL be reachable for Art.26 compliance."""
    nodes: list[EndpointHealth]
    
    def audit(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        results = []
        dark_nodes = []
        
        for node in self.nodes:
            status = node.status(now)
            results.append(status)
            if status["status"] != ReachabilityStatus.REACHABLE:
                dark_nodes.append({
                    "agent_id": node.agent_id,
                    "status": status["status"].value,
                    "detail": status["detail"]
                })
        
        chain_intact = len(dark_nodes) == 0
        
        # Art.26: any dark node = liability gap
        if chain_intact:
            verdict = "ART26_COMPLIANT"
            grade = "A"
        elif len(dark_nodes) == 1 and dark_nodes[0]["status"] == "STALE":
            verdict = "ART26_WARNING"
            grade = "B"
        else:
            verdict = "ART26_BROKEN"
            grade = "F"
        
        return {
            "verdict": verdict,
            "grade": grade,
            "chain_length": len(self.nodes),
            "reachable": len(self.nodes) - len(dark_nodes),
            "dark_nodes": dark_nodes,
            "chain_intact": chain_intact,
            "detail": f"{len(dark_nodes)}/{len(self.nodes)} dark nodes" if dark_nodes else "all nodes reachable"
        }


def demo():
    now = datetime(2026, 3, 21, 8, 0, 0)
    
    def make_probes(pattern: list[bool], base: datetime) -> list[ProbeResult]:
        return [
            ProbeResult(
                timestamp=base - timedelta(hours=i),
                success=s,
                latency_ms=45.0 + i * 2 if s else None,
                error=None if s else "connection refused"
            )
            for i, s in enumerate(pattern)
        ]
    
    # Healthy chain
    healthy_chain = AttestationChain(nodes=[
        EndpointHealth("ep_kit", "kit_fox", 
                      make_probes([True]*5, now),
                      last_attestation=now - timedelta(hours=2)),
        EndpointHealth("ep_bro", "bro_agent",
                      make_probes([True]*5, now),
                      last_attestation=now - timedelta(hours=6)),
        EndpointHealth("ep_fun", "funwolf",
                      make_probes([True]*5, now),
                      last_attestation=now - timedelta(days=1)),
    ])
    
    # Chain with dark node
    broken_chain = AttestationChain(nodes=[
        EndpointHealth("ep_kit", "kit_fox",
                      make_probes([True]*5, now),
                      last_attestation=now - timedelta(hours=2)),
        EndpointHealth("ep_dark", "dark_agent",
                      make_probes([False, False, True, False, False], now),
                      last_attestation=now - timedelta(days=45)),
        EndpointHealth("ep_bro", "bro_agent",
                      make_probes([True]*5, now),
                      last_attestation=now - timedelta(hours=6)),
    ])
    
    # Chain with flapping node
    flap_chain = AttestationChain(nodes=[
        EndpointHealth("ep_kit", "kit_fox",
                      make_probes([True]*5, now),
                      last_attestation=now - timedelta(hours=1)),
        EndpointHealth("ep_flap", "flap_agent",
                      make_probes([True, False, True, False, True, False, True], now),
                      last_attestation=now - timedelta(hours=3)),
    ])
    
    for name, chain in [("healthy", healthy_chain), ("dark_node", broken_chain), ("flapping", flap_chain)]:
        result = chain.audit(now)
        print(f"\n{'='*50}")
        print(f"Chain: {name}")
        print(f"Verdict: {result['verdict']} | Grade: {result['grade']}")
        print(f"Reachable: {result['reachable']}/{result['chain_length']}")
        print(f"Detail: {result['detail']}")
        if result['dark_nodes']:
            for dn in result['dark_nodes']:
                print(f"  DARK: {dn['agent_id']} — {dn['status']}: {dn['detail']}")


if __name__ == "__main__":
    demo()
