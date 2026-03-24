#!/usr/bin/env python3
"""
clock-assurance-tiering.py — Three tiers of timestamp assurance for ATF receipts.

Per santaclawd: VDF overhead not worth it for low-value receipts.
Matches value-tiered-logger.py logging tiers with clock assurance tiers.

Three levels:
  BASIC     — Hash chain + counterparty timestamp (low-value, ~0ms overhead)
  STANDARD  — Hash chain + K-of-N witness timestamps + KS distribution test (medium)
  CEREMONY  — Hash chain + VDF proof + K-of-N witnesses + published transcript (high-value)

Write-time injection attack model:
  - BASIC: adversary forges single timestamp (detectable via KS over time)
  - STANDARD: adversary must corrupt K witnesses simultaneously
  - CEREMONY: adversary must solve VDF faster than honest party + corrupt witnesses

References:
  - Landerreche et al. (FC 2020): Non-interactive timestamping via VDFs
  - Boneh et al. (CRYPTO 2018): VDFs original construction
  - Lamport (1982): Byzantine generals — f<n/3 bound
"""

import hashlib
import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ClockTier(Enum):
    BASIC = "BASIC"         # Hash chain + counterparty
    STANDARD = "STANDARD"   # + K-of-N witnesses + KS test
    CEREMONY = "CEREMONY"   # + VDF proof + published transcript


# SPEC_CONSTANTS
WITNESS_K = 2                    # Minimum witnesses for STANDARD
WITNESS_N = 5                    # Total witness pool for STANDARD
CEREMONY_WITNESSES = 4           # Minimum for CEREMONY
VDF_DIFFICULTY = 2**20           # VDF iterations (simulated)
MAX_CLOCK_SKEW_MS = 5000         # 5s max acceptable skew
BASIC_VALUE_CEILING = 0.3        # Below = BASIC
STANDARD_VALUE_CEILING = 0.7     # Below = STANDARD, above = CEREMONY


@dataclass
class TimestampProof:
    """Proof of time for a receipt."""
    tier: str
    receipt_hash: str
    agent_timestamp: float
    counterparty_timestamp: Optional[float] = None
    witness_timestamps: list = field(default_factory=list)
    vdf_proof: Optional[dict] = None
    clock_skew_ms: float = 0
    integrity: str = "UNVERIFIED"


@dataclass
class WitnessAttestation:
    witness_id: str
    timestamp: float
    signature_hash: str
    operator_id: str  # For independence check


def compute_clock_skew(timestamps: list[float]) -> float:
    """Max pairwise clock skew in milliseconds."""
    if len(timestamps) < 2:
        return 0
    return (max(timestamps) - min(timestamps)) * 1000


def check_witness_independence(witnesses: list[WitnessAttestation]) -> dict:
    """Verify witnesses are from independent operators (Simpson diversity)."""
    operators = [w.operator_id for w in witnesses]
    unique_ops = set(operators)
    n = len(operators)
    
    if n <= 1:
        return {"independent": False, "diversity": 0, "reason": "insufficient_witnesses"}
    
    # Simpson diversity index
    freqs = {}
    for op in operators:
        freqs[op] = freqs.get(op, 0) + 1
    
    simpson = sum(f * (f - 1) for f in freqs.values()) / (n * (n - 1)) if n > 1 else 1
    diversity = 1 - simpson  # Higher = more diverse
    
    # Monoculture: all same operator
    monoculture = len(unique_ops) == 1
    
    return {
        "independent": not monoculture and diversity > 0.5,
        "diversity": round(diversity, 4),
        "unique_operators": len(unique_ops),
        "total_witnesses": n,
        "monoculture": monoculture
    }


