#!/usr/bin/env python3
"""
cert-dag-blame.py — Causal DAG blame traversal for cert chains

santaclawd: "GAAS cascade as graph traversal. blame assignment becomes deterministic."
Hash: "cert_id = sha256(issuer+skill_hash+scope_hash+ts), parent_hash → upstream cert"

Inspired by microservice RCA (Purdue 2022, NeurIPS): service dependency graph +
anomaly propagation → root cause analysis with 92% accuracy.

Agent cert chains ARE dependency graphs. scope_hash mismatch = anomaly signal.
Walk backwards from failed leaf → find cascade origin.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Cert:
    cert_id: str
    issuer: str
    skill_hash: str
    scope_hash: str
    parent_hash: Optional[str] = None  # upstream cert consumed
    trust_score: float = 1.0
    observed_scope_hash: str = ""      # what scope was actually observed
    
    @property
    def scope_match(self) -> bool:
        if not self.observed_scope_hash:
            return True  # not yet observed
        return self.scope_hash == self.observed_scope_hash
    
    @property
    def anomaly(self) -> bool:
        return not self.scope_match


def make_cert(issuer: str, skill: str, scope: str, parent: Optional[str] = None, observed_scope: str = "") -> Cert:
    payload = f"{issuer}:{skill}:{scope}"
    cert_id = hashlib.sha256(payload.encode()).hexdigest()[:12]
    return Cert(
        cert_id=cert_id,
        issuer=issuer,
        skill_hash=skill,
        scope_hash=scope,
        parent_hash=parent,
        observed_scope_hash=observed_scope or scope  # default: matches
    )


@dataclass
class CertDAG:
    """Directed acyclic graph of cert dependencies"""
    certs: dict = field(default_factory=dict)  # cert_id → Cert
    
    def add(self, cert: Cert):
        self.certs[cert.cert_id] = cert
    
    def find_root_cause(self, failed_cert_id: str) -> list:
        """Walk backwards from failed leaf to find cascade origin"""
        path = []
        current_id = failed_cert_id
        
        while current_id and current_id in self.certs:
            cert = self.certs[current_id]
            path.append({
                "cert_id": cert.cert_id,
                "issuer": cert.issuer,
                "scope_match": cert.scope_match,
                "anomaly": cert.anomaly
            })
            current_id = cert.parent_hash
        
        # Find cascade origin: first anomalous node in reverse path
        origin = None
        for node in path:
            if node["anomaly"]:
                origin = node
        
        return {
            "failed_leaf": failed_cert_id,
            "path_length": len(path),
            "path": path,
            "cascade_origin": origin["cert_id"] if origin else None,
            "cascade_issuer": origin["issuer"] if origin else None,
            "contaminated_count": sum(1 for n in path if n["anomaly"])
        }
    
    def audit(self) -> dict:
        """Full DAG audit"""
        anomalies = [c for c in self.certs.values() if c.anomaly]
        clean = [c for c in self.certs.values() if not c.anomaly]
        
        return {
            "total_certs": len(self.certs),
            "clean": len(clean),
            "anomalous": len(anomalies),
            "anomaly_rate": round(len(anomalies) / max(len(self.certs), 1), 2),
            "anomalous_issuers": list(set(c.issuer for c in anomalies)),
            "grade": "A" if not anomalies else "C" if len(anomalies) <= 1 else "F"
        }


def demo():
    print("=" * 60)
    print("Cert DAG Blame Traversal")
    print("Walk backwards from failure → deterministic blame")
    print("=" * 60)
    
    dag = CertDAG()
    
    # Chain: root_issuer → skill_a → skill_b → skill_c (leaf fails)
    c1 = make_cert("root_issuer", "skill_a", "scope_001")
    dag.add(c1)
    
    c2 = make_cert("agent_alpha", "skill_b", "scope_002", parent=c1.cert_id)
    dag.add(c2)
    
    # c3: scope drifted! attested scope_003 but observed scope_003_expanded
    c3 = make_cert("agent_beta", "skill_c", "scope_003", parent=c2.cert_id, 
                    observed_scope="scope_003_expanded")
    dag.add(c3)
    
    # c4: downstream of c3, also contaminated
    c4 = make_cert("agent_gamma", "skill_d", "scope_004", parent=c3.cert_id,
                    observed_scope="scope_004_drifted")
    dag.add(c4)
    
    print(f"\nCert chain: {c1.cert_id} → {c2.cert_id} → {c3.cert_id} → {c4.cert_id}")
    
    # Find root cause from leaf failure
    rca = dag.find_root_cause(c4.cert_id)
    print(f"\n--- Root Cause Analysis (leaf: {rca['failed_leaf'][:8]}...) ---")
    print(f"Path length: {rca['path_length']}")
    for node in rca['path']:
        status = "✓" if node['scope_match'] else "✗ ANOMALY"
        print(f"  {node['cert_id'][:8]}... ({node['issuer']}): {status}")
    print(f"\nCascade origin: {rca['cascade_origin'][:8] if rca['cascade_origin'] else 'none'}... ({rca['cascade_issuer']})")
    print(f"Contaminated downstream: {rca['contaminated_count']}")
    
    # Full audit
    audit = dag.audit()
    print(f"\n--- DAG Audit ---")
    print(f"Total: {audit['total_certs']}, Clean: {audit['clean']}, Anomalous: {audit['anomalous']}")
    print(f"Anomaly rate: {audit['anomaly_rate']}")
    print(f"Anomalous issuers: {audit['anomalous_issuers']}")
    print(f"Grade: {audit['grade']}")
    
    print(f"\n{'='*60}")
    print("Cert DAG = dependency graph. Scope mismatch = anomaly signal.")
    print("Walk backwards = root cause. Deterministic blame, no jury needed.")
    print("Purdue 2022: causal discovery on service traces → 92% RCA accuracy.")


if __name__ == "__main__":
    demo()
