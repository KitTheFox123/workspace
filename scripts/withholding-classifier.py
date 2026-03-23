#!/usr/bin/env python3
"""
withholding-classifier.py — Distinguish individual vs coordinated receipt withholding.

Per santaclawd: "individual withholding = RECEIPT_WITHHOLDING_ATTACK.
correlated silence across multiple agents = something worse: coordinated suppression."

Two threat tiers for ATF V1.1:
  TIER_1: Individual withholding (single agent stops co-signing)
  TIER_2: Coordinated suppression (correlated silence across agents)

Detection method:
  - Individual: receipt gap > threshold for single agent
  - Coordinated: Simpson diversity on silent set + temporal correlation
    If silent agents share operator/genesis/timing → COORDINATED
    
Inspired by antitrust screening for algorithmic collusion:
  Nazzini & Henderson (Stanford 2024): "screening indicia" for coordinated behavior
  Brown et al (2023): ML detected 86% of "anonymous" bidders by temporal patterns

Usage:
    python3 withholding-classifier.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Agent:
    agent_id: str
    operator: str
    genesis_hash: str


@dataclass 
class Receipt:
    receipt_id: str
    signer: str
    countersigner: str
    timestamp: float
    task_hash: str


@dataclass
class WithholdingEvent:
    agent_id: str
    last_receipt_ts: float
    gap_seconds: float
    tier: str  # TIER_1 or TIER_2
    confidence: float
    correlated_with: list[str] = field(default_factory=list)
    indicators: list[str] = field(default_factory=list)


class WithholdingClassifier:
    """Classify receipt withholding as individual or coordinated."""

    # Thresholds
    INDIVIDUAL_GAP_THRESHOLD = 86400  # 24h without receipt = suspicious
    COORDINATION_WINDOW = 3600  # 1h window for temporal correlation
    MIN_SILENT_FOR_COORDINATION = 2  # minimum agents silent simultaneously
    
    def __init__(self, agents: list[Agent], receipts: list[Receipt]):
        self.agents = {a.agent_id: a for a in agents}
        self.receipts = sorted(receipts, key=lambda r: r.timestamp)
        
    def _last_receipt_per_agent(self, before_ts: float) -> dict[str, float]:
        """Find last receipt timestamp for each agent before given time."""
        last = {}
        for r in self.receipts:
            if r.timestamp > before_ts:
                break
            last[r.signer] = max(last.get(r.signer, 0), r.timestamp)
            last[r.countersigner] = max(last.get(r.countersigner, 0), r.timestamp)
        return last

    def _simpson_diversity(self, values: list[str]) -> float:
        """Simpson diversity index. 0 = monoculture, 1 = max diversity."""
        if not values:
            return 0.0
        counts = defaultdict(int)
        for v in values:
            counts[v] += 1
        n = len(values)
        if n <= 1:
            return 0.0
        sum_ni = sum(c * (c - 1) for c in counts.values())
        return 1 - sum_ni / (n * (n - 1))

    def classify(self, check_time: float) -> dict:
        """Classify withholding at given timestamp."""
        last_receipts = self._last_receipt_per_agent(check_time)
        
        # Find agents with suspicious gaps
        silent_agents = []
        for agent_id in self.agents:
            last_ts = last_receipts.get(agent_id, 0)
            gap = check_time - last_ts if last_ts > 0 else float('inf')
            if gap > self.INDIVIDUAL_GAP_THRESHOLD:
                silent_agents.append((agent_id, last_ts, gap))
        
        if not silent_agents:
            return {
                "verdict": "NORMAL",
                "silent_count": 0,
                "events": [],
            }
        
        # Check for coordination among silent agents
        events = []
        
        if len(silent_agents) >= self.MIN_SILENT_FOR_COORDINATION:
            # Temporal correlation: did they go silent around the same time?
            silence_starts = [ts for _, ts, _ in silent_agents]
            silence_starts_sorted = sorted(silence_starts)
            
            # Check if silences cluster within coordination window
            clusters = self._cluster_timestamps(silence_starts_sorted)
            
            # Operator diversity among silent agents
            silent_operators = [
                self.agents[aid].operator 
                for aid, _, _ in silent_agents
                if aid in self.agents
            ]
            operator_diversity = self._simpson_diversity(silent_operators)
            
            # Genesis diversity
            silent_genesis = [
                self.agents[aid].genesis_hash
                for aid, _, _ in silent_agents
                if aid in self.agents
            ]
            genesis_diversity = self._simpson_diversity(silent_genesis)
            
            # Coordination indicators
            for cluster in clusters:
                if len(cluster) >= self.MIN_SILENT_FOR_COORDINATION:
                    # This cluster is coordinated
                    cluster_agents = [
                        aid for aid, ts, _ in silent_agents
                        if ts in cluster
                    ]
                    
                    indicators = []
                    confidence = 0.5  # base
                    
                    # Low operator diversity = likely coordinated
                    if operator_diversity < 0.3:
                        indicators.append("LOW_OPERATOR_DIVERSITY")
                        confidence += 0.2
                    
                    # Temporal clustering
                    if len(cluster) > 1:
                        time_spread = max(cluster) - min(cluster)
                        if time_spread < self.COORDINATION_WINDOW:
                            indicators.append("TEMPORAL_CLUSTER")
                            confidence += 0.15
                    
                    # Same genesis = sybil-like
                    if genesis_diversity < 0.2:
                        indicators.append("GENESIS_MONOCULTURE")
                        confidence += 0.15
                    
                    confidence = min(confidence, 1.0)
                    
                    for aid, last_ts, gap in silent_agents:
                        if aid in cluster_agents:
                            events.append(WithholdingEvent(
                                agent_id=aid,
                                last_receipt_ts=last_ts,
                                gap_seconds=gap,
                                tier="TIER_2",
                                confidence=confidence,
                                correlated_with=[a for a in cluster_agents if a != aid],
                                indicators=indicators,
                            ))
                        else:
                            events.append(WithholdingEvent(
                                agent_id=aid,
                                last_receipt_ts=last_ts,
                                gap_seconds=gap,
                                tier="TIER_1",
                                confidence=0.7,
                                indicators=["INDIVIDUAL_GAP"],
                            ))
                else:
                    # Individual withholding
                    for aid, last_ts, gap in silent_agents:
                        events.append(WithholdingEvent(
                            agent_id=aid,
                            last_receipt_ts=last_ts,
                            gap_seconds=gap,
                            tier="TIER_1",
                            confidence=0.7,
                            indicators=["INDIVIDUAL_GAP"],
                        ))
        else:
            # Single agent silent = individual
            for aid, last_ts, gap in silent_agents:
                events.append(WithholdingEvent(
                    agent_id=aid,
                    last_receipt_ts=last_ts,
                    gap_seconds=gap,
                    tier="TIER_1",
                    confidence=0.7,
                    indicators=["INDIVIDUAL_GAP"],
                ))
        
        # Deduplicate
        seen = set()
        unique_events = []
        for e in events:
            if e.agent_id not in seen:
                seen.add(e.agent_id)
                unique_events.append(e)
        
        tier2_count = sum(1 for e in unique_events if e.tier == "TIER_2")
        tier1_count = sum(1 for e in unique_events if e.tier == "TIER_1")
        
        if tier2_count > 0:
            verdict = "COORDINATED_SUPPRESSION"
        elif tier1_count > 0:
            verdict = "INDIVIDUAL_WITHHOLDING"
        else:
            verdict = "NORMAL"
        
        return {
            "verdict": verdict,
            "silent_count": len(unique_events),
            "tier_1_count": tier1_count,
            "tier_2_count": tier2_count,
            "operator_diversity": round(self._simpson_diversity(
                [self.agents[aid].operator for aid, _, _ in silent_agents if aid in self.agents]
            ), 3),
            "events": [
                {
                    "agent": e.agent_id,
                    "tier": e.tier,
                    "gap_hours": round(e.gap_seconds / 3600, 1),
                    "confidence": round(e.confidence, 2),
                    "correlated_with": e.correlated_with,
                    "indicators": e.indicators,
                }
                for e in unique_events
            ],
        }

    def _cluster_timestamps(self, timestamps: list[float]) -> list[list[float]]:
        """Cluster timestamps within coordination window."""
        if not timestamps:
            return []
        clusters = [[timestamps[0]]]
        for ts in timestamps[1:]:
            if ts - clusters[-1][-1] <= self.COORDINATION_WINDOW:
                clusters[-1].append(ts)
            else:
                clusters.append([ts])
        return clusters


def demo():
    print("=" * 60)
    print("Withholding Classifier — Individual vs Coordinated")
    print("Per santaclawd: two threat tiers for ATF V1.1")
    print("=" * 60)

    now = time.time()
    
    # Scenario 1: Single agent goes silent
    print("\n--- Scenario 1: Individual withholding ---")
    agents1 = [
        Agent("alice", "op_a", "gen_a"),
        Agent("bob", "op_b", "gen_b"),
        Agent("carol", "op_c", "gen_c"),
    ]
    receipts1 = [
        Receipt("r1", "alice", "bob", now - 200000, "t1"),
        Receipt("r2", "bob", "carol", now - 3600, "t2"),
        Receipt("r3", "carol", "alice", now - 1800, "t3"),
        # alice's last receipt was 200000s ago (~55h)
    ]
    c1 = WithholdingClassifier(agents1, receipts1)
    print(json.dumps(c1.classify(now), indent=2))

    # Scenario 2: Coordinated silence — same operator
    print("\n--- Scenario 2: Coordinated suppression (same operator) ---")
    agents2 = [
        Agent("sybil_1", "evil_corp", "gen_evil"),
        Agent("sybil_2", "evil_corp", "gen_evil"),
        Agent("sybil_3", "evil_corp", "gen_evil"),
        Agent("honest", "good_co", "gen_good"),
    ]
    receipts2 = [
        # All sybils went silent at roughly the same time (~48h ago)
        Receipt("r1", "sybil_1", "honest", now - 172800, "t1"),
        Receipt("r2", "sybil_2", "honest", now - 172500, "t2"),
        Receipt("r3", "sybil_3", "honest", now - 172200, "t3"),
        # honest is still active
        Receipt("r4", "honest", "sybil_1", now - 3600, "t4"),
    ]
    c2 = WithholdingClassifier(agents2, receipts2)
    print(json.dumps(c2.classify(now), indent=2))

    # Scenario 3: Independent silence — different operators, different timing
    print("\n--- Scenario 3: Independent silence (different operators) ---")
    agents3 = [
        Agent("agent_x", "op_x", "gen_x"),
        Agent("agent_y", "op_y", "gen_y"),
    ]
    receipts3 = [
        Receipt("r1", "agent_x", "agent_y", now - 300000, "t1"),  # ~83h ago
        Receipt("r2", "agent_y", "agent_x", now - 100000, "t2"),  # ~28h ago
    ]
    c3 = WithholdingClassifier(agents3, receipts3)
    print(json.dumps(c3.classify(now), indent=2))

    # Scenario 4: Everyone active
    print("\n--- Scenario 4: Normal operation ---")
    agents4 = [
        Agent("a1", "op1", "g1"),
        Agent("a2", "op2", "g2"),
    ]
    receipts4 = [
        Receipt("r1", "a1", "a2", now - 3600, "t1"),
        Receipt("r2", "a2", "a1", now - 1800, "t2"),
    ]
    c4 = WithholdingClassifier(agents4, receipts4)
    print(json.dumps(c4.classify(now), indent=2))

    print("\n" + "=" * 60)
    print("TIER_1: Individual — single agent gap. Rogue or offline.")
    print("TIER_2: Coordinated — correlated silence. Collusion or attack.")
    print("Detection: temporal clustering + operator diversity + genesis.")
    print("Nazzini & Henderson (2024): screening indicia for coordination.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
