#!/usr/bin/env python3
"""
grace-period-enforcer.py — ATF grace period for stale trust staples.

Per bro_agent: genesis declares max_age + grace_period at issuance.
  - Fresh: age < max_age → ACCEPT
  - Grace: max_age < age < max_age + grace_period → DEGRADED_GRADE
  - Expired: age > max_age + grace_period → REJECT

LE parallel: OCSP responses had nextUpdate field. Problem: responders
cached stale responses beyond nextUpdate. ATF fix: delivery_hash
timestamps the enforcement boundary immutably.

Usage:
    python3 grace-period-enforcer.py
"""

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum


class FreshnessVerdict(Enum):
    FRESH = "FRESH"
    GRACE = "GRACE_PERIOD"
    EXPIRED = "EXPIRED"
    MISSING_STAPLE = "MISSING_STAPLE"
    HASH_MISMATCH = "HASH_MISMATCH"


@dataclass
class GenesisPolicy:
    """Trust freshness policy declared at genesis."""
    agent_id: str
    max_age_seconds: int          # primary TTL
    grace_period_seconds: int     # degraded-but-not-rejected window
    must_staple: bool
    genesis_hash: str

    @property
    def total_window(self) -> int:
        return self.max_age_seconds + self.grace_period_seconds


@dataclass
class TrustStaple:
    """Stapled trust state on a receipt."""
    table_hash: str
    issued_at: float
    delivery_hash: str    # immutable timestamp anchor (bro_agent)
    agent_id: str


class GracePeriodEnforcer:
    """Enforce ATF trust freshness with grace period degradation."""

    def __init__(self, current_table_hash: str):
        self.current_hash = current_table_hash

    def enforce(self, staple: TrustStaple | None, policy: GenesisPolicy, now: float = None) -> dict:
        now = now or time.time()

        if staple is None:
            return {
                "verdict": FreshnessVerdict.MISSING_STAPLE.value,
                "action": "REJECT" if policy.must_staple else "WARN",
                "grade_modifier": -2 if policy.must_staple else -1,
                "reason": "no staple attached to receipt",
            }

        # Hash check first — table may have changed
        if staple.table_hash != self.current_hash:
            return {
                "verdict": FreshnessVerdict.HASH_MISMATCH.value,
                "action": "REJECT",
                "grade_modifier": -3,
                "reason": f"table_hash mismatch: {staple.table_hash[:12]} != {self.current_hash[:12]}",
                "le_parallel": "CRL supersedes stale OCSP response",
            }

        age = now - staple.issued_at

        if age <= policy.max_age_seconds:
            pct = age / policy.max_age_seconds * 100
            return {
                "verdict": FreshnessVerdict.FRESH.value,
                "action": "ACCEPT",
                "grade_modifier": 0,
                "age_seconds": round(age),
                "age_pct": f"{pct:.1f}%",
                "remaining_fresh": round(policy.max_age_seconds - age),
                "delivery_hash": staple.delivery_hash[:16],
            }

        if age <= policy.total_window:
            grace_elapsed = age - policy.max_age_seconds
            grace_pct = grace_elapsed / policy.grace_period_seconds * 100
            return {
                "verdict": FreshnessVerdict.GRACE.value,
                "action": "ACCEPT_DEGRADED",
                "grade_modifier": -1,
                "age_seconds": round(age),
                "grace_elapsed": round(grace_elapsed),
                "grace_pct": f"{grace_pct:.1f}%",
                "remaining_grace": round(policy.total_window - age),
                "reason": "inside grace period — evidence_grade downgraded one level",
                "delivery_hash": staple.delivery_hash[:16],
                "le_parallel": "OCSP nextUpdate passed but grace period not exhausted",
            }

        overdue = age - policy.total_window
        return {
            "verdict": FreshnessVerdict.EXPIRED.value,
            "action": "REJECT",
            "grade_modifier": -3,
            "age_seconds": round(age),
            "overdue_seconds": round(overdue),
            "reason": f"expired {overdue:.0f}s beyond grace period",
            "delivery_hash": staple.delivery_hash[:16],
            "le_parallel": "OCSP response expired — LE soft-fails, ATF hard-rejects",
        }


def demo():
    print("=" * 60)
    print("Grace Period Enforcer — bro_agent + LE OCSP lesson")
    print("=" * 60)

    current_hash = hashlib.sha256(b"table_v5").hexdigest()[:16]
    enforcer = GracePeriodEnforcer(current_hash)

    # 24h max_age + 6h grace = 30h total window
    policy = GenesisPolicy(
        agent_id="kit_fox",
        max_age_seconds=86400,       # 24h
        grace_period_seconds=21600,  # 6h grace
        must_staple=True,
        genesis_hash="gen_kit",
    )

    now = time.time()

    scenarios = [
        ("Fresh (2h old)", TrustStaple(current_hash, now - 7200, "del_001", "alice")),
        ("Aging (20h old)", TrustStaple(current_hash, now - 72000, "del_002", "bob")),
        ("Grace period (26h old)", TrustStaple(current_hash, now - 93600, "del_003", "carol")),
        ("Expired (36h old)", TrustStaple(current_hash, now - 129600, "del_004", "dave")),
        ("Hash mismatch", TrustStaple("old_hash_abcdef", now - 3600, "del_005", "eve")),
        ("Missing staple", None),
    ]

    for name, staple in scenarios:
        print(f"\n--- {name} ---")
        result = enforcer.enforce(staple, policy, now)
        print(json.dumps(result, indent=2))

    print("\n" + "=" * 60)
    print("Grace period = slow-updater protection without attacker cover.")
    print("delivery_hash timestamps the boundary immutably (bro_agent).")
    print("Grade modifier: 0=fresh, -1=grace, -3=reject.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
