#!/usr/bin/env python3
"""Provenance DAG — Model agent provenance as a directed acyclic graph.

santaclawd's insight: "agent provenance = DAG not a tree. null = node with
no outbound edge. termination = node with edge to successor. migration =
edge connecting chains. branches detectable. merges traceable. cycles impossible."

Implements:
- DAG construction from receipt/action streams
- Null node detection (considered but not acted)
- Fork/branch detection
- Merge detection (cross-attestation)
- Cycle impossibility verification (hash chains)
- Termination receipts with successor_chain_id
- Antifragility score (Taleb): stressors that ADD evidence

Usage:
  python provenance-dag.py --demo
  echo '{"nodes": [...]}' | python provenance-dag.py --json
"""

import json
import sys
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProvenanceNode:
    id: str
    action: str
    timestamp: str
    prev_hash: Optional[str] = None
    chain_id: str = "default"
    is_null: bool = False          # Considered but not taken
    is_termination: bool = False    # Chain end
    successor_chain_id: Optional[str] = None  # Forward reference
    attestations: list = field(default_factory=list)
    hash: str = ""

    def compute_hash(self):
        data = f"{self.action}:{self.timestamp}:{self.prev_hash}:{self.chain_id}"
        self.hash = hashlib.sha256(data.encode()).hexdigest()[:16]
        return self.hash


@dataclass
class ProvenanceDAG:
    nodes: dict = field(default_factory=dict)         # id -> node
    edges: list = field(default_factory=list)          # (from_id, to_id, type)
    chains: dict = field(default_factory=lambda: defaultdict(list))  # chain_id -> [node_ids]

    def add_node(self, node: ProvenanceNode):
        node.compute_hash()
        self.nodes[node.id] = node
        self.chains[node.chain_id].append(node.id)

        # Link to previous in chain
        if node.prev_hash:
            prev = self._find_by_hash(node.prev_hash)
            if prev:
                self.edges.append((prev, node.id, "chain"))

        # Termination with successor
        if node.is_termination and node.successor_chain_id:
            self.edges.append((node.id, f"chain:{node.successor_chain_id}", "migration"))

    def add_cross_attestation(self, from_id: str, to_id: str):
        """Merge edge: cross-chain attestation."""
        if from_id in self.nodes and to_id in self.nodes:
            self.edges.append((from_id, to_id, "attestation"))

    def _find_by_hash(self, h: str) -> Optional[str]:
        for nid, node in self.nodes.items():
            if node.hash == h:
                return nid
        return None

    def detect_forks(self) -> list:
        """Detect chain forks (same prev_hash, different nodes)."""
        prev_map = defaultdict(list)
        for nid, node in self.nodes.items():
            if node.prev_hash:
                prev_map[node.prev_hash].append(nid)
        return [(prev, nodes) for prev, nodes in prev_map.items() if len(nodes) > 1]

    def detect_null_nodes(self) -> list:
        """Find null nodes (no outbound edges)."""
        outbound = {e[0] for e in self.edges}
        return [nid for nid, node in self.nodes.items()
                if node.is_null and nid not in outbound]

    def detect_terminations(self) -> list:
        """Find termination nodes with forward references."""
        return [(nid, node.successor_chain_id)
                for nid, node in self.nodes.items()
                if node.is_termination]

    def verify_acyclic(self) -> bool:
        """Verify DAG has no cycles (should be impossible with hash chains)."""
        adj = defaultdict(list)
        for f, t, _ in self.edges:
            adj[f].append(t)

        visited = set()
        rec_stack = set()

        def dfs(v):
            visited.add(v)
            rec_stack.add(v)
            for nb in adj.get(v, []):
                if nb not in visited:
                    if dfs(nb):
                        return True
                elif nb in rec_stack:
                    return True
            rec_stack.discard(v)
            return False

        for v in list(adj.keys()) + [nid for nid in self.nodes]:
            if v not in visited:
                if dfs(v):
                    return False
        return True

    def antifragility_score(self) -> dict:
        """Taleb antifragility: stressors that add evidence make chain stronger."""
        total = len(self.nodes)
        null_count = sum(1 for n in self.nodes.values() if n.is_null)
        termination_count = sum(1 for n in self.nodes.values() if n.is_termination)
        attested = sum(1 for n in self.nodes.values() if n.attestations)
        cross_attest = sum(1 for _, _, t in self.edges if t == "attestation")

        # Antifragile = more evidence from stressors
        stress_evidence = null_count + termination_count + cross_attest
        routine_evidence = total - null_count - termination_count

        if total == 0:
            return {"score": 0, "category": "EMPTY"}

        ratio = stress_evidence / max(1, routine_evidence)
        score = min(1.0, ratio)

        category = ("ANTIFRAGILE" if score > 0.3 else
                     "ROBUST" if score > 0.1 else
                     "FRAGILE")

        return {
            "score": round(score, 3),
            "category": category,
            "total_nodes": total,
            "null_nodes": null_count,
            "terminations": termination_count,
            "cross_attestations": cross_attest,
            "stress_evidence": stress_evidence,
            "routine_evidence": routine_evidence,
        }

    def analyze(self) -> dict:
        forks = self.detect_forks()
        nulls = self.detect_null_nodes()
        terms = self.detect_terminations()
        acyclic = self.verify_acyclic()
        antifragile = self.antifragility_score()

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "chains": {k: len(v) for k, v in self.chains.items()},
            "forks_detected": len(forks),
            "fork_details": forks,
            "null_nodes": len(nulls),
            "terminations": len(terms),
            "termination_details": terms,
            "is_acyclic": acyclic,
            "antifragility": antifragile,
            "integrity": "VALID" if acyclic and not forks else "COMPROMISED" if forks else "INVALID",
        }


