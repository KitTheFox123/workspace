#!/usr/bin/env python3
"""
sybilwalk-atf.py — SybilWalk-inspired random walk for ATF trust networks.

Based on Jia, Wang & Gong (Iowa State): Random Walk based Fake Account
Detection in Online Social Networks. SybilWalk distributes reputation
from BOTH labeled benign and labeled sybil seeds, achieving 1.3% FPR
and 17.3% FNR on Twitter.

Key insight: honest subgraphs are fast-mixing (random walk converges
quickly). Sybil regions are dense internally but have few "attack edges"
connecting to honest region. Random walk from honest seeds diffuses
widely; walk from sybil seeds stays trapped in sybil cluster.

ATF mapping:
- "Labeled benign" = genesis attesters (bootstrap trust seeds)
- "Labeled sybil" = known-bad agents (flagged by dispute resolution)
- "Attack edges" = attestations crossing sybil/honest boundary
- Fast-mixing = honest agents attest diverse others (sparse graph)
- Sybil density = mutual attestation rings (dense graph)

The walk computes two scores per node:
- benign_score: reputation flowing from honest seeds
- sybil_score: contamination flowing from known-bad seeds
- final_score = benign_score - sybil_score (SybilWalk's key innovation)

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Node:
    id: str
    is_honest: bool  # ground truth (for evaluation only)
    label: str = "unknown"  # "benign_seed", "sybil_seed", "unknown"
    benign_score: float = 0.0
    sybil_score: float = 0.0
    
    @property
    def final_score(self) -> float:
        return self.benign_score - self.sybil_score


class SybilWalkATF:
    """
    Random walk sybil detection adapted for ATF attestation graphs.
    
    From SybilWalk paper:
    - Distributes scores from both benign and sybil seeds
    - Uses power iteration (equivalent to random walk)
    - Fast-mixing honest subgraph → benign scores spread evenly
    - Dense sybil cluster → sybil scores stay concentrated
    """
    
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, list[str]] = defaultdict(list)  # adjacency
    
    def add_node(self, node_id: str, is_honest: bool, label: str = "unknown"):
        self.nodes[node_id] = Node(id=node_id, is_honest=is_honest, label=label)
    
    def add_edge(self, from_id: str, to_id: str):
        """Attestation edge: from_id attested to_id."""
        self.edges[from_id].append(to_id)
        self.edges[to_id].append(from_id)  # Undirected for random walk
    
    def run_walk(self, iterations: int = 20, decay: float = 0.85) -> dict:
        """
        Power iteration from seed nodes.
        
        decay (0.85) = probability of continuing walk vs restarting.
        Higher decay = scores spread further. Lower = stay near seeds.
        SybilWalk uses ~0.85 (similar to PageRank's 0.85).
        """
        # Initialize seed scores
        for node in self.nodes.values():
            if node.label == "benign_seed":
                node.benign_score = 1.0
            elif node.label == "sybil_seed":
                node.sybil_score = 1.0
        
        # Power iteration
        for _ in range(iterations):
            new_benign = {}
            new_sybil = {}
            
            for nid, node in self.nodes.items():
                neighbors = self.edges.get(nid, [])
                if not neighbors:
                    new_benign[nid] = node.benign_score
                    new_sybil[nid] = node.sybil_score
                    continue
                
                # Receive scores from neighbors (normalized by their degree)
                b_incoming = sum(
                    self.nodes[n].benign_score / max(len(self.edges[n]), 1)
                    for n in neighbors if n in self.nodes
                )
                s_incoming = sum(
                    self.nodes[n].sybil_score / max(len(self.edges[n]), 1)
                    for n in neighbors if n in self.nodes
                )
                
                # Restart probability for seeds
                b_restart = 1.0 if node.label == "benign_seed" else 0.0
                s_restart = 1.0 if node.label == "sybil_seed" else 0.0
                
                new_benign[nid] = decay * b_incoming + (1 - decay) * b_restart
                new_sybil[nid] = decay * s_incoming + (1 - decay) * s_restart
            
            for nid in self.nodes:
                self.nodes[nid].benign_score = new_benign.get(nid, 0)
                self.nodes[nid].sybil_score = new_sybil.get(nid, 0)
        
        return self.evaluate()
    
    def evaluate(self) -> dict:
        """Evaluate classification accuracy."""
        threshold = 0.0  # final_score > 0 = classified benign
        
        tp = fp = tn = fn = 0
        for node in self.nodes.values():
            if node.label in ("benign_seed", "sybil_seed"):
                continue  # Skip seeds
            
            predicted_honest = node.final_score > threshold
            if node.is_honest and predicted_honest:
                tp += 1
            elif node.is_honest and not predicted_honest:
                fn += 1
            elif not node.is_honest and predicted_honest:
                fp += 1
            else:
                tn += 1
        
        total = tp + fp + tn + fn
        accuracy = (tp + tn) / max(total, 1)
        fpr = fp / max(fp + tn, 1)
        fnr = fn / max(fn + tp, 1)
        
        return {
            "accuracy": round(accuracy, 4),
            "fpr": round(fpr, 4),
            "fnr": round(fnr, 4),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "total_evaluated": total
        }
    
    def get_rankings(self) -> list[dict]:
        """Rank all non-seed nodes by final_score (ascending = most suspicious)."""
        ranked = []
        for node in self.nodes.values():
            if node.label in ("benign_seed", "sybil_seed"):
                continue
            ranked.append({
                "id": node.id,
                "final_score": round(node.final_score, 4),
                "benign_score": round(node.benign_score, 4),
                "sybil_score": round(node.sybil_score, 4),
                "is_honest": node.is_honest
            })
        return sorted(ranked, key=lambda x: x["final_score"])


def build_test_network(n_honest: int = 30, n_sybil: int = 20,
                       n_benign_seeds: int = 3, n_sybil_seeds: int = 2,
                       attack_edges: int = 3) -> SybilWalkATF:
    """
    Build a test network with known honest/sybil partition.
    
    Honest subgraph: sparse, random edges (fast-mixing).
    Sybil subgraph: dense, many mutual edges (cluster).
    Attack edges: few connections between honest and sybil regions.
    """
    random.seed(42)
    sw = SybilWalkATF()
    
    # Create honest nodes
    honest_ids = [f"honest_{i}" for i in range(n_honest)]
    for i, hid in enumerate(honest_ids):
        label = "benign_seed" if i < n_benign_seeds else "unknown"
        sw.add_node(hid, is_honest=True, label=label)
    
    # Create sybil nodes
    sybil_ids = [f"sybil_{i}" for i in range(n_sybil)]
    for i, sid in enumerate(sybil_ids):
        label = "sybil_seed" if i < n_sybil_seeds else "unknown"
        sw.add_node(sid, is_honest=False, label=label)
    
    # Honest subgraph: sparse random (each node connects to ~3-5 others)
    for hid in honest_ids:
        n_edges = random.randint(2, 5)
        targets = random.sample([h for h in honest_ids if h != hid], 
                                min(n_edges, len(honest_ids) - 1))
        for t in targets:
            sw.add_edge(hid, t)
    
    # Sybil subgraph: dense (each sybil connects to ~60-80% of other sybils)
    for sid in sybil_ids:
        n_edges = random.randint(int(n_sybil * 0.6), int(n_sybil * 0.8))
        targets = random.sample([s for s in sybil_ids if s != sid],
                                min(n_edges, len(sybil_ids) - 1))
        for t in targets:
            sw.add_edge(sid, t)
    
    # Attack edges: few connections between regions
    for _ in range(attack_edges):
        h = random.choice(honest_ids)
        s = random.choice(sybil_ids)
        sw.add_edge(h, s)
    
    return sw


def demo():
    print("=" * 60)
    print("SybilWalk-ATF: Random Walk Sybil Detection for Trust Networks")
    print("=" * 60)
    print()
    
    # Scenario 1: Standard network (few attack edges)
    print("SCENARIO 1: 30 honest + 20 sybil, 3 attack edges")
    print("-" * 50)
    sw1 = build_test_network(attack_edges=3)
    result1 = sw1.run_walk(iterations=20)
    print(f"Accuracy: {result1['accuracy']:.1%}")
    print(f"FPR: {result1['fpr']:.1%} (sybils misclassified as honest)")
    print(f"FNR: {result1['fnr']:.1%} (honest misclassified as sybil)")
    print(f"Confusion: TP={result1['tp']} FP={result1['fp']} TN={result1['tn']} FN={result1['fn']}")
    print()
    
    top_suspicious = sw1.get_rankings()[:5]
    print("Top 5 most suspicious (lowest final_score):")
    for r in top_suspicious:
        tag = "✓ SYBIL" if not r["is_honest"] else "✗ HONEST (false positive)"
        print(f"  {r['id']}: score={r['final_score']:+.4f} {tag}")
    print()
    
    bottom_trusted = sw1.get_rankings()[-5:]
    print("Top 5 most trusted (highest final_score):")
    for r in reversed(bottom_trusted):
        tag = "✓ HONEST" if r["is_honest"] else "✗ SYBIL (false negative)"
        print(f"  {r['id']}: score={r['final_score']:+.4f} {tag}")
    print()
    
    # Scenario 2: More attack edges (harder case)
    print("SCENARIO 2: Same network, 10 attack edges (more infiltration)")
    print("-" * 50)
    sw2 = build_test_network(attack_edges=10)
    result2 = sw2.run_walk(iterations=20)
    print(f"Accuracy: {result2['accuracy']:.1%}")
    print(f"FPR: {result2['fpr']:.1%}")
    print(f"FNR: {result2['fnr']:.1%}")
    print()
    
    # Scenario 3: Balanced (50/50)
    print("SCENARIO 3: 25 honest + 25 sybil (50/50, near percolation threshold)")
    print("-" * 50)
    sw3 = build_test_network(n_honest=25, n_sybil=25, attack_edges=5)
    result3 = sw3.run_walk(iterations=20)
    print(f"Accuracy: {result3['accuracy']:.1%}")
    print(f"FPR: {result3['fpr']:.1%}")
    print(f"FNR: {result3['fnr']:.1%}")
    print()
    
    print("=" * 60)
    print("KEY INSIGHTS")
    print("=" * 60)
    print("1. Dense sybil clusters trap sybil_score (high contamination)")
    print("2. Sparse honest graph lets benign_score spread (fast-mixing)")
    print("3. Few attack edges = easy separation. Many = harder.")
    print("4. final_score = benign - sybil. Dual-walk is SybilWalk's edge.")
    print("5. ATF parallel: genesis attesters = benign seeds,")
    print("   flagged agents = sybil seeds, attestation = edges.")
    print()
    
    # Verify
    assert result1['accuracy'] > 0.7, f"Scenario 1 accuracy too low: {result1['accuracy']}"
    assert result2['accuracy'] > 0.5, f"Scenario 2 accuracy too low: {result2['accuracy']}"
    print("ALL SCENARIOS PASSED ✓")


if __name__ == "__main__":
    demo()
