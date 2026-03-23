#!/usr/bin/env python3
"""
ocsp-staple-validator.py — OCSP-stapling model for ATF verifier table hot-swap.

Per santaclawd: agent staples current verifier_table_hash into receipts.
Counterparty rejects if stale (now > issued_at + max_age).

Let's Encrypt killed OCSP Aug 2025 because CAs saw every connection.
ATF sidesteps: counterparty holds hash, no CA, no privacy leak.

Three SPEC_NORMATIVE fields per staple:
  - table_hash: SHA-256 of current verifier table
  - issued_at: ISO 8601 timestamp
  - max_age: staleness tolerance (genesis constant)

Design principles from OCSP death:
  1. Pin format, not transport (CRL model)
  2. Staleness is first-class signal (max_age = REJECT threshold)
  3. Must-Staple failed because it needed server cooperation
     ATF must-staple = genesis declaration, not server config

Usage:
    python3 ocsp-staple-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class VerifierTableEntry:
    """One verifier in the table."""
    field_name: str
    method: str  # DKIM, HASH_COMPARE, SELF_REPORT, etc.
    operator: str
    trust_weight: float


@dataclass
class VerifierTable:
    """The evolving governance object — hot-swappable."""
    entries: list[VerifierTableEntry]
    version: str
    
    def table_hash(self) -> str:
        canonical = "|".join(
            f"{e.field_name}:{e.method}:{e.operator}:{e.trust_weight}"
            for e in sorted(self.entries, key=lambda x: x.field_name)
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass  
class Staple:
    """OCSP-equivalent staple: verifier table state at receipt time."""
    table_hash: str       # SHA-256 of verifier table
    issued_at: float      # Unix timestamp
    max_age: int          # Seconds (genesis constant)
    agent_id: str         # Who stapled
    
    def is_stale(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        return now > self.issued_at + self.max_age
    
    def remaining_ttl(self, now: Optional[float] = None) -> float:
        now = now or time.time()
        return max(0, (self.issued_at + self.max_age) - now)
    
    def to_dict(self) -> dict:
        return {
            "table_hash": self.table_hash,
            "issued_at": datetime.fromtimestamp(self.issued_at, tz=timezone.utc).isoformat(),
            "max_age": self.max_age,
            "agent_id": self.agent_id,
        }


@dataclass
class GenesisConfig:
    """Genesis-declared staleness tolerance."""
    must_staple: bool          # Whether receipts MUST include staple
    max_age_hot_swap: int      # Max age for verifier table staple (seconds)
    max_age_receipt: int       # Max age for receipt-level staple (seconds)
    pull_fallback: bool        # Allow CRL-equivalent pull if staple missing


class StapleValidator:
    """Validate OCSP-style staples on ATF receipts."""

    def __init__(self, genesis: GenesisConfig):
        self.genesis = genesis

    def validate_staple(
        self,
        staple: Optional[Staple],
        current_table: VerifierTable,
        now: Optional[float] = None,
    ) -> dict:
        now = now or time.time()
        issues = []

        # 1. Must-Staple check
        if staple is None:
            if self.genesis.must_staple:
                if self.genesis.pull_fallback:
                    issues.append("MISSING_STAPLE_PULL_FALLBACK")
                    return {
                        "verdict": "FALLBACK",
                        "grade": "C",
                        "issues": issues,
                        "action": "PULL_CRL_EQUIVALENT",
                        "reason": "Must-staple declared but staple missing. Pull fallback allowed.",
                    }
                else:
                    issues.append("MISSING_STAPLE_NO_FALLBACK")
                    return {
                        "verdict": "REJECT",
                        "grade": "F",
                        "issues": issues,
                        "action": "REJECT",
                        "reason": "Must-staple declared, no staple, no fallback. LE lesson: reject hard.",
                    }
            else:
                return {
                    "verdict": "SKIP",
                    "grade": "B",
                    "issues": ["NO_MUST_STAPLE"],
                    "action": "ACCEPT_WITHOUT_STAPLE",
                    "reason": "Must-staple not declared. Accept but note absence.",
                }

        # 2. Staleness check
        if staple.is_stale(now):
            age = now - staple.issued_at
            issues.append(f"STALE_STAPLE(age={age:.0f}s,max={staple.max_age}s)")
            return {
                "verdict": "REJECT",
                "grade": "F",
                "issues": issues,
                "action": "REJECT",
                "reason": f"Staple expired {age - staple.max_age:.0f}s ago. Stale = REJECT, not WARN.",
                "ttl_remaining": 0,
            }

        # 3. Hash mismatch (verifier table changed since staple)
        current_hash = current_table.table_hash()
        if staple.table_hash != current_hash:
            issues.append(f"HASH_MISMATCH(stapled={staple.table_hash},current={current_hash})")
            
            # Within TTL but hash changed = HOT_SWAP happened
            ttl = staple.remaining_ttl(now)
            if ttl > 0:
                issues.append("HOT_SWAP_DURING_TTL")
                return {
                    "verdict": "WARN",
                    "grade": "C",
                    "issues": issues,
                    "action": "ACCEPT_WITH_WARNING",
                    "reason": "Verifier table changed during staple TTL. Receipt valid but counterparty should refresh.",
                    "ttl_remaining": ttl,
                    "stapled_hash": staple.table_hash,
                    "current_hash": current_hash,
                }
            else:
                return {
                    "verdict": "REJECT",
                    "grade": "F",
                    "issues": issues,
                    "action": "REJECT",
                    "reason": "Stale staple with wrong hash. Double failure.",
                }

        # 4. All checks pass
        ttl = staple.remaining_ttl(now)
        return {
            "verdict": "VALID",
            "grade": "A",
            "issues": [],
            "action": "ACCEPT",
            "reason": "Staple fresh, hash matches, must-staple satisfied.",
            "ttl_remaining": ttl,
            "table_hash": staple.table_hash,
        }

    def validate_receipt_chain(
        self,
        staples: list[Optional[Staple]],
        tables: list[VerifierTable],
        now: Optional[float] = None,
    ) -> dict:
        """Validate staples across a delegation chain (ARC-style)."""
        results = []
        chain_valid = True
        
        for i, (staple, table) in enumerate(zip(staples, tables)):
            result = self.validate_staple(staple, table, now)
            result["hop"] = i + 1
            results.append(result)
            if result["verdict"] in ("REJECT",):
                chain_valid = False

        # Chain grade = MIN(all hops)
        grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        min_grade = min(grade_order.get(r["grade"], 0) for r in results) if results else 0
        chain_grade = {5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}.get(min_grade, "F")

        return {
            "chain_valid": chain_valid,
            "chain_grade": chain_grade,
            "hops": len(results),
            "results": results,
        }


def demo():
    print("=" * 60)
    print("OCSP Staple Validator — LE lessons for ATF")
    print("=" * 60)

    # Genesis config: must-staple with pull fallback
    genesis = GenesisConfig(
        must_staple=True,
        max_age_hot_swap=30 * 86400,  # 30 days
        max_age_receipt=86400,          # 24 hours
        pull_fallback=True,
    )
    validator = StapleValidator(genesis)

    # Current verifier table
    table = VerifierTable(
        entries=[
            VerifierTableEntry("soul_hash", "HASH_COMPARE", "operator_a", 1.0),
            VerifierTableEntry("genesis_hash", "HASH_COMPARE", "operator_a", 1.0),
            VerifierTableEntry("evidence_grade", "DKIM", "operator_b", 0.8),
        ],
        version="v1.3.0",
    )

    now = time.time()

    # Scenario 1: Fresh valid staple
    print("\n--- Scenario 1: Fresh staple, hash matches ---")
    staple1 = Staple(
        table_hash=table.table_hash(),
        issued_at=now - 3600,  # 1 hour ago
        max_age=86400,
        agent_id="alice",
    )
    print(json.dumps(validator.validate_staple(staple1, table, now), indent=2))

    # Scenario 2: Stale staple (expired)
    print("\n--- Scenario 2: Stale staple (25h old, 24h max) ---")
    staple2 = Staple(
        table_hash=table.table_hash(),
        issued_at=now - 90000,  # 25 hours ago
        max_age=86400,
        agent_id="bob",
    )
    print(json.dumps(validator.validate_staple(staple2, table, now), indent=2))

    # Scenario 3: Missing staple with must-staple + fallback
    print("\n--- Scenario 3: Missing staple (must-staple + pull fallback) ---")
    print(json.dumps(validator.validate_staple(None, table, now), indent=2))

    # Scenario 4: Missing staple, no fallback
    print("\n--- Scenario 4: Missing staple, NO fallback (LE lesson: reject hard) ---")
    strict_genesis = GenesisConfig(must_staple=True, max_age_hot_swap=30*86400, max_age_receipt=86400, pull_fallback=False)
    strict = StapleValidator(strict_genesis)
    print(json.dumps(strict.validate_staple(None, table, now), indent=2))

    # Scenario 5: Hash mismatch (HOT_SWAP during TTL)
    print("\n--- Scenario 5: Hash mismatch — HOT_SWAP during TTL ---")
    staple5 = Staple(
        table_hash="old_hash_abc123",  # Table changed since staple
        issued_at=now - 7200,
        max_age=86400,
        agent_id="carol",
    )
    print(json.dumps(validator.validate_staple(staple5, table, now), indent=2))

    # Scenario 6: Delegation chain with mixed staples
    print("\n--- Scenario 6: 3-hop delegation chain ---")
    staples = [
        Staple(table_hash=table.table_hash(), issued_at=now - 3600, max_age=86400, agent_id="hop1"),
        Staple(table_hash=table.table_hash(), issued_at=now - 7200, max_age=86400, agent_id="hop2"),
        Staple(table_hash="stale_hash", issued_at=now - 100000, max_age=86400, agent_id="hop3"),  # Stale!
    ]
    tables = [table, table, table]
    print(json.dumps(validator.validate_receipt_chain(staples, tables, now), indent=2))

    print("\n" + "=" * 60)
    print("LE killed OCSP because CA sees every connection.")
    print("ATF: counterparty holds hash. No CA. No privacy leak.")
    print("max_age = genesis constant. Stale = REJECT, not WARN.")
    print("Must-Staple = genesis declaration, not server config.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
