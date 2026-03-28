#!/usr/bin/env python3
"""
resistance-sybil-classifier.py — Sybil detection via user resistance modeling.

Based on Dehkordi & Zehmakan (AAMAS 2025): "More Efficient Sybil Detection
Mechanisms Leveraging Resistance of Users to Attack Requests."

Key insight: sybils send friendship/attestation requests freely. Resistant
nodes (established agents with strong identity layers) reject them. Non-resistant
nodes accept. The resulting graph structure reveals sybil regions.

ATF mapping:
- Resistance = identity layer strength (DKIM chain days, behavioral samples)
- Attack edge = attestation request from unknown agent to established one
- Sybil region = cluster of agents that only attest each other
- Benign region = sparse trust graph with diverse cross-connections

Three attack strategies modeled:
1. RANDOM — sybils send requests uniformly (easiest to detect)
2. TARGETED — sybils target low-resistance nodes (harder)
3. ADAPTIVE — sybils adjust strategy based on acceptance rate (hardest)

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict


@dataclass
class Node:
    id: str
    is_sybil: bool = False
    resistance: float = 0.5  # 0 = accepts everything, 1 = rejects everything
    identity_strength: float = 0.0  # Proxy for identity layer
    connections: set = field(default_factory=set)
    
    def accepts_request(self, from_node: 'Node') -> bool:
        """
        Resistance-based acceptance (Dehkordi & Zehmakan 2025).
        Probability of acceptance = 1 - resistance (for sybil requests).
        Honest requests from agents with strong identity get bonus.
        """
        if from_node.is_sybil:
            return random.random() > self.resistance
        else:
            # Honest agents get identity-based bonus
            bonus = from_node.identity_strength * 0.3
            return random.random() > max(0, self.resistance - bonus)


@dataclass
class GraphMetrics:
    """Metrics for classifying sybil vs honest regions."""
    internal_density: float = 0.0  # Edges within cluster / possible edges
    conductance: float = 0.0       # Cut edges / min(vol_S, vol_complement)
    avg_resistance: float = 0.0
    avg_identity: float = 0.0
    cluster_size: int = 0


class ResistanceSybilClassifier:
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.nodes: dict[str, Node] = {}
        self.edges: set[tuple[str, str]] = set()
    
    def add_honest_agent(self, agent_id: str, resistance: float, identity: float):
        self.nodes[agent_id] = Node(
            id=agent_id, is_sybil=False,
            resistance=resistance, identity_strength=identity
        )
    
    def add_sybil_agent(self, agent_id: str):
        """Sybils have low resistance (accept each other) and no real identity."""
        self.nodes[agent_id] = Node(
            id=agent_id, is_sybil=True,
            resistance=0.05,  # Accept almost anything
            identity_strength=0.0
        )
    
    def simulate_attack(self, strategy: str = "random", rounds: int = 50):
        """
        Simulate sybil attack with given strategy.
        Returns attack statistics.
        """
        sybils = [n for n in self.nodes.values() if n.is_sybil]
        honest = [n for n in self.nodes.values() if not n.is_sybil]
        
        # Phase 1: Sybils connect to each other (free, always accepted)
        for i, s1 in enumerate(sybils):
            for s2 in sybils[i+1:]:
                self._add_edge(s1.id, s2.id)
                s1.connections.add(s2.id)
                s2.connections.add(s1.id)
        
        # Phase 2: Honest agents form sparse trust connections
        for _ in range(len(honest) * 2):
            a, b = random.sample(honest, 2)
            if b.accepts_request(a):
                self._add_edge(a.id, b.id)
                a.connections.add(b.id)
                b.connections.add(a.id)
        
        # Phase 3: Sybils try to connect to honest agents
        stats = {"requests": 0, "accepted": 0, "rejected": 0}
        
        for _ in range(rounds):
            for sybil in sybils:
                if strategy == "random":
                    target = random.choice(honest)
                elif strategy == "targeted":
                    # Target lowest resistance honest agents
                    target = min(honest, key=lambda n: n.resistance)
                elif strategy == "adaptive":
                    # Try random first, learn who accepts
                    candidates = [h for h in honest if h.id not in sybil.connections]
                    if not candidates:
                        continue
                    # Prefer nodes that previously accepted (not modeled here, use random)
                    target = random.choice(candidates)
                else:
                    target = random.choice(honest)
                
                stats["requests"] += 1
                if target.accepts_request(sybil):
                    self._add_edge(sybil.id, target.id)
                    sybil.connections.add(target.id)
                    target.connections.add(sybil.id)
                    stats["accepted"] += 1
                else:
                    stats["rejected"] += 1
        
        stats["acceptance_rate"] = stats["accepted"] / max(stats["requests"], 1)
        return stats
    
    def _add_edge(self, a: str, b: str):
        edge = tuple(sorted([a, b]))
        self.edges.add(edge)
    
    def compute_cluster_metrics(self, cluster_ids: list[str]) -> GraphMetrics:
        """Compute density and conductance for a cluster."""
        cluster_set = set(cluster_ids)
        n = len(cluster_set)
        
        if n <= 1:
            return GraphMetrics(cluster_size=n)
        
        # Internal edges
        internal = sum(1 for a, b in self.edges if a in cluster_set and b in cluster_set)
        possible = n * (n - 1) / 2
        density = internal / possible if possible > 0 else 0
        
        # Cut edges (crossing cluster boundary)
        cut = sum(1 for a, b in self.edges 
                  if (a in cluster_set) != (b in cluster_set))
        
        # Volume = sum of degrees for cluster nodes
        vol_cluster = sum(len(self.nodes[nid].connections) for nid in cluster_ids if nid in self.nodes)
        vol_complement = sum(len(n.connections) for n in self.nodes.values() if n.id not in cluster_set)
        min_vol = min(vol_cluster, vol_complement)
        
        conductance = cut / min_vol if min_vol > 0 else 1.0
        
        cluster_nodes = [self.nodes[nid] for nid in cluster_ids if nid in self.nodes]
        avg_res = sum(n.resistance for n in cluster_nodes) / len(cluster_nodes) if cluster_nodes else 0
        avg_id = sum(n.identity_strength for n in cluster_nodes) / len(cluster_nodes) if cluster_nodes else 0
        
        return GraphMetrics(
            internal_density=round(density, 4),
            conductance=round(conductance, 4),
            avg_resistance=round(avg_res, 4),
            avg_identity=round(avg_id, 4),
            cluster_size=n
        )
    
    def classify(self, threshold_density: float = 0.5, threshold_conductance: float = 0.2) -> dict:
        """
        Classify nodes as sybil or honest based on cluster properties.
        
        Sybil signal: high internal density + low conductance (dense internally,
        few connections to outside). SybilGuard (Yu 2006) + SybilRank (Cao 2012).
        """
        sybil_ids = [n.id for n in self.nodes.values() if n.is_sybil]
        honest_ids = [n.id for n in self.nodes.values() if not n.is_sybil]
        
        sybil_metrics = self.compute_cluster_metrics(sybil_ids)
        honest_metrics = self.compute_cluster_metrics(honest_ids)
        
        # Classification: high density + low conductance = sybil
        sybil_detected = (sybil_metrics.internal_density > threshold_density 
                         and sybil_metrics.conductance < threshold_conductance)
        
        return {
            "sybil_cluster": {
                "detected_as_sybil": sybil_detected,
                "metrics": {
                    "density": sybil_metrics.internal_density,
                    "conductance": sybil_metrics.conductance,
                    "avg_resistance": sybil_metrics.avg_resistance,
                    "avg_identity": sybil_metrics.avg_identity,
                    "size": sybil_metrics.cluster_size
                }
            },
            "honest_cluster": {
                "metrics": {
                    "density": honest_metrics.internal_density,
                    "conductance": honest_metrics.conductance,
                    "avg_resistance": honest_metrics.avg_resistance,
                    "avg_identity": honest_metrics.avg_identity,
                    "size": honest_metrics.cluster_size
                }
            },
            "detection_rule": f"density > {threshold_density} AND conductance < {threshold_conductance}"
        }


def demo():
    strategies = ["random", "targeted", "adaptive"]
    
    for strategy in strategies:
        print("=" * 60)
        print(f"ATTACK STRATEGY: {strategy.upper()}")
        print("=" * 60)
        
        clf = ResistanceSybilClassifier(seed=42)
        
        # 20 honest agents with varying resistance
        for i in range(20):
            resistance = 0.3 + random.random() * 0.6  # 0.3-0.9
            identity = 0.2 + random.random() * 0.8      # 0.2-1.0
            clf.add_honest_agent(f"honest_{i}", resistance, identity)
        
        # 8 sybil agents
        for i in range(8):
            clf.add_sybil_agent(f"sybil_{i}")
        
        # Simulate
        stats = clf.simulate_attack(strategy=strategy, rounds=30)
        print(f"Attack stats: {stats['requests']} requests, "
              f"{stats['accepted']} accepted ({stats['acceptance_rate']:.1%})")
        
        # Classify
        result = clf.classify()
        print(f"\nSybil cluster:")
        print(f"  Density: {result['sybil_cluster']['metrics']['density']}")
        print(f"  Conductance: {result['sybil_cluster']['metrics']['conductance']}")
        print(f"  Detected: {result['sybil_cluster']['detected_as_sybil']}")
        print(f"\nHonest cluster:")
        print(f"  Density: {result['honest_cluster']['metrics']['density']}")
        print(f"  Conductance: {result['honest_cluster']['metrics']['conductance']}")
        print()
    
    # Key insight demonstration
    print("=" * 60)
    print("KEY INSIGHT: Resistance ↔ Identity Layer Strength")
    print("=" * 60)
    print()
    print("High resistance (strong identity) → rejects sybil requests")
    print("Low resistance (weak identity) → accepts sybil requests")
    print("Sybil clusters: dense internal, sparse external (low conductance)")
    print("Honest clusters: sparse internal, diverse connections")
    print()
    print("ATF mapping:")
    print("  resistance = identity_layer_strength (DKIM days, behavioral samples)")
    print("  attack_edge = attestation request from unknown to established")
    print("  SybilGuard random walk = trust propagation bounded by conductance")
    print()
    print("Dehkordi & Zehmakan (AAMAS 2025): resistance is the missing variable")
    print("that determines graph structure. Not homophily — resistance × strategy.")


if __name__ == "__main__":
    demo()
