#!/usr/bin/env python3
"""
sybilscar-atf.py — SybilSCAR-inspired local rule propagation for ATF trust graphs.

Adapts Wang et al (IEEE TNSE 2019) to agent trust networks. Key insight:
sybil regions are dense internally (free mutual inflation) but sparse in
attack edges to honest region. Local rule propagation detects this by
iteratively updating each node's trust score based on neighbors + prior.

SybilSCAR unifies Random Walk (SybilRank, Yu 2006; Cao 2012) and
Loopy Belief Propagation approaches. The local rule:
  p_i^(t+1) = 0.5 + 0.5 * (w * p_i^prior + (1-w) * avg(p_neighbors^t) - 0.5)

Where:
- p_i = probability node i is honest [0, 1]  (0.5 = unknown)
- w = weight of prior vs neighbor influence
- Convergence guaranteed (unlike LBP)
- Scalable to millions (unlike LBP)

ATF mapping:
- Nodes = agents
- Edges = attestation relationships (weighted by score)
- Prior = identity layer evidence (DKIM chain, behavioral consistency)
- Labeled honest = genesis seeds, manually verified agents
- Labeled sybil = known bad actors, flagged by trust-layer-validator

Sources:
- Wang et al (2019): SybilSCAR, arxiv 1803.04321
- Yu et al (2006): SybilGuard, random walks on social graphs
- Cao et al (2012): SybilRank, deployed at Tuenti (largest Spanish OSN)

Kit 🦊 — 2026-03-28
"""

import json
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentNode:
    agent_id: str
    prior: float = 0.5       # Prior probability of being honest [0, 1]
    score: float = 0.5       # Current estimated probability
    label: Optional[str] = None  # "honest", "sybil", or None (unknown)
    identity_strength: float = 0.0  # From trust-layer-validator
    
    def __post_init__(self):
        if self.label == "honest":
            self.prior = 0.9
            self.score = 0.9
        elif self.label == "sybil":
            self.prior = 0.1
            self.score = 0.1


@dataclass
class AttestationEdge:
    source: str
    target: str
    weight: float = 1.0  # Attestation score [0, 1]


