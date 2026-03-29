#!/usr/bin/env python3
"""
resistance-preprocessor.py — Sybil detection preprocessor via user resistance.

Based on Dehkordi & Zehmakan (AAMAS 2025): "More Efficient Sybil Detection
Mechanisms Leveraging Resistance of Users to Attack Requests."

Key insight: homophily assumption (most edges same-type) breaks in practice.
Instead, model USER RESISTANCE — whether a node rejects sybil connection
requests. Resistance is a preprocessing step: reveal resistance of a subset
of nodes to maximize:
  1. Discovered benign nodes
  2. Identified attack edges (sybil→benign connections)

ATF mapping:
- Resistance = identity layer strength (agents with strong DKIM chains, 
  behavioral consistency, high fingerprint scores reject sybil attestations)
- Attack edges = attestation requests from unknown agents
- Non-resistant nodes = cold-start agents who accept any attestation
- Preprocessing = before running expensive sybil detection, identify
  resistant nodes cheaply via trust-layer-validator scores

The greedy algorithm: reveal resistance of highest-degree unknown nodes first.
Each resistant node found eliminates all its connections to sybils.

Kit 🦊 — 2026-03-29
"""

import random
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Node:
    id: str
    is_sybil: bool
    resistant: bool = False  # Only meaningful for benign nodes
    revealed: bool = False   # Has resistance been checked?
    trust_layer_score: float = 0.0  # From trust-layer-validator


@dataclass
class Edge:
    source: str
    target: str
    is_attack_edge: bool = False  # sybil → benign


