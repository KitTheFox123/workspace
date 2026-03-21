#!/usr/bin/env python3
"""
ca-fingerprint-auditor.py — Publish and audit CA fingerprint sets for oracle quorums.

Per santaclawd: "CA monoculture is invisible. 7 oracles, 3 operators, 3 models — 
same attestation root = independence theater."

CT for agent attestation: each oracle publishes its CA chain fingerprints.
Monoculture is auditable when fingerprints are public.
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CAFingerprint:
    oracle_id: str
    root_ca: str           # root CA fingerprint
    intermediate_ca: str   # intermediate CA fingerprint  
    leaf_cert: str         # leaf cert fingerprint
    ca_operator: str       # who runs the CA
    issued_at: str         # ISO timestamp
    
    @property
    def chain_hash(self) -> str:
        """Hash the full chain for comparison."""
        data = f"{self.root_ca}:{self.intermediate_ca}:{self.leaf_cert}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class CAFingerprintRegistry:
    fingerprints: list[CAFingerprint] = field(default_factory=list)
    
    def register(self, fp: CAFingerprint):
        self.fingerprints.append(fp)
    
    def audit(self) -> dict:
        n = len(self.fingerprints)
        if n == 0:
            return {"grade": "N/A", "verdict": "EMPTY", "issues": []}
        
        issues = []
        
        # 1. Root CA concentration
        root_cas = [fp.root_ca for fp in self.fingerprints]
        root_counts = Counter(root_cas)
        unique_roots = len(root_counts)
        
        if unique_roots == 1:
            issues.append({
                "type": "ROOT_CA_MONOCULTURE",
                "severity": "CRITICAL",
                "detail": f"All {n} oracles share root CA {root_counts.most_common(1)[0][0][:12]}...",
                "concentration": 1.0
            })
        else:
            max_root = root_counts.most_common(1)[0]
            if max_root[1] > n / 3:
                issues.append({
                    "type": "ROOT_CA_CONCENTRATION",
                    "severity": "CRITICAL" if max_root[1] > n * 2/3 else "WARNING",
                    "detail": f"{max_root[1]}/{n} oracles share root CA {max_root[0][:12]}...",
                    "concentration": max_root[1] / n
                })
        
        # 2. CA operator concentration
        ca_ops = [fp.ca_operator for fp in self.fingerprints]
        op_counts = Counter(ca_ops)
        unique_ops = len(op_counts)
        
        max_op = op_counts.most_common(1)[0]
        if max_op[1] > n / 3:
            issues.append({
                "type": "CA_OPERATOR_CONCENTRATION",
                "severity": "CRITICAL" if max_op[1] > n * 2/3 else "WARNING",
                "detail": f"{max_op[1]}/{n} oracles use CA operator '{max_op[0]}'",
                "concentration": max_op[1] / n
            })
        
        # 3. Chain hash diversity (full chain comparison)
        chain_hashes = [fp.chain_hash for fp in self.fingerprints]
        unique_chains = len(set(chain_hashes))
        chain_counts = Counter(chain_hashes)
        
        if unique_chains < n * 0.5:
            issues.append({
                "type": "CHAIN_DUPLICATION",
                "severity": "WARNING",
                "detail": f"Only {unique_chains}/{n} unique cert chains (possible shared infrastructure)",
                "diversity": unique_chains / n
            })
        
        # 4. Independence theater detection
        # Looks diverse on oracle dimensions but shares CA root
        oracle_ids = set(fp.oracle_id for fp in self.fingerprints)
        if len(oracle_ids) >= 5 and unique_roots == 1:
            issues.append({
                "type": "INDEPENDENCE_THEATER",
                "severity": "CRITICAL",
                "detail": f"{len(oracle_ids)} distinct oracles but single root CA = theater",
                "oracle_count": len(oracle_ids),
                "ca_count": unique_roots
            })
        
        # Grade
        critical = sum(1 for i in issues if i["severity"] == "CRITICAL")
        warnings = sum(1 for i in issues if i["severity"] == "WARNING")
        
        if critical > 0:
            grade = "F"
        elif warnings > 1:
            grade = "D"
        elif warnings == 1:
            grade = "C"
        else:
            grade = "A"
        
        # Gini coefficient for root CA distribution
        values = sorted(root_counts.values())
        cumsum = 0
        weighted_sum = 0
        for i, v in enumerate(values):
            cumsum += v
            weighted_sum += (i + 1) * v
        gini = (2 * weighted_sum) / (n * cumsum) - (len(values) + 1) / len(values) if cumsum > 0 else 0
        gini = max(0, min(1, gini))
        
        return {
            "grade": grade,
            "verdict": "HEALTHY" if grade == "A" else "DEGRADED" if grade in ("C", "D") else "COMPROMISED",
            "oracles": n,
            "unique_root_cas": unique_roots,
            "unique_ca_operators": unique_ops,
            "unique_chains": unique_chains,
            "gini_root_ca": round(gini, 3),
            "issues": issues,
            "fingerprint_set": {fp.oracle_id: fp.chain_hash for fp in self.fingerprints}
        }


def demo():
    registry = CAFingerprintRegistry()
    
    # Scenario 1: Independence theater — 5 oracles, 1 root CA
    print("=" * 50)
    print("Scenario: INDEPENDENCE THEATER")
    theater = CAFingerprintRegistry()
    for i in range(5):
        theater.register(CAFingerprint(
            oracle_id=f"oracle_{i}",
            root_ca="ca_root_letsencrypt_abc123",
            intermediate_ca=f"ca_inter_{i}",
            leaf_cert=f"leaf_{i}",
            ca_operator="letsencrypt",
            issued_at="2026-03-21T00:00:00Z"
        ))
    result = theater.audit()
    print(f"Grade: {result['grade']} | Verdict: {result['verdict']}")
    print(f"Oracles: {result['oracles']} | Unique roots: {result['unique_root_cas']} | Gini: {result['gini_root_ca']}")
    for issue in result['issues']:
        print(f"  [{issue['severity']}] {issue['type']}: {issue['detail']}")
    
    # Scenario 2: Healthy diverse
    print("\n" + "=" * 50)
    print("Scenario: HEALTHY DIVERSE")
    diverse = CAFingerprintRegistry()
    cas = [("digicert", "root_dc"), ("letsencrypt", "root_le"), ("comodo", "root_co"), 
           ("globalsign", "root_gs"), ("entrust", "root_en")]
    for i, (op, root) in enumerate(cas):
        diverse.register(CAFingerprint(
            oracle_id=f"oracle_{i}",
            root_ca=root,
            intermediate_ca=f"inter_{op}",
            leaf_cert=f"leaf_{i}",
            ca_operator=op,
            issued_at="2026-03-21T00:00:00Z"
        ))
    result = diverse.audit()
    print(f"Grade: {result['grade']} | Verdict: {result['verdict']}")
    print(f"Oracles: {result['oracles']} | Unique roots: {result['unique_root_cas']} | Gini: {result['gini_root_ca']}")
    for issue in result['issues']:
        print(f"  [{issue['severity']}] {issue['type']}: {issue['detail']}")
    
    # Scenario 3: Subtle concentration — 3/7 share root
    print("\n" + "=" * 50)
    print("Scenario: SUBTLE CONCENTRATION")
    subtle = CAFingerprintRegistry()
    configs = [
        ("o1", "root_a", "op_a"), ("o2", "root_a", "op_a"), ("o3", "root_a", "op_b"),
        ("o4", "root_b", "op_c"), ("o5", "root_c", "op_d"),
        ("o6", "root_d", "op_e"), ("o7", "root_e", "op_f"),
    ]
    for oid, root, op in configs:
        subtle.register(CAFingerprint(oid, root, f"inter_{oid}", f"leaf_{oid}", op, "2026-03-21"))
    result = subtle.audit()
    print(f"Grade: {result['grade']} | Verdict: {result['verdict']}")
    print(f"Oracles: {result['oracles']} | Unique roots: {result['unique_root_cas']} | Gini: {result['gini_root_ca']}")
    for issue in result['issues']:
        print(f"  [{issue['severity']}] {issue['type']}: {issue['detail']}")


if __name__ == "__main__":
    demo()
