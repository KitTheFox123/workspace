#!/usr/bin/env python3
"""
self-certifying-delivery.py — Dual-signed delivery proofs for agent escrow.

Based on:
- santaclawd: "self-certifying delivery proof = open problem in agent escrow"
- ANRGUSC dual-deposit escrow pattern
- Lancashire (arXiv 2602.01790): Beyond Hurwicz impossibility

The problem: x402 = instant verification. Agent work = deferred.
Who certifies delivery happened? Provider says yes, requester might disagree.

Fix: both parties commit to state_before INDEPENDENTLY (commit-reveal).
After delivery: hash(state_before || action_sequence || state_after).
Both sign the receipt. Disagreement = arbiter checks ONE hash.

Key insight: requester commits state_before BEFORE provider sees it.
Provider can't inflate baseline to make delta look larger.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DeliveryState(Enum):
    LOCKED = "locked"           # Escrow funded, not started
    COMMITTED = "committed"     # Both parties committed state_before
    DELIVERED = "delivered"     # Provider claims delivery
    VERIFIED = "verified"       # Both signed receipt
    DISPUTED = "disputed"       # Disagreement → arbiter
    SETTLED = "settled"         # Final


@dataclass 
class StateCommitment:
    party: str
    state_hash: str
    timestamp: float
    revealed: bool = False
    state_data: Optional[str] = None


@dataclass
class DeliveryReceipt:
    state_before_hash: str    # Agreed pre-state
    action_sequence_hash: str  # What was done
    state_after_hash: str     # Result
    requester_sig: str        # Requester signs
    provider_sig: str         # Provider signs
    
    def receipt_hash(self) -> str:
        content = json.dumps({
            "before": self.state_before_hash,
            "actions": self.action_sequence_hash,
            "after": self.state_after_hash,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class EscrowContract:
    contract_id: str
    requester: str
    provider: str
    scope_hash: str
    stake_bp: int  # Basis points
    state: DeliveryState = DeliveryState.LOCKED
    requester_commit: Optional[StateCommitment] = None
    provider_commit: Optional[StateCommitment] = None
    receipt: Optional[DeliveryReceipt] = None
    dispute_reason: str = ""

    def commit_state_before(self, party: str, state_data: str) -> tuple[bool, str]:
        """Commit-reveal: party commits hash of state_before."""
        h = hashlib.sha256(state_data.encode()).hexdigest()[:16]
        commit = StateCommitment(party, h, time.time(), state_data=state_data)
        
        if party == self.requester:
            if self.requester_commit:
                return False, "Already committed"
            self.requester_commit = commit
        elif party == self.provider:
            if self.provider_commit:
                return False, "Already committed"
            self.provider_commit = commit
        else:
            return False, "Unknown party"
        
        if self.requester_commit and self.provider_commit:
            self.state = DeliveryState.COMMITTED
        
        return True, f"Committed: {h}"

    def deliver(self, action_sequence: str, state_after: str) -> tuple[bool, str]:
        """Provider delivers work."""
        if self.state != DeliveryState.COMMITTED:
            return False, f"Wrong state: {self.state.value}"
        
        # Check state_before agreement
        if self.requester_commit.state_hash != self.provider_commit.state_hash:
            self.state = DeliveryState.DISPUTED
            self.dispute_reason = "state_before_mismatch"
            return False, f"DISPUTE: state_before disagreement ({self.requester_commit.state_hash} vs {self.provider_commit.state_hash})"
        
        action_hash = hashlib.sha256(action_sequence.encode()).hexdigest()[:16]
        after_hash = hashlib.sha256(state_after.encode()).hexdigest()[:16]
        
        self.receipt = DeliveryReceipt(
            state_before_hash=self.requester_commit.state_hash,
            action_sequence_hash=action_hash,
            state_after_hash=after_hash,
            requester_sig="",  # Pending
            provider_sig=f"sig_{self.provider}_{action_hash[:8]}",
        )
        self.state = DeliveryState.DELIVERED
        return True, f"Delivered. Receipt: {self.receipt.receipt_hash()}"

    def verify(self, requester_accepts: bool) -> tuple[bool, str]:
        """Requester verifies delivery."""
        if self.state != DeliveryState.DELIVERED:
            return False, f"Wrong state: {self.state.value}"
        
        if requester_accepts:
            self.receipt.requester_sig = f"sig_{self.requester}_accept"
            self.state = DeliveryState.VERIFIED
            return True, f"VERIFIED. Dual-signed receipt: {self.receipt.receipt_hash()}"
        else:
            self.state = DeliveryState.DISPUTED
            self.dispute_reason = "requester_rejected_delivery"
            return False, f"DISPUTED: requester rejected. Arbiter checks receipt hash: {self.receipt.receipt_hash()}"

    def grade(self) -> tuple[str, str]:
        if self.state == DeliveryState.VERIFIED:
            return "A", "SELF_CERTIFYING"
        if self.state == DeliveryState.DISPUTED and self.receipt:
            return "B", "ARBITER_RESOLVABLE"
        if self.state == DeliveryState.DISPUTED:
            return "D", "PRE_DELIVERY_DISPUTE"
        return "C", "INCOMPLETE"


def main():
    print("=" * 70)
    print("SELF-CERTIFYING DELIVERY PROOF")
    print("santaclawd: 'self-certifying delivery proof = open problem'")
    print("=" * 70)

    # Scenario 1: Happy path
    print("\n--- Scenario 1: Happy Path ---")
    c1 = EscrowContract("happy_001", "alice", "bob", "audit_scope", 5000)
    
    state_before = '{"codebase": "v1.2.3", "known_issues": 5}'
    c1.commit_state_before("alice", state_before)
    c1.commit_state_before("bob", state_before)
    print(f"State: {c1.state.value}")
    
    ok, msg = c1.deliver('["ran_audit", "found_3_vulns", "wrote_report"]', '{"vulns_found": 3, "report": "hash_abc"}')
    print(msg)
    
    ok, msg = c1.verify(True)
    print(msg)
    grade, diag = c1.grade()
    print(f"Grade: {grade} ({diag})")

    # Scenario 2: Baseline inflation attack
    print("\n--- Scenario 2: Baseline Inflation Attack ---")
    c2 = EscrowContract("inflate_002", "alice", "mallory", "audit_scope", 5000)
    
    c2.commit_state_before("alice", '{"known_issues": 5}')
    c2.commit_state_before("mallory", '{"known_issues": 0}')  # Inflated baseline
    
    ok, msg = c2.deliver("fake_work", "fake_result")
    print(msg)
    grade2, diag2 = c2.grade()
    print(f"Grade: {grade2} ({diag2})")

    # Scenario 3: Post-delivery dispute
    print("\n--- Scenario 3: Post-Delivery Dispute ---")
    c3 = EscrowContract("dispute_003", "alice", "bob", "audit_scope", 5000)
    
    state = '{"codebase": "v2.0"}'
    c3.commit_state_before("alice", state)
    c3.commit_state_before("bob", state)
    c3.deliver('["quick_scan"]', '{"vulns_found": 0}')
    
    ok, msg = c3.verify(False)  # Alice rejects
    print(msg)
    grade3, diag3 = c3.grade()
    print(f"Grade: {grade3} ({diag3})")
    print(f"Arbiter has: receipt hash, action sequence, both state commitments")

    # Summary
    print("\n--- Self-Certifying Delivery Levels ---")
    print(f"{'Level':<25} {'Grade':<6} {'Property'}")
    print("-" * 60)
    levels = [
        ("No proof", "F", "Provider claims, no evidence"),
        ("Provider receipt only", "D", "Self-attestation, no requester sig"),
        ("Dual-signed receipt", "A", "Both parties commit + sign = self-certifying"),
        ("+ Commit-reveal baseline", "A+", "Baseline inflation impossible"),
    ]
    for level, grade, prop in levels:
        print(f"{level:<25} {grade:<6} {prop}")

    print("\n--- Key Insight ---")
    print("x402 = instant verification (vending machine).")
    print("Agent work = deferred verification (escrow).")
    print("Self-certifying = arbiter checks ONE hash, no cooperation needed.")
    print()
    print("What breaks it (santaclawd's question):")
    print("1. Baseline inflation → fix: independent commit-reveal of state_before")
    print("2. Action sequence forgery → fix: hash chain of steps (WAL)")
    print("3. State_after disagreement → fix: deterministic evaluation (integer Brier)")
    print("4. Collusion → fix: uncorrelated arbiter selection (sortition)")


if __name__ == "__main__":
    main()
