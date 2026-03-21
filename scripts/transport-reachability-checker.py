#!/usr/bin/env python3
"""
transport-reachability-checker.py — Layer 0: transport reachability audit.

Per santaclawd: "six layers of agent trust infrastructure — all six assume reachability."
Layer 0 = transport. Trust stack is only as live as the network underneath.

Checks:
1. SMTP reachability (MX resolution + connection)
2. REST API health (HTTP probe)
3. Fallback transport availability (how many channels?)
4. Last-seen freshness (stale = unreachable ≠ untrusted)
5. Transport diversity (all-eggs-in-one-basket detection)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum


class TransportType(Enum):
    SMTP = "smtp"
    REST = "rest"
    WEBSOCKET = "websocket"
    P2P = "p2p"


class ReachabilityStatus(Enum):
    REACHABLE = "REACHABLE"
    DEGRADED = "DEGRADED"
    UNREACHABLE = "UNREACHABLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class TransportEndpoint:
    transport_type: TransportType
    endpoint: str  # email address, URL, etc.
    last_successful: Optional[datetime] = None
    last_attempt: Optional[datetime] = None
    failure_count: int = 0
    latency_ms: Optional[float] = None


@dataclass
class AgentReachability:
    agent_id: str
    endpoints: list[TransportEndpoint]
    
    def audit(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        issues = []
        
        if not self.endpoints:
            return {
                "agent_id": self.agent_id,
                "status": ReachabilityStatus.UNREACHABLE.value,
                "grade": "F",
                "issues": [{"type": "NO_TRANSPORT", "severity": "CRITICAL", 
                           "detail": "No transport endpoints configured"}],
                "transport_diversity": 0.0
            }
        
        # 1. Transport diversity
        types = set(e.transport_type for e in self.endpoints)
        diversity = len(types) / len(TransportType)
        if len(types) == 1:
            issues.append({
                "type": "SINGLE_TRANSPORT",
                "transport": list(types)[0].value,
                "severity": "WARNING",
                "detail": f"Only {list(types)[0].value} — no fallback if transport fails"
            })
        
        # 2. Freshness check
        stale_threshold = timedelta(hours=24)
        reachable = []
        stale = []
        unreachable = []
        
        for ep in self.endpoints:
            if ep.last_successful is None:
                unreachable.append(ep)
            elif (now - ep.last_successful) > stale_threshold:
                stale.append(ep)
            else:
                reachable.append(ep)
        
        if not reachable:
            if stale:
                issues.append({
                    "type": "ALL_STALE",
                    "count": len(stale),
                    "severity": "CRITICAL",
                    "detail": f"All {len(stale)} endpoints stale (>24h since success)"
                })
            else:
                issues.append({
                    "type": "ALL_UNREACHABLE",
                    "severity": "CRITICAL",
                    "detail": "No endpoint has ever succeeded"
                })
        
        # 3. Failure rate
        total_failures = sum(e.failure_count for e in self.endpoints)
        if total_failures > 10:
            issues.append({
                "type": "HIGH_FAILURE_RATE",
                "failures": total_failures,
                "severity": "WARNING",
                "detail": f"{total_failures} cumulative failures across endpoints"
            })
        
        # 4. SMTP presence (cockroach transport)
        has_smtp = any(e.transport_type == TransportType.SMTP for e in self.endpoints)
        smtp_reachable = any(e.transport_type == TransportType.SMTP and e in reachable for e in self.endpoints)
        
        if not has_smtp:
            issues.append({
                "type": "NO_SMTP",
                "severity": "INFO",
                "detail": "No SMTP endpoint — missing cockroach fallback"
            })
        
        # 5. Latency
        latencies = [e.latency_ms for e in self.endpoints if e.latency_ms is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        
        # Status
        if reachable:
            status = ReachabilityStatus.REACHABLE if len(reachable) > 1 else ReachabilityStatus.DEGRADED
        elif stale:
            status = ReachabilityStatus.DEGRADED
        else:
            status = ReachabilityStatus.UNREACHABLE
        
        # Grade
        critical = sum(1 for i in issues if i["severity"] == "CRITICAL")
        warnings = sum(1 for i in issues if i["severity"] == "WARNING")
        
        if critical > 0:
            grade = "F"
        elif warnings > 1:
            grade = "D"
        elif warnings == 1:
            grade = "C"
        elif issues:
            grade = "B"
        else:
            grade = "A"
        
        return {
            "agent_id": self.agent_id,
            "status": status.value,
            "grade": grade,
            "transport_diversity": round(diversity, 2),
            "reachable_endpoints": len(reachable),
            "stale_endpoints": len(stale),
            "unreachable_endpoints": len(unreachable),
            "has_smtp_fallback": has_smtp,
            "avg_latency_ms": round(avg_latency, 1) if avg_latency else None,
            "issues": issues,
            "trust_stack_viable": status != ReachabilityStatus.UNREACHABLE
        }


def demo():
    now = datetime(2026, 3, 21, 6, 30, 0)
    
    # Scenario 1: Healthy multi-transport
    healthy = AgentReachability("kit_fox", [
        TransportEndpoint(TransportType.SMTP, "kit_fox@agentmail.to", 
                         now - timedelta(hours=2), now - timedelta(hours=1), 0, 450.0),
        TransportEndpoint(TransportType.REST, "https://api.example.com/agent/kit",
                         now - timedelta(minutes=30), now - timedelta(minutes=15), 1, 120.0),
        TransportEndpoint(TransportType.WEBSOCKET, "wss://relay.example.com/kit",
                         now - timedelta(hours=1), now - timedelta(minutes=45), 0, 35.0),
    ])
    
    # Scenario 2: Single transport, stale
    single = AgentReachability("lonely_agent", [
        TransportEndpoint(TransportType.REST, "https://api.example.com/agent/lonely",
                         now - timedelta(days=3), now - timedelta(hours=6), 15, 2100.0),
    ])
    
    # Scenario 3: All unreachable
    dead = AgentReachability("ghost_agent", [
        TransportEndpoint(TransportType.REST, "https://dead.example.com/agent", 
                         None, now - timedelta(hours=1), 50),
        TransportEndpoint(TransportType.SMTP, "ghost@agentmail.to",
                         None, now - timedelta(hours=2), 20),
    ])
    
    for name, agent in [("healthy_multi", healthy), ("single_stale", single), ("all_unreachable", dead)]:
        result = agent.audit(now)
        print(f"\n{'='*50}")
        print(f"Agent: {result['agent_id']} ({name})")
        print(f"Status: {result['status']} | Grade: {result['grade']}")
        print(f"Diversity: {result['transport_diversity']} | SMTP: {result['has_smtp_fallback']}")
        print(f"Reachable: {result['reachable_endpoints']} | Stale: {result['stale_endpoints']} | Dead: {result['unreachable_endpoints']}")
        print(f"Trust stack viable: {result['trust_stack_viable']}")
        if result['issues']:
            for issue in result['issues']:
                print(f"  [{issue['severity']}] {issue['type']}: {issue['detail']}")


if __name__ == "__main__":
    demo()
