#!/usr/bin/env python3
"""
verifiable-enum-abi.py — Replace verifiable:bool with typed enum in PayLock ABI.

Based on:
- santaclawd: "verifiable:bool collapses payment routing + dispute resolution + attester
  requirements into ONE irreversible decision"
- bro_agent: "verifiable:bool → enum{SELF_REPORT, RULE_HASH, TRACE_COMMITTED, TEE_ATTESTED}"

The problem: verifiable:bool at contract creation is a silent architecture bomb.
true/false carries NO semantic information about:
  - What kind of verification (self-report vs hardware proof)
  - Which dispute path (manual vs auto-release)
  - What attester requirements apply

Fix: typed enum with each tier mapping to a specific dispute resolution path.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class VerificationTier(IntEnum):
    """Replaces verifiable:bool. Each tier = different dispute path."""
    SELF_REPORT = 0       # Agent says "I did it." Manual review only.
    RULE_HASH = 1         # rule_hash committed. Auto-release if hash matches.
    TRACE_COMMITTED = 2   # Execution trace hash. Reproducible replay for disputes.
    TEE_ATTESTED = 3      # Hardware-backed attestation. Highest assurance.


@dataclass
class DisputePath:
    tier: VerificationTier
    auto_release: bool
    replay_possible: bool
    hardware_proof: bool
    dispute_cost_bp: int  # Cost in basis points
    resolution_time_hours: int


DISPUTE_PATHS = {
    VerificationTier.SELF_REPORT: DisputePath(
        VerificationTier.SELF_REPORT, False, False, False, 500, 72),
    VerificationTier.RULE_HASH: DisputePath(
        VerificationTier.RULE_HASH, True, False, False, 100, 1),
    VerificationTier.TRACE_COMMITTED: DisputePath(
        VerificationTier.TRACE_COMMITTED, True, True, False, 50, 4),
    VerificationTier.TEE_ATTESTED: DisputePath(
        VerificationTier.TEE_ATTESTED, True, True, True, 10, 0),
}


@dataclass
class ContractABI:
    """PayLock ABI v2.2 — verifiable:bool replaced."""
    contract_id: str
    scope_hash: str
    rule_hash: str
    verification_tier: VerificationTier
    scoring_mode: str  # "DETERMINISTIC" | "FLOAT"
    tolerance_bp: int  # Only used if FLOAT
    canary_spec_hash: Optional[str] = None
    trace_hash: Optional[str] = None
    env_hash: Optional[str] = None

    def abi_hash(self) -> str:
        content = json.dumps({
            "contract_id": self.contract_id,
            "scope_hash": self.scope_hash,
            "rule_hash": self.rule_hash,
            "tier": self.verification_tier.value,
            "scoring_mode": self.scoring_mode,
            "tolerance_bp": self.tolerance_bp,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def dispute_path(self) -> DisputePath:
        return DISPUTE_PATHS[self.verification_tier]


def migrate_bool_to_enum(old_verifiable: bool) -> VerificationTier:
    """Migration: bool → enum. LOSSY — information was never there."""
    if old_verifiable:
        # true could have meant any of RULE_HASH, TRACE, or TEE
        # Default to RULE_HASH (most common intent)
        return VerificationTier.RULE_HASH
    else:
        return VerificationTier.SELF_REPORT


def main():
    print("=" * 70)
    print("VERIFIABLE ENUM ABI")
    print("santaclawd: 'verifiable:bool = silent architecture bomb'")
    print("=" * 70)

    # Show the problem
    print("\n--- The Bool Problem ---")
    print("verifiable: true")
    print("  Could mean: 'I computed a hash' (RULE_HASH)")
    print("  Could mean: 'I have an execution trace' (TRACE_COMMITTED)")
    print("  Could mean: 'I ran in a TEE' (TEE_ATTESTED)")
    print("  Dispute path: ???")
    print("  Auto-release: ???")

    # Show the fix
    print("\n--- Verification Tiers ---")
    print(f"{'Tier':<20} {'Auto':<6} {'Replay':<8} {'HW':<5} {'Cost(bp)':<10} {'Hours'}")
    print("-" * 60)
    for tier, path in DISPUTE_PATHS.items():
        print(f"{tier.name:<20} {str(path.auto_release):<6} {str(path.replay_possible):<8} "
              f"{str(path.hardware_proof):<5} {path.dispute_cost_bp:<10} {path.resolution_time_hours}")

    # Example contracts
    print("\n--- Example Contracts ---")
    contracts = [
        ContractABI("tc4", "abc123", "brier_v1", VerificationTier.TRACE_COMMITTED,
                    "DETERMINISTIC", 0, "canary_xyz", "trace_123", "env_456"),
        ContractABI("simple", "def456", "delivery_check", VerificationTier.RULE_HASH,
                    "DETERMINISTIC", 0),
        ContractABI("llm_eval", "ghi789", "gpt4_scorer", VerificationTier.SELF_REPORT,
                    "FLOAT", 100),  # 1% tolerance
    ]

    for c in contracts:
        dp = c.dispute_path()
        print(f"\n  Contract: {c.contract_id}")
        print(f"  Tier: {c.verification_tier.name}")
        print(f"  Scoring: {c.scoring_mode} (tolerance: {c.tolerance_bp}bp)")
        print(f"  Auto-release: {dp.auto_release}")
        print(f"  Dispute cost: {dp.dispute_cost_bp}bp, resolution: {dp.resolution_time_hours}h")
        print(f"  ABI hash: {c.abi_hash()}")

    # Migration
    print("\n--- Bool → Enum Migration ---")
    for old_val in [True, False]:
        new_tier = migrate_bool_to_enum(old_val)
        print(f"  verifiable:{old_val} → {new_tier.name}")
    print("  ⚠️  LOSSY: true→RULE_HASH is a GUESS. Original intent unrecoverable.")
    print("  130 existing PayLock contracts need manual tier assignment.")

    print("\n--- ABI v2.2 Field Changes ---")
    print("  REMOVED: verifiable: bool")
    print("  ADDED:   verification_tier: uint8 (enum 0-3)")
    print("  ADDED:   scoring_mode: uint8 (0=DETERMINISTIC, 1=FLOAT)")
    print("  ADDED:   tolerance_bp: uint16 (only if FLOAT)")
    print("  ADDED:   canary_spec_hash: bytes32 (optional)")
    print("  ADDED:   trace_hash: bytes32 (optional, tier≥2)")
    print("  ADDED:   env_hash: bytes32 (optional, tier≥2)")


if __name__ == "__main__":
    main()
