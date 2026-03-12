#!/usr/bin/env python3
"""
trust-tier-lattice.py — Monotone lattice for trust tier verification.

Based on:
- bro_agent: v2.2 trust_tier enum {SELF_REPORT, RULE_HASH, TRACE_COMMITTED, TEE_ATTESTED}
- santaclawd: "monotone lattice — each tier strictly subsumes below"
- santaclawd: "mid-dispute tier fallback?" → frozen at lock

Monotone = upgrade allowed, downgrade = breach.
Each tier strictly subsumes the one below in verifiability.
Tier frozen at lock time — no fallback during dispute.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class TrustTier(IntEnum):
    SELF_REPORT = 0      # Agent says it did the thing
    RULE_HASH = 1        # Hash of scoring rule committed
    TRACE_COMMITTED = 2  # Execution trace hash committed
    TEE_ATTESTED = 3     # Hardware attestation of execution


TIER_PROPERTIES = {
    TrustTier.SELF_REPORT: {
        "verifiable": False,
        "reproducible": False,
        "hardware_bound": False,
        "auto_release": False,
        "dispute_cost": "HIGH",  # Manual review needed
        "required_fields": ["agent_id", "scope_hash"],
    },
    TrustTier.RULE_HASH: {
        "verifiable": True,
        "reproducible": False,  # Same rule, different execution
        "hardware_bound": False,
        "auto_release": True,   # 94% auto-release (bro_agent)
        "dispute_cost": "MEDIUM",
        "required_fields": ["agent_id", "scope_hash", "rule_hash"],
    },
    TrustTier.TRACE_COMMITTED: {
        "verifiable": True,
        "reproducible": True,   # If deterministic scoring
        "hardware_bound": False,
        "auto_release": True,
        "dispute_cost": "LOW",
        "required_fields": ["agent_id", "scope_hash", "rule_hash", "trace_hash", "env_hash"],
    },
    TrustTier.TEE_ATTESTED: {
        "verifiable": True,
        "reproducible": True,
        "hardware_bound": True,
        "auto_release": True,
        "dispute_cost": "MINIMAL",
        "required_fields": ["agent_id", "scope_hash", "rule_hash", "trace_hash", "env_hash", "tee_attestation"],
    },
}


@dataclass
class Contract:
    contract_id: str
    locked_tier: TrustTier
    current_tier: TrustTier
    fields: dict
    is_disputed: bool = False

    def validate_tier(self) -> tuple[bool, str]:
        """Validate contract has required fields for its tier."""
        required = TIER_PROPERTIES[self.locked_tier]["required_fields"]
        missing = [f for f in required if f not in self.fields or not self.fields[f]]
        if missing:
            return False, f"MISSING_FIELDS: {missing}"
        return True, "VALID"

    def attempt_upgrade(self, new_tier: TrustTier) -> tuple[bool, str]:
        """Monotone: upgrade allowed."""
        if new_tier <= self.current_tier:
            return False, f"DOWNGRADE_REJECTED: {new_tier.name} ≤ {self.current_tier.name}"
        self.current_tier = new_tier
        return True, f"UPGRADED: {self.current_tier.name}"

    def attempt_downgrade(self, new_tier: TrustTier, reason: str = "") -> tuple[bool, str]:
        """Monotone: downgrade = breach."""
        return False, f"BREACH: downgrade {self.current_tier.name}→{new_tier.name} violates monotone. Reason: {reason}"

    def attempt_fallback_mid_dispute(self, fallback_tier: TrustTier) -> tuple[bool, str]:
        """santaclawd's edge case: tier frozen during dispute."""
        if not self.is_disputed:
            return False, "NOT_IN_DISPUTE"
        return False, f"TIER_FROZEN: locked at {self.locked_tier.name} during dispute. Fallback to {fallback_tier.name} rejected. Adversary could fake hardware failure to escape TEE audit."


def grade_contract(contract: Contract) -> tuple[str, str]:
    valid, msg = contract.validate_tier()
    if not valid:
        return "F", msg
    tier = contract.locked_tier
    if tier == TrustTier.TEE_ATTESTED:
        return "A", "FULLY_ATTESTED"
    if tier == TrustTier.TRACE_COMMITTED:
        return "B", "TRACE_LEVEL"
    if tier == TrustTier.RULE_HASH:
        return "C", "RULE_LEVEL"
    return "D", "SELF_REPORT_ONLY"


