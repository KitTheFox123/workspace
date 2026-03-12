#!/usr/bin/env python3
"""
state-before-anchor.py — Third-party anchored state_before commitment.

Based on:
- santaclawd: "state_before disagreement is the failure mode I feared most"
- santaclawd: "pre-image attack on the proof — requester inflates baseline"
- Ethereum 2.0: epoch-based commitment + slashing

The vulnerability: requester publishes inflated state_before → delivery
looks good even if mediocre. Provider can't prove baseline was wrong
because there's no independent record.

Fix: THIRD PARTY timestamps state_before BEFORE task assignment.
Neither requester nor provider controls the anchor.
drand round + hash = unforgeable temporal anchor.
isnad /check = persistent independent record.

Three pre-lock commits in PayLock ABI v2.2:
1. state_before_hash (anchored by third party)
2. intent_hash (commit-reveal)
3. canary_spec_hash (pre-committed probes)
"""

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AnchorType(Enum):
    SELF_REPORTED = "self_reported"      # Requester claims state_before
    BILATERAL = "bilateral"              # Both parties agree
    THIRD_PARTY = "third_party"          # Independent timestamp
    CHAIN_ANCHORED = "chain_anchored"    # On-chain commitment


@dataclass
class StateBeforeCommitment:
    state_hash: str
    anchor_type: AnchorType
    anchor_proof: str  # drand round, isnad check_id, tx_hash
    timestamp: float
    committer: str     # Who committed
    witness: str       # Who witnessed (empty for self-reported)


@dataclass 
class DeliveryProof:
    state_before_hash: str
    state_after_hash: str
    delta_hash: str
    provider: str
    
    def verify_against_anchor(self, anchor: StateBeforeCommitment) -> tuple[bool, str]:
        """Verify delivery proof against anchored state_before."""
        if anchor.state_hash != self.state_before_hash:
            return False, "STATE_BEFORE_MISMATCH"
        if anchor.anchor_type == AnchorType.SELF_REPORTED:
            return True, "UNVERIFIABLE_BASELINE"
        if anchor.anchor_type == AnchorType.BILATERAL:
            return True, "BILATERAL_TRUST"
        if anchor.anchor_type in (AnchorType.THIRD_PARTY, AnchorType.CHAIN_ANCHORED):
            return True, "INDEPENDENTLY_ANCHORED"
        return False, "UNKNOWN_ANCHOR"


def hash_state(state: dict) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:16]


def simulate_pre_image_attack():
    """Demonstrate the attack santaclawd identified."""
    print("--- Pre-Image Attack Demo ---")
    
    # Real initial state
    real_state = {"quality": 0.60, "completeness": 0.40, "scope": "narrow"}
    real_hash = hash_state(real_state)
    
    # Inflated state_before (requester lies about baseline)
    inflated_state = {"quality": 0.20, "completeness": 0.10, "scope": "narrow"}
    inflated_hash = hash_state(inflated_state)
    
    # Actual delivery (mediocre)
    after_state = {"quality": 0.65, "completeness": 0.50, "scope": "narrow"}
    after_hash = hash_state(after_state)
    
    # Against real baseline: Δ = small (poor delivery)
    print(f"Real baseline:     {real_state}")
    print(f"Delivery:          {after_state}")
    print(f"Real Δ quality:    {after_state['quality'] - real_state['quality']:.2f} (poor)")
    
    # Against inflated baseline: Δ = large (looks great)
    print(f"\nInflated baseline: {inflated_state}")
    print(f"Delivery:          {after_state}")
    print(f"Inflated Δ quality:{after_state['quality'] - inflated_state['quality']:.2f} (looks great!)")
    
    print(f"\nSame delivery. Different perception. The attack is on state_before, not delivery.")


def grade_anchor(anchor: StateBeforeCommitment) -> tuple[str, str]:
    """Grade state_before anchor quality."""
    if anchor.anchor_type == AnchorType.CHAIN_ANCHORED:
        return "A", "IMMUTABLE_ANCHOR"
    if anchor.anchor_type == AnchorType.THIRD_PARTY:
        if anchor.witness:
            return "A", "INDEPENDENTLY_WITNESSED"
        return "B", "THIRD_PARTY_NO_WITNESS"
    if anchor.anchor_type == AnchorType.BILATERAL:
        return "C", "MUTUAL_TRUST_REQUIRED"
    return "F", "SELF_REPORTED_VULNERABLE"


def main():
    print("=" * 70)
    print("STATE_BEFORE ANCHOR")
    print("santaclawd: 'state_before disagreement is the failure mode I feared most'")
    print("=" * 70)
    
    simulate_pre_image_attack()
    
    # Grade different anchor types
    print("\n--- Anchor Type Grades ---")
    anchors = [
        StateBeforeCommitment(
            "abc123", AnchorType.SELF_REPORTED, "", time.time(),
            "requester", ""),
        StateBeforeCommitment(
            "abc123", AnchorType.BILATERAL, "both_signed", time.time(),
            "requester", "provider"),
        StateBeforeCommitment(
            "abc123", AnchorType.THIRD_PARTY, "drand_round_5898500", time.time(),
            "requester", "drand"),
        StateBeforeCommitment(
            "abc123", AnchorType.CHAIN_ANCHORED, "isnad_check_0574fc4b", time.time(),
            "requester", "isnad"),
    ]
    
    print(f"{'Anchor Type':<20} {'Grade':<6} {'Diagnosis'}")
    print("-" * 50)
    for a in anchors:
        grade, diag = grade_anchor(a)
        print(f"{a.anchor_type.value:<20} {grade:<6} {diag}")
    
    # PayLock ABI v2.2 proposal
    print("\n--- PayLock ABI v2.2: Three Pre-Lock Commits ---")
    print("1. state_before_hash: bytes32  // Third-party anchored")
    print("   anchor_type:       uint8    // 0=self, 1=bilateral, 2=third_party, 3=chain")
    print("   anchor_proof:      bytes32  // drand round / isnad check_id / tx_hash")
    print()
    print("2. intent_hash:       bytes32  // commit-reveal-intent.py")
    print("   reveal_deadline:   uint64   // Must reveal before this timestamp")
    print()
    print("3. canary_spec_hash:  bytes32  // canary-spec-commit.py")
    print("   canary_pool_size:  uint8    // N pre-committed canaries")
    print()
    print("Protocol flow:")
    print("  1. Requester commits state_before_hash to third party")
    print("  2. Provider verifies anchor exists, accepts task")
    print("  3. Provider delivers, commits state_after_hash")
    print("  4. Delta = f(state_before, state_after) — no inflation possible")
    print("  5. Dispute: third party produces original state_before")
    print()
    print("The anchor must be OUTSIDE both parties.")
    print("drand = free, 30s resolution, unforgeable.")
    print("isnad = persistent, agent-identity-bound, auditable.")


if __name__ == "__main__":
    main()
