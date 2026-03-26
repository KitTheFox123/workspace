#!/usr/bin/env python3
"""
attestation-freshness.py — Heartbeat-based attestation freshness for ATF.

The missing primitive from the ATF toolchain discussion (santaclawd, 2026-03-26):
All existing tools detect state-at-time-of-check. None detect drift BETWEEN checks.

Solution: periodic re-attestation that decays if not refreshed.
Like ASPA records needing maintenance when providers change.
Like OCSP stapling with a validity window.
Like DNS TTL — cached trust that expires.

Freshness model:
- Each attestation has a TTL (time-to-live)
- Confidence decays exponentially after TTL expires: C(t) = C_0 * decay^((t - ttl) / ttl)
- FRESH: within TTL
- STALE: past TTL but within grace period (2x TTL default)
- EXPIRED: past grace period — attestation is void
- REFRESHED: re-attested within TTL — resets the clock

ASPA parallel (from valley-free-verifier.py):
- ASPA records must be updated when upstream providers change
- Stale ASPA = valid routes marked INVALID by downstream enforcers
- Same pattern: stale attestation = valid agent marked untrusted by relying parties

CRL/OCSP parallel (from santaclawd email thread):
- CRL = push-based, issuer-controlled — fails because issuers are slow
- OCSP = pull-based with stapling — better but still issuer-controlled
- ATF freshness = relying-party-controlled pull with local TTL
- The relying party decides when "stale" matters, not the issuer
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class FreshnessState(Enum):
    FRESH = "FRESH"           # Within TTL
    STALE = "STALE"           # Past TTL, within grace
    EXPIRED = "EXPIRED"       # Past grace period
    REFRESHED = "REFRESHED"   # Re-attested, TTL reset
    NEVER = "NEVER"           # No attestation exists


@dataclass
class Attestation:
    """A single attestation with freshness metadata."""
    attestation_id: str
    agent_id: str
    claim: str
    score: float                    # 0.0-1.0
    issued_at: datetime
    ttl_seconds: int = 86400        # Default 24h
    grace_multiplier: float = 2.0   # Grace = ttl * multiplier
    decay_rate: float = 0.95        # Per-TTL exponential decay
    refreshed_at: Optional[datetime] = None
    refresh_count: int = 0
    
    @property
    def effective_time(self) -> datetime:
        """The time from which freshness is measured."""
        return self.refreshed_at or self.issued_at
    
    @property
    def ttl_expiry(self) -> datetime:
        return self.effective_time + timedelta(seconds=self.ttl_seconds)
    
    @property
    def grace_expiry(self) -> datetime:
        return self.effective_time + timedelta(seconds=int(self.ttl_seconds * self.grace_multiplier))
    
    def state_at(self, t: datetime) -> FreshnessState:
        """Determine freshness state at time t."""
        if t < self.effective_time:
            return FreshnessState.NEVER
        if t <= self.ttl_expiry:
            return FreshnessState.FRESH if self.refresh_count == 0 else FreshnessState.REFRESHED
        if t <= self.grace_expiry:
            return FreshnessState.STALE
        return FreshnessState.EXPIRED
    
    def confidence_at(self, t: datetime) -> float:
        """
        Confidence decays exponentially after TTL.
        Within TTL: full confidence (score).
        After TTL: score * decay^((t - ttl_expiry) / ttl).
        After grace: 0.0.
        """
        state = self.state_at(t)
        if state in (FreshnessState.FRESH, FreshnessState.REFRESHED):
            return self.score
        if state == FreshnessState.EXPIRED or state == FreshnessState.NEVER:
            return 0.0
        # STALE: decay
        elapsed = (t - self.ttl_expiry).total_seconds()
        periods = elapsed / self.ttl_seconds
        return self.score * (self.decay_rate ** periods)
    
    def refresh(self, t: datetime, new_score: Optional[float] = None):
        """Refresh the attestation, resetting TTL."""
        self.refreshed_at = t
        self.refresh_count += 1
        if new_score is not None:
            self.score = new_score


class FreshnessMonitor:
    """
    Monitor attestation freshness across a pool of agents.
    
    Detects:
    1. Stale attestations approaching expiry
    2. Agents with no recent re-attestation
    3. Drift between refresh intervals (inconsistent heartbeat)
    4. Pool-level freshness degradation
    """
    
    def __init__(self):
        self.attestations: dict[str, list[Attestation]] = {}  # agent_id -> attestations
    
    def add(self, att: Attestation):
        if att.agent_id not in self.attestations:
            self.attestations[att.agent_id] = []
        self.attestations[att.agent_id].append(att)
    
    def pool_report(self, at_time: datetime) -> dict:
        """Generate freshness report for the entire pool."""
        states = {"FRESH": 0, "STALE": 0, "EXPIRED": 0, "REFRESHED": 0, "NEVER": 0}
        total_confidence = 0.0
        total_attestations = 0
        agent_reports = {}
        
        for agent_id, atts in self.attestations.items():
            agent_fresh = 0
            agent_stale = 0
            agent_expired = 0
            agent_conf = 0.0
            
            for att in atts:
                state = att.state_at(at_time)
                states[state.value] += 1
                conf = att.confidence_at(at_time)
                total_confidence += conf
                agent_conf += conf
                total_attestations += 1
                
                if state == FreshnessState.FRESH or state == FreshnessState.REFRESHED:
                    agent_fresh += 1
                elif state == FreshnessState.STALE:
                    agent_stale += 1
                else:
                    agent_expired += 1
            
            agent_reports[agent_id] = {
                "fresh": agent_fresh,
                "stale": agent_stale,
                "expired": agent_expired,
                "avg_confidence": round(agent_conf / len(atts), 4) if atts else 0,
            }
        
        avg_conf = total_confidence / total_attestations if total_attestations > 0 else 0
        fresh_ratio = (states["FRESH"] + states["REFRESHED"]) / total_attestations if total_attestations > 0 else 0
        
        # Pool health
        if fresh_ratio > 0.8:
            health = "HEALTHY"
        elif fresh_ratio > 0.5:
            health = "DEGRADING"
        elif fresh_ratio > 0.2:
            health = "STALE"
        else:
            health = "EXPIRED"
        
        return {
            "timestamp": at_time.isoformat(),
            "health": health,
            "total_attestations": total_attestations,
            "states": states,
            "fresh_ratio": round(fresh_ratio, 4),
            "avg_confidence": round(avg_conf, 4),
            "agents": agent_reports,
        }


def run_demo():
    """Demonstrate attestation freshness monitoring."""
    monitor = FreshnessMonitor()
    
    now = datetime(2026, 3, 26, 15, 0, 0, tzinfo=timezone.utc)
    
    # Agent 1: Fresh attestation (issued 6h ago, 24h TTL)
    monitor.add(Attestation("att1", "agent_alpha", "skill:verified", 0.92,
                            issued_at=now - timedelta(hours=6)))
    
    # Agent 2: Stale attestation (issued 30h ago, 24h TTL)
    monitor.add(Attestation("att2", "agent_beta", "skill:verified", 0.88,
                            issued_at=now - timedelta(hours=30)))
    
    # Agent 3: Expired attestation (issued 72h ago, 24h TTL)
    monitor.add(Attestation("att3", "agent_gamma", "skill:verified", 0.95,
                            issued_at=now - timedelta(hours=72)))
    
    # Agent 4: Refreshed attestation (issued 48h ago, refreshed 2h ago)
    att4 = Attestation("att4", "agent_delta", "skill:verified", 0.85,
                       issued_at=now - timedelta(hours=48))
    att4.refresh(now - timedelta(hours=2), new_score=0.87)
    monitor.add(att4)
    
    # Agent 5: Multiple attestations, mixed freshness
    monitor.add(Attestation("att5a", "agent_epsilon", "skill:verified", 0.90,
                            issued_at=now - timedelta(hours=3)))
    monitor.add(Attestation("att5b", "agent_epsilon", "identity:confirmed", 0.95,
                            issued_at=now - timedelta(hours=36)))
    
    print("=" * 70)
    print("ATTESTATION FRESHNESS MONITOR")
    print("=" * 70)
    
    report = monitor.pool_report(now)
    print(f"\nPool Health: {report['health']}")
    print(f"Fresh Ratio: {report['fresh_ratio']:.0%}")
    print(f"Avg Confidence: {report['avg_confidence']:.4f}")
    print(f"States: {json.dumps(report['states'])}")
    
    print("\nPer-Agent:")
    for agent_id, info in report['agents'].items():
        print(f"  {agent_id}: fresh={info['fresh']} stale={info['stale']} expired={info['expired']} conf={info['avg_confidence']}")
    
    # Show confidence decay over time
    print(f"\n--- Confidence Decay Demo (agent_beta, stale attestation) ---")
    att_stale = Attestation("demo", "demo", "test", 0.88,
                            issued_at=now - timedelta(hours=30), ttl_seconds=86400)
    
    for hours_from_issue in [0, 12, 24, 30, 36, 42, 48]:
        t = att_stale.issued_at + timedelta(hours=hours_from_issue)
        state = att_stale.state_at(t)
        conf = att_stale.confidence_at(t)
        marker = " ← TTL" if hours_from_issue == 24 else " ← GRACE" if hours_from_issue == 48 else ""
        print(f"  +{hours_from_issue:2d}h: {state.value:10s} conf={conf:.4f}{marker}")
    
    print(f"\n--- Refresh Demo (agent_delta) ---")
    att_refresh = Attestation("demo2", "demo2", "test", 0.85,
                              issued_at=now - timedelta(hours=48))
    print(f"  Issued 48h ago, no refresh: state={att_refresh.state_at(now).value}, conf={att_refresh.confidence_at(now):.4f}")
    att_refresh.refresh(now - timedelta(hours=2), new_score=0.87)
    print(f"  After refresh 2h ago:       state={att_refresh.state_at(now).value}, conf={att_refresh.confidence_at(now):.4f}")
    
    print(f"\n{'=' * 70}")
    print("ASPA parallel: stale ASPA record = valid routes marked INVALID.")
    print("ATF parallel: stale attestation = valid agent marked untrusted.")
    print("The relying party decides when 'stale' matters, not the issuer.")
    print("Pull > push. TTL > revocation list. Heartbeat > one-time check.")


if __name__ == "__main__":
    run_demo()
