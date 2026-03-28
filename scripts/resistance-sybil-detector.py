#!/usr/bin/env python3
"""
resistance-sybil-detector.py — Sybil detection via user resistance (Dehkordi & Zehmakan, AAMAS 2025).

Key insight from the paper (arxiv 2501.16624): sybil detection algorithms assume
homophily (most edges are same-type). But real networks violate this because
attack edges are a function of STRATEGY × RESISTANCE, not topology alone.

Resistance = whether a user rejects friendship requests from sybils.
In ATF terms: resistance = identity layer strength. Agents with established
identity (DKIM chain, behavioral history) reject bogus attestation requests.

Algorithm:
1. Reveal resistance of k nodes (budget-constrained probing)
2. Propagate: if node v is resistant + benign, neighbors of v are benign
3. Identify potential attack edges: incoming edges to non-resistant nodes
4. Feed cleaned graph to SybilWalk/SybilSCAR for improved detection

This implements the greedy benign-maximization from Section 3.1 of the paper.

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class NodeType(Enum):
    BENIGN = "benign"
    SYBIL = "sybil"
    UNKNOWN = "unknown"


@dataclass
class Node:
    id: str
    true_type: NodeType          # Ground truth
    predicted_type: NodeType = NodeType.UNKNOWN
    resistant: bool = False      # Rejects sybil requests
    resistance_revealed: bool = False
    identity_score: float = 0.0  # ATF identity layer score [0, 1]
    neighbors: list = field(default_factory=list)


class ResistanceSybilDetector:
    """
    Implements resistance-based sybil detection preprocessing.
    
    Dehkordi & Zehmakan (AAMAS 2025) show that revealing resistance
    of k nodes as preprocessing improves SybilSCAR/SybilWalk/SybilMetric.
    
    Resistance maps to ATF identity layer: agents with history reject
    bogus attestation requests because they have reputation to protect.
    """
    
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[tuple[str, str]] = []
    
    def add_node(self, node: Node):
        self.nodes[node.id] = node
    
    def add_edge(self, src: str, dst: str):
        self.edges.append((src, dst))
        if dst not in self.nodes[src].neighbors:
            self.nodes[src].neighbors.append(dst)
        if src not in self.nodes[dst].neighbors:
            self.nodes[dst].neighbors.append(src)
    
    def probe_resistance(self, node_id: str) -> bool:
        """Reveal whether a node is resistant (costs 1 probe budget)."""
        node = self.nodes[node_id]
        node.resistance_revealed = True
        return node.resistant
    
    def greedy_benign_maximization(self, budget: int, seeds: list[str]) -> dict:
        """
        Greedy algorithm from Section 3.1: spend budget k to reveal
        resistance, then propagate benign labels.
        
        Greedy heuristic: probe nodes with highest degree first
        (more neighbors = more propagation if resistant + benign).
        """
        # Start with known benign seeds
        known_benign = set(seeds)
        for sid in seeds:
            self.nodes[sid].predicted_type = NodeType.BENIGN
        
        # Sort unknown nodes by degree (greedy)
        candidates = [
            (nid, len(n.neighbors)) 
            for nid, n in self.nodes.items() 
            if nid not in known_benign and n.predicted_type == NodeType.UNKNOWN
        ]
        candidates.sort(key=lambda x: -x[1])
        
        probes_used = 0
        discovered_benign = set()
        attack_edges_found = []
        
        for nid, degree in candidates:
            if probes_used >= budget:
                break
            
            is_resistant = self.probe_resistance(nid)
            probes_used += 1
            
            if is_resistant and nid in known_benign:
                # Propagate: all neighbors of resistant benign are benign
                for neighbor_id in self.nodes[nid].neighbors:
                    if self.nodes[neighbor_id].predicted_type == NodeType.UNKNOWN:
                        self.nodes[neighbor_id].predicted_type = NodeType.BENIGN
                        discovered_benign.add(neighbor_id)
                        known_benign.add(neighbor_id)
            elif not is_resistant:
                # Non-resistant: incoming edges are potential attack edges
                for neighbor_id in self.nodes[nid].neighbors:
                    attack_edges_found.append((neighbor_id, nid))
        
        # Second pass: propagate from newly discovered benigns
        queue = deque(discovered_benign)
        while queue:
            nid = queue.popleft()
            node = self.nodes[nid]
            if node.resistance_revealed and node.resistant:
                for neighbor_id in node.neighbors:
                    if self.nodes[neighbor_id].predicted_type == NodeType.UNKNOWN:
                        self.nodes[neighbor_id].predicted_type = NodeType.BENIGN
                        discovered_benign.add(neighbor_id)
                        known_benign.add(neighbor_id)
                        queue.append(neighbor_id)
        
        return {
            "probes_used": probes_used,
            "known_benign": len(known_benign),
            "discovered_benign": len(discovered_benign),
            "attack_edges_found": len(attack_edges_found),
            "coverage": len(known_benign) / len(self.nodes) if self.nodes else 0
        }
    
    def evaluate(self) -> dict:
        """Evaluate detection accuracy against ground truth."""
        tp = fp = tn = fn = 0
        for node in self.nodes.values():
            if node.predicted_type == NodeType.BENIGN:
                if node.true_type == NodeType.BENIGN:
                    tp += 1
                else:
                    fp += 1
            elif node.predicted_type == NodeType.UNKNOWN:
                if node.true_type == NodeType.SYBIL:
                    tn += 1  # Correctly not labeled benign
                else:
                    fn += 1  # Missed benign
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "fpr": round(fpr, 4),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn
        }


def generate_test_network(n_benign: int = 100, n_sybil: int = 30,
                          resistance_rate: float = 0.6,
                          honest_density: float = 0.05,
                          sybil_density: float = 0.3,
                          attack_edge_rate: float = 0.1) -> ResistanceSybilDetector:
    """
    Generate synthetic network following Dehkordi & Zehmakan framework.
    
    Honest graph: sparse (density ~0.05), power-law-ish
    Sybil graph: dense (density ~0.3), mutual inflation
    Attack edges: function of strategy × resistance
    """
    random.seed(42)
    detector = ResistanceSybilDetector()
    
    # Create benign nodes
    for i in range(n_benign):
        resistant = random.random() < resistance_rate
        identity = random.uniform(0.5, 1.0) if resistant else random.uniform(0.0, 0.4)
        detector.add_node(Node(
            id=f"benign_{i}",
            true_type=NodeType.BENIGN,
            resistant=resistant,
            identity_score=identity
        ))
    
    # Create sybil nodes (never resistant — they accept everything)
    for i in range(n_sybil):
        detector.add_node(Node(
            id=f"sybil_{i}",
            true_type=NodeType.SYBIL,
            resistant=False,
            identity_score=random.uniform(0.0, 0.15)
        ))
    
    # Honest edges (sparse)
    benign_ids = [f"benign_{i}" for i in range(n_benign)]
    for i in range(n_benign):
        for j in range(i + 1, n_benign):
            if random.random() < honest_density:
                detector.add_edge(benign_ids[i], benign_ids[j])
    
    # Sybil edges (dense — mutual inflation)
    sybil_ids = [f"sybil_{i}" for i in range(n_sybil)]
    for i in range(n_sybil):
        for j in range(i + 1, n_sybil):
            if random.random() < sybil_density:
                detector.add_edge(sybil_ids[i], sybil_ids[j])
    
    # Attack edges: sybils send requests; resistant benigns reject
    for sid in sybil_ids:
        for bid in benign_ids:
            if random.random() < attack_edge_rate:
                benign_node = detector.nodes[bid]
                if not benign_node.resistant:
                    # Non-resistant accepts attack request
                    detector.add_edge(sid, bid)
                # Resistant nodes reject → no edge (key insight!)
    
    return detector


def demo():
    print("=" * 60)
    print("RESISTANCE-BASED SYBIL DETECTION")
    print("Dehkordi & Zehmakan, AAMAS 2025 (arxiv 2501.16624)")
    print("=" * 60)
    
    detector = generate_test_network()
    
    n_benign = sum(1 for n in detector.nodes.values() if n.true_type == NodeType.BENIGN)
    n_sybil = sum(1 for n in detector.nodes.values() if n.true_type == NodeType.SYBIL)
    n_resistant = sum(1 for n in detector.nodes.values() if n.resistant)
    
    print(f"\nNetwork: {n_benign} benign, {n_sybil} sybil, {n_resistant} resistant")
    print(f"Edges: {len(detector.edges)}")
    print(f"Resistance rate: {n_resistant}/{len(detector.nodes)} = {n_resistant/len(detector.nodes):.1%}")
    
    # Seed with 3 known benign nodes
    seeds = ["benign_0", "benign_10", "benign_50"]
    
    # Run with different budgets
    for budget in [5, 10, 20, 50]:
        # Reset predictions
        for node in detector.nodes.values():
            node.predicted_type = NodeType.UNKNOWN
            node.resistance_revealed = False
        
        result = detector.greedy_benign_maximization(budget=budget, seeds=seeds)
        eval_result = detector.evaluate()
        
        print(f"\n--- Budget k={budget} ---")
        print(f"  Probes used: {result['probes_used']}")
        print(f"  Known benign: {result['known_benign']} ({result['coverage']:.1%} coverage)")
        print(f"  Discovered via propagation: {result['discovered_benign']}")
        print(f"  Attack edges found: {result['attack_edges_found']}")
        print(f"  Precision: {eval_result['precision']:.3f}")
        print(f"  Recall: {eval_result['recall']:.3f}")
        print(f"  FPR: {eval_result['fpr']:.3f}")
    
    print("\n" + "=" * 60)
    print("ATF MAPPING")
    print("=" * 60)
    print("• Resistance = identity layer (DKIM chain, behavioral history)")
    print("• Resistant agents reject bogus attestation requests")
    print("• Probing resistance = checking identity layer completeness")
    print("• Attack edges = sybil attestations accepted by non-resistant agents")
    print("• Budget k = how many agents can we deeply verify before detection")
    print("• Greedy by degree = verify high-connectivity agents first (hubs)")
    print()
    print("Key result (paper): revealing resistance of just k nodes as")
    print("preprocessing NOTABLY improves SybilSCAR/SybilWalk accuracy.")
    print("ATF implication: identity layer checks are the preprocessing")
    print("step that makes trust-layer detection work.")


if __name__ == "__main__":
    demo()
