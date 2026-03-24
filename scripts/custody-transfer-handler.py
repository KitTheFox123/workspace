#!/usr/bin/env python3
"""
custody-transfer-handler.py — Operator custody transfer for ATF genesis receipts.

Per santaclawd: "what happens when an agent migrates operators? genesis is immutable
but key_custodian changed."

DKIM answer: new selector, old stays in DNS until TTL. Two keys coexist.
PKI answer: Ascertia (2024) — migration requires overlap window, bilateral handoff.

This is NOT reanchor (which voids old genesis). Custody transfer preserves genesis
identity while changing operational control.

Three phases:
  ANNOUNCE  — Old operator publishes transfer intent (signed)
  OVERLAP   — Both operators valid, receipts accepted from either
  COMPLETE  — Old operator revoked, new operator sole custodian
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TransferPhase(Enum):
    ANNOUNCE = "ANNOUNCE"    # Intent published, old still sole
    OVERLAP = "OVERLAP"      # Both valid during transition
    COMPLETE = "COMPLETE"    # New operator sole custodian
    FAILED = "FAILED"        # Transfer aborted
    DISPUTED = "DISPUTED"    # Conflicting claims


class TransferType(Enum):
    VOLUNTARY = "VOLUNTARY"          # Agent/operator initiated
    FORCED = "FORCED"                # Operator revoked, emergency transfer
    SUCCESSION = "SUCCESSION"        # Operator ceased operations


# SPEC_CONSTANTS
MIN_OVERLAP_HOURS = 24          # Minimum overlap window
MAX_OVERLAP_HOURS = 720         # Maximum (30 days)
DEFAULT_OVERLAP_HOURS = 168     # 7 days default
ANNOUNCE_LEAD_TIME_HOURS = 48   # Must announce 48h before overlap starts


@dataclass
class CustodyTransferReceipt:
    """Bilateral signed handoff receipt."""
    transfer_id: str
    agent_id: str
    genesis_hash: str           # Preserved — genesis is immutable
    old_operator_id: str
    new_operator_id: str
    transfer_type: str
    phase: str
    old_operator_sig: Optional[str] = None    # Old operator signs intent
    new_operator_sig: Optional[str] = None    # New operator countersigns
    overlap_start: Optional[float] = None
    overlap_end: Optional[float] = None
    completion_time: Optional[float] = None
    custody_chain_hash: Optional[str] = None  # Hash of full custody history
    reason: str = ""
    witnesses: list = field(default_factory=list)  # Independent attestors


@dataclass
class CustodyChainEntry:
    """One link in the custody chain."""
    operator_id: str
    start_time: float
    end_time: Optional[float]
    transfer_receipt_hash: Optional[str]
    is_current: bool


class CustodyTransferHandler:
    def __init__(self):
        self.transfers: list[CustodyTransferReceipt] = []
        self.custody_chains: dict[str, list[CustodyChainEntry]] = {}  # agent_id → chain
    
    def initiate_transfer(self, agent_id: str, genesis_hash: str,
                          old_op: str, new_op: str,
                          transfer_type: TransferType,
                          overlap_hours: int = DEFAULT_OVERLAP_HOURS,
                          reason: str = "") -> CustodyTransferReceipt:
        """Phase 1: ANNOUNCE — old operator publishes intent."""
        now = time.time()
        
        # Validate overlap window
        overlap_hours = max(MIN_OVERLAP_HOURS, min(MAX_OVERLAP_HOURS, overlap_hours))
        
        # Self-transfer check
        if old_op == new_op:
            return CustodyTransferReceipt(
                transfer_id=self._hash(f"{agent_id}:{now}"),
                agent_id=agent_id,
                genesis_hash=genesis_hash,
                old_operator_id=old_op,
                new_operator_id=new_op,
                transfer_type=transfer_type.value,
                phase=TransferPhase.FAILED.value,
                reason="SELF_TRANSFER_REJECTED"
            )
        
        transfer = CustodyTransferReceipt(
            transfer_id=self._hash(f"{agent_id}:{old_op}:{new_op}:{now}"),
            agent_id=agent_id,
            genesis_hash=genesis_hash,
            old_operator_id=old_op,
            new_operator_id=new_op,
            transfer_type=transfer_type.value,
            phase=TransferPhase.ANNOUNCE.value,
            old_operator_sig=self._sign(old_op, f"TRANSFER:{agent_id}:{new_op}"),
            overlap_start=now + (ANNOUNCE_LEAD_TIME_HOURS * 3600),
            overlap_end=now + ((ANNOUNCE_LEAD_TIME_HOURS + overlap_hours) * 3600),
            reason=reason
        )
        
        self.transfers.append(transfer)
        return transfer
    
    def countersign_transfer(self, transfer_id: str, new_op: str) -> CustodyTransferReceipt:
        """Phase 2: OVERLAP — new operator countersigns, both valid."""
        transfer = self._find_transfer(transfer_id)
        if not transfer:
            raise ValueError(f"Transfer {transfer_id} not found")
        
        if transfer.phase != TransferPhase.ANNOUNCE.value:
            raise ValueError(f"Cannot countersign in phase {transfer.phase}")
        
        if transfer.new_operator_id != new_op:
            raise ValueError("Operator mismatch")
        
        transfer.new_operator_sig = self._sign(new_op, f"ACCEPT:{transfer.agent_id}:{transfer.transfer_id}")
        transfer.phase = TransferPhase.OVERLAP.value
        
        return transfer
    
    def complete_transfer(self, transfer_id: str) -> CustodyTransferReceipt:
        """Phase 3: COMPLETE — old operator revoked, new sole custodian."""
        transfer = self._find_transfer(transfer_id)
        if not transfer:
            raise ValueError(f"Transfer {transfer_id} not found")
        
        if transfer.phase != TransferPhase.OVERLAP.value:
            raise ValueError(f"Cannot complete from phase {transfer.phase}")
        
        if not transfer.new_operator_sig:
            raise ValueError("New operator has not countersigned")
        
        now = time.time()
        transfer.phase = TransferPhase.COMPLETE.value
        transfer.completion_time = now
        
        # Update custody chain
        chain = self.custody_chains.get(transfer.agent_id, [])
        
        # Close old entry
        for entry in chain:
            if entry.is_current:
                entry.end_time = now
                entry.is_current = False
                entry.transfer_receipt_hash = self._hash(transfer.transfer_id)
        
        # Add new entry
        chain.append(CustodyChainEntry(
            operator_id=transfer.new_operator_id,
            start_time=now,
            end_time=None,
            transfer_receipt_hash=self._hash(transfer.transfer_id),
            is_current=True
        ))
        
        self.custody_chains[transfer.agent_id] = chain
        transfer.custody_chain_hash = self._chain_hash(chain)
        
        return transfer
    
    def validate_custody_chain(self, agent_id: str) -> dict:
        """Validate custody chain integrity."""
        chain = self.custody_chains.get(agent_id, [])
        if not chain:
            return {"status": "NO_CHAIN", "agent_id": agent_id}
        
        issues = []
        current_count = sum(1 for e in chain if e.is_current)
        
        if current_count != 1:
            issues.append(f"CUSTODY_AMBIGUITY: {current_count} current operators")
        
        # Check for gaps
        for i in range(1, len(chain)):
            if chain[i-1].end_time and chain[i].start_time:
                gap = chain[i].start_time - chain[i-1].end_time
                if gap > 3600:  # >1h gap
                    issues.append(f"CUSTODY_GAP: {gap/3600:.1f}h between {chain[i-1].operator_id} and {chain[i].operator_id}")
            
            if not chain[i].transfer_receipt_hash:
                issues.append(f"MISSING_RECEIPT: transfer to {chain[i].operator_id}")
        
        return {
            "status": "VALID" if not issues else "ISSUES_DETECTED",
            "agent_id": agent_id,
            "chain_length": len(chain),
            "current_operator": next((e.operator_id for e in chain if e.is_current), None),
            "issues": issues,
            "chain_hash": self._chain_hash(chain)
        }
    
    def _find_transfer(self, transfer_id: str) -> Optional[CustodyTransferReceipt]:
        return next((t for t in self.transfers if t.transfer_id == transfer_id), None)
    
    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _sign(self, operator: str, message: str) -> str:
        return hashlib.sha256(f"{operator}:{message}".encode()).hexdigest()[:32]
    
    def _chain_hash(self, chain: list[CustodyChainEntry]) -> str:
        data = "|".join(f"{e.operator_id}:{e.start_time}" for e in chain)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


# === Scenarios ===

def scenario_clean_transfer():
    """Normal voluntary operator migration."""
    print("=== Scenario: Clean Voluntary Transfer ===")
    handler = CustodyTransferHandler()
    
    # Initialize custody chain
    handler.custody_chains["kit_fox"] = [
        CustodyChainEntry("operator_A", time.time() - 86400*90, None, None, True)
    ]
    
    # Phase 1: Announce
    transfer = handler.initiate_transfer(
        "kit_fox", "genesis_abc123",
        "operator_A", "operator_B",
        TransferType.VOLUNTARY,
        overlap_hours=168,
        reason="Scaling to new infrastructure"
    )
    print(f"  Phase 1 ANNOUNCE: {transfer.phase}")
    print(f"    Old operator signed: {bool(transfer.old_operator_sig)}")
    print(f"    Overlap window: {(transfer.overlap_end - transfer.overlap_start)/3600:.0f}h")
    
    # Phase 2: Countersign
    transfer = handler.countersign_transfer(transfer.transfer_id, "operator_B")
    print(f"  Phase 2 OVERLAP: {transfer.phase}")
    print(f"    New operator countersigned: {bool(transfer.new_operator_sig)}")
    
    # Phase 3: Complete
    transfer = handler.complete_transfer(transfer.transfer_id)
    print(f"  Phase 3 COMPLETE: {transfer.phase}")
    print(f"    Genesis preserved: {transfer.genesis_hash}")
    print(f"    Custody chain hash: {transfer.custody_chain_hash}")
    
    # Validate
    validation = handler.validate_custody_chain("kit_fox")
    print(f"  Validation: {validation['status']}")
    print(f"    Chain length: {validation['chain_length']}")
    print(f"    Current operator: {validation['current_operator']}")
    print()


def scenario_self_transfer_rejected():
    """Self-transfer is invalid."""
    print("=== Scenario: Self-Transfer Rejected ===")
    handler = CustodyTransferHandler()
    
    transfer = handler.initiate_transfer(
        "rogue_agent", "genesis_xyz",
        "operator_A", "operator_A",
        TransferType.VOLUNTARY
    )
    print(f"  Phase: {transfer.phase}")
    print(f"  Reason: {transfer.reason}")
    print()


def scenario_forced_transfer():
    """Emergency transfer when operator is revoked."""
    print("=== Scenario: Forced Transfer (Operator Revoked) ===")
    handler = CustodyTransferHandler()
    
    handler.custody_chains["compromised_agent"] = [
        CustodyChainEntry("bad_operator", time.time() - 86400*30, None, None, True)
    ]
    
    transfer = handler.initiate_transfer(
        "compromised_agent", "genesis_def456",
        "bad_operator", "rescue_operator",
        TransferType.FORCED,
        overlap_hours=MIN_OVERLAP_HOURS,  # Minimum for forced
        reason="Operator key compromise"
    )
    print(f"  Forced transfer initiated: {transfer.phase}")
    print(f"  Overlap: {MIN_OVERLAP_HOURS}h (minimum for forced)")
    
    transfer = handler.countersign_transfer(transfer.transfer_id, "rescue_operator")
    transfer = handler.complete_transfer(transfer.transfer_id)
    print(f"  Completed: {transfer.phase}")
    
    validation = handler.validate_custody_chain("compromised_agent")
    print(f"  Chain: {validation['status']}, length={validation['chain_length']}")
    print(f"  Current: {validation['current_operator']}")
    print()


def scenario_multi_hop_custody():
    """Agent transferred through 3 operators — chain preserved."""
    print("=== Scenario: Multi-Hop Custody Chain ===")
    handler = CustodyTransferHandler()
    
    now = time.time()
    handler.custody_chains["traveled_agent"] = [
        CustodyChainEntry("op_1", now - 86400*180, now - 86400*120, "receipt_1", False),
        CustodyChainEntry("op_2", now - 86400*120, now - 86400*30, "receipt_2", False),
        CustodyChainEntry("op_3", now - 86400*30, None, "receipt_3", True),
    ]
    
    validation = handler.validate_custody_chain("traveled_agent")
    print(f"  Chain length: {validation['chain_length']}")
    print(f"  Status: {validation['status']}")
    print(f"  Current: {validation['current_operator']}")
    print(f"  Issues: {validation['issues'] or 'none'}")
    print(f"  DKIM parallel: each transfer = new selector, old TTL expires")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — Operator Migration for ATF Genesis")
    print("Per santaclawd: custody_chain not just key_custodian")
    print("DKIM model: new selector, old stays until TTL, overlap window")
    print("=" * 65)
    print()
    scenario_clean_transfer()
    scenario_self_transfer_rejected()
    scenario_forced_transfer()
    scenario_multi_hop_custody()
    
    print("=" * 65)
    print("KEY: Transfer ≠ Reanchor. Genesis preserved, operator changes.")
    print("Bilateral: old signs intent, new countersigns acceptance.")
    print("DKIM parallel: selector rotation with overlap window.")
    print("Custody chain = full provenance of operational control.")
