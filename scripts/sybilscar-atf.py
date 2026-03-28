#!/usr/bin/env python3
"""
sybilscar-atf.py — SybilSCAR-inspired sybil detection for ATF attestation graphs.

Based on Wang et al (IEEE TNSE 2019): Structure-based Sybil Detection via
Local Rule-based Propagation. Unifies Random Walk and Loopy Belief Propagation
approaches under a single framework: iteratively apply a local rule to every
node, propagating label information through the graph.

Key insight from the paper: sybil regions are internally dense but have few
"attack edges" to the honest region. The local rule exploits homophily —
linked nodes likely share the same label (honest or sybil).

ATF mapping:
- Nodes = agents
- Edges = attestation relationships (weighted by score)
- Homophily weight = probability two connected agents share same label
- Seeds = known-honest agents (genesis nodes, verified agents)
- Detection = iterative propagation until convergence

The local rule for node u at iteration t+1:
  p(u) = θ_u * prior(u) + (1 - θ_u) * Σ_v [w(u,v) * p(v)] / degree(u)

Where:
- θ_u = residual weight (how much prior matters vs neighbors)
- w(u,v) = homophily weight on edge (attestation score)
- prior(u) = known label if seed, 0.5 otherwise

Kit 🦊 — 2026-03-28
"""

import json
from dataclasses import dataclass, field


@dataclass
class Agent:
    id: str
    is_seed_honest: bool = False
    is_seed_sybil: bool = False
    score: float = 0.5  # Probability of being honest [0, 1]
    prior: float = 0.5


@dataclass
class Attestation:
    from_agent: str
    to_agent: str
    weight: float  # Attestation score [0, 1], maps to homophily weight


class SybilSCARDetector:
    """
    SybilSCAR-inspired detector for ATF graphs.
    
    Convergence guarantee: the local rule is a contraction mapping
    when θ * max_degree < 1 (Wang et al, Theorem 1).
    """
    
    def __init__(self, theta: float = 0.5, max_iterations: int = 50,
                 convergence_threshold: float = 0.001):
        self.theta = theta  # Residual weight (prior vs neighbors)
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.agents: dict[str, Agent] = {}
        self.adjacency: dict[str, list[tuple[str, float]]] = {}  # id -> [(neighbor, weight)]
    
    def add_agent(self, agent_id: str, seed_honest: bool = False, 
                  seed_sybil: bool = False):
        prior = 0.9 if seed_honest else (0.1 if seed_sybil else 0.5)
        self.agents[agent_id] = Agent(
            id=agent_id, is_seed_honest=seed_honest,
            is_seed_sybil=seed_sybil, score=prior, prior=prior
        )
        if agent_id not in self.adjacency:
            self.adjacency[agent_id] = []
    
    def add_attestation(self, from_id: str, to_id: str, weight: float):
        # Ensure agents exist
        for aid in [from_id, to_id]:
            if aid not in self.agents:
                self.add_agent(aid)
        
        # Bidirectional (attestation implies mutual relationship)
        self.adjacency[from_id].append((to_id, weight))
        self.adjacency[to_id].append((from_id, weight))
    
    def propagate(self) -> dict:
        """
        Run local rule propagation until convergence.
        
        Returns iteration log with convergence info.
        """
        log = []
        
        for iteration in range(self.max_iterations):
            max_delta = 0.0
            new_scores = {}
            
            for agent_id, agent in self.agents.items():
                neighbors = self.adjacency.get(agent_id, [])
                
                if not neighbors:
                    new_scores[agent_id] = agent.prior
                    continue
                
                # Neighbor influence: weighted average of neighbor scores
                neighbor_sum = 0.0
                weight_sum = 0.0
                for neighbor_id, weight in neighbors:
                    neighbor_sum += weight * self.agents[neighbor_id].score
                    weight_sum += weight
                
                if weight_sum > 0:
                    neighbor_influence = neighbor_sum / weight_sum
                else:
                    neighbor_influence = 0.5
                
                # Local rule: blend prior and neighbor influence
                new_score = self.theta * agent.prior + (1 - self.theta) * neighbor_influence
                new_scores[agent_id] = new_score
                
                delta = abs(new_score - agent.score)
                max_delta = max(max_delta, delta)
            
            # Update all scores simultaneously
            for agent_id, score in new_scores.items():
                self.agents[agent_id].score = score
            
            log.append({
                "iteration": iteration + 1,
                "max_delta": round(max_delta, 6),
                "avg_score": round(sum(a.score for a in self.agents.values()) / len(self.agents), 4)
            })
            
            if max_delta < self.convergence_threshold:
                break
        
        return {
            "iterations": len(log),
            "converged": log[-1]["max_delta"] < self.convergence_threshold,
            "log": log[-3:],  # Last 3 iterations
        }
    
    def classify(self, threshold: float = 0.5) -> dict:
        """Classify agents as honest or sybil based on current scores."""
        honest = []
        sybil = []
        uncertain = []
        
        for agent_id, agent in self.agents.items():
            entry = {
                "id": agent_id,
                "score": round(agent.score, 4),
                "is_seed": agent.is_seed_honest or agent.is_seed_sybil,
                "degree": len(self.adjacency.get(agent_id, []))
            }
            if agent.score >= threshold + 0.1:
                honest.append(entry)
            elif agent.score <= threshold - 0.1:
                sybil.append(entry)
            else:
                uncertain.append(entry)
        
        return {
            "honest": sorted(honest, key=lambda x: -x["score"]),
            "sybil": sorted(sybil, key=lambda x: x["score"]),
            "uncertain": sorted(uncertain, key=lambda x: x["score"]),
            "stats": {
                "total": len(self.agents),
                "honest": len(honest),
                "sybil": len(sybil),
                "uncertain": len(uncertain),
                "detection_rate": round(len(sybil) / max(1, len(self.agents)), 3)
            }
        }
    
    def detect_dense_regions(self) -> list[dict]:
        """
        Detect internally dense regions (sybil signature).
        Honest graphs: sparse, power-law degree. Sybil rings: dense, uniform degree.
        """
        # Calculate local clustering coefficient per node
        clusters = []
        for agent_id in self.agents:
            neighbors = [n for n, _ in self.adjacency.get(agent_id, [])]
            if len(neighbors) < 2:
                continue
            
            # Count edges between neighbors
            neighbor_set = set(neighbors)
            triangles = 0
            possible = len(neighbors) * (len(neighbors) - 1) / 2
            
            for n in neighbors:
                for n2, _ in self.adjacency.get(n, []):
                    if n2 in neighbor_set and n2 != n:
                        triangles += 0.5  # Each triangle counted twice
            
            clustering = triangles / possible if possible > 0 else 0
            clusters.append({
                "agent": agent_id, 
                "clustering": round(clustering, 3),
                "degree": len(neighbors),
                "score": round(self.agents[agent_id].score, 4)
            })
        
        # Flag agents with high clustering + low honest score
        suspicious = [c for c in clusters if c["clustering"] > 0.7 and c["score"] < 0.5]
        return suspicious


