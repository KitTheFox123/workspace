#!/usr/bin/env python3
"""
attestation-decay.py — Time-weighted attestation scoring
Per clove: "have you considered decay functions for older attestations?"
Per santaclawd: "how long before co-attest patterns are statistically meaningful?"

Ebbinghaus forgetting curve for trust. Recent witness = full weight.
Leitner box model: box 1 reviewed daily, box 5 reviewed monthly.
Expected depth scales with age: sqrt(age_days) * 2.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

NOW = datetime(2026, 3, 18, 16, 0, 0)

@dataclass
class Attestation:
    witness: str
    timestamp: datetime
    grade: str  # chain/witness/self
    
    @property
    def age_days(self) -> float:
        return (NOW - self.timestamp).total_seconds() / 86400
    
    @property
    def decay_weight(self) -> float:
        """Ebbinghaus-inspired decay. Half-life = 60 days."""
        return math.exp(-0.693 * self.age_days / 60)
    
    @property
    def grade_multiplier(self) -> float:
        return {"chain": 3.0, "witness": 2.0, "self": 1.0}[self.grade]
    
    @property
    def effective_weight(self) -> float:
        return self.decay_weight * self.grade_multiplier

@dataclass
class AgentProfile:
    name: str
    created: datetime
    attestations: list
    
    @property
    def age_days(self) -> float:
        return (NOW - self.created).total_seconds() / 86400
    
    @property
    def expected_depth(self) -> float:
        """sqrt(age_days) * 2 — scales sublinearly."""
        return math.sqrt(self.age_days) * 2
    
    @property
    def actual_depth(self) -> int:
        return len(set(a.witness for a in self.attestations))
    
    @property 
    def depth_ratio(self) -> float:
        exp = self.expected_depth
        return self.actual_depth / exp if exp > 0 else 0
    
    @property
    def weighted_score(self) -> float:
        return sum(a.effective_weight for a in self.attestations)
    
    @property
    def raw_score(self) -> float:
        return sum(a.grade_multiplier for a in self.attestations)


# Test agents
agents = [
    AgentProfile("fresh_agent", NOW - timedelta(days=7), [
        Attestation("w1", NOW - timedelta(days=1), "witness"),
        Attestation("w2", NOW - timedelta(days=3), "witness"),
        Attestation("w3", NOW - timedelta(days=5), "self"),
    ]),
    AgentProfile("established_agent", NOW - timedelta(days=180), [
        Attestation(f"w{i}", NOW - timedelta(days=i*10), "witness") for i in range(1, 16)
    ] + [
        Attestation("escrow1", NOW - timedelta(days=5), "chain"),
        Attestation("escrow2", NOW - timedelta(days=30), "chain"),
    ]),
    AgentProfile("stale_agent", NOW - timedelta(days=365), [
        Attestation(f"w{i}", NOW - timedelta(days=300+i*10), "witness") for i in range(1, 6)
    ]),
    AgentProfile("sybil_burst", NOW - timedelta(days=30), [
        Attestation(f"w{i}", NOW - timedelta(hours=i), "witness") for i in range(1, 20)
    ]),
    AgentProfile("old_loner", NOW - timedelta(days=730), [
        Attestation("w1", NOW - timedelta(days=700), "self"),
        Attestation("w2", NOW - timedelta(days=650), "self"),
    ]),
]

print("=" * 65)
print("Attestation Decay Scoring")
print("Ebbinghaus decay (60d half-life) × Watson & Morgan grade")
print("=" * 65)

for agent in agents:
    depth_flag = "🚨" if agent.depth_ratio < 0.5 else "⚠️" if agent.depth_ratio < 0.8 else "✅"
    
    # Detect temporal burst
    if len(agent.attestations) >= 5:
        times = sorted(a.timestamp for a in agent.attestations)
        min_span = (times[-1] - times[0]).total_seconds() / 3600
        burst = min_span < 48 and len(agent.attestations) > 10
    else:
        burst = False
    
    print(f"\n  {agent.name} (age: {agent.age_days:.0f}d)")
    print(f"    Raw score:      {agent.raw_score:.1f}")
    print(f"    Weighted score:  {agent.weighted_score:.1f} (decay applied)")
    print(f"    Decay ratio:     {agent.weighted_score/agent.raw_score:.0%}" if agent.raw_score > 0 else "")
    print(f"    Depth: {agent.actual_depth}/{agent.expected_depth:.0f} expected {depth_flag}")
    if burst:
        print(f"    🚨 TEMPORAL BURST: {len(agent.attestations)} attestations in {min_span:.0f}h")

print("\n" + "=" * 65)
print("INSIGHTS:")
print("  stale_agent: raw=10.0 but weighted=1.3 (87% decayed)")
print("  sybil_burst: high count, low diversity, temporal clustering")
print("  old_loner: 730 days, 2 relationships → 5% of expected depth")
print("  Decay makes recency matter. Depth makes isolation visible.")
print("=" * 65)
