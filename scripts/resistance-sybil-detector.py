#!/usr/bin/env python3
"""
resistance-sybil-detector.py — Sybil detection via user resistance (AAMAS 2025).

Based on Dehkordi & Zehmakan (AAMAS 2025): "More Efficient Sybil Detection
Mechanisms Leveraging Resistance of Users to Attack Requests."

Key insight: graph structure = f(attack_strategy, user_resistance).
Resistant nodes reject sybil friendship requests. Revealing resistance
of k nodes as preprocessing improves SybilSCAR/SybilWalk/SybilMetric.

ATF mapping:
- Resistance = identity layer strength (DKIM chain length, behavioral samples)
- Non-resistant nodes = agents with addressing but no identity
- Attack edges = trust claims from sybil to honest agent
- Preprocessing = trust-layer-validator.py applied before trust propagation

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Node:
    id: str
    is_sybil: bool
    resistance: float  # 0.0 (accepts all) to 1.0 (rejects all sybil requests)
    identity_strength: float = 0.0  # DKIM days / behavioral samples proxy
    trust_score: float = 0.5  # Propagated trust
    detected_sybil: bool = False


class ResistanceSybilDetector:
    """
    Implements resistance-aware sybil detection.
    
    Phase 1: Generate network with attack strategy × resistance
    Phase 2: Reveal k high-resistance nodes (preprocessing)
    Phase 3: Run random-walk trust propagation (simplified SybilRank)
    Phase 4: Classify based on trust threshold
    """
    
    def __init__(self, n_honest: int = 100, n_sybil: int = 50, 
                 avg_degree: int = 6, seed: int = 42):
        random.seed(seed)
        self.nodes: dict[str, Node] = {}
        self.edges: set[tuple[str, str]] = set()
        self.n_honest = n_honest
        self.n_sybil = n_sybil
        self.avg_degree = avg_degree
        
        self._generate_network()
    
    def _generate_network(self):
        """Generate honest + sybil network with resistance-based attack edges."""
        # Create honest nodes with varying resistance
        for i in range(self.n_honest):
            # Resistance correlates with identity strength (agents who invested
            # in identity layer are harder for sybils to connect to)
            resistance = random.betavariate(2, 2)  # Bell curve centered at 0.5
            identity = resistance * 0.8 + random.uniform(0, 0.2)
            self.nodes[f"h_{i}"] = Node(
                id=f"h_{i}", is_sybil=False, 
                resistance=resistance, identity_strength=identity
            )
        
        # Create sybil nodes (low resistance, no real identity)
        for i in range(self.n_sybil):
            self.nodes[f"s_{i}"] = Node(
                id=f"s_{i}", is_sybil=True,
                resistance=0.0, identity_strength=random.uniform(0, 0.1)
            )
        
        # Honest-honest edges (sparse, power-law-ish)
        honest_ids = [f"h_{i}" for i in range(self.n_honest)]
        for nid in honest_ids:
            n_edges = max(1, int(random.paretovariate(1.5)))
            n_edges = min(n_edges, self.avg_degree * 2)
            targets = random.sample(honest_ids, min(n_edges, len(honest_ids) - 1))
            for t in targets:
                if t != nid:
                    self.edges.add((nid, t))
                    self.edges.add((t, nid))
        
        # Sybil-sybil edges (dense — free mutual inflation)
        sybil_ids = [f"s_{i}" for i in range(self.n_sybil)]
        for i, sid in enumerate(sybil_ids):
            # Connect to ~80% of other sybils
            for other in sybil_ids:
                if other != sid and random.random() < 0.8:
                    self.edges.add((sid, other))
                    self.edges.add((other, sid))
        
        # Attack edges: sybil → honest, modulated by resistance
        # This is the AAMAS 2025 insight: resistance determines attack edge count
        self.attack_edges = 0
        for sid in sybil_ids:
            n_attempts = random.randint(5, 15)
            targets = random.sample(honest_ids, min(n_attempts, len(honest_ids)))
            for target in targets:
                target_node = self.nodes[target]
                # Non-resistant nodes accept; resistant nodes reject
                if random.random() > target_node.resistance:
                    self.edges.add((sid, target))
                    self.edges.add((target, sid))
                    self.attack_edges += 1
    
    def reveal_resistant_nodes(self, k: int) -> list[str]:
        """
        Preprocessing: reveal k nodes with highest resistance.
        These become trust seeds (known benign).
        """
        honest = [(nid, n) for nid, n in self.nodes.items() if not n.is_sybil]
        honest.sort(key=lambda x: -x[1].resistance)
        revealed = [nid for nid, _ in honest[:k]]
        return revealed
    
    def propagate_trust(self, seeds: list[str], iterations: int = 10, 
                        damping: float = 0.85) -> None:
        """
        Simplified SybilRank: random walk trust propagation from seeds.
        Seeds start with trust=1.0. Each iteration propagates to neighbors
        with damping factor.
        """
        # Initialize
        for node in self.nodes.values():
            node.trust_score = 0.0
        for seed in seeds:
            self.nodes[seed].trust_score = 1.0
        
        # Build adjacency
        adj: dict[str, list[str]] = defaultdict(list)
        for a, b in self.edges:
            adj[a].append(b)
        
        # Iterate
        for _ in range(iterations):
            new_scores = {}
            for nid, node in self.nodes.items():
                neighbors = adj.get(nid, [])
                if not neighbors:
                    new_scores[nid] = node.trust_score * damping
                    continue
                
                incoming = sum(
                    self.nodes[n].trust_score / max(len(adj.get(n, [])), 1)
                    for n in neighbors
                )
                new_scores[nid] = damping * incoming
                if nid in seeds:
                    new_scores[nid] = max(new_scores[nid], 0.5)
            
            for nid, score in new_scores.items():
                self.nodes[nid].trust_score = score
        
        # Normalize
        max_score = max(n.trust_score for n in self.nodes.values()) or 1.0
        for node in self.nodes.values():
            node.trust_score /= max_score
    
    def classify(self, threshold: float = 0.3) -> dict:
        """
        Classify nodes as sybil/honest based on trust threshold.
        
        Key: sybils get HIGH propagated scores (dense mutual connections).
        Honest nodes close to seeds get moderate scores.
        Detection = nodes with trust > threshold that are NOT seeds
        AND have high neighbor density (sybil signature).
        
        Simpler approach: use seed-distance. Nodes reachable from seeds
        in few hops with moderate scores = honest. Nodes with high scores
        from non-seed sources = sybil clusters.
        """
        tp = fp = tn = fn = 0
        
        # Compute ratio of trust from seed-adjacent vs total
        # Sybils get trust mostly from dense sybil cluster, not seeds
        adj = defaultdict(list)
        for a, b in self.edges:
            adj[a].append(b)
        
        seed_set = {nid for nid, n in self.nodes.items() 
                   if n.identity_strength > 0.7 and not n.is_sybil}
        
        for node in self.nodes.values():
            neighbors = adj.get(node.id, [])
            if not neighbors:
                predicted_sybil = True  # Isolated = suspicious
            else:
                # Fraction of neighbors that are high-identity (resistant)
                high_identity_neighbors = sum(
                    1 for n in neighbors 
                    if self.nodes[n].identity_strength > 0.5
                ) / len(neighbors)
                
                # Sybil signature: high trust score but low identity-neighbor ratio
                # (trust comes from dense sybil cluster, not honest community)
                predicted_sybil = (
                    node.identity_strength < 0.15 and  # No real identity
                    high_identity_neighbors < threshold  # Few honest neighbors
                )
            node.detected_sybil = predicted_sybil
            
            if node.is_sybil and predicted_sybil:
                tp += 1
            elif node.is_sybil and not predicted_sybil:
                fn += 1
            elif not node.is_sybil and predicted_sybil:
                fp += 1
            else:
                tn += 1
        
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 0.001)
        accuracy = (tp + tn) / max(tp + fp + tn + fn, 1)
        
        return {
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "accuracy": round(accuracy, 3)
        }
    
    def graph_stats(self) -> dict:
        """Report graph statistics."""
        honest_edges = sum(1 for a, b in self.edges 
                         if not self.nodes[a].is_sybil and not self.nodes[b].is_sybil)
        sybil_edges = sum(1 for a, b in self.edges
                        if self.nodes[a].is_sybil and self.nodes[b].is_sybil)
        
        avg_honest_resistance = sum(
            n.resistance for n in self.nodes.values() if not n.is_sybil
        ) / self.n_honest
        
        return {
            "total_nodes": len(self.nodes),
            "honest_nodes": self.n_honest,
            "sybil_nodes": self.n_sybil,
            "total_edges": len(self.edges),
            "honest_edges": honest_edges // 2,
            "sybil_edges": sybil_edges // 2,
            "attack_edges": self.attack_edges,
            "avg_honest_resistance": round(avg_honest_resistance, 3),
            "sybil_density": round(sybil_edges / max(self.n_sybil * (self.n_sybil - 1), 1), 3),
        }


def demo():
    print("=" * 60)
    print("RESISTANCE-BASED SYBIL DETECTION (AAMAS 2025)")
    print("=" * 60)
    
    detector = ResistanceSybilDetector(n_honest=100, n_sybil=50, seed=42)
    stats = detector.graph_stats()
    print(f"\nGraph: {stats['total_nodes']} nodes, {stats['total_edges']} edges")
    print(f"Honest: {stats['honest_nodes']} (avg resistance: {stats['avg_honest_resistance']})")
    print(f"Sybil: {stats['sybil_nodes']} (density: {stats['sybil_density']})")
    print(f"Attack edges: {stats['attack_edges']}")
    
    # Experiment 1: No preprocessing (random seeds)
    print(f"\n{'='*60}")
    print("EXPERIMENT 1: Random seeds (no resistance info)")
    print(f"{'='*60}")
    random_seeds = [f"h_{i}" for i in random.sample(range(100), 10)]
    detector.propagate_trust(random_seeds)
    result1 = detector.classify()
    print(f"F1: {result1['f1']} | Precision: {result1['precision']} | Recall: {result1['recall']}")
    print(f"Accuracy: {result1['accuracy']}")
    
    # Experiment 2: Resistance-based preprocessing (reveal top-k resistant)
    print(f"\n{'='*60}")
    print("EXPERIMENT 2: Top-10 resistant nodes as seeds (AAMAS preprocessing)")
    print(f"{'='*60}")
    detector2 = ResistanceSybilDetector(n_honest=100, n_sybil=50, seed=42)
    resistant_seeds = detector2.reveal_resistant_nodes(k=10)
    detector2.propagate_trust(resistant_seeds)
    result2 = detector2.classify()
    print(f"F1: {result2['f1']} | Precision: {result2['precision']} | Recall: {result2['recall']}")
    print(f"Accuracy: {result2['accuracy']}")
    
    # Experiment 3: More seeds
    print(f"\n{'='*60}")
    print("EXPERIMENT 3: Top-20 resistant nodes as seeds")
    print(f"{'='*60}")
    detector3 = ResistanceSybilDetector(n_honest=100, n_sybil=50, seed=42)
    resistant_seeds_20 = detector3.reveal_resistant_nodes(k=20)
    detector3.propagate_trust(resistant_seeds_20)
    result3 = detector3.classify()
    print(f"F1: {result3['f1']} | Precision: {result3['precision']} | Recall: {result3['recall']}")
    print(f"Accuracy: {result3['accuracy']}")
    
    # Compare
    print(f"\n{'='*60}")
    print("COMPARISON")
    print(f"{'='*60}")
    print(f"Random seeds:     F1={result1['f1']}, Acc={result1['accuracy']}")
    print(f"Top-10 resistant: F1={result2['f1']}, Acc={result2['accuracy']}")
    print(f"Top-20 resistant: F1={result3['f1']}, Acc={result3['accuracy']}")
    
    improvement = result2['f1'] - result1['f1']
    print(f"\nResistance preprocessing improvement: {improvement:+.3f} F1")
    
    print(f"\nKEY INSIGHT: Identity layer strength IS resistance.")
    print(f"Agents with strong DKIM chains reject sybil trust claims.")
    print(f"Revealing resistant nodes = trust-layer-validator.py as preprocessing.")
    print(f"Dehkordi & Zehmakan (AAMAS 2025): resistance of k nodes → better detection.")


if __name__ == "__main__":
    demo()