class ResistancePreprocessor:
    """
    Greedy resistance revelation for sybil detection preprocessing.
    
    Strategy: reveal resistance of highest-degree unknown nodes first.
    Resistant nodes reject sybil requests → their sybil neighbors are exposed.
    """
    
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.adjacency: dict[str, list[str]] = {}
    
    def add_node(self, node: Node):
        self.nodes[node.id] = node
        if node.id not in self.adjacency:
            self.adjacency[node.id] = []
    
    def add_edge(self, source: str, target: str):
        s = self.nodes.get(source)
        t = self.nodes.get(target)
        is_attack = False
        if s and t:
            is_attack = (s.is_sybil != t.is_sybil)
        self.edges.append(Edge(source=source, target=target, is_attack_edge=is_attack))
        self.adjacency.setdefault(source, []).append(target)
        self.adjacency.setdefault(target, []).append(source)
    
    def greedy_reveal(self, budget: int) -> dict:
        """
        Greedy algorithm: reveal resistance of highest-degree unrevealed nodes.
        
        For each revealed resistant node:
        - All its sybil neighbors are identified (attack edges found)
        - The node itself is confirmed benign
        
        Returns stats on discovered benigns and attack edges.
        """
        discovered_benign = set()
        discovered_attack_edges = set()
        discovered_sybils = set()
        reveal_log = []
        
        for step in range(budget):
            # Find unrevealed node with highest degree
            candidates = [
                (nid, len(self.adjacency.get(nid, [])))
                for nid, node in self.nodes.items()
                if not node.revealed
            ]
            if not candidates:
                break
            
            candidates.sort(key=lambda x: -x[1])
            chosen_id = candidates[0][0]
            chosen = self.nodes[chosen_id]
            chosen.revealed = True
            
            step_result = {
                "step": step + 1,
                "revealed": chosen_id,
                "degree": candidates[0][1],
                "is_sybil": chosen.is_sybil,
                "resistant": chosen.resistant if not chosen.is_sybil else None,
                "new_benigns": 0,
                "new_attack_edges": 0,
                "new_sybils": 0
            }
            
            if not chosen.is_sybil and chosen.resistant:
                # Resistant benign: reject all sybil connections
                discovered_benign.add(chosen_id)
                neighbors = self.adjacency.get(chosen_id, [])
                for nid in neighbors:
                    neighbor = self.nodes.get(nid)
                    if neighbor and neighbor.is_sybil:
                        edge_key = (min(chosen_id, nid), max(chosen_id, nid))
                        if edge_key not in discovered_attack_edges:
                            discovered_attack_edges.add(edge_key)
                            step_result["new_attack_edges"] += 1
                        if nid not in discovered_sybils:
                            discovered_sybils.add(nid)
                            step_result["new_sybils"] += 1
                step_result["new_benigns"] = 1
                
            elif not chosen.is_sybil and not chosen.resistant:
                # Non-resistant benign: accepted sybil requests, no info gained
                discovered_benign.add(chosen_id)
                step_result["new_benigns"] = 1
                # But we can't distinguish their sybil neighbors
            
            # If sybil is revealed: we know it's sybil (but in practice
            # we wouldn't know ahead of time — this is oracle evaluation)
            
            reveal_log.append(step_result)
        
        return {
            "budget": budget,
            "revealed": len(reveal_log),
            "discovered_benign": len(discovered_benign),
            "discovered_sybils": len(discovered_sybils),
            "discovered_attack_edges": len(discovered_attack_edges),
            "total_nodes": len(self.nodes),
            "total_sybils": sum(1 for n in self.nodes.values() if n.is_sybil),
            "total_benign": sum(1 for n in self.nodes.values() if not n.is_sybil),
            "sybil_detection_rate": round(
                len(discovered_sybils) / max(1, sum(1 for n in self.nodes.values() if n.is_sybil)), 3
            ),
            "log": reveal_log
        }
    
    def trust_layer_guided_reveal(self, budget: int) -> dict:
        """
        Enhanced: use trust-layer-validator scores to guide revelation order.
        
        High trust_layer_score nodes are more likely resistant.
        Reveal highest-score × highest-degree nodes first.
        """
        discovered_benign = set()
        discovered_attack_edges = set()
        discovered_sybils = set()
        reveal_log = []
        
        for step in range(budget):
            candidates = [
                (nid, node.trust_layer_score * len(self.adjacency.get(nid, [])))
                for nid, node in self.nodes.items()
                if not node.revealed
            ]
            if not candidates:
                break
            
            candidates.sort(key=lambda x: -x[1])
            chosen_id = candidates[0][0]
            chosen = self.nodes[chosen_id]
            chosen.revealed = True
            
            step_result = {
                "step": step + 1,
                "revealed": chosen_id,
                "trust_score": chosen.trust_layer_score,
                "is_sybil": chosen.is_sybil,
                "new_sybils": 0
            }
            
            if not chosen.is_sybil and chosen.resistant:
                discovered_benign.add(chosen_id)
                for nid in self.adjacency.get(chosen_id, []):
                    neighbor = self.nodes.get(nid)
                    if neighbor and neighbor.is_sybil:
                        edge_key = (min(chosen_id, nid), max(chosen_id, nid))
                        discovered_attack_edges.add(edge_key)
                        if nid not in discovered_sybils:
                            discovered_sybils.add(nid)
                            step_result["new_sybils"] += 1
            
            reveal_log.append(step_result)
        
        return {
            "budget": budget,
            "discovered_sybils": len(discovered_sybils),
            "sybil_detection_rate": round(
                len(discovered_sybils) / max(1, sum(1 for n in self.nodes.values() if n.is_sybil)), 3
            ),
            "strategy": "trust_layer_guided"
        }


