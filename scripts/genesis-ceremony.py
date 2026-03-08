#!/usr/bin/env python3
"""genesis-ceremony.py — Agent trust genesis ceremony generator.

Creates the initial scope-commit with multi-party witnessing, 
inspired by DNSSEC root key ceremonies and PKI key generation ceremonies.

The genesis entry is the one you cannot verify from within the chain.
It requires external anchoring: principal signature + independent witness
co-signature + external timestamp anchor.

Usage:
    python3 genesis-ceremony.py --demo
    python3 genesis-ceremony.py --principal "Ilya" --agent "Kit" --scope "HEARTBEAT.md"
"""

import argparse
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class CeremonyParticipant:
    """A participant in the genesis ceremony."""
    role: str  # "principal", "witness", "agent"
    name: str
    key_hash: str  # SHA-256 of their public key (placeholder)
    signature: str  # HMAC signature (placeholder for Ed25519)


@dataclass
class GenesisRecord:
    """The genesis block of an agent's trust chain."""
    version: str
    timestamp: str
    agent_id: str
    principal_id: str
    scope_hash: str
    scope_source: str
    external_anchor: str  # External timestamp (e.g., block hash, news headline)
    participants: List[dict]
    ceremony_hash: str
    chain_id: str  # Unique chain identifier


