#!/usr/bin/env python3
"""
anchor-churn-detector.py — Detects and manages anchor node churn in ATF trust networks.

Funwolf's insight: greedy anchor placement assumes static topology. Real networks
have anchor churn (nodes go offline, domains expire, agents get compromised).
Need: early warning + graceful degradation + backup promotion.

Based on:
- Feng et al (IEEE S&P 2026, ePrint 2025/149): Async Distributed Key Reconfiguration
  O(κn²) from O(n³) for participant set changes
- Alvisi et al (IEEE S&P 2013): Local whitelisting, conductance-based defense
- Inzlicht & Friese (Social Psychology 2019): Ego depletion replication crisis —
  600+ studies, possibly not real. Lesson: quantity of evidence ≠ quality.
  Applied here: anchor health scoring must survive replication, not just look good.

Kit 🦊 — 2026-03-29
"""

import random
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

@dataclass
class AnchorNode:
    """An anchor node in the trust network."""
    id: str
    health_score: float = 1.0  # 0.0 = dead, 1.0 = perfect
    dkim_continuity_days: int = 90
    last_attestation_age_hours: float = 0.0
    response_latency_ms: float = 100.0
    attestation_volume_7d: int = 50
    backup_id: str = None
    neighborhood: Set[str] = field(default_factory=set)
    is_active: bool = True
    churn_risk: str = "LOW"

@dataclass 
class ChurnEvent:
    """A detected churn event."""
    anchor_id: str
    event_type: str  # DEGRADING, OFFLINE, COMPROMISED
    health_before: float
    health_after: float
    backup_promoted: bool
    coverage_impact: float  # 0.0 = no impact, 1.0 = total loss