def generate_network(n_honest: int = 50, n_sybil: int = 20, 
                     resistance_rate: float = 0.6,
                     honest_edge_prob: float = 0.1,
                     sybil_edge_prob: float = 0.5,
                     attack_edge_prob: float = 0.15) -> ResistancePreprocessor:
    """Generate a network with honest + sybil regions."""
    rp = ResistancePreprocessor()
    random.seed(42)
    
    # Create honest nodes (some resistant, some not)
    for i in range(n_honest):
        resistant = random.random() < resistance_rate
        trust_score = 0.7 + random.random() * 0.3 if resistant else 0.2 + random.random() * 0.3
        rp.add_node(Node(
            id=f"honest_{i}", is_sybil=False, 
            resistant=resistant, trust_layer_score=trust_score
        ))
    
    # Create sybil nodes (low trust scores)
    for i in range(n_sybil):
        rp.add_node(Node(
            id=f"sybil_{i}", is_sybil=True,
            trust_layer_score=0.1 + random.random() * 0.2
        ))
    
    # Honest edges (sparse, community structure)
    honest_ids = [f"honest_{i}" for i in range(n_honest)]
    for i in range(n_honest):
        for j in range(i + 1, n_honest):
            if random.random() < honest_edge_prob:
                rp.add_edge(honest_ids[i], honest_ids[j])
    
    # Sybil edges (dense clique — Alvisi 2013)
    sybil_ids = [f"sybil_{i}" for i in range(n_sybil)]
    for i in range(n_sybil):
        for j in range(i + 1, n_sybil):
            if random.random() < sybil_edge_prob:
                rp.add_edge(sybil_ids[i], sybil_ids[j])
    
    # Attack edges (sybil → honest, non-resistant accept more)
    for s in sybil_ids:
        for h in honest_ids:
            node = rp.nodes[h]
            # Non-resistant nodes accept sybil requests at higher rate
            prob = attack_edge_prob * (0.3 if node.resistant else 1.0)
            if random.random() < prob:
                rp.add_edge(s, h)
    
    return rp


def demo():
    print("=" * 60)
    print("RESISTANCE PREPROCESSOR (Dehkordi & Zehmakan, AAMAS 2025)")
    print("=" * 60)
    print()
    
    rp = generate_network()
    
    n_honest = sum(1 for n in rp.nodes.values() if not n.is_sybil)
    n_sybil = sum(1 for n in rp.nodes.values() if n.is_sybil)
    n_resistant = sum(1 for n in rp.nodes.values() if not n.is_sybil and n.resistant)
    n_attack = sum(1 for e in rp.edges if e.is_attack_edge)
    
    print(f"Network: {n_honest} honest ({n_resistant} resistant), {n_sybil} sybil")
    print(f"Edges: {len(rp.edges)} total, {n_attack} attack edges")
    print()
    
    # Test different budgets
    for budget in [5, 10, 20]:
        # Reset revealed state
        for n in rp.nodes.values():
            n.revealed = False
        
        result = rp.greedy_reveal(budget)
        print(f"GREEDY (budget={budget}):")
        print(f"  Discovered benign: {result['discovered_benign']}/{result['total_benign']}")
        print(f"  Discovered sybils: {result['discovered_sybils']}/{result['total_sybils']} "
              f"({result['sybil_detection_rate']:.1%})")
        print(f"  Attack edges found: {result['discovered_attack_edges']}")
        print()
    
    # Compare: trust-layer-guided vs pure greedy
    print("=" * 60)
    print("COMPARISON: Greedy vs Trust-Layer-Guided (budget=10)")
    print("=" * 60)
    
    for n in rp.nodes.values():
        n.revealed = False
    greedy = rp.greedy_reveal(10)
    
    for n in rp.nodes.values():
        n.revealed = False
    guided = rp.trust_layer_guided_reveal(10)
    
    print(f"  Greedy:  {greedy['sybil_detection_rate']:.1%} sybils detected")
    print(f"  Guided:  {guided['sybil_detection_rate']:.1%} sybils detected")
    print()
    
    improvement = guided['sybil_detection_rate'] - greedy['sybil_detection_rate']
    print(f"  Trust-layer guidance {'improves' if improvement > 0 else 'matches'} "
          f"detection by {abs(improvement):.1%}")
    print()
    print("INSIGHT: Trust-layer scores from identity evidence (DKIM chains,")
    print("behavioral fingerprints) predict resistance. Resistant nodes are")
    print("natural sybil detectors — they reject attack edges automatically.")
    print("Preprocessing = reveal resistance cheaply before expensive detection.")


if __name__ == "__main__":
    demo()