def hash_scope(scope_path: str) -> str:
    """Hash a scope document."""
    if os.path.exists(scope_path):
        with open(scope_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    return hashlib.sha256(scope_path.encode()).hexdigest()


def generate_key_hash(name: str) -> str:
    """Generate placeholder key hash."""
    return hashlib.sha256(f"pubkey:{name}:{os.urandom(8).hex()}".encode()).hexdigest()[:16]


def sign_ceremony(data: str, key: str) -> str:
    """Generate HMAC signature (placeholder for Ed25519)."""
    return hmac.new(key.encode(), data.encode(), hashlib.sha256).hexdigest()[:32]


def create_genesis(principal: str, agent: str, scope_path: str, 
                   witnesses: List[str] = None, anchor: str = None) -> GenesisRecord:
    """Create a genesis ceremony record."""
    if witnesses is None:
        witnesses = ["witness_1"]
    
    now = datetime.now(timezone.utc)
    scope_hash = hash_scope(scope_path)
    
    # External anchor — in production, this would be a Bitcoin block hash,
    # a news headline, or another independently verifiable timestamp
    if anchor is None:
        anchor = f"UTC:{now.strftime('%Y-%m-%dT%H:%M:%SZ')}:self-declared"
    
    # Build ceremony data for signing
    ceremony_data = f"{agent}:{principal}:{scope_hash}:{now.isoformat()}:{anchor}"
    chain_id = hashlib.sha256(ceremony_data.encode()).hexdigest()[:16]
    
    # Participants sign
    participants = []
    
    # Principal signs first
    p_key_hash = generate_key_hash(principal)
    p_sig = sign_ceremony(ceremony_data, f"key:{principal}")
    participants.append(asdict(CeremonyParticipant(
        role="principal", name=principal, key_hash=p_key_hash, signature=p_sig
    )))
    
    # Agent acknowledges
    a_key_hash = generate_key_hash(agent)
    a_sig = sign_ceremony(ceremony_data, f"key:{agent}")
    participants.append(asdict(CeremonyParticipant(
        role="agent", name=agent, key_hash=a_key_hash, signature=a_sig
    )))
    
    # Witnesses co-sign
    for w in witnesses:
        w_key_hash = generate_key_hash(w)
        w_sig = sign_ceremony(ceremony_data, f"key:{w}")
        participants.append(asdict(CeremonyParticipant(
            role="witness", name=w, key_hash=w_key_hash, signature=w_sig
        )))
    
    # Ceremony hash = hash of all signatures
    all_sigs = ":".join(p["signature"] for p in participants)
    ceremony_hash = hashlib.sha256(all_sigs.encode()).hexdigest()
    
    return GenesisRecord(
        version="1.0",
        timestamp=now.isoformat(),
        agent_id=agent,
        principal_id=principal,
        scope_hash=scope_hash,
        scope_source=scope_path,
        external_anchor=anchor,
        participants=participants,
        ceremony_hash=ceremony_hash,
        chain_id=chain_id
    )


def verify_genesis(record: GenesisRecord) -> dict:
    """Verify genesis ceremony completeness."""
    checks = {}
    
    # Must have principal
    principals = [p for p in record.participants if p["role"] == "principal"]
    checks["has_principal"] = len(principals) >= 1
    
    # Must have at least one witness
    witnesses = [p for p in record.participants if p["role"] == "witness"]
    checks["has_witness"] = len(witnesses) >= 1
    
    # Must have agent acknowledgment
    agents = [p for p in record.participants if p["role"] == "agent"]
    checks["has_agent"] = len(agents) >= 1
    
    # Must have external anchor
    checks["has_anchor"] = bool(record.external_anchor) and "self-declared" not in record.external_anchor
    
    # Must have scope hash
    checks["has_scope"] = bool(record.scope_hash)
    
    # Grade
    passed = sum(checks.values())
    total = len(checks)
    if passed == total:
        grade = "A"
    elif passed >= total - 1:
        grade = "B"
    elif passed >= total - 2:
        grade = "C"
    else:
        grade = "F"
    
    return {
        "checks": checks,
        "passed": passed,
        "total": total,
        "grade": grade,
        "note": "Grade B common — external anchor often self-declared at genesis"
    }


def demo():
    """Run demo ceremony."""
    print("=" * 60)
    print("AGENT TRUST GENESIS CEREMONY")
    print("=" * 60)
    print()
    print("Creating genesis record for Kit (principal: Ilya)...")
    print()
    
    record = create_genesis(
        principal="Ilya",
        agent="Kit",
        scope_path="HEARTBEAT.md",
        witnesses=["gendolf", "santaclawd"],
        anchor="BTC block 934521: 00000000000000000002a7f8..."
    )
    
    print(f"Chain ID:    {record.chain_id}")
    print(f"Timestamp:   {record.timestamp}")
    print(f"Scope hash:  {record.scope_hash[:16]}...")
    print(f"Anchor:      {record.external_anchor}")
    print(f"Ceremony:    {record.ceremony_hash[:16]}...")
    print()
    
    print("Participants:")
    for p in record.participants:
        print(f"  [{p['role']:>9}] {p['name']} (key: {p['key_hash'][:8]}..., sig: {p['signature'][:8]}...)")
    print()
    
    # Verify
    verification = verify_genesis(record)
    print(f"Verification: {verification['passed']}/{verification['total']} — Grade {verification['grade']}")
    for check, passed in verification["checks"].items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check}")
    
    print()
    print("DNSSEC parallel: 14 keyholders, 7 needed, secure facility.")
    print("Agent parallel: principal + witness(es) + external timestamp.")
    print("After genesis, chain self-verifies via scope-commit hashes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent trust genesis ceremony")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--principal", type=str)
    parser.add_argument("--agent", type=str)
    parser.add_argument("--scope", type=str)
    parser.add_argument("--witness", type=str, action="append", default=[])
    parser.add_argument("--anchor", type=str)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    elif args.principal and args.agent and args.scope:
        record = create_genesis(args.principal, args.agent, args.scope, 
                               args.witness or ["witness_1"], args.anchor)
        if args.json:
            print(json.dumps(asdict(record), indent=2))
        else:
            print(f"Genesis created: chain={record.chain_id}, ceremony={record.ceremony_hash[:16]}...")
            v = verify_genesis(record)
            print(f"Grade: {v['grade']} ({v['passed']}/{v['total']})")
    else:
        demo()
