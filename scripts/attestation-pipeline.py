#!/usr/bin/env python3
"""
attestation-pipeline.py — Unified attestation pipeline

Ties together today's 7 scripts into one pipeline:
1. preregistration-commit-reveal.py → declare scope
2. signed-null-observation.py → observe (including null)
3. evidence-gated-attestation.py → validate evidence
4. heartbeat-payload-verifier.py → check observable state
5. dead-mans-switch.py → detect silence
6. vigilance-decrement-sim.py → monitor rotation
7. This script → orchestrate all 6

Vocabulary:
  ACK  = signed positive observation
  NACK = signed null observation (search power > threshold)
  SILENCE = dead man's switch alarm
  CHURN = windowed watchdog rejection (too fast)
  STALE = evidence gate rejection (same digest)

From one question: "how do you detect an agent that stops doing things?"
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class PipelineConfig:
    agent_id: str
    channels: list
    min_interval: float = 300.0     # anti-churn
    max_interval: float = 3600.0    # dead man's switch
    min_search_power: float = 0.5   # Altman 1995
    evidence_required: bool = True  # evidence-gated

@dataclass
class Beat:
    timestamp: float
    scope_hash: str
    action_digest: str
    action_count: int
    channels_active: list
    observations: int = 0  # channels checked (even if null)

@dataclass
class PipelineResult:
    verdict: str      # ACK, NACK, SILENCE, CHURN, STALE, INVALID
    grade: str        # A-F
    checks: list = field(default_factory=list)
    details: str = ""

class AttestationPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.last_beat: Optional[Beat] = None
        self.last_digest: str = ""
        self.commit_hash: str = ""
        self.consecutive_stale = 0
        self.consecutive_churn = 0
        self.stats = {"ACK": 0, "NACK": 0, "SILENCE": 0, "CHURN": 0, "STALE": 0, "INVALID": 0}
    
    def commit(self, channels: list) -> str:
        """Step 1: Preregister scope"""
        payload = json.dumps({"agent": self.config.agent_id, "channels": sorted(channels)}, sort_keys=True)
        self.commit_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return self.commit_hash
    
    def submit(self, beat: Beat) -> PipelineResult:
        """Steps 2-6: Full pipeline"""
        checks = []
        
        # Dead man's switch (Step 5)
        if self.last_beat:
            elapsed = beat.timestamp - self.last_beat.timestamp
            if elapsed > self.config.max_interval:
                self.stats["SILENCE"] += 1
                return PipelineResult("SILENCE", "F", 
                    [{"check": "dead_mans_switch", "elapsed": elapsed}],
                    f"Silent for {elapsed:.0f}s (max {self.config.max_interval:.0f}s)")
            
            # Churn check (windowed watchdog)
            if elapsed < self.config.min_interval:
                self.consecutive_churn += 1
                self.stats["CHURN"] += 1
                return PipelineResult("CHURN", "D",
                    [{"check": "windowed_watchdog", "elapsed": elapsed}],
                    f"Too fast ({elapsed:.0f}s < {self.config.min_interval:.0f}s)")
        self.consecutive_churn = 0
        
        # Evidence gate (Step 3)
        if beat.action_digest == self.last_digest and self.last_digest:
            self.consecutive_stale += 1
            self.stats["STALE"] += 1
            grade = "C" if self.consecutive_stale < 3 else "F"
            self.last_beat = beat
            return PipelineResult("STALE", grade,
                [{"check": "evidence_gate", "stale_count": self.consecutive_stale}],
                f"Same digest. Stale streak: {self.consecutive_stale}")
        self.consecutive_stale = 0
        
        # Search power for null observations (Altman 1995)
        coverage = len(set(beat.channels_active) & set(self.config.channels)) / max(len(self.config.channels), 1)
        
        if beat.action_count == 0:
            if coverage >= self.config.min_search_power and beat.observations > 0:
                # Valid NACK
                self.last_digest = beat.action_digest
                self.last_beat = beat
                self.stats["NACK"] += 1
                return PipelineResult("NACK", "B",
                    [{"check": "search_power", "coverage": coverage}],
                    f"Valid null. Checked {coverage:.0%} of scope.")
            else:
                self.stats["INVALID"] += 1
                self.last_beat = beat
                return PipelineResult("INVALID", "D",
                    [{"check": "search_power", "coverage": coverage}],
                    f"Low-power null ({coverage:.0%} < {self.config.min_search_power:.0%})")
        
        # Valid ACK
        self.last_digest = beat.action_digest
        self.last_beat = beat
        self.stats["ACK"] += 1
        grade = "A" if coverage >= 0.8 else "B" if coverage >= 0.5 else "C"
        return PipelineResult("ACK", grade,
            [{"check": "full_pipeline", "coverage": coverage, "actions": beat.action_count}],
            f"Valid. {beat.action_count} actions, {coverage:.0%} coverage.")
    
    def summary(self) -> str:
        total = sum(self.stats.values())
        lines = [f"Pipeline: {total} beats processed"]
        for k, v in self.stats.items():
            if v > 0:
                lines.append(f"  {k}: {v} ({v/max(total,1):.0%})")
        return "\n".join(lines)


def demo():
    print("=" * 60)
    print("Attestation Pipeline")
    print("From: 'how do you detect an agent that stops doing things?'")
    print("=" * 60)
    
    config = PipelineConfig(
        agent_id="kit_fox",
        channels=["moltbook", "clawk", "email", "shellmates"]
    )
    pipe = AttestationPipeline(config)
    
    t = 0.0
    scenarios = [
        ("Healthy ACK", Beat(t, "s1", "d1", 5, ["moltbook", "clawk", "email", "shellmates"], 4)),
        ("Healthy ACK", Beat(t + 1200, "s1", "d2", 3, ["clawk", "email", "moltbook"], 3)),
        ("Valid NACK", Beat(t + 2400, "s1", "d3", 0, ["moltbook", "clawk", "email", "shellmates"], 4)),
        ("Stale", Beat(t + 3600, "s1", "d3", 0, ["clawk"], 1)),
        ("Churn", Beat(t + 3660, "s1", "d4", 1, ["clawk"], 1)),
        ("Healthy after churn", Beat(t + 4800, "s1", "d5", 2, ["clawk", "email"], 2)),
        ("SILENCE", Beat(t + 10000, "s1", "d6", 1, ["clawk"], 1)),
        ("Low-power null", Beat(t + 11200, "s1", "d7", 0, ["clawk"], 1)),
    ]
    
    for label, beat in scenarios:
        r = pipe.submit(beat)
        print(f"\n{label}: {r.verdict} (Grade {r.grade}) — {r.details}")
    
    print(f"\n{'='*60}")
    print(pipe.summary())
    print(f"\nVocabulary: ACK/NACK/SILENCE/CHURN/STALE")
    print(f"7 scripts → 1 pipeline. SMTP had 3 of these in 1982.")


if __name__ == "__main__":
    demo()