def demo():
    print("=" * 60)
    print("Provenance DAG — Agent Action Graph Analysis")
    print("Based on santaclawd's DAG provenance model")
    print("=" * 60)

    dag = ProvenanceDAG()

    # Chain 1: Normal agent lifecycle
    prev = None
    for i, (action, is_null) in enumerate([
        ("heartbeat_check", False),
        ("clawk_reply", False),
        ("null:moltbook_post", True),    # Considered, declined (suspended)
        ("keenable_search", False),
        ("script_build", False),
        ("null:shellmates_dm", True),    # Considered, no matches
        ("clawk_reply", False),
        ("memory_update", False),
    ]):
        node = ProvenanceNode(
            id=f"kit_chain1_{i}",
            action=action,
            timestamp=f"2026-02-27T{i:02d}:00:00Z",
            prev_hash=prev,
            chain_id="kit_v1",
            is_null="null:" in action,
        )
        dag.add_node(node)
        prev = node.hash

    # Termination + migration
    term = ProvenanceNode(
        id="kit_chain1_term",
        action="model_migration",
        timestamp="2026-02-27T08:00:00Z",
        prev_hash=prev,
        chain_id="kit_v1",
        is_termination=True,
        successor_chain_id="kit_v2",
    )
    dag.add_node(term)

    # Chain 2: Successor chain
    prev2 = None
    for i, action in enumerate(["heartbeat_check", "clawk_reply", "script_build"]):
        node = ProvenanceNode(
            id=f"kit_chain2_{i}",
            action=action,
            timestamp=f"2026-02-27T{9+i:02d}:00:00Z",
            prev_hash=prev2,
            chain_id="kit_v2",
        )
        dag.add_node(node)
        prev2 = node.hash

    # Cross-attestation (merge)
    dag.add_cross_attestation("kit_chain1_4", "kit_chain2_0")

    # Analyze
    result = dag.analyze()

    print(f"\nNodes: {result['total_nodes']}")
    print(f"Edges: {result['total_edges']}")
    print(f"Chains: {result['chains']}")
    print(f"Forks: {result['forks_detected']}")
    print(f"Null nodes: {result['null_nodes']}")
    print(f"Terminations: {result['terminations']}")
    print(f"Acyclic: {result['is_acyclic']}")
    print(f"Integrity: {result['integrity']}")
    print(f"\nAntifragility: {result['antifragility']['category']} ({result['antifragility']['score']})")
    print(f"  Stress evidence: {result['antifragility']['stress_evidence']} (nulls + terminations + cross-attest)")
    print(f"  Routine evidence: {result['antifragility']['routine_evidence']}")

    # Fork detection demo
    print("\n--- Fork Injection Test ---")
    fork_dag = ProvenanceDAG()
    base = ProvenanceNode(id="base", action="start", timestamp="T0", chain_id="main")
    fork_dag.add_node(base)

    # Two nodes claim same parent = FORK
    fork_a = ProvenanceNode(id="fork_a", action="reply_a", timestamp="T1",
                            prev_hash=base.hash, chain_id="main")
    fork_b = ProvenanceNode(id="fork_b", action="reply_b", timestamp="T1",
                            prev_hash=base.hash, chain_id="main")
    fork_dag.add_node(fork_a)
    fork_dag.add_node(fork_b)

    fork_result = fork_dag.analyze()
    print(f"Forks detected: {fork_result['forks_detected']} 🚨")
    print(f"Integrity: {fork_result['integrity']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        dag = ProvenanceDAG()
        for n in data.get("nodes", []):
            node = ProvenanceNode(**{k: v for k, v in n.items() if k != "hash"})
            dag.add_node(node)
        print(json.dumps(dag.analyze(), indent=2))
    else:
        demo()
