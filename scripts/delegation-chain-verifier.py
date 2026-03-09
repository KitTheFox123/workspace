#!/usr/bin/env python3
"""delegation-chain-verifier.py — Capability-based delegation chain verifier.

Verifies that authority monotonically decreases through delegation chains.
Based on Hardy 1988 (confused deputy) + Niyikiza 2025 (capabilities for agent delegation).

Key principle: delegation is an OPERATION on authority, not an attribute of identity.
IAM checks "who are you?" — capabilities check "where did this authority come from?"

Usage:
    python3 delegation-chain-verifier.py [--demo]
"""

import argparse
import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Set
from datetime import datetime, timezone


@dataclass
class Capability:
    """An unforgeable token granting specific access."""
    resource: str
    actions: Set[str]
    scope_hash: str = ""
    ttl_hours: float = 24.0
    
    def __post_init__(self):
        if not self.scope_hash:
            data = f"{self.resource}:{sorted(self.actions)}:{self.ttl_hours}"
            self.scope_hash = hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def is_subset_of(self, parent: 'Capability') -> bool:
        """Check if this capability is a valid attenuation of parent."""
        if self.resource != parent.resource:
            return False
        if not self.actions.issubset(parent.actions):
            return False
        if self.ttl_hours > parent.ttl_hours:
            return False
        return True


@dataclass
class DelegationHop:
    """A single hop in a delegation chain."""
    delegator: str
    delegatee: str
    capability: Capability
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass 
class DelegationChain:
    """A chain of capability delegations."""
    hops: List[DelegationHop] = field(default_factory=list)
    
    def verify(self) -> dict:
        """Verify the entire chain. Returns verdict."""
        if not self.hops:
            return {"valid": False, "grade": "F", "reason": "Empty chain"}
        
        violations = []
        
        for i in range(1, len(self.hops)):
            parent_cap = self.hops[i-1].capability
            child_cap = self.hops[i].capability
            
            # Check monotonic attenuation
            if not child_cap.is_subset_of(parent_cap):
                extra_actions = child_cap.actions - parent_cap.actions
                violations.append({
                    "hop": i,
                    "type": "escalation",
                    "delegator": self.hops[i].delegator,
                    "delegatee": self.hops[i].delegatee,
                    "detail": f"Actions {extra_actions} not in parent scope"
                })
            
            # Check TTL doesn't extend
            if child_cap.ttl_hours > parent_cap.ttl_hours:
                violations.append({
                    "hop": i,
                    "type": "ttl_extension",
                    "delegator": self.hops[i].delegator,
                    "delegatee": self.hops[i].delegatee,
                    "detail": f"TTL {child_cap.ttl_hours}h > parent {parent_cap.ttl_hours}h"
                })
            
            # Check continuity
            if self.hops[i].delegator != self.hops[i-1].delegatee:
                violations.append({
                    "hop": i,
                    "type": "chain_break",
                    "detail": f"Gap: {self.hops[i-1].delegatee} → {self.hops[i].delegator}"
                })
        
        # Confused deputy check: does any delegatee use capabilities beyond delegation?
        # (Would need runtime trace — here we check structural validity)
        
        if not violations:
            grade = "A"
            if len(self.hops) > 3:
                grade = "B"  # Long chains = more risk
        else:
            escalations = sum(1 for v in violations if v["type"] == "escalation")
            ttl_extensions = sum(1 for v in violations if v["type"] == "ttl_extension")
            chain_breaks = sum(1 for v in violations if v["type"] == "chain_break")
            if escalations > 0:
                grade = "F"  # Privilege escalation = critical
            elif ttl_extensions > 0:
                grade = "F"  # TTL extension = authority persistence attack
            elif chain_breaks > 0:
                grade = "D"  # Gap = provenance failure
            else:
                grade = "D"
        
        return {
            "valid": len(violations) == 0,
            "grade": grade,
            "chain_length": len(self.hops),
            "violations": violations,
            "root_authority": self.hops[0].delegator,
            "leaf_agent": self.hops[-1].delegatee,
            "attenuation_ratio": self._attenuation_ratio()
        }
    
    def _attenuation_ratio(self) -> float:
        """How much authority was shed from root to leaf."""
        if len(self.hops) < 2:
            return 0.0
        root_actions = len(self.hops[0].capability.actions)
        leaf_actions = len(self.hops[-1].capability.actions)
        if root_actions == 0:
            return 0.0
        return 1.0 - (leaf_actions / root_actions)


