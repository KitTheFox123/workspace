#!/usr/bin/env python3
"""
sybil-density-detector.py — Graph density-based sybil detection for ATF.

Core insight from Clawk thread (2026-03-28): "honest agents form sparse graphs
(trust is hard to earn). sybils form dense ones (free mutual inflation)."

Uses SybilRank-inspired approach (Cao et al, 2012): short random walks from
known-honest seeds stay in the honest region; walks entering sybil clusters
get trapped in dense mutual attestation. Landing probability after O(log n)
steps = trust score.

Also incorporates Dehkordi & Zehmakan (AAMAS 2025, arxiv 2501.16624):
resistance of nodes to attack edges. In ATF: identity layer strength
(DKIM chain days × behavioral consistency) = resistance score.

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
    resistance: float = 0.5  # Identity layer strength [0,1]
    dkim_days: int = 0
    trust_rank: float = 0.0  # Computed by random walk


class TrustGraph:
    """Directed attestation graph with sybil detection."""
    
    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.edges: dict[str, dict[str, float]] = defaultdict(dict)  # from -> {to: weight}
        self.reverse: dict[str, set[str]] = defaultdict(set)  # to -> {from}
    
    def add_agent(self, agent: Agent):
        self.agents[agent.id] = agent
    
    def add_attestation(self, attester: str, subject: str, score: float = 1.0):
        self.edges[attester][subject] = score
        self.reverse[subject].add(attester)
    
    def degree(self, agent_id: str) -> tuple[int, int]:
        """(out_degree, in_degree)"""
        out_d = len(self.edges.get(agent_id, {}))
        in_d = len(self.reverse.get(agent_id, set()))
        return out_d, in_d
    
    def local_density(self, agent_id: str) -> float:
        """
        Clustering coefficient for agent's neighborhood.
        Sybil clusters have high density (everyone attests everyone).
        Honest networks have lower density (selective attestation).
        """
        neighbors = set(self.edges.get(agent_id, {}).keys())
        neighbors.update(self.reverse.get(agent_id, set()))
        neighbors.discard(agent_id)
        
        if len(neighbors) < 2:
            return 0.0
        
        # Count edges between neighbors
        neighbor_edges = 0
        for n1 in neighbors:
            for n2 in neighbors:
                if n1 != n2 and n2 in self.edges.get(n1, {}):
                    neighbor_edges += 1
        
        max_edges = len(neighbors) * (len(neighbors) - 1)
        return neighbor_edges / max_edges if max_edges > 0 else 0.0
    
    def random_walk_rank(self, seeds: list[str], walk_length: int = 10, 
                         num_walks: int = 1000) -> dict[str, float]:
        """
        SybilRank-inspired: start random walks from honest seeds.
        Landing probability = trust score.
        Walks get trapped in dense sybil clusters (low landing prob
        for honest nodes from sybil walks).
        """
        visit_count: dict[str, int] = defaultdict(int)
        total_visits = 0
        
        for _ in range(num_walks):
            # Start from random seed
            current = random.choice(seeds)
            
            for _ in range(walk_length):
                visit_count[current] += 1
                total_visits += 1
                
                # Walk to random neighbor (outgoing attestation)
                neighbors = list(self.edges.get(current, {}).keys())
                # Also consider reverse edges (who attests me)
                reverse_n = list(self.reverse.get(current, set()))
                all_neighbors = neighbors + reverse_n
                
                if not all_neighbors:
                    break  # Dead end, restart
                
                current = random.choice(all_neighbors)
        
        # Normalize
        ranks = {}
        for aid in self.agents:
            ranks[aid] = visit_count.get(aid, 0) / max(total_visits, 1)
        
        return ranks
    
    def detect_sybils(self, seeds: list[str], 
                      density_threshold: float = 0.7,
                      rank_threshold: float = None) -> dict:
        """
        Combined detection: local density + random walk rank + resistance.
        
        Sybil indicators:
        1. High local density (everyone attests everyone)
        2. Low random walk rank from honest seeds
        3. Low resistance (no identity layer evidence)
        """
        ranks = self.random_walk_rank(seeds)
        
        # Auto-threshold: median rank of seeds
        if rank_threshold is None:
            seed_ranks = [ranks.get(s, 0) for s in seeds]
            rank_threshold = sorted(seed_ranks)[len(seed_ranks) // 2] * 0.3
        
        results = {}
        for aid, agent in self.agents.items():
            density = self.local_density(aid)
            rank = ranks.get(aid, 0)
            out_d, in_d = self.degree(aid)
            
            # Sybil score: high density + low rank + low resistance = sybil
            sybil_signals = 0
            if density > density_threshold:
                sybil_signals += 1
            if rank < rank_threshold and aid not in seeds:
                sybil_signals += 1
            if agent.resistance < 0.3:
                sybil_signals += 1
            # Reciprocity check: mutual attestation ratio
            mutual = 0
            for target in self.edges.get(aid, {}):
                if aid in self.edges.get(target, {}):
                    mutual += 1
            reciprocity = mutual / max(out_d, 1)
            if reciprocity > 0.8 and out_d > 2:
                sybil_signals += 1
            
            classified_sybil = sybil_signals >= 2
            
            results[aid] = {
                "classified_sybil": classified_sybil,
                "actual_sybil": agent.is_sybil,
                "correct": classified_sybil == agent.is_sybil,
                "sybil_signals": sybil_signals,
                "density": round(density, 3),
                "rank": round(rank, 6),
                "resistance": agent.resistance,
                "reciprocity": round(reciprocity, 3),
                "degree": {"out": out_d, "in": in_d}
            }
        
        # Compute accuracy
        correct = sum(1 for r in results.values() if r["correct"])
        total = len(results)
        tp = sum(1 for r in results.values() if r["classified_sybil"] and r["actual_sybil"])
        fp = sum(1 for r in results.values() if r["classified_sybil"] and not r["actual_sybil"])
        fn = sum(1 for r in results.values() if not r["classified_sybil"] and r["actual_sybil"])
        tn = sum(1 for r in results.values() if not r["classified_sybil"] and not r["actual_sybil"])
        
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 0.001)
        
        return {
            "agents": results,
            "metrics": {
                "accuracy": round(correct / max(total, 1), 3),
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
                "tp": tp, "fp": fp, "fn": fn, "tn": tn
            }
        }


def build_test_network(n_honest: int = 20, n_sybil: int = 10, 
                       attack_edges: int = 3) -> tuple[TrustGraph, list[str]]:
    """Build a test network with honest sparse + sybil dense clusters."""
    g = TrustGraph()
    
    honest_ids = [f"honest_{i}" for i in range(n_honest)]
    sybil_ids = [f"sybil_{i}" for i in range(n_sybil)]
    
    # Add honest agents (high resistance, DKIM history)
    for hid in honest_ids:
        g.add_agent(Agent(
            id=hid, is_sybil=False,
            resistance=random.uniform(0.5, 1.0),
            dkim_days=random.randint(30, 180)
        ))
    
    # Add sybil agents (low resistance, no DKIM)
    for sid in sybil_ids:
        g.add_agent(Agent(
            id=sid, is_sybil=True,
            resistance=random.uniform(0.0, 0.2),
            dkim_days=random.randint(0, 5)
        ))
    
    # Honest graph: sparse, selective attestation (avg degree ~4)
    for hid in honest_ids:
        n_attest = random.randint(2, 6)
        targets = random.sample([h for h in honest_ids if h != hid], 
                                min(n_attest, len(honest_ids) - 1))
        for t in targets:
            g.add_attestation(hid, t, random.uniform(0.5, 1.0))
    
    # Sybil graph: dense, mutual attestation (everyone attests everyone)
    for i, sid1 in enumerate(sybil_ids):
        for j, sid2 in enumerate(sybil_ids):
            if i != j:
                g.add_attestation(sid1, sid2, random.uniform(0.8, 1.0))
    
    # Attack edges: sybils try to get attested by honest agents
    for _ in range(attack_edges):
        s = random.choice(sybil_ids)
        h = random.choice(honest_ids)
        # Honest agent might attest sybil (low score)
        g.add_attestation(h, s, random.uniform(0.3, 0.6))
        # Sybil attests honest (trying to appear connected)
        g.add_attestation(s, h, random.uniform(0.7, 1.0))
    
    # Seeds: known-honest agents (3 randomly chosen)
    seeds = random.sample(honest_ids, 3)
    
    return g, seeds


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("SYBIL DENSITY DETECTOR — ATF Trust Graph Analysis")
    print("=" * 60)
    print()
    
    g, seeds = build_test_network(n_honest=20, n_sybil=10, attack_edges=3)
    
    print(f"Network: {len(g.agents)} agents ({20} honest, {10} sybil)")
    print(f"Seeds (known honest): {seeds}")
    print()
    
    # Show graph properties
    honest_densities = [g.local_density(f"honest_{i}") for i in range(20)]
    sybil_densities = [g.local_density(f"sybil_{i}") for i in range(10)]
    
    print(f"Avg honest density: {sum(honest_densities)/len(honest_densities):.3f}")
    print(f"Avg sybil density:  {sum(sybil_densities)/len(sybil_densities):.3f}")
    print(f"Density gap:        {sum(sybil_densities)/len(sybil_densities) - sum(honest_densities)/len(honest_densities):.3f}")
    print()
    
    # Run detection
    results = g.detect_sybils(seeds)
    m = results["metrics"]
    
    print("DETECTION RESULTS:")
    print(f"  Accuracy:  {m['accuracy']:.1%}")
    print(f"  Precision: {m['precision']:.1%}")
    print(f"  Recall:    {m['recall']:.1%}")
    print(f"  F1:        {m['f1']:.1%}")
    print(f"  TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}")
    print()
    
    # Show misclassifications
    misclass = [(aid, r) for aid, r in results["agents"].items() if not r["correct"]]
    if misclass:
        print(f"MISCLASSIFIED ({len(misclass)}):")
        for aid, r in misclass:
            label = "sybil" if r["actual_sybil"] else "honest"
            classified = "sybil" if r["classified_sybil"] else "honest"
            print(f"  {aid}: actual={label}, classified={classified}, "
                  f"density={r['density']}, rank={r['rank']:.6f}, "
                  f"resistance={r['resistance']:.2f}, signals={r['sybil_signals']}")
    else:
        print("NO MISCLASSIFICATIONS ✓")
    
    print()
    print("KEY INSIGHT: Sybil clusters are dense (mutual inflation).")
    print("Honest networks are sparse (selective trust). The density")
    print("gap + random walk trapping + identity resistance = detection.")
    print("Dehkordi & Zehmakan (AAMAS 2025): known-resistance nodes")
    print("as preprocessing improves SybilSCAR/SybilWalk accuracy.")
    
    # Assertions
    assert m['accuracy'] >= 0.7, f"Accuracy too low: {m['accuracy']}"
    assert m['precision'] >= 0.6, f"Precision too low: {m['precision']}"
    print("\nASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
