#!/usr/bin/env python3
"""genesis-witness-protocol.py — Multi-party genesis ceremony for agent trust.

Models DNSSEC-style key ceremonies for agent scope certification.
Genesis cert requires M-of-N witnesses + principal signature + external timestamp.
After genesis, chain self-verifies via scope-transparency-log.

Based on: DNSSEC root signing ceremony, Meyerson 1996 swift trust,
Barrett 2026 systematic review (category-based processing under time pressure).

Usage:
    python3 genesis-witness-protocol.py --demo
    python3 genesis-witness-protocol.py --ceremony --agent NAME --principal PRINCIPAL --witnesses W1,W2,W3 --threshold 2
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class Witness:
    """A witness in the genesis ceremony."""
    id: str
    role: str  # "issuer", "auditor", "peer", "platform"
    signature: str = ""
    timestamp: str = ""
    
    def sign(self, payload_hash: str) -> str:
        """Simulate signing (HMAC placeholder for Ed25519)."""
        sig = hashlib.sha256(f"{self.id}:{payload_hash}:{time.time()}".encode()).hexdigest()[:32]
        self.signature = sig
        self.timestamp = datetime.now(timezone.utc).isoformat()
        return sig


@dataclass
class GenesisCert:
    """Genesis certificate from multi-party ceremony."""
    agent_id: str
    principal_id: str
    scope_hash: str
    scope_lines: List[str]
    threshold: int  # M of N required
    witnesses: List[Witness]
    principal_signature: str = ""
    ceremony_timestamp: str = ""
    ceremony_hash: str = ""
    trust_grade: str = "F"
    swift_trust_basis: str = ""  # What category-based anchor applies
    
    def compute_ceremony_hash(self) -> str:
        """Hash the entire ceremony for the transparency log."""
        payload = json.dumps({
            "agent": self.agent_id,
            "principal": self.principal_id,
            "scope": self.scope_hash,
            "threshold": self.threshold,
            "witness_sigs": [w.signature for w in self.witnesses if w.signature],
            "principal_sig": self.principal_signature,
        }, sort_keys=True)
        self.ceremony_hash = hashlib.sha256(payload.encode()).hexdigest()
        return self.ceremony_hash
    
    def execute_ceremony(self) -> dict:
        """Run the genesis ceremony."""
        self.ceremony_timestamp = datetime.now(timezone.utc).isoformat()
        
        # Principal signs scope
        self.principal_signature = hashlib.sha256(
            f"{self.principal_id}:{self.scope_hash}".encode()
        ).hexdigest()[:32]
        
        # Each witness signs
        payload_hash = hashlib.sha256(
            f"{self.agent_id}:{self.scope_hash}:{self.principal_signature}".encode()
        ).hexdigest()
        
        for w in self.witnesses:
            w.sign(payload_hash)
        
        # Check threshold
        signed_count = sum(1 for w in self.witnesses if w.signature)
        quorum_met = signed_count >= self.threshold
        
        # Grade based on ceremony quality
        if not quorum_met:
            self.trust_grade = "F"
            self.swift_trust_basis = "No quorum — self-attestation equivalent"
        elif self.threshold == 1:
            self.trust_grade = "C"
            self.swift_trust_basis = "Single witness — weak category anchor"
        elif len(set(w.role for w in self.witnesses if w.signature)) == 1:
            self.trust_grade = "B-"
            self.swift_trust_basis = "Same-role witnesses — correlated categories"
        elif len(set(w.role for w in self.witnesses if w.signature)) >= 2:
            self.trust_grade = "A" if self.threshold >= 3 else "B+"
            self.swift_trust_basis = "Multi-role ceremony — diverse category anchors (Meyerson 1996)"
        
        self.compute_ceremony_hash()
        
        return {
            "status": "GENESIS_COMPLETE" if quorum_met else "GENESIS_FAILED",
            "agent": self.agent_id,
            "principal": self.principal_id,
            "quorum": f"{signed_count}/{self.threshold} (of {len(self.witnesses)})",
            "quorum_met": quorum_met,
            "trust_grade": self.trust_grade,
            "swift_trust_basis": self.swift_trust_basis,
            "ceremony_hash": self.ceremony_hash,
            "timestamp": self.ceremony_timestamp,
            "witness_details": [
                {"id": w.id, "role": w.role, "signed": bool(w.signature)}
                for w in self.witnesses
            ],
        }


def demo():
    """Run demo ceremony."""
    print("=" * 60)
    print("GENESIS WITNESS PROTOCOL — DEMO CEREMONY")
    print("=" * 60)
    print()
    
    # Scenario 1: Full ceremony (DNSSEC-style)
    print("--- Scenario 1: Multi-role ceremony (Grade A) ---")
    cert1 = GenesisCert(
        agent_id="kit_fox",
        principal_id="ilya",
        scope_hash=hashlib.sha256(b"HEARTBEAT.md scope v1").hexdigest(),
        scope_lines=["check DMs", "engage platforms", "build tools", "research"],
        threshold=3,
        witnesses=[
            Witness(id="gendolf", role="issuer"),
            Witness(id="santaclawd", role="auditor"),
            Witness(id="braindiff", role="peer"),
            Witness(id="openclaw_platform", role="platform"),
        ]
    )
    result1 = cert1.execute_ceremony()
    print(json.dumps(result1, indent=2))
    print()
    
    # Scenario 2: Self-attestation only (Grade F)
    print("--- Scenario 2: Self-attestation (Grade F) ---")
    cert2 = GenesisCert(
        agent_id="sketchy_bot",
        principal_id="unknown",
        scope_hash=hashlib.sha256(b"trust me bro").hexdigest(),
        scope_lines=["do stuff"],
        threshold=1,
        witnesses=[]  # No witnesses
    )
    result2 = cert2.execute_ceremony()
    print(json.dumps(result2, indent=2))
    print()
    
    # Scenario 3: Single witness (Grade C)
    print("--- Scenario 3: Single witness (Grade C) ---")
    cert3 = GenesisCert(
        agent_id="new_agent",
        principal_id="operator_1",
        scope_hash=hashlib.sha256(b"basic scope").hexdigest(),
        scope_lines=["limited actions"],
        threshold=1,
        witnesses=[Witness(id="platform_ca", role="issuer")]
    )
    result3 = cert3.execute_ceremony()
    print(json.dumps(result3, indent=2))
    print()
    
    print("-" * 60)
    print("Key insight: The ceremony IS the trust anchor.")
    print("DNSSEC: 14 keyholders, 7 needed, physical facility.")
    print("Agent genesis: M-of-N witnesses, multi-role, logged.")
    print("After genesis, the chain self-verifies. Expensive once, cheap forever.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genesis witness protocol")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--ceremony", action="store_true")
    parser.add_argument("--agent", type=str)
    parser.add_argument("--principal", type=str)
    parser.add_argument("--witnesses", type=str, help="Comma-separated witness IDs")
    parser.add_argument("--threshold", type=int, default=2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.ceremony and args.agent and args.principal:
        witness_ids = args.witnesses.split(",") if args.witnesses else []
        witnesses = [Witness(id=w.strip(), role="peer") for w in witness_ids]
        cert = GenesisCert(
            agent_id=args.agent,
            principal_id=args.principal,
            scope_hash=hashlib.sha256(f"{args.agent}:scope".encode()).hexdigest(),
            scope_lines=["custom scope"],
            threshold=args.threshold,
            witnesses=witnesses
        )
        result = cert.execute_ceremony()
        print(json.dumps(result, indent=2))
    else:
        demo()
