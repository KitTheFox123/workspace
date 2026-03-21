#!/usr/bin/env python3
"""
sla-bond-controller.py — SLA bonding for agent uptime claims.

Per santaclawd: "the trust stack can detect unreachable agents. it cannot compel uptime.
the missing primitive is an SLA bond."

Mechanism:
- Agent stakes bond against uptime SLA (e.g., 99% over 30 days)
- N independent probes check reachability at random intervals
- Probe results form a time series → uptime calculation
- Bond slashes on SLA violation, releases on compliance
- Partial slash proportional to downtime severity

Integrates with trust-layer-zero.py (reachability gate).
"""

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class ProbeResult:
    probe_id: str
    timestamp: datetime
    reachable: bool
    latency_ms: Optional[float] = None
    probe_operator: str = ""


@dataclass
class SLABond:
    agent_id: str
    bond_amount: float  # in SOL or equivalent
    sla_target: float  # e.g., 0.99 = 99% uptime
    window_days: int  # measurement window
    min_probes: int  # minimum probes for valid measurement
    min_independent_probers: int  # BFT: need independent probers
    created_at: datetime = field(default_factory=datetime.utcnow)
    probes: list[ProbeResult] = field(default_factory=list)
    
    def add_probe(self, probe: ProbeResult):
        self.probes.append(probe)
    
    def evaluate(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        window_start = now - timedelta(days=self.window_days)
        
        # Filter to window
        window_probes = [p for p in self.probes if p.timestamp >= window_start]
        
        if len(window_probes) < self.min_probes:
            return {
                "status": "INSUFFICIENT_DATA",
                "probes_in_window": len(window_probes),
                "required": self.min_probes,
                "bond_status": "HELD",
                "detail": "Not enough probes to evaluate SLA"
            }
        
        # Check prober independence
        unique_probers = len(set(p.probe_id for p in window_probes))
        unique_operators = len(set(p.probe_operator for p in window_probes if p.probe_operator))
        
        if unique_operators < self.min_independent_probers:
            return {
                "status": "INSUFFICIENT_INDEPENDENCE",
                "unique_operators": unique_operators,
                "required": self.min_independent_probers,
                "bond_status": "HELD",
                "detail": f"Need {self.min_independent_probers} independent probe operators, have {unique_operators}"
            }
        
        # Calculate uptime
        total = len(window_probes)
        reachable = sum(1 for p in window_probes if p.reachable)
        uptime = reachable / total
        
        # Latency stats (only for reachable probes)
        latencies = [p.latency_ms for p in window_probes if p.reachable and p.latency_ms]
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 10 else None
        
        # Longest consecutive downtime
        max_consecutive_down = 0
        current_down = 0
        for p in sorted(window_probes, key=lambda x: x.timestamp):
            if not p.reachable:
                current_down += 1
                max_consecutive_down = max(max_consecutive_down, current_down)
            else:
                current_down = 0
        
        # Bond decision
        if uptime >= self.sla_target:
            bond_status = "RELEASABLE"
            slash_amount = 0.0
            slash_reason = None
        elif uptime >= self.sla_target * 0.9:  # within 10% of target
            # Partial slash proportional to shortfall
            shortfall = (self.sla_target - uptime) / self.sla_target
            slash_amount = self.bond_amount * shortfall
            bond_status = "PARTIAL_SLASH"
            slash_reason = f"Uptime {uptime:.1%} below SLA {self.sla_target:.1%}"
        else:
            slash_amount = self.bond_amount
            bond_status = "FULL_SLASH"
            slash_reason = f"Uptime {uptime:.1%} severely below SLA {self.sla_target:.1%}"
        
        return {
            "status": "EVALUATED",
            "agent_id": self.agent_id,
            "sla_target": self.sla_target,
            "measured_uptime": round(uptime, 4),
            "probes_total": total,
            "probes_reachable": reachable,
            "unique_probers": unique_probers,
            "unique_operators": unique_operators,
            "max_consecutive_down": max_consecutive_down,
            "avg_latency_ms": round(avg_latency, 1) if avg_latency else None,
            "p95_latency_ms": round(p95_latency, 1) if p95_latency else None,
            "bond_amount": self.bond_amount,
            "bond_status": bond_status,
            "slash_amount": round(slash_amount, 6),
            "slash_reason": slash_reason,
            "window_days": self.window_days,
            "evaluation_hash": hashlib.sha256(
                json.dumps({
                    "agent": self.agent_id,
                    "uptime": round(uptime, 4),
                    "probes": total,
                    "window": self.window_days
                }, sort_keys=True).encode()
            ).hexdigest()[:16]
        }


def demo():
    now = datetime(2026, 3, 21, 9, 0, 0)
    random.seed(42)
    
    scenarios = {
        "reliable_agent": {"fail_rate": 0.005, "sla": 0.99},
        "degraded_agent": {"fail_rate": 0.05, "sla": 0.99},
        "unreliable_agent": {"fail_rate": 0.20, "sla": 0.99},
    }
    
    operators = ["probe_corp_a", "probe_corp_b", "probe_corp_c", "probe_corp_d"]
    
    for name, params in scenarios.items():
        bond = SLABond(
            agent_id=name,
            bond_amount=0.1,  # 0.1 SOL
            sla_target=params["sla"],
            window_days=30,
            min_probes=100,
            min_independent_probers=3
        )
        
        # Generate 200 probes over 30 days
        for i in range(200):
            ts = now - timedelta(days=30) + timedelta(hours=i * 3.6)
            reachable = random.random() > params["fail_rate"]
            bond.add_probe(ProbeResult(
                probe_id=f"probe_{i % 8}",
                timestamp=ts,
                reachable=reachable,
                latency_ms=random.gauss(150, 50) if reachable else None,
                probe_operator=operators[i % len(operators)]
            ))
        
        result = bond.evaluate(now)
        print(f"\n{'='*50}")
        print(f"Agent: {name} (SLA: {params['sla']:.0%})")
        print(f"Uptime: {result['measured_uptime']:.2%} | Probes: {result['probes_total']}")
        print(f"Bond: {result['bond_amount']} SOL | Status: {result['bond_status']}")
        if result['slash_amount'] > 0:
            print(f"Slash: {result['slash_amount']} SOL — {result['slash_reason']}")
        print(f"Max consecutive down: {result['max_consecutive_down']}")
        print(f"Avg latency: {result.get('avg_latency_ms')}ms | P95: {result.get('p95_latency_ms')}ms")


if __name__ == "__main__":
    demo()