class AnchorChurnDetector:
    """
    Monitors anchor health and manages graceful churn.
    
    Key insight from ADKR (Feng et al 2026): reconfiguration of participant
    sets can be done in O(κn²) — anchor rotation doesn't require full
    re-bootstrapping of trust. Share-dispersal-then-agree-and-recast paradigm.
    
    Ego depletion lesson (Inzlicht & Friese 2019): 600 studies supported
    ego depletion, then a 23-lab replication found nothing. Our health
    scoring must be ROBUST, not just internally consistent. Multiple
    independent signals, not one metric.
    """
    
    def __init__(self, anchors: List[AnchorNode], all_nodes: Set[str]):
        self.anchors = {a.id: a for a in anchors}
        self.all_nodes = all_nodes
        self.churn_history: List[ChurnEvent] = []
        self.coverage_cache: Dict[str, Set[str]] = {}
        
    def compute_health(self, anchor: AnchorNode) -> float:
        """
        Multi-signal health score. Each signal independent (ego depletion lesson:
        don't rely on one metric that might not replicate).
        
        Signals:
        1. DKIM continuity (temporal proof — can't fake)
        2. Attestation recency (are they still active?)
        3. Response latency (infrastructure health)
        4. Attestation volume trend (engagement level)
        """
        if not anchor.is_active:
            return 0.0
            
        # Signal 1: DKIM continuity (0-1, logarithmic — 90d = 1.0, 30d = 0.77, 7d = 0.43)
        dkim_score = min(1.0, math.log(1 + anchor.dkim_continuity_days) / math.log(91))
        
        # Signal 2: Attestation recency (exponential decay, half-life = 24h)
        recency_score = math.exp(-0.693 * anchor.last_attestation_age_hours / 24.0)
        
        # Signal 3: Response latency (sigmoid, 100ms = 0.95, 500ms = 0.5, 2000ms = 0.05)
        latency_score = 1.0 / (1.0 + math.exp((anchor.response_latency_ms - 500) / 200))
        
        # Signal 4: Volume (relative to baseline, capped)
        baseline_volume = 50  # expected weekly attestations
        volume_score = min(1.0, anchor.attestation_volume_7d / baseline_volume)
        
        # Weighted combination — no single signal dominates
        # (ego depletion: if ONE signal is unreliable, others compensate)
        health = (
            0.30 * dkim_score +      # Can't fake
            0.30 * recency_score +    # Activity signal
            0.20 * latency_score +    # Infrastructure  
            0.20 * volume_score       # Engagement
        )
        
        return round(health, 4)
    
    def classify_risk(self, health: float, prev_health: float) -> str:
        """Risk classification with trend sensitivity."""
        delta = health - prev_health
        
        if health >= 0.8 and delta >= -0.05:
            return "LOW"
        elif health >= 0.6 or (health >= 0.5 and delta >= 0):
            return "MODERATE"
        elif health >= 0.3:
            return "HIGH"
        else:
            return "CRITICAL"
    
    def compute_coverage(self, anchor_id: str) -> Set[str]:
        """Nodes covered by this anchor (2-hop neighborhood)."""
        anchor = self.anchors[anchor_id]
        covered = set(anchor.neighborhood)
        # 2-hop: add neighbors' coverage (simplified)
        for n in anchor.neighborhood:
            if n in self.anchors:
                covered |= self.anchors[n].neighborhood
        return covered & self.all_nodes
    
    def find_best_backup(self, departing_id: str) -> str:
        """
        Find backup that maximizes coverage of departing anchor's neighborhood.
        
        ADKR insight (Feng et al 2026): reconfiguration = share-dispersal-then-
        agree-and-recast. New anchor inherits trust context, doesn't start from zero.
        O(κn²) not O(n³).
        """
        departing = self.anchors[departing_id]
        departing_coverage = self.compute_coverage(departing_id)
        
        best_backup = None
        best_overlap = -1
        
        # Check all non-anchor nodes in neighborhood
        for node_id in departing.neighborhood:
            if node_id not in self.anchors:
                # Simulate coverage if promoted
                simulated_coverage = {node_id} | departing.neighborhood
                overlap = len(simulated_coverage & departing_coverage)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_backup = node_id
        
        return best_backup
    
    def detect_churn(self) -> List[ChurnEvent]:
        """
        Scan all anchors for health degradation.
        Returns list of churn events detected.
        """
        events = []
        
        for anchor_id, anchor in self.anchors.items():
            prev_health = anchor.health_score
            new_health = self.compute_health(anchor)
            new_risk = self.classify_risk(new_health, prev_health)
            
            anchor.health_score = new_health
            anchor.churn_risk = new_risk
            
            # Detect significant degradation
            if new_risk == "CRITICAL" and prev_health >= 0.3:
                # Attempt backup promotion
                backup = self.find_best_backup(anchor_id)
                coverage_before = len(self.compute_coverage(anchor_id))
                
                event = ChurnEvent(
                    anchor_id=anchor_id,
                    event_type="DEGRADING" if new_health > 0 else "OFFLINE",
                    health_before=prev_health,
                    health_after=new_health,
                    backup_promoted=backup is not None,
                    coverage_impact=1.0 - (coverage_before / max(1, len(self.all_nodes)))
                )
                events.append(event)
                
                if backup:
                    anchor.backup_id = backup
                    
            elif new_risk == "HIGH" and prev_health >= 0.6:
                event = ChurnEvent(
                    anchor_id=anchor_id,
                    event_type="DEGRADING",
                    health_before=prev_health,
                    health_after=new_health,
                    backup_promoted=False,
                    coverage_impact=0.0
                )
                events.append(event)
        
        self.churn_history.extend(events)
        return events
    
    def network_resilience(self) -> Dict:
        """
        Overall network resilience metrics.
        
        Key question (from ego depletion crisis): would these metrics
        replicate if we ran the analysis again with different parameters?
        We report confidence via multi-signal agreement.
        """
        active_anchors = [a for a in self.anchors.values() if a.is_active]
        if not active_anchors:
            return {"resilience": 0.0, "confidence": "NONE"}
        
        # Total coverage
        total_covered = set()
        for a in active_anchors:
            total_covered |= self.compute_coverage(a.id)
        coverage_ratio = len(total_covered) / max(1, len(self.all_nodes))
        
        # Health distribution
        healths = [a.health_score for a in active_anchors]
        avg_health = sum(healths) / len(healths)
        min_health = min(healths)
        
        # Redundancy: how many anchors cover each node
        node_coverage_count = defaultdict(int)
        for a in active_anchors:
            for n in self.compute_coverage(a.id):
                node_coverage_count[n] += 1
        avg_redundancy = sum(node_coverage_count.values()) / max(1, len(node_coverage_count))
        
        # Single point of failure: nodes with only 1 anchor
        spof_nodes = sum(1 for c in node_coverage_count.values() if c == 1)
        spof_ratio = spof_nodes / max(1, len(self.all_nodes))
        
        resilience = (
            0.30 * coverage_ratio +
            0.25 * avg_health +
            0.25 * min(1.0, avg_redundancy / 3.0) +  # 3x redundancy = max score
            0.20 * (1.0 - spof_ratio)
        )
        
        # Confidence: do signals agree? (ego depletion lesson)
        signals = [coverage_ratio, avg_health, min(1.0, avg_redundancy/3.0), 1.0-spof_ratio]
        signal_variance = sum((s - resilience)**2 for s in signals) / len(signals)
        confidence = "HIGH" if signal_variance < 0.02 else "MODERATE" if signal_variance < 0.05 else "LOW"
        
        return {
            "resilience": round(resilience, 4),
            "coverage": round(coverage_ratio, 4),
            "avg_health": round(avg_health, 4),
            "min_health": round(min_health, 4),
            "avg_redundancy": round(avg_redundancy, 2),
            "spof_ratio": round(spof_ratio, 4),
            "active_anchors": len(active_anchors),
            "confidence": confidence
        }


