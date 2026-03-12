#!/usr/bin/env python3
"""
trace-custody-checker.py — Checks trace availability for dispute resolution.

Based on:
- santaclawd: "trace availability is the v3 blind spot. hash without data = unauditable"
- Ethereum data availability: erasure coding + DAS (Buterin 2018)
- Two-phase contract commit: trace custody as third commitment

The problem: execution_trace_hash committed at settlement.
Scoring agent goes offline → hash unverifiable → dispute deadlock.
Same as blockchain data availability: block header without block data = useless.

Fix: trace escrow to k-of-N independent parties.
Minimum: hash + 2 independent copies + TTL ≥ dispute window.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum


class CustodyStatus(Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"      # Some custodians offline
    UNAVAILABLE = "unavailable"  # Below threshold
    EXPIRED = "expired"         # Past TTL


@dataclass
class Custodian:
    name: str
    substrate: str  # "ipfs", "email", "isnad", "local"
    online: bool = True
    last_verified: float = 0.0


@dataclass
class TraceCustody:
    trace_hash: str
    custodians: list[Custodian] = field(default_factory=list)
    k_threshold: int = 2       # Minimum custodians for reconstruction
    ttl_hours: float = 168.0   # 7 days default (= dispute window)
    created_at: float = 0.0

    def available_custodians(self) -> int:
        return sum(1 for c in self.custodians if c.online)

    def status(self) -> CustodyStatus:
        now = time.time()
        if now - self.created_at > self.ttl_hours * 3600:
            return CustodyStatus.EXPIRED
        avail = self.available_custodians()
        if avail >= self.k_threshold:
            return CustodyStatus.AVAILABLE
        if avail > 0:
            return CustodyStatus.DEGRADED
        return CustodyStatus.UNAVAILABLE

    def redundancy_factor(self) -> float:
        """Available / threshold. >1 = redundant, <1 = at risk."""
        if self.k_threshold == 0:
            return 0.0
        return self.available_custodians() / self.k_threshold

    def substrate_diversity(self) -> float:
        """Unique substrates / total custodians."""
        if not self.custodians:
            return 0.0
        substrates = set(c.substrate for c in self.custodians if c.online)
        return len(substrates) / max(1, self.available_custodians())

    def grade(self) -> tuple[str, str]:
        status = self.status()
        if status == CustodyStatus.EXPIRED:
            return "F", "EXPIRED"
        if status == CustodyStatus.UNAVAILABLE:
            return "F", "DISPUTE_DEADLOCK"
        
        rf = self.redundancy_factor()
        sd = self.substrate_diversity()
        score = rf * 0.6 + sd * 0.4
        
        if score >= 1.5:
            return "A", "WELL_CUSTODIED"
        if score >= 1.0:
            return "B", "ADEQUATE"
        if score >= 0.5:
            return "C", "AT_RISK"
        return "D", "FRAGILE"


def build_scenarios() -> list[tuple[str, TraceCustody]]:
    now = time.time()
    scenarios = []

    # 1. Well-custodied: 3 diverse custodians, k=2
    scenarios.append(("well_custodied", TraceCustody(
        trace_hash="abc123",
        custodians=[
            Custodian("ipfs_pin", "ipfs", True, now),
            Custodian("email_archive", "email", True, now),
            Custodian("isnad_anchor", "isnad", True, now),
        ],
        k_threshold=2, ttl_hours=168, created_at=now,
    )))

    # 2. Single custodian (common case — scoring agent holds trace)
    scenarios.append(("single_custodian", TraceCustody(
        trace_hash="def456",
        custodians=[
            Custodian("scoring_agent", "local", True, now),
        ],
        k_threshold=1, ttl_hours=168, created_at=now,
    )))

    # 3. Custodian offline during dispute
    scenarios.append(("offline_during_dispute", TraceCustody(
        trace_hash="ghi789",
        custodians=[
            Custodian("scoring_agent", "local", False, now - 86400),
            Custodian("backup_ipfs", "ipfs", True, now),
        ],
        k_threshold=2, ttl_hours=168, created_at=now,
    )))

    # 4. Expired TTL
    scenarios.append(("expired_ttl", TraceCustody(
        trace_hash="jkl012",
        custodians=[
            Custodian("ipfs_pin", "ipfs", True, now),
            Custodian("email_archive", "email", True, now),
        ],
        k_threshold=2, ttl_hours=168, created_at=now - 700000,  # >7 days ago
    )))

    # 5. Same substrate (correlated failure)
    scenarios.append(("same_substrate", TraceCustody(
        trace_hash="mno345",
        custodians=[
            Custodian("ipfs_pin_1", "ipfs", True, now),
            Custodian("ipfs_pin_2", "ipfs", True, now),
            Custodian("ipfs_pin_3", "ipfs", True, now),
        ],
        k_threshold=2, ttl_hours=168, created_at=now,
    )))

    return scenarios


def main():
    print("=" * 70)
    print("TRACE CUSTODY CHECKER")
    print("santaclawd: 'hash without data = unauditable'")
    print("=" * 70)

    print(f"\n{'Scenario':<25} {'Grade':<6} {'Status':<15} {'Avail':<6} {'Redun':<6} {'Diversity'}")
    print("-" * 70)

    for name, custody in build_scenarios():
        grade, diag = custody.grade()
        status = custody.status()
        avail = custody.available_custodians()
        rf = custody.redundancy_factor()
        sd = custody.substrate_diversity()
        print(f"{name:<25} {grade:<6} {diag:<15} {avail}/{len(custody.custodians):<4} {rf:<6.1f} {sd:<6.1%}")

    print("\n--- Trace Custody Spec ---")
    print("Minimum viable custody for dispute resolution:")
    print("  1. hash(trace) committed at settlement (v3)")
    print("  2. k-of-N custodians hold actual trace data")
    print("  3. TTL ≥ dispute_window (trace expires WITH the dispute right)")
    print("  4. Substrate diversity ≥ 2 (correlated failure protection)")
    print("  5. Custodian liveness: periodic proof-of-custody (hash challenge)")
    print()
    print("Cheapest tier: CID on IPFS + email self-archive + isnad anchor")
    print("= 3 substrates, k=2, zero marginal cost.")
    print()
    print("Data availability ≠ data permanence.")
    print("Traces should EXPIRE. Dispute window = trace TTL.")
    print("After TTL: hash remains (audit trail), data gone (privacy).")


if __name__ == "__main__":
    main()
