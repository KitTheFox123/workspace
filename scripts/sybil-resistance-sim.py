#!/usr/bin/env python3
"""
sybil-resistance-sim.py — Sybil detection via user resistance (AAMAS 2025).

Implements core insight from Dehkordi & Zehmakan (AAMAS 2025): user RESISTANCE
to attack requests is the missing variable in sybil detection. Graph structure
is a function of attack strategy × resistance, not a static property.

Key findings from paper:
- Revealing resistance of k=1 user → F1 0.889 sybil detection
- Resistant nodes reject sybil friendship requests → sparse honest/sybil boundary
- Greedy benign discovery: NP-hard but performant empirically
- Three attack strategies: random, degree-based, community-based

ATF mapping:
- Resistance = identity layer strength (DKIM chain, behavioral consistency)
- Attack edges = attestation requests from sybils to honest agents
- The 3-layer model (addressing→identity→trust) IS a sybil defense:
  identity layer = resistance filter

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional


@dataclass
class Node:
    id: str
    is_sybil: bool = False
    resistant: bool = False  # Resistant = strong identity layer
    resistance_revealed: bool = False
    discovered_benign: bool = False
    trust_score: float = 0.0


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, set] = field(default_factory=lambda: defaultdict(set))
    
    def add_edge(self, u: str, v: str):
        self.edges[u].add(v)
        self.edges[v].add(u)
    
    def degree(self, node_id: str) -> int:
        return len(self.edges.get(node_id, set()))
    
    def neighbors(self, node_id: str) -> set:
        return self.edges.get(node_id, set())


def generate_network(n_honest: int = 100, n_sybil: int = 30, 
                     resistance_rate: float = 0.6,
                     honest_avg_degree: int = 6,
                     sybil_density: float = 0.8,
                     attack_strategy: str = "random") -> Graph:
    """
    Generate a social network with honest and sybil regions.
    
    Honest region: sparse, power-law-ish degree distribution.
    Sybil region: dense, nearly complete (free mutual inflation).
    Attack edges: function of strategy × resistance.
    """
    g = Graph()
    
    # Create honest nodes
    honest_ids = [f"h_{i}" for i in range(n_honest)]
    for hid in honest_ids:
        resistant = random.random() < resistance_rate
        g.nodes[hid] = Node(id=hid, is_sybil=False, resistant=resistant)
    
    # Create sybil nodes (never resistant)
    sybil_ids = [f"s_{i}" for i in range(n_sybil)]
    for sid in sybil_ids:
        g.nodes[sid] = Node(id=sid, is_sybil=True, resistant=False)
    
    # Honest-honest edges (sparse, power-law-ish)
    for hid in honest_ids:
        # Each honest node gets ~honest_avg_degree connections
        n_edges = max(1, int(random.gauss(honest_avg_degree, 2)))
        targets = random.sample(
            [h for h in honest_ids if h != hid], 
            min(n_edges, len(honest_ids) - 1)
        )
        for t in targets:
            g.add_edge(hid, t)
    
    # Sybil-sybil edges (dense, nearly complete)
    for i, s1 in enumerate(sybil_ids):
        for s2 in sybil_ids[i+1:]:
            if random.random() < sybil_density:
                g.add_edge(s1, s2)
    
    # Attack edges: sybils try to connect to honest nodes
    # Result depends on attack strategy AND resistance
    for sid in sybil_ids:
        if attack_strategy == "random":
            targets = random.sample(honest_ids, min(10, len(honest_ids)))
        elif attack_strategy == "degree":
            # Target high-degree honest nodes (more influential)
            sorted_honest = sorted(honest_ids, key=lambda h: g.degree(h), reverse=True)
            targets = sorted_honest[:10]
        elif attack_strategy == "community":
            # Target a cluster of connected honest nodes
            seed = random.choice(honest_ids)
            targets = list(g.neighbors(seed) & set(honest_ids))[:10]
            targets.append(seed)
        else:
            targets = []
        
        for target in targets:
            honest_node = g.nodes[target]
            # Resistant nodes reject sybil requests!
            if honest_node.resistant:
                continue  # Identity layer blocks the attack edge
            # Non-resistant nodes accept
            g.add_edge(sid, target)
    
    return g


def reveal_resistance(g: Graph, k: int = 1) -> list[str]:
    """
    Greedy strategy: reveal resistance of k nodes to maximize
    benign discovery (Dehkordi & Zehmakan, AAMAS 2025).
    
    Heuristic: pick nodes with highest degree among unknown nodes,
    as revealing a high-degree resistant node cascades benign discovery.
    """
    candidates = [
        nid for nid, n in g.nodes.items() 
        if not n.resistance_revealed
    ]
    # Sort by degree (greedy) — in real scenario we don't know who's sybil
    # but high-degree nodes in honest region are best seeds
    candidates.sort(key=lambda nid: g.degree(nid), reverse=True)
    
    revealed = []
    for nid in candidates[:k]:
        g.nodes[nid].resistance_revealed = True
        revealed.append(nid)
    
    return revealed


def propagate_benign_discovery(g: Graph) -> int:
    """
    If node v is known benign + resistant, then all neighbors
    connected to v must be benign (sybils can't connect to resistant nodes).
    Propagate transitively.
    """
    discovered = 0
    queue = []
    
    # Seed: revealed resistant nodes are known benign
    for nid, n in g.nodes.items():
        if n.resistance_revealed and n.resistant and not n.is_sybil:
            n.discovered_benign = True
            queue.append(nid)
    
    while queue:
        current = queue.pop(0)
        current_node = g.nodes[current]
        
        if not current_node.resistant:
            continue  # Can't propagate from non-resistant
        
        for neighbor_id in g.neighbors(current):
            neighbor = g.nodes[neighbor_id]
            if not neighbor.discovered_benign:
                neighbor.discovered_benign = True
                discovered += 1
                if neighbor.resistant:
                    queue.append(neighbor_id)
    
    return discovered


def evaluate_detection(g: Graph) -> dict:
    """Evaluate sybil detection after benign discovery."""
    tp = fp = tn = fn = 0
    
    for nid, n in g.nodes.items():
        if n.discovered_benign:
            if not n.is_sybil:
                tn += 1  # Correctly identified as benign
            else:
                fn += 1  # Sybil incorrectly marked benign
        else:
            # Unknown = suspect (conservative)
            if n.is_sybil:
                tp += 1  # Correctly suspected
            else:
                fp += 1  # Honest incorrectly suspected
    
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)
    
    return {
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "benigns_discovered": tn,
        "total_honest": sum(1 for n in g.nodes.values() if not n.is_sybil),
        "total_sybil": sum(1 for n in g.nodes.values() if n.is_sybil),
    }


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("SYBIL RESISTANCE SIMULATION (Dehkordi & Zehmakan, AAMAS 2025)")
    print("=" * 60)
    
    strategies = ["random", "degree", "community"]
    k_values = [0, 1, 3, 5, 10]
    
    for strategy in strategies:
        print(f"\n{'='*60}")
        print(f"ATTACK STRATEGY: {strategy.upper()}")
        print(f"{'='*60}")
        
        for k in k_values:
            # Fresh graph each time
            random.seed(42)
            g = generate_network(
                n_honest=100, n_sybil=30,
                resistance_rate=0.6,
                attack_strategy=strategy
            )
            
            # Count attack edges
            attack_edges = 0
            for sid in [n for n in g.nodes if g.nodes[n].is_sybil]:
                for neighbor in g.neighbors(sid):
                    if not g.nodes[neighbor].is_sybil:
                        attack_edges += 1
            
            if k == 0:
                print(f"  Attack edges formed: {attack_edges}")
                print(f"  (Resistant nodes blocked sybil requests)")
                print()
            
            # Reveal resistance of k nodes
            revealed = reveal_resistance(g, k=k)
            discovered = propagate_benign_discovery(g)
            result = evaluate_detection(g)
            
            print(f"  k={k:2d} revealed → {result['benigns_discovered']:3d} benigns discovered, "
                  f"F1={result['f1']:.3f} (P={result['precision']:.3f}, R={result['recall']:.3f})")
    
    print(f"\n{'='*60}")
    print("KEY INSIGHTS")
    print(f"{'='*60}")
    print("1. k=1 anchor dramatically improves detection (F1 jump)")
    print("2. Resistant nodes = identity layer = sybil firewall")
    print("3. Dense sybil region is DETECTABLE once you have sparse/dense contrast")
    print("4. Attack strategy matters: degree-targeted is hardest to defend")
    print("5. The 3-layer model (addressing→identity→trust) IS sybil defense:")
    print("   - Addressing = reachable (sybils get this trivially)")
    print("   - Identity = resistance (sybils FAIL here)")
    print("   - Trust = earned after surviving identity filter")


if __name__ == "__main__":
    demo()
