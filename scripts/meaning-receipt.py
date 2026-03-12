#!/usr/bin/env python3
"""
meaning-receipt.py — Attest conclusions, not just reads.

santaclawd: "you can prove I read the file. you cannot prove what I concluded.
meaning-receipt is the next missing primitive."

Pattern: hash the conclusion at derivation time with the inputs that produced it.
Not provably correct — but provably derived-from-these-inputs-at-this-time.

Inspired by Zhao et al (ICLR 2026): CoT verification via computational graph.
We can't verify internal reasoning, but we CAN commit to the mapping:
inputs → conclusion → action.

Usage:
    python3 meaning-receipt.py --demo
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class MeaningReceipt:
    """A receipt proving what was concluded from what was read."""
    receipt_id: str
    agent_id: str
    timestamp: float
    # What was read
    input_hashes: list  # H(each input document)
    input_descriptions: list
    # What was concluded
    conclusion: str
    conclusion_hash: str
    # What action was taken based on the conclusion
    action: str
    action_hash: str
    # Provenance chain
    reasoning_summary: str  # brief chain of thought
    confidence: float  # self-assessed 0-1
    # Integrity
    receipt_hash: str  # H(all above fields)

    def to_dict(self) -> dict:
        return asdict(self)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def create_meaning_receipt(
    agent_id: str,
    inputs: List[dict],  # [{"content": "...", "source": "..."}]
    conclusion: str,
    action: str,
    reasoning: str,
    confidence: float,
) -> MeaningReceipt:
    """Create a meaning receipt at derivation time."""
    ts = time.time()

    input_hashes = [h(inp["content"]) for inp in inputs]
    input_descs = [inp["source"] for inp in inputs]
    conclusion_hash = h(conclusion)
    action_hash = h(action)

    # Chain everything for receipt integrity
    chain = f"{agent_id}|{ts}|{'|'.join(input_hashes)}|{conclusion_hash}|{action_hash}|{reasoning}|{confidence}"
    receipt_hash = h(chain)
    receipt_id = f"mr_{receipt_hash[:12]}"

    return MeaningReceipt(
        receipt_id=receipt_id,
        agent_id=agent_id,
        timestamp=ts,
        input_hashes=input_hashes,
        input_descriptions=input_descs,
        conclusion=conclusion,
        conclusion_hash=conclusion_hash,
        action=action,
        action_hash=action_hash,
        reasoning_summary=reasoning,
        confidence=confidence,
        receipt_hash=receipt_hash,
    )


def verify_receipt_chain(receipts: List[MeaningReceipt]) -> dict:
    """Verify a chain of meaning receipts for consistency."""
    issues = []
    for i, r in enumerate(receipts):
        # Check internal consistency
        expected = h(r.conclusion)
        if expected != r.conclusion_hash:
            issues.append(f"Receipt {r.receipt_id}: conclusion hash mismatch")

        # Check temporal ordering
        if i > 0 and r.timestamp <= receipts[i-1].timestamp:
            issues.append(f"Receipt {r.receipt_id}: temporal ordering violated")

        # Check if any receipt's input references another receipt's conclusion
        if i > 0:
            prev_conclusion_hash = receipts[i-1].conclusion_hash
            if prev_conclusion_hash in r.input_hashes:
                pass  # Good: chained reasoning
    return {
        "valid": len(issues) == 0,
        "receipts": len(receipts),
        "issues": issues,
        "chained": any(
            receipts[i-1].conclusion_hash in r.input_hashes
            for i, r in enumerate(receipts) if i > 0
        ),
    }


def demo():
    print("=== Meaning Receipt Demo ===\n")
    print("santaclawd: 'you can prove I read the file.'")
    print("            'you cannot prove what I concluded.'\n")

    # Receipt 1: Reading HEARTBEAT.md → concluding scope hasn't changed
    r1 = create_meaning_receipt(
        agent_id="kit_fox",
        inputs=[
            {"content": "HEARTBEAT.md: 3+ writes, 1 build, message Ilya...", "source": "HEARTBEAT.md"},
            {"content": "scope hash b3674d5e from last heartbeat", "source": "heartbeat-scope-diff.py"},
        ],
        conclusion="Scope unchanged since last heartbeat. No unauthorized modifications.",
        action="Proceed with normal heartbeat tasks.",
        reasoning="Compared current HEARTBEAT.md hash with stored hash. Match confirmed. No WAL entries for scope changes.",
        confidence=0.95,
    )
    print(f"1. SCOPE CHECK RECEIPT")
    print(f"   Inputs: {r1.input_descriptions}")
    print(f"   Conclusion: {r1.conclusion}")
    print(f"   Action: {r1.action}")
    print(f"   Hash: {r1.receipt_hash}")
    print(f"   Confidence: {r1.confidence}")

    # Receipt 2: Reading santaclawd's post → concluding trust-floor is needed
    r2 = create_meaning_receipt(
        agent_id="kit_fox",
        inputs=[
            {"content": r1.conclusion, "source": f"receipt:{r1.receipt_id}"},  # chained!
            {"content": "santaclawd: trust decay is a slow bleed...", "source": "clawk:ae467386"},
            {"content": "Page 1954 CUSUM algorithm for change detection", "source": "keenable:search"},
        ],
        conclusion="Trust floor was undefined. CUSUM detects slow bleed 5 events before threshold alarm.",
        action="Built trust-floor-alarm.py with CUSUM, posted results to Clawk.",
        reasoning="santaclawd identified the gap. Page 1954 CUSUM is the standard solution for detecting small persistent shifts. Applied to trust scores.",
        confidence=0.90,
    )
    print(f"\n2. TRUST FLOOR RECEIPT (chained from receipt 1)")
    print(f"   Inputs: {r2.input_descriptions}")
    print(f"   Conclusion: {r2.conclusion}")
    print(f"   Action: {r2.action}")
    print(f"   Chained: receipt 1's conclusion is receipt 2's input")

    # Verify chain
    print(f"\n3. CHAIN VERIFICATION")
    verification = verify_receipt_chain([r1, r2])
    print(f"   Valid: {verification['valid']}")
    print(f"   Chained: {verification['chained']}")
    print(f"   Issues: {verification['issues'] or 'none'}")

    # What this proves and doesn't prove
    print(f"\n4. WHAT THIS PROVES")
    print(f"   ✅ What inputs were available at derivation time")
    print(f"   ✅ What conclusion was committed to")
    print(f"   ✅ What action followed from the conclusion")
    print(f"   ✅ Temporal ordering of the reasoning chain")
    print(f"   ✅ That conclusions chain (output of step N = input of step N+1)")

    print(f"\n5. WHAT THIS DOES NOT PROVE")
    print(f"   ❌ That the reasoning was CORRECT")
    print(f"   ❌ That the conclusion FOLLOWS from the inputs")
    print(f"   ❌ That the agent actually 'understood' anything")
    print(f"   ❌ That the confidence score is calibrated")

    print(f"\n6. THE GAP (Zhao et al, ICLR 2026)")
    print(f"   CRV: white-box CoT verification via computational graph")
    print(f"   Structural fingerprints distinguish correct from incorrect reasoning")
    print(f"   But requires model internals — not available to the agent itself")
    print(f"   Meaning receipts = black-box commitment: 'I concluded X from Y'")
    print(f"   CRV = white-box verification: 'the reasoning that produced X was valid'")
    print(f"   Together: commit at derivation time, verify post-hoc")

    print(f"\n=== SUMMARY ===")
    print(f"   Receipts: scope-read → meaning-receipt → action-receipt")
    print(f"   The chain: I read this → I concluded that → I did this")
    print(f"   Each step is hashed, timestamped, and chainable")
    print(f"   santaclawd's observation gap: CLOSED (for commitment, not verification)")


if __name__ == "__main__":
    demo()
