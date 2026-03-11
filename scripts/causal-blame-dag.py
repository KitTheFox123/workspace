#!/usr/bin/env python3
"""
causal-blame-dag.py — Backwards DAG traversal for blame assignment

santaclawd: "dispute resolution = backwards graph traversal. GAAS cascade
answers 'who knew what when' deterministically."

Purdue NeurIPS 2022: microservice root cause analysis through causal discovery.
Same pattern: leaf failure → traverse causal graph → find contamination origin.

Protocol:
1. Build cert DAG (parent_hash chain)
2. Leaf node fails
3. Traverse parent_hash backwards
4. First scope_hash mismatch = contamination origin
5. Everything downstream = tainted
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CertNode:
    """A node in the certification DAG"""
    cert_id: str
    agent_id: str
    scope_hash: str          # hash of capability manifest at cert time
    observed_scope: str = ""  # actual scope at audit time
    parent_id: Optional[str] = None
    children: list = field(default_factory=list)
    status: str = "VALID"     # VALID, DRIFTED, TAINTED
    
    def has_drifted(self) -> bool:
        return self.observed_scope and self.observed_scope != self.scope_hash


@dataclass
class BlameDAG:
    """Cert DAG with backwards traversal for blame"""
    nodes: dict = field(default_factory=dict)  # cert_id → CertNode
    
    def add_cert(self, cert_id: str, agent_id: str, scope_hash: str, parent_id: str = None):
        node = CertNode(cert_id=cert_id, agent_id=agent_id, scope_hash=scope_hash, parent_id=parent_id)
        self.nodes[cert_id] = node
        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id].children.append(cert_id)
    
    def audit(self, cert_id: str, observed_scope: str):
        """Record what scope was actually observed at audit time"""
        if cert_id in self.nodes:
            self.nodes[cert_id].observed_scope = observed_scope
    
    def find_contamination_origin(self, failed_cert_id: str) -> dict:
        """Backwards traversal: leaf → root, find first scope mismatch"""
        path = []
        current_id = failed_cert_id
        origin = None
        
        while current_id and current_id in self.nodes:
            node = self.nodes[current_id]
            path.append({
                "cert_id": node.cert_id,
                "agent_id": node.agent_id,
                "drifted": node.has_drifted(),
                "scope_hash": node.scope_hash,
                "observed": node.observed_scope or "(not audited)"
            })
            if node.has_drifted() and origin is None:
                origin = node.cert_id
            current_id = node.parent_id
        
        return {
            "failed_leaf": failed_cert_id,
            "traversal_path": list(reversed(path)),
            "contamination_origin": origin,
            "path_length": len(path)
        }
    
    def taint_downstream(self, origin_cert_id: str) -> list:
        """Mark all downstream certs as tainted"""
        tainted = []
        queue = [origin_cert_id]
        while queue:
            cert_id = queue.pop(0)
            if cert_id in self.nodes:
                self.nodes[cert_id].status = "TAINTED"
                tainted.append(cert_id)
                queue.extend(self.nodes[cert_id].children)
        return tainted
    
    def blame_report(self, failed_cert_id: str) -> dict:
        """Full blame analysis"""
        origin = self.find_contamination_origin(failed_cert_id)
        tainted = []
        if origin["contamination_origin"]:
            tainted = self.taint_downstream(origin["contamination_origin"])
        
        return {
            "origin": origin,
            "tainted_certs": tainted,
            "total_tainted": len(tainted),
            "blame_agent": self.nodes[origin["contamination_origin"]].agent_id if origin["contamination_origin"] else None,
            "deterministic": origin["contamination_origin"] is not None
        }


def demo():
    print("=" * 60)
    print("Causal Blame DAG")
    print("Backwards traversal for deterministic blame assignment")
    print("=" * 60)
    
    dag = BlameDAG()
    
    # Build cert chain: root → agent1 → agent2 → agent3
    dag.add_cert("cert_root", "platform", "scope_aaa")
    dag.add_cert("cert_a1", "agent_alpha", "scope_bbb", parent_id="cert_root")
    dag.add_cert("cert_a2", "agent_beta", "scope_ccc", parent_id="cert_a1")
    dag.add_cert("cert_a3", "agent_gamma", "scope_ddd", parent_id="cert_a2")
    
    # Branch: root → agent1 → agent4
    dag.add_cert("cert_a4", "agent_delta", "scope_eee", parent_id="cert_a1")
    
    print("\nDAG structure:")
    print("  cert_root (platform)")
    print("    └─ cert_a1 (alpha)")
    print("        ├─ cert_a2 (beta)")
    print("        │   └─ cert_a3 (gamma)")
    print("        └─ cert_a4 (delta)")
    
    # Scenario 1: agent_beta drifts, caught at agent_gamma
    print("\n--- Scenario 1: Drift at beta, caught at gamma ---")
    dag.audit("cert_root", "scope_aaa")  # root OK
    dag.audit("cert_a1", "scope_bbb")    # alpha OK
    dag.audit("cert_a2", "scope_CHANGED")  # beta DRIFTED
    dag.audit("cert_a3", "scope_ddd")    # gamma OK but downstream
    
    report = dag.blame_report("cert_a3")
    print(f"  Origin: {report['origin']['contamination_origin']}")
    print(f"  Blame: {report['blame_agent']}")
    print(f"  Tainted: {report['tainted_certs']}")
    print(f"  Deterministic: {report['deterministic']}")
    
    # Scenario 2: No drift (clean chain)
    print("\n--- Scenario 2: Clean chain ---")
    dag2 = BlameDAG()
    dag2.add_cert("c1", "root", "s1")
    dag2.add_cert("c2", "agent_a", "s2", parent_id="c1")
    dag2.add_cert("c3", "agent_b", "s3", parent_id="c2")
    dag2.audit("c1", "s1")
    dag2.audit("c2", "s2")
    dag2.audit("c3", "s3")
    report2 = dag2.blame_report("c3")
    print(f"  Origin: {report2['origin']['contamination_origin']}")
    print(f"  Deterministic: {report2['deterministic']}")
    print(f"  All clean — no blame to assign.")
    
    print(f"\n{'='*60}")
    print("Blame is deterministic, not negotiated.")
    print("Leaf fails → traverse backwards → first scope mismatch = origin.")
    print("Everything downstream = tainted. The cert DAG answers it.")


if __name__ == "__main__":
    demo()
