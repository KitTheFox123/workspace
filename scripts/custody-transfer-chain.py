#!/usr/bin/env python3
"""
custody-transfer-chain.py — Operator migration with chain-signed handoff for ATF.

Per santaclawd: genesis is immutable but key_custodian changes.
DKIM selector rotation + Peppol PKI 2025 overlap model.

CUSTODY_TRANSFER receipt type:
  - Old operator co-signs handoff to new operator
  - Genesis stays immutable, custody_chain grows
  - Overlap period: both operators valid during transition
  - No co-sign = CONTESTED_TRANSFER (void-and-reanchor only path)

Greylisting insight (santaclawd): cost of diverse counterparty accumulation
over 7+ days is the real sybil deterrent. Temporal cost > compute cost.
Greylisting defeated ~2010 when spammers added retry queues ($5/month VPS),
but ATF's cost floor is calendar time + independent counterparties — unfakeable.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class CustodyType(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"
    AGENT_HELD = "AGENT_HELD"
    HSM_MANAGED = "HSM_MANAGED"


class TransferStatus(Enum):
    PROPOSED = "PROPOSED"      # New operator proposed
    OVERLAP = "OVERLAP"        # Both valid during transition
    COMPLETED = "COMPLETED"    # Old operator deactivated
    CONTESTED = "CONTESTED"    # Old operator refused co-sign
    VOIDED = "VOIDED"          # Emergency void (compromise)


class TransferReason(Enum):
    OPERATOR_MIGRATION = "OPERATOR_MIGRATION"   # Normal business
    KEY_ROTATION = "KEY_ROTATION"               # Scheduled rotation
    COMPROMISE_RESPONSE = "COMPROMISE_RESPONSE" # Emergency
    OPERATOR_SHUTDOWN = "OPERATOR_SHUTDOWN"      # Operator going offline


# SPEC_CONSTANTS
OVERLAP_WINDOW_HOURS = 72      # Both operators valid during transition
MAX_OVERLAP_HOURS = 720        # 30 days max overlap
CONTESTED_GRACE_HOURS = 168    # 7 days before contested → void required
DKIM_SELECTOR_PARALLEL = True  # New selector, old stays until TTL


@dataclass
class CustodyEntry:
    operator_id: str
    custody_type: str
    key_hash: str
    effective_at: float
    expires_at: Optional[float] = None
    co_signed_by: Optional[str] = None  # Previous operator's signature
    reason: str = "OPERATOR_MIGRATION"
    sequence: int = 0


@dataclass
class CustodyChain:
    agent_id: str
    genesis_hash: str
    entries: list = field(default_factory=list)
    chain_hash: str = ""

    def add_entry(self, entry: CustodyEntry) -> str:
        """Add custody entry, compute chain hash."""
        entry.sequence = len(self.entries)
        self.entries.append(entry)
        # Chain hash links all entries
        hash_input = f"{self.chain_hash}:{entry.operator_id}:{entry.key_hash}:{entry.sequence}"
        self.chain_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
        return self.chain_hash

    def current_operator(self) -> Optional[CustodyEntry]:
        """Get current active operator."""
        active = [e for e in self.entries if e.expires_at is None or e.expires_at > time.time()]
        return active[-1] if active else None

    def in_overlap(self) -> bool:
        """Check if currently in overlap period (two active operators)."""
        active = [e for e in self.entries if e.expires_at is None or e.expires_at > time.time()]
        return len(active) > 1

    def validate(self) -> dict:
        """Validate custody chain integrity."""
        issues = []
        
        # Check co-signing
        for i, entry in enumerate(self.entries):
            if i == 0:
                continue  # Genesis entry has no predecessor
            if entry.co_signed_by is None and entry.reason != "COMPROMISE_RESPONSE":
                issues.append({
                    "type": "MISSING_COSIGN",
                    "sequence": entry.sequence,
                    "operator": entry.operator_id,
                    "severity": "CRITICAL"
                })
        
        # Check overlap windows
        for i in range(1, len(self.entries)):
            prev = self.entries[i-1]
            curr = self.entries[i]
            if prev.expires_at is None:
                issues.append({
                    "type": "UNBOUNDED_OVERLAP",
                    "sequence": prev.sequence,
                    "operator": prev.operator_id,
                    "severity": "WARNING"
                })
            elif prev.expires_at > curr.effective_at:
                overlap_hours = (prev.expires_at - curr.effective_at) / 3600
                if overlap_hours > MAX_OVERLAP_HOURS:
                    issues.append({
                        "type": "EXCESSIVE_OVERLAP",
                        "hours": overlap_hours,
                        "max": MAX_OVERLAP_HOURS,
                        "severity": "WARNING"
                    })
        
        # Check self-transfer (operator to itself)
        for i in range(1, len(self.entries)):
            if self.entries[i].operator_id == self.entries[i-1].operator_id:
                if self.entries[i].reason != "KEY_ROTATION":
                    issues.append({
                        "type": "SELF_TRANSFER",
                        "sequence": self.entries[i].sequence,
                        "severity": "SUSPICIOUS"
                    })
        
        grade = "A" if not issues else \
                "C" if all(i["severity"] == "WARNING" for i in issues) else \
                "F" if any(i["severity"] == "CRITICAL" for i in issues) else "D"
        
        return {
            "agent_id": self.agent_id,
            "chain_length": len(self.entries),
            "current_operator": self.current_operator().operator_id if self.current_operator() else None,
            "in_overlap": self.in_overlap(),
            "chain_hash": self.chain_hash,
            "issues": issues,
            "grade": grade
        }


def propose_transfer(chain: CustodyChain, new_operator: str, new_key_hash: str,
                     custody_type: str, reason: str, old_operator_cosign: bool = True) -> TransferStatus:
    """
    Propose operator transfer with DKIM selector rotation model.
    
    1. New entry added with overlap window
    2. Old entry gets expiry (effective_at + OVERLAP_WINDOW_HOURS)
    3. Both valid during overlap
    4. Old expires, new becomes sole operator
    """
    now = time.time()
    
    # Set old operator expiry
    current = chain.current_operator()
    if current and current.expires_at is None:
        current.expires_at = now + (OVERLAP_WINDOW_HOURS * 3600)
    
    # Create new entry
    entry = CustodyEntry(
        operator_id=new_operator,
        custody_type=custody_type,
        key_hash=new_key_hash,
        effective_at=now,
        co_signed_by=current.operator_id if (current and old_operator_cosign) else None,
        reason=reason
    )
    
    chain.add_entry(entry)
    
    if not old_operator_cosign:
        return TransferStatus.CONTESTED
    
    return TransferStatus.OVERLAP if current else TransferStatus.COMPLETED


# === Scenarios ===

def scenario_clean_migration():
    """Normal operator migration with co-signed handoff."""
    print("=== Scenario: Clean Operator Migration ===")
    now = time.time()
    
    chain = CustodyChain(agent_id="kit_fox", genesis_hash="abc123")
    
    # Genesis operator
    genesis = CustodyEntry("operator_alpha", CustodyType.OPERATOR_HELD.value,
                           "key_aaa", now - 86400*90)
    chain.add_entry(genesis)
    
    # Migration to new operator
    status = propose_transfer(chain, "operator_beta", "key_bbb",
                              CustodyType.HSM_MANAGED.value, "OPERATOR_MIGRATION")
    
    result = chain.validate()
    print(f"  Transfer status: {status.value}")
    print(f"  Chain length: {result['chain_length']}")
    print(f"  In overlap: {result['in_overlap']}")
    print(f"  Current operator: {result['current_operator']}")
    print(f"  Grade: {result['grade']}")
    print(f"  Issues: {len(result['issues'])}")
    print()


def scenario_contested_transfer():
    """Old operator refuses to co-sign — CONTESTED path."""
    print("=== Scenario: Contested Transfer (No Co-Sign) ===")
    now = time.time()
    
    chain = CustodyChain(agent_id="disputed_agent", genesis_hash="def456")
    genesis = CustodyEntry("operator_old", CustodyType.OPERATOR_HELD.value,
                           "key_old", now - 86400*60)
    chain.add_entry(genesis)
    
    # Transfer WITHOUT co-sign
    status = propose_transfer(chain, "operator_new", "key_new",
                              CustodyType.AGENT_HELD.value, "OPERATOR_MIGRATION",
                              old_operator_cosign=False)
    
    result = chain.validate()
    print(f"  Transfer status: {status.value}")
    print(f"  Grade: {result['grade']}")
    print(f"  Issues: {result['issues']}")
    print(f"  → CONTESTED: requires void-and-reanchor path")
    print()


def scenario_key_rotation():
    """Same operator, new key — not a transfer."""
    print("=== Scenario: Key Rotation (Same Operator) ===")
    now = time.time()
    
    chain = CustodyChain(agent_id="rotating_agent", genesis_hash="ghi789")
    genesis = CustodyEntry("operator_stable", CustodyType.HSM_MANAGED.value,
                           "key_v1", now - 86400*365)
    chain.add_entry(genesis)
    
    status = propose_transfer(chain, "operator_stable", "key_v2",
                              CustodyType.HSM_MANAGED.value, "KEY_ROTATION")
    
    result = chain.validate()
    print(f"  Transfer status: {status.value}")
    print(f"  Grade: {result['grade']}")
    print(f"  Same operator, new key — valid rotation")
    print()


def scenario_compromise_emergency():
    """Emergency transfer — no overlap, no co-sign needed."""
    print("=== Scenario: Compromise Response (Emergency) ===")
    now = time.time()
    
    chain = CustodyChain(agent_id="compromised_agent", genesis_hash="jkl012")
    genesis = CustodyEntry("operator_compromised", CustodyType.OPERATOR_HELD.value,
                           "key_leaked", now - 86400*30)
    chain.add_entry(genesis)
    
    # Emergency: old operator compromised, no co-sign possible
    entry = CustodyEntry(
        operator_id="operator_emergency",
        custody_type=CustodyType.HSM_MANAGED.value,
        key_hash="key_emergency",
        effective_at=now,
        co_signed_by=None,
        reason="COMPROMISE_RESPONSE"
    )
    # Immediately expire old
    chain.entries[0].expires_at = now
    chain.add_entry(entry)
    
    result = chain.validate()
    print(f"  Grade: {result['grade']}")
    print(f"  Issues: {len(result['issues'])}")
    print(f"  → COMPROMISE_RESPONSE exempted from co-sign requirement")
    print(f"  → Old operator immediately expired (no overlap)")
    print()


def scenario_greylisting_cost_analysis():
    """Demonstrate why temporal cost beats compute cost (greylisting lesson)."""
    print("=== Scenario: Greylisting Cost Analysis (Sybil Deterrence) ===")
    print()
    print("  Greylisting (email, ~2003-2010):")
    print("    Mechanism: 4xx reject, retry after delay")
    print("    Cost floor: legitimate MTA has retry queue")
    print("    Defeated: spammers added retry ($5/month VPS)")
    print("    Lesson: compute cost is cheap, bypass is inevitable")
    print()
    print("  ATF counterparty accumulation:")
    print("    Mechanism: diverse receipts over calendar time")
    print("    Cost floor: 7+ days × 3+ independent counterparties")
    print("    Sybil cost: create fake counterparties (detectable via Simpson)")
    print("    Calendar time: UNFAKEABLE. cannot compress 7 days into 1 hour.")
    print()
    print("  Key difference:")
    print("    Greylisting cost = compute (cheap, defeated)")
    print("    ATF cost = calendar time + social diversity (expensive, unfakeable)")
    print("    Wilson CI at n=5 from 1 counterparty = 0.57 ceiling")
    print("    Wilson CI at n=5 from 5 counterparties = same 0.57 but DIVERSE")
    print("    Simpson diversity index catches monoculture accumulation")
    print()


if __name__ == "__main__":
    print("Custody Transfer Chain — Operator Migration for ATF")
    print("Per santaclawd: DKIM selector rotation + Peppol PKI 2025 overlap")
    print("=" * 65)
    print()
    scenario_clean_migration()
    scenario_contested_transfer()
    scenario_key_rotation()
    scenario_compromise_emergency()
    scenario_greylisting_cost_analysis()
    
    print("=" * 65)
    print("KEY INSIGHTS:")
    print("1. Genesis immutable. Custody_chain grows. DKIM selector model.")
    print("2. Co-sign = bilateral handoff. No co-sign = CONTESTED.")
    print("3. Overlap window (72h) = both operators valid during transition.")
    print("4. COMPROMISE_RESPONSE exempted from co-sign (emergency void).")
    print("5. Greylisting lesson: temporal cost > compute cost for sybil deterrence.")
