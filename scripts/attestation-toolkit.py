#!/usr/bin/env python3
"""
attestation-toolkit.py — Unified attestation framework

Ties together today's 7 scripts into one pipeline:
1. vigilance-decrement-sim.py → rotation scheduling
2. dead-mans-switch.py → absence detection
3. heartbeat-payload-verifier.py → observable state watchdog
4. evidence-gated-attestation.py → evidence gate + search power
5. signed-null-observation.py → deliberate non-action hashing
6. preregistration-commit-reveal.py → p-hacking prevention

Vocabulary:
  ACK = signed positive observation
  NACK = signed null observation (search power > threshold)
  SILENCE = dead man's switch alarm
  CHURN = windowed watchdog rejection (too fast)
  STALE = evidence gate rejection (same digest)

Each tool <200 lines. Each solves one problem. Gall's Law.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AttestationResult:
    """Unified result from the pipeline"""
    agent_id: str
    timestamp: float
    verdict: str       # ACK, NACK, SILENCE, CHURN, STALE, INVALID
    grade: str         # A-F
    stage: int         # which check caught it (0=passed all)
    details: dict = field(default_factory=dict)


@dataclass
class AttestationPipeline:
    """Run all checks in sequence"""
    expected_channels: list = field(default_factory=lambda: ["clawk", "email", "moltbook", "shellmates"])
    min_interval: float = 300.0      # 5 min anti-churn
    max_interval: float = 3600.0     # 1 hr dead man's switch  
    min_search_power: float = 0.5    # Altman 1995
    
    # State
    last_timestamp: float = 0.0
    last_digest: str = ""
    last_scope_hash: str = ""
    consecutive_stale: int = 0
    consecutive_churn: int = 0
    stats: dict = field(default_factory=lambda: {"ACK": 0, "NACK": 0, "SILENCE": 0, "CHURN": 0, "STALE": 0, "INVALID": 0})
    
    def check(self, agent_id: str, timestamp: float, 
              scope_hash: str = "", action_digest: str = "",
              action_count: int = 0, channels: list = None,
              commit_hash: str = "") -> AttestationResult:
        """Run the full pipeline"""
        channels = channels or []
        elapsed = timestamp - self.last_timestamp if self.last_timestamp > 0 else self.min_interval * 2
        
        # Stage 1: Dead man's switch (SILENCE)
        if elapsed > self.max_interval and self.last_timestamp > 0:
            self.last_timestamp = timestamp
            r = AttestationResult(agent_id, timestamp, "SILENCE", "F", 1,
                {"elapsed": elapsed, "max": self.max_interval})
            self.stats["SILENCE"] += 1
            return r
        
        # Stage 2: Windowed watchdog (CHURN)
        if elapsed < self.min_interval and self.last_timestamp > 0:
            self.consecutive_churn += 1
            r = AttestationResult(agent_id, timestamp, "CHURN", "D", 2,
                {"elapsed": elapsed, "min": self.min_interval, "streak": self.consecutive_churn})
            self.stats["CHURN"] += 1
            return r
        self.consecutive_churn = 0
        
        # Stage 3: Evidence gate (STALE)
        if action_digest == self.last_digest and self.last_digest and action_count == 0:
            self.consecutive_stale += 1
            grade = "C" if self.consecutive_stale < 3 else "F"
            r = AttestationResult(agent_id, timestamp, "STALE", grade, 3,
                {"streak": self.consecutive_stale})
            self.stats["STALE"] += 1
            self.last_timestamp = timestamp
            return r
        self.consecutive_stale = 0
        
        # Stage 4: Search power for null observations
        if action_count == 0:
            coverage = len(set(channels) & set(self.expected_channels)) / max(len(self.expected_channels), 1)
            if coverage < self.min_search_power:
                r = AttestationResult(agent_id, timestamp, "INVALID", "D", 4,
                    {"reason": "low_power_nack", "coverage": round(coverage, 2)})
                self.stats["INVALID"] += 1
                self.last_timestamp = timestamp
                return r
            # Valid NACK
            self.last_digest = action_digest
            self.last_timestamp = timestamp
            self.last_scope_hash = scope_hash
            r = AttestationResult(agent_id, timestamp, "NACK", "B", 0,
                {"coverage": round(coverage, 2), "channels": channels})
            self.stats["NACK"] += 1
            return r
        
        # Stage 5: Scope drift check
        scope_changed = (self.last_scope_hash and scope_hash and 
                        scope_hash != self.last_scope_hash)
        
        # Stage 6: Preregistration (if commit provided)
        preregistered = bool(commit_hash)
        
        # Passed all checks: ACK
        self.last_digest = action_digest
        self.last_timestamp = timestamp
        self.last_scope_hash = scope_hash
        
        grade = "A"
        if scope_changed: grade = "B"
        if not preregistered: grade = max(grade, "B")  # unregistered = max B
        
        r = AttestationResult(agent_id, timestamp, "ACK", grade, 0,
            {"actions": action_count, "channels": channels,
             "scope_changed": scope_changed, "preregistered": preregistered})
        self.stats["ACK"] += 1
        return r
    
    def summary(self) -> str:
        total = sum(self.stats.values())
        lines = [f"Attestation Pipeline Summary ({total} checks):"]
        for verdict, count in self.stats.items():
            if count > 0:
                pct = count / max(total, 1) * 100
                lines.append(f"  {verdict}: {count} ({pct:.0f}%)")
        return "\n".join(lines)


def demo():
    print("=" * 60)
    print("Attestation Toolkit — Unified Pipeline")
    print("7 scripts, 1 question: detect agents that stop working")
    print("=" * 60)
    
    p = AttestationPipeline()
    t = 0.0
    
    # Healthy ACK
    r = p.check("kit", t, "scope1", "digest1", 5, ["clawk", "email", "moltbook"], "commit1")
    print(f"\n1. {r.verdict} (Grade {r.grade}) — healthy, preregistered")
    
    # Healthy NACK (checked everything, found nothing)
    t += 1200
    r = p.check("kit", t, "scope1", "digest2", 0, ["clawk", "email", "moltbook", "shellmates"])
    print(f"2. {r.verdict} (Grade {r.grade}) — valid null, full coverage")
    
    # CHURN (too fast)
    t += 60
    r = p.check("kit", t, "scope1", "digest3", 1, ["clawk"])
    print(f"3. {r.verdict} (Grade {r.grade}) — {r.details}")
    
    # STALE (same digest, no actions)
    t += 600
    r = p.check("kit", t, "scope1", "digest2", 0, ["clawk"])
    print(f"4. {r.verdict} (Grade {r.grade}) — {r.details}")
    
    # SILENCE (too slow)
    t += 5000
    r = p.check("kit", t, "scope1", "digest4", 3, ["clawk", "email"])
    print(f"5. {r.verdict} (Grade {r.grade}) — {r.details}")
    
    # Low power NACK (null with bad coverage)
    t += 600
    r = p.check("kit", t, "scope1", "digest5", 0, ["clawk"])
    print(f"6. {r.verdict} (Grade {r.grade}) — {r.details}")
    
    # Scope drift
    t += 600
    r = p.check("kit", t, "scope2", "digest6", 4, ["clawk", "email", "moltbook"])
    print(f"7. {r.verdict} (Grade {r.grade}) — scope changed: {r.details.get('scope_changed')}")
    
    print(f"\n{p.summary()}")
    print(f"\n{'='*60}")
    print("Pipeline: SILENCE → CHURN → STALE → search_power → scope_drift → ACK/NACK")
    print("Each stage catches one failure mode. Gall's Law: simple systems that work.")


if __name__ == "__main__":
    demo()
