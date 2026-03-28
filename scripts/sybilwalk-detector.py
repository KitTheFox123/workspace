#!/usr/bin/env python3
"""
sybilwalk-detector.py — SybilWalk-inspired random walk sybil detection for ATF.

Based on Jia, Wang & Gong (Iowa State): "Random Walk based Fake Account 
Detection in Online Social Networks." SybilWalk uses BOTH labeled benign 
and labeled sybil seeds, achieving 1.3% FPR / 17.3% FNR on Twitter.

Core insight: random walks from honest seeds stay in the honest region
(fast-mixing honest subgraph). Random walks from sybil seeds stay in the
sybil region (dense sybil clique). The ATTACK SURFACE = edges between 
honest and sybil regions. Fewer cross-edges → better separation.

ATF mapping:
- Honest seeds = agents with full trust stack (addressing + identity + trust)
- Sybil seeds = known-bad agents (caught by burst detector, density analysis)
- Edges = attestation relationships
- Walk probability = trust score on attestation
- Attack surface = attestations between honest and sybil regions

Kit 🦊 — 2026-03-28
"""

import random
import math
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Agent:
    id: str
    is_sybil: bool = False
    benign_score: float = 0.0  # Higher = more likely honest
    sybil_score: float = 0.0   # Higher = more likely sybil
    final_label: str = "unknown"


class TrustGraph:
    """Weighted directed graph of attestation relationships."""
    
    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.edges: dict[str, dict[str, float]] = defaultdict(dict)  # from → {to: weight}
        self.reverse_edges: dict[str, dict[str, float]] = defaultdict(dict)
    
    def add_agent(self, agent_id: str, is_sybil: bool = False):
        self.agents[agent_id] = Agent(id=agent_id, is_sybil=is_sybil)
    
    def add_attestation(self, attester: str, subject: str, score: float):
        """Add weighted edge (attestation)."""
        self.edges[attester][subject] = score
        self.reverse_edges[subject][attester] = score
    
    def get_neighbors(self, agent_id: str) -> dict[str, float]:
        return self.edges.get(agent_id, {})
    
    def degree(self, agent_id: str) -> int:
        return len(self.edges.get(agent_id, {})) + len(self.reverse_edges.get(agent_id, {}))