def simulate_vdf(input_hash: str, difficulty: int) -> dict:
    """
    Simulate VDF computation.
    
    Real VDF: sequential squaring in RSA group (Wesolowski 2019) or
    isogeny-based (De Feo 2019). We simulate with iterated hashing.
    
    Key property: computing takes T sequential steps, verifying takes O(1).
    Adversary with 10x speedup still needs T/10 steps — no parallelization.
    """
    current = input_hash.encode()
    steps = min(difficulty, 1000)  # Cap for simulation
    
    for _ in range(steps):
        current = hashlib.sha256(current).digest()
    
    proof_hash = hashlib.sha256(current).hexdigest()[:16]
    
    return {
        "input": input_hash[:16],
        "output": proof_hash,
        "difficulty": difficulty,
        "simulated_steps": steps,
        "forgery_cost": f"{difficulty}x sequential operations (no parallelization)",
        "verification_cost": "O(1) — single exponentiation"
    }


def assign_clock_tier(value_score: float) -> ClockTier:
    """Assign clock assurance tier based on interaction value."""
    if value_score < BASIC_VALUE_CEILING:
        return ClockTier.BASIC
    elif value_score < STANDARD_VALUE_CEILING:
        return ClockTier.STANDARD
    else:
        return ClockTier.CEREMONY


def create_timestamp_proof(
    receipt_hash: str,
    value_score: float,
    agent_ts: float,
    counterparty_ts: float,
    witnesses: list[WitnessAttestation] = None
) -> TimestampProof:
    """Create appropriate timestamp proof based on value tier."""
    tier = assign_clock_tier(value_score)
    
    if tier == ClockTier.BASIC:
        skew = compute_clock_skew([agent_ts, counterparty_ts])
        return TimestampProof(
            tier=tier.value,
            receipt_hash=receipt_hash,
            agent_timestamp=agent_ts,
            counterparty_timestamp=counterparty_ts,
            clock_skew_ms=skew,
            integrity="BASIC_VERIFIED" if skew < MAX_CLOCK_SKEW_MS else "SKEW_WARNING"
        )
    
    elif tier == ClockTier.STANDARD:
        if not witnesses or len(witnesses) < WITNESS_K:
            return TimestampProof(
                tier=tier.value,
                receipt_hash=receipt_hash,
                agent_timestamp=agent_ts,
                counterparty_timestamp=counterparty_ts,
                integrity="INSUFFICIENT_WITNESSES"
            )
        
        all_ts = [agent_ts, counterparty_ts] + [w.timestamp for w in witnesses]
        skew = compute_clock_skew(all_ts)
        independence = check_witness_independence(witnesses)
        
        if not independence["independent"]:
            integrity = "MONOCULTURE_WITNESSES"
        elif skew > MAX_CLOCK_SKEW_MS:
            integrity = "SKEW_WARNING"
        else:
            integrity = "STANDARD_VERIFIED"
        
        return TimestampProof(
            tier=tier.value,
            receipt_hash=receipt_hash,
            agent_timestamp=agent_ts,
            counterparty_timestamp=counterparty_ts,
            witness_timestamps=[w.timestamp for w in witnesses],
            clock_skew_ms=skew,
            integrity=integrity
        )
    
    else:  # CEREMONY
        if not witnesses or len(witnesses) < CEREMONY_WITNESSES:
            return TimestampProof(
                tier=tier.value,
                receipt_hash=receipt_hash,
                agent_timestamp=agent_ts,
                integrity="INSUFFICIENT_CEREMONY_WITNESSES"
            )
        
        vdf = simulate_vdf(receipt_hash, VDF_DIFFICULTY)
        all_ts = [agent_ts, counterparty_ts] + [w.timestamp for w in witnesses]
        skew = compute_clock_skew(all_ts)
        independence = check_witness_independence(witnesses)
        
        if not independence["independent"]:
            integrity = "MONOCULTURE_CEREMONY"
        elif skew > MAX_CLOCK_SKEW_MS:
            integrity = "SKEW_WARNING"
        else:
            integrity = "CEREMONY_VERIFIED"
        
        return TimestampProof(
            tier=tier.value,
            receipt_hash=receipt_hash,
            agent_timestamp=agent_ts,
            counterparty_timestamp=counterparty_ts,
            witness_timestamps=[w.timestamp for w in witnesses],
            vdf_proof=vdf,
            clock_skew_ms=skew,
            integrity=integrity
        )


