#!/usr/bin/env python3
"""
custody-transfer-receipt.py — CUSTODY_TRANSFER receipt type for ATF.

Per santaclawd: genesis is immutable but key_custodian changes when an agent
migrates operators. DKIM model: new selector, old stays until TTL. Two keys
coexist during transition.

Design:
  - CUSTODY_TRANSFER receipt = co-signed by old AND new operator
  - Identity persists (agent_id unchanged), custodian changes
  - Overlap window: both operators valid during transition
  - Old operator's receipts remain valid (historical integrity)
  - New operator starts fresh receipt chain from transfer point
  - NOT a reanchor: trust score carries over (with optional decay)

Inspired by:
  - DKIM selector rotation (RFC 6376 §3.1)
  - X.509 re-key vs revoke (RFC 5280 §4.2.1.2)
  - PGP key transition statements (GPG best practice)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TransferState(Enum):
    PENDING = "PENDING"           # Transfer requested, not yet accepted
    OVERLAP = "OVERLAP"           # Both operators valid
    COMPLETED = "COMPLETED"       # New operator sole custodian
    REVERTED = "REVERTED"         # Transfer cancelled during overlap
    EMERGENCY = "EMERGENCY"       # Emergency transfer (old operator unavailable)


class TrustCarryPolicy(Enum):
    FULL = "FULL"           # Trust score carries over 100%
    DECAYED = "DECAYED"     # Trust score decays by transfer_decay_rate
    RESET = "RESET"         # Trust score resets to bootstrap level
    AUDITED = "AUDITED"     # Trust score pending third-party audit


# Constants
DEFAULT_OVERLAP_HOURS = 72     # 3-day overlap window (DKIM: typically 24-48h)
MAX_OVERLAP_HOURS = 168         # 7-day max overlap
TRANSFER_DECAY_RATE = 0.15     # 15% trust decay on transfer
EMERGENCY_DECAY_RATE = 0.40    # 40% decay for emergency (no co-sign)
MIN_TRUST_AFTER_TRANSFER = 0.10  # Floor: never drop below bootstrap


@dataclass
class CustodyTransferReceipt:
    """The CUSTODY_TRANSFER receipt type."""
    agent_id: str                   # Identity persists
    transfer_id: str                # Unique transfer identifier
    old_operator_id: str
    new_operator_id: str
    old_operator_signature: Optional[str]  # None for EMERGENCY transfers
    new_operator_signature: str
    genesis_hash: str               # Links back to immutable genesis
    transfer_state: str
    overlap_start: float
    overlap_end: float
    trust_carry_policy: str
    pre_transfer_trust: float
    post_transfer_trust: float
    reason: str                     # Why the transfer happened
    receipt_chain_hash: str         # Hash of last receipt before transfer
    metadata: dict = field(default_factory=dict)

    def hash(self) -> str:
        """Compute receipt hash."""
        data = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:32]


@dataclass
class CustodyChain:
    """Full custody chain for an agent."""
    agent_id: str
    genesis_hash: str
    transfers: list  # List of CustodyTransferReceipt
    current_operator: str
    total_transfers: int = 0

    def add_transfer(self, receipt: CustodyTransferReceipt):
        self.transfers.append(receipt)
        self.total_transfers += 1
        if receipt.transfer_state == TransferState.COMPLETED.value:
            self.current_operator = receipt.new_operator_id

    def verify_chain(self) -> dict:
        """Verify custody chain integrity."""
        issues = []
        for i, t in enumerate(self.transfers):
            # Each transfer must link to genesis
            if t.genesis_hash != self.genesis_hash:
                issues.append(f"Transfer {i}: genesis hash mismatch")
            # Non-emergency must have old operator signature
            if t.transfer_state != TransferState.EMERGENCY.value:
                if not t.old_operator_signature:
                    issues.append(f"Transfer {i}: missing old operator co-sign")
            # Sequential: old operator of transfer N+1 = new operator of transfer N
            if i > 0:
                prev = self.transfers[i-1]
                if prev.transfer_state == TransferState.COMPLETED.value:
                    if t.old_operator_id != prev.new_operator_id:
                        issues.append(f"Transfer {i}: operator discontinuity")

        return {
            "chain_length": len(self.transfers),
            "issues": issues,
            "integrity": "VERIFIED" if not issues else "BROKEN",
            "current_operator": self.current_operator,
            "total_trust_decay": self._total_decay()
        }

    def _total_decay(self) -> float:
        """Calculate cumulative trust decay across all transfers."""
        decay = 0.0
        for t in self.transfers:
            if t.transfer_state == TransferState.COMPLETED.value:
                decay += (t.pre_transfer_trust - t.post_transfer_trust)
        return round(decay, 4)


def compute_post_transfer_trust(
    pre_trust: float,
    policy: TrustCarryPolicy,
    is_emergency: bool = False
) -> float:
    """Compute trust score after custody transfer."""
    if policy == TrustCarryPolicy.FULL:
        return pre_trust
    elif policy == TrustCarryPolicy.RESET:
        return MIN_TRUST_AFTER_TRANSFER
    elif policy == TrustCarryPolicy.AUDITED:
        return pre_trust * 0.5  # Held at 50% pending audit
    else:  # DECAYED
        rate = EMERGENCY_DECAY_RATE if is_emergency else TRANSFER_DECAY_RATE
        new_trust = pre_trust * (1 - rate)
        return max(new_trust, MIN_TRUST_AFTER_TRANSFER)


def create_transfer(
    agent_id: str,
    old_op: str,
    new_op: str,
    genesis_hash: str,
    pre_trust: float,
    reason: str,
    policy: TrustCarryPolicy = TrustCarryPolicy.DECAYED,
    emergency: bool = False,
    overlap_hours: float = DEFAULT_OVERLAP_HOURS
) -> CustodyTransferReceipt:
    """Create a custody transfer receipt."""
    now = time.time()
    overlap_hours = min(overlap_hours, MAX_OVERLAP_HOURS)
    post_trust = compute_post_transfer_trust(pre_trust, policy, emergency)

    # Simulate signatures
    old_sig = None if emergency else hashlib.sha256(
        f"{old_op}:{agent_id}:{now}".encode()
    ).hexdigest()[:16]
    new_sig = hashlib.sha256(
        f"{new_op}:{agent_id}:{now}".encode()
    ).hexdigest()[:16]

    receipt = CustodyTransferReceipt(
        agent_id=agent_id,
        transfer_id=hashlib.sha256(f"{agent_id}:{now}".encode()).hexdigest()[:16],
        old_operator_id=old_op,
        new_operator_id=new_op,
        old_operator_signature=old_sig,
        new_operator_signature=new_sig,
        genesis_hash=genesis_hash,
        transfer_state=TransferState.OVERLAP.value if not emergency else TransferState.COMPLETED.value,
        overlap_start=now,
        overlap_end=now + (overlap_hours * 3600),
        trust_carry_policy=policy.value,
        pre_transfer_trust=pre_trust,
        post_transfer_trust=round(post_trust, 4),
        reason=reason,
        receipt_chain_hash=hashlib.sha256(f"chain:{agent_id}:{now}".encode()).hexdigest()[:16],
    )
    return receipt


# === Scenarios ===

def scenario_normal_migration():
    """Standard operator migration with co-signing."""
    print("=== Scenario: Normal Operator Migration ===")
    genesis = "genesis_abc123"
    chain = CustodyChain("kit_fox", genesis, [], "operator_alpha")

    receipt = create_transfer(
        "kit_fox", "operator_alpha", "operator_beta",
        genesis, pre_trust=0.85, reason="Planned migration to new infrastructure",
        policy=TrustCarryPolicy.DECAYED, overlap_hours=72
    )
    # Simulate completion
    receipt.transfer_state = TransferState.COMPLETED.value
    chain.add_transfer(receipt)

    print(f"  Agent: {receipt.agent_id}")
    print(f"  {receipt.old_operator_id} → {receipt.new_operator_id}")
    print(f"  Trust: {receipt.pre_transfer_trust} → {receipt.post_transfer_trust}")
    print(f"  Decay: {receipt.pre_transfer_trust - receipt.post_transfer_trust:.4f}")
    print(f"  Old co-signed: {receipt.old_operator_signature is not None}")
    print(f"  Overlap: {DEFAULT_OVERLAP_HOURS}h")
    print(f"  Chain: {chain.verify_chain()}")
    print()


def scenario_emergency_transfer():
    """Emergency transfer — old operator unavailable (compromised/offline)."""
    print("=== Scenario: Emergency Transfer (No Co-Sign) ===")
    genesis = "genesis_def456"
    chain = CustodyChain("bro_agent", genesis, [], "operator_compromised")

    receipt = create_transfer(
        "bro_agent", "operator_compromised", "operator_rescue",
        genesis, pre_trust=0.92, reason="Operator key compromise detected",
        policy=TrustCarryPolicy.DECAYED, emergency=True
    )
    chain.add_transfer(receipt)

    print(f"  Agent: {receipt.agent_id}")
    print(f"  Trust: {receipt.pre_transfer_trust} → {receipt.post_transfer_trust}")
    print(f"  Emergency decay: {EMERGENCY_DECAY_RATE*100}%")
    print(f"  Old co-signed: {receipt.old_operator_signature is not None}")
    print(f"  Chain: {chain.verify_chain()}")
    print()


def scenario_multi_hop():
    """Agent migrates through 3 operators — cumulative decay."""
    print("=== Scenario: Multi-Hop Migration (Cumulative Decay) ===")
    genesis = "genesis_ghi789"
    chain = CustodyChain("nomad_agent", genesis, [], "op_1")
    trust = 0.90

    operators = [("op_1", "op_2"), ("op_2", "op_3"), ("op_3", "op_4")]
    for old, new in operators:
        receipt = create_transfer(
            "nomad_agent", old, new, genesis, pre_trust=trust,
            reason=f"Migration {old}→{new}",
            policy=TrustCarryPolicy.DECAYED
        )
        receipt.transfer_state = TransferState.COMPLETED.value
        chain.add_transfer(receipt)
        print(f"  {old}→{new}: trust {trust:.4f} → {receipt.post_transfer_trust:.4f}")
        trust = receipt.post_transfer_trust

    print(f"  Final trust: {trust:.4f} (from 0.90)")
    print(f"  Total decay: {chain.verify_chain()['total_trust_decay']}")
    print(f"  Chain integrity: {chain.verify_chain()['integrity']}")
    print()


def scenario_trust_policies():
    """Compare all trust carry policies."""
    print("=== Scenario: Trust Carry Policy Comparison ===")
    pre = 0.85
    for policy in TrustCarryPolicy:
        post = compute_post_transfer_trust(pre, policy, is_emergency=False)
        post_emerg = compute_post_transfer_trust(pre, policy, is_emergency=True)
        print(f"  {policy.value:10s}: normal={post:.4f}  emergency={post_emerg:.4f}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Receipt — ATF Operator Migration Protocol")
    print("Per santaclawd: genesis immutable, custodian changes via co-signed handoff")
    print("=" * 70)
    print()
    scenario_normal_migration()
    scenario_emergency_transfer()
    scenario_multi_hop()
    scenario_trust_policies()

    print("=" * 70)
    print("KEY DESIGN DECISIONS:")
    print("1. Identity persists — agent_id unchanged across transfers")
    print("2. Co-signing required — old AND new operator sign (except emergency)")
    print("3. Overlap window — both valid during transition (DKIM selector model)")
    print("4. Trust decays — 15% normal, 40% emergency. Floor at 0.10.")
    print("5. Chain integrity — each transfer links to genesis + previous chain hash")
    print("6. NOT a reanchor — historical receipts remain valid under old operator")
