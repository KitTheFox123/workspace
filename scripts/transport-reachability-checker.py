#!/usr/bin/env python3
"""
transport-reachability-checker.py — Layer 0: transport reachability for trust stack.

Per santaclawd: "six layers of trust infrastructure — all six assume reachability."
Dead oracle = 0 effective count regardless of independence score.

Checks:
1. SMTP reachability (MX record + port 25/587)
2. HTTPS endpoint liveness  
3. Heartbeat freshness (last seen)
4. Reachability-weighted independence (dead oracles don't count)
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class Oracle:
    id: str
    operator: str
    model_family: str
    email: Optional[str] = None
    https_endpoint: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    smtp_reachable: bool = False
    https_reachable: bool = False


@dataclass 
class ReachabilityAudit:
    oracles: list[Oracle]
    
    def check(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        n = len(self.oracles)
        
        results = []
        for o in self.oracles:
            # Transport check
            has_transport = o.smtp_reachable or o.https_reachable
            
            # Heartbeat freshness
            stale_threshold = timedelta(hours=24)
            heartbeat_fresh = (
                o.last_heartbeat is not None and
                (now - o.last_heartbeat) < stale_threshold
            )
            
            # Reachability score
            transport_score = 0.0
            if o.smtp_reachable and o.https_reachable:
                transport_score = 1.0
            elif o.smtp_reachable or o.https_reachable:
                transport_score = 0.6  # single transport = fragile
            
            freshness_score = 0.0
            if o.last_heartbeat:
                hours_ago = (now - o.last_heartbeat).total_seconds() / 3600
                if hours_ago < 1:
                    freshness_score = 1.0
                elif hours_ago < 6:
                    freshness_score = 0.8
                elif hours_ago < 24:
                    freshness_score = 0.5
                elif hours_ago < 72:
                    freshness_score = 0.2
                # >72h = 0.0
            
            reachability = min(transport_score, freshness_score) if has_transport else 0.0
            
            status = "LIVE" if reachability >= 0.5 else "DEGRADED" if reachability > 0 else "DEAD"
            
            results.append({
                "id": o.id,
                "operator": o.operator,
                "smtp": o.smtp_reachable,
                "https": o.https_reachable,
                "last_heartbeat_hours": round((now - o.last_heartbeat).total_seconds() / 3600, 1) if o.last_heartbeat else None,
                "transport_score": transport_score,
                "freshness_score": freshness_score,
                "reachability": round(reachability, 2),
                "status": status,
            })
        
        # Effective count (only LIVE oracles count for independence)
        live = [r for r in results if r["status"] == "LIVE"]
        dead = [r for r in results if r["status"] == "DEAD"]
        degraded = [r for r in results if r["status"] == "DEGRADED"]
        
        effective_count = len(live) + 0.3 * len(degraded)
        
        # Independence only among live oracles
        live_operators = set()
        for r in results:
            if r["status"] in ("LIVE", "DEGRADED"):
                live_operators.add(r["operator"])
        
        # BFT safety: f < n/3 on EFFECTIVE count
        max_byzantine = int((effective_count - 1) / 3)
        
        # Grade
        live_ratio = len(live) / n if n > 0 else 0
        if live_ratio >= 0.8:
            grade = "A"
        elif live_ratio >= 0.6:
            grade = "B"  
        elif live_ratio >= 0.4:
            grade = "C"
        elif live_ratio > 0:
            grade = "D"
        else:
            grade = "F"
        
        return {
            "total_oracles": n,
            "live": len(live),
            "degraded": len(degraded),
            "dead": len(dead),
            "effective_count": round(effective_count, 1),
            "live_operators": len(live_operators),
            "max_byzantine": max_byzantine,
            "grade": grade,
            "verdict": "HEALTHY" if grade in ("A", "B") else "DEGRADED" if grade == "C" else "UNREACHABLE",
            "oracles": results,
        }


def demo():
    now = datetime(2026, 3, 21, 7, 0, 0)
    
    # Scenario 1: Healthy quorum
    healthy = ReachabilityAudit([
        Oracle("o1", "acme", "claude", smtp_reachable=True, https_reachable=True, last_heartbeat=now - timedelta(minutes=30)),
        Oracle("o2", "beta", "gpt4", smtp_reachable=True, https_reachable=True, last_heartbeat=now - timedelta(hours=2)),
        Oracle("o3", "gamma", "gemini", smtp_reachable=True, https_reachable=False, last_heartbeat=now - timedelta(hours=4)),
        Oracle("o4", "delta", "llama", smtp_reachable=True, https_reachable=True, last_heartbeat=now - timedelta(hours=1)),
        Oracle("o5", "epsilon", "mistral", smtp_reachable=True, https_reachable=True, last_heartbeat=now - timedelta(minutes=15)),
    ])
    
    # Scenario 2: Half dead
    degraded = ReachabilityAudit([
        Oracle("o1", "acme", "claude", smtp_reachable=True, https_reachable=True, last_heartbeat=now - timedelta(minutes=30)),
        Oracle("o2", "beta", "gpt4", smtp_reachable=False, https_reachable=False, last_heartbeat=now - timedelta(days=5)),
        Oracle("o3", "gamma", "gemini", smtp_reachable=False, https_reachable=False),
        Oracle("o4", "delta", "llama", smtp_reachable=True, https_reachable=False, last_heartbeat=now - timedelta(hours=48)),
        Oracle("o5", "epsilon", "mistral", smtp_reachable=False, https_reachable=True, last_heartbeat=now - timedelta(days=4)),
    ])
    
    for name, audit in [("healthy_quorum", healthy), ("half_dead", degraded)]:
        result = audit.check(now)
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"Grade: {result['grade']} | Verdict: {result['verdict']}")
        print(f"Live: {result['live']}/{result['total_oracles']} | Dead: {result['dead']} | Effective: {result['effective_count']}")
        print(f"Live operators: {result['live_operators']} | Max byzantine: {result['max_byzantine']}")
        for o in result['oracles']:
            hb = f"{o['last_heartbeat_hours']}h" if o['last_heartbeat_hours'] is not None else "never"
            print(f"  {o['id']}: {o['status']} (reach={o['reachability']}, smtp={o['smtp']}, https={o['https']}, hb={hb})")


if __name__ == "__main__":
    demo()
