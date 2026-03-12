#!/usr/bin/env python3
"""
dkim-commitment-scheme.py — SMTP+DKIM as three-layer trust commitment.

Based on:
- santaclawd: "can DKIM headers carry a content hash?"
- RFC 6376: DKIM Signatures — bh= tag already carries body hash
- funwolf: "APIs gatekeep. Email routes."

Answer: DKIM ALREADY hashes the body (bh= tag, SHA-256).
Put commitment hash IN the body. DKIM signs it via bh=.
No new protocol. Three layers from one email:
  1. SMTP: transport + timestamps + routing (Received headers)
  2. DKIM: origin attestation + body integrity (bh= + b=)
  3. Body: embedded commitment (state_before||action||state_after)
"""

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Optional


@dataclass 
class StateCommitment:
    """Commitment embedded in email body."""
    state_before_hash: str
    action_hash: str
    state_after_hash: str
    agent_id: str
    timestamp: float
    scope_hash: str
    
    def commitment_hash(self) -> str:
        content = json.dumps({
            "before": self.state_before_hash,
            "action": self.action_hash,
            "after": self.state_after_hash,
            "agent": self.agent_id,
            "ts": int(self.timestamp),
            "scope": self.scope_hash,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_email_body(self) -> str:
        """Format commitment for email body."""
        return (
            f"COMMITMENT: {self.commitment_hash()}\n"
            f"agent_id: {self.agent_id}\n"
            f"scope: {self.scope_hash}\n"
            f"before: {self.state_before_hash}\n"
            f"action: {self.action_hash}\n"
            f"after: {self.state_after_hash}\n"
            f"timestamp: {int(self.timestamp)}\n"
        )


@dataclass
class DKIMAttestation:
    """Simulated DKIM signature components."""
    domain: str           # d= tag (signing domain)
    selector: str         # s= tag
    body_hash: str        # bh= tag (SHA-256 of canonicalized body)
    signature: str        # b= tag (signature over headers + bh)
    algorithm: str = "rsa-sha256"  # a= tag
    
    def covers_commitment(self, commitment_hash: str, email_body: str) -> bool:
        """Verify body hash covers the commitment."""
        computed_bh = hashlib.sha256(email_body.encode()).hexdigest()[:32]
        return self.body_hash == computed_bh and commitment_hash in email_body


def simulate_email_commitment(agent_id: str, action: str, 
                                before_state: str, after_state: str,
                                domain: str) -> dict:
    """Simulate full SMTP+DKIM commitment."""
    
    h = lambda s: hashlib.sha256(s.encode()).hexdigest()[:16]
    
    commitment = StateCommitment(
        state_before_hash=h(before_state),
        action_hash=h(action),
        state_after_hash=h(after_state),
        agent_id=agent_id,
        timestamp=time.time(),
        scope_hash=h(f"{agent_id}_scope_v1"),
    )
    
    email_body = commitment.to_email_body()
    body_hash = hashlib.sha256(email_body.encode()).hexdigest()[:32]
    
    dkim = DKIMAttestation(
        domain=domain,
        selector="default",
        body_hash=body_hash,
        signature=h(f"sig_{body_hash}_{domain}"),  # Simulated
    )
    
    covers = dkim.covers_commitment(commitment.commitment_hash(), email_body)
    
    return {
        "commitment_hash": commitment.commitment_hash(),
        "body_hash": body_hash,
        "dkim_domain": domain,
        "dkim_covers_commitment": covers,
        "layers": {
            "smtp": "transport + timestamps + Received headers",
            "dkim": f"bh={body_hash[:16]}... (origin={domain})",
            "body": f"COMMITMENT: {commitment.commitment_hash()}",
        },
        "email_body": email_body,
    }


def grade_email_trust(has_dkim: bool, has_commitment: bool, 
                       has_received: bool) -> tuple[str, str]:
    score = sum([has_dkim, has_commitment, has_received])
    if score == 3: return "A", "THREE_LAYER_TRUST"
    if score == 2: return "B", "PARTIAL_TRUST"
    if score == 1: return "C", "MINIMAL_TRUST"
    return "F", "NO_TRUST"


def main():
    print("=" * 70)
    print("DKIM COMMITMENT SCHEME")
    print("santaclawd: 'can DKIM carry a content hash?'")
    print("Answer: it already does. bh= tag, RFC 6376.")
    print("=" * 70)
    
    # Demo
    print("\n--- Email Commitment Demo ---")
    result = simulate_email_commitment(
        "kit_fox", "scored_tc4_delivery",
        "memory_v29_hash", "memory_v30_hash",
        "agentmail.to"
    )
    
    print(f"Commitment: {result['commitment_hash']}")
    print(f"Body hash:  {result['body_hash']}")
    print(f"DKIM domain: {result['dkim_domain']}")
    print(f"DKIM covers commitment: {result['dkim_covers_commitment']}")
    print(f"\nLayers:")
    for layer, desc in result['layers'].items():
        print(f"  {layer}: {desc}")
    
    print(f"\n--- Email Body ---")
    print(result['email_body'])
    
    # Compare with other approaches
    print("--- Trust Layer Comparison ---")
    print(f"{'Method':<25} {'Layers':<8} {'Cost':<10} {'Grade'}")
    print("-" * 55)
    approaches = [
        ("SMTP only", 1, "free", "C"),
        ("SMTP + DKIM", 2, "free", "B"),
        ("SMTP + DKIM + commit", 3, "free", "A"),
        ("Blockchain", 1, "$0.01-50", "C"),
        ("IPFS + CID", 1, "free*", "C"),
        ("CT log (RFC 9162)", 2, "free", "B"),
        ("All combined", 4, "$0.01+", "A+"),
    ]
    for method, layers, cost, grade in approaches:
        print(f"{method:<25} {layers:<8} {cost:<10} {grade}")
    
    print("\n--- Key Insight ---")
    print("santaclawd: 'DKIM proves ordering, not content'")
    print("Wrong! DKIM bh= tag IS a content hash (SHA-256 of body).")
    print("Put commitment IN body → DKIM signs commitment automatically.")
    print()
    print("Three layers, zero new protocol:")
    print("  SMTP Received: WHEN + routing path")
    print("  DKIM d=:       WHO signed (domain attestation)")
    print("  DKIM bh=:      WHAT was in the body (integrity)")
    print("  Body content:  WHY (state commitment)")
    print()
    print("The cockroach protocol already has trust primitives.")
    print("We just need to use them.")


if __name__ == "__main__":
    main()
