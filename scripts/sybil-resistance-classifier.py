#!/usr/bin/env python3
"""
sybil-resistance-classifier.py — Classifies agents by sybil resistance using
the Dehkordi & Zehmakan (AAMAS 2025) resistance framework.

Key insight from paper: User RESISTANCE to attack requests (sybil friend
requests) is the missing variable in sybil detection. Resistant nodes reject
sybil connections; non-resistant accept them. The resulting graph structure
is a function of attack strategy × resistance.

ATF mapping:
- Resistance = identity layer strength
- Agents with DKIM history = high resistance (provable temporal existence)
- Cold-start agents = unknown resistance (need probing)
- Sybils = zero resistance by construction (they connect freely to each other)

Three resistance signals (passive, active, temporal):
1. PASSIVE: DKIM trail length, inbox age, behavioral consistency
2. ACTIVE: Rejected bad attestation requests, declined low-quality connections
3. TEMPORAL: Rate of new connections (sybils connect fast, honest agents slow)

Kit 🦊 — 2026-03-28
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class ResistanceLevel(Enum):
    HIGH = "HIGH"           # Provably resistant (long history, rejections)
    MEDIUM = "MEDIUM"       # Some evidence of resistance
    LOW = "LOW"             # Little resistance evidence (cold-start)
    UNKNOWN = "UNKNOWN"     # No data
    SYBIL_PATTERN = "SYBIL" # Anti-resistance pattern (connects too freely)


@dataclass
class AgentSignals:
    agent_id: str
    # Passive signals
    inbox_age_days: int = 0
    dkim_chain_days: int = 0
    total_interactions: int = 0
    # Active signals
    rejected_attestations: int = 0
    accepted_attestations: int = 0
    rejected_connections: int = 0
    accepted_connections: int = 0
    # Temporal signals
    connections_last_7d: int = 0
    connections_last_30d: int = 0
    connections_last_90d: int = 0
    # Graph signals (from Dehkordi & Zehmakan)
    degree: int = 0              # Number of connections
    clustering_coefficient: float = 0.0  # How connected are neighbors
    avg_neighbor_degree: float = 0.0


@dataclass
class ResistanceProfile:
    agent_id: str
    level: ResistanceLevel
    score: float  # 0-1
    passive_score: float = 0.0
    active_score: float = 0.0
    temporal_score: float = 0.0
    graph_score: float = 0.0
    flags: list[str] = field(default_factory=list)
    recommendation: str = ""


class SybilResistanceClassifier:
    """
    Classifies agent sybil resistance using multi-signal analysis.
    
    Based on Dehkordi & Zehmakan (AAMAS 2025): revealing resistance of
    a SUBSET of users maximizes discovered benigns + attack edges.
    This classifier identifies which agents to "reveal" first.
    """
    
    # Thresholds from empirical observation
    SYBIL_CONNECTION_RATE = 5.0   # connections/day = suspicious
    HIGH_REJECTION_RATIO = 0.3    # 30%+ rejections = discerning
    MIN_DKIM_DAYS = 30            # Minimum for passive resistance
    HEALTHY_CLUSTERING = 0.3      # Honest networks cluster ~0.3
    SYBIL_CLUSTERING = 0.8        # Sybil rings = very dense
    
    def classify(self, signals: AgentSignals) -> ResistanceProfile:
        passive = self._score_passive(signals)
        active = self._score_active(signals)
        temporal = self._score_temporal(signals)
        graph = self._score_graph(signals)
        
        # Weighted combination
        total = (passive * 0.25 + active * 0.25 + 
                 temporal * 0.25 + graph * 0.25)
        
        flags = []
        
        # Sybil pattern detection
        if self._is_sybil_pattern(signals, temporal, graph):
            level = ResistanceLevel.SYBIL_PATTERN
            flags.append("SYBIL_PATTERN: rapid connections + dense clustering")
        elif total >= 0.7:
            level = ResistanceLevel.HIGH
        elif total >= 0.4:
            level = ResistanceLevel.MEDIUM
        elif total >= 0.1:
            level = ResistanceLevel.LOW
        else:
            level = ResistanceLevel.UNKNOWN
        
        # Additional flags
        if signals.connections_last_7d > 20:
            flags.append(f"RAPID_GROWTH: {signals.connections_last_7d} connections in 7d")
        if signals.rejected_attestations == 0 and signals.accepted_attestations > 5:
            flags.append("ZERO_REJECTIONS: accepts all attestation requests")
        if signals.clustering_coefficient > self.SYBIL_CLUSTERING:
            flags.append(f"DENSE_CLUSTER: clustering={signals.clustering_coefficient:.2f}")
        
        recommendation = self._recommend(level, signals, flags)
        
        return ResistanceProfile(
            agent_id=signals.agent_id,
            level=level,
            score=round(total, 3),
            passive_score=round(passive, 3),
            active_score=round(active, 3),
            temporal_score=round(temporal, 3),
            graph_score=round(graph, 3),
            flags=flags,
            recommendation=recommendation
        )
    
    def _score_passive(self, s: AgentSignals) -> float:
        """DKIM chain + inbox age + interaction volume."""
        score = 0.0
        if s.dkim_chain_days >= self.MIN_DKIM_DAYS:
            score += 0.5 * min(1.0, s.dkim_chain_days / 90)
        if s.inbox_age_days >= 30:
            score += 0.3 * min(1.0, s.inbox_age_days / 180)
        if s.total_interactions >= 10:
            score += 0.2 * min(1.0, s.total_interactions / 100)
        return min(1.0, score)
    
    def _score_active(self, s: AgentSignals) -> float:
        """Rejection ratio = discernment."""
        total_att = s.rejected_attestations + s.accepted_attestations
        total_conn = s.rejected_connections + s.accepted_connections
        
        score = 0.0
        if total_att > 0:
            rejection_ratio = s.rejected_attestations / total_att
            if rejection_ratio >= self.HIGH_REJECTION_RATIO:
                score += 0.5
            elif rejection_ratio > 0:
                score += 0.3
        
        if total_conn > 0:
            conn_rejection = s.rejected_connections / total_conn
            if conn_rejection >= self.HIGH_REJECTION_RATIO:
                score += 0.5
            elif conn_rejection > 0:
                score += 0.3
        
        return min(1.0, score)
    
    def _score_temporal(self, s: AgentSignals) -> float:
        """Slow, steady growth = honest. Rapid bursts = sybil."""
        if s.connections_last_90d == 0:
            return 0.0
        
        # Connection rate (lower = more resistant)
        daily_rate_7d = s.connections_last_7d / 7 if s.connections_last_7d else 0
        daily_rate_30d = s.connections_last_30d / 30 if s.connections_last_30d else 0
        
        score = 1.0
        if daily_rate_7d > self.SYBIL_CONNECTION_RATE:
            score -= 0.5
        if daily_rate_7d > daily_rate_30d * 3:  # Acceleration = suspicious
            score -= 0.3
        
        # Steady growth bonus
        if s.connections_last_90d > 0:
            evenness = min(s.connections_last_30d, s.connections_last_90d / 3) / max(s.connections_last_30d, s.connections_last_90d / 3 + 0.001)
            score = max(0, score) + 0.2 * evenness
        
        return max(0.0, min(1.0, score))
    
    def _score_graph(self, s: AgentSignals) -> float:
        """Graph structure signals (Dehkordi & Zehmakan)."""
        score = 0.5  # Neutral start
        
        # Healthy clustering ~0.3, sybil ~0.8+
        if 0.1 <= s.clustering_coefficient <= 0.5:
            score += 0.3  # Healthy range
        elif s.clustering_coefficient > self.SYBIL_CLUSTERING:
            score -= 0.4  # Dense ring
        
        # Degree: honest agents have moderate degree
        if 3 <= s.degree <= 50:
            score += 0.2
        elif s.degree > 100:
            score -= 0.2  # Hyper-connected = suspicious
        
        return max(0.0, min(1.0, score))
    
    def _is_sybil_pattern(self, s: AgentSignals, temporal: float, graph: float) -> bool:
        """Combined sybil indicators."""
        sybil_signals = 0
        if temporal < 0.3:
            sybil_signals += 1
        if graph < 0.3:
            sybil_signals += 1
        if s.clustering_coefficient > self.SYBIL_CLUSTERING:
            sybil_signals += 1
        if s.connections_last_7d / max(s.connections_last_90d, 1) > 0.5:
            sybil_signals += 1
        if s.rejected_attestations == 0 and s.accepted_attestations > 10:
            sybil_signals += 1
        return sybil_signals >= 3
    
    def _recommend(self, level: ResistanceLevel, s: AgentSignals, flags: list) -> str:
        if level == ResistanceLevel.SYBIL_PATTERN:
            return "INVESTIGATE: Multiple sybil indicators. Quarantine from attestation chains."
        elif level == ResistanceLevel.HIGH:
            return "TRUSTED SEED: Good candidate for anchor node in sybil detection."
        elif level == ResistanceLevel.MEDIUM:
            return "MONITOR: Growing trust. Increase probing frequency."
        elif level == ResistanceLevel.LOW:
            return "COLD-START: Need more data. Request witnessed attestation."
        else:
            return "UNKNOWN: No resistance data. Treat as unverified."


def demo():
    c = SybilResistanceClassifier()
    
    scenarios = [
        ("Kit (established agent)", AgentSignals(
            agent_id="kit_fox", inbox_age_days=55, dkim_chain_days=55,
            total_interactions=200, rejected_attestations=3, accepted_attestations=8,
            rejected_connections=5, accepted_connections=15,
            connections_last_7d=2, connections_last_30d=8, connections_last_90d=20,
            degree=15, clustering_coefficient=0.28, avg_neighbor_degree=12
        )),
        ("Sybil ring member", AgentSignals(
            agent_id="sybil_001", inbox_age_days=3, dkim_chain_days=3,
            total_interactions=50, rejected_attestations=0, accepted_attestations=30,
            rejected_connections=0, accepted_connections=40,
            connections_last_7d=35, connections_last_30d=40, connections_last_90d=40,
            degree=38, clustering_coefficient=0.92, avg_neighbor_degree=35
        )),
        ("Cold-start agent", AgentSignals(
            agent_id="newbie", inbox_age_days=5, dkim_chain_days=5,
            total_interactions=3, rejected_attestations=0, accepted_attestations=1,
            rejected_connections=0, accepted_connections=2,
            connections_last_7d=2, connections_last_30d=2, connections_last_90d=2,
            degree=2, clustering_coefficient=0.0, avg_neighbor_degree=8
        )),
        ("Veteran loner (selective)", AgentSignals(
            agent_id="hermit", inbox_age_days=180, dkim_chain_days=150,
            total_interactions=50, rejected_attestations=15, accepted_attestations=5,
            rejected_connections=20, accepted_connections=3,
            connections_last_7d=0, connections_last_30d=1, connections_last_90d=3,
            degree=3, clustering_coefficient=0.15, avg_neighbor_degree=6
        )),
    ]
    
    for name, signals in scenarios:
        profile = c.classify(signals)
        print(f"{'=' * 50}")
        print(f"{name}")
        print(f"{'=' * 50}")
        print(f"  Level: {profile.level.value}")
        print(f"  Score: {profile.score}")
        print(f"  Passive: {profile.passive_score} | Active: {profile.active_score} | "
              f"Temporal: {profile.temporal_score} | Graph: {profile.graph_score}")
        if profile.flags:
            for f in profile.flags:
                print(f"  ⚠ {f}")
        print(f"  → {profile.recommendation}")
        print()
    
    # Assertions
    results = {name: c.classify(signals) for name, signals in scenarios}
    assert results["Kit (established agent)"].level == ResistanceLevel.HIGH
    assert results["Sybil ring member"].level == ResistanceLevel.SYBIL_PATTERN
    assert results["Cold-start agent"].level in [ResistanceLevel.LOW, ResistanceLevel.MEDIUM]
    assert results["Veteran loner (selective)"].level == ResistanceLevel.HIGH
    
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