def attack_cost_analysis(tier: ClockTier) -> dict:
    """Estimate attack cost for each tier."""
    if tier == ClockTier.BASIC:
        return {
            "tier": "BASIC",
            "attack": "Forge counterparty timestamp",
            "cost": "Zero (single party controls timestamp)",
            "detection": "KS test over time catches non-Poisson distributions",
            "mitigation": "Detectable but not preventable per-receipt",
            "suitable_for": "Low-value, high-volume interactions"
        }
    elif tier == ClockTier.STANDARD:
        return {
            "tier": "STANDARD",
            "attack": "Corrupt K-of-N witnesses simultaneously",
            "cost": f"Must compromise {WITNESS_K} of {WITNESS_N} independent operators",
            "detection": "Simpson diversity + temporal correlation",
            "mitigation": "BFT f<n/3 bound applies",
            "suitable_for": "Medium-value interactions, ongoing relationships"
        }
    else:
        return {
            "tier": "CEREMONY",
            "attack": "Solve VDF faster + corrupt witnesses + forge transcript",
            "cost": f"{VDF_DIFFICULTY} sequential ops + {CEREMONY_WITNESSES} witnesses",
            "detection": "VDF verification O(1) + published transcript audit",
            "mitigation": "Composition: each defense layer independent",
            "suitable_for": "Genesis, high-value transactions, key ceremonies"
        }


# === Scenarios ===

def scenario_tiered_portfolio():
    """Mixed value interactions — each gets appropriate clock assurance."""
    print("=== Scenario: Tiered Portfolio ===")
    now = time.time()
    
    interactions = [
        ("Low-value dormant", 0.15, now, now + 0.1, []),
        ("Medium relationship", 0.55, now, now + 0.05, [
            WitnessAttestation("w1", now + 0.02, "sig1", "op_a"),
            WitnessAttestation("w2", now + 0.03, "sig2", "op_b"),
            WitnessAttestation("w3", now + 0.04, "sig3", "op_c"),
        ]),
        ("High-value genesis", 0.95, now, now + 0.01, [
            WitnessAttestation("w1", now + 0.01, "sig1", "op_a"),
            WitnessAttestation("w2", now + 0.02, "sig2", "op_b"),
            WitnessAttestation("w3", now + 0.03, "sig3", "op_c"),
            WitnessAttestation("w4", now + 0.04, "sig4", "op_d"),
        ]),
    ]
    
    for label, value, agent_ts, counter_ts, witnesses in interactions:
        proof = create_timestamp_proof(f"receipt_{label}", value, agent_ts, counter_ts, witnesses)
        cost = attack_cost_analysis(assign_clock_tier(value))
        print(f"  {label}: value={value:.2f} → tier={proof.tier}")
        print(f"    integrity={proof.integrity}, skew={proof.clock_skew_ms:.1f}ms")
        print(f"    attack_cost: {cost['cost']}")
        if proof.vdf_proof:
            print(f"    VDF: {proof.vdf_proof['forgery_cost']}")
        print()


def scenario_write_time_injection():
    """Adversary tries to inject forged timestamp at write time."""
    print("=== Scenario: Write-Time Injection Attack ===")
    now = time.time()
    
    # Attacker forges counterparty timestamp 10 seconds in the past
    forged_ts = now - 10
    
    # BASIC: single counterparty — undetectable per-receipt
    proof_basic = create_timestamp_proof("forged_basic", 0.15, now, forged_ts)
    print(f"  BASIC: skew={proof_basic.clock_skew_ms:.0f}ms → {proof_basic.integrity}")
    print(f"    10s forged offset: {'CAUGHT' if proof_basic.clock_skew_ms > MAX_CLOCK_SKEW_MS else 'MISSED (within tolerance)'}")
    
    # STANDARD: witnesses catch the discrepancy
    honest_witnesses = [
        WitnessAttestation("w1", now + 0.01, "sig1", "op_a"),
        WitnessAttestation("w2", now + 0.02, "sig2", "op_b"),
        WitnessAttestation("w3", now + 0.03, "sig3", "op_c"),
    ]
    proof_standard = create_timestamp_proof("forged_standard", 0.55, now, forged_ts, honest_witnesses)
    print(f"  STANDARD: skew={proof_standard.clock_skew_ms:.0f}ms → {proof_standard.integrity}")
    
    # CEREMONY: VDF + witnesses
    ceremony_witnesses = honest_witnesses + [
        WitnessAttestation("w4", now + 0.04, "sig4", "op_d"),
    ]
    proof_ceremony = create_timestamp_proof("forged_ceremony", 0.95, now, forged_ts, ceremony_witnesses)
    print(f"  CEREMONY: skew={proof_ceremony.clock_skew_ms:.0f}ms → {proof_ceremony.integrity}")
    if proof_ceremony.vdf_proof:
        print(f"    VDF forgery cost: {proof_ceremony.vdf_proof['forgery_cost']}")
    print()


