#!/usr/bin/env python3
"""
e2e-attestation-demo.py — End-to-end 3-class attestation scoring demo.

Simulates a full tc3-style delivery with real proof generation:
1. Payment class: x402 tx hash
2. Generation class: content hash (SHA-256 of deliverable)  
3. Transport class: DKIM-like signature over claim hash

Then feeds all three into proof-class-scorer for grading.
This is what v0.3 looks like in practice.
"""

import hashlib
import json
import time
import sys
from datetime import datetime, timezone

# Import the scorer
import importlib.util
spec = importlib.util.spec_from_file_location("scorer", "scripts/proof-class-scorer.py")
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def simulate_payment(amount: float, payer: str, payee: str) -> dict:
    """Simulate x402 payment receipt."""
    tx_hash = sha256(f"x402:{payer}:{payee}:{amount}:{time.time()}")
    return {
        "proof_type": "x402_tx",
        "issuer": payer,
        "claim_hash": tx_hash[:16],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evidence_hash": tx_hash,
        "signature": sha256(f"sig:{tx_hash}")[:32],
        "meta": {"amount": amount, "currency": "SOL", "payer": payer, "payee": payee}
    }


def simulate_generation(content: str, author: str) -> dict:
    """Simulate generation signature (content hash + author binding)."""
    content_hash = sha256(content)
    binding = sha256(f"gen:{author}:{content_hash}")
    return {
        "proof_type": "gen_sig",
        "issuer": author,
        "claim_hash": content_hash[:16],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evidence_hash": content_hash,
        "signature": binding[:32],
        "meta": {"content_length": len(content), "author": author}
    }


def simulate_transport(claim_hash: str, sender: str, recipient: str) -> dict:
    """Simulate DKIM transport attestation (X-Claim-Hash in signed headers)."""
    dkim_sig = sha256(f"dkim:{sender}:{recipient}:{claim_hash}")
    return {
        "proof_type": "dkim",
        "issuer": f"{sender}@agentmail.to",
        "claim_hash": claim_hash[:16],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evidence_hash": sha256(f"transport:{claim_hash}"),
        "signature": dkim_sig[:32],
        "meta": {"from": sender, "to": recipient, "x_claim_hash": claim_hash[:16]}
    }


def run_demo():
    print("=== End-to-End 3-Class Attestation Demo ===")
    print("Simulating tc3-style delivery with v0.3 spec\n")
    
    # 1. Deliverable content
    deliverable = "What Does the Agent Economy Need at Scale? The agent economy needs plumbing not intelligence..."
    print(f"📄 Deliverable: {len(deliverable)} chars")
    
    # 2. Generate 3-class proofs
    print("\n--- Generating Proofs ---")
    
    payment = simulate_payment(0.01, "gendolf", "kit_fox")
    print(f"💰 Payment: x402 tx {payment['evidence_hash'][:12]}... (0.01 SOL)")
    
    generation = simulate_generation(deliverable, "kit_fox")
    print(f"✍️  Generation: content hash {generation['evidence_hash'][:12]}...")
    
    transport = simulate_transport(generation['evidence_hash'], "kit_fox", "bro-agent")
    print(f"📨 Transport: DKIM sig {transport['signature'][:12]}...")
    
    # 3. Score the bundle
    print("\n--- Scoring ---")
    proofs = [payment, generation, transport]
    result = scorer.classify_proofs(proofs)
    
    print(f"Score: {result['score']} ({result['tier']})")
    print(f"Classes: {result['classes']}")
    print(f"Entropy: {result['entropy']}")
    if result['warnings']:
        for w in result['warnings']:
            print(f"⚠️  {w}")
    else:
        print("✅ No warnings — all 3 core classes covered")
    
    # 4. Compare with degraded bundles
    print("\n--- Degradation Analysis ---")
    
    # Remove payment
    no_payment = scorer.classify_proofs([generation, transport])
    print(f"Without payment: {no_payment['score']} ({no_payment['tier']}) — missing: {', '.join(no_payment.get('warnings', []))}")
    
    # Only generation
    gen_only = scorer.classify_proofs([generation])
    print(f"Generation only: {gen_only['score']} ({gen_only['tier']})")
    
    # 5. Full receipt
    print("\n--- Full Receipt ---")
    receipt = {
        "version": "0.3",
        "contract_id": "tc3",
        "proofs": proofs,
        "score": result['score'],
        "tier": result['tier'],
        "scored_at": result['scored_at'],
    }
    print(json.dumps(receipt, indent=2)[:1000])
    print("...")


if __name__ == "__main__":
    run_demo()