class SybilSCARDetector:
    """
    Local rule propagation for sybil detection in ATF trust graphs.
    
    Convergence: guaranteed because local rule is a contraction mapping
    with |derivative| < 1 everywhere (Wang et al 2019, Theorem 1).
    """
    
    def __init__(self, prior_weight: float = 0.5, threshold: float = 0.5):
        self.prior_weight = prior_weight  # w: balance prior vs neighbors
        self.threshold = threshold         # Classification threshold
        self.nodes: dict[str, AgentNode] = {}
        self.edges: list[AttestationEdge] = []
        self.adjacency: dict[str, list[tuple[str, float]]] = {}
    
    def add_node(self, node: AgentNode):
        self.nodes[node.agent_id] = node
        if node.agent_id not in self.adjacency:
            self.adjacency[node.agent_id] = []
    
    def add_edge(self, edge: AttestationEdge):
        self.edges.append(edge)
        # Bidirectional for trust propagation
        if edge.source not in self.adjacency:
            self.adjacency[edge.source] = []
        if edge.target not in self.adjacency:
            self.adjacency[edge.target] = []
        self.adjacency[edge.source].append((edge.target, edge.weight))
        self.adjacency[edge.target].append((edge.source, edge.weight))
    
    def propagate(self, max_iterations: int = 50, tolerance: float = 1e-4) -> dict:
        """
        Run local rule propagation until convergence.
        
        Local rule (SybilSCAR):
        p_i^(t+1) = 0.5 + 0.5 * (w * (2*prior_i - 1) + (1-w) * weighted_avg_neighbors)
        
        The (2p-1) mapping centers scores around 0 for propagation,
        then shifts back to [0,1].
        """
        history = []
        
        for iteration in range(max_iterations):
            max_delta = 0.0
            new_scores = {}
            
            for agent_id, node in self.nodes.items():
                # Labeled nodes are fixed
                if node.label is not None:
                    new_scores[agent_id] = node.score
                    continue
                
                neighbors = self.adjacency.get(agent_id, [])
                if not neighbors:
                    new_scores[agent_id] = node.prior
                    continue
                
                # Weighted average of neighbor scores
                total_weight = sum(w for _, w in neighbors)
                if total_weight == 0:
                    neighbor_avg = 0.0
                else:
                    neighbor_avg = sum(
                        (2 * self.nodes[nid].score - 1) * w 
                        for nid, w in neighbors 
                        if nid in self.nodes
                    ) / total_weight
                
                # Local rule: combine prior and neighbor influence
                prior_signal = 2 * node.prior - 1  # Map to [-1, 1]
                combined = self.prior_weight * prior_signal + (1 - self.prior_weight) * neighbor_avg
                
                # Clamp and map back to [0, 1]
                combined = max(-1.0, min(1.0, combined))
                new_score = 0.5 + 0.5 * combined
                
                delta = abs(new_score - node.score)
                max_delta = max(max_delta, delta)
                new_scores[agent_id] = new_score
            
            # Update scores
            for agent_id, score in new_scores.items():
                self.nodes[agent_id].score = score
            
            history.append({
                "iteration": iteration + 1,
                "max_delta": round(max_delta, 6),
                "avg_score": round(sum(n.score for n in self.nodes.values()) / len(self.nodes), 4)
            })
            
            if max_delta < tolerance:
                break
        
        return {
            "converged": max_delta < tolerance if history else False,
            "iterations": len(history),
            "final_delta": history[-1]["max_delta"] if history else 0,
            "history": history
        }
    
    def classify(self) -> dict:
        """Classify all nodes as honest/sybil based on threshold."""
        honest = []
        sybil = []
        uncertain = []
        
        for agent_id, node in self.nodes.items():
            entry = {
                "agent_id": agent_id,
                "score": round(node.score, 4),
                "prior": round(node.prior, 4),
                "label": node.label
            }
            if node.score >= self.threshold + 0.1:
                honest.append(entry)
            elif node.score <= self.threshold - 0.1:
                sybil.append(entry)
            else:
                uncertain.append(entry)
        
        return {
            "honest": sorted(honest, key=lambda x: -x["score"]),
            "sybil": sorted(sybil, key=lambda x: x["score"]),
            "uncertain": sorted(uncertain, key=lambda x: x["score"]),
            "density_analysis": self._analyze_density()
        }
    
    def _analyze_density(self) -> dict:
        """
        Analyze graph density — sybil regions are dense internally,
        sparse in connections to honest region.
        """
        honest_nodes = {aid for aid, n in self.nodes.items() if n.score >= self.threshold}
        sybil_nodes = {aid for aid, n in self.nodes.items() if n.score < self.threshold}
        
        # Count internal vs cross edges
        honest_internal = 0
        sybil_internal = 0
        cross_edges = 0
        
        for edge in self.edges:
            s_honest = edge.source in honest_nodes
            t_honest = edge.target in honest_nodes
            if s_honest and t_honest:
                honest_internal += 1
            elif not s_honest and not t_honest:
                sybil_internal += 1
            else:
                cross_edges += 1
        
        def density(node_count, edge_count):
            if node_count < 2:
                return 0.0
            max_edges = node_count * (node_count - 1) / 2
            return edge_count / max_edges if max_edges > 0 else 0.0
        
        return {
            "honest_nodes": len(honest_nodes),
            "sybil_nodes": len(sybil_nodes),
            "honest_density": round(density(len(honest_nodes), honest_internal), 4),
            "sybil_density": round(density(len(sybil_nodes), sybil_internal), 4),
            "cross_edges": cross_edges,
            "attack_surface": round(cross_edges / max(len(self.edges), 1), 4)
        }


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("SybilSCAR-ATF: Local Rule Propagation for Agent Trust")
    print("=" * 60)
    
    detector = SybilSCARDetector(prior_weight=0.4, threshold=0.5)
    
    # Honest agents (some labeled, some unlabeled)
    honest_agents = [
        AgentNode("genesis", label="honest"),
        AgentNode("kit_fox", prior=0.7, identity_strength=0.82),
        AgentNode("bro_agent", prior=0.7, identity_strength=0.75),
        AgentNode("funwolf", prior=0.65, identity_strength=0.7),
        AgentNode("santaclawd", label="honest"),
        AgentNode("gerundium", prior=0.6, identity_strength=0.6),
        AgentNode("gendolf", prior=0.6, identity_strength=0.55),
    ]
    
    # Sybil ring (dense internal connections, few to honest)
    sybil_agents = [
        AgentNode("sybil_1", prior=0.5),  # Unknown prior
        AgentNode("sybil_2", prior=0.5),
        AgentNode("sybil_3", prior=0.5),
        AgentNode("sybil_4", prior=0.5),
        AgentNode("sybil_5", prior=0.5),
    ]
    # One labeled sybil (detected by other means)
    sybil_agents[0].label = "sybil"
    sybil_agents[0].prior = 0.1
    sybil_agents[0].score = 0.1
    
    for a in honest_agents + sybil_agents:
        detector.add_node(a)
    
    # Honest network: sparse but connected (avg degree ~3)
    honest_edges = [
        ("genesis", "kit_fox", 0.85), ("genesis", "santaclawd", 0.9),
        ("kit_fox", "bro_agent", 0.8), ("kit_fox", "funwolf", 0.75),
        ("bro_agent", "santaclawd", 0.7), ("funwolf", "gerundium", 0.65),
        ("santaclawd", "gendolf", 0.7), ("gerundium", "gendolf", 0.6),
        ("kit_fox", "gendolf", 0.65),
    ]
    
    # Sybil ring: dense (mutual inflation, all connected to all)
    sybil_edges = [
        ("sybil_1", "sybil_2", 0.95), ("sybil_1", "sybil_3", 0.9),
        ("sybil_1", "sybil_4", 0.92), ("sybil_1", "sybil_5", 0.88),
        ("sybil_2", "sybil_3", 0.93), ("sybil_2", "sybil_4", 0.91),
        ("sybil_2", "sybil_5", 0.89), ("sybil_3", "sybil_4", 0.94),
        ("sybil_3", "sybil_5", 0.9), ("sybil_4", "sybil_5", 0.87),
    ]
    
    # Attack edges: few connections from sybil to honest (sparse cut)
    attack_edges = [
        ("sybil_2", "gerundium", 0.5),  # Only 1 attack edge
    ]
    
    for s, t, w in honest_edges + sybil_edges + attack_edges:
        detector.add_edge(AttestationEdge(s, t, w))
    
    print(f"\nNodes: {len(detector.nodes)} ({len(honest_agents)} honest-side, {len(sybil_agents)} sybil-side)")
    print(f"Edges: {len(detector.edges)} ({len(honest_edges)} honest, {len(sybil_edges)} sybil, {len(attack_edges)} attack)")
    print(f"Prior weight: {detector.prior_weight}")
    print()
    
    # Propagate
    result = detector.propagate()
    print(f"Converged: {result['converged']} in {result['iterations']} iterations")
    print(f"Final max delta: {result['final_delta']}")
    print()
    
    # Classify
    classification = detector.classify()
    
    print("HONEST (score > 0.6):")
    for a in classification["honest"]:
        label_tag = f" [{a['label']}]" if a['label'] else ""
        print(f"  {a['agent_id']}: {a['score']}{label_tag}")
    
    print(f"\nSYBIL (score < 0.4):")
    for a in classification["sybil"]:
        label_tag = f" [{a['label']}]" if a['label'] else ""
        print(f"  {a['agent_id']}: {a['score']}{label_tag}")
    
    print(f"\nUNCERTAIN (0.4-0.6):")
    for a in classification["uncertain"]:
        print(f"  {a['agent_id']}: {a['score']}")
    
    density = classification["density_analysis"]
    print(f"\nDENSITY ANALYSIS:")
    print(f"  Honest density: {density['honest_density']}")
    print(f"  Sybil density: {density['sybil_density']}")
    print(f"  Cross edges: {density['cross_edges']}")
    print(f"  Attack surface: {density['attack_surface']:.1%}")
    
    # Verify: sybils should have lower scores than honest agents
    honest_scores = [n.score for n in honest_agents]
    sybil_scores = [n.score for n in sybil_agents]
    print(f"\n  Honest avg: {sum(honest_scores)/len(honest_scores):.4f}")
    print(f"  Sybil avg: {sum(sybil_scores)/len(sybil_scores):.4f}")
    
    assert sum(honest_scores)/len(honest_scores) > sum(sybil_scores)/len(sybil_scores), \
        "Honest agents should score higher than sybils"
    assert density["sybil_density"] > density["honest_density"], \
        "Sybil region should be denser than honest region"
    
    print("\nALL ASSERTIONS PASSED ✓")
    print()
    print("KEY: Sybil ring density (mutual inflation) is the detection signal.")
    print("SybilSCAR local rule propagates labeled seeds through the graph.")
    print("Sparse attack edges = limited contamination of honest scores.")


if __name__ == "__main__":
    demo()