def demo():
    """Run demo scenarios."""
    print("=" * 60)
    print("DELEGATION CHAIN VERIFIER")
    print("Niyikiza 2025 + Hardy 1988")
    print("=" * 60)
    
    # Scenario 1: Valid attenuation (valet key)
    print("\n--- Scenario 1: Valid Attenuation (Valet Key) ---")
    chain1 = DelegationChain(hops=[
        DelegationHop("ilya", "kit", Capability("codebase", {"read", "write", "deploy"}, ttl_hours=24)),
        DelegationHop("kit", "sub_agent", Capability("codebase", {"read", "write"}, ttl_hours=4)),
        DelegationHop("sub_agent", "linter", Capability("codebase", {"read"}, ttl_hours=1)),
    ])
    result1 = chain1.verify()
    print(f"  Grade: {result1['grade']} | Valid: {result1['valid']}")
    print(f"  Attenuation: {result1['attenuation_ratio']:.0%} authority shed")
    
    # Scenario 2: Privilege escalation (confused deputy)
    print("\n--- Scenario 2: Privilege Escalation (Confused Deputy) ---")
    chain2 = DelegationChain(hops=[
        DelegationHop("ilya", "kit", Capability("codebase", {"read", "write"}, ttl_hours=24)),
        DelegationHop("kit", "rogue_agent", Capability("codebase", {"read", "write", "deploy", "delete"}, ttl_hours=48)),
    ])
    result2 = chain2.verify()
    print(f"  Grade: {result2['grade']} | Valid: {result2['valid']}")
    for v in result2['violations']:
        print(f"  ⚠️ {v['type']}: {v['detail']}")
    
    # Scenario 3: Chain break (gap in delegation)
    print("\n--- Scenario 3: Chain Break ---")
    chain3 = DelegationChain(hops=[
        DelegationHop("ilya", "kit", Capability("api", {"call"}, ttl_hours=8)),
        DelegationHop("unknown", "worker", Capability("api", {"call"}, ttl_hours=4)),
    ])
    result3 = chain3.verify()
    print(f"  Grade: {result3['grade']} | Valid: {result3['valid']}")
    for v in result3['violations']:
        print(f"  ⚠️ {v['type']}: {v['detail']}")
    
    # Scenario 4: TTL extension attack
    print("\n--- Scenario 4: TTL Extension ---")
    chain4 = DelegationChain(hops=[
        DelegationHop("ilya", "kit", Capability("data", {"read"}, ttl_hours=2)),
        DelegationHop("kit", "cache", Capability("data", {"read"}, ttl_hours=720)),
    ])
    result4 = chain4.verify()
    print(f"  Grade: {result4['grade']} | Valid: {result4['valid']}")
    for v in result4['violations']:
        print(f"  ⚠️ {v['type']}: {v['detail']}")
    
    print("\n" + "=" * 60)
    print("Key insight: IAM checks identity. Capabilities check derivation.")
    print("Authority must monotonically decrease through delegation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delegation chain verifier")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        chain = DelegationChain(hops=[
            DelegationHop("ilya", "kit", Capability("codebase", {"read", "write", "deploy"}, ttl_hours=24)),
            DelegationHop("kit", "sub_agent", Capability("codebase", {"read", "write"}, ttl_hours=4)),
        ])
        print(json.dumps(chain.verify(), indent=2))
    else:
        demo()
