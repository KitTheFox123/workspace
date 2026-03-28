#!/usr/bin/env python3
"""
sybil-resistance-detector.py — Graph-based sybil detection using resistance model.

Implements the core insight from Dehkordi & Zehmakan (AAMAS 2025):
user RESISTANCE to attack requests is the missing variable in sybil detection.
Graph structure = f(attack_strategy × resistance), not just homophily assumption.

ATF mapping:
- Resistance = identity layer strength (DKIM chain days, behavioral consistency)
- Attack edges = attestation requests from sybils to honest agents
- Resistant agents reject sybil attestation requests (strong identity = filter)
- Non-resistant agents accept (weak identity = sybil bridge)

Detection approach:
1. Build trust graph from attestation data
2. Compute resistance score per agent (identity layer strength)
3. Reveal resistance of k seed agents (known-honest)
4. Propagate labels via modified random walk (SybilRank-style)
5. Dense subgraph = sybil ring, sparse honest region = verified

Key numbers from literature:
- SybilGuard (Yu 2006): O(√n log n) attack edges needed to fool random walk
- SybilRank (Cao 2012): trust propagation from seeds, O(n log n)
- Dehkordi & Zehmakan (2025): resistance preprocessing improves accuracy 15-30%
- Percolation threshold: p_c ≈ 0.54 honest fraction for trust to propagate

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Agent:
    id: str
    is_sybil: bool = False
    resistance: float = 0.5  # 0 = accepts everything, 1 = rejects all unknown
    identity_strength: float = 0.0  # DKIM days / behavioral samples composite
    trust_score: float = 0.0  # Computed by detection algorithm
    label: str = "unknown"  # "honest", "sybil", "unknown"


class TrustGraph:
    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.edges: dict[str, set[str]] = defaultdict(set)  # bidirectional
        self.edge_weights: dict[tuple, float] = {}
    
    def add_agent(self, agent: Agent):
        self.agents[agent.id] = agent
    
    def add_edge(self, a: str, b: str, weight: float = 1.0):
        self.edges[a].add(b)
        self.edges[b].add(a)
        self.edge_weights[(a, b)] = weight
        self.edge_weights[(b, a)] = weight
    
    def degree(self, agent_id: str) -> int:
        return len(self.edges.get(agent_id, set()))
    
    def clustering_coefficient(self, agent_id: str) -> float:
        """Local clustering coefficient."""
        neighbors = self.edges.get(agent_id, set())
        if len(neighbors) < 2:
            return 0.0
        possible = len(neighbors) * (len(neighbors) - 1) / 2
        actual = 0
        neighbor_list = list(neighbors)
        for i in range(len(neighbor_list)):
            for j in range(i + 1, len(neighbor_list)):
                if neighbor_list[j] in self.edges.get(neighbor_list[i], set()):
                    actual += 1
        return actual / possible if possible > 0 else 0.0


def generate_network(n_honest: int = 50, n_sybil: int = 20, 
                     n_attack_edges: int = 15, seed: int = 42) -> TrustGraph:
    """
    Generate a trust network with honest and sybil regions.
    
    Honest region: sparse, power-law-ish degree distribution
    Sybil region: dense mutual connections (free to create)
    Attack edges: sybils → honest (filtered by resistance)
    """
    random.seed(seed)
    graph = TrustGraph()
    
    # Create honest agents with varying resistance
    for i in range(n_honest):
        resistance = random.betavariate(3, 2)  # Skewed toward higher resistance
        identity = random.betavariate(2, 1) * 90  # Days of DKIM history
        graph.add_agent(Agent(
            id=f"honest_{i}",
            is_sybil=False,
            resistance=resistance,
            identity_strength=identity / 90  # Normalize to 0-1
        ))
    
    # Create sybil agents (low identity, low resistance to each other)
    for i in range(n_sybil):
        graph.add_agent(Agent(
            id=f"sybil_{i}",
            is_sybil=True,
            resistance=0.1,  # Accept everything from sybil ring
            identity_strength=random.uniform(0, 0.15)  # Minimal history
        ))
    
    # Honest edges: sparse, preferential attachment
    honest_ids = [f"honest_{i}" for i in range(n_honest)]
    # Start with a small clique
    for i in range(min(5, n_honest)):
        for j in range(i + 1, min(5, n_honest)):
            graph.add_edge(honest_ids[i], honest_ids[j])
    
    # Add remaining edges with preferential attachment
    for i in range(5, n_honest):
        n_edges = random.choices([1, 2, 3, 4, 5], weights=[5, 3, 2, 1, 0.5])[0]
        targets = random.sample(honest_ids[:i], min(n_edges, i))
        for t in targets:
            graph.add_edge(honest_ids[i], t)
    
    # Sybil edges: dense internal connections (free mutual attestation)
    sybil_ids = [f"sybil_{i}" for i in range(n_sybil)]
    for i in range(n_sybil):
        for j in range(i + 1, n_sybil):
            if random.random() < 0.7:  # 70% internal density
                graph.add_edge(sybil_ids[i], sybil_ids[j])
    
    # Attack edges: sybils try to connect to honest agents
    # Resistance determines whether edge forms (Dehkordi & Zehmakan model)
    attack_edges_formed = 0
    attack_edges_rejected = 0
    for _ in range(n_attack_edges * 3):  # Try more than needed
        sybil = random.choice(sybil_ids)
        honest = random.choice(honest_ids)
        
        # Resistance check: honest agent's resistance filters attack edges
        if random.random() > graph.agents[honest].resistance:
            graph.add_edge(sybil, honest, weight=0.5)
            attack_edges_formed += 1
        else:
            attack_edges_rejected += 1
        
        if attack_edges_formed >= n_attack_edges:
            break
    
    return graph


def sybilrank_detect(graph: TrustGraph, seeds: list[str], 
                     iterations: int = 10, decay: float = 0.85) -> dict[str, float]:
    """
    Modified SybilRank: trust propagation from honest seeds.
    
    Seeds = known-honest agents (high resistance, strong identity).
    Trust propagates via random walk but decays. Sybil region
    gets less trust because attack edges are sparse.
    
    Dehkordi & Zehmakan improvement: revealing resistance of k agents
    as preprocessing helps identify attack edges → prune them → 
    improve SybilRank accuracy by 15-30%.
    """
    # Initialize trust: seeds get 1.0, others get 0
    trust = {aid: 0.0 for aid in graph.agents}
    for s in seeds:
        trust[s] = 1.0
    
    # Iterative propagation
    for _ in range(iterations):
        new_trust = {aid: 0.0 for aid in graph.agents}
        for aid in graph.agents:
            neighbors = graph.edges.get(aid, set())
            if not neighbors:
                continue
            # Distribute trust to neighbors, weighted by edge weight
            share = trust[aid] * decay / len(neighbors)
            for n in neighbors:
                weight = graph.edge_weights.get((aid, n), 1.0)
                new_trust[n] += share * weight
        
        # Add back seed trust (teleportation)
        for s in seeds:
            new_trust[s] += (1 - decay)
        
        trust = new_trust
    
    return trust


def resistance_preprocessing(graph: TrustGraph, k: int = 5) -> list[str]:
    """
    Dehkordi & Zehmakan preprocessing: reveal resistance of k agents
    to identify attack edges and honest seeds.
    
    Strategy: pick agents with highest identity_strength (most resistant).
    These are most likely to be honest (sybils can't fake history).
    """
    ranked = sorted(
        graph.agents.values(),
        key=lambda a: (a.identity_strength, a.resistance),
        reverse=True
    )
    return [a.id for a in ranked[:k]]


def detect_sybils(graph: TrustGraph, n_seeds: int = 5) -> dict:
    """Full detection pipeline."""
    
    # Step 1: Resistance preprocessing (identify seeds)
    seeds = resistance_preprocessing(graph, k=n_seeds)
    
    # Step 2: SybilRank propagation
    trust_scores = sybilrank_detect(graph, seeds)
    
    # Step 3: Label agents based on trust score
    # Use density-based threshold: sybil region has inflated internal trust
    # but low trust from honest seeds
    scores = sorted(trust_scores.values())
    threshold = scores[len(scores) // 3]  # Bottom third = likely sybil
    
    results = {"honest": [], "sybil": [], "uncertain": []}
    true_pos = false_pos = true_neg = false_neg = 0
    
    for aid, score in trust_scores.items():
        agent = graph.agents[aid]
        agent.trust_score = score
        
        if score > threshold * 2:
            agent.label = "honest"
            if agent.is_sybil:
                false_neg += 1
            else:
                true_neg += 1
            results["honest"].append(aid)
        elif score < threshold:
            agent.label = "sybil"
            if agent.is_sybil:
                true_pos += 1
            else:
                false_pos += 1
            results["sybil"].append(aid)
        else:
            agent.label = "uncertain"
            results["uncertain"].append(aid)
    
    total_sybil = sum(1 for a in graph.agents.values() if a.is_sybil)
    total_honest = sum(1 for a in graph.agents.values() if not a.is_sybil)
    
    precision = true_pos / max(true_pos + false_pos, 1)
    recall = true_pos / max(total_sybil, 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)
    
    # Graph structure analysis
    honest_degrees = [graph.degree(a.id) for a in graph.agents.values() if not a.is_sybil]
    sybil_degrees = [graph.degree(a.id) for a in graph.agents.values() if a.is_sybil]
    
    honest_clustering = [graph.clustering_coefficient(a.id) for a in graph.agents.values() if not a.is_sybil]
    sybil_clustering = [graph.clustering_coefficient(a.id) for a in graph.agents.values() if a.is_sybil]
    
    return {
        "seeds": seeds,
        "detection": {
            "true_positives": true_pos,
            "false_positives": false_pos,
            "true_negatives": true_neg,
            "false_negatives": false_neg,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        },
        "labels": {
            "honest": len(results["honest"]),
            "sybil": len(results["sybil"]),
            "uncertain": len(results["uncertain"]),
        },
        "graph_structure": {
            "honest_avg_degree": round(sum(honest_degrees) / max(len(honest_degrees), 1), 2),
            "sybil_avg_degree": round(sum(sybil_degrees) / max(len(sybil_degrees), 1), 2),
            "honest_avg_clustering": round(sum(honest_clustering) / max(len(honest_clustering), 1), 3),
            "sybil_avg_clustering": round(sum(sybil_clustering) / max(len(sybil_clustering), 1), 3),
            "density_ratio": round(
                (sum(sybil_degrees) / max(len(sybil_degrees), 1)) / 
                max(sum(honest_degrees) / max(len(honest_degrees), 1), 0.01), 2
            )
        },
        "methodology": (
            "SybilRank trust propagation from identity-strong seeds. "
            "Resistance preprocessing (Dehkordi & Zehmakan AAMAS 2025) "
            "selects seeds by identity layer strength. Dense sybil subgraphs "
            "get less seed trust because attack edges are sparse and "
            "resistance-filtered."
        )
    }


def demo():
    print("=" * 60)
    print("SYBIL RESISTANCE DETECTION — ATF TRUST GRAPH")
    print("=" * 60)
    print()
    
    graph = generate_network(n_honest=50, n_sybil=20, n_attack_edges=15)
    
    total_edges = sum(len(v) for v in graph.edges.values()) // 2
    print(f"Network: {len(graph.agents)} agents, {total_edges} edges")
    print(f"  Honest: 50, Sybil: 20")
    print()
    
    result = detect_sybils(graph, n_seeds=5)
    
    print(f"Seeds (highest identity strength): {result['seeds'][:3]}...")
    print()
    
    print("DETECTION RESULTS:")
    print(f"  Precision: {result['detection']['precision']}")
    print(f"  Recall: {result['detection']['recall']}")
    print(f"  F1: {result['detection']['f1']}")
    print(f"  True Positives: {result['detection']['true_positives']}")
    print(f"  False Positives: {result['detection']['false_positives']}")
    print(f"  False Negatives: {result['detection']['false_negatives']}")
    print()
    
    print("LABELS:")
    print(f"  Honest: {result['labels']['honest']}")
    print(f"  Sybil: {result['labels']['sybil']}")
    print(f"  Uncertain: {result['labels']['uncertain']}")
    print()
    
    gs = result['graph_structure']
    print("GRAPH STRUCTURE (honest vs sybil):")
    print(f"  Avg degree: honest={gs['honest_avg_degree']}, sybil={gs['sybil_avg_degree']}")
    print(f"  Avg clustering: honest={gs['honest_avg_clustering']}, sybil={gs['sybil_avg_clustering']}")
    print(f"  Density ratio (sybil/honest): {gs['density_ratio']}x")
    print()
    
    print("KEY INSIGHT: Sybils form dense subgraphs (mutual inflation is free).")
    print("Honest agents form sparse ones (trust is earned). Random walks from")
    print("identity-strong seeds stay in honest region. Resistance = identity")
    print("layer strength = the filter that keeps sybils out.")
    print()
    
    # Assertions
    assert result['detection']['precision'] > 0.5, f"Precision too low: {result['detection']['precision']}"
    assert gs['sybil_avg_clustering'] > gs['honest_avg_clustering'], "Sybil clustering should be higher"
    print("ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