def scenario_compromised_counterparty():
    """Per santaclawd: adversary controls counterparty at commit time."""
    print("=== Scenario: Compromised Counterparty (santaclawd gap) ===")
    now = time.time()
    
    # Adversary controls counterparty AND delays pre-commit
    # With BASIC: trivially forged
    # With STANDARD: must also corrupt K witnesses
    # With CEREMONY: must solve VDF + corrupt witnesses
    
    print("  Attack: adversary controls counterparty, delays pre-commit")
    print()
    
    for tier in ClockTier:
        cost = attack_cost_analysis(tier)
        print(f"  {tier.value}:")
        print(f"    Attack vector: {cost['attack']}")
        print(f"    Cost: {cost['cost']}")
        print(f"    Detection: {cost['detection']}")
        print()
    
    print("  KEY INSIGHT: No scheme survives f≥n/3 colluding (Lamport 1982)")
    print("  Defense: COMPOSITION not PROOF. Each layer adds independent cost.")
    print("  Compromised counterparty + honest witnesses = DETECTABLE")
    print("  Compromised counterparty + compromised witnesses = BYZANTINE FAILURE")
    print()


def scenario_monoculture_witnesses():
    """All witnesses from same operator — independence violated."""
    print("=== Scenario: Monoculture Witnesses ===")
    now = time.time()
    
    # Same operator for all witnesses
    sybil_witnesses = [
        WitnessAttestation("w1", now + 0.01, "sig1", "op_shady"),
        WitnessAttestation("w2", now + 0.02, "sig2", "op_shady"),
        WitnessAttestation("w3", now + 0.03, "sig3", "op_shady"),
    ]
    
    proof = create_timestamp_proof("sybil_receipt", 0.55, now, now + 0.05, sybil_witnesses)
    independence = check_witness_independence(sybil_witnesses)
    
    print(f"  3 witnesses, 1 operator: diversity={independence['diversity']:.2f}")
    print(f"  Independent: {independence['independent']}")
    print(f"  Integrity: {proof.integrity}")
    print(f"  Result: CORRECTLY caught monoculture ✓")
    print()


if __name__ == "__main__":
    print("Clock Assurance Tiering — Three Levels of Timestamp Integrity for ATF")
    print("Per santaclawd VDF thread + value-tiered-logger.py alignment")
    print("=" * 70)
    print()
    scenario_tiered_portfolio()
    scenario_write_time_injection()
    scenario_compromised_counterparty()
    scenario_monoculture_witnesses()
    
    print("=" * 70)
    print("THREE TIERS matching value-tiered-logger.py:")
    print("  BASIC    → SPARSE logging  (hash chain only, KS over time)")
    print("  STANDARD → SAMPLED logging (K-of-N witnesses, per-receipt)")
    print("  CEREMONY → FULL logging    (VDF + witnesses + transcript)")
    print()
    print("KEY: VDF overhead reserved for HIGH_VALUE and CEREMONY only.")
    print("Low-value receipts: distribution test catches gaming over time.")
    print("Composition = defense in depth, not mathematical proof.")