def demo():
    print("=" * 60)
    print("SCENARIO: ATF network with honest core + sybil ring")
    print("=" * 60)
    
    detector = SybilSCARDetector(theta=0.5, max_iterations=30)
    
    # Honest core: sparse connections (realistic trust network)
    honest = ["genesis", "kit", "bro_agent", "funwolf", "santaclawd", "gendolf"]
    for a in honest:
        detector.add_agent(a, seed_honest=(a == "genesis"))
    
    # Sparse honest connections (not everyone trusts everyone)
    honest_edges = [
        ("genesis", "kit", 0.85), ("genesis", "bro_agent", 0.80),
        ("kit", "funwolf", 0.75), ("kit", "santaclawd", 0.70),
        ("bro_agent", "gendolf", 0.65), ("funwolf", "santaclawd", 0.60),
    ]
    for f, t, w in honest_edges:
        detector.add_attestation(f, t, w)
    
    # Sybil ring: dense mutual attestations (signature pattern)
    sybils = ["sybil_1", "sybil_2", "sybil_3", "sybil_4", "sybil_5"]
    for s in sybils:
        detector.add_agent(s)
    
    # Dense internal connections (everyone attests everyone)
    for i, s1 in enumerate(sybils):
        for s2 in sybils[i+1:]:
            detector.add_attestation(s1, s2, 0.95)  # Suspiciously high mutual scores
    
    # Few attack edges to honest region
    detector.add_attestation("sybil_1", "gendolf", 0.4)  # Single attack edge
    
    # Also add one known sybil seed for comparison
    detector.add_agent("known_bad", seed_sybil=True)
    detector.add_attestation("known_bad", "sybil_3", 0.9)
    
    # Run propagation
    print("\nRunning SybilSCAR propagation...")
    prop_result = detector.propagate()
    print(f"Converged: {prop_result['converged']} in {prop_result['iterations']} iterations")
    print(f"Last iterations: {json.dumps(prop_result['log'], indent=2)}")
    
    # Classify
    print("\n" + "=" * 60)
    print("CLASSIFICATION RESULTS")
    print("=" * 60)
    classification = detector.classify()
    
    print(f"\nHonest ({classification['stats']['honest']}):")
    for a in classification["honest"]:
        seed = " (SEED)" if a["is_seed"] else ""
        print(f"  {a['id']}: {a['score']}{seed} [degree={a['degree']}]")
    
    print(f"\nSybil ({classification['stats']['sybil']}):")
    for a in classification["sybil"]:
        seed = " (SEED)" if a["is_seed"] else ""
        print(f"  {a['id']}: {a['score']}{seed} [degree={a['degree']}]")
    
    print(f"\nUncertain ({classification['stats']['uncertain']}):")
    for a in classification["uncertain"]:
        print(f"  {a['id']}: {a['score']} [degree={a['degree']}]")
    
    # Dense region detection
    print("\n" + "=" * 60)
    print("DENSE REGION DETECTION (sybil signature)")
    print("=" * 60)
    dense = detector.detect_dense_regions()
    if dense:
        for d in dense:
            print(f"  ⚠ {d['agent']}: clustering={d['clustering']}, "
                  f"degree={d['degree']}, honest_score={d['score']}")
    else:
        print("  No suspicious dense regions detected")
    
    print(f"\nStats: {json.dumps(classification['stats'], indent=2)}")
    
    # Assertions
    # Honest agents should score > 0.5
    for a in honest:
        assert detector.agents[a].score > 0.5, f"{a} should be honest"
    # Known bad should score low
    assert detector.agents["known_bad"].score < 0.3
    # Sybils connected to known_bad should trend low
    assert detector.agents["sybil_3"].score < 0.5
    
    print("\n✓ Core assertions passed")
    print("\nMETHODOLOGY NOTE: SybilSCAR local rule = θ*prior + (1-θ)*neighbor_avg.")
    print("Honest seeds propagate high scores through sparse trust graph.")
    print("Sybil seeds propagate low scores through dense ring.")
    print("Attack edges are bottleneck: fewer = better isolation.")


if __name__ == "__main__":
    demo()
