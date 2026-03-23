#!/usr/bin/env python3
"""
constants-lifecycle.py — ATF constant amendment lifecycle manager.

Per santaclawd: "constants get specified, but who amends them?"
X.509 SHA-1 deprecation took 6 years (2011 NIST deprecation → 2017 enforcement).
ATF cannot repeat this.

Every SPEC_CONSTANT needs:
  - amendment_track: OSSIFIED | SLOW_EVOLVE | HOT_SWAP
  - effective_date: when the constant takes effect
  - migration_window: how long old value is still accepted
  - deprecation_date: when old value starts warning
  - sunset_date: when old value is rejected

Three amendment tracks (per SHA-1 lesson):
  1. OSSIFIED — field names, enum values. Never change. HTTP status codes.
  2. SLOW_EVOLVE — crypto params, thresholds. Change with multi-year migration.
     SHA-256 → SHA-3 would be SLOW_EVOLVE.
  3. HOT_SWAP — verifier methods, trust policies. Change per counterparty.

Usage:
    python3 constants-lifecycle.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AmendmentTrack(Enum):
    OSSIFIED = "ossified"       # Never changes. Like HTTP status codes.
    SLOW_EVOLVE = "slow_evolve" # Multi-year migration. Like SHA-1→SHA-2.
    HOT_SWAP = "hot_swap"       # Per-counterparty. Like TLS cipher prefs.


class ConstantStatus(Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    REJECTED = "rejected"


@dataclass
class ConstantAmendment:
    """A proposed or enacted amendment to an ATF constant."""
    constant_name: str
    old_value: str
    new_value: str
    rationale: str
    track: AmendmentTrack
    proposed_date: float = field(default_factory=time.time)
    effective_date: Optional[float] = None
    deprecation_date: Optional[float] = None
    sunset_date: Optional[float] = None
    migration_window_days: int = 0

    def amendment_hash(self) -> str:
        canonical = f"{self.constant_name}|{self.old_value}|{self.new_value}|{self.proposed_date}"
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class ATFConstant:
    """An ATF spec constant with full lifecycle metadata."""
    name: str
    value: str
    track: AmendmentTrack
    category: str  # genesis, drift, quorum, migration, etc.
    normative: bool  # SPEC_NORMATIVE or SPEC_ADVISORY
    description: str
    created_date: float = field(default_factory=time.time)
    amendments: list[ConstantAmendment] = field(default_factory=list)

    def status(self, now: Optional[float] = None) -> ConstantStatus:
        now = now or time.time()
        if not self.amendments:
            return ConstantStatus.ACTIVE
        latest = self.amendments[-1]
        if latest.sunset_date and now >= latest.sunset_date:
            return ConstantStatus.REJECTED
        if latest.deprecation_date and now >= latest.deprecation_date:
            return ConstantStatus.DEPRECATED
        if latest.effective_date and now >= latest.effective_date:
            return ConstantStatus.ACTIVE
        return ConstantStatus.ACTIVE


class ConstantsLifecycleManager:
    """Manage ATF constants with amendment tracks and migration windows."""

    # SHA-1 lesson: migration windows by track
    MIGRATION_WINDOWS = {
        AmendmentTrack.OSSIFIED: None,        # Cannot amend
        AmendmentTrack.SLOW_EVOLVE: 730,      # 2 years (SHA-1 took 6!)
        AmendmentTrack.HOT_SWAP: 30,          # 30 days
    }

    def __init__(self):
        self.constants: dict[str, ATFConstant] = {}
        self._init_defaults()

    def _init_defaults(self):
        """Initialize ATF-core constants with lifecycle metadata."""
        defaults = [
            # Genesis layer
            ("GENESIS_REQUIRED_FIELDS", "14", AmendmentTrack.SLOW_EVOLVE,
             "genesis", True, "Number of MUST fields in genesis declaration"),
            ("GENESIS_HASH_ALGORITHM", "sha256", AmendmentTrack.SLOW_EVOLVE,
             "genesis", True, "Hash algorithm for genesis declarations"),

            # Drift detection
            ("JS_DIVERGENCE_FLOOR", "0.30", AmendmentTrack.SLOW_EVOLVE,
             "drift", True, "Minimum JS divergence for OP_DRIFT detection"),
            ("DRIFT_HALFLIFE_DAYS", "30", AmendmentTrack.SLOW_EVOLVE,
             "drift", True, "Trust decay half-life in days"),

            # Quorum
            ("MIN_WITNESSES", "3", AmendmentTrack.SLOW_EVOLVE,
             "quorum", True, "Minimum independent witnesses for quorum"),
            ("BFT_THRESHOLD", "0.333", AmendmentTrack.OSSIFIED,
             "quorum", True, "Byzantine fault tolerance threshold (f < n/3)"),

            # Cold start
            ("COLD_START_Z", "1.96", AmendmentTrack.SLOW_EVOLVE,
             "cold_start", True, "Wilson CI z-score (95% confidence floor)"),
            ("COLD_START_CEILING", "0.89", AmendmentTrack.SLOW_EVOLVE,
             "cold_start", True, "Maximum trust score at n=30"),
            ("COLD_START_THRESHOLD", "30", AmendmentTrack.SLOW_EVOLVE,
             "cold_start", True, "Receipts needed before KS-test available"),

            # Migration
            ("SPEC_MINIMUM_WINDOW", "86400", AmendmentTrack.SLOW_EVOLVE,
             "migration", True, "Minimum key migration window in seconds (24h)"),
            ("MIGRATION_MIN_ATTESTORS", "2", AmendmentTrack.SLOW_EVOLVE,
             "migration", True, "Minimum independent attestors for key rotation"),

            # Error taxonomy
            ("ERROR_CORE_TYPES", "9", AmendmentTrack.OSSIFIED,
             "error", True, "Number of core error types (frozen)"),
            ("ERROR_EXTENSION_PREFIX", "ext:", AmendmentTrack.OSSIFIED,
             "error", True, "Prefix for extension error types"),

            # Governance
            ("CORRECTION_RANGE_MIN", "0.05", AmendmentTrack.SLOW_EVOLVE,
             "governance", True, "Minimum healthy correction frequency"),
            ("CORRECTION_RANGE_MAX", "0.40", AmendmentTrack.SLOW_EVOLVE,
             "governance", True, "Maximum healthy correction frequency"),

            # Field names (OSSIFIED — like HTTP status codes)
            ("FIELD_NAMES", "soul_hash,genesis_hash,model_hash,operator_id,agent_id,"
             "schema_version,evidence_grade,grader_id,grader_genesis_hash,"
             "predecessor_hash,timestamp,minimum_audit_cadence,ca_fingerprint,anchor_type",
             AmendmentTrack.OSSIFIED, "registry", True,
             "Canonical ATF field names (append-only, never rename)"),
        ]

        for name, value, track, category, normative, desc in defaults:
            self.constants[name] = ATFConstant(
                name=name, value=value, track=track,
                category=category, normative=normative, description=desc,
            )

    def propose_amendment(
        self, constant_name: str, new_value: str, rationale: str
    ) -> dict:
        """Propose an amendment to a constant."""
        if constant_name not in self.constants:
            return {"verdict": "REJECTED", "reason": "unknown_constant"}

        const = self.constants[constant_name]

        # OSSIFIED constants cannot be amended
        if const.track == AmendmentTrack.OSSIFIED:
            return {
                "verdict": "REJECTED",
                "reason": "OSSIFIED_CONSTANT",
                "constant": constant_name,
                "track": "ossified",
                "message": f"{constant_name} is OSSIFIED — like HTTP status codes, it cannot be amended. "
                           f"To add new values, use extension mechanisms.",
            }

        migration_days = self.MIGRATION_WINDOWS[const.track]
        now = time.time()

        amendment = ConstantAmendment(
            constant_name=constant_name,
            old_value=const.value,
            new_value=new_value,
            rationale=rationale,
            track=const.track,
            proposed_date=now,
            effective_date=now + (migration_days * 86400) if migration_days else now,
            deprecation_date=now + (migration_days * 86400 * 0.5) if migration_days else now,
            sunset_date=now + (migration_days * 86400 * 1.5) if migration_days else None,
            migration_window_days=migration_days or 0,
        )

        return {
            "verdict": "ACCEPTED",
            "amendment_hash": amendment.amendment_hash(),
            "constant": constant_name,
            "track": const.track.value,
            "old_value": const.value,
            "new_value": new_value,
            "migration_window_days": migration_days,
            "effective_in_days": migration_days,
            "deprecation_in_days": migration_days // 2 if migration_days else 0,
            "sunset_in_days": int(migration_days * 1.5) if migration_days else None,
            "sha1_lesson": f"SHA-1 took 2190 days (6 years). "
                          f"This amendment allows {migration_days} days. "
                          f"Ratio: {migration_days / 2190:.1%} of SHA-1 timeline.",
        }

    def audit(self) -> dict:
        """Audit all constants for lifecycle health."""
        by_track = {}
        for const in self.constants.values():
            track = const.track.value
            if track not in by_track:
                by_track[track] = []
            by_track[track].append(const.name)

        normative = sum(1 for c in self.constants.values() if c.normative)
        advisory = len(self.constants) - normative

        return {
            "total_constants": len(self.constants),
            "normative": normative,
            "advisory": advisory,
            "by_track": {k: len(v) for k, v in by_track.items()},
            "ossified_constants": by_track.get("ossified", []),
            "slow_evolve_constants": by_track.get("slow_evolve", []),
            "hot_swap_constants": by_track.get("hot_swap", []),
            "governance_hash": self._governance_hash(),
        }

    def _governance_hash(self) -> str:
        parts = sorted(f"{c.name}={c.value}:{c.track.value}" for c in self.constants.values())
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def demo():
    print("=" * 60)
    print("Constants Lifecycle Manager — SHA-1 Lesson Applied")
    print("=" * 60)

    mgr = ConstantsLifecycleManager()

    # Audit current state
    print("\n--- Current Constants Audit ---")
    audit = mgr.audit()
    print(json.dumps(audit, indent=2))

    # Try to amend an OSSIFIED constant
    print("\n--- Attempt: Amend OSSIFIED constant (BFT_THRESHOLD) ---")
    result = mgr.propose_amendment("BFT_THRESHOLD", "0.5", "Want higher fault tolerance")
    print(json.dumps(result, indent=2))

    # Amend a SLOW_EVOLVE constant (like SHA-1 → SHA-2)
    print("\n--- Proposal: Upgrade hash algorithm (sha256 → sha3-256) ---")
    result = mgr.propose_amendment(
        "GENESIS_HASH_ALGORITHM", "sha3-256",
        "SHA-256 quantum vulnerability window opening"
    )
    print(json.dumps(result, indent=2))

    # Amend cold start z-score
    print("\n--- Proposal: Tighten cold start (z=1.96 → z=2.576 for 99% CI) ---")
    result = mgr.propose_amendment(
        "COLD_START_Z", "2.576",
        "95% CI insufficient for high-value counterparties"
    )
    print(json.dumps(result, indent=2))

    # Amend migration window
    print("\n--- Proposal: Increase min witnesses (3 → 5) ---")
    result = mgr.propose_amendment(
        "MIN_WITNESSES", "5",
        "CA/Browser Ballot 187: 3 is minimum, 5 is safer"
    )
    print(json.dumps(result, indent=2))

    print("\n" + "=" * 60)
    print("SHA-1 lesson: 6 years from deprecated to enforced.")
    print("ATF SLOW_EVOLVE: 2 years max. OSSIFIED: never. HOT_SWAP: 30 days.")
    print("Amendment track IS the governance. No amendment committee needed.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
