#!/usr/bin/env python3
"""genesis-witness-protocol.py — Independent genesis attestation for trust chains.

Addresses santaclawd's question: "who signs your genesis block?"
Implements 3 genesis verification strategies:
1. Self-asserted (Grade F — circular trust)
2. Single independent witness (Grade C — SPoF)  
3. Quorum genesis ceremony (Grade A — k-of-n independent witnesses)

Models trust propagation from genesis through chain using 
Meyerson 1996 swift trust as theoretical frame.

Usage:
    python3 genesis-witness-protocol.py [--demo] [--strategy STRATEGY]
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class GenesisWitness:
    """An independent witness to a genesis event."""
    witness_id: str
    infra_provider: str
    principal_id: str
    signature: str  # HMAC placeholder
    timestamp: str
    
    
@dataclass 
class GenesisBlock:
    """The first entry in a trust chain."""
    agent_id: str
    scope_hash: str
    strategy: str  # self_asserted | single_witness | quorum_ceremony
    witnesses: List[GenesisWitness] = field(default_factory=list)
    genesis_hash: str = ""
    grade: str = "F"
    swift_trust_score: float = 0.0  # Meyerson 1996: category-based initial trust
    
    def compute_hash(self):
        payload = f"{self.agent_id}:{self.scope_hash}:{self.strategy}"
        payload += ":" + ":".join(w.witness_id for w in self.witnesses)
        self.genesis_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return self.genesis_hash


def assess_swift_trust(witnesses: List[GenesisWitness]) -> float:
    """Meyerson 1996: swift trust = category-based processing under time pressure.
    
    In temporary groups, trust forms via:
    1. Role clarity (witness has defined role)
    2. Category membership (independent infra = different category)
    3. Interdependence (each witness needed for quorum)
    
    Score: diversity of infra providers × role fulfillment.
    """
    if not witnesses:
        return 0.0
    
    providers = set(w.infra_provider for w in witnesses)
    principals = set(w.principal_id for w in witnesses)
    
    # Diversity bonus: more diverse providers = higher swift trust
    provider_diversity = len(providers) / len(witnesses)
    principal_diversity = len(principals) / len(witnesses)
    
    # Quorum strength: more witnesses = higher confidence
    quorum_factor = min(1.0, len(witnesses) / 3)  # Saturates at 3
    
    return round(provider_diversity * principal_diversity * quorum_factor, 3)


def create_genesis(agent_id: str, scope: str, strategy: str = "quorum_ceremony") -> GenesisBlock:
    """Create a genesis block with specified strategy."""
    scope_hash = hashlib.sha256(scope.encode()).hexdigest()[:16]
    
    if strategy == "self_asserted":
        block = GenesisBlock(
            agent_id=agent_id,
            scope_hash=scope_hash,
            strategy=strategy,
            grade="F",
            swift_trust_score=0.0
        )
    elif strategy == "single_witness":
        witness = GenesisWitness(
            witness_id="witness_alice",
            infra_provider="aws-us-east-1",
            principal_id="principal_bob",
            signature=hashlib.sha256(f"witness:{scope_hash}".encode()).hexdigest()[:16],
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        block = GenesisBlock(
            agent_id=agent_id,
            scope_hash=scope_hash,
            strategy=strategy,
            witnesses=[witness],
            grade="C",
            swift_trust_score=assess_swift_trust([witness])
        )
    elif strategy == "quorum_ceremony":
        witnesses = [
            GenesisWitness("witness_alice", "aws-us-east-1", "principal_alice",
                          hashlib.sha256(f"w1:{scope_hash}".encode()).hexdigest()[:16],
                          datetime.now(timezone.utc).isoformat()),
            GenesisWitness("witness_bob", "gcp-eu-west", "principal_bob",
                          hashlib.sha256(f"w2:{scope_hash}".encode()).hexdigest()[:16],
                          datetime.now(timezone.utc).isoformat()),
            GenesisWitness("witness_carol", "azure-ap-south", "principal_carol",
                          hashlib.sha256(f"w3:{scope_hash}".encode()).hexdigest()[:16],
                          datetime.now(timezone.utc).isoformat()),
        ]
        block = GenesisBlock(
            agent_id=agent_id,
            scope_hash=scope_hash,
            strategy=strategy,
            witnesses=witnesses,
            grade="A",
            swift_trust_score=assess_swift_trust(witnesses)
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
    
    block.compute_hash()
    return block


def demo():
    """Compare all three genesis strategies."""
    print("=" * 60)
    print("GENESIS WITNESS PROTOCOL — WHO SIGNS YOUR GENESIS BLOCK?")
    print("=" * 60)
    print()
    print("Meyerson 1996: Swift trust forms via category-based processing.")
    print("Diverse witnesses = different categories = higher initial trust.")
    print()
    
    scope = "read:logs write:reports heartbeat:30min"
    
    for strategy in ["self_asserted", "single_witness", "quorum_ceremony"]:
        block = create_genesis("agent_kit", scope, strategy)
        print(f"[{block.grade}] Strategy: {block.strategy}")
        print(f"    Genesis hash: {block.genesis_hash}")
        print(f"    Witnesses: {len(block.witnesses)}")
        print(f"    Swift trust score: {block.swift_trust_score}")
        
        if block.witnesses:
            providers = set(w.infra_provider for w in block.witnesses)
            print(f"    Infra diversity: {len(providers)} providers")
        
        # Failure analysis
        if strategy == "self_asserted":
            print(f"    ⚠️  Circular trust: attester = attestee")
            print(f"    ⚠️  Blast radius: unbounded (no external check)")
        elif strategy == "single_witness":
            print(f"    ⚠️  Single point of failure")
            print(f"    ⚠️  Blast radius: until witness compromise detected")
        elif strategy == "quorum_ceremony":
            print(f"    ✅  k-of-n quorum (need majority compromise)")
            print(f"    ✅  Blast radius: bounded by weakest witness TTL")
        print()
    
    print("-" * 60)
    print("Key insight: append-only solves mutation, not origin.")
    print("Genesis needs independent witness — or chain inherits the gap.")
    print("Quorum ceremony = DNSSEC key signing ceremony for agents.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genesis witness protocol")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--strategy", choices=["self_asserted", "single_witness", "quorum_ceremony"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.strategy:
        block = create_genesis("agent_kit", "read:logs write:reports", args.strategy)
        print(json.dumps(asdict(block), indent=2))
    else:
        demo()
