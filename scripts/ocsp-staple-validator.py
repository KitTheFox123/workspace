#!/usr/bin/env python3
"""
ocsp-staple-validator.py — OCSP-stapling model for ATF trust freshness.

Per Let's Encrypt killing OCSP (July 2024): phone-home = privacy leak.
ATF solution: agent staples current verifier_table_hash to every receipt.
Counterparty rejects if stale. No central oracle needed.

Two TTLs (per santaclawd):
  - HOT_SWAP max_age: 30d (verifier methods evolve monthly)
  - Receipt max_age: 24h (TOCTOU window for trust state)

Must-staple: genesis field declaring staleness tolerance.

Usage:
    python3 ocsp-staple-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class StaleVerdict(Enum):
    FRESH = "FRESH"
    AGING = "AGING"          # >50% of max_age
    STALE = "STALE"          # past max_age
    MISSING = "MISSING"      # no staple present
    HASH_MISMATCH = "HASH_MISMATCH"  # staple hash != current table


# ATF-core constants (from atf-constants.py)
HOT_SWAP_MAX_AGE = 30 * 86400    # 30 days in seconds
RECEIPT_MAX_AGE = 24 * 3600      # 24 hours in seconds
AGING_THRESHOLD = 0.5             # warn at 50% of max_age


@dataclass
class GenesisDeclaration:
    """Agent's genesis with must-staple field."""
    agent_id: str
    genesis_hash: str
    must_staple: bool              # like TLS must-staple extension
    hot_swap_max_age: int = HOT_SWAP_MAX_AGE
    receipt_max_age: int = RECEIPT_MAX_AGE


@dataclass
class VerifierTableStaple:
    """Stapled to every receipt — current verifier table state."""
    table_hash: str                # SHA-256 of current verifier table
    issued_at: float               # when this staple was created
    max_age: int                   # TTL in seconds
    agent_id: str                  # who issued the staple

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.max_age

    @property
    def age(self) -> float:
        return time.time() - self.issued_at

    @property
    def remaining(self) -> float:
        return max(0, self.expires_at - time.time())


@dataclass
class Receipt:
    """ATF receipt with optional staple."""
    task_hash: str
    deliverable_hash: str
    evidence_grade: str
    agent_id: str
    timestamp: float = field(default_factory=time.time)
    staple: Optional[VerifierTableStaple] = None


class OCSPStapleValidator:
    """Validate ATF receipt staples — OCSP model without the privacy leak."""

    def __init__(self, current_table_hash: str):
        self.current_table_hash = current_table_hash

    def validate_staple(
        self,
        receipt: Receipt,
        genesis: GenesisDeclaration,
    ) -> dict:
        """Validate a receipt's staple against genesis requirements."""

        # No staple present
        if receipt.staple is None:
            if genesis.must_staple:
                return {
                    "verdict": StaleVerdict.MISSING.value,
                    "action": "REJECT",
                    "reason": "must-staple declared in genesis but no staple present",
                    "privacy_model": "NO_PHONE_HOME",
                }
            return {
                "verdict": StaleVerdict.MISSING.value,
                "action": "WARN",
                "reason": "no staple, but must-staple not required",
                "privacy_model": "NO_PHONE_HOME",
            }

        staple = receipt.staple
        now = time.time()

        # Hash mismatch — verifier table changed
        if staple.table_hash != self.current_table_hash:
            return {
                "verdict": StaleVerdict.HASH_MISMATCH.value,
                "action": "REJECT",
                "reason": f"staple hash {staple.table_hash[:12]}... != current {self.current_table_hash[:12]}...",
                "stale_by": "N/A (hash mismatch)",
                "privacy_model": "NO_PHONE_HOME",
                "le_parallel": "CRL supersedes — stapled status is outdated",
            }

        # Check TTL
        age = now - staple.issued_at
        max_age = staple.max_age

        if age > max_age:
            return {
                "verdict": StaleVerdict.STALE.value,
                "action": "REJECT",
                "reason": f"staple expired: age={age:.0f}s > max_age={max_age}s",
                "expired_by": f"{age - max_age:.0f}s",
                "privacy_model": "NO_PHONE_HOME",
                "le_parallel": "OCSP response expired — LE would soft-fail, ATF hard-rejects",
            }

        if age > max_age * AGING_THRESHOLD:
            return {
                "verdict": StaleVerdict.AGING.value,
                "action": "ACCEPT_WITH_WARNING",
                "reason": f"staple aging: {age/max_age*100:.0f}% of max_age consumed",
                "remaining": f"{max_age - age:.0f}s",
                "privacy_model": "NO_PHONE_HOME",
            }

        return {
            "verdict": StaleVerdict.FRESH.value,
            "action": "ACCEPT",
            "reason": f"staple fresh: {age/max_age*100:.1f}% of max_age consumed",
            "remaining": f"{max_age - age:.0f}s",
            "privacy_model": "NO_PHONE_HOME",
            "le_parallel": "OCSP staple valid — no CA contact needed",
        }

    def validate_receipt_chain(
        self,
        receipts: list[Receipt],
        genesis: GenesisDeclaration,
    ) -> dict:
        """Validate a chain of receipts for staple freshness."""
        results = []
        for r in receipts:
            result = self.validate_staple(r, genesis)
            result["receipt_task"] = r.task_hash
            result["agent"] = r.agent_id
            results.append(result)

        verdicts = [r["verdict"] for r in results]
        rejected = sum(1 for v in verdicts if v in ("STALE", "HASH_MISMATCH", "MISSING") and genesis.must_staple)
        
        chain_verdict = "CHAIN_VALID" if rejected == 0 else "CHAIN_BROKEN"
        
        return {
            "chain_verdict": chain_verdict,
            "total_receipts": len(receipts),
            "fresh": sum(1 for v in verdicts if v == "FRESH"),
            "aging": sum(1 for v in verdicts if v == "AGING"),
            "stale": sum(1 for v in verdicts if v == "STALE"),
            "missing": sum(1 for v in verdicts if v == "MISSING"),
            "hash_mismatch": sum(1 for v in verdicts if v == "HASH_MISMATCH"),
            "rejected": rejected,
            "privacy_model": "NO_PHONE_HOME — all validation local",
            "receipts": results,
        }


