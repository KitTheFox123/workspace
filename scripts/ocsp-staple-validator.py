#!/usr/bin/env python3
"""
ocsp-staple-validator.py — OCSP-stapling model for ATF verifier table updates.

Per Let's Encrypt OCSP deprecation (Aug 2025): privacy killed push-only.
ATF stapling model: agent staples current verifier_table_hash into receipts.
Counterparty validates locally. No oracle phone-home.

Three SPEC_NORMATIVE fields per staple:
  - table_hash: SHA-256 of current verifier table
  - issued_at: ISO 8601 timestamp
  - max_age: staleness tolerance (genesis constant)

Reject if: stale (now > issued_at + max_age) OR hash mismatch.

Usage:
    python3 ocsp-staple-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


# ATF Constants (from atf-constants.py)
SPEC_FLOOR_MAX_AGE_HOURS = 24       # Minimum: OCSP equivalent
SPEC_RECOMMENDED_MAX_AGE_DAYS = 30  # HOT_SWAP window
SPEC_CEILING_MAX_AGE_DAYS = 90      # Beyond this = stale by definition


@dataclass
class VerifierTable:
    """Current verifier table state."""
    fields: dict  # field_name -> verifier config
    version: str
    updated_at: float = field(default_factory=time.time)

    def hash(self) -> str:
        canonical = json.dumps(self.fields, sort_keys=True) + f"|v={self.version}"
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class Staple:
    """OCSP-stapling equivalent: verifier table state pinned to a receipt."""
    table_hash: str        # SHA-256 (truncated)
    issued_at: str         # ISO 8601
    max_age_seconds: int   # staleness tolerance
    issuer_agent: str      # who issued this staple

    @property
    def issued_timestamp(self) -> float:
        return datetime.fromisoformat(self.issued_at).timestamp()

    @property
    def expires_at(self) -> float:
        return self.issued_timestamp + self.max_age_seconds

    def is_stale(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        return now > self.expires_at


@dataclass
class StapleValidation:
    """Result of validating a staple against current state."""
    valid: bool
    verdict: str  # FRESH, STALE, HASH_MISMATCH, BELOW_FLOOR, ABOVE_CEILING
    details: dict


class OCSPStapleValidator:
    """Validate ATF verifier table staples — OCSP model without the privacy leak."""

    def __init__(self, genesis_max_age_days: int = 30):
        self.genesis_max_age = genesis_max_age_days
        self.known_tables: dict[str, VerifierTable] = {}

    def register_table(self, agent_id: str, table: VerifierTable):
        self.known_tables[agent_id] = table

    def create_staple(self, agent_id: str, table: VerifierTable) -> Staple:
        """Agent creates a staple to include in receipts."""
        return Staple(
            table_hash=table.hash(),
            issued_at=datetime.now(timezone.utc).isoformat(),
            max_age_seconds=self.genesis_max_age * 86400,
            issuer_agent=agent_id,
        )

    def validate_staple(
        self,
        staple: Staple,
        counterparty_table: Optional[VerifierTable] = None,
        now: Optional[float] = None,
    ) -> StapleValidation:
        """Counterparty validates a received staple."""
        now = now or time.time()
        issues = []

        # 1. Check max_age bounds
        max_age_hours = staple.max_age_seconds / 3600
        max_age_days = staple.max_age_seconds / 86400

        if max_age_hours < SPEC_FLOOR_MAX_AGE_HOURS:
            issues.append("BELOW_FLOOR")

        if max_age_days > SPEC_CEILING_MAX_AGE_DAYS:
            issues.append("ABOVE_CEILING")

        # 2. Check staleness
        stale = staple.is_stale(now)
        if stale:
            age_hours = (now - staple.issued_timestamp) / 3600
            issues.append(f"STALE ({age_hours:.1f}h old, max {max_age_hours:.0f}h)")

        # 3. Check hash against known table (if available)
        hash_match = None
        if counterparty_table:
            expected_hash = counterparty_table.hash()
            hash_match = staple.table_hash == expected_hash
            if not hash_match:
                issues.append(f"HASH_MISMATCH (got {staple.table_hash}, expected {expected_hash})")

        # 4. Verdict
        if not issues:
            verdict = "FRESH"
            valid = True
        elif stale and not hash_match:
            verdict = "STALE_AND_MISMATCHED"
            valid = False
        elif stale:
            verdict = "STALE"
            valid = False
        elif hash_match is False:
            verdict = "HASH_MISMATCH"
            valid = False
        elif "ABOVE_CEILING" in issues:
            verdict = "ABOVE_CEILING"
            valid = False
        elif "BELOW_FLOOR" in issues:
            verdict = "BELOW_FLOOR"
            valid = False
        else:
            verdict = "DEGRADED"
            valid = False

        remaining = max(0, staple.expires_at - now)

        return StapleValidation(
            valid=valid,
            verdict=verdict,
            details={
                "table_hash": staple.table_hash,
                "issued_at": staple.issued_at,
                "max_age_days": max_age_days,
                "stale": stale,
                "hash_match": hash_match,
                "remaining_hours": remaining / 3600,
                "issues": issues,
                "privacy_model": "pull_only",  # No CA phone-home
            },
        )

    def validate_receipt_chain(
        self,
        staples: list[Staple],
        now: Optional[float] = None,
    ) -> dict:
        """Validate a chain of staples (delegation scenario)."""
        now = now or time.time()
        results = []
        chain_valid = True

        for i, staple in enumerate(staples):
            table = self.known_tables.get(staple.issuer_agent)
            result = self.validate_staple(staple, table, now)
            results.append({
                "hop": i + 1,
                "agent": staple.issuer_agent,
                "verdict": result.verdict,
                "valid": result.valid,
            })
            if not result.valid:
                chain_valid = False

        return {
            "chain_valid": chain_valid,
            "hops": len(staples),
            "results": results,
            "privacy_model": "no_intermediary",
        }


def demo():
    print("=" * 60)
    print("OCSP Staple Validator — LE lesson applied to ATF")
    print("=" * 60)

    validator = OCSPStapleValidator(genesis_max_age_days=30)

    # Create a verifier table
    table_v1 = VerifierTable(
        fields={
            "soul_hash": {"method": "SHA-256", "verifier": "counterparty"},
            "genesis_hash": {"method": "SHA-256", "verifier": "counterparty"},
            "evidence_grade": {"method": "receipt_chain", "verifier": "oracle"},
        },
        version="1.0.0",
    )
    validator.register_table("alice", table_v1)

    # Scenario 1: Fresh staple
    print("\n--- Scenario 1: Fresh staple (valid) ---")
    staple1 = validator.create_staple("alice", table_v1)
    result1 = validator.validate_staple(staple1, table_v1)
    print(json.dumps({"verdict": result1.verdict, "valid": result1.valid, **result1.details}, indent=2, default=str))

    # Scenario 2: Stale staple (45 days old)
    print("\n--- Scenario 2: Stale staple (45 days old) ---")
    staple2 = Staple(
        table_hash=table_v1.hash(),
        issued_at=(datetime.now(timezone.utc) - timedelta(days=45)).isoformat(),
        max_age_seconds=30 * 86400,
        issuer_agent="alice",
    )
    result2 = validator.validate_staple(staple2, table_v1)
    print(json.dumps({"verdict": result2.verdict, "valid": result2.valid, "issues": result2.details["issues"]}, indent=2))

    # Scenario 3: Hash mismatch (table updated but staple is old)
    print("\n--- Scenario 3: Hash mismatch (table evolved) ---")
    table_v2 = VerifierTable(
        fields={
            "soul_hash": {"method": "SHA-256", "verifier": "counterparty"},
            "genesis_hash": {"method": "SHA-256", "verifier": "counterparty"},
            "evidence_grade": {"method": "receipt_chain", "verifier": "oracle"},
            "grader_id": {"method": "genesis_anchor", "verifier": "counterparty"},  # NEW
        },
        version="1.1.0",
    )
    staple3 = Staple(
        table_hash=table_v1.hash(),  # Old hash
        issued_at=datetime.now(timezone.utc).isoformat(),
        max_age_seconds=30 * 86400,
        issuer_agent="alice",
    )
    result3 = validator.validate_staple(staple3, table_v2)  # Validate against new table
    print(json.dumps({"verdict": result3.verdict, "valid": result3.valid, "issues": result3.details["issues"]}, indent=2))

    # Scenario 4: Below floor (1 hour max_age)
    print("\n--- Scenario 4: Below SPEC_FLOOR (1h max_age) ---")
    staple4 = Staple(
        table_hash=table_v1.hash(),
        issued_at=datetime.now(timezone.utc).isoformat(),
        max_age_seconds=3600,  # 1 hour — below 24h floor
        issuer_agent="alice",
    )
    result4 = validator.validate_staple(staple4, table_v1)
    print(json.dumps({"verdict": result4.verdict, "valid": result4.valid, "issues": result4.details["issues"]}, indent=2))

    # Scenario 5: Delegation chain
    print("\n--- Scenario 5: 3-hop delegation chain ---")
    table_bob = VerifierTable(fields={"soul_hash": {"method": "SHA-256"}}, version="1.0.0")
    table_carol = VerifierTable(fields={"soul_hash": {"method": "SHA-256"}}, version="1.0.0")
    validator.register_table("bob", table_bob)
    validator.register_table("carol", table_carol)

    chain = [
        validator.create_staple("alice", table_v1),
        validator.create_staple("bob", table_bob),
        validator.create_staple("carol", table_carol),
    ]
    chain_result = validator.validate_receipt_chain(chain)
    print(json.dumps(chain_result, indent=2, default=str))

    print("\n" + "=" * 60)
    print("LE lesson: privacy beats freshness. No CA in the loop.")
    print("Staple = fast path. CRL-equivalent query = fallback.")
    print("Pin format (SHA-256 + ISO 8601), keep transport composable.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
