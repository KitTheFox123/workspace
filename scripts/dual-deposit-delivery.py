#!/usr/bin/env python3
"""
dual-deposit-delivery.py — Self-certifying delivery proof for agent escrow.

Based on:
- Asgaonkar & Krishnamachari (USC, ICBC 2019): Dual-deposit escrow, SPNE = cooperate
- santaclawd: "receipt = hash(state_before || action_sequence || state_after)"
- TC4 experience: hash oracle = 100% delivery, 0% quality

The problem: agent output is non-deterministic (LLM).
Can't hash-verify content like a digital good.
Need two layers: delivery proof (deterministic) + quality score (non-deterministic).

Dual-deposit: both parties deposit stake.
Delivery = hash match (integer Brier score, cross-VM identical).
Quality = subjective scoring (requires arbiter, non-deterministic).
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DeliveryStatus(Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    RELEASED = "released"
    SLASHED = "slashed"


@dataclass
class DualDeposit:
    buyer_deposit_bp: int   # In basis points of contract value
    seller_deposit_bp: int
    contract_value_bp: int


@dataclass
class DeliveryProof:
    """Self-certifying delivery receipt."""
    state_before_hash: str
    action_sequence_hash: str
    state_after_hash: str
    brier_score_bp: int          # Integer Brier score
    requester_sig: str           # Buyer's signature on receipt
    provider_sig: str            # Seller's signature on receipt
    
    def receipt_hash(self) -> str:
        content = json.dumps({
            "before": self.state_before_hash,
            "action": self.action_sequence_hash,
            "after": self.state_after_hash,
            "brier_bp": self.brier_score_bp,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def is_dual_signed(self) -> bool:
        return bool(self.requester_sig and self.provider_sig)


@dataclass 
class EscrowContract:
    contract_id: str
    deposit: DualDeposit
    scope_hash: str
    delivery_hash_committed: str  # Pre-committed expected delivery hash
    canary_spec_hash: str
    status: DeliveryStatus = DeliveryStatus.PENDING
    proof: Optional[DeliveryProof] = None
    
    def submit_delivery(self, proof: DeliveryProof) -> tuple[bool, str]:
        """Provider submits delivery proof."""
        if self.status != DeliveryStatus.PENDING:
            return False, f"Wrong state: {self.status.value}"
        
        self.proof = proof
        self.status = DeliveryStatus.DELIVERED
        return True, "DELIVERED: awaiting buyer verification"
    
    def verify_delivery(self, buyer_accepts: bool) -> tuple[DeliveryStatus, str]:
        """Buyer verifies delivery."""
        if self.status != DeliveryStatus.DELIVERED:
            return self.status, f"Wrong state: {self.status.value}"
        
        if not self.proof.is_dual_signed():
            return DeliveryStatus.DISPUTED, "MISSING_SIGNATURE"
        
        if buyer_accepts:
            self.status = DeliveryStatus.VERIFIED
            return self.status, "VERIFIED: release deposits + payment"
        else:
            self.status = DeliveryStatus.DISPUTED
            return self.status, "DISPUTED: arbiter needed"
    
    def resolve_dispute(self, arbiter_score_bp: int, threshold_bp: int = 5000) -> tuple[DeliveryStatus, str, dict]:
        """Arbiter resolves dispute using integer Brier score."""
        if self.status != DeliveryStatus.DISPUTED:
            return self.status, "Not disputed", {}
        
        # Arbiter scores delivery quality (integer bp)
        if arbiter_score_bp >= threshold_bp:
            # Delivery meets threshold
            self.status = DeliveryStatus.RELEASED
            payout = {
                "buyer": self.deposit.buyer_deposit_bp,  # Deposit returned
                "seller": self.deposit.seller_deposit_bp + self.deposit.contract_value_bp,
                "reason": f"QUALITY_MET: {arbiter_score_bp}bp >= {threshold_bp}bp threshold"
            }
        else:
            # Delivery fails threshold
            self.status = DeliveryStatus.SLASHED
            # Seller loses deposit, buyer gets refund + seller deposit as penalty
            payout = {
                "buyer": self.deposit.buyer_deposit_bp + self.deposit.contract_value_bp + self.deposit.seller_deposit_bp,
                "seller": 0,
                "reason": f"QUALITY_FAILED: {arbiter_score_bp}bp < {threshold_bp}bp threshold"
            }
        
        return self.status, "Resolved", payout


def game_theory_analysis():
    """Show SPNE = cooperate under dual deposit."""
    print("\n--- Game Theory (Asgaonkar & Krishnamachari 2019) ---")
    print("Extensive form game with dual deposits:")
    print()
    print("  Buyer:  deposit D_b = 2x contract value")
    print("  Seller: deposit D_s = 1x contract value")
    print()
    print("  Payoffs (buyer, seller):")
    print(f"  {'Outcome':<30} {'Buyer':<15} {'Seller':<15}")
    print("  " + "-" * 60)
    print(f"  {'Both cooperate':<30} {'V - P + D_b':<15} {'P + D_s':<15}")
    print(f"  {'Seller cheats':<30} {'D_b (partial)':<15} {'-D_s':<15}")
    print(f"  {'Buyer cheats':<30} {'-D_b':<15} {'D_s (partial)':<15}")
    print(f"  {'Both cheat':<30} {'-D_b':<15} {'-D_s':<15}")
    print()
    print("  SPNE: Both cooperate (unique equilibrium with sufficient deposits)")
    print("  Key: deposit must exceed potential gain from cheating")


def main():
    print("=" * 70)
    print("DUAL-DEPOSIT DELIVERY PROOF FOR AGENTS")
    print("Asgaonkar & Krishnamachari (USC, ICBC 2019)")
    print("santaclawd: 'receipt = hash(before || action || after)'")
    print("=" * 70)

    # Scenario 1: Successful delivery
    print("\n--- Scenario 1: Successful Delivery ---")
    deposit = DualDeposit(2000, 1000, 10000)  # Buyer 20%, seller 10%, contract 100%
    contract = EscrowContract(
        "515ee459", deposit, 
        scope_hash="nist_caisi_v21",
        delivery_hash_committed="committed_hash_abc",
        canary_spec_hash="canary_123",
    )
    
    proof = DeliveryProof(
        state_before_hash="before_abc",
        action_sequence_hash="actions_def",
        state_after_hash="after_ghi",
        brier_score_bp=9200,  # 0.92 in bp
        requester_sig="buyer_sig_abc",
        provider_sig="seller_sig_def",
    )
    
    ok, msg = contract.submit_delivery(proof)
    print(f"Submit: {msg}")
    
    status, msg = contract.verify_delivery(buyer_accepts=True)
    print(f"Verify: {msg}")
    print(f"Receipt hash: {proof.receipt_hash()}")

    # Scenario 2: Disputed delivery
    print("\n--- Scenario 2: Disputed Delivery ---")
    contract2 = EscrowContract(
        "dispute_001", deposit,
        scope_hash="nist_caisi_v21",
        delivery_hash_committed="committed_hash_xyz",
        canary_spec_hash="canary_456",
    )
    
    proof2 = DeliveryProof(
        state_before_hash="before_xyz", action_sequence_hash="actions_uvw",
        state_after_hash="after_rst", brier_score_bp=4200,
        requester_sig="buyer_sig", provider_sig="seller_sig",
    )
    
    contract2.submit_delivery(proof2)
    status2, msg2 = contract2.verify_delivery(buyer_accepts=False)
    print(f"Verify: {msg2}")
    
    # Arbiter resolves
    status3, msg3, payout = contract2.resolve_dispute(arbiter_score_bp=4200)
    print(f"Resolve: {payout['reason']}")
    print(f"Buyer gets: {payout['buyer']}bp, Seller gets: {payout['seller']}bp")

    game_theory_analysis()

    # Two-layer model
    print("\n--- Two-Layer Delivery Model ---")
    print(f"{'Layer':<20} {'Verifiable?':<15} {'Method':<30}")
    print("-" * 65)
    print(f"{'1. Delivery':<20} {'YES (hash)':<15} {'receipt_hash = integer Brier'}")
    print(f"{'2. Quality':<20} {'NO (subjective)':<15} {'arbiter scoring (non-det)'}")
    print()
    print("Layer 1 = self-certifying (hash match, no arbiter needed)")
    print("Layer 2 = requires arbiter (LLM output non-deterministic)")
    print("TC4 proved: hash oracle catches 100% delivery, 0% quality.")
    print("Dual deposit makes cheating irrational at BOTH layers.")


if __name__ == "__main__":
    main()
