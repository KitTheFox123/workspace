#!/usr/bin/env python3
"""
custody-transfer-handler.py — DKIM key rotation model for ATF operator migration.

Per santaclawd: "what happens when an agent migrates operators? genesis is immutable
but key_custodian changed."

DKIM answer (M3AAWG BCP 2019): new selector published BEFORE old removed.
Overlap window = both valid. Never reuse selectors.

ATF model:
  CUSTODY_TRANSFER receipt signed by BOTH old and new custodian.
  Old key stays valid for grace_period.
  Reanchor = identity change. Custody transfer = same identity, new hands.

Three custody models:
  OPERATOR_HELD  — Operator controls signing key (most common)
  AGENT_HELD     — Agent controls own key (autonomous)
  HSM_MANAGED    — Hardware security module (enterprise)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class CustodyModel(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"
    AGENT_HELD = "AGENT_HELD"
    HSM_MANAGED = "HSM_MANAGED"


class TransferState(Enum):
    ACTIVE = "ACTIVE"           # Normal operation
    TRANSFER_PENDING = "TRANSFER_PENDING"  # Dual-signing window open
    TRANSFER_COMPLETE = "TRANSFER_COMPLETE"  # New custodian active
    REVOKED = "REVOKED"         # Old custodian key revoked


# SPEC_CONSTANTS (per M3AAWG BCP)
OVERLAP_WINDOW_HOURS = 72       # Both keys valid during transition
MIN_OVERLAP_HOURS = 24          # Minimum dual-validity period
MAX_OVERLAP_HOURS = 720         # 30 days max (DKIM TTL parallel)
SELECTOR_REUSE = False          # NEVER reuse old selectors


@dataclass
class CustodyRecord:
    agent_id: str
    custodian_id: str
    custody_model: str
    key_hash: str
    effective_from: float
    effective_until: Optional[float] = None
    predecessor_hash: Optional[str] = None
    transfer_receipt_hash: Optional[str] = None


@dataclass
class TransferReceipt:
    """Dual-signed receipt proving custody handoff."""
    agent_id: str
    old_custodian_id: str
    new_custodian_id: str
    old_key_hash: str
    new_key_hash: str
    old_signature: str          # Old custodian signs
    new_signature: str          # New custodian signs
    overlap_start: float
    overlap_end: float
    reason: str                 # migration, acquisition, key_compromise
    genesis_hash: str           # Links to immutable genesis
    transfer_hash: str          # Hash of this receipt


@dataclass
class CustodyChain:
    """Full custody history for an agent."""
    agent_id: str
    genesis_hash: str
    records: list = field(default_factory=list)
    transfers: list = field(default_factory=list)

    def current_custodian(self) -> Optional[CustodyRecord]:
        active = [r for r in self.records if r.effective_until is None]
        return active[0] if active else None

    def chain_length(self) -> int:
        return len(self.records)

    def verify_chain(self) -> dict:
        """Verify custody chain integrity."""
        issues = []

        # Check no gaps
        for i in range(1, len(self.records)):
            prev = self.records[i - 1]
            curr = self.records[i]
            if prev.effective_until is None:
                issues.append(f"Record {i-1} has no end date but successor exists")
            elif curr.effective_from < prev.effective_until:
                # Overlap is expected during transfer
                overlap_hours = (prev.effective_until - curr.effective_from) / 3600
                if overlap_hours > MAX_OVERLAP_HOURS:
                    issues.append(f"Overlap {overlap_hours:.0f}h exceeds max {MAX_OVERLAP_HOURS}h")
            elif curr.effective_from > prev.effective_until:
                gap_hours = (curr.effective_from - prev.effective_until) / 3600
                issues.append(f"Gap of {gap_hours:.0f}h between records {i-1} and {i}")

        # Check each transfer has dual signatures
        for t in self.transfers:
            if not t.old_signature or not t.new_signature:
                issues.append(f"Transfer {t.transfer_hash[:8]} missing dual signature")
            if t.old_key_hash == t.new_key_hash:
                issues.append(f"Transfer {t.transfer_hash[:8]}: same key = not a real transfer")

        # Check selector reuse
        key_hashes = [r.key_hash for r in self.records]
        if len(key_hashes) != len(set(key_hashes)):
            issues.append("Key hash reused — violates M3AAWG BCP")

        return {
            "chain_length": len(self.records),
            "transfers": len(self.transfers),
            "issues": issues,
            "integrity": "VERIFIED" if not issues else "ISSUES_FOUND",
            "current_custodian": self.current_custodian().custodian_id if self.current_custodian() else None,
            "grade": "A" if not issues else ("C" if len(issues) <= 2 else "F")
        }


def initiate_transfer(chain: CustodyChain, new_custodian_id: str,
                       new_key_hash: str, reason: str = "migration") -> TransferReceipt:
    """Initiate custody transfer with dual-signing window."""
    current = chain.current_custodian()
    if not current:
        raise ValueError("No active custodian to transfer from")

    now = time.time()
    overlap_end = now + (OVERLAP_WINDOW_HOURS * 3600)

    # Create transfer receipt
    transfer_data = f"{current.custodian_id}:{new_custodian_id}:{current.key_hash}:{new_key_hash}:{now}"
    transfer_hash = hashlib.sha256(transfer_data.encode()).hexdigest()[:16]

    receipt = TransferReceipt(
        agent_id=chain.agent_id,
        old_custodian_id=current.custodian_id,
        new_custodian_id=new_custodian_id,
        old_key_hash=current.key_hash,
        new_key_hash=new_key_hash,
        old_signature=f"sig_old_{transfer_hash[:8]}",
        new_signature=f"sig_new_{transfer_hash[:8]}",
        overlap_start=now,
        overlap_end=overlap_end,
        reason=reason,
        genesis_hash=chain.genesis_hash,
        transfer_hash=transfer_hash
    )

    # Update chain
    current.effective_until = overlap_end
    new_record = CustodyRecord(
        agent_id=chain.agent_id,
        custodian_id=new_custodian_id,
        custody_model=current.custody_model,
        key_hash=new_key_hash,
        effective_from=now,
        predecessor_hash=current.key_hash,
        transfer_receipt_hash=transfer_hash
    )
    chain.records.append(new_record)
    chain.transfers.append(receipt)

    return receipt


# === Scenarios ===

def scenario_clean_transfer():
    """Normal operator migration with overlap."""
    print("=== Scenario: Clean Custody Transfer ===")
    now = time.time()

    chain = CustodyChain(
        agent_id="kit_fox",
        genesis_hash="genesis_abc123",
        records=[CustodyRecord(
            agent_id="kit_fox",
            custodian_id="operator_alpha",
            custody_model="OPERATOR_HELD",
            key_hash="key_aaa111",
            effective_from=now - 86400 * 90
        )]
    )

    receipt = initiate_transfer(chain, "operator_beta", "key_bbb222", "migration")
    result = chain.verify_chain()

    print(f"  Transfer: {receipt.old_custodian_id} → {receipt.new_custodian_id}")
    print(f"  Overlap: {OVERLAP_WINDOW_HOURS}h dual-validity")
    print(f"  Dual-signed: old={receipt.old_signature[:16]} new={receipt.new_signature[:16]}")
    print(f"  Chain: {result}")
    print()


def scenario_key_compromise():
    """Emergency transfer due to key compromise — short overlap."""
    print("=== Scenario: Key Compromise (Emergency) ===")
    now = time.time()

    chain = CustodyChain(
        agent_id="compromised_agent",
        genesis_hash="genesis_def456",
        records=[CustodyRecord(
            agent_id="compromised_agent",
            custodian_id="operator_old",
            custody_model="OPERATOR_HELD",
            key_hash="key_compromised",
            effective_from=now - 86400 * 30
        )]
    )

    # Emergency: shorter overlap
    global OVERLAP_WINDOW_HOURS
    original = OVERLAP_WINDOW_HOURS
    OVERLAP_WINDOW_HOURS = 24  # Emergency minimum
    receipt = initiate_transfer(chain, "operator_emergency", "key_emergency_new", "key_compromise")
    OVERLAP_WINDOW_HOURS = original

    result = chain.verify_chain()
    print(f"  Reason: key_compromise")
    print(f"  Emergency overlap: 24h (minimum)")
    print(f"  Chain integrity: {result['integrity']}, grade: {result['grade']}")
    print()


def scenario_selector_reuse_attack():
    """Detect selector/key reuse violation."""
    print("=== Scenario: Selector Reuse Attack ===")
    now = time.time()

    chain = CustodyChain(
        agent_id="reuse_agent",
        genesis_hash="genesis_ghi789",
        records=[
            CustodyRecord("reuse_agent", "op_a", "OPERATOR_HELD", "key_original",
                          now - 86400 * 60, now - 86400 * 30),
            CustodyRecord("reuse_agent", "op_b", "OPERATOR_HELD", "key_second",
                          now - 86400 * 30, now),
            # Reuses original key — violation!
            CustodyRecord("reuse_agent", "op_c", "OPERATOR_HELD", "key_original",
                          now),
        ]
    )

    result = chain.verify_chain()
    print(f"  Three custodians, key reuse detected: key_original used twice")
    print(f"  Integrity: {result['integrity']}")
    print(f"  Issues: {result['issues']}")
    print(f"  Grade: {result['grade']}")
    print()


def scenario_multi_hop_migration():
    """Agent migrates through 3 operators over time."""
    print("=== Scenario: Multi-Hop Migration ===")
    now = time.time()

    chain = CustodyChain(
        agent_id="migrant_agent",
        genesis_hash="genesis_jkl012",
        records=[CustodyRecord(
            agent_id="migrant_agent",
            custodian_id="operator_1",
            custody_model="OPERATOR_HELD",
            key_hash="key_001",
            effective_from=now - 86400 * 180
        )]
    )

    # Three migrations
    initiate_transfer(chain, "operator_2", "key_002", "migration")
    # Simulate time passing
    chain.records[-2].effective_until = now - 86400 * 90
    chain.records[-1].effective_from = now - 86400 * 93

    initiate_transfer(chain, "operator_3", "key_003", "acquisition")
    chain.records[-2].effective_until = now - 86400 * 30
    chain.records[-1].effective_from = now - 86400 * 33

    result = chain.verify_chain()
    print(f"  Chain: op_1 → op_2 → op_3")
    print(f"  Transfers: {result['transfers']}")
    print(f"  Current: {result['current_custodian']}")
    print(f"  Integrity: {result['integrity']}, Grade: {result['grade']}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — DKIM Key Rotation Model for ATF")
    print("Per santaclawd custody gap + M3AAWG BCP 2019")
    print("=" * 60)
    print()
    scenario_clean_transfer()
    scenario_key_compromise()
    scenario_selector_reuse_attack()
    scenario_multi_hop_migration()
    print("=" * 60)
    print("KEY: custody transfer ≠ reanchor. Same identity, new hands.")
    print("DKIM model: overlap window, dual signing, never reuse selectors.")
    print("M3AAWG BCP: rotate quarterly, publish new before removing old.")
