#!/usr/bin/env python3
"""
sybil-density-detector.py — Graph-structural sybil detection for ATF networks.

Core insight from Clawk sybil density thread + AAMAS 2025 (Dehkordi & Zehmakan):
Honest agents form SPARSE graphs (trust is hard to earn). Sybils form DENSE ones
(free mutual inflation). SybilRank/SybilGuard exploit this density gap via random walks.

Healthy honest network properties (at scale):
- Power-law degree distribution (most agents 3-5 connections, few hubs at 50+)
- Clustering coefficient ~0.3 (triadic closure)
- Average degree 5-8
- Sparse overall (edges << n²)

Sybil ring signatures:
- Uniform/near-uniform degree (everyone trusts everyone)
- Near-1.0 internal clustering
- Dense subgraph (edges ≈ n² within ring)
- Weak cut to honest network (few attack edges)

Detection: Random walk from trusted seed gets "trapped" in dense sybil regions
(SybilRank, Cao et al 2012). We implement a simpler density-based detector:
identify subgraphs where internal density >> external connectivity.

Also implements "resistance" scoring from AAMAS 2025: agents with strong
identity layers (DKIM chain, behavioral consistency) have high resistance
to sybil friendship/attestation requests.

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional


@dataclass
class Agent:
    id: str
    is_sybil: bool = False
    identity_strength: float = 0.0  # 0-1, resistance to sybil requests
    trust_edges: set = field(default_factory=set)
    
    @property
    def degree(self) -> int:
        return len(self.trust_edges)


class TrustNetwork:
    def __init__(self):
        self.agents: dict[str, Agent] = {}
    
    def add_agent(self, agent_id: str, is_sybil: bool = False, 
                  identity_strength: float = 0.5) -> Agent:
        agent = Agent(id=agent_id, is_sybil=is_sybil, 
                     identity_strength=identity_strength)
        self.agents[agent_id] = agent
        return agent
    
    def add_edge(self, a: str, b: str):
        if a in self.agents and b in self.agents:
            self.agents[a].trust_edges.add(b)
            self.agents[b].trust_edges.add(a)
    
    def subgraph_density(self, agent_ids: set) -> float:
        """Internal edge density of a subgraph. 1.0 = complete graph."""
        n = len(agent_ids)
        if n < 2:
            return 0.0
        max_edges = n * (n - 1) / 2
        actual = sum(
            1 for a in agent_ids
            for b in self.agents[a].trust_edges
            if b in agent_ids and a < b
        )
        return actual / max_edges
    
    def clustering_coefficient(self, agent_id: str) -> float:
        """Local clustering coefficient."""
        neighbors = self.agents[agent_id].trust_edges
        if len(neighbors) < 2:
            return 0.0
        
        triangles = 0
        neighbor_list = list(neighbors)
        for i in range(len(neighbor_list)):
            for j in range(i + 1, len(neighbor_list)):
                if neighbor_list[j] in self.agents[neighbor_list[i]].trust_edges:
                    triangles += 1
        
        possible = len(neighbors) * (len(neighbors) - 1) / 2
        return triangles / possible if possible > 0 else 0.0
    
    def cut_ratio(self, subgraph: set) -> float:
        """Ratio of external edges to total edges for a subgraph."""
        external = 0
        internal = 0
        for a in subgraph:
            for b in self.agents[a].trust_edges:
                if b in subgraph:
                    internal += 1
                else:
                    external += 1
        total = internal + external
        return external / total if total > 0 else 0.0


@dataclass
class SybilDetectionResult:
    suspect_clusters: list[dict]
    network_stats: dict
    resistance_scores: dict  # agent_id → resistance


class SybilDensityDetector:
    """
    Detects sybil rings via density analysis.
    
    Algorithm:
    1. Find dense subgraphs (greedy expansion from high-degree nodes)
    2. Check sybil signatures: high density + low cut ratio + uniform degree
    3. Score resistance: identity-layer strength × degree diversity
    """
    
    DENSITY_THRESHOLD = 0.7    # Internal density above this = suspicious
    CUT_THRESHOLD = 0.15       # External connectivity below this = suspicious
    DEGREE_CV_THRESHOLD = 0.2  # Coefficient of variation below this = uniform
    
    def detect(self, network: TrustNetwork, seeds: set[str] = None) -> SybilDetectionResult:
        # 1. Compute network-wide stats
        stats = self._network_stats(network)
        
        # 2. Find dense subgraphs
        clusters = self._find_dense_clusters(network)
        
        # 3. Score each cluster for sybil signatures
        suspect_clusters = []
        for cluster in clusters:
            density = network.subgraph_density(cluster)
            cut = network.cut_ratio(cluster)
            degrees = [network.agents[a].degree for a in cluster]
            avg_degree = sum(degrees) / len(degrees)
            degree_cv = (sum((d - avg_degree)**2 for d in degrees) / len(degrees))**0.5 / max(avg_degree, 1)
            
            avg_clustering = sum(network.clustering_coefficient(a) for a in cluster) / len(cluster)
            
            # Sybil score: high density + low cut + uniform degree
            sybil_score = 0.0
            reasons = []
            
            if density > self.DENSITY_THRESHOLD:
                sybil_score += 0.4
                reasons.append(f"high_density={density:.2f}")
            if cut < self.CUT_THRESHOLD:
                sybil_score += 0.3
                reasons.append(f"low_cut_ratio={cut:.2f}")
            if degree_cv < self.DEGREE_CV_THRESHOLD:
                sybil_score += 0.2
                reasons.append(f"uniform_degree_cv={degree_cv:.2f}")
            if avg_clustering > 0.8:
                sybil_score += 0.1
                reasons.append(f"high_clustering={avg_clustering:.2f}")
            
            if sybil_score >= 0.5:
                suspect_clusters.append({
                    "agents": sorted(cluster),
                    "size": len(cluster),
                    "sybil_score": round(sybil_score, 2),
                    "density": round(density, 3),
                    "cut_ratio": round(cut, 3),
                    "degree_cv": round(degree_cv, 3),
                    "avg_clustering": round(avg_clustering, 3),
                    "reasons": reasons,
                    "actual_sybils": sum(1 for a in cluster if network.agents[a].is_sybil)
                })
        
        # 4. Resistance scores
        resistance = {}
        for aid, agent in network.agents.items():
            # Resistance = identity strength × normalized degree diversity
            neighbors_diverse = len(set(
                network.agents[n].is_sybil for n in agent.trust_edges
                if n in network.agents
            ))
            resistance[aid] = round(agent.identity_strength * min(1.0, neighbors_diverse / 2), 3)
        
        return SybilDetectionResult(
            suspect_clusters=sorted(suspect_clusters, key=lambda x: -x["sybil_score"]),
            network_stats=stats,
            resistance_scores=resistance
        )
    
    def _network_stats(self, network: TrustNetwork) -> dict:
        degrees = [a.degree for a in network.agents.values()]
        honest = [a for a in network.agents.values() if not a.is_sybil]
        sybils = [a for a in network.agents.values() if a.is_sybil]
        
        return {
            "total_agents": len(network.agents),
            "honest_count": len(honest),
            "sybil_count": len(sybils),
            "avg_degree": round(sum(degrees) / max(len(degrees), 1), 2),
            "max_degree": max(degrees) if degrees else 0,
            "honest_avg_degree": round(
                sum(a.degree for a in honest) / max(len(honest), 1), 2
            ),
            "sybil_avg_degree": round(
                sum(a.degree for a in sybils) / max(len(sybils), 1), 2
            ) if sybils else 0,
        }
    
    def _find_dense_clusters(self, network: TrustNetwork, min_size: int = 3) -> list[set]:
        """Greedy: start from each high-degree node, expand to dense neighbors."""
        visited = set()
        clusters = []
        
        # Strategy: find cliques/near-cliques by looking for nodes where
        # most neighbors are also neighbors of each other
        sorted_agents = sorted(network.agents.values(), key=lambda a: -a.degree)
        
        for agent in sorted_agents:
            if agent.id in visited:
                continue
            
            # Start with agent + all mutual neighbors (neighbors that connect to each other)
            neighbors = agent.trust_edges & set(network.agents.keys())
            cluster = {agent.id}
            
            # Add neighbors that are well-connected to existing cluster
            for n in sorted(neighbors, key=lambda x: -len(network.agents[x].trust_edges & neighbors)):
                test = cluster | {n}
                if network.subgraph_density(test) >= 0.6:
                    cluster.add(n)
            
            if len(cluster) >= min_size:
                clusters.append(cluster)
                visited.update(cluster)
        
        return clusters


def build_demo_network() -> TrustNetwork:
    """Build a network with honest agents + a sybil ring."""
    random.seed(42)
    net = TrustNetwork()
    
    # 20 honest agents, sparse connections (power-law-ish)
    for i in range(20):
        net.add_agent(f"honest_{i}", is_sybil=False, 
                     identity_strength=random.uniform(0.5, 1.0))
    
    # Sparse honest edges (avg degree ~4)
    for i in range(20):
        n_edges = random.choices([2, 3, 4, 5, 8], weights=[15, 30, 30, 15, 10])[0]
        targets = random.sample([f"honest_{j}" for j in range(20) if j != i], 
                               min(n_edges, 19))
        for t in targets:
            net.add_edge(f"honest_{i}", t)
    
    # 6-node sybil ring (dense, mutual inflation)
    for i in range(6):
        net.add_agent(f"sybil_{i}", is_sybil=True, identity_strength=0.1)
    
    # Sybils: fully connected internally
    for i in range(6):
        for j in range(i + 1, 6):
            net.add_edge(f"sybil_{i}", f"sybil_{j}")
    
    # 2 attack edges (sybils reaching into honest network)
    net.add_edge("sybil_0", "honest_3")
    net.add_edge("sybil_1", "honest_7")
    
    return net


def demo():
    print("=" * 60)
    print("SYBIL DENSITY DETECTOR")
    print("=" * 60)
    print("AAMAS 2025 (Dehkordi & Zehmakan): resistance to attack requests")
    print("SybilRank (Cao 2012): random walks trapped in dense regions")
    print()
    
    net = build_demo_network()
    detector = SybilDensityDetector()
    result = detector.detect(net)
    
    print("NETWORK STATS:")
    print(json.dumps(result.network_stats, indent=2))
    print()
    
    print(f"SUSPECT CLUSTERS: {len(result.suspect_clusters)}")
    for cluster in result.suspect_clusters:
        print(f"\n  Cluster ({cluster['size']} agents):")
        print(f"    Agents: {cluster['agents']}")
        print(f"    Sybil score: {cluster['sybil_score']}")
        print(f"    Internal density: {cluster['density']}")
        print(f"    Cut ratio: {cluster['cut_ratio']}")
        print(f"    Degree CV: {cluster['degree_cv']}")
        print(f"    Avg clustering: {cluster['avg_clustering']}")
        print(f"    Reasons: {', '.join(cluster['reasons'])}")
        print(f"    Actual sybils in cluster: {cluster['actual_sybils']}/{cluster['size']}")
    
    # Verify sybil ring detected
    sybil_detected = any(
        c["actual_sybils"] >= 4 and c["sybil_score"] >= 0.5
        for c in result.suspect_clusters
    )
    
    print(f"\n{'✓' if sybil_detected else '✗'} Sybil ring detected: {sybil_detected}")
    
    # Show resistance distribution
    honest_resistance = [v for k, v in result.resistance_scores.items() if "honest" in k]
    sybil_resistance = [v for k, v in result.resistance_scores.items() if "sybil" in k]
    
    print(f"\nRESISTANCE SCORES:")
    print(f"  Honest avg: {sum(honest_resistance)/len(honest_resistance):.3f}")
    print(f"  Sybil avg:  {sum(sybil_resistance)/len(sybil_resistance):.3f}")
    print(f"  Gap: {sum(honest_resistance)/len(honest_resistance) - sum(sybil_resistance)/len(sybil_resistance):.3f}")
    
    assert sybil_detected, "Should detect sybil ring"
    print("\nALL CHECKS PASSED ✓")


if __name__ == "__main__":
    demo()
