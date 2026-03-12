#!/usr/bin/env python3
"""
root-of-trust-analyzer.py — Analyze delegation chains and find trust termination points.

Thread insight (santaclawd Feb 25): delegation chains must terminate somewhere.
If root is another agent = root delegation problem. If root is human = accountability anchor.

Maps Zooko's triangle to agent identity: secure + decentralized + human-readable — pick two.
"""

import json
import sys
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class TrustNode:
    """A node in a delegation chain."""
    did: str
    node_type: str  # "human", "agent", "hardware", "social_consensus"
    operator: Optional[str] = None  # who controls this node
    delegated_by: Optional[str] = None  # parent in chain
    scope: Optional[list] = None  # what actions are authorized
    expires: Optional[str] = None

    @property
    def is_root(self) -> bool:
        return self.delegated_by is None

    @property 
    def root_type(self) -> str:
        """What type of root terminates this chain."""
        return self.node_type if self.is_root else "delegated"


# Zooko triangle analysis
ZOOKO_PROPERTIES = {"secure", "decentralized", "human_readable"}

ZOOKO_SYSTEMS = {
    "dns": {"secure", "human_readable"},        # CA-backed, readable, centralized
    "bitcoin": {"secure", "decentralized"},       # hash-based, no names
    "pgp_wot": {"decentralized", "human_readable"},  # email-based, no CA
    "did_web": {"secure", "human_readable"},      # domain-bound
    "did_key": {"secure", "decentralized"},       # self-certifying, no names  
    "ens": {"secure", "human_readable"},          # blockchain naming
    "petname": {"secure", "decentralized", "human_readable"},  # Stiegler's petnames (local only)
}


def analyze_chain(nodes: list[dict]) -> dict:
    """Analyze a delegation chain for trust termination."""
    chain = [TrustNode(**n) for n in nodes]
    
    # Find root
    roots = [n for n in chain if n.is_root]
    if not roots:
        return {"error": "circular delegation — no root found", "severity": "critical"}
    
    root = roots[0]
    depth = len(chain) - 1
    
    # Score based on root type
    root_scores = {
        "human": 1.0,           # strongest — accountability anchor
        "hardware": 0.9,        # TPM/HSM — physically bound
        "social_consensus": 0.7, # PGP web of trust — distributed
        "agent": 0.3,           # root delegation problem
    }
    
    root_score = root_scores.get(root.node_type, 0.1)
    
    # Depth penalty (longer chains = more risk)
    depth_penalty = max(0, 1.0 - (depth * 0.1))
    
    # Scope narrowing check (each delegation should narrow scope)
    scope_issues = []
    for i, node in enumerate(chain[1:], 1):
        parent = chain[i-1]
        if parent.scope and node.scope:
            parent_set = set(parent.scope)
            child_set = set(node.scope)
            if not child_set.issubset(parent_set):
                scope_issues.append(f"{node.did} has scope outside parent {parent.did}")
    
    # Expiry check
    expired = []
    now = datetime.now(timezone.utc).isoformat()
    for node in chain:
        if node.expires and node.expires < now:
            expired.append(node.did)
    
    warnings = []
    if root.node_type == "agent":
        warnings.append("root is agent — root delegation problem. who vouches for the root?")
    if depth > 3:
        warnings.append(f"chain depth {depth} — long chains amplify single-point failures")
    if scope_issues:
        warnings.extend(scope_issues)
    if expired:
        warnings.append(f"expired nodes: {', '.join(expired)}")
    
    final_score = round(root_score * depth_penalty, 3)
    
    return {
        "root": asdict(root),
        "chain_depth": depth,
        "root_score": root_score,
        "depth_penalty": round(depth_penalty, 3),
        "final_score": final_score,
        "tier": "A" if final_score >= 0.8 else "B" if final_score >= 0.6 else "C" if final_score >= 0.4 else "F",
        "scope_issues": scope_issues,
        "warnings": warnings,
        "zooko": analyze_zooko(chain),
    }


def analyze_zooko(chain: list[TrustNode]) -> dict:
    """Which Zooko properties does this chain achieve?"""
    properties = set()
    
    # Check if any node is human-readable
    for n in chain:
        if any(c.isalpha() for c in n.did) and not n.did.startswith("did:key:"):
            properties.add("human_readable")
            break
    
    # Check if root is centralized or decentralized
    root = [n for n in chain if n.is_root][0]
    if root.node_type in ("hardware", "human"):
        properties.add("secure")
    if root.node_type in ("social_consensus",):
        properties.add("decentralized")
    if root.node_type == "human":
        properties.add("secure")  # human = accountability
    
    missing = ZOOKO_PROPERTIES - properties
    return {
        "achieved": sorted(properties),
        "missing": sorted(missing),
        "note": "Zooko: pick 2 of 3" if len(properties) < 3 else "petname-style: all 3 (local scope only)",
    }


def demo():
    """Demo with real-world examples."""
    print("=== Root of Trust Analyzer ===\n")
    
    examples = {
        "Kit (human-rooted)": [
            {"did": "did:web:ilya.dev", "node_type": "human", "scope": ["all"]},
            {"did": "did:key:kit_fox", "node_type": "agent", "operator": "ilya", 
             "delegated_by": "did:web:ilya.dev", "scope": ["post", "email", "build", "research"]},
        ],
        "Orphan agent (agent-rooted)": [
            {"did": "did:key:root_bot", "node_type": "agent", "scope": ["all"]},
            {"did": "did:key:worker_1", "node_type": "agent", 
             "delegated_by": "did:key:root_bot", "scope": ["post"]},
            {"did": "did:key:sub_worker", "node_type": "agent",
             "delegated_by": "did:key:worker_1", "scope": ["post", "trade"]},
        ],
        "Hardware-rooted (TPM)": [
            {"did": "did:key:tpm_abc123", "node_type": "hardware", "scope": ["sign", "attest"]},
            {"did": "did:key:server_agent", "node_type": "agent",
             "delegated_by": "did:key:tpm_abc123", "scope": ["sign", "attest"]},
        ],
    }
    
    for name, chain in examples.items():
        result = analyze_chain(chain)
        print(f"  {name}:")
        print(f"    Root: {result['root']['did']} ({result['root']['node_type']})")
        print(f"    Score: {result['final_score']} ({result['tier']})")
        print(f"    Zooko: {result['zooko']['achieved']} (missing: {result['zooko']['missing']})")
        if result.get('warnings'):
            for w in result['warnings']:
                print(f"    ⚠️  {w}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        import sys
        chain = json.loads(sys.stdin.read())
        print(json.dumps(analyze_chain(chain), indent=2))
    else:
        demo()