def demo():
    print("=" * 60)
    print("OCSP Staple Validator — LE lesson applied to ATF")
    print("=" * 60)

    current_hash = hashlib.sha256(b"verifier_table_v3").hexdigest()[:16]
    validator = OCSPStapleValidator(current_hash)

    genesis = GenesisDeclaration(
        agent_id="kit_fox",
        genesis_hash="abc123",
        must_staple=True,
        hot_swap_max_age=HOT_SWAP_MAX_AGE,
        receipt_max_age=RECEIPT_MAX_AGE,
    )

    now = time.time()

    # Scenario 1: Fresh staple
    print("\n--- Scenario 1: Fresh receipt (2 hours old) ---")
    r1 = Receipt(
        task_hash="task001", deliverable_hash="del001",
        evidence_grade="A", agent_id="alice",
        staple=VerifierTableStaple(
            table_hash=current_hash, issued_at=now - 7200,
            max_age=RECEIPT_MAX_AGE, agent_id="alice",
        ),
    )
    print(json.dumps(validator.validate_staple(r1, genesis), indent=2))

    # Scenario 2: Aging staple (14 hours)
    print("\n--- Scenario 2: Aging receipt (14 hours old) ---")
    r2 = Receipt(
        task_hash="task002", deliverable_hash="del002",
        evidence_grade="B", agent_id="bob",
        staple=VerifierTableStaple(
            table_hash=current_hash, issued_at=now - 50400,
            max_age=RECEIPT_MAX_AGE, agent_id="bob",
        ),
    )
    print(json.dumps(validator.validate_staple(r2, genesis), indent=2))

    # Scenario 3: Stale staple (36 hours)
    print("\n--- Scenario 3: Stale receipt (36 hours — past max_age) ---")
    r3 = Receipt(
        task_hash="task003", deliverable_hash="del003",
        evidence_grade="B", agent_id="carol",
        staple=VerifierTableStaple(
            table_hash=current_hash, issued_at=now - 129600,
            max_age=RECEIPT_MAX_AGE, agent_id="carol",
        ),
    )
    print(json.dumps(validator.validate_staple(r3, genesis), indent=2))

    # Scenario 4: Hash mismatch (table changed)
    print("\n--- Scenario 4: Hash mismatch (verifier table updated) ---")
    old_hash = hashlib.sha256(b"verifier_table_v2").hexdigest()[:16]
    r4 = Receipt(
        task_hash="task004", deliverable_hash="del004",
        evidence_grade="A", agent_id="dave",
        staple=VerifierTableStaple(
            table_hash=old_hash, issued_at=now - 3600,
            max_age=RECEIPT_MAX_AGE, agent_id="dave",
        ),
    )
    print(json.dumps(validator.validate_staple(r4, genesis), indent=2))

    # Scenario 5: Missing staple with must-staple
    print("\n--- Scenario 5: Missing staple (must-staple = true) ---")
    r5 = Receipt(
        task_hash="task005", deliverable_hash="del005",
        evidence_grade="C", agent_id="eve",
    )
    print(json.dumps(validator.validate_staple(r5, genesis), indent=2))

    # Scenario 6: HOT_SWAP TTL (30 day verifier table)
    print("\n--- Scenario 6: HOT_SWAP staple (20 days old, 30d max) ---")
    r6 = Receipt(
        task_hash="task006", deliverable_hash="del006",
        evidence_grade="A", agent_id="frank",
        staple=VerifierTableStaple(
            table_hash=current_hash, issued_at=now - 20 * 86400,
            max_age=HOT_SWAP_MAX_AGE, agent_id="frank",
        ),
    )
    print(json.dumps(validator.validate_staple(r6, genesis), indent=2))

    print("\n" + "=" * 60)
    print("LE killed OCSP: CA sees every connection = privacy leak.")
    print("ATF staples: agent carries own trust state. No phone-home.")
    print("Two TTLs: HOT_SWAP=30d (methods), receipt=24h (TOCTOU).")
    print("must-staple in genesis = hard-reject if missing.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
