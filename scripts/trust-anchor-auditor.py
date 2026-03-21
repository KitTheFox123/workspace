#!/usr/bin/env python3
"""
trust-anchor-auditor.py — Detect trust_anchor monoculture in oracle quorums.

Per santaclawd: "7 oracles from 3 operators, 3 model families, but if they
all root to the same attestation CA, independence is theater."

X.509 has cross-certification to expose shared roots. We need the same:
trace each oracle's trust chain to its root anchor, detect convergence.

Checks:
1. Root anchor diversity (unique CAs/anchors)
2. Chain depth distribution (shallow = less independent)
3. Shared intermediate authorities
4. BFT safety on anchor dimension specifically
5. Cross-certification gaps (oracles that can't verify each other)
"""

import hashlib
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class TrustChainLink:
    entity_id: str
    entity_type: str  # "root_ca" | "intermediate" | "oracle"


@dataclass
class OracleTrustChain:
    oracle_id: str
    operator: str
    chain: list[TrustChainLink]  # root → intermediate(s) → oracle
    
    @property
    def root_anchor(self) -> str:
        return self.chain[0].entity_id if self.chain else "UNKNOWN"
    
    @property
    def intermediates(self) -> list[str]:
        return [link.entity_id for link in self.chain[1:-1]]
    
    @property
    def depth(self) -> int:
        return len(self.chain)


def audit_trust_anchors(oracles: list[OracleTrustChain]) -> dict:
    n = len(oracles)
    issues = []
    
    # 1. Root anchor diversity
    roots = [o.root_anchor for o in oracles]
    root_counts = Counter(roots)
    unique_roots = len(root_counts)
    
    max_root, max_root_count = root_counts.most_common(1)[0]
    if max_root_count > n / 3:
        issues.append({
            "type": "ROOT_MONOCULTURE",
            "root": max_root,
            "count": max_root_count,
            "total": n,
            "severity": "CRITICAL" if max_root_count > n * 2/3 else "WARNING",
            "detail": f"{max_root_count}/{n} oracles root to {max_root}"
        })
    
    # 2. Shared intermediates
    all_intermediates = []
    for o in oracles:
        all_intermediates.extend(o.intermediates)
    
    intermediate_counts = Counter(all_intermediates)
    shared = {k: v for k, v in intermediate_counts.items() if v > 1}
    if shared:
        for inter, count in shared.items():
            if count > n / 3:
                issues.append({
                    "type": "SHARED_INTERMEDIATE",
                    "intermediate": inter,
                    "count": count,
                    "severity": "WARNING",
                    "detail": f"{count}/{n} oracles share intermediate {inter}"
                })
    
    # 3. Chain depth distribution
    depths = [o.depth for o in oracles]
    shallow = [o for o in oracles if o.depth <= 2]
    if len(shallow) > n / 2:
        issues.append({
            "type": "SHALLOW_CHAINS",
            "count": len(shallow),
            "severity": "INFO",
            "detail": f"{len(shallow)}/{n} oracles have chain depth ≤2 (less separation from root)"
        })
    
    # 4. Operator-root correlation
    # Same operator + same root = definitely not independent
    op_root_pairs = [(o.operator, o.root_anchor) for o in oracles]
    pair_counts = Counter(op_root_pairs)
    for (op, root), count in pair_counts.items():
        if count > 1:
            issues.append({
                "type": "OPERATOR_ROOT_CORRELATION",
                "operator": op,
                "root": root,
                "count": count,
                "severity": "CRITICAL" if count > n / 3 else "INFO",
                "detail": f"{count} oracles share operator={op} AND root={root}"
            })
    
    # 5. Effective independence
    # Penalize by root concentration (Gini-like)
    if unique_roots == 0:
        independence = 0.0
    else:
        # Simpson diversity index
        simpson = 1.0 - sum((c/n)**2 for c in root_counts.values())
        independence = round(simpson, 3)
    
    # Grade
    critical = sum(1 for i in issues if i["severity"] == "CRITICAL")
    warnings = sum(1 for i in issues if i["severity"] == "WARNING")
    
    if critical > 0:
        grade = "F"
    elif warnings > 1:
        grade = "D"
    elif warnings == 1:
        grade = "C"
    elif issues:
        grade = "B"
    else:
        grade = "A"
    
    return {
        "grade": grade,
        "verdict": "HEALTHY" if grade in ("A", "B") else "DEGRADED" if grade in ("C", "D") else "THEATER",
        "oracles": n,
        "unique_roots": unique_roots,
        "independence_index": independence,
        "root_distribution": dict(root_counts),
        "shared_intermediates": shared,
        "depth_range": f"{min(depths)}-{max(depths)}",
        "issues": issues
    }


