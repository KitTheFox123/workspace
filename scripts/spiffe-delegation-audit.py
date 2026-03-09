#!/usr/bin/env python3
"""spiffe-delegation-audit.py — SPIFFE-inspired delegation chain auditor.

Maps SPIFFE trust domain / SVID concepts to agent delegation chains.
Verifies: trust domain membership, chain attenuation, SVID freshness,
federation boundaries.

Based on SPIFFE spec + Niyikiza 2025 + Hardy 1988.

Usage:
    python3 spiffe-delegation-audit.py [--demo]
"""

import argparse
import json
import hashlib
from dataclasses import dataclass, asdict, field
from typing import List, Optional
from datetime import datetime, timezone, timedelta


@dataclass
class SVID:
    """SPIFFE Verifiable Identity Document for agents."""
    spiffe_id: str  # spiffe://trust-domain/path
    issuer: str
    subject: str
    capabilities: List[str]
    ttl_hours: float
    issued_at: str
    parent_svid_hash: Optional[str] = None
    
    @property
    def trust_domain(self) -> str:
        return self.spiffe_id.split("//")[1].split("/")[0]
    
    @property
    def is_expired(self) -> bool:
        issued = datetime.fromisoformat(self.issued_at.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > issued + timedelta(hours=self.ttl_hours)
    
    @property
    def hash(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class DelegationChain:
    """Chain of SVIDs from root to leaf."""
    svids: List[SVID]
    
    def audit(self) -> dict:
        issues = []
        grade_score = 100
        
        if not self.svids:
            return {"grade": "F", "score": 0, "issues": ["Empty chain"]}
        
        # Check 1: Trust domain consistency
        domains = set(s.trust_domain for s in self.svids)
        if len(domains) > 1:
            issues.append(f"Cross-domain delegation: {domains} (federation required)")
            grade_score -= 20
        
        # Check 2: Monotonic capability attenuation
        for i in range(1, len(self.svids)):
            parent_caps = set(self.svids[i-1].capabilities)
            child_caps = set(self.svids[i].capabilities)
            if not child_caps.issubset(parent_caps):
                escalated = child_caps - parent_caps
                issues.append(f"Privilege escalation at hop {i}: +{escalated}")
                grade_score -= 30
        
        # Check 3: TTL attenuation
        for i in range(1, len(self.svids)):
            if self.svids[i].ttl_hours > self.svids[i-1].ttl_hours:
                issues.append(f"TTL extension at hop {i}: {self.svids[i-1].ttl_hours}h → {self.svids[i].ttl_hours}h")
                grade_score -= 25
        
        # Check 4: Chain continuity (parent hash linkage)
        for i in range(1, len(self.svids)):
            if self.svids[i].parent_svid_hash != self.svids[i-1].hash:
                issues.append(f"Chain break at hop {i}: parent hash mismatch")
                grade_score -= 30
        
        # Check 5: Freshness
        expired = [s for s in self.svids if s.is_expired]
        if expired:
            issues.append(f"{len(expired)} expired SVID(s) in chain")
            grade_score -= 20 * len(expired)
        
        # Check 6: Root is human-accountable
        root = self.svids[0]
        if "human" not in root.issuer.lower() and "principal" not in root.issuer.lower():
            issues.append(f"Root issuer '{root.issuer}' not human-accountable (HRoT gap)")
            grade_score -= 15
        
        grade_score = max(0, grade_score)
        grade = "A" if grade_score >= 90 else "B" if grade_score >= 75 else "C" if grade_score >= 60 else "D" if grade_score >= 40 else "F"
        
        authority_shed = 0
        if len(self.svids) > 1:
            root_caps = len(self.svids[0].capabilities)
            leaf_caps = len(self.svids[-1].capabilities)
            authority_shed = (root_caps - leaf_caps) / max(root_caps, 1)
        
        return {
            "grade": grade,
            "score": grade_score,
            "chain_length": len(self.svids),
            "trust_domains": list(domains),
            "authority_shed_pct": round(authority_shed * 100, 1),
            "issues": issues if issues else ["Clean chain"],
            "root_issuer": self.svids[0].issuer,
            "leaf_agent": self.svids[-1].subject,
        }


def demo():
    now = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    
    # Scenario 1: Valid attenuated chain
    root = SVID("spiffe://ilya.trust/principal", "principal_ilya", "ilya",
                 ["read", "write", "execute", "delegate", "admin"], 720, now)
    mid = SVID("spiffe://ilya.trust/kit", root.issuer, "kit",
               ["read", "write", "execute"], 24, now, root.hash)
    leaf = SVID("spiffe://ilya.trust/kit/subtask", "kit", "kit-subtask",
                ["read", "write"], 4, now, mid.hash)
    
    chain1 = DelegationChain([root, mid, leaf])
    
    # Scenario 2: Privilege escalation
    bad_leaf = SVID("spiffe://ilya.trust/kit/rogue", "kit", "kit-rogue",
                    ["read", "write", "admin"], 4, now, mid.hash)  # admin not in mid!
    chain2 = DelegationChain([root, mid, bad_leaf])
    
    # Scenario 3: Expired + chain break
    exp = SVID("spiffe://ilya.trust/kit/old", "kit", "kit-old",
               ["read"], 2, old, "wrong_hash")
    chain3 = DelegationChain([root, mid, exp])
    
    # Scenario 4: Cross-domain (federation)
    foreign = SVID("spiffe://gendolf.trust/collab", "gendolf", "gendolf-collab",
                   ["read"], 4, now, mid.hash)
    chain4 = DelegationChain([root, mid, foreign])
    
    scenarios = [
        ("Valid attenuated chain", chain1),
        ("Privilege escalation", chain2),
        ("Expired + chain break", chain3),
        ("Cross-domain federation", chain4),
    ]
    
    print("=" * 60)
    print("SPIFFE DELEGATION CHAIN AUDIT")
    print("=" * 60)
    
    for name, chain in scenarios:
        result = chain.audit()
        print(f"\n[{result['grade']}] {name}")
        print(f"    Chain: {result['chain_length']} hops, {result['root_issuer']} → {result['leaf_agent']}")
        print(f"    Authority shed: {result['authority_shed_pct']}%")
        print(f"    Domains: {result['trust_domains']}")
        for issue in result['issues']:
            print(f"    • {issue}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
