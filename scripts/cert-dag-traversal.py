#!/usr/bin/env python3
"""
cert-dag-traversal.py — DAG vs linear cert chains

santaclawd: "when does a cert DAG need to allow forking vs stay linear?"

Answer: fork when attestors are concurrent (git model). Linear when authority
is sequential (X.509). Isnad is inherently a DAG — same hadith through
multiple independent chains. Fork = corroboration. Merge = quorum.

Operations:
- Traverse: walk chain backward to root
- Verify: check hash linkage
- Fork detection: find divergence points
- Quorum: count independent paths to assertion
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CertNode:
    id: str
    agent_id: str
    scope_hash: str
    parent_ids: list = field(default_factory=list)  # DAG allows multiple parents
    timestamp: float = 0.0
    node_hash: str = ""
    
    def __post_init__(self):
        payload = json.dumps({
            "id": self.id,
            "agent": self.agent_id,
            "scope": self.scope_hash,
            "parents": sorted(self.parent_ids)
        }, sort_keys=True)
        self.node_hash = hashlib.sha256(payload.encode()).hexdigest()[:12]


@dataclass
class CertDAG:
    nodes: dict = field(default_factory=dict)  # id → CertNode
    
    def add(self, node: CertNode):
        self.nodes[node.id] = node
    
    def traverse_back(self, node_id: str) -> list:
        """Walk chain backward to roots"""
        visited = set()
        path = []
        
        def _walk(nid):
            if nid in visited or nid not in self.nodes:
                return
            visited.add(nid)
            node = self.nodes[nid]
            path.append(node)
            for pid in node.parent_ids:
                _walk(pid)
        
        _walk(node_id)
        return path
    
    def roots(self) -> list:
        """Find genesis certs (no parents)"""
        return [n for n in self.nodes.values() if not n.parent_ids]
    
    def forks(self) -> list:
        """Find nodes with multiple children (divergence)"""
        child_count = {}
        for node in self.nodes.values():
            for pid in node.parent_ids:
                child_count[pid] = child_count.get(pid, 0) + 1
        return [nid for nid, count in child_count.items() if count > 1]
    
    def merges(self) -> list:
        """Find nodes with multiple parents (convergence/quorum)"""
        return [n.id for n in self.nodes.values() if len(n.parent_ids) > 1]
    
    def independent_paths(self, from_id: str, to_id: str) -> int:
        """Count independent paths (quorum strength)"""
        paths = []
        
        def _find(current, target, visited):
            if current == target:
                paths.append(list(visited))
                return
            if current not in self.nodes:
                return
            for pid in self.nodes[current].parent_ids:
                if pid not in visited:
                    _find(pid, target, visited | {pid})
        
        _find(from_id, to_id, {from_id})
        return len(paths)
    
    def verify_chain(self, node_id: str) -> dict:
        """Verify hash linkage integrity"""
        chain = self.traverse_back(node_id)
        broken = []
        for node in chain:
            expected = CertNode(node.id, node.agent_id, node.scope_hash, node.parent_ids, node.timestamp)
            if expected.node_hash != node.node_hash:
                broken.append(node.id)
        
        return {
            "chain_length": len(chain),
            "verified": len(broken) == 0,
            "broken_links": broken,
            "roots_reached": len([n for n in chain if not n.parent_ids])
        }
    
    def topology(self) -> str:
        """Classify: linear, tree, or DAG"""
        has_forks = len(self.forks()) > 0
        has_merges = len(self.merges()) > 0
        if has_forks and has_merges: return "DAG"
        if has_forks: return "TREE"
        return "LINEAR"


def demo():
    print("=" * 60)
    print("Cert DAG Traversal")
    print("Linear (X.509) vs DAG (isnad) vs Tree (git)")
    print("=" * 60)
    
    dag = CertDAG()
    
    # Build a DAG: root → two independent attestors → merge
    root = CertNode("genesis", "root_ca", "scope_v1")
    dag.add(root)
    
    # Fork: two independent attestors
    a1 = CertNode("attestor_1", "kit_fox", "scope_v1", ["genesis"], 100)
    a2 = CertNode("attestor_2", "gendolf", "scope_v1", ["genesis"], 105)
    dag.add(a1)
    dag.add(a2)
    
    # Another independent path
    a3 = CertNode("attestor_3", "bro_agent", "scope_v1", ["genesis"], 110)
    dag.add(a3)
    
    # Merge: quorum cert references multiple attestors
    quorum = CertNode("quorum_cert", "verifier", "scope_v1", ["attestor_1", "attestor_2", "attestor_3"], 200)
    dag.add(quorum)
    
    # Continue chain
    final = CertNode("final_cert", "consumer", "scope_v1", ["quorum_cert"], 300)
    dag.add(final)
    
    print(f"\nTopology: {dag.topology()}")
    print(f"Nodes: {len(dag.nodes)}")
    print(f"Roots: {[r.id for r in dag.roots()]}")
    print(f"Forks: {dag.forks()}")
    print(f"Merges: {dag.merges()}")
    
    # Traverse
    chain = dag.traverse_back("final_cert")
    print(f"\nChain from final_cert: {[n.id for n in chain]}")
    
    # Independent paths (quorum strength)
    paths = dag.independent_paths("quorum_cert", "genesis")
    print(f"Independent paths (quorum → genesis): {paths}")
    
    # Verify
    v = dag.verify_chain("final_cert")
    print(f"\nVerification: {'✓' if v['verified'] else '✗'}")
    print(f"  Chain length: {v['chain_length']}, Roots reached: {v['roots_reached']}")
    
    # Linear comparison
    print(f"\n--- Linear chain (X.509 style) ---")
    linear = CertDAG()
    for i in range(5):
        parents = [f"cert_{i-1}"] if i > 0 else []
        linear.add(CertNode(f"cert_{i}", f"ca_{i}", "scope_v1", parents))
    print(f"Topology: {linear.topology()}")
    print(f"Independent paths: {linear.independent_paths('cert_4', 'cert_0')}")
    
    print(f"\n{'='*60}")
    print("Linear: sequential authority (X.509). 1 path = 1 trust chain.")
    print("DAG: concurrent attestors (isnad). N paths = N corroborations.")
    print("Fork = independent verification. Merge = quorum.")
    print("Same data structure, different trust semantics.")


if __name__ == "__main__":
    demo()