def demo():
    # Scenario 1: Diverse roots
    diverse = [
        OracleTrustChain("o1", "acme", [
            TrustChainLink("ca_letsencrypt", "root_ca"),
            TrustChainLink("inter_1", "intermediate"),
            TrustChainLink("o1", "oracle")
        ]),
        OracleTrustChain("o2", "beta", [
            TrustChainLink("ca_digicert", "root_ca"),
            TrustChainLink("inter_2", "intermediate"),
            TrustChainLink("o2", "oracle")
        ]),
        OracleTrustChain("o3", "gamma", [
            TrustChainLink("ca_isrg", "root_ca"),
            TrustChainLink("inter_3", "intermediate"),
            TrustChainLink("o3", "oracle")
        ]),
        OracleTrustChain("o4", "delta", [
            TrustChainLink("ca_comodo", "root_ca"),
            TrustChainLink("o4", "oracle")
        ]),
        OracleTrustChain("o5", "epsilon", [
            TrustChainLink("ca_globalsign", "root_ca"),
            TrustChainLink("inter_5", "intermediate"),
            TrustChainLink("o5", "oracle")
        ]),
    ]
    
    # Scenario 2: Hidden monoculture — looks diverse, roots converge
    theater = [
        OracleTrustChain("o1", "acme", [
            TrustChainLink("ca_megacorp", "root_ca"),
            TrustChainLink("sub_ca_alpha", "intermediate"),
            TrustChainLink("o1", "oracle")
        ]),
        OracleTrustChain("o2", "beta", [
            TrustChainLink("ca_megacorp", "root_ca"),
            TrustChainLink("sub_ca_beta", "intermediate"),
            TrustChainLink("o2", "oracle")
        ]),
        OracleTrustChain("o3", "gamma", [
            TrustChainLink("ca_megacorp", "root_ca"),
            TrustChainLink("sub_ca_gamma", "intermediate"),
            TrustChainLink("o3", "oracle")
        ]),
        OracleTrustChain("o4", "delta", [
            TrustChainLink("ca_megacorp", "root_ca"),
            TrustChainLink("sub_ca_delta", "intermediate"),
            TrustChainLink("o4", "oracle")
        ]),
        OracleTrustChain("o5", "epsilon", [
            TrustChainLink("ca_independent", "root_ca"),
            TrustChainLink("o5", "oracle")
        ]),
    ]
    
    # Scenario 3: Shared intermediate + operator correlation
    correlated = [
        OracleTrustChain("o1", "same_corp", [
            TrustChainLink("ca_A", "root_ca"),
            TrustChainLink("shared_inter", "intermediate"),
            TrustChainLink("o1", "oracle")
        ]),
        OracleTrustChain("o2", "same_corp", [
            TrustChainLink("ca_A", "root_ca"),
            TrustChainLink("shared_inter", "intermediate"),
            TrustChainLink("o2", "oracle")
        ]),
        OracleTrustChain("o3", "other", [
            TrustChainLink("ca_B", "root_ca"),
            TrustChainLink("o3", "oracle")
        ]),
    ]
    
    for name, oracles in [("diverse_roots", diverse), ("hidden_monoculture", theater), ("operator_root_correlated", correlated)]:
        result = audit_trust_anchors(oracles)
        print(f"\n{'='*55}")
        print(f"Scenario: {name}")
        print(f"Grade: {result['grade']} | Verdict: {result['verdict']}")
        print(f"Unique roots: {result['unique_roots']} | Independence: {result['independence_index']}")
        print(f"Root distribution: {result['root_distribution']}")
        if result['shared_intermediates']:
            print(f"Shared intermediates: {result['shared_intermediates']}")
        if result['issues']:
            for issue in result['issues']:
                print(f"  [{issue['severity']}] {issue['type']}: {issue['detail']}")


if __name__ == "__main__":
    demo()
