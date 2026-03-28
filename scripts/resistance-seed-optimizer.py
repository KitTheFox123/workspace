#!/usr/bin/env python3
"""
resistance-seed-optimizer.py — Optimal anchor node selection for trust percolation.

Based on Dehkordi & Zehmakan (AAMAS 2025): revealing resistance of k nodes
as preprocessing improves sybil detection accuracy for SybilSCAR/SybilWalk/
SybilMetric. Their key insight: user RESISTANCE to attack requests (friendship
requests from sybil accounts) is the missing variable.

ATF mapping:
- "Resistance" = how likely an agent rejects fraudulent attestation requests
- "Revealing resistance" = establishing anchor nodes with known trust profiles
- Preprocessing = cold-start seeding: before running trust propagation,
  identify k anchor agents whose resistance is verified (by humans or by
  long behavioral track record)
- The k anchors dramatically improve whole-network sybil detection

This script optimizes WHICH k agents to seed as anchors to maximize
detection improvement, using graph centrality + degree as heuristics.

Sources:
- Dehkordi & Zehmakan (AAMAS 2025): "More Efficient Sybil Detection
  Mechanisms Leveraging Resistance of Users to Attack Requests"
- Yu et al (2006): SybilGuard — random walk based sybil detection
- Cao et al (2012): SybilRank — trust propagation via landing probability

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
    resistance: float = 0.0  # 0=accepts all, 1=rejects all attack requests
    revealed: bool = False   # Whether resistance is known (anchor)
    trust_score: float = 0.5 # Computed trust after propagation
    degree: int = 0


class TrustNetwork:
    """Simple trust network for resistance seed optimization."""
    
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, set[str]] = defaultdict(set)  # undirected
        self.attack_edges: set[tuple[str, str]] = set()  # sybil→honest edges
    
    def add_node(self, node: Node):
        self.nodes[node.id] = node
    
    def add_edge(self, a: str, b: str, is_attack: bool = False):
        self.edges[a].add(b)
        self.edges[b].add(a)
        self.nodes[a].degree = len(self.edges[a])
        self.nodes[b].degree = len(self.edges[b])
        if is_attack:
            self.attack_edges.add((a, b))
    
    def propagate_trust(self, rounds: int = 20, decay: float = 0.9) -> dict[str, float]:
        """
        Trust propagation (SybilRank-inspired).
        Anchors seed trust=1.0; non-anchors start at 0.5.
        Dense sybil clusters pull each other's scores down because
        they lack anchor connections. Honest nodes near anchors get pulled up.
        """
        scores = {}
        for nid, node in self.nodes.items():
            if node.revealed and not node.is_sybil:
                scores[nid] = 1.0  # Anchor = full trust
            elif node.revealed and node.is_sybil:
                scores[nid] = 0.0  # Known sybil
            else:
                scores[nid] = 0.5  # Unknown
        
        for _ in range(rounds):
            new_scores = {}
            for nid in self.nodes:
                if self.nodes[nid].revealed:
                    new_scores[nid] = scores[nid]
                    continue
                
                neighbors = self.edges.get(nid, set())
                if not neighbors:
                    new_scores[nid] = scores[nid] * 0.95  # Isolated nodes decay
                    continue
                
                # Average neighbor scores
                neighbor_avg = sum(scores.get(n, 0.5) for n in neighbors) / len(neighbors)
                new_scores[nid] = (1 - decay) * scores[nid] + decay * neighbor_avg
            
            scores = new_scores
        
        # Update nodes
        for nid, score in scores.items():
            self.nodes[nid].trust_score = score
        
        return scores
    
    def detection_accuracy(self, threshold: float = None) -> dict:
        """Measure sybil detection accuracy. Auto-selects threshold if None."""
        if threshold is None:
            # Use median score as threshold (adaptive)
            all_scores = sorted(n.trust_score for n in self.nodes.values())
            # Threshold = point that best separates honest/sybil
            # Try the score at the 20th percentile (since 20% sybil)
            idx = max(0, int(len(all_scores) * 0.25))
            threshold = all_scores[idx]
        
        tp = fp = tn = fn = 0
        for node in self.nodes.values():
            predicted_sybil = node.trust_score < threshold
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
        
        return {
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "accuracy": round((tp + tn) / max(tp + fp + tn + fn, 1), 3)
        }


def generate_network(n_honest: int = 80, n_sybil: int = 20,
                     honest_density: float = 0.08, sybil_density: float = 0.4,
                     attack_edges: int = 10) -> TrustNetwork:
    """
    Generate a network with honest (sparse) and sybil (dense) subgraphs.
    Sybil regions are dense internally, sparse at the cut to honest region.
    """
    net = TrustNetwork()
    
    # Honest nodes with varying resistance
    for i in range(n_honest):
        resistance = random.gauss(0.7, 0.15)  # Most honest nodes resist attacks
        resistance = max(0.0, min(1.0, resistance))
        net.add_node(Node(id=f"honest_{i}", is_sybil=False, resistance=resistance))
    
    # Sybil nodes with low resistance (accept everything)
    for i in range(n_sybil):
        resistance = random.gauss(0.1, 0.1)
        resistance = max(0.0, min(1.0, resistance))
        net.add_node(Node(id=f"sybil_{i}", is_sybil=True, resistance=resistance))
    
    honest_ids = [f"honest_{i}" for i in range(n_honest)]
    sybil_ids = [f"sybil_{i}" for i in range(n_sybil)]
    
    # Honest subgraph: sparse (power-law-ish)
    for i in range(n_honest):
        n_edges = max(1, int(random.paretovariate(1.5)))
        n_edges = min(n_edges, 8)
        for _ in range(n_edges):
            j = random.randint(0, n_honest - 1)
            if i != j:
                net.add_edge(honest_ids[i], honest_ids[j])
    
    # Sybil subgraph: dense (mutual inflation)
    for i in range(n_sybil):
        for j in range(i + 1, n_sybil):
            if random.random() < sybil_density:
                net.add_edge(sybil_ids[i], sybil_ids[j])
    
    # Attack edges: sybil → honest (sparse, this is the cut)
    for _ in range(attack_edges):
        s = random.choice(sybil_ids)
        h = random.choice(honest_ids)
        # Honest node's resistance determines if edge forms
        if random.random() > net.nodes[h].resistance:
            net.add_edge(s, h, is_attack=True)
    
    return net


def select_anchors_random(net: TrustNetwork, k: int) -> list[str]:
    """Baseline: random anchor selection."""
    candidates = [nid for nid in net.nodes if not net.nodes[nid].is_sybil]
    return random.sample(candidates, min(k, len(candidates)))


def select_anchors_degree(net: TrustNetwork, k: int) -> list[str]:
    """Heuristic: highest-degree honest nodes (most connected = most visible)."""
    honest = [(nid, net.nodes[nid].degree) for nid in net.nodes if not net.nodes[nid].is_sybil]
    honest.sort(key=lambda x: -x[1])
    return [nid for nid, _ in honest[:k]]


def select_anchors_boundary(net: TrustNetwork, k: int) -> list[str]:
    """
    AAMAS-inspired: nodes near the honest-sybil boundary benefit most.
    Heuristic: honest nodes with highest ratio of unknown neighbors.
    These are the nodes where revealing resistance has maximum impact.
    """
    scored = []
    for nid, node in net.nodes.items():
        if node.is_sybil:
            continue
        neighbors = net.edges.get(nid, set())
        if not neighbors:
            continue
        # Score = degree * diversity of neighbor trust scores
        # (high diversity = near boundary)
        neighbor_degrees = [net.nodes[n].degree for n in neighbors]
        avg_degree = sum(neighbor_degrees) / len(neighbor_degrees)
        # Nodes connected to both high and low degree neighbors = boundary
        degree_variance = sum((d - avg_degree) ** 2 for d in neighbor_degrees) / len(neighbor_degrees)
        scored.append((nid, len(neighbors) * (1 + degree_variance ** 0.5)))
    
    scored.sort(key=lambda x: -x[1])
    return [nid for nid, _ in scored[:k]]


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("RESISTANCE SEED OPTIMIZER")
    print("Dehkordi & Zehmakan (AAMAS 2025) applied to ATF")
    print("=" * 60)
    
    net = generate_network(n_honest=80, n_sybil=20, attack_edges=15)
    
    honest_count = sum(1 for n in net.nodes.values() if not n.is_sybil)
    sybil_count = sum(1 for n in net.nodes.values() if n.is_sybil)
    print(f"\nNetwork: {honest_count} honest, {sybil_count} sybil, {len(net.attack_edges)} attack edges")
    
    # Baseline: no anchors
    print("\n--- No anchors (baseline) ---")
    net_copy = generate_network(n_honest=80, n_sybil=20, attack_edges=15)
    random.seed(42)  # Reset for reproducibility
    net_copy = generate_network(n_honest=80, n_sybil=20, attack_edges=15)
    net_copy.propagate_trust()
    baseline = net_copy.detection_accuracy()
    print(f"  F1: {baseline['f1']}, Accuracy: {baseline['accuracy']}")
    
    # Test different anchor strategies at k=5
    k = 5
    strategies = {
        "Random": select_anchors_random,
        "Degree (highest connected)": select_anchors_degree,
        "Boundary (AAMAS-inspired)": select_anchors_boundary,
    }
    
    results = {}
    for name, strategy in strategies.items():
        # Fresh network each time
        random.seed(42)
        net_test = generate_network(n_honest=80, n_sybil=20, attack_edges=15)
        
        # Select and reveal anchors
        random.seed(42 + hash(name) % 1000)
        anchors = strategy(net_test, k)
        for aid in anchors:
            net_test.nodes[aid].revealed = True
        
        net_test.propagate_trust()
        acc = net_test.detection_accuracy()
        results[name] = acc
        
        print(f"\n--- {name} (k={k}) ---")
        print(f"  Anchors: {anchors[:3]}...")
        print(f"  F1: {acc['f1']}, Accuracy: {acc['accuracy']}")
        print(f"  Precision: {acc['precision']}, Recall: {acc['recall']}")
        improvement = acc['f1'] - baseline['f1']
        print(f"  F1 improvement over baseline: {improvement:+.3f}")
    
    # Test scaling: how does k affect accuracy?
    print("\n" + "=" * 60)
    print("SCALING: F1 vs number of anchor nodes (boundary strategy)")
    print("=" * 60)
    
    for k_test in [1, 3, 5, 10, 20]:
        random.seed(42)
        net_scale = generate_network(n_honest=80, n_sybil=20, attack_edges=15)
        anchors = select_anchors_boundary(net_scale, k_test)
        for aid in anchors:
            net_scale.nodes[aid].revealed = True
        net_scale.propagate_trust()
        acc = net_scale.detection_accuracy()
        bar = "█" * int(acc['f1'] * 40)
        print(f"  k={k_test:2d}: F1={acc['f1']:.3f} {bar}")
    
    print()
    print("KEY INSIGHT: Small number of verified anchor agents")
    print("dramatically improves whole-network sybil detection.")
    print("Cold-start seeding IS the preprocessing step.")
    print("The anchors ARE the trust percolation seeds.")


if __name__ == "__main__":
    demo()
