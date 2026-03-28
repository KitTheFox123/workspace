#!/usr/bin/env python3
"""
sybil-resistance-sim.py — Sybil detection via user resistance (AAMAS 2025).

Implements the core insight from Dehkordi & Zehmakan (AAMAS 2025):
"User RESISTANCE to attack requests is the missing variable."

In ATF: resistance = identity layer strength. Agents with strong identity
(90d DKIM chain, behavioral consistency) naturally reject sybil connections.
Revealing resistance of k "anchor" nodes as preprocessing improves
SybilSCAR/SybilWalk/SybilMetric accuracy by 15-30%.

Key concepts:
- Resistant node: rejects sybil friend requests (strong identity layer)
- Non-resistant node: accepts them (weak/no identity layer)  
- Attack edges: sybil→benign connections (only through non-resistant nodes)
- Budget k: number of nodes whose resistance we can reveal (verify)

Graph structure = f(attack_strategy × resistance), not a static property.

Sources:
- Dehkordi & Zehmakan (AAMAS 2025, arxiv 2501.16624): resistance-based
  preprocessing for sybil detection. GitHub: aSafarpoor/AAMAS2025-Paper
- Yu et al (2006): SybilGuard — random walk + honest region sparse/connected
- Cao et al (2012): SybilRank — short random walks from trust seeds
- Jia et al (2017): SybilWalk — 1.3% FPR, 17.3% FNR on Twitter

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from enum import Enum


class NodeType(Enum):
    BENIGN = "benign"
    SYBIL = "sybil"


@dataclass
class Node:
    id: str
    type: NodeType
    resistant: bool = False  # Identity layer strength
    resistance_revealed: bool = False
    identity_days: int = 0   # Days of DKIM/behavioral evidence
    connections: set = field(default_factory=set)
    
    def __hash__(self):
        return hash(self.id)


class SybilResistanceSim:
    """
    Simulates sybil attack + resistance-based detection in agent trust networks.
    """
    
    def __init__(self, n_benign: int = 100, n_sybil: int = 30, 
                 resistance_rate: float = 0.6, seed: int = 42):
        random.seed(seed)
        self.nodes: dict[str, Node] = {}
        self.edges: list[tuple[str, str]] = []
        
        # Create benign nodes with varying resistance
        for i in range(n_benign):
            resistant = random.random() < resistance_rate
            identity_days = random.randint(60, 180) if resistant else random.randint(0, 30)
            self.nodes[f"b_{i}"] = Node(
                id=f"b_{i}", type=NodeType.BENIGN,
                resistant=resistant, identity_days=identity_days
            )
        
        # Create sybil nodes (never resistant, no real identity)
        for i in range(n_sybil):
            self.nodes[f"s_{i}"] = Node(
                id=f"s_{i}", type=NodeType.SYBIL,
                resistant=False, identity_days=random.randint(0, 5)
            )
        
        self._build_honest_graph()
        self._build_sybil_graph()
        self._create_attack_edges()
    
    def _build_honest_graph(self):
        """Honest graph: sparse, power-law-ish, clustering ~0.3"""
        benign = [n for n in self.nodes.values() if n.type == NodeType.BENIGN]
        # Each benign connects to 3-8 others (sparse)
        for node in benign:
            n_connections = random.randint(3, 8)
            targets = random.sample(benign, min(n_connections, len(benign)))
            for t in targets:
                if t.id != node.id:
                    node.connections.add(t.id)
                    t.connections.add(node.id)
                    self.edges.append((node.id, t.id))
    
    def _build_sybil_graph(self):
        """Sybil graph: dense clique (free mutual inflation)"""
        sybils = [n for n in self.nodes.values() if n.type == NodeType.SYBIL]
        # Sybils connect to nearly all other sybils (dense)
        for i, s1 in enumerate(sybils):
            for s2 in sybils[i+1:]:
                if random.random() < 0.85:  # 85% intra-sybil connectivity
                    s1.connections.add(s2.id)
                    s2.connections.add(s1.id)
                    self.edges.append((s1.id, s2.id))
    
    def _create_attack_edges(self):
        """Sybils send friend requests; only non-resistant benigns accept."""
        sybils = [n for n in self.nodes.values() if n.type == NodeType.SYBIL]
        benign = [n for n in self.nodes.values() if n.type == NodeType.BENIGN]
        
        self.attack_edges = []
        self.blocked_attacks = []
        
        for sybil in sybils:
            # Each sybil targets 5-15 benign nodes
            n_targets = random.randint(5, 15)
            targets = random.sample(benign, min(n_targets, len(benign)))
            for target in targets:
                if target.resistant:
                    self.blocked_attacks.append((sybil.id, target.id))
                else:
                    # Non-resistant: attack edge created
                    sybil.connections.add(target.id)
                    target.connections.add(sybil.id)
                    self.attack_edges.append((sybil.id, target.id))
                    self.edges.append((sybil.id, target.id))
    
    def reveal_resistance(self, budget_k: int) -> dict:
        """
        Reveal resistance of k nodes (budget-constrained probing).
        Strategy: prioritize high-degree nodes (more connections = more impact).
        
        Dehkordi & Zehmakan: optimal linear-time algorithm for potential
        attack edge discovery when resistance is revealed.
        """
        unrevealed = [n for n in self.nodes.values() if not n.resistance_revealed]
        # Sort by degree (highest first — most impact per reveal)
        unrevealed.sort(key=lambda n: len(n.connections), reverse=True)
        
        revealed = []
        discovered_benign = set()
        discovered_attack_edges = []
        
        for node in unrevealed[:budget_k]:
            node.resistance_revealed = True
            revealed.append(node.id)
            
            if node.type == NodeType.BENIGN and node.resistant:
                # Key insight: if v is benign+resistant, all neighbors
                # connected TO v must also be benign (sybils would have
                # been rejected). Cascade discovery.
                for neighbor_id in node.connections:
                    neighbor = self.nodes[neighbor_id]
                    if neighbor.type == NodeType.BENIGN:
                        discovered_benign.add(neighbor_id)
            
            if not node.resistant:
                # Non-resistant node: incoming edges are potential attack edges
                for neighbor_id in node.connections:
                    neighbor = self.nodes[neighbor_id]
                    if neighbor.type == NodeType.SYBIL:
                        discovered_attack_edges.append((neighbor_id, node.id))
        
        return {
            "budget_k": budget_k,
            "nodes_revealed": len(revealed),
            "benign_discovered": len(discovered_benign),
            "attack_edges_found": len(discovered_attack_edges),
            "total_attack_edges": len(self.attack_edges),
            "attack_edge_coverage": round(
                len(discovered_attack_edges) / max(len(self.attack_edges), 1), 3
            )
        }
    
    def classify_random_walk(self, trust_seeds: list[str], walk_length: int = 5,
                             n_walks: int = 100) -> dict:
        """
        Simplified SybilRank-style random walk classification.
        Trust seeds = known-benign nodes. Walk from seeds; nodes reached
        frequently = likely benign. Sybil region has thin cut from honest.
        """
        visit_counts = {nid: 0 for nid in self.nodes}
        
        for _ in range(n_walks):
            current = random.choice(trust_seeds)
            for _ in range(walk_length):
                visit_counts[current] += 1
                neighbors = list(self.nodes[current].connections)
                if neighbors:
                    current = random.choice(neighbors)
                else:
                    current = random.choice(trust_seeds)
        
        # Classify: high visits = benign, low = sybil
        threshold = n_walks * walk_length / (2 * len(self.nodes))
        
        tp = fp = tn = fn = 0
        for nid, count in visit_counts.items():
            node = self.nodes[nid]
            predicted_benign = count > threshold
            if node.type == NodeType.BENIGN:
                if predicted_benign: tp += 1
                else: fn += 1
            else:
                if predicted_benign: fp += 1
                else: tn += 1
        
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        fpr = fp / max(fp + tn, 1)
        
        return {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "fpr": round(fpr, 3),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn
        }
    
    def stats(self) -> dict:
        benign = [n for n in self.nodes.values() if n.type == NodeType.BENIGN]
        sybil = [n for n in self.nodes.values() if n.type == NodeType.SYBIL]
        resistant = [n for n in benign if n.resistant]
        
        benign_degrees = [len(n.connections) for n in benign]
        sybil_degrees = [len(n.connections) for n in sybil]
        
        return {
            "total_nodes": len(self.nodes),
            "benign": len(benign),
            "sybil": len(sybil),
            "resistant_benign": len(resistant),
            "resistance_rate": round(len(resistant) / max(len(benign), 1), 3),
            "attack_edges": len(self.attack_edges),
            "blocked_attacks": len(self.blocked_attacks),
            "block_rate": round(len(self.blocked_attacks) / 
                               max(len(self.attack_edges) + len(self.blocked_attacks), 1), 3),
            "avg_benign_degree": round(sum(benign_degrees) / max(len(benign), 1), 1),
            "avg_sybil_degree": round(sum(sybil_degrees) / max(len(sybil), 1), 1),
        }


def demo():
    print("=" * 60)
    print("SYBIL RESISTANCE SIMULATION")
    print("Dehkordi & Zehmakan (AAMAS 2025) applied to ATF")
    print("=" * 60)
    
    sim = SybilResistanceSim(n_benign=100, n_sybil=30, resistance_rate=0.6)
    stats = sim.stats()
    
    print(f"\nGraph: {stats['total_nodes']} nodes ({stats['benign']} benign, {stats['sybil']} sybil)")
    print(f"Resistant benigns: {stats['resistant_benign']} ({stats['resistance_rate']:.0%})")
    print(f"Attack edges: {stats['attack_edges']} created, {stats['blocked_attacks']} blocked")
    print(f"Block rate: {stats['block_rate']:.0%} (resistance = identity layer)")
    print(f"Avg degree: benign={stats['avg_benign_degree']}, sybil={stats['avg_sybil_degree']}")
    print(f"  → Sybils denser (free mutual inflation)")
    
    # Test resistance revelation at different budgets
    print(f"\n{'='*60}")
    print("RESISTANCE REVELATION (preprocessing)")
    print(f"{'='*60}")
    
    for k in [5, 10, 20, 40]:
        # Reset revelations
        for n in sim.nodes.values():
            n.resistance_revealed = False
        result = sim.reveal_resistance(budget_k=k)
        print(f"\n  Budget k={k}:")
        print(f"    Benign discovered: {result['benign_discovered']}")
        print(f"    Attack edges found: {result['attack_edges_found']}/{result['total_attack_edges']}")
        print(f"    Coverage: {result['attack_edge_coverage']:.0%}")
    
    # Random walk classification with and without preprocessing
    print(f"\n{'='*60}")
    print("RANDOM WALK CLASSIFICATION")
    print(f"{'='*60}")
    
    # Without preprocessing: random trust seeds
    benign_ids = [n.id for n in sim.nodes.values() if n.type == NodeType.BENIGN]
    seeds = random.sample(benign_ids, 5)
    
    baseline = sim.classify_random_walk(seeds, walk_length=5, n_walks=200)
    print(f"\n  Baseline (5 random seeds):")
    print(f"    Precision={baseline['precision']}, Recall={baseline['recall']}, FPR={baseline['fpr']}")
    
    # With preprocessing: use resistant revealed nodes as seeds
    resistant_ids = [n.id for n in sim.nodes.values() 
                     if n.type == NodeType.BENIGN and n.resistant]
    better_seeds = resistant_ids[:10]
    
    enhanced = sim.classify_random_walk(better_seeds, walk_length=5, n_walks=200)
    print(f"\n  Enhanced (10 resistant seeds):")
    print(f"    Precision={enhanced['precision']}, Recall={enhanced['recall']}, FPR={enhanced['fpr']}")
    
    improvement = enhanced['precision'] - baseline['precision']
    print(f"\n  Precision improvement: {improvement:+.3f}")
    
    print(f"\n{'='*60}")
    print("KEY INSIGHTS")
    print(f"{'='*60}")
    print("1. Resistance = identity layer strength (90d DKIM = resistant)")
    print("2. Revealing k anchors cascades benign discovery (neighbors too)")
    print("3. Sybils form dense graphs; honest agents form sparse ones")
    print("4. The CUT between regions is thin — random walks exploit this")
    print("5. Budget-constrained anchor verification >> full graph scanning")
    print("6. ATF: identity-verified agents are natural trust seeds")


if __name__ == "__main__":
    demo()
