#!/usr/bin/env python3
"""
sybil-density-detector.py — Density-based sybil detection for agent trust graphs.

Core insight (Clawk thread 2026-03-28): Sybil problem is a DENSITY problem.
- Honest agents form sparse graphs (trust is hard to earn)
- Sybils form dense cliques (mutual inflation = free edges)
- The density gap is the detection signal

Methods implemented:
1. Local density ratio — compare node's neighborhood density to graph average
2. Conductance cut — low conductance between regions = attack edge boundary
3. Resistance-aware preprocessing (Dehkordi & Zehmakan, AAMAS 2025) —
   revealing resistance of k nodes improves detection accuracy

Sources:
- Dehkordi & Zehmakan (AAMAS 2025, arxiv 2501.16624): User resistance to
  attack requests. Revealing resistance of k nodes as preprocessing improves
  SybilSCAR/SybilWalk/SybilMetric. Code: github.com/aSafarpoor/AAMAS2025-Paper
- Yu et al (2006): SybilGuard — random walks stay trapped in dense regions
- Cao et al (2012): SybilRank — trust propagation from known-good seeds
- Jia et al (2017): SybilWalk — random walk landing probabilities

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class TrustEdge:
    source: str
    target: str
    weight: float = 1.0
    mutual: bool = False  # Both directions exist


@dataclass
class DetectionResult:
    node: str
    classification: str  # "honest", "sybil", "uncertain"
    confidence: float
    local_density: float
    resistance_score: float
    signals: list[str] = field(default_factory=list)


class SybilDensityDetector:
    """
    Detects sybil clusters using density analysis.
    
    Honest graph properties (empirical, Yu 2006):
    - Power-law degree distribution
    - Average degree 5-8
    - Clustering coefficient ~0.3
    - Sparse inter-cluster edges
    
    Sybil graph properties:
    - Dense cliques (mutual attestation is free)
    - High clustering within cluster (>0.7)
    - Few attack edges to honest region
    - Synchronized creation times
    """
    
    def __init__(self):
        self.edges: list[TrustEdge] = []
        self.adjacency: dict[str, dict[str, float]] = defaultdict(dict)
        self.known_honest: set[str] = set()
        self.known_sybil: set[str] = set()
        self.resistance: dict[str, float] = {}  # AAMAS 2025: revealed resistance
    
    def add_edge(self, source: str, target: str, weight: float = 1.0):
        self.edges.append(TrustEdge(source, target, weight))
        self.adjacency[source][target] = weight
        # Check mutual
        if source in self.adjacency.get(target, {}):
            for e in self.edges:
                if e.source == target and e.target == source:
                    e.mutual = True
            self.edges[-1].mutual = True
    
    def set_known(self, honest: set[str] = None, sybil: set[str] = None):
        if honest:
            self.known_honest = honest
        if sybil:
            self.known_sybil = sybil
    
    def reveal_resistance(self, node: str, resistance: float):
        """
        AAMAS 2025 preprocessing: reveal that node has resistance score.
        Resistance = probability of rejecting sybil friendship/attestation requests.
        High resistance = strong identity layer = unlikely to accept sybil edges.
        """
        self.resistance[node] = resistance
    
    def local_density(self, node: str) -> float:
        """
        Local clustering coefficient — fraction of possible edges between
        neighbors that actually exist. Sybil cliques → high density.
        """
        neighbors = set(self.adjacency.get(node, {}).keys())
        if len(neighbors) < 2:
            return 0.0
        
        possible = len(neighbors) * (len(neighbors) - 1) / 2
        actual = 0
        neighbor_list = list(neighbors)
        for i in range(len(neighbor_list)):
            for j in range(i + 1, len(neighbor_list)):
                if neighbor_list[j] in self.adjacency.get(neighbor_list[i], {}):
                    actual += 1
        
        return actual / possible
    
    def mutual_edge_ratio(self, node: str) -> float:
        """Fraction of edges that are mutual. Sybils have high mutual ratios."""
        neighbors = self.adjacency.get(node, {})
        if not neighbors:
            return 0.0
        
        mutual = sum(1 for n in neighbors if node in self.adjacency.get(n, {}))
        return mutual / len(neighbors)
    
    def conductance(self, cluster: set[str]) -> float:
        """
        Conductance of a cluster — ratio of external edges to total edges.
        Low conductance = isolated cluster (sybil pattern).
        """
        internal = 0
        external = 0
        
        for node in cluster:
            for neighbor, weight in self.adjacency.get(node, {}).items():
                if neighbor in cluster:
                    internal += 1
                else:
                    external += 1
        
        total = internal + external
        if total == 0:
            return 0.0
        return external / total
    
    def random_walk_from_seeds(self, steps: int = 10, walks: int = 100) -> dict[str, float]:
        """
        SybilRank-inspired: random walks from known honest seeds.
        Honest nodes get high landing probability. Sybil nodes get low
        (walks get trapped in sybil region rarely reaching honest seeds).
        """
        all_nodes = set(self.adjacency.keys())
        landing_counts = defaultdict(int)
        
        if not self.known_honest:
            return {n: 0.5 for n in all_nodes}
        
        for _ in range(walks):
            current = random.choice(list(self.known_honest))
            for _ in range(steps):
                neighbors = list(self.adjacency.get(current, {}).keys())
                if not neighbors:
                    break
                current = random.choice(neighbors)
                landing_counts[current] += 1
        
        total_landings = sum(landing_counts.values()) or 1
        return {n: landing_counts.get(n, 0) / total_landings for n in all_nodes}
    
    def detect(self) -> list[DetectionResult]:
        """Run full detection pipeline."""
        all_nodes = set(self.adjacency.keys())
        
        # Step 1: Compute graph-wide stats
        densities = {n: self.local_density(n) for n in all_nodes}
        avg_density = sum(densities.values()) / max(len(densities), 1)
        
        mutual_ratios = {n: self.mutual_edge_ratio(n) for n in all_nodes}
        
        # Step 2: Random walk scores
        walk_scores = self.random_walk_from_seeds()
        
        # Step 3: Classify each node
        results = []
        for node in sorted(all_nodes):
            signals = []
            sybil_score = 0.0
            
            density = densities[node]
            mutual = mutual_ratios[node]
            walk = walk_scores.get(node, 0)
            
            # Signal 1: Abnormally high local density (sybil clique)
            if density > 0.7 and avg_density < 0.5:
                sybil_score += 0.3
                signals.append(f"high_density={density:.2f} (avg={avg_density:.2f})")
            
            # Signal 2: High mutual edge ratio
            if mutual > 0.9:
                sybil_score += 0.2
                signals.append(f"high_mutual={mutual:.2f}")
            
            # Signal 3: Low random walk score from honest seeds
            if walk < 0.001 and self.known_honest:
                sybil_score += 0.3
                signals.append(f"low_walk_score={walk:.4f}")
            
            # Signal 4: Known labels
            if node in self.known_honest:
                sybil_score = 0.0
                signals = ["known_honest"]
            elif node in self.known_sybil:
                sybil_score = 1.0
                signals = ["known_sybil"]
            
            # Signal 5: AAMAS 2025 resistance preprocessing
            resistance = self.resistance.get(node, 0.5)
            if node in self.resistance:
                if resistance > 0.8:
                    sybil_score *= 0.5  # High resistance = less likely sybil
                    signals.append(f"high_resistance={resistance:.2f}")
                elif resistance < 0.2:
                    sybil_score += 0.2
                    signals.append(f"low_resistance={resistance:.2f}")
            
            # Classify
            if sybil_score > 0.5:
                classification = "sybil"
            elif sybil_score < 0.2:
                classification = "honest"
            else:
                classification = "uncertain"
            
            results.append(DetectionResult(
                node=node,
                classification=classification,
                confidence=1.0 - abs(0.5 - sybil_score) * 2 if classification == "uncertain" else max(sybil_score, 1 - sybil_score),
                local_density=density,
                resistance_score=resistance,
                signals=signals
            ))
        
        return results


def demo():
    random.seed(42)
    detector = SybilDensityDetector()
    
    # Build honest network: sparse, power-law-ish
    honest_nodes = [f"honest_{i}" for i in range(20)]
    for i, node in enumerate(honest_nodes):
        # Each honest node connects to 2-5 others (sparse)
        n_edges = random.randint(2, 5)
        targets = random.sample([n for n in honest_nodes if n != node], min(n_edges, len(honest_nodes) - 1))
        for t in targets:
            detector.add_edge(node, t)
    
    # Build sybil clique: dense, all mutual
    sybil_nodes = [f"sybil_{i}" for i in range(8)]
    for i, s1 in enumerate(sybil_nodes):
        for j, s2 in enumerate(sybil_nodes):
            if i != j:
                detector.add_edge(s1, s2)  # Full clique
    
    # Attack edges: sybils connect to a few honest nodes
    for s in sybil_nodes[:3]:
        target = random.choice(honest_nodes)
        detector.add_edge(s, target)
    
    # Set known labels (3 honest seeds)
    detector.set_known(
        honest={honest_nodes[0], honest_nodes[1], honest_nodes[2]},
        sybil={sybil_nodes[0]}
    )
    
    # AAMAS 2025: reveal resistance of some nodes
    for n in honest_nodes[:5]:
        detector.reveal_resistance(n, random.uniform(0.7, 0.95))
    for n in sybil_nodes[:3]:
        detector.reveal_resistance(n, random.uniform(0.05, 0.2))
    
    print("=" * 60)
    print("SYBIL DENSITY DETECTION")
    print(f"Honest nodes: {len(honest_nodes)}, Sybil nodes: {len(sybil_nodes)}")
    print(f"Known honest seeds: 3, Known sybil: 1")
    print(f"Resistance revealed: 8 nodes (AAMAS 2025 preprocessing)")
    print("=" * 60)
    
    results = detector.detect()
    
    # Summary
    correct = 0
    total = 0
    for r in results:
        is_actually_sybil = r.node.startswith("sybil_")
        is_actually_honest = r.node.startswith("honest_")
        
        if r.classification == "sybil" and is_actually_sybil:
            correct += 1
        elif r.classification == "honest" and is_actually_honest:
            correct += 1
        
        if r.classification != "uncertain":
            total += 1
    
    accuracy = correct / max(total, 1)
    
    print(f"\nAccuracy (excl. uncertain): {accuracy:.1%} ({correct}/{total})")
    
    sybil_detected = [r for r in results if r.classification == "sybil"]
    honest_detected = [r for r in results if r.classification == "honest"]
    uncertain = [r for r in results if r.classification == "uncertain"]
    
    print(f"Classified sybil: {len(sybil_detected)}")
    print(f"Classified honest: {len(honest_detected)}")
    print(f"Uncertain: {len(uncertain)}")
    
    print("\n--- Sybil detections ---")
    for r in sybil_detected:
        print(f"  {r.node}: density={r.local_density:.2f} resistance={r.resistance_score:.2f} signals={r.signals}")
    
    print("\n--- False negatives (sybils classified honest/uncertain) ---")
    for r in results:
        if r.node.startswith("sybil_") and r.classification != "sybil":
            print(f"  {r.node}: {r.classification} density={r.local_density:.2f} signals={r.signals}")
    
    # Conductance analysis
    sybil_set = set(sybil_nodes)
    honest_set = set(honest_nodes)
    
    print(f"\nConductance (sybil cluster): {detector.conductance(sybil_set):.3f}")
    print(f"Conductance (honest cluster): {detector.conductance(honest_set):.3f}")
    print("Low conductance = isolated cluster = sybil signal")
    
    print(f"\nDensity gap: honest_avg={sum(detector.local_density(n) for n in honest_nodes)/len(honest_nodes):.3f} vs sybil_avg={sum(detector.local_density(n) for n in sybil_nodes)/len(sybil_nodes):.3f}")
    
    assert accuracy > 0.7, f"Accuracy too low: {accuracy}"
    print("\n✓ ALL CHECKS PASSED")


if __name__ == "__main__":
    demo()