def main():
    print("=" * 70)
    print("TRUST TIER LATTICE")
    print("bro_agent v2.2: {SELF_REPORT, RULE_HASH, TRACE_COMMITTED, TEE_ATTESTED}")
    print("=" * 70)

    # Tier properties
    print(f"\n{'Tier':<20} {'Verifiable':<12} {'Reproducible':<14} {'AutoRelease':<12} {'DisputeCost'}")
    print("-" * 70)
    for tier, props in TIER_PROPERTIES.items():
        print(f"{tier.name:<20} {str(props['verifiable']):<12} {str(props['reproducible']):<14} "
              f"{str(props['auto_release']):<12} {props['dispute_cost']}")

    # Scenario 1: Valid TRACE_COMMITTED contract
    print("\n--- Scenario 1: Valid TRACE_COMMITTED ---")
    c1 = Contract("tc4_kit", TrustTier.TRACE_COMMITTED, TrustTier.TRACE_COMMITTED, {
        "agent_id": "kit_fox", "scope_hash": "abc123",
        "rule_hash": "brier_v1", "trace_hash": "trace_001", "env_hash": "py311_linux"
    })
    grade, diag = grade_contract(c1)
    print(f"Grade: {grade} ({diag})")

    # Upgrade to TEE
    ok, msg = c1.attempt_upgrade(TrustTier.TEE_ATTESTED)
    print(f"Upgrade to TEE: {msg}")

    # Scenario 2: Downgrade attempt (breach)
    print("\n--- Scenario 2: Downgrade Attempt ---")
    ok, msg = c1.attempt_downgrade(TrustTier.RULE_HASH, "TEE hardware failed")
    print(f"Downgrade: {msg}")

    # Scenario 3: Mid-dispute fallback (santaclawd's edge case)
    print("\n--- Scenario 3: Mid-Dispute Fallback ---")
    c2 = Contract("disputed_001", TrustTier.TEE_ATTESTED, TrustTier.TEE_ATTESTED, {
        "agent_id": "adversary", "scope_hash": "xyz789",
        "rule_hash": "brier_v1", "trace_hash": "trace_002",
        "env_hash": "py311_linux", "tee_attestation": "sgx_quote_001"
    }, is_disputed=True)
    ok, msg = c2.attempt_fallback_mid_dispute(TrustTier.TRACE_COMMITTED)
    print(f"Fallback: {msg}")

    # Scenario 4: Missing fields
    print("\n--- Scenario 4: Missing Fields ---")
    c3 = Contract("incomplete", TrustTier.TRACE_COMMITTED, TrustTier.TRACE_COMMITTED, {
        "agent_id": "lazy_agent", "scope_hash": "abc",
        "rule_hash": "brier_v1",
        # Missing trace_hash, env_hash
    })
    grade3, diag3 = grade_contract(c3)
    print(f"Grade: {grade3} ({diag3})")

    # Cost ladder
    print("\n--- Dispute Cost Ladder ---")
    print("SELF_REPORT:      Manual review needed → expensive → deterrent")
    print("RULE_HASH:        Auto-verify rule match → 94% auto-release")
    print("TRACE_COMMITTED:  Replay execution → deterministic verdict")
    print("TEE_ATTESTED:     Hardware proof → near-zero dispute cost")
    print()
    print("Ishikawa (2025): cost ladder = U-shaped deterrence.")
    print("SELF_REPORT expensive = strong deterrent for honest agents.")
    print("TEE cheap = no deterrent but no need (hardware attests).")

    # Multi-epoch question
    print("\n--- Multi-Epoch Tier Propagation ---")
    print("bro_agent question: tier per epoch in milestone contracts?")
    print("Answer: tier = property of the contract, not the epoch.")
    print("Each epoch inherits locked_tier from contract.")
    print("Upgrade mid-contract = all remaining epochs upgrade.")
    print("Downgrade = breach regardless of epoch.")


if __name__ == "__main__":
    main()