class SybilWalkDetector:
    """
    Two-pronged random walk sybil detection.
    
    Walk 1: Benign seeds propagate "benign-ness" scores.
    Walk 2: Sybil seeds propagate "sybil-ness" scores.
    Final classification uses both scores.
    """
    
    def __init__(self, graph: TrustGraph, walk_length: int = 10, 
                 num_walks: int = 1000, restart_prob: float = 0.15):
        self.graph = graph
        self.walk_length = walk_length
        self.num_walks = num_walks
        self.restart_prob = restart_prob  # Random restart probability
    
    def _random_walk(self, start: str, direction: str = "forward") -> list[str]:
        """Single random walk from start node."""
        path = [start]
        current = start
        
        for _ in range(self.walk_length):
            # Random restart
            if random.random() < self.restart_prob:
                current = start
                path.append(current)
                continue
            
            if direction == "forward":
                neighbors = self.graph.get_neighbors(current)
            else:
                neighbors = self.graph.reverse_edges.get(current, {})
            
            if not neighbors:
                break
            
            # Weighted random step (higher trust score = higher probability)
            agents = list(neighbors.keys())
            weights = list(neighbors.values())
            total = sum(weights)
            if total == 0:
                break
            weights = [w / total for w in weights]
            
            current = random.choices(agents, weights=weights, k=1)[0]
            path.append(current)
        
        return path
    
    def propagate_benign(self, benign_seeds: list[str]):
        """Propagate benign scores from honest seeds via random walks."""
        visit_counts = defaultdict(int)
        
        for _ in range(self.num_walks):
            seed = random.choice(benign_seeds)
            path = self._random_walk(seed, direction="forward")
            for node in path:
                visit_counts[node] += 1
        
        # Normalize by degree (higher-degree nodes visited more by chance)
        max_visits = max(visit_counts.values()) if visit_counts else 1
        for agent_id in self.graph.agents:
            raw = visit_counts.get(agent_id, 0)
            degree = max(1, self.graph.degree(agent_id))
            self.graph.agents[agent_id].benign_score = (raw / max_visits) / (1 + math.log(degree))
    
    def propagate_sybil(self, sybil_seeds: list[str]):
        """Propagate sybil scores from known-bad seeds via random walks."""
        visit_counts = defaultdict(int)
        
        for _ in range(self.num_walks):
            seed = random.choice(sybil_seeds)
            path = self._random_walk(seed, direction="forward")
            for node in path:
                visit_counts[node] += 1
        
        max_visits = max(visit_counts.values()) if visit_counts else 1
        for agent_id in self.graph.agents:
            raw = visit_counts.get(agent_id, 0)
            degree = max(1, self.graph.degree(agent_id))
            self.graph.agents[agent_id].sybil_score = (raw / max_visits) / (1 + math.log(degree))
    
    def classify(self, benign_seeds: list[str], sybil_seeds: list[str],
                 threshold: float = 0.0) -> dict:
        """
        Classify all agents using both benign and sybil walks.
        
        Score = benign_score - sybil_score
        Above threshold → honest. Below → sybil.
        """
        self.propagate_benign(benign_seeds)
        self.propagate_sybil(sybil_seeds)
        
        results = {"honest": [], "sybil": [], "uncertain": []}
        
        for agent_id, agent in self.graph.agents.items():
            if agent_id in benign_seeds:
                agent.final_label = "honest (seed)"
                results["honest"].append(agent_id)
                continue
            if agent_id in sybil_seeds:
                agent.final_label = "sybil (seed)"
                results["sybil"].append(agent_id)
                continue
            
            combined = agent.benign_score - agent.sybil_score
            if combined > threshold:
                agent.final_label = "honest"
                results["honest"].append(agent_id)
            elif combined < -threshold:
                agent.final_label = "sybil"
                results["sybil"].append(agent_id)
            else:
                agent.final_label = "uncertain"
                results["uncertain"].append(agent_id)
        
        return results
    
    def attack_surface(self) -> dict:
        """Measure attack surface = cross-edges between honest and sybil regions."""
        cross_edges = 0
        honest_edges = 0
        sybil_edges = 0
        
        for attester, subjects in self.graph.edges.items():
            a = self.graph.agents.get(attester)
            for subject in subjects:
                s = self.graph.agents.get(subject)
                if not a or not s:
                    continue
                
                a_honest = a.final_label in ("honest", "honest (seed)")
                s_honest = s.final_label in ("honest", "honest (seed)")
                
                if a_honest and s_honest:
                    honest_edges += 1
                elif not a_honest and not s_honest:
                    sybil_edges += 1
                else:
                    cross_edges += 1
        
        total = honest_edges + sybil_edges + cross_edges
        return {
            "cross_edges": cross_edges,
            "honest_edges": honest_edges,
            "sybil_edges": sybil_edges,
            "total_edges": total,
            "attack_surface_ratio": round(cross_edges / max(total, 1), 4)
        }


