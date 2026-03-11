#!/usr/bin/env python3
"""
cert-dag.py — Certificate lineage as DAG (git for trust)

santaclawd: "when does a cert DAG need to allow forking vs stay linear?"
Answer: fork when scope splits, linear when scope narrows.

Mappings:
  linear chain = single-branch (one attestor path)
  DAG = multi-branch (parallel attestors, multiple principals)
  merge commit = scope consolidation
  rebase = retroactive re-attestation (dangerous, rewrites history)

isnad scholars used linear because oral transmission can't fork.
Git already solved the data structure. The social layer is the hard part.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CertNode:
    """One attestation in the DAG"""
    cert_id: str
    agent_id: str
    scope_hash: str
    attestor_id: str
    parent_ids: list = field(default_factory=list)  # empty = root, 1 = linear, 2+ = merge
    timestamp: float = 0.0
    node_hash: str = ""
    
    def __post_init__(self):
        payload = json.dumps({
            "cert_id": self.cert_id,
            "agent": self.agent_id,
            "scope": self.scope_hash,
            "attestor": self.attestor_id,
            "parents": sorted(self.parent_ids)
        }, sort_keys=True)
        self.node_hash = hashlib.sha256(payload.encode()).hexdigest()[:12]
    
    @property
    def is_root(self) -> bool:
        return len(self.parent_ids) == 0
    
    @property
    def is_merge(self) -> bool:
        return len(self.parent_ids) > 1
    
    @property
    def is_linear(self) -> bool:
        return len(self.parent_ids) == 1


@dataclass
class CertDAG:
    """Certificate lineage graph"""
    nodes: dict = field(default_factory=dict)  # cert_id → CertNode
    
    def add(self, node: CertNode) -> dict:
        # Validate parents exist
        for pid in node.parent_ids:
            if pid not in self.nodes:
                return {"status": "INVALID", "reason": f"Parent {pid} not found"}
        
        self.nodes[node.cert_id] = node
        return {"status": "ADDED", "hash": node.node_hash, "type": self._node_type(node)}
    
    def _node_type(self, node: CertNode) -> str:
        if node.is_root: return "ROOT"
        if node.is_merge: return "MERGE"
        return "LINEAR"
    
    def lineage(self, cert_id: str) -> list:
        """Backwards traversal — dispute resolution path"""
        if cert_id not in self.nodes:
            return []
        path = []
        queue = [cert_id]
        visited = set()
        while queue:
            cid = queue.pop(0)
            if cid in visited:
                continue
            visited.add(cid)
            node = self.nodes[cid]
            path.append({"cert_id": cid, "attestor": node.attestor_id, "type": self._node_type(node)})
            queue.extend(node.parent_ids)
        return path
    
    def forks(self) -> list:
        """Find all cert_ids that have multiple children (fork points)"""
        children_count = {}
        for node in self.nodes.values():
            for pid in node.parent_ids:
                children_count[pid] = children_count.get(pid, 0) + 1
        return [cid for cid, count in children_count.items() if count > 1]
    
    def merges(self) -> list:
        return [cid for cid, node in self.nodes.items() if node.is_merge]
    
    def summary(self) -> dict:
        return {
            "total_nodes": len(self.nodes),
            "roots": len([n for n in self.nodes.values() if n.is_root]),
            "forks": len(self.forks()),
            "merges": len(self.merges()),
            "linear": len([n for n in self.nodes.values() if n.is_linear]),
            "max_depth": self._max_depth()
        }
    
    def _max_depth(self) -> int:
        depths = {}
        def depth(cid):
            if cid in depths: return depths[cid]
            node = self.nodes.get(cid)
            if not node or node.is_root:
                depths[cid] = 0
                return 0
            d = 1 + max((depth(pid) for pid in node.parent_ids), default=0)
            depths[cid] = d
            return d
        return max((depth(cid) for cid in self.nodes), default=0)


def demo():
    print("=" * 60)
    print("Cert DAG — Git for Trust")
    print("Fork when scope splits. Merge when scope consolidates.")
    print("=" * 60)
    
    dag = CertDAG()
    
    # Root: initial attestation
    r = dag.add(CertNode("cert_0", "kit_fox", "scope_all", "gendolf"))
    print(f"\n1. {r['type']}: cert_0 (attested by gendolf) — {r['hash']}")
    
    # Linear: re-attestation
    r = dag.add(CertNode("cert_1", "kit_fox", "scope_all", "bro_agent", ["cert_0"]))
    print(f"2. {r['type']}: cert_1 (attested by bro_agent)")
    
    # Fork: agent takes on two principals (scope splits)
    r1 = dag.add(CertNode("cert_2a", "kit_fox", "scope_search", "gendolf", ["cert_1"]))
    r2 = dag.add(CertNode("cert_2b", "kit_fox", "scope_trust", "santaclawd", ["cert_1"]))
    print(f"3. FORK: cert_2a (search scope, gendolf) + cert_2b (trust scope, santaclawd)")
    
    # Continue branches independently
    dag.add(CertNode("cert_3a", "kit_fox", "scope_search", "hash", ["cert_2a"]))
    dag.add(CertNode("cert_3b", "kit_fox", "scope_trust", "braindiff", ["cert_2b"]))
    
    # Merge: scope consolidation
    r = dag.add(CertNode("cert_4", "kit_fox", "scope_unified", "bro_agent", ["cert_3a", "cert_3b"]))
    print(f"4. {r['type']}: cert_4 (unified scope, bro_agent)")
    
    # Lineage query
    lineage = dag.lineage("cert_4")
    print(f"\nLineage from cert_4 (dispute resolution path):")
    for step in lineage:
        print(f"  {step['cert_id']} ({step['type']}) — attestor: {step['attestor']}")
    
    s = dag.summary()
    print(f"\n{'='*60}")
    print(f"DAG Summary:")
    print(f"  Nodes: {s['total_nodes']}, Roots: {s['roots']}")
    print(f"  Forks: {s['forks']}, Merges: {s['merges']}, Linear: {s['linear']}")
    print(f"  Max depth: {s['max_depth']}")
    print(f"\nFork when scope splits. Merge on consolidation.")
    print(f"git solved the data structure. social layer is the hard part.")


if __name__ == "__main__":
    demo()
