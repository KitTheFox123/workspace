#!/usr/bin/env python3
"""
cross-layer-blame.py — Multi-layer graph traversal for root cause analysis.

Inspired by PRAXIS (Cui et al, IBM/UIUC Dec 2025): agentic structured graph
traversal across service dependency graph + program dependency graph.
3.1x accuracy over ReAct, 3.8x fewer tokens.

Applied to agent cert DAGs: traverse across trust layers
(scope layer, behavioral layer, attestation layer) to classify
each node as PRIMARY_FAILURE / SYMPTOM_ONLY / UNRELATED.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NodeClassification(Enum):
    PRIMARY_FAILURE = "PRIMARY_FAILURE"
    SYMPTOM_ONLY = "SYMPTOM_ONLY"
    UNRELATED = "UNRELATED"
    UNCLASSIFIED = "UNCLASSIFIED"


class Layer(Enum):
    SCOPE = "scope"          # manifest/capability layer
    BEHAVIORAL = "behavioral"  # runtime behavior layer
    ATTESTATION = "attestation"  # trust/cert layer


@dataclass
class Node:
    id: str
    layer: Layer
    agent_id: str
    description: str
    anomaly_score: float = 0.0  # 0=normal, 1=fully anomalous
    classification: NodeClassification = NodeClassification.UNCLASSIFIED
    
    @property
    def is_anomalous(self) -> bool:
        return self.anomaly_score > 0.5


@dataclass
class Edge:
    source_id: str
    target_id: str
    edge_type: str  # "depends_on", "attests", "cross_layer"
    

class BlameGraph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._adjacency: dict[str, list[str]] = {}
        self._reverse: dict[str, list[str]] = {}
    
    def add_node(self, node: Node):
        self.nodes[node.id] = node
        if node.id not in self._adjacency:
            self._adjacency[node.id] = []
            self._reverse[node.id] = []
    
    def add_edge(self, source_id: str, target_id: str, edge_type: str = "depends_on"):
        self.edges.append(Edge(source_id, target_id, edge_type))
        self._adjacency.setdefault(source_id, []).append(target_id)
        self._reverse.setdefault(target_id, []).append(source_id)
    
    def traverse_backwards(self, start_id: str) -> list[str]:
        """PRAXIS-style backwards traversal from symptom to root cause."""
        visited = []
        queue = [start_id]
        seen = set()
        
        while queue:
            node_id = queue.pop(0)
            if node_id in seen:
                continue
            seen.add(node_id)
            
            node = self.nodes.get(node_id)
            if node and node.is_anomalous:
                visited.append(node_id)
                # Follow reverse edges (parents/dependencies)
                # Follow forward edges (dependencies this node depends on)
                for parent_id in self._adjacency.get(node_id, []):
                    if parent_id not in seen:
                        queue.append(parent_id)
        
        return visited
    
    def classify_nodes(self, symptom_id: str) -> dict[str, NodeClassification]:
        """Classify all nodes relative to a symptom using backwards traversal."""
        anomalous_path = self.traverse_backwards(symptom_id)
        
        # Primary failure = anomalous node with no anomalous parents
        # Symptom = anomalous node with anomalous parents
        classifications = {}
        
        for node_id in anomalous_path:
            # Dependencies = nodes this one depends on (forward edges)
            deps = self._adjacency.get(node_id, [])
            anomalous_parents = [p for p in deps if self.nodes.get(p, Node("", Layer.SCOPE, "", "")).is_anomalous]
            
            if not anomalous_parents:
                classifications[node_id] = NodeClassification.PRIMARY_FAILURE
            else:
                classifications[node_id] = NodeClassification.SYMPTOM_ONLY
        
        # Everything not on the path is unrelated
        for node_id in self.nodes:
            if node_id not in classifications:
                classifications[node_id] = NodeClassification.UNRELATED
        
        return classifications
    
    def cross_layer_paths(self) -> list[list[str]]:
        """Find paths that cross layer boundaries (PRAXIS cross-SDG-PDG)."""
        cross_paths = []
        for edge in self.edges:
            src = self.nodes.get(edge.source_id)
            tgt = self.nodes.get(edge.target_id)
            if src and tgt and src.layer != tgt.layer:
                cross_paths.append([edge.source_id, edge.target_id])
        return cross_paths


def demo():
    graph = BlameGraph()
    
    # Scope layer: agent manifests
    graph.add_node(Node("scope_alpha", Layer.SCOPE, "alpha", "alpha manifest: file_read, file_write", 0.2))
    graph.add_node(Node("scope_beta", Layer.SCOPE, "beta", "beta manifest: file_read, file_write, net_send", 0.9))  # scope drift!
    graph.add_node(Node("scope_gamma", Layer.SCOPE, "gamma", "gamma manifest: file_read", 0.3))
    
    # Behavioral layer: runtime actions
    graph.add_node(Node("behav_alpha", Layer.BEHAVIORAL, "alpha", "alpha: normal heartbeat pattern", 0.1))
    graph.add_node(Node("behav_beta", Layer.BEHAVIORAL, "beta", "beta: burst of net_send calls", 0.85))  # behavioral anomaly
    graph.add_node(Node("behav_gamma", Layer.BEHAVIORAL, "gamma", "gamma: degraded response time", 0.7))  # downstream symptom
    
    # Attestation layer: cert chain
    graph.add_node(Node("cert_alpha", Layer.ATTESTATION, "alpha", "alpha cert: valid, scope match", 0.1))
    graph.add_node(Node("cert_beta", Layer.ATTESTATION, "beta", "beta cert: scope mismatch!", 0.95))  # cert anomaly
    graph.add_node(Node("cert_gamma", Layer.ATTESTATION, "gamma", "gamma cert: valid but stale", 0.6))
    
    # Intra-layer edges (dependencies)
    graph.add_edge("scope_gamma", "scope_beta", "depends_on")  # gamma depends on beta's output
    graph.add_edge("scope_beta", "scope_alpha", "depends_on")
    
    graph.add_edge("behav_gamma", "behav_beta", "depends_on")  # gamma's degradation from beta
    graph.add_edge("behav_beta", "behav_alpha", "depends_on")
    
    # Cross-layer edges (PRAXIS-style SDG↔PDG, here scope↔behavioral↔attestation)
    graph.add_edge("behav_beta", "scope_beta", "cross_layer")  # behavior anomaly → scope check
    graph.add_edge("cert_beta", "scope_beta", "cross_layer")   # cert anomaly → scope check
    graph.add_edge("cert_gamma", "behav_gamma", "cross_layer")  # cert staleness → behavioral
    
    # Classify from symptom (gamma's degraded behavior)
    classifications = graph.classify_nodes("behav_gamma")
    
    print("=" * 60)
    print("CROSS-LAYER BLAME TRAVERSAL")
    print("Inspired by PRAXIS (Cui et al, IBM/UIUC Dec 2025)")
    print("=" * 60)
    
    # Group by classification
    for cls in NodeClassification:
        nodes = [nid for nid, c in classifications.items() if c == cls]
        if nodes:
            print(f"\n{cls.value}:")
            for nid in nodes:
                node = graph.nodes[nid]
                print(f"  [{node.layer.value}] {nid} (anomaly={node.anomaly_score:.1f})")
                print(f"    {node.description}")
    
    # Cross-layer paths
    cross = graph.cross_layer_paths()
    print(f"\nCross-layer edges: {len(cross)}")
    for path in cross:
        src = graph.nodes[path[0]]
        tgt = graph.nodes[path[1]]
        print(f"  {src.layer.value}:{path[0]} → {tgt.layer.value}:{path[1]}")
    
    # Backwards traversal from symptom
    path = graph.traverse_backwards("behav_gamma")
    print(f"\nBackwards traversal from behav_gamma:")
    print(f"  Path: {' → '.join(path)}")
    
    # Grade
    primaries = sum(1 for c in classifications.values() if c == NodeClassification.PRIMARY_FAILURE)
    symptoms = sum(1 for c in classifications.values() if c == NodeClassification.SYMPTOM_ONLY)
    
    if primaries == 1:
        grade = "A"
        verdict = "Single root cause identified"
    elif primaries > 1:
        grade = "B"
        verdict = f"Multiple root causes ({primaries})"
    else:
        grade = "F"
        verdict = "No root cause found"
    
    print(f"\nVerdict: {verdict} | Grade: {grade}")
    print(f"Primary failures: {primaries} | Symptoms: {symptoms}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: blame that crosses layer boundaries needs")
    print("witness nodes at the crossing point. PRAXIS: cross-SDG-PDG.")
    print("Agent trust: cross scope-behavioral-attestation.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