def build_test_graph(n_honest: int = 50, n_sybil: int = 20, 
                     honest_density: float = 0.08, sybil_density: float = 0.6,
                     cross_density: float = 0.02) -> TrustGraph:
    """
    Build a test graph with honest (sparse) and sybil (dense) regions.
    
    Honest: power-law-ish, sparse, realistic attestation patterns.
    Sybil: dense mutual attestation (free trust inflation).
    Cross: few edges between regions (attack surface).
    """
    g = TrustGraph()
    
    # Create agents
    honest_ids = [f"honest_{i}" for i in range(n_honest)]
    sybil_ids = [f"sybil_{i}" for i in range(n_sybil)]
    
    for aid in honest_ids:
        g.add_agent(aid, is_sybil=False)
    for aid in sybil_ids:
        g.add_agent(aid, is_sybil=True)
    
    # Honest edges (sparse, realistic trust scores)
    for i, a in enumerate(honest_ids):
        for j, b in enumerate(honest_ids):
            if i != j and random.random() < honest_density:
                score = random.uniform(0.5, 0.95)  # Earned trust varies
                g.add_attestation(a, b, score)
    
    # Sybil edges (dense, inflated scores)
    for i, a in enumerate(sybil_ids):
        for j, b in enumerate(sybil_ids):
            if i != j and random.random() < sybil_density:
                score = random.uniform(0.85, 1.0)  # Mutual inflation
                g.add_attestation(a, b, score)
    
    # Cross edges (attack surface)
    for a in sybil_ids:
        for b in honest_ids:
            if random.random() < cross_density:
                score = random.uniform(0.3, 0.7)
                g.add_attestation(a, b, score)
    
    return g


def demo():
    random.seed(42)
    random.seed(42)
    
    print("=" * 60)
    print("SYBILWALK DETECTOR — ATF Trust Graph")
    print("=" * 60)
    
    # Build graph
    g = build_test_graph(n_honest=50, n_sybil=20)
    
    total_edges = sum(len(v) for v in g.edges.values())
    print(f"Agents: {len(g.agents)} (50 honest, 20 sybil)")
    print(f"Total edges: {total_edges}")
    print()
    
    # Seeds: 5 known honest, 3 known sybil
    benign_seeds = [f"honest_{i}" for i in range(5)]
    sybil_seeds = [f"sybil_{i}" for i in range(3)]
    
    print(f"Benign seeds: {len(benign_seeds)}")
    print(f"Sybil seeds: {len(sybil_seeds)}")
    print()
    
    # Run detection
    detector = SybilWalkDetector(g, walk_length=15, num_walks=2000, restart_prob=0.15)
    results = detector.classify(benign_seeds, sybil_seeds, threshold=0.01)
    
    # Compute accuracy
    tp = sum(1 for aid in results["sybil"] if g.agents[aid].is_sybil)
    fp = sum(1 for aid in results["sybil"] if not g.agents[aid].is_sybil)
    tn = sum(1 for aid in results["honest"] if not g.agents[aid].is_sybil)
    fn = sum(1 for aid in results["honest"] if g.agents[aid].is_sybil)
    uncertain = len(results["uncertain"])
    
    total_classified = tp + fp + tn + fn
    accuracy = (tp + tn) / max(total_classified, 1)
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)
    
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Classified honest: {len(results['honest'])}")
    print(f"Classified sybil: {len(results['sybil'])}")
    print(f"Uncertain: {uncertain}")
    print()
    print(f"True positives (sybil→sybil): {tp}")
    print(f"False positives (honest→sybil): {fp}")
    print(f"True negatives (honest→honest): {tn}")
    print(f"False negatives (sybil→honest): {fn}")
    print()
    print(f"Accuracy: {accuracy:.1%}")
    print(f"FPR: {fpr:.1%}")
    print(f"FNR: {fnr:.1%}")
    
    # Attack surface
    surface = detector.attack_surface()
    print()
    print(f"Attack surface: {surface['cross_edges']} cross-edges ({surface['attack_surface_ratio']:.1%} of total)")
    print(f"Honest edges: {surface['honest_edges']}")
    print(f"Sybil edges: {surface['sybil_edges']}")
    
    print()
    print("KEY: Sparse honest + dense sybil = separable by random walks.")
    print("Attack surface width determines detection quality.")
    print("ATF: minimize cross-attestations via identity layer requirements.")
    
    # Assertions
    assert accuracy > 0.7, f"Accuracy too low: {accuracy}"
    assert fpr < 0.15, f"FPR too high: {fpr}"
    print("\n✓ ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    demo()
