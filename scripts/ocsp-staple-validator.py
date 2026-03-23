#!/usr/bin/env python3
"""
ocsp-staple-validator.py — OCSP-style staple validation for ATF receipts.

Per santaclawd: ATF HOT_SWAP receipt staple needs 3 SPEC_NORMATIVE fields:
  - table_hash: SHA-256 of current verifier table
  - issued_at: ISO 8601 timestamp
  - max_age: staleness tolerance (genesis constant, default 30d)

Let's Encrypt killed OCSP Aug 2025 because CA saw every connection.
ATF sidesteps: counterparty holds the hash, no CA, no privacy leak.

Key insight: must-staple as genesis field = parties declare staleness
tolerance upfront. Stale staple = REJECT + force pull.

Usage:
    python3 ocsp-staple-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class VerifierTable:
    """The hot-swap verifier table — evolves independently of field registry."""
    version: str
    verifiers: dict[str, dict]  # name -> {method, operator, trust_weight}
    updated_at: float = field(default_factory=time.time)

    def compute_hash(self) -> str:
        canonical = json.dumps(self.verifiers, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class Staple:
    """OCSP-style staple attached to ATF receipts."""
    table_hash: str       # SHA-256 of verifier table at staple time
    issued_at: str        # ISO 8601
    max_age_seconds: int  # staleness tolerance (genesis constant)
    issuer_agent_id: str  # who created this staple
    table_version: str    # verifier table version for debugging

    def is_stale(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        issued = datetime.fromisoformat(self.issued_at)
        return (now - issued).total_seconds() > self.max_age_seconds

    def age_seconds(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        issued = datetime.fromisoformat(self.issued_at)
        return (now - issued).total_seconds()


@dataclass
class GenesisConfig:
    """Genesis-declared staleness tolerance and must-staple flag."""
    max_age_seconds: int = 30 * 24 * 3600  # 30d default
    must_staple: bool = True  # if True, missing staple = REJECT
    agent_id: str = ""


class StapleValidator:
    """Validate OCSP-style staples on ATF receipts."""

    VERDICTS = {
        "VALID": "Staple fresh, hash matches current table",
        "STALE": "Staple expired (age > max_age)",
        "HASH_MISMATCH": "Staple hash doesn't match current verifier table",
        "MISSING_REQUIRED": "must-staple declared but no staple provided",
        "MISSING_OPTIONAL": "No staple, but must-staple not declared",
        "FUTURE_DATED": "Staple issued_at is in the future",
        "STALE_HASH_MISMATCH": "Both stale AND hash mismatch (worst case)",
    }

    def validate(
        self,
        staple: Optional[Staple],
        current_table: VerifierTable,
        genesis: GenesisConfig,
        now: Optional[datetime] = None,
    ) -> dict:
        now = now or datetime.now(timezone.utc)

        # No staple provided
        if staple is None:
            if genesis.must_staple:
                return self._result("MISSING_REQUIRED", "F", genesis, now=now)
            return self._result("MISSING_OPTIONAL", "D", genesis, now=now,
                                note="Staple absent but not required. DEGRADED trust.")

        # Future-dated staple
        issued = datetime.fromisoformat(staple.issued_at)
        if issued > now:
            return self._result("FUTURE_DATED", "F", genesis, staple=staple, now=now,
                                note="Clock skew or manipulation")

        # Check staleness
        stale = staple.is_stale(now)
        age = staple.age_seconds(now)

        # Check hash match
        current_hash = current_table.compute_hash()
        hash_match = staple.table_hash == current_hash

        if stale and not hash_match:
            return self._result("STALE_HASH_MISMATCH", "F", genesis, staple=staple,
                                now=now, age=age, expected_hash=current_hash)
        if stale:
            return self._result("STALE", "D", genesis, staple=staple,
                                now=now, age=age, expected_hash=current_hash,
                                note=f"Expired {age - staple.max_age_seconds:.0f}s ago")
        if not hash_match:
            return self._result("HASH_MISMATCH", "D", genesis, staple=staple,
                                now=now, age=age, expected_hash=current_hash,
                                note="Table updated since staple issued. HOT_SWAP in progress?")

        # All good
        remaining = staple.max_age_seconds - age
        grade = "A" if remaining > staple.max_age_seconds * 0.5 else "B"
        return self._result("VALID", grade, genesis, staple=staple,
                            now=now, age=age, expected_hash=current_hash,
                            note=f"{remaining:.0f}s remaining before staleness")

    def _result(self, verdict, grade, genesis, staple=None, now=None,
                age=None, expected_hash=None, note=None):
        r = {
            "verdict": verdict,
            "grade": grade,
            "description": self.VERDICTS[verdict],
            "must_staple": genesis.must_staple,
            "max_age_seconds": genesis.max_age_seconds,
        }
        if staple:
            r["staple"] = {
                "table_hash": staple.table_hash,
                "issued_at": staple.issued_at,
                "issuer": staple.issuer_agent_id,
                "table_version": staple.table_version,
            }
            if age is not None:
                r["age_seconds"] = round(age, 1)
                r["age_human"] = f"{age/3600:.1f}h" if age < 86400 else f"{age/86400:.1f}d"
        if expected_hash:
            r["current_table_hash"] = expected_hash
            r["hash_match"] = staple.table_hash == expected_hash if staple else False
        if note:
            r["note"] = note
        return r


def demo():
    print("=" * 60)
    print("OCSP Staple Validator for ATF — LE killed OCSP Aug 2025")
    print("=" * 60)

    validator = StapleValidator()
    now = datetime.now(timezone.utc)

    # Current verifier table
    table = VerifierTable(
        version="v3.1.0",
        verifiers={
            "dkim_check": {"method": "dns_txt", "operator": "dns", "trust_weight": 1.0},
            "genesis_verify": {"method": "hash_compare", "operator": "counterparty", "trust_weight": 0.9},
            "behavior_audit": {"method": "receipt_analysis", "operator": "independent", "trust_weight": 0.8},
        }
    )

    genesis = GenesisConfig(
        max_age_seconds=30 * 24 * 3600,  # 30d
        must_staple=True,
        agent_id="kit_fox",
    )

    # Scenario 1: Fresh valid staple
    print("\n--- Scenario 1: Fresh valid staple ---")
    staple1 = Staple(
        table_hash=table.compute_hash(),
        issued_at=(now - timedelta(hours=2)).isoformat(),
        max_age_seconds=30 * 24 * 3600,
        issuer_agent_id="kit_fox",
        table_version="v3.1.0",
    )
    print(json.dumps(validator.validate(staple1, table, genesis, now), indent=2))

    # Scenario 2: Stale staple (35 days old)
    print("\n--- Scenario 2: Stale staple (35 days old) ---")
    staple2 = Staple(
        table_hash=table.compute_hash(),
        issued_at=(now - timedelta(days=35)).isoformat(),
        max_age_seconds=30 * 24 * 3600,
        issuer_agent_id="kit_fox",
        table_version="v3.0.0",
    )
    print(json.dumps(validator.validate(staple2, table, genesis, now), indent=2))

    # Scenario 3: Hash mismatch (table updated since staple)
    print("\n--- Scenario 3: Hash mismatch (HOT_SWAP in progress) ---")
    staple3 = Staple(
        table_hash="old_hash_abcdef",
        issued_at=(now - timedelta(hours=6)).isoformat(),
        max_age_seconds=30 * 24 * 3600,
        issuer_agent_id="kit_fox",
        table_version="v3.0.0",
    )
    print(json.dumps(validator.validate(staple3, table, genesis, now), indent=2))

    # Scenario 4: Missing staple with must-staple
    print("\n--- Scenario 4: Missing staple (must-staple = true) ---")
    print(json.dumps(validator.validate(None, table, genesis, now), indent=2))

    # Scenario 5: Missing staple without must-staple
    print("\n--- Scenario 5: Missing staple (must-staple = false) ---")
    genesis_optional = GenesisConfig(must_staple=False, agent_id="relaxed_agent")
    print(json.dumps(validator.validate(None, table, genesis_optional, now), indent=2))

    # Scenario 6: Future-dated staple (clock skew or manipulation)
    print("\n--- Scenario 6: Future-dated staple ---")
    staple6 = Staple(
        table_hash=table.compute_hash(),
        issued_at=(now + timedelta(hours=2)).isoformat(),
        max_age_seconds=30 * 24 * 3600,
        issuer_agent_id="attacker",
        table_version="v3.1.0",
    )
    print(json.dumps(validator.validate(staple6, table, genesis, now), indent=2))

    # Scenario 7: Stale AND hash mismatch (worst case)
    print("\n--- Scenario 7: Stale + hash mismatch (worst case) ---")
    staple7 = Staple(
        table_hash="very_old_hash",
        issued_at=(now - timedelta(days=45)).isoformat(),
        max_age_seconds=30 * 24 * 3600,
        issuer_agent_id="compromised_agent",
        table_version="v2.0.0",
    )
    print(json.dumps(validator.validate(staple7, table, genesis, now), indent=2))

    print("\n" + "=" * 60)
    print("LE killed OCSP because CA saw every connection.")
    print("ATF: counterparty holds hash. No CA. No privacy leak.")
    print("max_age = genesis constant (30d). must-staple = genesis field.")
    print("Stale staple = REJECT + force pull. No silent degradation.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
