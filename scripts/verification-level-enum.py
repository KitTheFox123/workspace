#!/usr/bin/env python3
"""
verification-level-enum.py — Replace verifiable:bool with typed verification enum.

Based on:
- santaclawd: "verifiable:bool collapses payment routing + dispute resolution + 
  attester requirements into ONE irreversible decision"
- Wasmtime docs: NaN canonicalization + relaxed SIMD determinism flags

The problem: verifiable:bool = {true, false}.
  true collapses: TEE attestation, self-report, rule_hash, trace commit, ZK proof
  All into ONE routing path. No audit granularity.

Fix: typed enum with each level mapping to:
  1. Verification method
  2. Dispute resolution path
  3. Required evidence
  4. Audit depth
"""

from dataclasses import dataclass
from enum import IntEnum
import json


class VerificationLevel(IntEnum):
    """Replaces verifiable:bool. Each level = distinct audit path."""
    SELF_REPORT = 0       # Agent says "I did it" — no proof
    RULE_HASH = 1         # Hash of scoring rule committed
    TRACE_COMMITTED = 2   # Execution trace hash committed
    ENV_LOCKED = 3        # Environment hash + trace committed
    TEE_ATTESTED = 4      # Trusted Execution Environment attestation
    ZK_PROVEN = 5         # Zero-knowledge proof of correct execution


@dataclass
class VerificationSpec:
    level: VerificationLevel
    verification_method: str
    dispute_path: str
    required_evidence: list[str]
    audit_depth: str
    deterministic_required: bool
    
    def to_abi_field(self) -> dict:
        return {
            "verification_level": self.level.value,
            "verification_name": self.level.name,
            "method": self.verification_method,
            "dispute_path": self.dispute_path,
            "evidence": self.required_evidence,
            "deterministic": self.deterministic_required,
        }


VERIFICATION_SPECS = {
    VerificationLevel.SELF_REPORT: VerificationSpec(
        VerificationLevel.SELF_REPORT,
        "Agent attestation only",
        "REPUTATION_ONLY — no machine-verifiable dispute possible",
        ["agent_id", "timestamp"],
        "NONE",
        False,
    ),
    VerificationLevel.RULE_HASH: VerificationSpec(
        VerificationLevel.RULE_HASH,
        "Hash of scoring rule committed at lock time",
        "RULE_MISMATCH — verify committed rule matches executed rule",
        ["rule_hash", "agent_id", "timestamp"],
        "WHAT",
        False,
    ),
    VerificationLevel.TRACE_COMMITTED: VerificationSpec(
        VerificationLevel.TRACE_COMMITTED,
        "Execution trace hash committed post-execution",
        "TRACE_REPLAY — re-execute and compare trace hashes",
        ["rule_hash", "trace_hash", "input_hash", "output_hash"],
        "WHAT + HOW",
        True,  # Must be deterministic for replay to work
    ),
    VerificationLevel.ENV_LOCKED: VerificationSpec(
        VerificationLevel.ENV_LOCKED,
        "Environment fingerprint + trace committed",
        "ENV_MISMATCH — verify environment matches declared config",
        ["rule_hash", "trace_hash", "env_hash", "input_hash", "output_hash"],
        "WHAT + HOW + WHERE",
        True,
    ),
    VerificationLevel.TEE_ATTESTED: VerificationSpec(
        VerificationLevel.TEE_ATTESTED,
        "TEE remote attestation (SGX/SEV-SNP/TrustZone)",
        "ATTESTATION_VERIFY — check TEE quote against manufacturer root",
        ["rule_hash", "tee_quote", "tee_measurement", "output_hash"],
        "HARDWARE_BOUND",
        True,
    ),
    VerificationLevel.ZK_PROVEN: VerificationSpec(
        VerificationLevel.ZK_PROVEN,
        "Zero-knowledge proof of correct execution",
        "PROOF_VERIFY — verify ZK proof on-chain or off-chain",
        ["rule_hash", "zk_proof", "public_inputs", "output_hash"],
        "MATHEMATICAL",
        True,
    ),
}


def grade_verification(level: VerificationLevel) -> tuple[str, str]:
    if level >= VerificationLevel.ZK_PROVEN:
        return "A+", "MATHEMATICAL_CERTAINTY"
    if level >= VerificationLevel.TEE_ATTESTED:
        return "A", "HARDWARE_TRUST"
    if level >= VerificationLevel.ENV_LOCKED:
        return "B+", "FULL_REPLAY"
    if level >= VerificationLevel.TRACE_COMMITTED:
        return "B", "PROCESS_AUDITABLE"
    if level >= VerificationLevel.RULE_HASH:
        return "C", "RULE_COMMITTED"
    return "F", "TRUST_ME_BRO"


def demonstrate_bool_collapse():
    """Show what verifiable:bool loses."""
    print("--- verifiable:bool Collapse ---")
    print("verifiable: true  → could mean ANY of:")
    for level in VerificationLevel:
        if level > VerificationLevel.SELF_REPORT:
            spec = VERIFICATION_SPECS[level]
            print(f"  Level {level.value}: {level.name} — {spec.verification_method}")
    print()
    print("All collapsed into ONE boolean. One routing path.")
    print("TEE attestation and rule_hash get same dispute resolution.")
    print("That's like treating a notarized contract and a pinky promise the same.")


def main():
    print("=" * 70)
    print("VERIFICATION LEVEL ENUM")
    print("santaclawd: 'verifiable:bool = silent architecture bomb'")
    print("=" * 70)

    demonstrate_bool_collapse()

    print("\n--- Verification Level Specs ---")
    print(f"{'Level':<20} {'Grade':<6} {'Audit':<15} {'Deterministic':<14} {'Dispute Path'}")
    print("-" * 85)
    for level, spec in VERIFICATION_SPECS.items():
        grade, diag = grade_verification(level)
        det = "YES" if spec.deterministic_required else "no"
        print(f"{level.name:<20} {grade:<6} {spec.audit_depth:<15} {det:<14} {spec.dispute_path[:35]}")

    # ABI v2.1 field
    print("\n--- PayLock ABI v2.1 Field ---")
    print("OLD: verifiable: bool")
    print("NEW: verification_level: uint8  // 0-5, see VerificationLevel enum")
    print()
    print("Each level REQUIRES specific evidence fields:")
    for level, spec in VERIFICATION_SPECS.items():
        print(f"  {level.value} ({level.name}): {', '.join(spec.required_evidence)}")

    # WASM determinism note
    print("\n--- WASM Determinism for Levels 2+ ---")
    print("Wasmtime config required for TRACE_COMMITTED and above:")
    print("  cranelift_nan_canonicalization: true")
    print("  relaxed_simd_deterministic: true")
    print("  wasi-virt: virtualize clocks + filesystem")
    print("  env_hash = hash(wasmtime_version + config_flags + target_triple)")
    print()
    print("Or: use integer arithmetic (basis points) and skip float entirely.")
    print("integer-brier-scorer.py = Level 3 without WASM overhead.")


if __name__ == "__main__":
    main()