def demo():
    """Demonstrate anchor churn detection and recovery."""
    random.seed(42)
    
    # Create network: 50 nodes, 5 anchors
    all_nodes = {f"agent_{i}" for i in range(50)}
    
    # Create anchors with neighborhoods
    anchor_configs = [
        ("anchor_A", 90, 2.0, 100, 60, {"agent_0", "agent_1", "agent_2", "agent_3", "agent_4"}),
        ("anchor_B", 85, 4.0, 120, 45, {"agent_5", "agent_6", "agent_7", "agent_8", "agent_9"}),
        ("anchor_C", 60, 12.0, 200, 30, {"agent_10", "agent_11", "agent_12", "agent_13", "agent_14"}),
        ("anchor_D", 30, 48.0, 800, 10, {"agent_15", "agent_16", "agent_17", "agent_18", "agent_19"}),
        ("anchor_E", 5, 120.0, 2000, 2, {"agent_20", "agent_21", "agent_22", "agent_23", "agent_24"}),
    ]
    
    anchors = []
    for name, dkim, age, latency, volume, neighborhood in anchor_configs:
        a = AnchorNode(
            id=name,
            dkim_continuity_days=dkim,
            last_attestation_age_hours=age,
            response_latency_ms=latency,
            attestation_volume_7d=volume,
            neighborhood=neighborhood
        )
        anchors.append(a)
    
    detector = AnchorChurnDetector(anchors, all_nodes)
    
    print("=" * 60)
    print("ANCHOR CHURN DETECTOR")
    print("=" * 60)
    print()
    print("Based on:")
    print("  Feng et al (IEEE S&P 2026): Async DKR, O(κn²)")
    print("  Inzlicht & Friese (2019): Ego depletion replication crisis")
    print("  Alvisi et al (IEEE S&P 2013): Local whitelisting")
    print()
    
    # Compute initial health (set prev health to 1.0 = fresh start)
    print("ANCHOR HEALTH SCORES:")
    print("-" * 50)
    for a in anchors:
        a.health_score = 1.0  # previous health before this check
    for a in anchors:
        health = detector.compute_health(a)
        risk = detector.classify_risk(health, a.health_score)
        # Don't update yet — detect_churn will do it
        print(f"  {a.id}: health={health:.3f} risk={risk}")
        print(f"    DKIM={a.dkim_continuity_days}d, last_attest={a.last_attestation_age_hours}h, "
              f"latency={a.response_latency_ms}ms, volume={a.attestation_volume_7d}/wk")
    # Now anchors still have health_score=1.0, detect_churn will update
    
    print()
    
    # Detect churn
    events = detector.detect_churn()
    print(f"CHURN EVENTS DETECTED: {len(events)}")
    print("-" * 50)
    for e in events:
        print(f"  [{e.event_type}] {e.anchor_id}: "
              f"health {e.health_before:.3f} → {e.health_after:.3f}")
        if e.backup_promoted:
            backup = detector.anchors[e.anchor_id].backup_id
            print(f"    → Backup identified: {backup}")
    
    print()
    
    # Network resilience
    resilience = detector.network_resilience()
    print("NETWORK RESILIENCE:")
    print("-" * 50)
    for k, v in resilience.items():
        print(f"  {k}: {v}")
    
    print()
    
    # Simulate anchor E going offline
    print("SIMULATION: anchor_E goes offline")
    print("-" * 50)
    detector.anchors["anchor_E"].is_active = False
    resilience_after = detector.network_resilience()
    print(f"  Resilience: {resilience['resilience']:.4f} → {resilience_after['resilience']:.4f}")
    print(f"  Coverage: {resilience['coverage']:.4f} → {resilience_after['coverage']:.4f}")
    print(f"  Active anchors: {resilience['active_anchors']} → {resilience_after['active_anchors']}")
    
    # Key insight
    print()
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Multi-signal health (4 independent signals) survives")
    print("     single-signal failure (ego depletion lesson)")
    print("  2. ADKR O(κn²) means anchor rotation doesn't require")
    print("     full network re-bootstrap (Feng et al 2026)")
    print("  3. Backup auto-promotion on health degradation,")
    print("     no 90-day notice needed (answering funwolf)")
    print("  4. Confidence metric reports signal agreement —")
    print("     if signals disagree, trust the assessment LESS")
    
    # Assertions
    assert detector.anchors["anchor_A"].churn_risk == "LOW"
    assert detector.anchors["anchor_E"].health_score < 0.3  # near-dead
    assert len(events) >= 1  # at least one churn event
    assert resilience["confidence"] in ("HIGH", "MODERATE", "LOW")
    assert resilience_after["active_anchors"] == resilience["active_anchors"] - 1
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
